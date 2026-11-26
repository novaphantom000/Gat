cmake_minimum_required(VERSION 3.22)
project(outonparole C)

# ---------------------------------------------------------------------------------------------------------
# Out on Parole for Android: the game's own sources plus raylib built from source for PLATFORM_ANDROID with
# OpenGL ES 3.0. raylib is fetched at configure time; point RAYLIB_DIR at a local checkout to build offline.
# ---------------------------------------------------------------------------------------------------------

set(REPO ${CMAKE_CURRENT_SOURCE_DIR}/..)
set(RAYLIB_TAG "6.2" CACHE STRING "raylib git tag to fetch (the game uses the 6.x Mesh.boneIndices API)")
set(RAYLIB_DIR "" CACHE PATH "existing raylib checkout, skips the download")
set(OOP_GEN_DIR "${REPO}/build" CACHE PATH "where tools/pack.py and tools/pack_sfx.py put assets.c and sfx.c")

foreach(f assets.c sfx.c)
    if(NOT EXISTS ${OOP_GEN_DIR}/${f})
        message(FATAL_ERROR
            "${OOP_GEN_DIR}/${f} is missing. The game's models and sounds are packed into generated C files:\n"
            "  python3 tools/pack_sfx.py   -> build/sfx.c    (needs ffmpeg with libvorbis)\n"
            "  make assets                 -> build/assets.c (needs Blender and the model packs in raw/, see README)\n"
            "or set -DOOP_GEN_DIR=<dir holding both>.")
    endif()
endforeach()

# ---- raylib
if(RAYLIB_DIR)
    set(RL_SRC ${RAYLIB_DIR}/src)
else()
    include(FetchContent)
    FetchContent_Declare(raylib_src
        GIT_REPOSITORY https://github.com/raysan5/raylib.git
        GIT_TAG ${RAYLIB_TAG}
        GIT_SHALLOW TRUE
        SOURCE_SUBDIR do-not-build)       # only the sources are wanted, not raylib's own CMake project
    FetchContent_MakeAvailable(raylib_src)
    set(RL_SRC ${raylib_src_SOURCE_DIR}/src)
endif()

# raylib asks EGL for an ES 2 context even when built for ES 3; ask for 3 so the game's GLSL ES 300 shaders,
# 2D array textures and multisampled renderbuffers are guaranteed. Done on a copy so the download stays pristine.
set(RL_PATCHED ${CMAKE_BINARY_DIR}/raylib-src)
if(NOT EXISTS ${RL_PATCHED}/.patched)
    file(REMOVE_RECURSE ${RL_PATCHED})
    file(COPY ${RL_SRC}/ DESTINATION ${RL_PATCHED})
    file(READ ${RL_PATCHED}/platforms/rcore_android.c android_c)
    string(REPLACE "EGL_CONTEXT_CLIENT_VERSION, 2," "EGL_CONTEXT_CLIENT_VERSION, 3," android_c "${android_c}")
    file(WRITE ${RL_PATCHED}/platforms/rcore_android.c "${android_c}")
    file(WRITE ${RL_PATCHED}/.patched "")
endif()

set(RAYLIB_SOURCES
    ${RL_PATCHED}/rcore.c ${RL_PATCHED}/rshapes.c ${RL_PATCHED}/rtextures.c ${RL_PATCHED}/rtext.c ${RL_PATCHED}/rmodels.c
    ${ANDROID_NDK}/sources/android/native_app_glue/android_native_app_glue.c)
set_source_files_properties(${RAYLIB_SOURCES} PROPERTIES COMPILE_FLAGS "-w")

# ---- the game
file(GLOB GAME_SOURCES ${REPO}/src/*.c ${REPO}/src/android/*.c)

add_library(outonparole SHARED
    ${GAME_SOURCES} ${OOP_GEN_DIR}/assets.c ${OOP_GEN_DIR}/sfx.c ${RAYLIB_SOURCES})

# Note: do not add ${RL_PATCHED}/external here. raylib keeps a Win32-only external/dirent.h that
# would shadow the NDK's <dirent.h> and pull in <io.h>. raylib includes its external headers with
# paths relative to ${RL_PATCHED} ("external/..."), which still resolves.
target_include_directories(outonparole PRIVATE
    ${REPO}/src ${RL_PATCHED} ${ANDROID_NDK}/sources/android/native_app_glue)

target_compile_definitions(outonparole PRIVATE
    PLATFORM_ANDROID GRAPHICS_API_OPENGL_ES3 OOP_GLES
    SUPPORT_MODULE_RAUDIO=0              # the game mixes its own sound (src/audio.c, src/out.c)
    _DEFAULT_SOURCE)

target_compile_options(outonparole PRIVATE -std=gnu11 -O2 -ffunction-sections -fdata-sections
    -Wno-missing-field-initializers -Wno-unused-parameter)

# raylib's Android layer wraps fopen (APK assets), like its own build does; android_main() calls the game's main()
target_link_options(outonparole PRIVATE
    -Wl,--wrap=fopen -Wl,--gc-sections -Wl,-z,max-page-size=16384
    -Wl,-u,ANativeActivity_onCreate)

target_link_libraries(outonparole PRIVATE log android EGL GLESv3 m)
