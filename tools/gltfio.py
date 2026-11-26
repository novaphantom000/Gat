import json, struct, os
import numpy as np

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NC = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


class Gltf:
    def __init__(self, path):
        self.dir = os.path.dirname(path)
        data = open(path, 'rb').read()
        self.bin = None
        if path.endswith('.glb'):
            n = struct.unpack('<I', data[12:16])[0]
            self.j = json.loads(data[20:20 + n])
            self.bin = data[28 + n:]
        else:
            self.j = json.loads(data)
        self.cache = {}

    def buf(self, i):
        if i not in self.cache:
            b = self.j['buffers'][i]
            self.cache[i] = self.bin if 'uri' not in b else open(os.path.join(self.dir, b['uri']), 'rb').read()
        return self.cache[i]

    def acc(self, i):
        a = self.j['accessors'][i]
        bv = self.j['bufferViews'][a['bufferView']]
        dt = np.dtype(CT[a['componentType']])
        nc = NC[a['type']]
        off = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = bv.get('byteStride', dt.itemsize * nc)
        raw = self.buf(bv['buffer'])
        if stride == dt.itemsize * nc:
            out = np.frombuffer(raw, dt, a['count'] * nc, off)
        else:
            out = np.stack([np.frombuffer(raw, dt, nc, off + k * stride) for k in range(a['count'])]).ravel()
        return out.reshape(a['count'], nc) if nc > 1 else out

    def prim(self, mesh_i, k=0):
        p = self.j['meshes'][mesh_i]['primitives'][k]
        at = p['attributes']
        d = {'pos': self.acc(at['POSITION']).astype(np.float64), 'idx': self.acc(p['indices']).astype(np.int64).reshape(-1, 3),
             'mat': p.get('material')}
        if 'JOINTS_0' in at:
            d['joints'] = self.acc(at['JOINTS_0']).astype(np.int64)
            d['weights'] = self.acc(at['WEIGHTS_0']).astype(np.float64)
        return d

    def node_trs(self, n):
        n = self.j['nodes'][n]
        return (np.array(n.get('translation', [0, 0, 0]), float), np.array(n.get('rotation', [0, 0, 0, 1]), float))


def qmul(a, b):
    ax, ay, az, aw = np.moveaxis(np.asarray(a, float), -1, 0)
    bx, by, bz, bw = np.moveaxis(np.asarray(b, float), -1, 0)
    return np.stack([aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz], -1)


def qinv(q):
    return np.asarray(q, float) * np.array([-1, -1, -1, 1])


def qrot(q, v):
    q = np.asarray(q, float)
    u = q[..., :3]
    return v + 2 * np.cross(u, np.cross(u, v) + q[..., 3:] * v)


def qmat(q, t):
    x, y, z, w = q
    m = np.eye(4)
    m[:3, :3] = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                 [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                 [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    m[:3, 3] = t
    return m
