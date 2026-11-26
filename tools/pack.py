# packs the blender intermediates into build/assets.c. run through `make`, or `make assets` to redo the blender step
import lzma, os, subprocess, struct, sys
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import meshenc, carlook, gltfio

BUILD = os.path.join(here, '..', 'build')
BLENDER = os.environ.get('BLENDER', '/Applications/Blender.app/Contents/MacOS/Blender')
CARS = ['sedan', 'compact', 'hatchback', 'minivan', 'pickup', 'suv', 'wagon', 'offroad']
MASS = dict(sedan=1500, compact=1200, hatchback=1250, minivan=1900, pickup=2000, suv=2000, wagon=1600, offroad=2100,
            cop=1700, taxi=1600)
CLIP_Q, HIPS_Q = 256, 1000


def ensure(npz, script, force):
    path = os.path.join(BUILD, npz)
    stale = os.path.exists(path) and os.path.getmtime(path) < os.path.getmtime(os.path.join(here, script))
    if force or stale or not os.path.exists(path):
        subprocess.run([BLENDER, '-b', '--python', os.path.join(here, script)], check=True, stdout=subprocess.DEVNULL)
    return np.load(path)


def car_record(name, d, body):
    wp = d[f'{name}_wpos']
    r, w = d[f'{name}_wr']
    m = body
    size = np.ptp(m['p'], axis=0)
    gp = m['glass']
    seat = [0.36 * size[0] / 1.9, 0.42 * m['p'][:, 1].max(), gp[:, 2].max() - 1.1]
    return wp, r, size, seat


def wheel_mesh(d, name):
    p, t = d[f'{name}_wv'].astype(float), d[f'{name}_wt']
    r = d[f'{name}_wr'][0]
    rad = np.hypot(p[:, 1], p[:, 2])
    cen = p[t].mean(1)
    cls = (np.hypot(cen[:, 1], cen[:, 2]) < 0.67 * r).astype(int)
    nv, nt, nn, src = meshenc.split(p, t, cls, 50)
    key = np.zeros(len(nv), int)
    key[nt.ravel()] = np.repeat(cls, 3)
    rgb = np.where(key[:, None] == 1, [0.58, 0.58, 0.60], [0.07, 0.07, 0.075])
    hub = rad[src] < 0.01 * r
    rgb[hub] = [0.25, 0.25, 0.27]
    rgba = np.zeros((len(nv), 4), np.uint8)
    rgba[:, :3] = np.round(rgb * 255)
    rgba[:, 3] = 0
    return meshenc.mesh(nv, nt, nn, rgba), len(nt)


def car_blob(d, name, kind=None, base=None):
    base = base or name
    m = carlook.load(d, base)
    extra, liv = [], None
    if kind == 'cop':
        liv = carlook.livery(m, 'cop')
        x = lambda k: (d[f'x_{k}_p'].astype(float), d[f'x_{k}_t'])
        black, red, blue = (0.05, 0.05, 0.06), (1.0, 0.08, 0.08), (0.12, 0.25, 1.0)
        extra = [x('base') + (black, carlook.PLAIN), x('push') + (black, carlook.PLAIN),
                 x('red') + (red, carlook.SIREN), x('blue') + (blue, carlook.SIREN)]
    if kind == 'taxi':
        liv = carlook.livery(m, 'taxi')
        x = lambda k: (d[f'x_{k}_p'].astype(float), d[f'x_{k}_t'])
        extra = [x('signbase') + ((0.05, 0.05, 0.06), carlook.PLAIN), x('sign') + ((1.0, 0.93, 0.62), carlook.PLAIN)]
    nv, nt, nn, rgb, mat = carlook.build(m, extra, liv)
    body = carlook.finish(nv, nt, nn, rgb, mat)
    wp, r, size, seat = car_record(base, d, m)
    wm, wtris = wheel_mesh(d, base)
    head = struct.pack('<12f', *wp.ravel()) + struct.pack('<f3f3ff', r, *size, *seat, MASS[kind or name])
    return head + wm + body, len(nt), wtris


def cars_section():
    d = ensure('cars.npz', 'prep_cars.py', FORCE)
    out, info = b'', []
    for n in CARS:
        b, tris, wt = car_blob(d, n)
        out += b
        info.append((n, tris, wt))
    for kind, base in (('cop', 'sedan'), ('taxi', 'wagon')):
        b, tris, wt = car_blob(d, kind, kind, base)
        out += b
        info.append((kind, tris, wt))
    return out, info


def skinned(d, key):
    p, t = d[f'{key}_p'].astype(float), d[f'{key}_t']
    nrm = meshenc.smooth(p, t)
    return meshenc.mesh(p, t, nrm, skin=(d[f'{key}_reg'], d[f'{key}_ao'], d[f'{key}_ids'], d[f'{key}_w'])), len(t)


def clip_blob(rot, hips, loop):
    nf, nb = rot.shape[:2]
    q = (np.round(rot[:, :, :3] * CLIP_Q).astype(np.int64) * (4096 // CLIP_Q)).transpose(1, 2, 0).reshape(nb * 3, nf)
    h = (np.round(hips * HIPS_Q).astype(np.int64) * (1000 // HIPS_Q)).T
    b = struct.pack('<HB', nf, int(loop))
    return b + meshenc.planes(meshenc.delta16(q)) + meshenc.planes(meshenc.delta16(h))


def chars_section():
    d = ensure('chars.npz', 'prep_chars.py', FORCE)
    names = list(d['names'])
    n = len(names)
    b = struct.pack('<B', n) + np.array(d['parent'], np.int8).tobytes()
    b += d['bind_pos'].astype('<f4').tobytes() + d['bind_rot'].astype('<f4').tobytes()
    b += bytes([names.index('Head'), names.index('hand_r'), names.index('hand_l'), 0, names.index('spine_02')])
    info = []
    for k in range(2):
        m, t = skinned(d, f'body{k}')
        b += m
        info.append((f'body{k}', t))
    for k in range(6):
        m, t = skinned(d, f'hair{k}')
        b += m
        info.append((f'hair{k}', t))
    clips = b''
    for i in range(22):
        clips += clip_blob(d[f'clip{i}_rot'], d[f'clip{i}_hips'], bool(d[f'clip{i}_loop']))
    return b, info, clips


def guns_section():
    d = ensure('guns.npz', 'prep_guns.py', FORCE)
    out, info = b'', []
    for k in range(3):
        p, t, c = d[f'gun{k}_p'].astype(float), d[f'gun{k}_t'], d[f'gun{k}_c']
        _, uid = np.unique(c, axis=0, return_inverse=True)
        nv, nt, nn, src = meshenc.split(p, t, uid.ravel(), 35)
        col = np.zeros((len(nv), 4), np.uint8)
        fc = np.zeros((len(nv), 3), np.uint8)
        fc[nt.ravel()] = np.repeat(c, 3, axis=0)
        col[:, :3] = fc
        col[:, 3] = 0
        out += meshenc.mesh(nv, nt, nn, col)
        info.append((f'gun{k}', len(nt)))
    return out, info


def heli_section():
    # one glb: body + rotor, 3 blades on a mast. origin = rotor hub, y up, nose +z, metres
    g = gltfio.Gltf(os.path.join(here, '..', 'raw', 'heli', 'heli.glb'))
    rot = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
    hub_y, scale = 1.39, 2.2
    dark, blue, white, glass = (0.09, 0.09, 0.10), (0.08, 0.16, 0.55), (0.93, 0.94, 0.96), (0.05, 0.08, 0.12)
    parts = {'body': ([], [], []), 'rotor': ([], [], [])}
    for k in range(4):
        d = g.prim(0, k)
        p = d['pos'] * 100 @ rot.T
        p = (p - [0, hub_y, 0]) * scale
        c = p[d['idx']].mean(1)
        y, z = c[:, 1] / scale + hub_y, c[:, 2] / scale
        col = np.tile(dark, (len(c), 1))
        if d['mat'] == 0:
            band = (y > 0.5) & (y < 0.7) & (z > -0.6)
            boom = (z < -1.3) & (z > -2.1) & (y > 0.75) & (y < 1.05)
            col[band] = white
            col[boom] = blue
        elif d['mat'] == 1:
            col[:] = blue
        elif d['mat'] == 2:
            col[:] = glass
        dst = parts['rotor' if d['mat'] == 3 else 'body']
        dst[0].append(p)
        dst[1].append(d['idx'] + sum(len(a) for a in dst[0][:-1]))
        dst[2].append(col)
    out, info = b'', []
    for name in ('body', 'rotor'):
        p, t, col = (np.concatenate(a) for a in parts[name])
        p, t, _ = _weld(p, t)
        fcol = col
        nv, nt, nn, src = meshenc.split(p, t, _key(fcol), 35)
        rgba = np.zeros((len(nv), 4), np.uint8)
        fc = np.zeros((len(nv), 3))
        fc[nt.ravel()] = np.repeat(fcol, 3, axis=0)
        rgba[:, :3] = np.round(fc * 255)
        out += meshenc.mesh(nv, nt, nn, rgba)
        info.append((name, len(nt)))
    return out, info


def _key(col):
    _, k = np.unique(col, axis=0, return_inverse=True)
    return k.ravel()


def _weld(p, t):
    q = np.round(p / 1e-4).astype(np.int64)
    _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    return p[first], inv[t], inv


def c_array(blob):
    lines = ['// generated by tools/pack.py', '', f'const int assets_blob_len = {len(blob)};',
             'const unsigned char assets_blob[] = {']
    for i in range(0, len(blob), 24):
        lines.append('    ' + ','.join(str(x) for x in blob[i:i + 24]) + ',')
    lines.append('};')
    return '\n'.join(lines) + '\n'


def lz(raw):
    f = [{'id': lzma.FILTER_LZMA1, 'preset': 9 | lzma.PRESET_EXTREME, 'lc': LC, 'lp': 0, 'pb': 0, 'dict_size': 1 << 22}]
    return bytes([LC]) + lzma.compress(raw, format=lzma.FORMAT_RAW, filters=f)


LC = 3


def main():
    cars, cinfo = cars_section()
    chars, hinfo, clips = chars_section()
    guns, ginfo = guns_section()
    heli, hl = heli_section()
    secs = [('cars', cars), ('chars', chars), ('guns', guns), ('clips', clips), ('heli', heli)]
    blob = struct.pack('<I', len(secs)) + b''.join(struct.pack('<I', len(r)) for _, r in secs)
    blob += lz(b''.join(r for _, r in secs))
    print(f'raw {sum(len(r) for _, r in secs)} packed {len(blob)}')
    print('cars', [(n, t, w) for n, t, w in cinfo])
    print('chars', hinfo, 'guns', ginfo, 'heli', hl)
    open(os.path.join(BUILD, 'assets.c'), 'w').write(c_array(blob))


FORCE = '--force' in sys.argv
main()
