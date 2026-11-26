import numpy as np
import meshenc

PLAIN, TAIL, HEAD, GLASS, SIREN, PAINT = 0, 32, 64, 128, 192, 255
GLASS_RGB = np.array([0.08, 0.13, 0.17])
LUM = np.array([0.3, 0.59, 0.11])


def vtx_area(p, t):
    a = np.linalg.norm(meshenc.face_normals(p, t), axis=1) / 2
    out = np.zeros(len(p))
    for k in range(3):
        np.add.at(out, t[:, k], a / 3)
    return out


def dominant(rgb, area, y):
    # body paint: the biggest hue (or, for grey cars, value) cluster among the exterior vertices
    h, sat, v = hsv(rgb)
    ext = y > 0.35
    dd = rgb.max(-1) - rgb.min(-1)
    chrom = ext & (sat > 0.25) & (v > 0.08) & (dd > 0.06)
    if area[chrom].sum() > 0.08 * area[ext].sum():
        sel = chrom
        key = (h * 36).astype(int) % 36
    else:
        sel = ext & (dd < 0.08)
        key = (v * 8).astype(int)
    m = np.bincount(key[sel], weights=area[sel], minlength=36).argmax()
    cl = sel & (key == m)
    top = rgb[cl][(rgb[cl] @ LUM) >= np.percentile(rgb[cl] @ LUM, 60)]
    return top.mean(0)


def hsv(c):
    mx, mn = c.max(-1), c.min(-1)
    d = mx - mn + 1e-9
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) / 6
    return h, d / (mx + 1e-9), mx


def paint_mask(rgb, ref):
    h, s, v = hsv(rgb)
    rh, rs, rv = hsv(ref)
    if rs > 0.25:
        dh = np.abs(h - rh)
        dh = np.minimum(dh, 1 - dh)
        return (dh < 0.05) & (s > 0.5 * rs) & (v > 0.025)
    return (rgb.max(-1) - rgb.min(-1) < 0.08) & (np.abs(v - rv) < 0.2)


def load(d, name):
    parts = {k: (d[f'{name}_{k}_p'].astype(float), d[f'{name}_{k}_t'], d[f'{name}_{k}_c'].astype(float)) for k in ('body', 'glass', 'optic')}
    bp, bt, bc = parts['body']
    ref = dominant(bc, vtx_area(bp, bt), bp[:, 1])
    pm = paint_mask(bc, ref)
    fm = np.where(pm[bt].sum(1) >= 2, PAINT, PLAIN)
    gp, gt, _ = parts['glass']
    op, ot, oc = parts['optic']
    fo = np.where(op[ot][:, :, 2].mean(1) > 0, HEAD, TAIL)
    P = np.concatenate([bp, gp, op])
    T = np.concatenate([bt, gt + len(bp), ot + len(bp) + len(gp)])
    C = np.concatenate([bc, np.tile(GLASS_RGB, (len(gp), 1)), oc])
    F = np.concatenate([fm, np.full(len(gt), GLASS), fo])
    return dict(p=P, t=T, c=C, f=F, ref=ref, glass=gp, body=bp)


def shade(c, ref):
    return np.clip((c @ LUM) / (ref @ LUM), 0.45, 1.0)


def build(m, extra=(), liv=None):
    # liv = (classes(P, T, F) -> 0 for unpainted faces, 1.. for livery colours, colour table)
    P, T, C, F = m['p'], m['t'], m['c'], m['f']
    for p, t, col, fm in extra:
        T = np.concatenate([T, t + len(P)])
        P = np.concatenate([P, p])
        C = np.concatenate([C, np.tile(col, (len(p), 1))])
        F = np.concatenate([F, np.full(len(t), fm)])
    painted = F == PAINT
    cls = np.zeros(len(T), int)
    if liv:
        cls = liv[0](P, T, F)
        F = np.where(painted, PLAIN, F)
    nv, nt, nn, src = meshenc.split(P, T, F * 16 + cls)
    key = np.zeros(len(nv), int)
    key[nt.ravel()] = np.repeat(F * 16 + cls, 3)
    mat, vc = key // 16, key % 16
    rgb = C[src].copy()
    sh = shade(C[src], m['ref'])[:, None]
    if liv:
        for k, col in enumerate(liv[1]):
            if k:
                rgb[vc == k] = np.array(col) * (0.65 + 0.35 * sh[vc == k])
    else:
        rgb[mat == PAINT] = sh[mat == PAINT]
    return nv, nt, nn, rgb, mat


def finish(nv, nt, nn, rgb, mat):
    rgba = np.zeros((len(nv), 4), np.uint8)
    rgba[:, :3] = np.clip(np.round(rgb * 255), 0, 255)
    rgba[:, 3] = mat
    return meshenc.mesh(nv, nt, nn, rgba)


def livery(m, kind):
    gp = m['glass']
    sill = gp[:, 1].min()
    g0, g1 = gp[:, 2].min(), gp[:, 2].max()
    lo, hi = g0 + 0.18 * (g1 - g0), g1 - 0.12 * (g1 - g0)

    def classes(P, T, F):
        cen = P[T].mean(1)
        c = np.zeros(len(T), int)
        if kind == 'cop':
            door = (cen[:, 2] > lo) & (cen[:, 2] < hi) & (cen[:, 1] > 0.38) & (np.abs(cen[:, 0]) > 0.55)
            c[:] = np.where((cen[:, 1] > sill + 0.02) | door, 2, 1)
        else:
            c[:] = 1
        c[F != PAINT] = 0
        return c
    table = [None, (0.07, 0.07, 0.08), (0.98, 0.98, 0.99)] if kind == 'cop' else [None, (1.0, 0.76, 0.02)]
    return classes, table
