# helpers shared by the blender prep scripts
import bpy
import numpy as np


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def weld(pos, tris, eps=1e-5):
    key = np.round(pos / eps).astype(np.int64)
    _, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    t = inv[tris]
    t = t[(t[:, 0] != t[:, 1]) & (t[:, 1] != t[:, 2]) & (t[:, 0] != t[:, 2])]
    return pos[first], t, inv


def decimate(pos, tris, target, sym_axis=None, groups=None):
    # returns decimated pos, tris and, per new vertex, the weights of each vertex group (n, ngroups)
    me = bpy.data.meshes.new('d')
    me.from_pydata(pos.tolist(), [], tris.tolist())
    me.update()
    ob = bpy.data.objects.new('d', me)
    bpy.context.collection.objects.link(ob)
    if groups is not None:
        for g in range(groups.shape[1]):
            vg = ob.vertex_groups.new(name=f'g{g}')
            for i in np.nonzero(groups[:, g] > 0)[0]:
                vg.add([int(i)], float(groups[i, g]), 'REPLACE')
    md = ob.modifiers.new('d', 'DECIMATE')
    md.decimate_type = 'COLLAPSE'
    md.ratio = min(1.0, target / len(tris))
    md.use_collapse_triangulate = True
    if sym_axis:
        md.use_symmetry = True
        md.symmetry_axis = sym_axis
    bpy.context.view_layer.update()
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    m2 = ev.to_mesh()
    m2.calc_loop_triangles()
    n = len(m2.vertices)
    p = np.empty(n * 3, np.float32)
    m2.vertices.foreach_get('co', p)
    t = np.empty(len(m2.loop_triangles) * 3, np.int64)
    m2.loop_triangles.foreach_get('vertices', t)
    w = None
    if groups is not None:
        w = np.zeros((n, groups.shape[1]))
        for v in m2.vertices:
            for ge in v.groups:
                w[v.index, ge.group] = ge.weight
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    return p.reshape(-1, 3).astype(np.float64), t.reshape(-1, 3), w


def sample_surface(pos, tris, q):
    # nearest surface point of a triangle soup for each query point -> (tri index, barycentric weights)
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from mathutils.interpolate import poly_3d_calc
    tree = BVHTree.FromPolygons([tuple(p) for p in pos.tolist()], [tuple(t) for t in tris.tolist()])
    ti = np.zeros(len(q), np.int64)
    bw = np.zeros((len(q), 3))
    for i, c in enumerate(q):
        loc, nor, idx, dist = tree.find_nearest(Vector(c))
        t = tris[idx]
        w = poly_3d_calc([Vector(pos[k]) for k in t], loc)
        ti[i] = idx
        bw[i] = w
    return ti, bw
