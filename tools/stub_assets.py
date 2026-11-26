# writes a minimal build/assets.c when the licensed model packs are not available.
# assets_load() sees zero sections and loads nothing, so the APK still compiles and links,
# but it has no cars, characters, guns, animations or helicopter.
import os

here = os.path.dirname(os.path.abspath(__file__))
build = os.path.join(here, '..', 'build')
os.makedirs(build, exist_ok=True)

# 4-byte section count (0), then a raw-LZMA stream that assets_load never decodes (total length is 0).
blob = bytes([0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0])

lines = ['// placeholder written by tools/stub_assets.py: the licensed model packs were not provided',
         f'const int assets_blob_len = {len(blob)};',
         'const unsigned char assets_blob[] = {']
for i in range(0, len(blob), 24):
    lines.append('    ' + ','.join(str(x) for x in blob[i:i + 24]) + ',')
lines.append('};')
open(os.path.join(build, 'assets.c'), 'w').write('\n'.join(lines) + '\n')
print('wrote placeholder build/assets.c (no models)')
