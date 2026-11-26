#ifndef TOUCH_H
#define TOUCH_H

#include "../game.h"

// On-screen controls for phones. touch_read adds the stick, the look drag and the buttons to what the
// keyboard/gamepad code already collected; touch_draw paints them over the HUD.
void touch_read(Input *in, uint16_t *held, int w, int h);
void touch_draw(int w, int h);

#endif
