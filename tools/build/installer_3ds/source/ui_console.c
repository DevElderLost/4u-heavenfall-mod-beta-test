/* The simple display (ui_draw.h): the view as text on the two consoles,
 * laid out by uitext.c (tested on the PC) in the console font's code page 437. Only the rows that changed since the
 * last frame are printed again, each at its full width, so nothing is cleared and nothing flickers. */
#include <3ds.h>
#include <stdio.h>
#include <string.h>

#include "ui_draw.h"
#include "uitext.h"

static PrintConsole top_console, bottom_console;
static HfTextScreens now, last;
static int have_last;

void console_init(void) {
    consoleInit(GFX_TOP, &top_console);
    consoleInit(GFX_BOTTOM, &bottom_console);
    have_last = 0;
}

/* A row's colour as the console's escape codes (bold: the bright colours). */
static const char *colour(int style) {
    switch (style) {
    case HF_TONE_GOOD:
    case HF_STYLE_GOLD: return "\x1b[0;1;33m";
    case HF_TONE_NEW: return "\x1b[0;1;35m";
    case HF_TONE_WARN: return "\x1b[0;33m";
    case HF_TONE_BAD: return "\x1b[0;1;31m";
    case HF_TONE_MUTED: return "\x1b[0;2;37m";
    case HF_STYLE_SELECTED: return "\x1b[0;7m";
    default: return "\x1b[0m";
    }
}

/* The rows of one screen that changed, never its last column (printing it would move the cursor on). */
static void rows(PrintConsole *console, const char *grid, size_t stride, int cols, const unsigned char *style,
                 const char *old, const unsigned char *old_style) {
    int r;
    consoleSelect(console);
    for (r = 0; r < HF_TEXT_ROWS; r++) {
        const char *row = grid + (size_t)r * stride;
        if (have_last && !strcmp(row, old + (size_t)r * stride) && style[r] == old_style[r]) continue;
        printf("\x1b[%d;1H%s%.*s\x1b[0m", r + 1, colour(style[r]), cols - 1, row);
    }
}

void console_draw(const HfView *v, unsigned tick, const char *badge) {
    hf_text_screens(v, badge, tick, &now);
    rows(&top_console, now.top[0], sizeof now.top[0], HF_TEXT_TOP_COLS, now.top_style, last.top[0], last.top_style);
    rows(&bottom_console, now.bottom[0], sizeof now.bottom[0], HF_TEXT_BOTTOM_COLS, now.bottom_style, last.bottom[0],
         last.bottom_style);
    gfxFlushBuffers();
    memcpy(&last, &now, sizeof last);
    have_last = 1;
}

int console_touch(const HfView *v, int px, int py) {
    return have_last ? hf_text_touch(&last, v, px, py) : -1;
}
