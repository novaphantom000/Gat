import struct
import numpy as np


def face_normals(p, t):
    return np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])


def smooth(p, t):
    n = np.zeros_like(p)
    fn = face_normals(p, t)
    for k in range(3):
        np.add.at(n, t[:, k], fn)
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-12)


def split(p, t, key, crease=38.0):
    # one vertex per (corner, face key, smoothing cluster). returns pos, tris, normals, source vertex ids
    fn = face_normals(p, t)
    area = np.linalg.norm(fn, axis=1)
    fn = fn / (area[:, None] + 1e-12)
    cosc = np.cos(np.radians(crease))
    inc = [[] for _ in range(len(p))]
    for f in range(len(t)):
        for c in range(3):
            inc[t[f, c]].append(f)
    newp, newn, src = [], [], []
    nt = np.zeros_like(t)
    for v in range(len(p)):
        clusters = []
        for f in inc[v]:
            for cl in clusters:
                if key[cl[0]] == key[f] and fn[cl[0]] @ fn[f] > cosc:
                    cl.append(f)
                    break
            else:
                clusters.append([f])
        for cl in clusters:
            nn = (fn[cl] * area[cl][:, None]).sum(0)
            nn /= np.linalg.norm(nn) + 1e-12
            for f in cl:
                nt[f, list(t[f]).index(v)] = len(newp)
            newp.append(p[v])
            newn.append(nn)
            src.append(v)
    return np.array(newp), nt, np.array(newn), np.array(src)


def first_use(t, *per_vertex):
    order = []
    seen = {}
    for v in t.ravel():
        if v not in seen:
            seen[v] = len(order)
            order.append(v)
    order = np.array(order)
    nt = np.vectorize(seen.get)(t) if len(t) else t
    return (nt,) + tuple(a[order] for a in per_vertex)


def delta16(a):
    a = np.asarray(a, np.int64)
    d = np.diff(a, prepend=0, axis=-1)
    return (d & 0xFFFF).astype(np.uint16)


def planes(a16):
    return (a16 & 0xFF).astype(np.uint8).tobytes() + (a16 >> 8).astype(np.uint8).tobytes()


def mesh(p, t, nrm, rgba=None, skin=None):
    # skin = (region, ao, ids(n,4), weights(n,4)) for skinned meshes, else rgba (n,4) uint8
    t, p, nrm, *rest = first_use(t, p, nrm, *([rgba] if skin is None else list(skin)))
    n = len(p)
    lo, hi = p.min(0), p.max(0)
    sc = np.maximum(hi - lo, 1e-6) / 1023
    q = np.round((p - lo) / sc).astype(np.int64)
    b = struct.pack('<HHB6f', n, len(t), 0 if skin is None else 1, *lo, *sc)
    # vertices split by normal share positions: ref = distance back to the first vertex at the same spot (0 = new spot)
    seen, ref, spots = {}, [], []
    for i, r in enumerate(map(tuple, q)):
        ref.append(i - seen[r] if r in seen else 0)
        if r not in seen:
            seen[r] = i
            spots.append(r)
    b += planes(np.array(ref, np.int64))
    spots = np.array(spots)
    for a in range(3):
        b += planes(delta16(spots[:, a]))
    nq = (np.round(nrm * 31) * 4).astype(np.int8)
    for a in range(3):
        b += nq[:, a].tobytes()
    if skin is None:
        for c in range(4):  # rgb in steps of 4 (alpha is a material code, kept exact)
            col = rest[0][:, c].astype(np.int32)
            b += (np.minimum((col + 2) // 4 * 4, 255) if c < 3 else col).astype(np.uint8).tobytes()
    else:
        reg, ao, ids, w = rest
        b += reg.astype(np.uint8).tobytes() + np.round(ao * 255).astype(np.uint8).tobytes()
        for c in range(4):
            b += ids[:, c].astype(np.uint8).tobytes()
        wq = np.round(w * 255).astype(np.int64)
        wq[:, 0] += 255 - wq.sum(1)
        for c in range(4):
            b += wq[:, c].astype(np.uint8).tobytes()
    hw, codes = -1, []
    for i in t.ravel():
        codes.append(hw + 1 - i)
        hw = max(hw, i)
    b += planes(np.array(codes, np.int64) & 0xFFFF)
    return b
