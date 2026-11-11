/* The Rare Materials Exchange at the Wyporium (option rare_exchange): a fifth line of the Wyporium's menu
(FUN_009b6d84, state byte at obj + 0xAA64) and its two
 * screens, which run in the Wyporium's state 12 (the game uses 0-11). Both are the game's own trade list (ui407 rows,
 * the materials box ui402_hituyo01), drawn by the game's code from the trade fields of the state block:
 *
 *   screen 1  what you get: one list of the rare items of the ranks the player has reached (low, high, G), 8 to a page;
 *             a row is grey when the pouch and the box hold too few of its pool, or the box has no room; the box shows
 *             "Hand over N items of:", how many the player holds, and the owners; A opens screen 2, B goes back
 *   screen 2  what you hand over: the pool's items the player holds and how many are handed of each;
 *             left / right takes or adds one (held repeats), up / down moves over the pages, the title counts
 *             "Handed over N/X"; A with N = X asks the game's yes / no, yes pays and the item box shows where it went;
 *             B goes back to screen 1
 *
 * The game's functions that draw the trade list read the entries at state + 0x334 (item and flags of the page's rows)
 * and the row, page and page count beside them: this code writes them (the game's builder walks only its own table)
 * and calls the drawing, then writes the lines of the materials box and the numbers of screen 2 itself.
 *
 * Hooks (ARM, below; gameplay/wyporium/rare_exchange.py points the game at them):
 *   exchange_state    0x9B6DE8  "b 0x9B7A38": the state switch's default case; state 12 runs exchange_update
 *   exchange_bright   0x9B6FDC  "bic r9, r9, #8": the bright lines; in the three-line menu ours (line 3) stays bright
 *   exchange_menu_a   0x9B6FEC  "bl 0x9EB38C": the menu's cursor and A; A on our line sets state 12
 *   exchange_help     0x9B7014  "cmp r0, #0": the help of the highlighted line; ours has its own
 *   exchange_leave    0x9B7A7C  "b 0x9B7B80": the old state's cases; leaving state 12 hides the trade list's groups
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define GAME __attribute__((long_call))
#define ARM __attribute__((target("arm"), noinline))
#define STR2(x) #x
#define STR(x) STR2(x)

GAME void facility_menu_set(u32 obj, u32 menu, u32 row, u32 bright);   /* FUN_00a1ea8c */
GAME void facility_help(u32 kind, u32 file, u32 message);               /* FUN_00298560 */
GAME void sound_play(u32 manager, u32 sound);                           /* FUN_0031294c */
GAME void text_slot(u32 slot, const u16 *text, u32 length);             /* FUN_005a99a8: a number node's text */
GAME void text_lobby(void *ref, u32 file, u32 message);                 /* FUN_005a882c */
GAME void text_show(u32 pane, u32 visible);                             /* FUN_00ae7618 */
GAME void pane_redraw(u32 ref_a, u32 node);                             /* FUN_00ae6bcc */
GAME void gui_group_show(u32 group, u32 shown);                         /* FUN_00ae53e0 */
GAME void trade_text_colour(void *ref, const u32 *rgba);                      /* FUN_00ae0f24 */
GAME void trade_icon_hide(void *ref, u32 shown);                            /* FUN_00d942d4 */
GAME void trade_draw(u32 obj, u32 what);                                /* FUN_009e2b20: 9 groups, 10 rows, 0xB panel */
GAME void trade_hide(u32 obj, u32 which);                               /* FUN_00a8c1fc: 0 hides every list group */
GAME void trade_row_number(u32 obj, u32 row, int value, u32 kind, u32 money); /* FUN_00a72a80 */
GAME u32 facility_pressed(u32 obj, u32 bits);                           /* FUN_009ac3a4 */
GAME u32 facility_dirs(u32 obj);                                        /* FUN_009b3830: pressed or repeating */
GAME u32 wyporium_menu_a(u32 obj, void *cursor, u32 zero);              /* FUN_009eb38c: 1 on A on a bright line */
GAME void window_open(u32 kind, u32 slot, u32 type, u32 first);         /* FUN_002921cc: type 4 is yes / no */
GAME void window_update(void);                                          /* FUN_002a2414 */
GAME void window_close(u32 kind, u32 slot);                             /* FUN_0029e5bc */
GAME u32 window_input(u32 obj);                                         /* FUN_00aa6480 */
GAME u32 window_answer(u32 obj, u32 at, u32 input, u32 mask);           /* FUN_00a66e60: 1 yes, 2 no */
GAME u32 item_room(u32 unused, u32 item, u32 place);                    /* FUN_00a02c60: room left; place 1 the box */
GAME u32 item_give(u32 save, u32 item, u32 quantity, u32 where);        /* FUN_00c1ea50: into the box */
GAME void item_take(u32 obj, u32 item, u32 quantity);                   /* FUN_00aab06c: the box first, then the pouch */
GAME u32 item_count(u32 save, u32 item);                                /* FUN_00c21b18: the pouch and the box */
GAME void trade_buttons(u32 obj, u32 layout, u32 flags);                /* FUN_00a51a24: the bottom buttons */
GAME void item_box_close(u32 obj);                                      /* FUN_00a981c4: the item box viewer */

#include "rank_unlock.h"

extern u32 sound_control;
#define NO_MENU 0xFF             /* facility_menu_set: FUN_00a0a708 hides ui401's own groups */

#define SHOP 4                   /* D_shop among the lobby's message files */
#define MAKESHOP 6               /* E_makeshop: its message 0x12 is "<number>/<number>" */
#define MESSAGE_PAIR 0x12
#define EXCHANGE_STATE 12        /* the Wyporium's state the screens run in */
#define LINE_COUNT 0x16          /* the Wyporium's state: the menu's lines, */
#define LINE_AT 0xC              /* the highlighted line */
#define OBJ_GIVE 0xA3D4          /* the lobby object: what FUN_00c1ea50 is told, as the game's trades do */
#define SOUND_GIVEN 0x1F         /* the trades' sound */
#define ANSWER_ANY 0xFFFF
#define BUTTON_A 0x10
#define BUTTON_B 0x20
#define DIR_UP 1
#define DIR_DOWN 2
#define DIR_LEFT 4
#define DIR_RIGHT 8
#define SOUND_DECIDE 1
#define SOUND_CANCEL 2
#define SOUND_ERROR 3
#define SOUND_CURSOR 4
#define SOUND_PAGE 7
#define ITEM_HELD_MAX 999

/* The trade list's fields in the Wyporium's state block (state = obj + 0xAA64) */
#define S_ROW 0x6A               /* u16: the cursor's row on the page */
#define S_PAGE 0x6E              /* u16 */
#define S_PAGES 0x70             /* u16 */
#define S_COUNT 0x80             /* u16: the rows of the page */
#define S_ENTRIES 0x334          /* 8 of {u32 row pointer (0: no materials), u16 item, u16 flags} */
#define FLAG_BOX_FULL 2          /* an entry's flags: any greys the row; these two are the game's */
#define FLAG_SHORT 8
#define PAGE_ROWS 8
#define HELP_LIST 0x42           /* D_shop: the trade list's help, and when a payment is short or the box is full */
#define HELP_BOX_FULL 0x43
#define HELP_SHORT 0x44
#define HELP_SENT 0x46           /* D_shop: "Sent to Item Box." */
#define BUTTONS_LIST 2           /* the bottom buttons: the list's (Accept / Back), the confirm's (Yes / No), */
#define BUTTONS_DONE 9           /* the done step's */
#define BUTTON_FLAGS 4

/* The lobby object's panes the trade list uses */
#define O_TITLE 0x9AE0           /* ui407 m_title00 */
#define O_BOX_GROUP 0xA024       /* ui402 item11, 12, 13: the box's lines, a group each (+4 each) */
#define O_BOX_NAME 0xA090        /* m_11_00, 12, 13 (+0x10 each) and their numbers one ref after */
#define O_BOX_ICON 0xA100        /* item_s11, 12, 13 (+0x10 each) */
#define O_BOX_FRAME 0xA108       /* each line's number frame, box03 (+0x10 each) */
#define BOX_LINES 3
#define BOX_GROUP_STEP 4
#define BOX_NAME_STEP 0x10
#define BOX_NUMBER 8
#define BOX_ICON_STEP 0x10

struct ref { u32 group; u8 *node; };   /* a pane of a group: node + 8 its data, + 0x14 its next sibling */
#define NODE_DATA 8
#define NODE_DIRTY 0xC
#define DIRTY_MARK 0x12
#define NODE_NEXT 0x14

#define POOL_MAX 24
#define XM_COUNT 6
#define X_MAGIC 0x47484358
enum { XM_NAME, XM_MENU_HELP, XM_HAND_OVER, XM_HANDED, XM_HELP_POOL, XM_PROMPT };   /* exchange_texts.py */
enum { X_LIST, X_POOL, X_PROMPT, X_DONE };

struct xhead {                   /* gameplay/wyporium/exchange_data.py, HEADER */
    u32 magic;
    u16 rows, pools;
    u16 messages[XM_COUNT];
    u16 unlock[RANKS - 1][UNLOCK_ROOM];
    u32 rows_at, pools_at;
};
/* owners: the first of two D_shop messages; units: the items the row asks (a scrap's count is not the rank's) */
struct xrow { u16 item; u8 rank, pool_count; u16 pool_at, owners; u8 units, pad; };
_Static_assert(sizeof(struct xrow) == 10, "exchange_data.py ROW");
_Static_assert(sizeof(struct xhead) == 44, "exchange_data.py HEADER");
extern const u8 rare_exchange_data[];
#define XD ((const struct xhead *)rare_exchange_data)

#define SLOTS 2                  /* the string slots a message with numbers fills: 0 and 1 */
struct xui {                     /* the variable exchange_ui */
    u8 open, sub, unlocked, shown_count;
    u16 index, total;            /* screen 1: the cursor among the listed rows, how many are listed */
    u16 row;                     /* the row being paid, among all the rows */
    u16 pool_index, pool_total;  /* screen 2: the cursor among the items held, how many */
    u16 handed, pad;
    u32 answer;                  /* the yes / no window's answer */
    u8 give[POOL_MAX];           /* handed over, by position in the pool */
    u8 shown[PAGE_ROWS];         /* the positions in the pool of screen 2's page */
    u16 digits[SLOTS][4];        /* the numbers of the string slots: a slot keeps the address, read by the next message */
};
_Static_assert(sizeof(struct xui) == 72, "exchange_ui size (game/executable/blocks.py)");
extern struct xui exchange_ui;
#define X (&exchange_ui)

static const u32 GREY = 0xFF646464, WHITE = 0xFFF0F0F0;   /* the box's lines, as the game colours them */

static inline void play(u32 sound)
{
    sound_play(sound_control, sound);
}

/* ----- the data ------------------------------------------------------------------------------------------- */

static const struct xrow *row_at(u32 i)
{
    return (const struct xrow *)(rare_exchange_data + XD->rows_at) + i;
}

static const u16 *pool_of(const struct xrow *r)
{
    return (const u16 *)(rare_exchange_data + XD->pools_at) + r->pool_at;
}

static u32 held(u32 item)
{
    u32 n = item_count(save_control, item);
    return n > ITEM_HELD_MAX ? ITEM_HELD_MAX : n;
}

static u32 held_total(const struct xrow *r)
{
    const u16 *pool = pool_of(r);
    u32 total = 0;
    for (u32 i = 0; i < r->pool_count; i++)
        total += held(pool[i]);
    return total;
}

static u32 units_of(const struct xrow *r)
{
    return r->units;
}

static u32 unlocked_rank(void)
{
    return rank_unlocked(XD->unlock);
}

/* How many rows the ranks reached list; those from `first` on, `room` of them, go to `out` (indexes of the rows). */
static u32 scan_rows(u32 first, u16 *out, u32 room)
{
    u32 found = 0;
    for (u32 i = 0; i < XD->rows; i++) {
        if (row_at(i)->rank > X->unlocked)
            continue;
        if (found >= first && found - first < room)
            out[found - first] = i;
        found++;
    }
    return found;
}

/* The pool's entries the player holds: how many; from `first` on, `room` of them, go to `out` (positions). */
static u32 scan_pool(u32 first, u16 *out, u32 room)
{
    const struct xrow *r = row_at(X->row);
    const u16 *pool = pool_of(r);
    u32 found = 0;
    for (u32 i = 0; i < r->pool_count; i++) {
        if (!held(pool[i]))
            continue;
        if (found >= first && found - first < room)
            out[found - first] = i;
        found++;
    }
    return found;
}

static u32 pages_of(u32 total)
{
    u32 pages = (total + PAGE_ROWS - 1) / PAGE_ROWS;
    return pages ? pages : 1;
}

/* ----- the game's panes ----------------------------------------------------------------------------------- */

static void ref_changed(const struct ref *r)
{
    u8 *holder = *(u8 **)(r->node + NODE_NEXT), *dirty = *(u8 **)(holder + NODE_DIRTY);
    if (dirty)
        dirty[DIRTY_MARK] = 3;
    else
        pane_redraw(r->group, (u32)holder);
}

/* A message of a text pane the game holds (obj + `at`), shown. */
static void say(u32 obj, u32 at, u32 file, u32 message)
{
    struct ref *r = (struct ref *)(obj + at);
    text_lobby(r, file, message);
    text_show(*(u32 *)(r->node + NODE_DATA), 1);
    ref_changed(r);
}

static void text_hide(u32 obj, u32 at)
{
    struct ref *r = (struct ref *)(obj + at);
    text_show(*(u32 *)(r->node + NODE_DATA), 0);
    ref_changed(r);
}

static void colour(u32 obj, u32 at, int grey)
{
    trade_text_colour((void *)(obj + at), grey ? &GREY : &WHITE);
}

/* `value` in decimal into string slot `slot`, which the next message with a number shows: 999 at most, as the game
   shows held counts (a whole pool's held total can pass it; the slot holds three digits). */
static void slot_number(u32 slot, u32 value)
{
    static const u32 tens[] = {100, 10, 1};
    if (value > 999)
        value = 999;
    u16 *out = X->digits[slot];
    u32 length = 0;
    for (u32 i = 0; i < sizeof tens / sizeof tens[0]; i++) {
        u32 digit = 0;
        while (value >= tens[i]) {
            value -= tens[i];
            digit++;
        }
        if (digit || length || tens[i] == 1)
            out[length++] = '0' + digit;
    }
    out[length] = 0;
    text_slot(slot, out, length);
}

/* ----- drawing -------------------------------------------------------------------------------------------- */

static u8 *entry_at(u8 *state, u32 n)
{
    return state + S_ENTRIES + 8 * n;
}

static void page_start(u8 *state)
{
    for (u32 i = 0; i < PAGE_ROWS * 2; i++)
        ((u32 *)(state + S_ENTRIES))[i] = 0;
}

static void page_entry(u8 *state, u32 n, u32 item, u32 flags)
{
    u8 *e = entry_at(state, n);
    *(u16 *)(e + 4) = item;
    *(u16 *)(e + 6) = flags;
}

static void page_end(u8 *state, u32 index, u32 total, u32 count)
{
    *(u16 *)(state + S_COUNT) = count;
    *(u16 *)(state + S_ROW) = index % PAGE_ROWS;
    *(u16 *)(state + S_PAGE) = index / PAGE_ROWS;
    *(u16 *)(state + S_PAGES) = pages_of(total);
}

/* Screen 1's page of the cursor into the trade fields: the rows' items, grey when short of materials or room. */
static void page_rows(u8 *state)
{
    u16 shown[PAGE_ROWS];
    for (u32 i = 0; i < PAGE_ROWS; i++)
        shown[i] = 0;
    u32 first = X->index / PAGE_ROWS * PAGE_ROWS, total = scan_rows(first, shown, PAGE_ROWS);
    u32 count = total > first ? total - first : 0;
    if (count > PAGE_ROWS)
        count = PAGE_ROWS;
    X->total = total;
    page_start(state);
    for (u32 n = 0; n < count; n++) {
        const struct xrow *r = row_at(shown[n]);
        u32 flags = (held_total(r) < units_of(r) ? FLAG_SHORT : 0) | (item_room(0, r->item, 1) < 1 ? FLAG_BOX_FULL : 0);
        page_entry(state, n, r->item, flags);
    }
    page_end(state, X->index, total, count);
}

/* Screen 2's page of the cursor: the items of the pool the player holds. */
static void page_pool(u8 *state)
{
    u16 shown[PAGE_ROWS];
    for (u32 i = 0; i < PAGE_ROWS; i++)
        shown[i] = 0;
    u32 first = X->pool_index / PAGE_ROWS * PAGE_ROWS, total = scan_pool(first, shown, PAGE_ROWS);
    u32 count = total > first ? total - first : 0;
    if (count > PAGE_ROWS)
        count = PAGE_ROWS;
    X->pool_total = total;
    X->shown_count = count;
    page_start(state);
    for (u32 n = 0; n < count; n++) {
        X->shown[n] = shown[n];
        page_entry(state, n, pool_of(row_at(X->row))[shown[n]], 0);
    }
    page_end(state, X->pool_index, total, count);
}

/* The materials box: "Hand over N items of:" with `count`/N, and the owners on two more lines. The game's drawing of
   the panel leaves its lines hidden (no row pointer), so this goes after every draw of it. */
static void box_number(u32 obj, const struct xrow *r, u32 count)
{
    slot_number(0, count);
    slot_number(1, units_of(r));
    colour(obj, O_BOX_NAME + BOX_NUMBER, count < units_of(r));
    say(obj, O_BOX_NAME + BOX_NUMBER, MAKESHOP, MESSAGE_PAIR);
}

static void box_lines(u32 obj, const struct xrow *r, u32 count)
{
    for (u32 line = 0; line < BOX_LINES; line++) {
        u32 name = O_BOX_NAME + line * BOX_NAME_STEP;
        gui_group_show(*(u32 *)(obj + O_BOX_GROUP + line * BOX_GROUP_STEP), 1);
        trade_icon_hide((void *)(obj + O_BOX_ICON + line * BOX_ICON_STEP), 0);
        if (line) {
            say(obj, name, SHOP, r->owners + line - 1);
            colour(obj, name, 0);
            text_hide(obj, name + BOX_NUMBER);
            /* the frame behind the line's number (box03), shown by FUN_00aa0a54 for a line with an item */
            trade_icon_hide((void *)(obj + O_BOX_FRAME + line * BOX_ICON_STEP), 0);
        }
    }
    slot_number(0, units_of(r));
    colour(obj, O_BOX_NAME, count < units_of(r));
    say(obj, O_BOX_NAME, SHOP, XD->messages[XM_HAND_OVER]);
    box_number(obj, r, count);
}

/* The rare item of screen 1's cursor. */
static const struct xrow *cursor_row(void)
{
    u16 shown = 0;
    scan_rows(X->index, &shown, 1);
    return row_at(shown);
}

static void list_cursor(u32 obj, u8 *state)
{
    *(u16 *)(state + S_ROW) = X->index % PAGE_ROWS;
    trade_draw(obj, 0xB);
    const struct xrow *r = cursor_row();
    box_lines(obj, r, held_total(r));
}

static void list_draw(u32 obj, u8 *state, u32 whole)
{
    page_rows(state);
    if (whole) {
        trade_draw(obj, 9);
        say(obj, O_TITLE, SHOP, XD->messages[XM_NAME]);
    }
    trade_draw(obj, 10);
    list_cursor(obj, state);
}

/* Screen 2: the handed count in the game's number column of each row (the held counts are the left panel's). */
static void pool_row_numbers(u32 obj, u32 row)
{
    if (row < X->shown_count)
        trade_row_number(obj, row, X->give[X->shown[row]], 0, 1);
}

static void pool_title(u32 obj)
{
    slot_number(0, X->handed);
    slot_number(1, units_of(row_at(X->row)));
    say(obj, O_TITLE, SHOP, XD->messages[XM_HANDED]);
}

static void pool_cursor(u32 obj, u8 *state)
{
    *(u16 *)(state + S_ROW) = X->pool_index % PAGE_ROWS;
    trade_draw(obj, 0xB);
    box_lines(obj, row_at(X->row), X->handed);
}

static void pool_draw(u32 obj, u8 *state, u32 whole)
{
    page_pool(state);
    if (whole)
        trade_draw(obj, 9);
    trade_draw(obj, 10);
    for (u32 row = 0; row < PAGE_ROWS; row++)
        pool_row_numbers(obj, row);
    pool_title(obj);
    pool_cursor(obj, state);
}

static void redraw(u32 obj, u8 *state, u32 whole)
{
    if (X->sub == X_LIST)
        list_draw(obj, state, whole);
    else
        pool_draw(obj, state, whole);
}

/* The cursor goes to `index` of the screen's list: a new page is drawn whole, the same page moves the cursor. */
static void go_to(u32 obj, u8 *state, u32 index, u32 sound)
{
    u16 *at = X->sub == X_LIST ? &X->index : &X->pool_index;
    u32 page = *at / PAGE_ROWS;
    *at = index;
    play(sound);
    if (index / PAGE_ROWS != page)
        redraw(obj, state, 0);
    else if (X->sub == X_LIST)
        list_cursor(obj, state);
    else
        pool_cursor(obj, state);
}

/* ----- the keys ------------------------------------------------------------------------------------------- */

/* `value` a step on, round `count` values. */
static u32 wrap(u32 value, u32 count, int up)
{
    if (up)
        return value ? value - 1 : count - 1;
    return value + 1 < count ? value + 1 : 0;
}

static void pool_open(u32 obj, u8 *state)
{
    u32 flags = *(u16 *)(entry_at(state, X->index % PAGE_ROWS) + 6);
    if (flags) {
        play(SOUND_ERROR);
        return;
    }
    u16 shown = 0;
    scan_rows(X->index, &shown, 1);
    X->row = shown;
    X->handed = 0;
    X->pool_index = 0;
    for (u32 i = 0; i < POOL_MAX; i++)
        X->give[i] = 0;
    X->sub = X_POOL;
    play(SOUND_DECIDE);
    redraw(obj, state, 1);
}

static void list_keys(u32 obj, u8 *state)
{
    u32 dirs = facility_dirs(obj), first = X->index / PAGE_ROWS * PAGE_ROWS, row = X->index - first;
    u32 count = X->total - first < PAGE_ROWS ? X->total - first : PAGE_ROWS;
    if (facility_pressed(obj, BUTTON_B)) {
        play(SOUND_CANCEL);
        state[0] = 2;
    } else if (dirs & (DIR_UP | DIR_DOWN)) {
        if (count > 1)
            go_to(obj, state, first + wrap(row, count, dirs & DIR_UP), SOUND_CURSOR);
    } else if (dirs & (DIR_LEFT | DIR_RIGHT)) {
        u32 pages = pages_of(X->total), page = wrap(first / PAGE_ROWS, pages, dirs & DIR_LEFT);
        if (pages > 1) {
            u32 there = X->total - page * PAGE_ROWS < PAGE_ROWS ? X->total - page * PAGE_ROWS : PAGE_ROWS;
            go_to(obj, state, page * PAGE_ROWS + (row < there ? row : there - 1), SOUND_PAGE);
        }
    } else if (facility_pressed(obj, BUTTON_A)) {
        pool_open(obj, state);
    }
}

static void prompt_ask(void)
{
    window_open(3, 0, 4, 1);
    window_open(6, 1, 4, 0);
    X->answer = 0;
    play(SOUND_DECIDE);
    X->sub = X_PROMPT;
}

/* One more handed over (right) or one taken back (left) of the item under the cursor. */
static void pool_step(u32 obj, int more, u32 fresh)
{
    const struct xrow *r = row_at(X->row);
    u32 row = X->pool_index % PAGE_ROWS, at = X->shown[row];
    int possible = more ? X->give[at] < held(pool_of(r)[at]) && X->handed < units_of(r) : X->give[at] > 0;
    if (!possible) {
        if (fresh)
            play(SOUND_ERROR);
        return;
    }
    X->give[at] += more ? 1 : -1;
    X->handed += more ? 1 : -1;
    play(SOUND_CURSOR);
    pool_row_numbers(obj, row);
    pool_title(obj);
    box_number(obj, r, X->handed);
}

static void pool_keys(u32 obj, u8 *state)
{
    u32 dirs = facility_dirs(obj);
    if (facility_pressed(obj, BUTTON_B)) {
        play(SOUND_CANCEL);
        X->sub = X_LIST;
        redraw(obj, state, 1);
    } else if (dirs & (DIR_UP | DIR_DOWN)) {
        if (X->pool_total > 1)
            go_to(obj, state, wrap(X->pool_index, X->pool_total, dirs & DIR_UP), SOUND_CURSOR);
    } else if (dirs & (DIR_LEFT | DIR_RIGHT)) {
        pool_step(obj, dirs & DIR_RIGHT && !(dirs & DIR_LEFT), facility_pressed(obj, DIR_LEFT | DIR_RIGHT));
    } else if (facility_pressed(obj, BUTTON_A)) {
        if (X->handed == units_of(row_at(X->row)))
            prompt_ask();
        else
            play(SOUND_ERROR);
    }
}

/* Yes: the items go, box first and then the pouch, and one of the rare item goes into the box, as the Wyporium's
   trades do (FUN_009dbb6c). */
static void pay(u32 obj)
{
    const struct xrow *r = row_at(X->row);
    const u16 *pool = pool_of(r);
    window_close(3, 0);
    for (u32 i = 0; i < r->pool_count; i++)
        if (X->give[i])
            item_take(obj, pool[i], X->give[i]);
    item_give(save_control, r->item, 1, obj + OBJ_GIVE);
    play(SOUND_GIVEN);
    trade_buttons(obj, BUTTONS_DONE, BUTTON_FLAGS);
    trade_draw(obj, 0xC);
    facility_help(1, SHOP, HELP_SENT);
    X->sub = X_DONE;
}

/* The game's done step: the item box open on the slot the item went to until A or B, then the list again. */
static void done_keys(u32 obj, u8 *state)
{
    if (!facility_pressed(obj, BUTTON_A) && !facility_pressed(obj, BUTTON_B))
        return;
    play(SOUND_DECIDE);
    item_box_close(obj);
    trade_buttons(obj, BUTTONS_LIST, BUTTON_FLAGS);
    X->sub = X_LIST;
    X->handed = 0;
    redraw(obj, state, 1);
}

static void prompt_keys(u32 obj)
{
    facility_help(1, SHOP, XD->messages[XM_PROMPT]);
    window_update();
    u32 answer = window_answer(obj, (u32)&X->answer, window_input(obj), ANSWER_ANY);
    if (answer == 1) {
        pay(obj);
    } else if (answer == 2) {
        window_close(3, 0);
        trade_buttons(obj, BUTTONS_LIST, BUTTON_FLAGS);
        X->sub = X_POOL;
    }
}

/* ----- the screens ---------------------------------------------------------------------------------------- */

static void open_screen(u32 obj, u8 *state)
{
    X->unlocked = unlocked_rank();
    X->open = 1;
    X->sub = X_LIST;
    X->index = 0;
    X->total = scan_rows(0, 0, 0);
    if (!X->total) {
        play(SOUND_ERROR);
        state[0] = 2;
        return;
    }
    facility_menu_set(obj, NO_MENU, 0, 0);
    redraw(obj, state, 1);
}

/* The help line, written every frame as the game's trade list does. */
static void help(u8 *state)
{
    u32 message;
    if (X->sub == X_LIST) {
        u32 flags = *(u16 *)(entry_at(state, X->index % PAGE_ROWS) + 6);
        message = flags & FLAG_SHORT ? HELP_SHORT : flags & FLAG_BOX_FULL ? HELP_BOX_FULL : HELP_LIST;
    } else {
        message = XD->messages[XM_HELP_POOL];
    }
    facility_help(1, SHOP, message);
}

static void exchange_step(u32 obj, u8 *state)
{
    if (!X->open) {
        open_screen(obj, state);
        return;
    }
    if (X->sub == X_PROMPT) {
        prompt_keys(obj);
        return;
    }
    if (X->sub == X_DONE) {
        done_keys(obj, state);
        return;
    }
    help(state);
    if (X->sub == X_POOL)
        pool_keys(obj, state);
    else
        list_keys(obj, state);
}

/* One frame of state 12. */
ARM void exchange_update(u32 obj, u8 *state)
{
    exchange_step(obj, state);
}

/* Any way out of state 12: the trade list's groups go (the game's own exit hides them too, but not the forced one). */
ARM void exchange_close(u32 obj)
{
    if (X->open) {
        if (X->sub == X_PROMPT)
            window_close(3, 0);
        if (X->sub == X_DONE)
            item_box_close(obj);
        trade_hide(obj, 0);
    }
    X->open = 0;
}

/* The menu: A on our line (the last: line count - 1) enters the screens; it is the only line state 12 is for. */
static int our_line(const u8 *state)
{
    return *(short *)(state + LINE_AT) + 1 == *(u16 *)(state + LINE_COUNT);
}

ARM u32 exchange_pressed(u32 obj, void *cursor, u32 zero, u8 *state)
{
    u32 result = wyporium_menu_a(obj, cursor, zero);
    if (result == 1 && our_line(state)) {
        X->open = 0;
        state[0] = EXCHANGE_STATE;
        return 0;
    }
    return result;
}

ARM u32 exchange_help_c(u8 *state)
{
    if (!our_line(state))
        return 0;
    facility_help(1, SHOP, XD->messages[XM_MENU_HELP]);
    return 1;
}

/* ----- the hooks ------------------------------------------------------------------------------------------ */

__asm__(
    "   .section .text.exchange_hooks, \"ax\", %progbits\n"
    "   .arm\n"
    "   .global exchange_state, exchange_bright, exchange_menu_a, exchange_help, exchange_leave\n"
    /* r4 = the Wyporium's state, r8 = the lobby object: state 12 runs the screens, the rest is the game's default */
    "exchange_state:\n"
    "   ldrb    r0, [r4]\n"
    "   cmp     r0, #" STR(EXCHANGE_STATE) "\n"
    "   bne     wyporium_tail\n"
    "   mov     r0, r8\n"
    "   mov     r1, r4\n"
    "   bl      exchange_update\n"
    "   b       wyporium_tail\n"
    /* "bic r9, r9, #8" (no request open: line 3 dim); the three-line menu's line 3 is ours */
    "exchange_bright:\n"
    "   bic     r9, r9, #8\n"
    "   ldrh    r0, [r4, #" STR(LINE_COUNT) "]\n"
    "   cmp     r0, #4\n"
    "   orreq   r9, r9, #8\n"
    "   bx      lr\n"
    /* the menu's cursor: r0 = obj, r1 = its state, r2 = 0 -> 1 on A (not on ours) */
    "exchange_menu_a:\n"
    "   push    {lr}\n"
    "   mov     r3, r4\n"
    "   bl      exchange_pressed\n"
    "   pop     {pc}\n"
    /* "cmp r0, #0" of the help chain (r0 = the highlighted line); ours has its own help, and the menu is redrawn */
    "exchange_help:\n"
    "   mov     r0, r4\n"
    "   bl      exchange_help_c\n"
    "   cmp     r0, #0\n"
    "   bne     wyporium_menu\n"
    "   ldrsh   r0, [r4, #" STR(LINE_AT) "]\n"
    "   cmp     r0, #0\n"
    "   b       wyporium_chain\n"
    /* the old state's cases (r1 = the old state): leaving state 12 hides the trade list */
    "exchange_leave:\n"
    "   cmp     r1, #" STR(EXCHANGE_STATE) "\n"
    "   bne     wyporium_leave\n"
    "   mov     r0, r8\n"
    "   bl      exchange_close\n"
    "   b       wyporium_leave\n"
    "   .ltorg\n"
    "   .text\n");
