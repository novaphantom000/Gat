# Gat: Out on Parole for Android

An Android port of [shaydex-codes/outonparole](https://github.com/shaydex-codes/outonparole), a small open-world
crime game in C and raylib. The game code is the original's; this repo adds the Android build, an OpenGL ES 3.0
renderer path, an AAudio sound backend and on-screen touch controls.

> **Status: written and statically checked, not yet run on a device.** The C sources compile warning-free against the
> GLES3 headers with the Android defines, and all 16 shader programs (32 stages) compile as GLSL ES 3.00 (`python3 tools/check_shaders.py`).
> The APK itself has not been built or launched. See "Untested" below.

## You need one thing first: the packed assets

The models and sounds are compiled into the executable from two generated files, `build/assets.c` and `build/sfx.c`.
Neither is in the upstream repo, and the build stops with a message until both exist.

* `build/sfx.c`: `python3 tools/pack_sfx.py` (needs `ffmpeg` with libvorbis; reads `assets/sfx/*.ogg`, which are in this repo).
* `build/assets.c`: `make assets` (needs Blender, the model packs unpacked under `raw/`, and numpy; see
  `tools/pack.py`, `tools/prep_*.py` and the credits below). The Makefile expects Blender at the macOS path, edit
  `BLENDER` in `tools/pack.py` for other systems.

The packs are Quaternius characters/animations/guns (CC0), the car pack by comrade1280 on Sketchfab (CC BY 4.0, needs
a Sketchfab login to download) and the police helicopter from Poly Pizza (CC0). They are not redistributed here.

## Build

Needs Android Studio (or JDK 17 + Android SDK), NDK r26 or newer, CMake 3.22.1 from the SDK manager, and network
access on the first configure (raylib 6.2 is fetched from GitHub; pass `-DRAYLIB_DIR=/path/to/raylib` to use a local copy).

    gradle wrapper            # once, if you are not using Android Studio, then:
    ./gradlew assembleDebug   # -> app/build/outputs/apk/debug/app-debug.apk
    adb install -r app/build/outputs/apk/debug/app-debug.apk

Opening the folder in Android Studio and pressing Run works too. minSdk is 26, ABIs are arm64-v8a and x86_64.

## Controls

Left half of the screen: drag anywhere for the move stick (steer and gas/brake in a car). Right half: drag to look.
Buttons: FIRE, AIM, JUMP (handbrake in a car), ENTER (get in/out, confirm in shops), R (reload), `<` `>` (weapon
swap, menu up/down), RUN, DUCK, HORN, MAP, CAM, RADIO, and II for pause. A gamepad works as upstream and hides the overlay.

## What changed from upstream

* `src/render.c`: `#version 300 es` prelude with precisions; 2x MSAA (the largest sample count the driver offers for the
  format) and a 2048 shadow map instead of 4x and 4096; RGBA16F/R11F_G11F_B10F targets need `GL_EXT_color_buffer_float`
  and fall back to 8-bit without it; `GL_DEPTH_COMPONENT24` uploaded as `GL_UNSIGNED_INT`; no `CLAMP_TO_BORDER` (the shader
  already returns "lit" outside the map); `glDrawBuffers` instead of `glDrawBuffer`.
* `src/world.c`: `glMultiDrawElements` becomes a loop of `glDrawElements` (not in ES).
* `src/city.h`: GLES3 headers instead of raylib's glad loader.
* `src/out.c`: AAudio backend, looked up with `dlopen`, in front of the existing Windows/macOS/ALSA ones.
* `src/main.c`: touch input hook, no cursor capture, no session logging, no MSAA backbuffer on Android.
* `src/android/touch.[ch]`: new, the on-screen controls.
* `app/`: Gradle module, manifest (NativeActivity, landscape), `CMakeLists.txt` that builds raylib 6.2 from source with
  `PLATFORM_ANDROID` + `GRAPHICS_API_OPENGL_ES3` and requests an ES 3 EGL context (raylib asks for 2 by default).
* `tools/check_shaders.py`: compiles every shader as 330 core and ES 300 with `glslangValidator`.

The desktop `Makefile` and everything else is untouched; the `#ifdef`s keep the desktop path as it was.

## Untested

Things I could not check without a device or the NDK, in the order I would look at them if something is wrong:

* The whole native build (NDK link, `--wrap=fopen`, `android_native_app_glue`).
* Frame rate. The renderer is a desktop one (HDR targets, bloom, 3x3 PCF shadows, dozens of dynamic lights). If it is slow,
  lower `MSAA` and `SH_SIZE` at the top of `src/render.c`, or render to a smaller target.
* Touch layout and sensitivity (`src/android/touch.c`, `LOOK_SENS`, the `btns` table).
* Behaviour across app backgrounding. raylib detaches and rebinds the EGL context, which keeps GL objects alive.

## License and credits

The upstream repo has no license file, so its code is all rights reserved by its author by default. Check with
shaydex-codes before publishing this port or distributing an APK. Asset credits from upstream:

- Characters, animations, guns: Quaternius (CC0)
- Cars: [Generic passenger car pack](https://sketchfab.com/3d-models/20f9af9b8a404d5cb022ac6fe87f21f5) by comrade1280, CC BY 4.0, simplified and repainted
- Police helicopter: kazuma, Poly Pizza (CC0)
- Sounds: Kenney and OpenGameArt (Tabasco / Vincent Sevedge, kurt, rubberduck, StarNinjas, Joth, TinyWorlds, Till Behrend, Nocturnal_Vanguard, WuxiaScrub), CC0. Engines, sirens and ambience are synthesized in `src/audio.c`.
