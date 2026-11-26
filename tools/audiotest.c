// offline checks for audio.c: renders scenes to wav files in build/audiowav/
// build: see the clang line in the audio notes; run from the project root
#include <stdio.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "game.h"

bool audio_offline = true;
int mode, heat;
float day_hours = 12;

static const char *names[S_COUNT] = { "pistol", "smg", "shotgun", "empty", "reload", "punch", "hit", "crash_small",
    "crash_big", "glass", "explosion", "ricochet", "step", "door", "scream", "pickup", "cash", "bodyfall", "ui" };

static void wav(const char *name, const float *b, int frames)
{
    char path[256];
    snprintf(path, sizeof path, "build/audiowav/%s.wav", name);
    FILE *f = fopen(path, "wb");
    int n = frames * 4, sr = 44100, br = sr * 4;
    short ch = 2, al = 4, bits = 16, fmt = 1;
    int sixteen = 16;
    fwrite("RIFF", 1, 4, f); int rl = 36 + n; fwrite(&rl, 4, 1, f);
    fwrite("WAVEfmt ", 1, 8, f); fwrite(&sixteen, 4, 1, f); fwrite(&fmt, 2, 1, f); fwrite(&ch, 2, 1, f);
    fwrite(&sr, 4, 1, f); fwrite(&br, 4, 1, f); fwrite(&al, 2, 1, f); fwrite(&bits, 2, 1, f);
    fwrite("data", 1, 4, f); fwrite(&n, 4, 1, f);
    for (int i = 0; i < frames * 2; i++) { float v = b[i] > 1 ? 1 : b[i] < -1 ? -1 : b[i]; short s = (short)(v * 32767); fwrite(&s, 2, 1, f); }
    fclose(f);
}

typedef void (*Scene)(float t);

static float *run(const char *name, float secs, Scene sc, int ragged)
{
    static const int odd[] = { 1, 63, 64, 65, 130, 733, 400 };
    int frames = (int)(secs * 44100), done = 0, k = 0;
    float *buf = malloc(sizeof(float) * frames * 2);
    while (done < frames) {
        if (done % 735 == 0 || !ragged) { if (sc) sc(done / 44100.0f); audio_tick(DT); }
        int n = ragged ? odd[k++ % 7] : 735;
        int to_tick = 735 - done % 735;
        if (n > to_tick) n = to_tick;
        if (n > frames - done) n = frames - done;
        audio_render(buf + done * 2, n);
        done += n;
    }
    if (name) wav(name, buf, frames);
    return buf;
}

static void reset(void)
{
    memset(cars, 0, sizeof cars);
    for (int i = 0; i < MAX_CARS; i++) cars[i].driver = -1;
    cam = (Camera3D){ { 0, 1.7f, 0 }, { 0, 1.7f, 10 }, { 0, 1, 0 }, 60, 0 };
    peds[PLAYER].car = -1;
}

static void s_none(float t) {}

static float cur_d;
static void s_oneshot(float t)
{
    static int fired = -1;
    int slot = (int)(t / 3);
    if (slot != fired && slot < S_COUNT) { fired = slot; sfx(slot, (Vector3){ 0, 1.2f, cur_d }, 1, 1); }
}

static void s_engine(float t)
{
    Car *c = &cars[0];
    c->used = true; c->driver = 1; c->model = CAR_SEDAN; c->rpm = t < 2 ? 0 : (t - 2) / 6; if (c->rpm > 1) c->rpm = 1;
    c->throttle = t < 2 ? 0 : 0.8f; c->pos = (Vector3){ 8, 0.5f, -50 + 20 * t }; c->vel = (Vector3){ 0, 0, 20 };
}

static void s_player(float t)
{
    Car *c = &cars[0];
    c->used = true; c->driver = 0; c->model = CAR_PICKUP; c->rpm = 0.1f + 0.8f * (t / 6); c->throttle = 0.7f;
    c->pos = (Vector3){ 0, 0.5f, 0 }; peds[PLAYER].car = 0;
}

static void s_siren(float t)
{
    Car *c = &cars[1];
    c->used = true; c->driver = 2; c->siren = true; c->model = CAR_COP; c->rpm = 0.5f; c->throttle = 0.5f;
    c->pos = (Vector3){ 10, 0.5f, -150 + 15 * t }; c->vel = (Vector3){ 0, 0, 15 };
}

static void s_misc(float t)
{
    Car *a = &cars[2], *b = &cars[3], *c = &cars[4];
    a->used = b->used = c->used = true;
    a->pos = (Vector3){ 6, 0, 8 }; b->pos = (Vector3){ -6, 0, 12 }; c->pos = (Vector3){ 4, 0, 6 };
    a->skid = t > 1 && t < 5 ? 0.3f + 0.6f * (t - 1) / 4 : 0;
    b->horn = (t > 1 && t < 1.6f) || (t > 3 && t < 4.5f);
    c->fire_s = t > 1 ? 5 : 0;
}

static void s_stress(float t)
{
    if ((int)(t * 60) % 3 == 0) sfx(S_PISTOL, (Vector3){ 0, 1, 2 }, 1, 1);
    if ((int)(t * 60) % 20 == 0) sfx(S_EXPLOSION, (Vector3){ 0, 1, 2 }, 1, 1);
    if ((int)(t * 60) % 7 == 0) sfx(S_SHOTGUN, (Vector3){ 0, 1, 2 }, 1, 1);
    if ((int)(t * 60) % 11 == 0) sfx(S_CRASH_BIG, (Vector3){ 0, 1, 2 }, 1, 1);
    if ((int)(t * 60) % 5 == 0) sfx(S_SMG, (Vector3){ 0, 1, 2 }, 1, 1);
    s_siren(t); cars[1].pos = (Vector3){ 0, 0, 4 };
    s_player(t);
}

static int check_continuity(const char *tag, const float *b, int frames)
{
    float worst = 0, peak = 0, dc = 0; int at = 0;
    for (int i = 2; i < frames * 2; i++) {
        float d = b[i] - b[i - 2] > 0 ? b[i] - b[i - 2] : b[i - 2] - b[i];
        if (d > worst) { worst = d; at = i / 2; }
        float a = b[i] > 0 ? b[i] : -b[i];
        if (a > peak) peak = a;
        dc += b[i];
    }
    printf("%-14s peak %.3f  max step %.3f at %.2fs  dc %.5f\n", tag, peak, worst, at / 44100.0f, dc / (frames * 2));
    return 0;
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    system("mkdir -p build/audiowav");
    audio_init();

    float dists[] = { 2, 30, 110 };
    for (int k = 0; k < 3; k++) {
        reset(); cur_d = dists[k];
        char nm[64]; snprintf(nm, sizeof nm, "oneshots_%dm", (int)dists[k]);
        float *b = run(nm, S_COUNT * 3, s_oneshot, 735);
        for (int i = 0; i < S_COUNT; i++) {
            char t[64]; snprintf(t, sizeof t, "%s@%dm", names[i], (int)dists[k]);
            float pk = 0; for (int j = i * 3 * 44100 * 2; j < (i * 3 + 3) * 44100 * 2; j++) { float a = b[j] < 0 ? -b[j] : b[j]; if (a > pk) pk = a; }
            printf("%-18s peak %.3f (%.1f dBFS)\n", t, pk, 20 * log10f(pk + 1e-9f));
        }
        free(b);
    }
    reset(); float *b;
    b = run("engine_pass", 10, s_engine, 735); check_continuity("engine_pass", b, 441000); free(b);
    reset(); b = run("engine_player", 6, s_player, 735); check_continuity("engine_player", b, 264600); free(b);
    reset(); b = run("siren", 24, s_siren, 735); check_continuity("siren", b, 24 * 44100); free(b);
    reset(); b = run("misc", 7, s_misc, 735); check_continuity("misc", b, 7 * 44100); free(b);
    day_hours = 12; reset(); b = run("amb_day", 12, s_none, 735); check_continuity("amb_day", b, 12 * 44100); free(b);
    day_hours = 23; reset(); b = run("amb_night", 12, s_none, 735); check_continuity("amb_night", b, 12 * 44100); free(b);
    day_hours = 12; reset(); b = run("stress", 6, s_stress, 735); check_continuity("stress", b, 6 * 44100); free(b);

    reset(); b = run("engine_ragged", 10, s_engine, 1); check_continuity("engine_ragged", b, 441000); free(b);
    return 0;
}
