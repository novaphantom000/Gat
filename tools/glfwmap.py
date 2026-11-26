# shrinks GLFW's gamepad database in a build copy of raylib: keeps this platform's entries, lzma-packed,
# and patches _glfwInitGamepadMappings to unpack them. usage: glfwmap.py mac|win|linux <glfw/src dir>
import ast, lzma, re, sys

target, d = sys.argv[1], sys.argv[2]
guard = dict(mac='_GLFW_COCOA', win='_GLFW_WIN32', linux='GLFW_BUILD_LINUX_JOYSTICK')[target.replace('test', '')]
text = open(f'{d}/mappings.h').read()
block = re.search(r'#if defined\(%s\)\n(.*?)#endif // %s' % (guard, guard), text, re.S).group(1)
lines = [ast.literal_eval(l.strip().rstrip(',')) for l in block.splitlines() if l.strip().startswith('"')]
raw = '\n'.join(lines).encode() + b'\n'
f = [{'id': lzma.FILTER_LZMA1, 'preset': 9 | lzma.PRESET_EXTREME, 'lc': 3, 'lp': 0, 'pb': 0, 'dict_size': 1 << 20}]
z = bytes([3]) + lzma.compress(raw, format=lzma.FORMAT_RAW, filters=f)
body = ',\n'.join(','.join(str(b) for b in z[i:i + 32]) for i in range(0, len(z), 32))
open(f'{d}/mappings.h', 'w').write(f'static const int mapLen = {len(raw)};\nstatic const unsigned char mapZ[] = {{\n{body}\n}};\n')

src = open(f'{d}/input.c').read()
a = src.index('void _glfwInitGamepadMappings(void)')
b = src.index('// Returns an available joystick object')
src = src[:a] + '''extern void lzma_unpack(const unsigned char *in, unsigned char *out, int n);

void _glfwInitGamepadMappings(void)
{
    char* text = _glfw_calloc(mapLen + 1, 1);
    int i, n = 0;
    lzma_unpack(mapZ, (unsigned char*) text, mapLen);
    for (i = 0;  i < mapLen;  i++)
        if (text[i] == '\\n') n++;
    _glfw.mappings = _glfw_calloc(n, sizeof(_GLFWmapping));
    for (i = 0;  i < mapLen;  )
    {
        char* line = text + i;
        while (text[i] != '\\n') i++;
        text[i++] = 0;
        if (parseMapping(&_glfw.mappings[_glfw.mappingCount], line))
            _glfw.mappingCount++;
    }
    _glfw_free(text);
}

''' + src[b:]
open(f'{d}/input.c', 'w').write(src)
print(f'gamepad db: {len(lines)} entries, {len(raw)} -> {len(z)} bytes')
