/* The drawing thread's two drawers (ui_core.c picks one at the start).
 * Init and fini run on the main thread, draw and touch on the drawing thread. */
#ifndef UI_DRAW_H
#define UI_DRAW_H

#include <stddef.h>

#include "uiview.h"

/* ui_gpu.c: citro2d with the system font. 0, or -1 with the step that failed in `why` (everything undone). */
int gpu_init(char *why, size_t cap);
void gpu_fini(void);
void gpu_draw(const HfView *v, unsigned tick);          /* one frame of both screens; `tick` turns the spinner */
int gpu_touch(const HfView *v, int px, int py);         /* the enabled button's id under the touch, else -1 */

/* ui_console.c: the simple display, the view as text on the two consoles. */
void console_init(void);
void console_draw(const HfView *v, unsigned tick, const char *badge);
int console_touch(const HfView *v, int px, int py);     /* in the layout last drawn */

#endif
