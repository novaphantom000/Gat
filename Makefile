CC      := clang
CFLAGS  := -std=c11 -O2 -g -Wall -Wextra -Wno-missing-field-initializers -Wno-unused-parameter \
           -mmacosx-version-min=26.0 -I/opt/homebrew/include -Iraw/raylib/src
LDLIBS  := /opt/homebrew/lib/libraylib.a -framework OpenGL -framework Cocoa -framework IOKit \
           -framework CoreVideo -framework CoreAudio -framework AudioToolbox -framework QuartzCore

SRC := $(wildcard src/*.c)
HEADERS := $(wildcard src/*.h)

GEN := build/assets.c build/sfx.c

outonparole: $(SRC) $(HEADERS) $(GEN)
	$(CC) $(CFLAGS) $(SRC) $(GEN) -o $@ $(LDLIBS)

build/assets.c: tools/pack.py $(wildcard assets/*)
	python3 tools/pack.py

build/sfx.c: tools/pack_sfx.py $(wildcard assets/sfx/*)
	python3 tools/pack_sfx.py

size: outonparole
	@strip -o build/stripped outonparole && ls -l build/stripped | awk '{print $$5, "bytes stripped"}'

clean:
	rm -rf build/*.o build/stripped outonparole

viewer: tools/viewer.c src/pack.c src/game.h build/assets.c
	mkdir -p build/view
	$(CC) $(CFLAGS) -Isrc tools/viewer.c src/pack.c build/assets.c -o build/viewer $(LDLIBS)
	./build/viewer

assets:
	python3 tools/pack.py --force

.PHONY: size clean viewer assets

# release builds: raylib from source (tools/rl.sh), one stripped file per target
OPT := -Os
REL = -std=gnu11 $(OPT) -flto -ffunction-sections -fno-unwind-tables -fno-asynchronous-unwind-tables \
       -fno-stack-protector -DRELEASE -w -Isrc -Iraw/raylib/src
REL_SRC := $(filter-out src/render.c src/fx.c,$(SRC)) build/rel/render.c build/rel/fx.c build/rel/shaders.c $(GEN)

build/rel/shaders.c: tools/shaders.py src/render.c src/fx.c
	@mkdir -p build/rel
	python3 tools/shaders.py build/rel src/render.c src/fx.c

# every gl* name the game source mentions; the glad trim in rl.sh keeps exactly those (plus raylib's own)
build/gl.used: $(SRC)
	@mkdir -p build
	@grep -ohE '\b(GLAD_)?gl[A-Z][A-Za-z0-9_]*' $(SRC) | sort -u > $@.tmp; cmp -s $@.tmp $@ && rm $@.tmp || mv $@.tmp $@

build/rl-%/libraylib.a: tools/rl.sh tools/glfwmap.py tools/gladtrim.py build/gl.used
	tools/rl.sh $*

dist/OutOnParole-mac: OPT := -Oz
dist/OutOnParole-mac: $(SRC) $(HEADERS) $(GEN) build/rel/shaders.c build/rl-mac/libraylib.a
	@mkdir -p dist
	clang -arch arm64 -mmacosx-version-min=12.0 -fdata-sections $(REL) $(REL_SRC) build/rl-mac/libraylib.a -o $@ \
	    -Wl,-dead_strip -framework OpenGL -framework Cocoa -framework IOKit -framework CoreVideo \
	    -framework CoreAudio -framework AudioToolbox -framework QuartzCore
	strip -x $@
	codesign -s - -f $@

# windows: each file through apple clang -Oz (mingw headers), linked by mingw gcc
WINCC = clang --target=x86_64-w64-mingw32 -isystem /opt/homebrew/opt/mingw-w64/toolchain-x86_64/x86_64-w64-mingw32/include
WINFLAGS := -std=gnu11 -Oz -ffunction-sections -fno-unwind-tables -fno-asynchronous-unwind-tables -fno-stack-protector -DRELEASE -w -Isrc -Iraw/raylib/src
WINOBJ := $(addprefix build/win/,$(notdir $(REL_SRC:.c=.o)))

# The shader generation step writes all three sources. An implicit rule
# can otherwise see src/render.c and src/fx.c first on a clean build.
build/win/render.o build/win/fx.o build/win/shaders.o: build/win/%.o: build/rel/shaders.c $(HEADERS) Makefile
	@mkdir -p build/win
	$(WINCC) $(WINFLAGS) -c build/rel/$*.c -o $@
build/win/%.o: src/%.c $(HEADERS)
	@mkdir -p build/win
	$(WINCC) $(WINFLAGS) -c $< -o $@
build/win/%.o: build/%.c
	@mkdir -p build/win
	$(WINCC) $(WINFLAGS) -c $< -o $@

dist/OutOnParole.exe: $(WINOBJ) build/rl-win/libraylib.a
	@mkdir -p dist
	x86_64-w64-mingw32-gcc $(WINOBJ) build/rl-win/libraylib.a -o $@ \
	    -static -mwindows -Wl,--gc-sections -s -lopengl32 -lgdi32 -lwinmm -lshell32

dist/OutOnParole-linux: OPT := -Oz
dist/OutOnParole-linux: $(SRC) $(HEADERS) $(GEN) build/rel/shaders.c build/rl-linux/libraylib.a
	@mkdir -p dist
	clang -fno-pie -fdata-sections $(REL) $(REL_SRC) build/rl-linux/libraylib.a -o $@ \
	    -fuse-ld=lld -no-pie -Wl,--gc-sections -Wl,--build-id=none -s -lm -lpthread -ldl -lrt

mac: dist/OutOnParole-mac
win: dist/OutOnParole.exe

# the linux build runs inside an x86_64 ubuntu container (colima); raylib's linux objects are built there too
linux: $(SRC) $(HEADERS) $(GEN)
	@docker image inspect oop-linux >/dev/null 2>&1 || docker build --platform linux/amd64 -t oop-linux -f tools/linux.Dockerfile tools
	docker run --rm --platform linux/amd64 -v $(CURDIR):/w -w /w oop-linux make dist/OutOnParole-linux

dist: mac win linux
	@wc -c dist/OutOnParole-mac dist/OutOnParole.exe dist/OutOnParole-linux | awk \
	    '$$2 ~ /^dist\// { print $$1 " bytes  " $$2 ($$1 >= 1000000 ? " (size limit reached)" : ""); n++; if ($$1 >= 1000000) over=1 } END { exit n != 3 || over }'

# a native arm64 linux box with a virtual display, for testing while the mac's screen is locked
build/oop-test: $(SRC) $(HEADERS) $(GEN) build/rel/shaders.c build/rl-linuxtest/libraylib.a
	gcc -std=gnu11 -O2 -g -w -Iraw/raylib/src $(REL_SRC) build/rl-linuxtest/libraylib.a -o $@ -no-pie -lm -lpthread -ldl -lrt

testbox: $(SRC) $(HEADERS) $(GEN)
	@docker image inspect oop-test >/dev/null 2>&1 || docker build -t oop-test -f tools/test.Dockerfile tools
	docker run --rm -v $(CURDIR):/w -w /w oop-test make build/oop-test

.PHONY: mac win linux dist testbox
