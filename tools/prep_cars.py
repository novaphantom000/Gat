# blender -b --python tools/prep_cars.py   ->  build/cars.npz
import bpy, bmesh, sys, os
import numpy as np
from mathutils import Vector

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
import bl

SRC = os.path.expanduser('~/Documents/fsdsim/assets/models')
OUT = os.path.join(here, '..', 'build', 'cars.npz')
NAMES = ['sedan', 'compact', 'hatchback', 'minivan', 'pickup', 'suv', 'wagon', 'offroad']
SCALE = 1.06
BODY_TRIS, GLASS_TRIS, OPTIC_TRIS = 1850, 110, 140


def to_model(p):
    # blender z-up, front along +x  ->  y up, +z forward, +x left
    return np.stack([p[:, 1], p[:, 2], p[:, 0]], 1)


def part(ob):
    me = ob.data
    me.calc_loop_triangles()
    n = len(me.vertices)
    co = np.empty(n * 3)
    me.vertices.foreach_get('co', co)
    mw = np.array(ob.matrix_world)
    co = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    lt = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get('vertices', lt)
    ll = np.empty(len(me.loop_triangles) * 3, np.int64)
    me.loop_triangles.foreach_get('loops', ll)
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers[0].data.foreach_get('uv', uv)
    return to_model(co) * SCALE, lt.reshape(-1, 3), uv.reshape(-1, 2)[ll].reshape(-1, 3, 2)


def base_image(ob):
    mat = ob.data.materials[0]
    for nd in mat.node_tree.nodes:
        if nd.type == 'BSDF_PRINCIPLED':
            for l in nd.inputs['Base Color'].links:
                if l.from_node.type == 'TEX_IMAGE':
                    im = l.from_node.image
                    px = np.empty(im.size[0] * im.size[1] * 4, np.float32)
                    im.pixels.foreach_get(px)
                    return px.reshape(im.size[1], im.size[0], 4)[:, :, :3]
    return None


def tex(img, uv, r=3):
    h, w = img.shape[:2]
    x = (uv[:, 0] % 1.0) * w
    y = (uv[:, 1] % 1.0) * h
    out = np.zeros((len(uv), 3))
    k = 0
    for dx in range(-r, r + 1, r):
        for dy in range(-r, r + 1, r):
            out += img[np.clip((y + dy).astype(int), 0, h - 1), np.clip((x + dx).astype(int), 0, w - 1)]
            k += 1
    return out / k


def build_car(name):
    bl.reset()
    bpy.ops.import_scene.gltf(filepath=f'{SRC}/car_{name}.glb')
    obs = [o for o in bpy.data.objects if o.type == 'MESH']
    body = next(o for o in obs if o.data.materials[0].name.startswith('Body') and not o.name.startswith('Wheel'))
    glass = next(o for o in obs if o.data.materials[0].name.startswith('Glass'))
    optic = next(o for o in obs if o.data.materials[0].name.startswith('Optics'))
    wheels = [o for o in obs if o.name.startswith('Wheel') and not o.data.materials[0].name.startswith('Body')]
    parts = {}
    for key, ob, tgt in (('body', body, BODY_TRIS), ('glass', glass, GLASS_TRIS), ('optic', optic, OPTIC_TRIS)):
        pos, tris, uv = part(ob)
        p0, t0, inv = bl.weld(pos, tris)
        wt = inv[tris]
        ok = (wt[:, 0] != wt[:, 1]) & (wt[:, 1] != wt[:, 2]) & (wt[:, 0] != wt[:, 2])
        p, t, _ = bl.decimate(p0, t0, tgt, 'X')
        # colour each new vertex from the texture at the nearest point of the source surface
        ti, bw = bl.sample_surface(p0, t0, p)
        puv = (uv[ok][ti] * bw[:, :, None]).sum(1)
        img = base_image(ob)
        parts[key] = dict(pos=p, tris=t, rgb=tex(img, puv) if img is not None else np.zeros((len(p), 3)))
    boxes = [to_model(np.array([w.matrix_world @ Vector(c) for c in w.bound_box])) * SCALE for w in wheels]
    return parts, boxes


def wheel_mesh(r, w, nseg=16):
    # lathe: tread, sidewalls, rim lips, rim faces fanned to a hub vertex. axle along x
    hw = w / 2
    side = [(r * .6, -hw * .62), (r * .68, -hw), (r, -hw * .9), (r, hw * .9), (r * .68, hw), (r * .6, hw * .62)]
    v = [(x, rr * np.sin(2 * np.pi * s / nseg), rr * np.cos(2 * np.pi * s / nseg)) for rr, x in side for s in range(nseg)]
    t = []
    for ring in range(5):
        a, b = ring * nseg, (ring + 1) * nseg
        for s in range(nseg):
            s2 = (s + 1) % nseg
            t += [[a + s, b + s, b + s2], [a + s, b + s2, a + s2]]
    for ring, x in ((0, -hw * .5), (5, hw * .5)):
        hub = len(v)
        v.append((x, 0, 0))
        for s in range(nseg):
            t.append([ring * nseg + s, hub, ring * nseg + (s + 1) % nseg])
    v, t = np.array(v), np.array(t)
    vol = np.einsum('ij,ij->i', v[t[:, 0]], np.cross(v[t[:, 1]], v[t[:, 2]])).sum()
    return v, (t if vol > 0 else t[:, ::-1])


def box(c, size, bevel=0.012):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    if bevel:
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=1, affect='EDGES')
    bmesh.ops.triangulate(bm, faces=bm.faces)
    p = np.array([v.co[:] for v in bm.verts]) + c
    idx = {v: i for i, v in enumerate(bm.verts)}
    t = np.array([[idx[v] for v in f.verts] for f in bm.faces])
    bm.free()
    return p, t


def roof_of(body):
    p = body['pos']
    top = p[:, 1] > p[:, 1].max() - 0.06
    return p[:, 1].max(), p[top, 2].mean(), np.ptp(p[top, 0])


def extras(out, sedan, wagon):
    y, z, w = roof_of(sedan)
    parts = {'base': box([0, y + 0.03, z], [0.95, 0.06, 0.26]),
             'red': box([0.24, y + 0.085, z], [0.42, 0.07, 0.24]),
             'blue': box([-0.24, y + 0.085, z], [0.42, 0.07, 0.24]),
             'push': box([0, 0.5, sedan['pos'][:, 2].max() + 0.02], [0.95, 0.3, 0.1], 0.02)}
    y, z, w = roof_of(wagon)
    parts['sign'] = box([0, y + 0.07, z], [0.55, 0.12, 0.2], 0.02)
    parts['signbase'] = box([0, y + 0.01, z], [0.36, 0.03, 0.12], 0)
    for k, (p, t) in parts.items():
        out[f'x_{k}_p'] = p.astype(np.float32)
        out[f'x_{k}_t'] = t


def corner(wc, left, front):
    # index of the wheel in a given corner (left = +x, front = +z)
    return int(np.argmax(wc[:, 0] * (1 if left else -1) + wc[:, 2] * (1 if front else -1)))


def main():
    out = {}
    bodies = {}
    for name in NAMES:
        parts, boxes = build_car(name)
        # the suv carries little hubcap bodies next to its tyres, skip anything smaller than a tyre
        boxes = [b for b in boxes if np.ptp(b[:, 1]) > 0.45 * SCALE]
        wc = np.array([b.mean(0) for b in boxes])
        order = [corner(wc, 1, 1), corner(wc, 0, 1), corner(wc, 1, 0), corner(wc, 0, 0)]
        tyre = boxes[order[0]]
        r, w = np.ptp(tyre[:, 1]) / 2, np.ptp(tyre[:, 0])
        # origin: ground under the middle of the wheelbase, centred on the body's width
        allx = np.concatenate([parts['body']['pos'][:, 0], parts['glass']['pos'][:, 0]])
        shift = np.array([-(allx.max() + allx.min()) / 2, -min(b[:, 1].min() for b in boxes), -wc[:, 2].mean()])
        for k in parts:
            parts[k]['pos'] = parts[k]['pos'] + shift
        wv, wt = wheel_mesh(r, w)
        out[f'{name}_wpos'] = wc[order] + shift
        out[f'{name}_wr'] = np.array([r, w])
        out[f'{name}_wv'] = wv
        out[f'{name}_wt'] = wt
        for k, d in parts.items():
            out[f'{name}_{k}_p'] = d['pos'].astype(np.float32)
            out[f'{name}_{k}_t'] = d['tris']
            out[f'{name}_{k}_c'] = d['rgb'].astype(np.float32)
        bodies[name] = parts['body']
        print(name, {k: len(d['tris']) for k, d in parts.items()}, 'wheel r', round(r, 3))
    extras(out, bodies['sedan'], bodies['wagon'])
    np.savez_compressed(OUT, **out)


main()
