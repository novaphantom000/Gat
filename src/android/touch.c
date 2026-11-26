// Touch controls: floating move stick on the left, camera drag on the right, buttons on top of both.
// Every finger is given a job when it lands (stick, look or one button) and keeps it until it lifts, so
// sliding off a button or across the screen never changes what a finger does.
#include "touch.h"
#include <math.h>
#include <string.h>

#define MAX_FINGERS 10
#define LOOK_SENS 0.0040f     // radians per pixel of drag, the mouse uses 0.0025
#define STICK_R 0.13f         // stick throw, in screen heights
#define DEAD 0.12f

typedef struct {
    uint16_t bit;
    const char *label;
    float x, y, r;            // centre offset from the anchor edge and radius, all in screen heights
    char ax, ay;              // 'l'/'r' and 't'/'b': which edges the offsets are measured from
} Btn;

static const Btn btns[] = {
    { BTN_FIRE,   "FIRE",   0.17f, 0.20f, 0.100f, 'r', 'b' },
    { BTN_JUMP,   "JUMP",   0.36f, 0.10f, 0.065f, 'r', 'b' },
    { BTN_AIM,    "AIM",    0.37f, 0.30f, 0.060f, 'r', 'b' },
    { BTN_ENTER,  "ENTER",  0.16f, 0.45f, 0.062f, 'r', 'b' },
    { BTN_RELOAD, "R",      0.55f, 0.18f, 0.052f, 'r', 'b' },
    { BTN_PREV,   "<",      0.52f, 0.36f, 0.046f, 'r', 'b' },
    { BTN_NEXT,   ">",      0.64f, 0.28f, 0.046f, 'r', 'b' },
    { BTN_SPRINT, "RUN",    0.13f, 0.45f, 0.060f, 'l', 'b' },
    { BTN_CROUCH, "DUCK",   0.28f, 0.58f, 0.050f, 'l', 'b' },
    { BTN_PAUSE,  "II",     0.06f, 0.07f, 0.045f, 'r', 't' },
    { BTN_MAP,    "MAP",    0.16f, 0.07f, 0.045f, 'r', 't' },
    { BTN_CAM,    "CAM",    0.26f, 0.07f, 0.045f, 'r', 't' },
    { BTN_RADIO,  "RADIO",  0.36f, 0.07f, 0.045f, 'r', 't' },
    { BTN_HORN,   "HORN",   0.46f, 0.07f, 0.045f, 'r', 't' },
};
#define NBTN ((int)(sizeof btns / sizeof *btns))

enum { ROLE_NONE = -1, ROLE_STICK = 0, ROLE_LOOK = 1, ROLE_BTN = 2 };   // buttons are ROLE_BTN + index

static struct { int id, role; Vector2 start, last, now; } fing[MAX_FINGERS];
static int nfing;
static uint16_t shown_held;
static float stick_x, stick_y;   // last stick output, for drawing

static Vector2 btn_pos(const Btn *b, int w, int h)
{
    return (Vector2){ b->ax == 'r' ? w - b->x * h : b->x * h, b->ay == 'b' ? h - b->y * h : b->y * h };
}

static int button_at(Vector2 p, int w, int h)
{
    for (int i = 0; i < NBTN; i++) {
        Vector2 c = btn_pos(&btns[i], w, h);
        float r = btns[i].r * h * 1.25f;   // generous: thumbs miss
        if ((p.x - c.x) * (p.x - c.x) + (p.y - c.y) * (p.y - c.y) <= r * r) return i;
    }
    return -1;
}

void touch_read(Input *in, uint16_t *held, int w, int h)
{
    // the fingers on the glass right now
    int n = GetTouchPointCount();
    if (n > MAX_FINGERS) n = MAX_FINGERS;
    Vector2 pos[MAX_FINGERS];
    int ids[MAX_FINGERS];
    for (int i = 0; i < n; i++) { pos[i] = GetTouchPosition(i); ids[i] = GetTouchPointId(i); }

    // drop the ones that lifted
    for (int k = 0; k < nfing; k++) {
        bool alive = false;
        for (int i = 0; i < n; i++) alive |= ids[i] == fing[k].id;
        if (!alive) fing[k--] = fing[--nfing];
    }
    // follow the ones that moved, hand out jobs to new ones
    for (int i = 0; i < n; i++) {
        int k = 0;
        while (k < nfing && fing[k].id != ids[i]) k++;
        if (k == nfing) {
            if (nfing == MAX_FINGERS) continue;
            int b = button_at(pos[i], w, h);
            int role = b >= 0 ? ROLE_BTN + b : pos[i].x < w * 0.42f && pos[i].y > h * 0.2f ? ROLE_STICK : ROLE_LOOK;
            if (role == ROLE_STICK) for (int j = 0; j < nfing; j++) if (fing[j].role == ROLE_STICK) role = ROLE_LOOK;   // one stick
            fing[nfing++] = (typeof(fing[0])){ ids[i], role, pos[i], pos[i], pos[i] };
        }
        fing[k].now = pos[i];
    }

    bool stick_on = false;
    for (int k = 0; k < nfing; k++) {
        if (fing[k].role == ROLE_STICK) {
            float dx = fing[k].now.x - fing[k].start.x, dy = fing[k].now.y - fing[k].start.y;
            float r = STICK_R * h, len = sqrtf(dx * dx + dy * dy), m = fminf(len / r, 1.0f);
            if (m > DEAD) {
                m = (m - DEAD) / (1 - DEAD);
                in->mx = dx / len * m;
                in->my = -dy / len * m;    // screen y points down, forward is up
            }
            stick_x = in->mx; stick_y = in->my;
            stick_on = true;
        } else if (fing[k].role == ROLE_LOOK) {
            in->lx += (fing[k].now.x - fing[k].last.x) * LOOK_SENS;
            in->ly += (fing[k].now.y - fing[k].last.y) * LOOK_SENS;
        } else if (fing[k].role >= ROLE_BTN) {
            *held |= btns[fing[k].role - ROLE_BTN].bit;
        }
        fing[k].last = fing[k].now;
    }
    if (!stick_on) stick_x = stick_y = 0;
    shown_held = *held;
}

void touch_draw(int w, int h)
{
    if (mode == MODE_DEAD || mode == MODE_BUSTED || IsGamepadAvailable(0)) return;
    const Color ink = { 255, 255, 255, 255 };

    // the stick: a faint home ring until a finger lands, then the ring sits where it landed
    Vector2 home = { 0.24f * h, h - 0.28f * h }, knob = home;
    for (int k = 0; k < nfing; k++)
        if (fing[k].role == ROLE_STICK) {
            home = fing[k].start;
            knob = (Vector2){ home.x + stick_x * STICK_R * h, home.y - stick_y * STICK_R * h };
        }
    DrawCircleLines((int)home.x, (int)home.y, STICK_R * h, (Color){ 255, 255, 255, 70 });
    DrawCircleV(knob, 0.055f * h, (Color){ 255, 255, 255, knob.x == home.x && knob.y == home.y ? 40 : 90 });

    for (int i = 0; i < NBTN; i++) {
        const Btn *b = &btns[i];
        Vector2 c = btn_pos(b, w, h);
        bool down = shown_held & b->bit;
        bool paused = mode == MODE_PAUSE && b->bit != BTN_PAUSE;
        int a = paused ? 30 : down ? 150 : 65;
        DrawCircleV(c, b->r * h, (Color){ 20, 24, 32, (unsigned char)a });
        DrawCircleLines((int)c.x, (int)c.y, b->r * h, (Color){ 255, 255, 255, (unsigned char)(paused ? 40 : down ? 230 : 120) });
        int fs = (int)(b->r * h * (strlen(b->label) > 3 ? 0.42f : 0.6f));
        int tw = MeasureText(b->label, fs);
        DrawText(b->label, (int)c.x - tw / 2, (int)c.y - fs / 2, fs, (Color){ ink.r, ink.g, ink.b, (unsigned char)(paused ? 70 : 220) });
    }
}
