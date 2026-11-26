#!/bin/sh
# build a trimmed static raylib for one target: tools/rl.sh mac|win|linux
set -e
T=$1
OUT=build/rl-$T
SRC=$OUT/src
rm -rf $SRC
mkdir -p $SRC
cp -R raw/raylib/src/. $SRC
python3 tools/glfwmap.py $T $SRC/external/glfw/src
python3 tools/gladtrim.py $SRC build/gl.used
# trace logging is off anyway, so glfw's ~100 error strings go too
echo '#define _glfwInputError(...) ((void)0)' >> $SRC/external/glfw/src/internal.h
sed -i.bak 's/^void _glfwInputError(int code, const char\* format, ...)$/#undef _glfwInputError\nvoid _glfwInputError(int code, const char* format, ...)/' $SRC/external/glfw/src/init.c
# the game never scales an image (ImageDraw is 1:1), so stb_image_resize (450 KB of source) becomes a nearest-neighbour stub
python3 - $SRC/rtextures.c <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
s = s.replace('#include "external/stb_image_resize2.h"', """typedef int stbir_pixel_layout;
static void stbir_resize_uint8_linear(const unsigned char *in, int iw, int ih, int is, unsigned char *out, int ow, int oh, int os, int ch)
{
    for (int y = 0; y < oh; y++) for (int x = 0; x < ow; x++) for (int c = 0; c < ch; c++)
        out[(y * ow + x) * ch + c] = in[((long)y * ih / oh * iw + (long)x * iw / ow) * ch + c];
}""")
open(p, 'w').write(s)
PY

FEATURES="-DSUPPORT_FILEFORMAT_OBJ=0 -DSUPPORT_FILEFORMAT_MTL=0 -DSUPPORT_FILEFORMAT_IQM=0 -DSUPPORT_FILEFORMAT_GLTF=0 -DSUPPORT_FILEFORMAT_VOX=0 -DSUPPORT_FILEFORMAT_M3D=0 -DSUPPORT_MESH_GENERATION=0 -DSUPPORT_TRACELOG=0 -DSUPPORT_CAMERA_SYSTEM=0 -DSUPPORT_GESTURES_SYSTEM=0
 -DSUPPORT_RPRAND_GENERATOR=0 -DSUPPORT_MOUSE_GESTURES=0 -DSUPPORT_SSH_KEYBOARD_RPI=0 -DSUPPORT_SCREEN_CAPTURE=0
 -DSUPPORT_AUTOMATION_EVENTS=0 -DSUPPORT_CLIPBOARD_IMAGE=0
 -DSUPPORT_FILEFORMAT_BMP=0 -DSUPPORT_FILEFORMAT_GIF=0 -DSUPPORT_FILEFORMAT_QOI=0
 -DSUPPORT_FILEFORMAT_DDS=0 -DSUPPORT_FILEFORMAT_TTF=0 -DSUPPORT_FILEFORMAT_FNT=0
 -DSUPPORT_FILEFORMAT_WAV=0 -DSUPPORT_FILEFORMAT_MP3=0 -DSUPPORT_FILEFORMAT_QOA=0 -DSUPPORT_FILEFORMAT_XM=0
 -DSUPPORT_FILEFORMAT_MOD=0 -DSUPPORT_FILEFORMAT_FLAC=0"

DS=-fdata-sections
OPT=-Os
case $T in
mac)
    CC="clang -arch arm64 -mmacosx-version-min=12.0"; AR=ar; OPT=-Oz
    EXTRA=; GLFWX="-x objective-c" ;;
win)
    DS= # mingw puts zero-init data in .data with -fdata-sections: 6 MB of exe
    CC=x86_64-w64-mingw32-gcc; AR=x86_64-w64-mingw32-gcc-ar
    EXTRA="-DUNICODE" ;;
linux)
    CC="clang -fno-pie"; AR=llvm-ar; OPT=-Oz # clang+lld lto gives the smallest elf
    EXTRA="-D_GLFW_X11" ;;
linuxtest)
    CC="gcc -fno-pie"; AR=gcc-ar
    EXTRA="-D_GLFW_X11" ;;
*) echo "usage: $0 mac|win|linux|linuxtest"; exit 1 ;;
esac

rm -f $OUT/*.o $OUT/fail
COMMON="-std=gnu11 $OPT -flto -ffunction-sections $DS -fno-unwind-tables -fno-asynchronous-unwind-tables
 -DNDEBUG -fno-stack-protector -fno-strict-aliasing -w -DPLATFORM_DESKTOP_GLFW -DGRAPHICS_API_OPENGL_33 -D_DEFAULT_SOURCE
 -I$SRC -I$SRC/external/glfw/include $FEATURES"

for m in rcore rmodels rshapes rtextures rtext; do
    ($CC $COMMON $EXTRA -c $SRC/$m.c -o $OUT/$m.o || touch $OUT/fail) &
done
($CC $COMMON $EXTRA $GLFWX -U_GNU_SOURCE -c $SRC/rglfw.c -o $OUT/rglfw.o || touch $OUT/fail) &
wait
[ -e $OUT/fail ] && exit 1
rm -f $OUT/libraylib.a
$AR rcs $OUT/libraylib.a $OUT/*.o
ls -l $OUT/libraylib.a
