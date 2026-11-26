# trims raylib's glad loader in a build copy: only GL entry points and extension flags that something references.
# usage: gladtrim.py <raylib src dir> <names file from the game sources>
import glob, re, sys

d, used_file = sys.argv[1:3]
tok = re.compile(r'\b(?:GLAD_)?gl[A-Z]\w*')
used = set(open(used_file).read().split())
for f in glob.glob(f'{d}/*.c') + [f'{d}/rlgl.h']:
    used |= set(tok.findall(open(f, errors='ignore').read()))
used |= {'glGetString', 'glGetStringi', 'glGetIntegerv'}
p = f'{d}/external/glad.h'
out, n = [], 0
for l in open(p).read().split('\n'):
    m = re.match(r'\s*glad_(gl\w+) = \(PFN\w+\) load\(userptr, "\w+"\);', l) or re.match(r'\s*(GLAD_GL_\w+) = glad_gl_has_extension\(', l)
    if m and m.group(1) not in used:
        n += 1
        continue
    out.append(l)
open(p, 'w').write('\n'.join(out))
print(f'glad: dropped {n} loader lines')
