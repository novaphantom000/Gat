# blender -b --python tools/prep_guns.py   ->  build/guns.npz   (Quaternius Ultimate Gun Pack, CC0, unzipped under raw/guns)
import sys, os
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import bl

DIR = os.path.join(here, '..', 'raw', 'guns', 'OBJ')
OUT = os.path.join(here, '..', 'build', 'guns.npz')
# file, metres per unit, hand position in file units
GUNS = [('Pistol_1', 0.108, (-0.10, -0.14)), ('SubmachineGun_1', 0.14, (-0.16, -0.12)), ('Shotgun_1', 0.19, (-0.03, 0.03))]
MAX_TRIS = 380


def srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def read_mtl(path):
    cols, cur = {}, None
    for l in open(path):
        a = l.split()
        if a and a[0] == 'newmtl':
            cur = a[1]
        elif a and a[0] == 'Kd':
            cols[cur] = srgb(np.array([float(x) for x in a[1:4]]))
    return cols


def read_obj(path):
    v, f, m, cur = [], [], [], None
    for l in open(path):
        a = l.split()
        if not a:
            continue
        if a[0] == 'v':
            v.append([float(x) for x in a[1:4]])
        elif a[0] == 'usemtl':
            cur = a[1]
        elif a[0] == 'f':
            ids = [int(x.split('/')[0]) - 1 for x in a[1:]]
            for k in range(1, len(ids) - 1):
                f.append((ids[0], ids[k], ids[k + 1]))
                m.append(cur)
    return np.array(v), np.array(f), m


def main():
    bl.reset()
    out = {}
    for k, (name, sc, hand) in enumerate(GUNS):
        v, f, m = read_obj(f'{DIR}/{name}.obj')
        cols = read_mtl(f'{DIR}/{name}.mtl')
        fc = np.array([cols[x] for x in m])
        v = v - [hand[0], hand[1], 0]
        v = np.stack([-v[:, 2], v[:, 1], v[:, 0]], 1) * sc
        p, t, inv = bl.weld(v, f)
        w = inv[f]
        keep = (w[:, 0] != w[:, 1]) & (w[:, 1] != w[:, 2]) & (w[:, 0] != w[:, 2])
        q, nt, _ = bl.decimate(p, t, MAX_TRIS)
        ti, _ = bl.sample_surface(p, t, q[nt].mean(1))
        out[f'gun{k}_p'] = q.astype(np.float32)
        out[f'gun{k}_t'] = nt
        out[f'gun{k}_c'] = (fc[keep][ti] * 255 + 0.5).astype(np.uint8)
        print(name, len(nt), 'tris')
    np.savez_compressed(OUT, **out)


main()
