#!/usr/bin/env python3
"""Compiles every shader the game builds as desktop GLSL 3.30 and as GLSL ES 3.00 with glslangValidator.
usage: python3 tools/check_shaders.py   (needs glslang-tools: apt install glslang-tools)"""
import os, re, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
src = os.path.join(here, '..', 'src')


def strip_comments(s):
    s = re.sub(r'/\*.*?\*/', ' ', s, flags=re.S)
    return re.sub(r'//[^\n]*', ' ', s)


def blocks(path):
    text = open(path).read()
    out = {}
    for m in re.finditer(r'static const char \*(\w+)\s*=\s*GLSL\(', text):
        i, depth = m.end(), 1
        while depth:
            c = text[i]
            depth += (c == '(') - (c == ')')
            i += 1
        body = strip_comments(text[m.end():i - 1])
        out[m.group(1)] = ' '.join(body.split())   # what #__VA_ARGS__ produces
    return out


def pretty(s):
    return ''.join(c + ('\n' if c in ';{}' else '') for c in s)


def plain(path, name):
    m = re.search(r'static const char \*%s\s*=\s*((?:\s*"(?:[^"\\]|\\.)*")+)\s*;' % name, open(path).read())
    return ''.join(bytes(x, 'utf8').decode('unicode_escape') for x in re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))


B = {**blocks(f'{src}/render.c'), **blocks(f'{src}/fx.c')}
B['FS_WORLD_FIX'] = plain(f'{src}/render.c', 'FS_WORLD_FIX')
FX = {'VS': B.pop('VS'), 'FS': B.pop('FS')} if 'VS' in B else {}
common = B['FS_COMMON']
progs = {
    'world': ('VS_STATIC', common + B['FS_WORLD_FIX'] + B['FS_WORLD']),
    'glass': ('VS_STATIC', common + B['FS_GLASS']),
    'water': ('VS_WATER', common + B['FS_WATER']),
    'car': ('VS_MESH', common + B['FS_CAR']),
    'prop': ('VS_MESH', common + B['FS_PROP']),
    'char': ('VS_SKIN', common + B['FS_CHAR']),
    'sky': ('VS_FULL', common + B['FS_SKY']),
    'shadow_static': ('VS_SHADOW_STATIC', B['FS_SHADOW_STATIC']),
    'shadow_mesh': ('VS_SHADOW_MESH', B['FS_EMPTY']),
    'shadow_skin': ('VS_SHADOW_SKIN', B['FS_EMPTY']),
    'bright': ('VS_FULL', B['FS_BRIGHT']), 'down': ('VS_FULL', B['FS_DOWN']), 'up': ('VS_FULL', B['FS_UP']),
    'compose': ('VS_FULL', B['FS_COMPOSE']), 'fxaa': ('VS_FULL', B['FS_FXAA']),
}
consts = 'const int L_PALM = 0, L_LEAF = 1, L_GRASS = 2, L_DETAIL = 3, L_SAND = 4, L_ASPHALT = 5, L_SIDEWALK = 6, L_QUAY = 7;\n'
preludes = {
    'desktop330': '#version 330 core\n',
    'es300': '#version 300 es\nprecision highp float;\nprecision highp int;\nprecision highp sampler2D;\n'
             'precision highp sampler2DArray;\nprecision highp sampler2DShadow;\n',
}
bad = checked = 0
with tempfile.TemporaryDirectory() as d:
    for pname, pre in preludes.items():
        for name, (vs, fs) in list(progs.items()) + [('fx', ('VS', 'FS'))]:
            v, f = (FX['VS'], FX['FS']) if name == 'fx' else (B[vs], fs)
            for stage, body in (('vert', v), ('frag', f)):
                p = os.path.join(d, f'{name}.{stage}')
                open(p, 'w').write(pre + consts + pretty(body))
                checked += 1
                r = subprocess.run(['glslangValidator', p], capture_output=True, text=True)
                if r.returncode:
                    bad += 1
                    print(f'--- {pname} {name}.{stage}\n{r.stdout.strip()}')
print(f'shaders: all {checked} stages compile (330 core + ES 300)' if not bad else f'shaders: {bad} of {checked} stage(s) failed')
sys.exit(1 if bad else 0)
