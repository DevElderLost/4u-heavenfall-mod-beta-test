/* The launcher's screens as text and its buttons' places (uitext.h). */
#include "uitext.h"

#include <stdio.h>
#include <string.h>

#define LEFT 1                       /* the top screen's text: columns 1-48 */
#define WIDTH 48
#define LAST_ROW (HF_TEXT_ROWS - 1)
#define MAX_LINES 32
#define BUTTON_LEFT 1                /* a text button: columns 1-38, its label in 3-36 */
#define BUTTON_RIGHT 38
#define LABEL_WIDTH 34
#define BUTTONS_END 27               /* the last row a text button may take: 28 is the badge's, 29 the footer's */
#define TASK_BUTTONS 7               /* on the task screen the buttons go under what B does (rows 2-5) */
#define BAR 40
#define LABEL_MAX 20                 /* a table's label column at most */
#define MESSAGE_WIDTH 45             /* a message's text: columns 2-46 inside its box's borders (0 and 48) */
#define MESSAGE_LINES 8

/* Code page 437's lines, check mark and bar cells. */
#define C_RULE 0xC4
#define C_CHECK 0xFB
#define C_FULL 0xDB
#define C_EMPTY 0xB0

typedef char Line[HF_TEXT_TOP_COLS + 1];

static const char SPIN[] = "|/-\\";

/* ---- text helpers (CP437 bytes) ---- */

/* `text` at `col` of a row `cols` wide, never in its last column. */
static void put(char *row, int cols, int col, const char *text) {
    for (; *text && col < cols - 1; col++, text++)
        if (col >= 0) row[col] = *text;
}

static void put_char(char *row, int cols, int col, int c) {
    if (col >= 0 && col < cols - 1) row[col] = (char)c;
}

/* "..." in place of the end of `line` so that it fits `width`, cut at a space when one is near. */
static void ellipsize(char *line, int width) {
    int keep = (int)strlen(line), i;
    if (width < 4) {
        if (keep > width) line[width] = 0;
        return;
    }
    if (keep + 3 > width) {
        keep = width - 3;
        if (line[keep] != ' ') {
            for (i = keep - 1; i > width / 2 && line[i] != ' '; i--) {}
            if (i > width / 2) keep = i;
        }
    }
    while (keep > 0 && line[keep - 1] == ' ') keep--;
    memcpy(line + keep, "...", 4);
}

/* `text` in `out` (room for width + 1), ending in "..." when it is longer than `width`. */
static void cut(const char *text, int width, char *out) {
    size_t n = strlen(text);
    if ((int)n <= width) {
        memcpy(out, text, n + 1);
        return;
    }
    memcpy(out, text, (size_t)width);
    out[width] = 0;
    ellipsize(out, width);
}

/* `text` in lines of at most `width` columns, at most `max` lines; the number of lines. Lines break at spaces (a word
 * longer than a line is cut); '\n' ends a paragraph, and an empty one is a blank line; a paragraph starting "- " goes
 * on indented by two. More text than fits ends the last line in "...". */
static int wrap(const char *text, int width, Line *lines, int max) {
    int n = 0;
    const char *p = text;
    if (!*p || max <= 0) return 0;
    if (max > MAX_LINES) max = MAX_LINES;
    for (;;) {
        const char *end = strchr(p, '\n'), *q = p, *stop;
        size_t len = end ? (size_t)(end - p) : strlen(p);
        int indent = len >= 2 && p[0] == '-' && p[1] == ' ' ? 2 : 0, first = 1;
        stop = p + len;
        if (q == stop) {
            if (n == max) { ellipsize(lines[n - 1], width); return n; }
            lines[n++][0] = 0;
        }
        while (q < stop) {
            int w = first ? width : width - indent, pre = first ? 0 : indent, take;
            const char *next;
            if (!first)
                while (q < stop && *q == ' ') q++;
            if (q >= stop) break;
            if (stop - q <= w) {
                take = (int)(stop - q);
                next = stop;
            } else {
                int i;
                for (i = w; i > 0 && q[i] != ' '; i--) {}
                take = i > 0 ? i : w;
                next = q + take;
            }
            while (take > 0 && q[take - 1] == ' ') take--;
            if (n == max) { ellipsize(lines[n - 1], width); return n; }
            memset(lines[n], ' ', (size_t)pre);
            memcpy(lines[n] + pre, q, (size_t)take);
            lines[n][pre + take] = 0;
            n++;
            q = next;
            first = 0;
        }
        if (!end || !end[1]) break;
        p = end + 1;
    }
    return n;
}

/* ---- the top screen ---- */

static void top_put(HfTextScreens *s, int row, int col, const char *text, int style) {
    if (row < 0 || row > LAST_ROW) return;
    put(s->top[row], HF_TEXT_TOP_COLS, col, text);
    s->top_style[row] = (unsigned char)style;
}

/* Wrapped UTF-8 text from row `y` at column `col`, at most `max` lines and never past the last row: the next row. */
static int top_text(HfTextScreens *s, int y, int col, int width, const char *utf8, int max, int style) {
    char text[HF_VIEW_NOTES];
    Line lines[MAX_LINES];
    int n, i;
    if (max > LAST_ROW - y + 1) max = LAST_ROW - y + 1;
    hf_cp437(utf8, text, sizeof text);
    n = wrap(text, width, lines, max);
    for (i = 0; i < n; i++) top_put(s, y + i, col, lines[i], style);
    return y + n;
}

static void heading(HfTextScreens *s, const char *utf8) {
    char text[HF_VIEW_LINE], line[WIDTH + 1];
    int i;
    hf_cp437(utf8, text, sizeof text);
    cut(text, WIDTH, line);
    top_put(s, 0, LEFT, line, HF_STYLE_GOLD);
    for (i = 0; i < WIDTH; i++) s->top[1][LEFT + i] = (char)C_RULE;
    s->top_style[1] = HF_TONE_MUTED;
}

/* The state line (the spinner before it while something runs) and what to do under it. The next row. */
static int state_lines(HfTextScreens *s, const HfView *v, int y, unsigned tick, int detail_max) {
    int indent = v->busy ? 2 : 0, next = y;
    if (v->state[0]) next = top_text(s, y, LEFT + indent, WIDTH - indent, v->state, 2, v->tone);
    if (v->busy && y <= LAST_ROW) {
        put_char(s->top[y], HF_TEXT_TOP_COLS, LEFT, SPIN[tick & 3]);
        s->top_style[y] = (unsigned char)v->tone;
        if (next == y) next = y + 1;
    }
    if (v->detail[0]) next = top_text(s, next, LEFT, WIDTH, v->detail, detail_max, HF_TONE_MUTED);
    return next;
}

/* The rows: a '\t' splits a label from its value (a table, the values in one column), any other row is wrapped. */
static int table(HfTextScreens *s, const HfView *v, int y) {
    char label[HF_VIEW_LINE], value[HF_VIEW_LINE], part[HF_VIEW_LINE], line[WIDTH + 1];
    int lw = 0, i;
    for (i = 0; i < v->row_count && i < HF_VIEW_ROWS; i++) {
        const char *tab = strchr(v->rows[i], '\t');
        if (tab) {
            size_t k = (size_t)(tab - v->rows[i]);
            int n;
            memcpy(part, v->rows[i], k);
            part[k] = 0;
            n = (int)hf_cp437(part, label, sizeof label);
            if (n > lw) lw = n;
        }
    }
    if (lw > LABEL_MAX) lw = LABEL_MAX;
    for (i = 0; i < v->row_count && i < HF_VIEW_ROWS && y <= LAST_ROW; i++) {
        const char *row = v->rows[i], *tab = strchr(row, '\t');
        if (tab) {
            size_t k = (size_t)(tab - row);
            memcpy(part, row, k);
            part[k] = 0;
            hf_cp437(part, label, sizeof label);
            cut(label, lw, line);
            top_put(s, y, LEFT, line, HF_TONE_PLAIN);
            hf_cp437(tab + 1, value, sizeof value);
            cut(value, WIDTH - lw - 2, line);
            top_put(s, y, LEFT + lw + 2, line, HF_TONE_PLAIN);
            y++;
        } else if (!row[0]) {
            y++;
        } else {
            y = top_text(s, y, LEFT, WIDTH, row, MAX_LINES, HF_TONE_PLAIN);
        }
    }
    return v->row_count ? y + 1 : y;
}

/* The notes from their line `scroll` on, to the screen's end. */
static void notes(HfTextScreens *s, const char *utf8, int scroll, int y) {
    while (scroll-- > 0 && utf8) {
        utf8 = strchr(utf8, '\n');
        if (utf8) utf8++;
    }
    if (utf8 && *utf8) top_text(s, y, LEFT, WIDTH, utf8, MAX_LINES, HF_TONE_PLAIN);
}

static void task(HfTextScreens *s, const HfView *v, unsigned tick) {
    char line[HF_TEXT_TOP_COLS + 1], text[HF_VIEW_LINE];
    unsigned permille = v->task.permille > 1000 ? 1000 : v->task.permille;
    int y = 3, i, filled = (int)(permille * BAR / 1000);
    if (v->task.stage_names[0][0]) {
        for (i = 0; i < HF_STAGES; i++) {
            int done = i < v->task.stage, now = i == v->task.stage;
            if (!v->task.stage_names[i][0]) continue;
            hf_cp437(v->task.stage_names[i], text, sizeof text);
            cut(text, WIDTH - 2, line);
            top_put(s, y, LEFT + 2, line, done ? HF_TONE_GOOD : now ? HF_TONE_PLAIN : HF_TONE_MUTED);
            put_char(s->top[y], HF_TEXT_TOP_COLS, LEFT, done ? C_CHECK : now ? '>' : ' ');
            y++;
        }
        y++;
    }
    line[0] = '[';
    for (i = 0; i < BAR; i++) line[1 + i] = (char)(i < filled ? C_FULL : C_EMPTY);
    snprintf(line + 1 + BAR, sizeof line - 1 - BAR, "] %3u%%", permille / 10);
    top_put(s, y++, LEFT, line, HF_STYLE_GOLD);
    if (v->task.eta[0]) {
        hf_cp437(v->task.eta, text, sizeof text);
        cut(text, WIDTH, line);
        top_put(s, y++, LEFT, line, HF_TONE_PLAIN);
    }
    y = state_lines(s, v, y + 1, tick, 2);
    if (v->task.note[0]) top_text(s, y + 1, LEFT, WIDTH, v->task.note, 3, HF_TONE_WARN);
}

/* A message's box over the top screen's last rows: its text, a blank row and the keys that answer it. */
/* A box over the top screen's last rows: its text, then its keys, or the spinner while a step runs. */
static void message(HfTextScreens *s, const HfView *v, unsigned tick) {
    char text[HF_VIEW_LINE * 2];
    Line lines[MESSAGE_LINES];
    char keys[HF_VIEW_LABEL], line[MESSAGE_WIDTH + 1];
    int n, h, top, r, c, style = v->message.tone, spin = !v->message.keys[0] && v->busy;
    hf_cp437(v->message.text, text, sizeof text);
    n = wrap(text, MESSAGE_WIDTH, lines, MESSAGE_LINES);
    h = 2 + n + (v->message.keys[0] || spin ? 2 : 0);
    top = LAST_ROW - h + 1;
    for (r = top; r <= LAST_ROW; r++) {
        int edge = r == top || r == LAST_ROW;
        memset(s->top[r], ' ', HF_TEXT_TOP_COLS);
        for (c = 1; c < WIDTH; c++) s->top[r][c] = (char)(edge ? 0xCD : ' ');
        s->top[r][0] = (char)(r == top ? 0xC9 : r == LAST_ROW ? 0xC8 : 0xBA);
        s->top[r][WIDTH] = (char)(r == top ? 0xBB : r == LAST_ROW ? 0xBC : 0xBA);
        s->top_style[r] = (unsigned char)style;
    }
    for (r = 0; r < n; r++) top_put(s, top + 1 + r, 2, lines[r], style);
    if (v->message.keys[0]) {
        hf_cp437(v->message.keys, keys, sizeof keys);
        cut(keys, MESSAGE_WIDTH, line);
        top_put(s, LAST_ROW - 1, 2, line, HF_STYLE_GOLD);
    } else if (spin) {
        char mark[2] = {SPIN[tick & 3], 0};
        top_put(s, LAST_ROW - 1, 2, mark, HF_STYLE_GOLD);
    }
}

/* ---- the bottom screen ---- */

static void bottom_put(HfTextScreens *s, int row, int col, const char *text, int style) {
    if (row < 0 || row > LAST_ROW) return;
    put(s->bottom[row], HF_TEXT_BOTTOM_COLS, col, text);
    s->bottom_style[row] = (unsigned char)style;
}

/* Button `i` from row `y`, `h` rows high: a double frame for the big one. */
static void button(HfTextScreens *s, const HfView *v, int i, int y, int h) {
    const HfViewButton *b = &v->buttons[i];
    int dbl = b->primary, r, c, style, mid = y + h / 2;
    char text[HF_VIEW_LABEL], label[LABEL_WIDTH + 1];
    style = !b->enabled ? HF_TONE_MUTED : b->primary ? HF_STYLE_GOLD : i == v->selected ? HF_STYLE_SELECTED : HF_TONE_PLAIN;
    for (r = 0; r < h; r++) {
        char *row = s->bottom[y + r];
        int edge = r == 0 || r == h - 1;
        for (c = BUTTON_LEFT + 1; c < BUTTON_RIGHT && edge; c++) row[c] = (char)(dbl ? 0xCD : 0xC4);
        row[BUTTON_LEFT] = (char)(r == 0 ? (dbl ? 0xC9 : 0xDA) : r == h - 1 ? (dbl ? 0xC8 : 0xC0) : (dbl ? 0xBA : 0xB3));
        row[BUTTON_RIGHT] = (char)(r == 0 ? (dbl ? 0xBB : 0xBF) : r == h - 1 ? (dbl ? 0xBC : 0xD9) : (dbl ? 0xBA : 0xB3));
        s->bottom_style[y + r] = (unsigned char)style;
        s->bottom_button[y + r] = (signed char)i;
    }
    hf_cp437(b->label, text, sizeof text);
    cut(text, LABEL_WIDTH, label);
    put(s->bottom[mid], HF_TEXT_BOTTOM_COLS, BUTTON_LEFT + 2 + (LABEL_WIDTH - (int)strlen(label)) / 2, label);
    if (i == v->selected) {
        s->bottom[mid][BUTTON_LEFT + 1] = '>';
        s->bottom[mid][BUTTON_RIGHT - 1] = '<';
    }
}

static void bottom(HfTextScreens *s, const HfView *v, const char *badge) {
    char text[HF_VIEW_LINE];
    Line lines[4];
    char line[HF_TEXT_BOTTOM_COLS];
    int y = 1, i, n;
    if (v->screen == HF_SCREEN_TASK) {
        hf_cp437(v->task.cancel, text, sizeof text);
        n = wrap(text, BUTTON_RIGHT, lines, 4);
        for (i = 0; i < n; i++) bottom_put(s, 2 + i, 1, lines[i], HF_TONE_PLAIN);
        y = TASK_BUTTONS;
    }
    for (i = 0; i < v->button_count && i < HF_VIEW_BUTTONS; i++) {
        int h = v->buttons[i].primary ? 5 : 3;
        if (y + h - 1 > BUTTONS_END) break;
        button(s, v, i, y, h);
        y += h + 1;
    }
    if (badge && badge[0]) {
        hf_cp437(badge, text, sizeof text);
        cut(text, BUTTON_RIGHT, line);
        bottom_put(s, LAST_ROW - 1, BUTTON_RIGHT + 1 - (int)strlen(line), line, HF_TONE_WARN);
    }
    hf_cp437(v->footer, text, sizeof text);
    cut(text, BUTTON_RIGHT, line);
    bottom_put(s, LAST_ROW, 1, line, HF_TONE_MUTED);
}

void hf_text_screens(const HfView *v, const char *badge, unsigned tick, HfTextScreens *s) {
    int r, y;
    for (r = 0; r < HF_TEXT_ROWS; r++) {
        memset(s->top[r], ' ', HF_TEXT_TOP_COLS);
        s->top[r][HF_TEXT_TOP_COLS] = 0;
        memset(s->bottom[r], ' ', HF_TEXT_BOTTOM_COLS);
        s->bottom[r][HF_TEXT_BOTTOM_COLS] = 0;
        s->top_style[r] = s->bottom_style[r] = HF_TONE_PLAIN;
        s->bottom_button[r] = -1;
    }
    if (v->screen == HF_SCREEN_NOTES) {
        heading(s, v->notes_title[0] ? v->notes_title : v->heading);
        notes(s, v->notes, v->notes_scroll, 3);
    } else if (v->screen == HF_SCREEN_TASK) {
        heading(s, v->heading);
        task(s, v, tick);
    } else {
        heading(s, v->heading);
        y = state_lines(s, v, 3, tick, 3);
        if (v->state[0] || v->detail[0] || v->busy) y++;
        y = table(s, v, y);
        if (v->screen == HF_SCREEN_HOME && v->notes_title[0] && y <= LAST_ROW) {
            char text[HF_VIEW_LABEL], line[WIDTH + 1];
            hf_cp437(v->notes_title, text, sizeof text);
            cut(text, WIDTH, line);
            top_put(s, y, LEFT, line, HF_STYLE_GOLD);
            notes(s, v->notes, 0, y + 1);
        }
    }
    if (v->message.on) message(s, v, tick);
    bottom(s, v, badge);
}

int hf_text_touch(const HfTextScreens *s, const HfView *v, int px, int py) {
    int row = py / 8, col = px / 8, i;
    if (px < 0 || py < 0 || row > LAST_ROW || col < BUTTON_LEFT || col > BUTTON_RIGHT) return -1;
    i = s->bottom_button[row];
    if (i < 0 || i >= v->button_count || !v->buttons[i].enabled) return -1;
    return v->buttons[i].id;
}

/* ---- the graphic layout's buttons ---- */

#define BOX_X 10
#define BOX_W 300
#define BOX_GAP 6
#define BOX_HALF ((BOX_W - BOX_GAP) / 2)
#define BOX_PRIMARY 56
#define BOX_PLAIN 44
#define BOXES_TOP 8
#define BOXES_TASK 104       /* under the task screen's cancel text */
#define BOXES_END 214        /* the footer's line under it */

typedef struct {
    HfBox *boxes;
    int y, count;
} Placing;

/* Button i across the screen at the next place: 0 when it does not fit. */
static int place_full(Placing *p, const HfView *v, int i) {
    int h = v->buttons[i].primary ? BOX_PRIMARY : BOX_PLAIN;
    if (p->y + h > BOXES_END) return 0;
    p->boxes[i].x = BOX_X;
    p->boxes[i].y = p->y;
    p->boxes[i].w = BOX_W;
    p->boxes[i].h = h;
    p->y += h + BOX_GAP;
    p->count++;
    return 1;
}

int hf_button_boxes(const HfView *v, HfBox boxes[HF_VIEW_BUTTONS]) {
    int n = v->button_count < 0 ? 0 : v->button_count > HF_VIEW_BUTTONS ? HF_VIEW_BUTTONS : v->button_count;
    int top = v->screen == HF_SCREEN_TASK ? BOXES_TASK : BOXES_TOP, total = 0, pending = -1, i;
    Placing p;
    memset(boxes, 0, sizeof(HfBox) * HF_VIEW_BUTTONS);
    p.boxes = boxes;
    p.y = top;
    p.count = 0;
    for (i = 0; i < n; i++) total += (v->buttons[i].primary ? BOX_PRIMARY : BOX_PLAIN) + (i ? BOX_GAP : 0);
    if (total <= BOXES_END - top) {
        for (i = 0; i < n; i++) place_full(&p, v, i);
        return p.count;
    }
    for (i = 0; i < n; i++) {
        if (v->buttons[i].primary) {
            if (pending >= 0 && !place_full(&p, v, pending)) return p.count;
            pending = -1;
            if (!place_full(&p, v, i)) return p.count;
        } else if (pending < 0) {
            pending = i;
        } else {
            if (p.y + BOX_PLAIN > BOXES_END) return p.count;
            boxes[pending].x = BOX_X;
            boxes[i].x = BOX_X + BOX_HALF + BOX_GAP;
            boxes[pending].y = boxes[i].y = p.y;
            boxes[pending].w = boxes[i].w = BOX_HALF;
            boxes[pending].h = boxes[i].h = BOX_PLAIN;
            p.y += BOX_PLAIN + BOX_GAP;
            p.count += 2;
            pending = -1;
        }
    }
    if (pending >= 0) place_full(&p, v, pending);
    return p.count;
}

int hf_button_step(const HfView *v, int from, int dx, int dy) {
    HfBox b[HF_VIEW_BUTTONS];
    int n = hf_button_boxes(v, b), i, best = -1;
    long best_score = 0, cx, cy;
    if (n <= 0) return from;
    if (from < 0 || from >= n || !b[from].h) {   /* nothing chosen yet: the first enabled one (the last going up) */
        for (i = 0; i < n; i++) {
            int k = dy < 0 ? n - 1 - i : i;
            if (b[k].h && v->buttons[k].enabled) return k;
        }
        return from;
    }
    cx = b[from].x + b[from].w / 2;
    cy = b[from].y + b[from].h / 2;
    for (i = 0; i < n; i++) {
        long ix, iy, along, across, score;
        if (i == from || !b[i].h || !v->buttons[i].enabled) continue;
        ix = b[i].x + b[i].w / 2;
        iy = b[i].y + b[i].h / 2;
        along = dx ? (ix - cx) * dx : (iy - cy) * dy;
        across = dx ? iy - cy : ix - cx;
        if (across < 0) across = -across;
        if (along <= 0 || (dx && across >= b[from].h)) continue;   /* left and right stay in the row */
        score = along + 2 * across;
        if (best < 0 || score < best_score) {
            best = i;
            best_score = score;
        }
    }
    if (best >= 0 || !dy) return best >= 0 ? best : from;
    for (i = 0; i < n; i++) {   /* past the end going up or down: round to the other end, the same column first */
        long ix, iy, across, score;
        if (i == from || !b[i].h || !v->buttons[i].enabled) continue;
        ix = b[i].x + b[i].w / 2;
        iy = b[i].y + b[i].h / 2;
        across = ix - cx < 0 ? cx - ix : ix - cx;
        score = (dy > 0 ? iy : -iy) * 4 + across;
        if (best < 0 || score < best_score) {
            best = i;
            best_score = score;
        }
    }
    return best >= 0 ? best : from;
}

int hf_box_touch(const HfView *v, const HfBox boxes[HF_VIEW_BUTTONS], int px, int py) {
    int i;
    for (i = 0; i < v->button_count && i < HF_VIEW_BUTTONS; i++) {
        const HfBox *b = &boxes[i];
        if (b->h && px >= b->x && px < b->x + b->w && py >= b->y && py < b->y + b->h)
            return v->buttons[i].enabled ? v->buttons[i].id : -1;
    }
    return -1;
}
