/* The graphic display (ui_draw.h): citro2d with the system font (mapped
 * by fontEnsureMapped, never loaded with C2D_FontLoadSystem) and the PC program's colours (hf_tuning.h). The top
 * screen: a header with the logo and the heading, then the screen's own text; a message is a box over it. The bottom
 * screen: the buttons in uitext.c's boxes (the touch reads the same ones), the big one golden, and the footer.
 * Text is wrapped here by the font's own widths; what does not fit ends in "...". One text buffer serves every line:
 * it is cleared before each, since a drawn line's glyphs are already in citro2d's vertex buffer. */
#include <3ds.h>
#include <citro2d.h>
#include <stdio.h>
#include <string.h>

#include "hf_tuning.h"
#include "ui_draw.h"
#include "uitext.h"

#define TOP_W 400.0f
#define BOTTOM_W 320.0f
#define SCREEN_H 240.0f
#define OBJECTS 2048                 /* citro2d's quads per frame: ~280 KB of linear memory */
#define GLYPHS 512                   /* one line's glyphs at most */
#define SPAN_MAX 512
#define LOGO_PATH "romfs:/gfx/logo.t3x"
#define LOGO_H 32.0f
#define HEADER_H 42.0f
#define MARGIN 12.0f
#define Z 0.5f

#define S_HEADING 0.72f
#define S_STATE 0.62f
#define S_BODY 0.5f
#define S_SMALL 0.45f
#define S_BUTTON 0.56f
#define S_PRIMARY 0.68f

enum { LEFT = 0, CENTRE, RIGHT };

static C3D_RenderTarget *top, *bot;
static C2D_TextBuf tbuf;
static C2D_SpriteSheet sheet;
static C2D_Image logo;
static CFNT_s *font;
static int started;                  /* how far gpu_init got: 1 citro3d, 2 citro2d */

static u32 rgba(u32 c, u8 a) { return C2D_Color32((u8)(c >> 16), (u8)(c >> 8), (u8)c, a); }
static u32 rgb(u32 c) { return rgba(c, 0xFF); }

static u32 tone_rgb(int tone) {
    switch (tone) {
    case HF_TONE_GOOD: return rgb(HF_RGB_GOLD);
    case HF_TONE_NEW: return rgb(HF_RGB_VIOLET);
    case HF_TONE_WARN: return rgb(HF_RGB_ORANGE);
    case HF_TONE_BAD: return rgb(HF_RGB_DANGER);
    case HF_TONE_MUTED: return rgb(HF_RGB_MUTED);
    default: return rgb(HF_RGB_TEXT);
    }
}

/* ---- start and end ---- */

void gpu_fini(void) {
    if (sheet) C2D_SpriteSheetFree(sheet);
    sheet = NULL;
    memset(&logo, 0, sizeof logo);
    if (tbuf) C2D_TextBufDelete(tbuf);
    tbuf = NULL;
    if (top) C3D_RenderTargetDelete(top);
    if (bot) C3D_RenderTargetDelete(bot);
    top = bot = NULL;
    if (started >= 2) C2D_Fini();
    if (started >= 1) C3D_Fini();
    started = 0;
}

static int failed(char *why, size_t cap, const char *step) {
    snprintf(why, cap, "%s failed", step);
    gpu_fini();
    return -1;
}

int gpu_init(char *why, size_t cap) {
    if (R_FAILED(fontEnsureMapped())) return failed(why, cap, "the system font");
    font = fontGetSystemFont();
    if (!C3D_Init(C3D_DEFAULT_CMDBUF_SIZE)) return failed(why, cap, "C3D_Init");
    started = 1;
    if (!C2D_Init(OBJECTS)) return failed(why, cap, "C2D_Init");
    started = 2;
    C2D_Prepare();
    top = C2D_CreateScreenTarget(GFX_TOP, GFX_LEFT);
    bot = C2D_CreateScreenTarget(GFX_BOTTOM, GFX_LEFT);
    if (!top || !bot) return failed(why, cap, "the screens' render targets");
    tbuf = C2D_TextBufNew(GLYPHS);
    if (!tbuf) return failed(why, cap, "the text buffer");
    sheet = C2D_SpriteSheetLoad(LOGO_PATH);
    if (!sheet || C2D_SpriteSheetCount(sheet) < 1) return failed(why, cap, "the logo's texture");
    logo = C2D_SpriteSheetGetImage(sheet, 0);
    return 0;
}

/* ---- text ---- */

static float line_h(float scale) { return fontGetInfo(font)->lineFeed * scale; }

/* The code point at `s` (UTF-8) and its bytes. */
static u32 next_cp(const char *s, int *bytes) {
    u32 cp = 0;
    ssize_t n = decode_utf8(&cp, (const u8 *)s);
    if (n <= 0) {
        *bytes = 1;
        return '?';
    }
    *bytes = (int)n;
    return cp;
}

static float glyph_w(u32 cp, float scale) {
    charWidthInfo_s *w = fontGetCharWidthInfo(font, fontGlyphIndexFromCodePoint(font, cp));
    return w ? w->charWidth * scale : 0;
}

static float width_of(const char *s, size_t n, float scale) {
    float w = 0;
    size_t i = 0;
    while (i < n && s[i]) {
        int k;
        w += glyph_w(next_cp(s + i, &k), scale);
        i += (size_t)k;
    }
    return w;
}

/* The bytes of s[0..n) that fit `width` (whole code points). */
static size_t fit(const char *s, size_t n, float width, float scale) {
    float w = 0;
    size_t i = 0;
    while (i < n && s[i]) {
        int k;
        float g = glyph_w(next_cp(s + i, &k), scale);
        if (w + g > width) break;
        w += g;
        i += (size_t)k;
    }
    return i;
}

/* s[0..n) drawn in a box from `x`, `width` wide: at its left, centred or at its right. */
static void draw_at(const char *s, size_t n, float x, float y, float width, float scale, u32 color, int align) {
    char buf[SPAN_MAX];
    C2D_Text t;
    if (!n) return;
    if (n >= sizeof buf) n = sizeof buf - 1;
    memcpy(buf, s, n);
    buf[n] = 0;
    C2D_TextBufClear(tbuf);
    C2D_TextParse(&t, tbuf, buf);
    C2D_TextOptimize(&t);
    if (align == CENTRE) C2D_DrawText(&t, C2D_WithColor | C2D_AlignCenter, x + width / 2, y, Z, scale, scale, color);
    else if (align == RIGHT) C2D_DrawText(&t, C2D_WithColor | C2D_AlignRight, x + width, y, Z, scale, scale, color);
    else C2D_DrawText(&t, C2D_WithColor, x, y, Z, scale, scale, color);
}

/* s[0..n) in `width`: when it is wider, or when `dots` (text is left after it), it ends in "...", cut at a space when
 * one is near. */
static void draw_cut(const char *s, size_t n, int dots, float x, float y, float width, float scale, u32 color, int align) {
    char buf[SPAN_MAX];
    float dw = width_of("...", 3, scale);
    if (!dots && width_of(s, n, scale) <= width) {
        draw_at(s, n, x, y, width, scale, color, align);
        return;
    }
    if (width_of(s, n, scale) + dw > width) {
        size_t k = fit(s, n, width - dw, scale), i = k;
        if (k < n && s[k] != ' ') {
            while (i > k / 2 && s[i] != ' ') i--;
            if (i > k / 2) k = i;
        }
        n = k;
    }
    while (n > 0 && s[n - 1] == ' ') n--;
    if (n > sizeof buf - 4) n = sizeof buf - 4;
    memcpy(buf, s, n);
    memcpy(buf + n, "...", 4);
    draw_at(buf, n + 3, x, y, width, scale, color, align);
}

static void draw_line(const char *s, float x, float y, float width, float scale, u32 color, int align) {
    draw_cut(s, strlen(s), 0, x, y, width, scale, color, align);
}

/* `s` wrapped to `width` from (x, y), at most `max` lines: lines break at spaces, '\n' ends a paragraph (an empty one
 * is a blank line), a "- " item goes on indented; "..." ends the last line when text is left. With `draw` 0 the lines
 * are only counted. The number of lines. */
static int para(const char *s, float x, float y, float width, float scale, u32 color, int max, int align, int draw) {
    float lh = line_h(scale), indent = width_of("- ", 2, scale);
    const char *p = s;
    int lines = 0;
    while (*p && lines < max) {
        const char *end = strchr(p, '\n'), *q = p, *stop;
        size_t len = end ? (size_t)(end - p) : strlen(p);
        int item = len >= 2 && p[0] == '-' && p[1] == ' ', first = 1;
        stop = p + len;
        if (q == stop) lines++;
        while (q < stop && lines < max) {
            float lx = x + (!first && item ? indent : 0), w = width - (lx - x);
            size_t n = (size_t)(stop - q), take = fit(q, n, w, scale), shown;
            const char *rest;
            int more;
            if (take < n) {
                size_t i = take;
                while (i > 0 && q[i] != ' ') i--;
                if (i > 0) take = i;
                else if (!take) {
                    int k;
                    next_cp(q, &k);
                    take = (size_t)k;
                }
            }
            for (rest = q + take; rest < stop && *rest == ' '; rest++) {}
            more = rest < stop || (end && end[1]);
            for (shown = take; shown > 0 && q[shown - 1] == ' '; shown--) {}
            if (draw) draw_cut(q, shown, lines == max - 1 && more, lx, y + lines * lh, w, scale, color, align);
            lines++;
            q = rest;
            first = 0;
        }
        if (!end || !end[1]) break;
        p = end + 1;
    }
    return lines;
}

/* ---- shapes ---- */

static const float DOT[8][2] = {{1, 0}, {.7071f, .7071f}, {0, 1}, {-.7071f, .7071f},
                                {-1, 0}, {-.7071f, -.7071f}, {0, -1}, {.7071f, -.7071f}};

/* Eight dots in a ring, the brightest one going round with `tick`. */
static void spinner(float cx, float cy, unsigned tick) {
    int i;
    for (i = 0; i < 8; i++) {
        unsigned age = (tick - (unsigned)i) & 7;
        C2D_DrawCircleSolid(cx + 6 * DOT[i][0], cy + 6 * DOT[i][1], Z, 1.8f, rgba(HF_RGB_GOLD, (u8)(255 - age * 30)));
    }
}

/* A filled box inside an edge `t` pixels wide. */
static void framed(float x, float y, float w, float h, float t, u32 edge, u32 fill) {
    C2D_DrawRectSolid(x, y, Z, w, h, edge);
    C2D_DrawRectSolid(x + t, y + t, Z, w - 2 * t, h - 2 * t, fill);
}

/* ---- the top screen ---- */

static void header(const char *title) {
    float lw = 0, s;
    C2D_DrawRectSolid(0, 0, Z, TOP_W, HEADER_H, rgb(HF_RGB_CARD));
    C2D_DrawRectSolid(0, HEADER_H, Z, TOP_W, 1, rgb(HF_RGB_BORDER));
    if (logo.subtex && logo.subtex->height) {
        s = LOGO_H / logo.subtex->height;
        C2D_DrawImageAt(logo, 8, (HEADER_H - LOGO_H) / 2, Z, NULL, s, s);
        lw = logo.subtex->width * s + 10;
    }
    draw_line(title, 8 + lw, (HEADER_H - line_h(S_HEADING)) / 2, TOP_W - 16 - lw, S_HEADING, rgb(HF_RGB_GOLD), LEFT);
}

/* The state line (the spinner before it while something runs) and what to do under it: the y under them. */
static float state_block(const HfView *v, float y, unsigned tick, int detail_max) {
    float x = MARGIN, lh = line_h(S_STATE);
    int n = 0;
    if (v->busy) {
        spinner(x + 8, y + lh / 2, tick);
        x += 24;
    }
    if (v->state[0]) n = para(v->state, x, y, TOP_W - MARGIN - x, S_STATE, tone_rgb(v->tone), 2, LEFT, 1);
    if (v->busy && !n) n = 1;
    y += n * lh;
    if (v->detail[0])
        y += para(v->detail, MARGIN, y + 2, TOP_W - 2 * MARGIN, S_BODY, rgb(HF_RGB_MUTED), detail_max, LEFT, 1) *
             line_h(S_BODY) + 2;
    return y;
}

static int lines_left(float y, float lh) {
    int n = (int)((SCREEN_H - 4 - y) / lh);
    return n > 0 ? n : 0;
}

/* The rows: a label and its value in two columns where a '\t' splits them, any other row wrapped. */
static float table(const HfView *v, float y) {
    float lh = line_h(S_BODY), lw = 0, vx;
    int i;
    for (i = 0; i < v->row_count && i < HF_VIEW_ROWS; i++) {
        const char *tab = strchr(v->rows[i], '\t');
        float w = tab ? width_of(v->rows[i], (size_t)(tab - v->rows[i]), S_BODY) : 0;
        if (w > lw) lw = w;
    }
    if (lw > 170) lw = 170;
    vx = MARGIN + lw + 12;
    for (i = 0; i < v->row_count && i < HF_VIEW_ROWS && lines_left(y, lh); i++) {
        const char *row = v->rows[i], *tab = strchr(row, '\t');
        if (tab) {
            draw_cut(row, (size_t)(tab - row), 0, MARGIN, y, lw, S_BODY, rgb(HF_RGB_MUTED), LEFT);
            draw_line(tab + 1, vx, y, TOP_W - MARGIN - vx, S_BODY, rgb(HF_RGB_TEXT), LEFT);
            y += lh;
        } else if (!row[0]) {
            y += lh;
        } else {
            y += para(row, MARGIN, y, TOP_W - 2 * MARGIN, S_BODY, rgb(HF_RGB_TEXT), lines_left(y, lh), LEFT, 1) * lh;
        }
    }
    return y;
}

/* The notes from their line `scroll` on, to the screen's end. */
static void notes(const char *s, int scroll, float y, float scale, float width) {
    while (scroll-- > 0 && s) {
        s = strchr(s, '\n');
        if (s) s++;
    }
    if (s && *s) para(s, MARGIN, y, width, scale, rgb(HF_RGB_TEXT), lines_left(y, line_h(scale)), LEFT, 1);
}

static void notes_screen(const HfView *v) {
    float y0 = HEADER_H + 8, h = SCREEN_H - y0 - 8;
    int count = 1;
    const char *p;
    header(v->notes_title[0] ? v->notes_title : v->heading);
    notes(v->notes, v->notes_scroll, y0, S_BODY, TOP_W - 2 * MARGIN - 8);
    for (p = v->notes; *p; p++) count += *p == '\n';
    if (count > 1) {
        int at = v->notes_scroll < 0 ? 0 : v->notes_scroll >= count ? count - 1 : v->notes_scroll;
        C2D_DrawRectSolid(TOP_W - 7, y0, Z, 3, h, rgb(HF_RGB_BORDER));
        C2D_DrawRectSolid(TOP_W - 8, y0 + (h - 20) * at / (count - 1), Z, 5, 20, rgb(HF_RGB_VIOLET));
    }
}

static void task_screen(const HfView *v, unsigned tick) {
    float y = HEADER_H + 10, lh = line_h(S_BODY), w = TOP_W - 2 * MARGIN, col = w / HF_STAGES, fw;
    unsigned permille = v->task.permille > 1000 ? 1000 : v->task.permille;
    char percent[8];
    int i;
    header(v->heading);
    if (v->task.stage_names[0][0]) {
        for (i = 0; i < HF_STAGES; i++) {
            float cx = MARGIN + i * col, cy = y + lh / 2;
            int done = i < v->task.stage, now = i == v->task.stage;
            if (!v->task.stage_names[i][0]) continue;
            C2D_DrawCircleSolid(cx + 6, cy, Z, 5, rgb(done || now ? HF_RGB_GOLD : HF_RGB_BORDER));
            if (now) C2D_DrawCircleSolid(cx + 6, cy, Z, 3, rgb(HF_RGB_BG));
            draw_line(v->task.stage_names[i], cx + 16, y, col - 20, S_BODY,
                      rgb(done ? HF_RGB_GOLD : now ? HF_RGB_TEXT : HF_RGB_MUTED), LEFT);
        }
        y += lh + 10;
    }
    framed(MARGIN - 1, y - 1, w + 2, 18, 1, rgb(HF_RGB_BORDER), rgb(HF_RGB_CARD));
    fw = w * permille / 1000.0f;
    if (fw > 0) C2D_DrawRectangle(MARGIN, y, Z, fw, 16, rgb(HF_RGB_ORANGE), rgb(HF_RGB_GOLD), rgb(HF_RGB_ORANGE),
                                  rgb(HF_RGB_GOLD));
    y += 22;
    snprintf(percent, sizeof percent, "%u%%", permille / 10);
    draw_line(percent, TOP_W - MARGIN - 60, y, 60, S_BODY, rgb(HF_RGB_GOLD), RIGHT);
    draw_line(v->task.eta, MARGIN, y, w - 70, S_BODY, rgb(HF_RGB_TEXT), LEFT);
    y = state_block(v, y + lh + 10, tick, 2);
    if (v->task.note[0]) para(v->task.note, MARGIN, y + 6, w, S_BODY, rgb(HF_RGB_ORANGE), 3, LEFT, 1);
}

/* A message box over the top screen: its text, then its keys, or the spinner while a step runs (ui_working). */
static void message(const HfView *v, unsigned tick) {
    float w = TOP_W - 48, tw = w - 24, x = 24, lh = line_h(S_BODY), h, y;
    int n = para(v->message.text, 0, 0, tw, S_BODY, 0, 8, LEFT, 0), keys = v->message.keys[0] != 0;
    int tone = v->message.tone, spin = !keys && v->busy;
    h = 14 + n * lh + (keys ? lh + 8 : 0) + (spin ? 30 : 0) + 12;
    y = (SCREEN_H - h) / 2;
    C2D_DrawRectSolid(0, 0, Z, TOP_W, SCREEN_H, rgba(0, 0xA8));
    framed(x - 2, y - 2, w + 4, h + 4, 2, tone == HF_TONE_PLAIN ? rgb(HF_RGB_VIOLET) : tone_rgb(tone), rgb(HF_RGB_CARD));
    para(v->message.text, x + 12, y + 14, tw, S_BODY, tone_rgb(tone), 8, LEFT, 1);
    if (keys) draw_line(v->message.keys, x + 12, y + 14 + n * lh + 8, tw, S_BODY, rgb(HF_RGB_GOLD), LEFT);
    if (spin) spinner(TOP_W / 2, y + 14 + n * lh + 18, tick);
}

static void draw_top(const HfView *v, unsigned tick) {
    float y;
    if (v->screen == HF_SCREEN_NOTES) {
        notes_screen(v);
    } else if (v->screen == HF_SCREEN_TASK) {
        task_screen(v, tick);
    } else {
        header(v->heading);
        y = state_block(v, HEADER_H + 8, tick, 3);
        if (v->state[0] || v->detail[0] || v->busy) y += 8;
        y = table(v, y);
        if (v->row_count) y += 8;
        if (v->screen == HF_SCREEN_HOME && v->notes_title[0] && lines_left(y, line_h(S_BODY)) >= 2) {
            C2D_DrawRectSolid(MARGIN, y - 4, Z, TOP_W - 2 * MARGIN, 1, rgb(HF_RGB_BORDER));
            draw_line(v->notes_title, MARGIN, y, TOP_W - 2 * MARGIN, S_BODY, rgb(HF_RGB_GOLD), LEFT);
            notes(v->notes, 0, y + line_h(S_BODY), S_SMALL, TOP_W - 2 * MARGIN);
        }
    }
    if (v->message.on) message(v, tick);
}

/* ---- the bottom screen ---- */

static void button(const HfView *v, int i, const HfBox *b) {
    const HfViewButton *bt = &v->buttons[i];
    int sel = i == v->selected && bt->enabled, n;
    float scale = bt->primary ? S_PRIMARY : S_BUTTON, lh = line_h(scale);
    u32 fill, text, edge;
    if (bt->primary) {
        fill = rgb(!bt->enabled ? HF_RGB_DISABLED : sel ? HF_RGB_GOLD_HOVER : HF_RGB_GOLD);
        text = rgb(bt->enabled ? HF_RGB_BG : HF_RGB_MUTED);
        edge = sel ? rgb(HF_RGB_TEXT) : fill;
    } else {
        fill = rgb(sel ? HF_RGB_CARD_HOVER : HF_RGB_CARD);
        text = rgb(bt->enabled ? HF_RGB_TEXT : HF_RGB_DISABLED);
        edge = rgb(sel ? HF_RGB_GOLD : HF_RGB_BORDER);
    }
    framed(b->x, b->y, b->w, b->h, sel ? 2 : 1, edge, fill);
    n = para(bt->label, 0, 0, b->w - 12, scale, 0, 2, CENTRE, 0);
    para(bt->label, b->x + 6, b->y + (b->h - n * lh) / 2, b->w - 12, scale, text, 2, CENTRE, 1);
}

static void draw_bottom(const HfView *v) {
    HfBox boxes[HF_VIEW_BUTTONS];
    int n = hf_button_boxes(v, boxes), i;
    if (v->screen == HF_SCREEN_TASK && v->task.cancel[0])
        para(v->task.cancel, 16, 20, BOTTOM_W - 32, S_STATE, rgb(HF_RGB_TEXT), 4, CENTRE, 1);
    for (i = 0; i < n; i++) button(v, i, &boxes[i]);
    if (v->screen == HF_SCREEN_TASK) {   /* the install page's hint big and whole: three lines alone, two under buttons */
        float scale = n ? S_BODY : S_STATE, lh = line_h(scale);
        int max = n ? 2 : 3, lines = para(v->footer, 0, 0, BOTTOM_W - 32, scale, 0, max, CENTRE, 0);
        para(v->footer, 16, SCREEN_H - lines * lh - 6, BOTTOM_W - 32, scale, rgb(HF_RGB_TEXT), max, CENTRE, 1);
    } else {   /* under the buttons: small, a second line when it is long */
        int lines = para(v->footer, 0, 0, BOTTOM_W - 16, S_SMALL, 0, 2, LEFT, 0);
        para(v->footer, 8, SCREEN_H - lines * line_h(S_SMALL) - 4, BOTTOM_W - 16, S_SMALL, rgb(HF_RGB_MUTED), 2, LEFT,
             1);
    }
}

void gpu_draw(const HfView *v, unsigned tick) {
    C3D_FrameBegin(C3D_FRAME_SYNCDRAW);
    C2D_TargetClear(top, rgb(HF_RGB_BG));
    C2D_SceneBegin(top);
    draw_top(v, tick);
    C2D_TargetClear(bot, rgb(HF_RGB_BG));
    C2D_SceneBegin(bot);
    draw_bottom(v);
    C3D_FrameEnd(0);
}

int gpu_touch(const HfView *v, int px, int py) {
    HfBox boxes[HF_VIEW_BUTTONS];
    hf_button_boxes(v, boxes);
    return hf_box_touch(v, boxes, px, py);
}
