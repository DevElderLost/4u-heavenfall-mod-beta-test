/* The launcher's screens as text and its buttons' places (portable C99).
 * The simple display mode draws an HfView (uiview.h) on the two consoles: the top one 50 x 30 cells, the bottom one
 * 40 x 30, in the console font's code page 437 (hf_cp437). The graphic drawer (the app's ui_gpu.c) takes the bottom
 * screen's button boxes from here, so a touch reads the same layout that was drawn in either mode.
 * tests/install/launcher/test_launcher_uitext.py builds this with the host gcc. */
#ifndef HF_UITEXT_H
#define HF_UITEXT_H

#include "uiview.h"

#define HF_TEXT_ROWS 30
#define HF_TEXT_TOP_COLS 50
#define HF_TEXT_BOTTOM_COLS 40

/* A row's colour: an HfTone (uiview.h), or one of these. */
enum { HF_STYLE_GOLD = HF_TONE_MUTED + 1, HF_STYLE_SELECTED };

typedef struct {
    char top[HF_TEXT_ROWS][HF_TEXT_TOP_COLS + 1];          /* CP437 bytes, padded with spaces, NUL-terminated */
    char bottom[HF_TEXT_ROWS][HF_TEXT_BOTTOM_COLS + 1];
    unsigned char top_style[HF_TEXT_ROWS];                 /* HfTone or HF_STYLE_* */
    unsigned char bottom_style[HF_TEXT_ROWS];
    signed char bottom_button[HF_TEXT_ROWS];               /* the index into the view's buttons drawn on this row, -1 */
} HfTextScreens;

/* The view as the two text grids. The last column of each grid stays blank (printing it would move the console's
 * cursor to the next row). `badge` (UTF-8, "" for none) goes at the bottom screen's right above the footer (the
 * simple display's name); `tick` turns the spinner shown while v->busy. A button that does not fit is not drawn. */
void hf_text_screens(const HfView *v, const char *badge, unsigned tick, HfTextScreens *out);

/* The id of the enabled button drawn under the bottom screen's pixel (px, py) in the text layout, else -1. */
int hf_text_touch(const HfTextScreens *s, const HfView *v, int px, int py);

/* ---- the graphic layout's buttons (320 x 240: the bottom screen) ---- */

typedef struct {
    int x, y, w, h;
} HfBox;

/* The boxes of v->buttons, in their order: a primary button 56 pixels high across the screen, the others 44; one
 * column when they fit, else the others two by two. Above the footer's line; on the task screen under the cancel
 * text. A button that does not fit gets an empty box, and so do all after it. The number laid out. */
int hf_button_boxes(const HfView *v, HfBox boxes[HF_VIEW_BUTTONS]);

/* The id of the enabled button whose box holds (px, py), else -1. */
int hf_box_touch(const HfView *v, const HfBox boxes[HF_VIEW_BUTTONS], int px, int py);

/* The button the D-pad moves to from button `from` (an index; -1 none yet), (dx, dy) one of the four directions, in
 * the graphic layout: the nearest enabled button that way, one in line first, so left and right cross the two columns.
 * Up and down wrap round to the other end; left and right with nothing that way stay. The index. */
int hf_button_step(const HfView *v, int from, int dx, int dy);

#endif
