# blender -b --python tools/prep_chars.py   ->  build/chars.npz
import sys, os
import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import bl
from gltfio import Gltf, qmul, qinv, qrot, qmat

RAW = os.path.join(here, '..', 'raw')
UAL = f'{RAW}/ual/Universal Animation Library[Standard]/Unreal-Godot/UAL1_Standard.glb'
UBC = f'{RAW}/ubc/Universal Base Characters[Standard]/Base Characters/Godot - UE'
HAIR = f'{RAW}/ubc/Universal Base Characters[Standard]/Hairstyles/Rigged to Head Bone/glTF (Godot -Unreal)'
OUT = os.path.join(here, '..', 'build', 'chars.npz')

KEEP = ['pelvis', 'spine_01', 'spine_02', 'spine_03', 'neck_01', 'Head', 'clavicle_l', 'upperarm_l', 'lowerarm_l',
        'hand_l', 'clavicle_r', 'upperarm_r', 'lowerarm_r', 'hand_r', 'thigh_l', 'calf_l', 'foot_l', 'ball_l',
        'thigh_r', 'calf_r', 'foot_r', 'ball_r']
KEEP_PARENT = [-1, 0, 1, 2, 3, 4, 3, 6, 7, 8, 3, 10, 11, 12, 0, 14, 15, 16, 0, 18, 19, 20]
CLIPS = ['Idle_Loop', 'Walk_Loop', 'Jog_Fwd_Loop', 'Sprint_Loop', 'Jump_Start', 'Jump_Loop', 'Jump_Land', 'Death01',
         'Driving_Loop', 'Hit_Chest', 'Hit_Head', 'Pistol_Idle_Loop', 'Pistol_Aim_Neutral', 'Pistol_Shoot',
         'Pistol_Reload', 'Punch_Jab', 'Punch_Cross', 'Crouch_Idle_Loop', 'Roll', 'Interact', 'Idle_Talking_Loop',
         'Crouch_Fwd_Loop']
HEAD = KEEP.index('Head')
SHELL, SHELL_TRIS = ('Hair_Long', 'Hair_Buns'), 190
HAIRS = ['Hair_Buzzed', 'Hair_SimpleParted', 'Hair_Long', 'Hair_Buns', 'Hair_Beard']
R_SKIN, R_SHIRT, R_PANTS, R_SHOES, R_HAIR, R_EYES = range(6)
REGION_OF = {}
for n in KEEP:
    REGION_OF[n] = (R_SKIN if n in ('Head', 'neck_01', 'hand_l', 'hand_r') else
                    R_SHOES if n.startswith(('foot', 'ball')) else
                    R_PANTS if n.startswith(('pelvis', 'thigh', 'calf')) else R_SHIRT)
BODY_TRIS, EYE_TRIS, HAIR_TRIS = 3500, 90, 560
WAIST_Y, WAIST_SNAP = 1.0, 0.045
COLLAR_Y, COLLAR_TILT = 1.52, -0.5
HEAD_CENTRE, HEAD_SCALE = np.array([0, 1.70, -0.005]), 0.95
FPS = 30


class Rig:
    def __init__(self, g):
        j = g.j
        self.names = [j['nodes'][i]['name'] for i in j['skins'][0]['joints']]
        self.node = {j['nodes'][i]['name']: i for i in j['skins'][0]['joints']}
        par = {}
        for i, n in enumerate(j['nodes']):
            for c in n.get('children', []):
                par[c] = i
        self.parent = {nm: (j['nodes'][par[i]]['name'] if i in par and j['nodes'][par[i]]['name'] in self.node else None)
                       for nm, i in self.node.items()}
        self.trs = {nm: g.node_trs(i) for nm, i in self.node.items()}
        self.world = {}
        for nm in self.names:
            self.world[nm] = self.mat(nm)

    def mat(self, nm):
        t, q = self.trs[nm]
        m = qmat(q, t)
        p = self.parent[nm]
        return m if p is None else self.mat(p) @ m

    def wrot(self, nm):
        t, q = self.trs[nm]
        p = self.parent[nm]
        return q if p is None else qmul(self.wrot(p), q)

    def kept_of(self, nm):
        while nm is not None and nm not in KEEP:
            nm = self.parent[nm]
        return KEEP.index(nm) if nm else 0


def weights22(rig, joints, weights):
    # merge dropped bones into the nearest kept ancestor, dense (n, 22)
    jm = np.array([rig.kept_of(n) for n in rig.names])
    out = np.zeros((len(joints), len(KEEP)))
    for k in range(4):
        np.add.at(out, (np.arange(len(joints)), jm[joints[:, k]]), weights[:, k])
    return out


def top4(w):
    ids = np.argsort(-w, axis=1)[:, :4]
    ww = np.take_along_axis(w, ids, 1)
    ww /= ww.sum(1, keepdims=True)
    return ids.astype(np.uint8), ww.astype(np.float32)


def mesh_by_node(g, key):
    for n in g.j['nodes']:
        if 'mesh' in n and key.lower() in n['name'].lower():
            return g.prim(n['mesh'])


def retarget_to(src, dst, pos, w22):
    # move a mesh skinned to rig `src` so it fits rig `dst` in bind pose
    out = np.zeros_like(pos)
    for b, nm in enumerate(KEEP):
        m = dst.world[nm] @ np.linalg.inv(src.world[nm])
        out += w22[:, b:b + 1] * (pos @ m[:3, :3].T + m[:3, 3])
    return out


def nbr_mean(x, t):
    s = np.zeros_like(x)
    c = np.zeros(len(x))
    for a, b in ((0, 1), (1, 2), (2, 0)):
        for i, j in ((a, b), (b, a)):
            np.add.at(s, t[:, i], x[t[:, j]])
            np.add.at(c, t[:, i], 1)
    return s / np.maximum(c, 1).reshape(-1, *([1] * (x.ndim - 1)))


def ao(pos, tris, nrm):
    lap = nbr_mean(pos, tris) - pos
    el = np.linalg.norm(lap, axis=1).mean() + 1e-9
    return np.clip((lap * nrm).sum(1) / el * 0.6, 0, 1)


def normals(pos, tris):
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    n = np.zeros_like(pos)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def skin_mesh(rig, prim, target, retarget=None, head_shift=None):
    p, t, inv = bl.weld(prim['pos'], prim['idx'])
    j = np.zeros((len(p), 4), np.int64)
    w = np.zeros((len(p), 4))
    j[inv] = prim['joints']
    w[inv] = prim['weights']
    w22 = weights22(rig, j, w)
    if retarget is not None:
        p = retarget_to(rig, retarget, p, w22)
    if head_shift is not None:
        c = HEAD_CENTRE
        p = p + w22[:, HEAD:HEAD + 1] * (c + (p + head_shift - c) * HEAD_SCALE - p)
    q, nt, g = bl.decimate(p, t, target, 'X', w22)
    g /= g.sum(1, keepdims=True) + 1e-9
    return q, nt, g


def torso_mask(p):
    return (np.abs(p[:, 0]) < 0.3) & (p[:, 1] > 0.8) & (p[:, 1] < 1.25)


def body_regions(p, t, g):
    cat = np.zeros((len(p), 4))
    for b, nm in enumerate(KEEP):
        cat[:, REGION_OF[nm]] += g[:, b]
    for _ in range(3):
        cat = 0.5 * cat + 0.5 * nbr_mean(cat, t)
    reg = cat.argmax(1)
    torso = torso_mask(p)
    reg[torso] = np.where(p[torso, 1] > WAIST_Y, R_SHIRT, R_PANTS)
    neck = (np.abs(p[:, 0]) < 0.13) & (p[:, 1] > 1.42) & (p[:, 1] < 1.62)
    reg[neck] = np.where(p[neck, 1] - COLLAR_TILT * p[neck, 2] > COLLAR_Y, R_SKIN, R_SHIRT)
    return reg


def cap():
    # peaked police cap on the head: band, crown, top, brim. lathe in numpy
    segs = 16
    cx, cz = 0.0, -0.012
    rings = [(1.742, 0.099, 0.117, R_SHOES), (1.778, 0.100, 0.118, R_SHOES), (1.786, 0.102, 0.121, R_SHIRT),
             (1.822, 0.122, 0.146, R_SHIRT), (1.834, 0.118, 0.140, R_SHIRT)]
    v, c, t = [], [], []
    for (y, rx, rz, reg) in rings:
        for s in range(segs):
            a = 2 * np.pi * s / segs
            v.append((cx + rx * np.sin(a), y, cz + rz * np.cos(a)))
            c.append(reg)
    for r in range(len(rings) - 1):
        for s in range(segs):
            a, b = r * segs + s, r * segs + (s + 1) % segs
            t += [[a, a + segs, b + segs], [a, b + segs, b]]
    top = len(v)
    v.append((cx, 1.838, cz + 0.006))
    c.append(R_SHIRT)
    base = (len(rings) - 1) * segs
    for s in range(segs):
        t.append([base + s, top, base + (s + 1) % segs])
    # brim: front arc, top and underside
    arc = [s for s in range(segs) if np.cos(2 * np.pi * s / segs) > 0.35]
    arc = sorted(arc, key=lambda s: ((s + segs / 2) % segs))
    ob = len(v)
    for s in arc:
        a = 2 * np.pi * s / segs
        v.append((cx + 0.100 * np.sin(a) * 1.34, 1.742 - 0.012 * np.cos(a), cz + 0.118 * np.cos(a) + 0.075 * np.cos(a) ** 2))
        c.append(R_SHOES)
    for i in range(len(arc) - 1):
        a0, a1 = arc[i], arc[i + 1]
        b0, b1 = ob + i, ob + i + 1
        t += [[a0, b0, b1], [a0, b1, a1], [a0, b1, b0], [a0, a1, b1]]
    v, t = np.array(v), np.array(t)
    n0 = np.cross(v[t[0, 1]] - v[t[0, 0]], v[t[0, 2]] - v[t[0, 0]])
    out = v[t[0]].mean(0) - [cx, v[t[0]][:, 1].mean(), cz]
    if n0 @ out < 0:
        t = t[:, ::-1]
    return v, t, np.array(c, np.uint8)


def hair_mesh(name):
    p, t, _ = bl.weld(*hair_prim(name))
    if name not in SHELL:
        return bl.decimate(p, t, HAIR_TRIS, 'X')[:2]
    # long hair files leave the crown bare (it was painted on the head), so add a thin scalp shell from the buzz cut
    q, nt, _ = bl.decimate(p, t, HAIR_TRIS - SHELL_TRIS, 'X')
    sp, st, _ = bl.weld(*hair_prim('Hair_Buzzed'))
    sp, st, _ = bl.decimate(sp, st, SHELL_TRIS, 'X')
    c = np.array([0, 1.72, -0.01])
    sp = c + (sp - c) * 1.015
    return np.concatenate([q, sp]), np.concatenate([nt, st + len(q)])


def hair_prim(name):
    prim = Gltf(f'{HAIR}/{name}.gltf').prim(0)
    return prim['pos'], prim['idx']


def pack_skinned(p, t, reg, head, aoval=None):
    n = len(p)
    ids = np.zeros((n, 4), np.uint8)
    ids[:, 0] = head
    w = np.zeros((n, 4), np.float32)
    w[:, 0] = 1
    return dict(p=p.astype(np.float32), t=t, ids=ids, w=w, reg=reg.astype(np.uint8),
                ao=np.ones(n, np.float32) if aoval is None else aoval.astype(np.float32))


def body(rig, g, fit=None, eye_ref=None):
    ep_p, ep_t, ew = skin_mesh(rig, mesh_by_node(g, 'eyes'), EYE_TRIS, retarget=fit)
    eye = ep_p.mean(0)
    # the female head sits a little behind the male one on the shared skeleton, so move it to where the hair fits
    shift = None if eye_ref is None else eye_ref - eye
    if shift is not None:
        ep_p = ep_p + ew[:, HEAD:HEAD + 1] * (HEAD_CENTRE + (ep_p + shift - HEAD_CENTRE) * HEAD_SCALE - ep_p)
    p, t, w = skin_mesh(rig, mesh_by_node(g, 'superhero'), BODY_TRIS, retarget=fit, head_shift=shift)
    p[torso_mask(p) & (np.abs(p[:, 1] - WAIST_Y) < WAIST_SNAP), 1] = WAIST_Y
    reg = body_regions(p, t, w)
    n = len(p)
    P = np.concatenate([p, ep_p])
    T = np.concatenate([t, ep_t + n])
    W = np.concatenate([w, ew])
    R = np.concatenate([reg, np.full(len(ep_p), R_EYES)])
    A = np.concatenate([ao(p, t, normals(p, t)), np.zeros(len(ep_p))])
    ids, ww = top4(W)
    d = dict(p=P.astype(np.float32), t=T, ids=ids, w=ww, reg=R.astype(np.uint8), ao=(1 - 0.45 * A).astype(np.float32))
    return d, eye


def read_tracks(g, anim, joint_name):
    # local rotation keys per kept bone and the pelvis translation keys
    rots, trans, dur = {}, None, 0
    for c in anim['channels']:
        nm = joint_name.get(c['target']['node'])
        s = anim['samplers'][c['sampler']]
        t, v = g.acc(s['input']), g.acc(s['output']).astype(float)
        dur = max(dur, t[-1])
        if c['target']['path'] == 'rotation' and nm in KEEP:
            rots[nm] = (t, v)
        if c['target']['path'] == 'translation' and nm == 'pelvis':
            trans = (t, v)
    return rots, trans, dur


def resample(times, keys):
    t, v = keys
    return np.stack([np.interp(times, t, v[:, k]) for k in range(v.shape[1])], 1)


def retarget_rotations(rest_a, rest_b, loc):
    # world-space delta from the UAL rest pose, applied on top of the UBC rest pose
    nf = len(next(iter(loc.values())))
    wa, wb = {}, {}
    rot = np.zeros((nf, len(KEEP), 4))
    for i, nm in enumerate(KEEP):
        par = KEEP_PARENT[i]
        wa[nm] = qmul(rest_a['root'] if par < 0 else wa[KEEP[par]], loc[nm])
        wb[nm] = qmul(qmul(wa[nm], qinv(rest_a[nm])), rest_b[nm])
        rot[:, i] = wb[nm] if par < 0 else qmul(qinv(wb[KEEP[par]]), wb[nm])
    rot[rot[:, :, 3] < 0] *= -1
    return rot


def retarget_hips(keys, times, ta, tb, root_q, loop):
    # scale the height to the taller rig and drop sideways/forward drift (loops are centred, one-shots start at the bind spot)
    o = resample(times, keys)
    t = np.stack([o[:, 0], tb[1] + (o[:, 1] - ta[1]), o[:, 2] * tb[2] / ta[2]], 1)
    ref = t.mean(0) if loop else t[0]
    t[:, :2] += tb[:2] - ref[:2]
    return qrot(root_q, t)


def clips(rig_a, rig_b):
    g = Gltf(UAL)
    anims = {a['name']: a for a in g.j['animations']}
    joint_name = {i: g.j['nodes'][i]['name'] for i in g.j['skins'][0]['joints']}
    rest_a = {n: rig_a.wrot(n) for n in KEEP + ['root']}
    rest_b = {n: rig_b.wrot(n) for n in KEEP + ['root']}
    out = []
    for name in CLIPS:
        rots, trans, dur = read_tracks(g, anims[name], joint_name)
        nf = int(round(dur * FPS)) + 1
        times = np.arange(nf) / FPS
        loc = {nm: resample(times, rots[nm]) for nm in KEEP}
        for q in loc.values():
            q /= np.linalg.norm(q, axis=1, keepdims=True)
        rot = retarget_rotations(rest_a, rest_b, loc)
        loop = name.endswith('_Loop')
        hips = retarget_hips(trans, times, rig_a.trs['pelvis'][0], rig_b.trs['pelvis'][0], rest_b['root'], loop)
        out.append(dict(frames=nf, loop=loop, rot=rot.astype(np.float32), hips=hips.astype(np.float32)))
    return out


def main():
    bl.reset()
    gm = Gltf(f'{UBC}/Superhero_Male_FullBody.gltf')
    gf = Gltf(f'{UBC}/Superhero_Female_FullBody.gltf')
    rm, rf = Rig(gm), Rig(gf)
    ga = Gltf(UAL)
    ra = Rig(ga)
    out = {}
    out['names'] = np.array(KEEP)
    out['parent'] = np.array(KEEP_PARENT)
    bpos, brot = [], []
    for i, nm in enumerate(KEEP):
        t, q = rm.trs[nm]
        if i == 0:
            q = qmul(rm.trs['root'][1], q)
            t = qrot(rm.trs['root'][1], t)
        bpos.append(t)
        brot.append(q)
    out['bind_pos'] = np.array(bpos, np.float32)
    out['bind_rot'] = np.array(brot, np.float32)
    head = KEEP.index('Head')
    eye = None
    for k, (rig, g, fit) in enumerate(((rm, gm, None), (rf, gf, rm))):
        d, e = body(rig, g, fit, eye)
        eye = e if eye is None else eye
        for key, v in d.items():
            out[f'body{k}_{key}'] = v
        print('body', k, 'verts', len(d['p']), 'tris', len(d['t']))
    for k, nm in enumerate(HAIRS):
        p, t = hair_mesh(nm)
        d = pack_skinned(p, t, np.full(len(p), R_HAIR), head)
        for key, v in d.items():
            out[f'hair{k}_{key}'] = v
        print(nm, len(t))
    p, t, reg = cap()
    d = pack_skinned(p, t, reg, head)
    for key, v in d.items():
        out[f'hair5_{key}'] = v
    print('cap', len(t))
    cl = clips(ra, rm)
    for i, c in enumerate(cl):
        out[f'clip{i}_rot'] = c['rot']
        out[f'clip{i}_hips'] = c['hips']
        out[f'clip{i}_loop'] = np.array(c['loop'])
    np.savez_compressed(OUT, **out)


main()
