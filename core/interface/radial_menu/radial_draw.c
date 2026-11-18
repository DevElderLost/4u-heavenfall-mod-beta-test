/* The item wheel's picture (interface/radial_menu/radial_draw.py makes its layouts and data; docs/interface/
 * radial_menu.md, "Drawing" and "The wheel in Edit Slots").
 *
 * The same painting serves two pictures: the quest's (below) and Edit Slots' in the START menu (radial_menu_wheel, at
 * the end: the same tree in ui020's big list frame group, its own state radial_menu_state, its own places, the pouch
 * the menu shows for the quantities, every slot's diamond kept as a target and the gold on the editor's slot).
 *
 * A unit of the wheel's block (radial_wheel.c), in two halves:
 *   - radial_seen(hunter, choices), from the wheel's entry in the local hunter's input update, once a frame: it keeps
 *     the hunter and whether the wheel is open (the item mode's bit in the hunter's actions word, the wheel's on / off
 *     choice) for this frame;
 *   - radial_frame(), from the quest's shared frame hook (interface/quest_layouts/, entry INDEX of radial_draw.py),
 *     after every system's move and before the render: it draws. A frame the input update did not run (a pause, a
 *     cutscene) leaves the wheel closed.
 * Open, in a quest with the HUD on (the health bar's group shown), our group `hf_wheel` (the layout the quest loads at
 * radial_draw_data.index) is shown with, for each of the 8 slots:
 *   - the slot's diamond and its item's picture, the game's own (FUN_00c0de18 writes the picture's cell and colour into
 *     the sprite), its colour darker (red, green and blue times the curated share) when the hunter does not carry the
 *     item; a slot with no item shows neither;
 *   - its quantity at the picture's bottom right (FUN_005e588c, at most 99), in the curated count colour, or 0 in the
 *     curated grey for an item not carried;
 *   - its item name (FUN_005a86f8, the item selector's own call) in the slot's own text.
 * The slot in the stick's direction (the pad object's angle and magnitude, as radial_wheel.c reads them; from the
 * curated magnitude on) is the chosen one, when it holds an item: its diamond gives way to the gold one (larger) with
 * the gold glow behind it, its picture is drawn larger, its sector's needle shows, and its name gives way to the
 * larger gold name (the big name's null moved to that slot's place, with the text of that slot's alignment). With the
 * stick at rest nothing is highlighted.
 *
 * The group is found by its index in the GUI manager and its name hash, never kept beyond a frame's check: the next
 * quest loads a new one. Its cache flag is cleared, so the GUI walks its panes every frame and plain writes of the
 * runtime fields show at once (as damage_numbers.c); a text's holder null is marked for redraw after its string
 * changes (as horn_songs.c). Only what differs from what radial_draw_state remembers is written, everything the first
 * time in a quest's group; closing the wheel hides the group and its panes keep what they hold. The panes are the
 * root null's children in the file's order (radial_draw.py root_children), each checked by its name hash: another
 * file draws nothing.
 *
 * FUN_005a86f8 lays a name out into sprites taken from the pane pool, which the game takes from without testing it
 * (with the pool full it writes through a null pointer). So nothing is
 * changed unless the pool (the group's context, its first word) has at least `reserve` free places; with fewer the
 * picture stays as it is (hidden until it was painted once) and `refusals` counts the frames.
 *
 * Runtime structures: the GUI object's + 0x100 is the layout manager, whose + 0x154 / + 0x160 are its group list and
 * length; a
 * group's + 0x00 is its name hash, + 0x08 its first pane, + 0x14 its context, + 0x44 its flags (0x400 shown, 0x100
 * cached); a pane's + 0x00 is its name hash, + 0x08 its data, + 0x0C its draw node, + 0x14 its next sibling and + 0x20
 * its first child. A null's data: x, y at + 0x00 / + 0x04, its scale at + 0x10 / + 0x14, bit 0 of + 0x24 shown. A
 * sprite's: x, y at + 0x10 / + 0x14, its scale at + 0x28 / + 0x2C, its cell at + 0x30.. + 0x3C, its corners' colours
 * at + 0x40.. (a word each: red, green, blue, alpha from the low byte), bit 0x80 of + 0x58 shown (the other bits are
 * its draw primitive and are never written). A text's holder null is the text pane's next sibling.
 *
 * The root null's place and scale come from the choices' position, size and text size (radial_draw.py wheel_places: at
 * the right and at the bottom left the wheel keeps to the screen's edges at every size, and a size that would leave the
 * screen is drawn at the largest that fits). The text size scales the 8 name nulls and the big name's null and moves
 * them so each name keeps to its diamond (radial_draw.py name_box): written with the root's place.
 *
 * A slot's craft mark (a plus of the game's item sheet at the top right of its picture) shows when its bit of the mask
 * the wheel last gave radial_mark_craftable is set and the slot has an item; the mask is 0 until the wheel gives one.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, Thumb, a unit of radial_wheel.c's block; the game's
 * functions and variables are named in blocks.py GAME_SYMBOLS). Nothing here computes with floats: every value is
 * copied as its bits (radial_draw.py computes them).
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef int s32;

#include "radial_choices.h"

#define GAME __attribute__((long_call))
#define ARM __attribute__((target("arm"), noinline))

#define SLOTS 8
#define POSITIONS 3             /* radial_draw.py POSITIONS: the centre, the right, the bottom left */
#define BIG_TEXTS 3             /* radial_draw.py BIG_TEXTS: left-aligned, right-aligned, centred */
#define BODY_PANES 3            /* radial_draw.py MENU_BODY: the frame's two sides and its middle */
#define MENU_LAYOUTS 2          /* radial_draw.py MENU_LAYOUTS: Edit Slots' centred and small wheels */
#define QUEST_PLACES (4 * MAX_SIZES)            /* a text size's places in a quest: position * MAX_SIZES + size (the
                                                   positions' room a power of two: the ARM11 has no divide) */
#define MENU_PLACE (MAX_TEXTS * QUEST_PLACES)   /* a place from here is a menu layout's: text * MENU_PLACES + size
                                                   centred, + MAX_SIZES + size small */
#define MENU_PLACES (MENU_LAYOUTS * MAX_SIZES)

enum { LAYOUT_HIDDEN, LAYOUT_CENTRED, LAYOUT_SMALL };          /* radial_menu_wheel's layouts (radial_choices.h) */

enum {                          /* the root null's children, in the file's order (radial_draw.py root_children) */
    RINGS = 0,                  /* the ring's 4 quarters */
    RHOMBI = RINGS + 4,         /* slot k: its fill RHOMBI + 2k, its edge RHOMBI + 2k + 1 */
    HALO = RHOMBI + 2 * SLOTS,
    GOLD_FILL,
    GOLD_EDGE,
    ICONS,                      /* slot k: ICONS + k */
    DIGITS = ICONS + SLOTS,     /* slot k: its tens DIGITS + 2k, its units DIGITS + 2k + 1 */
    CRAFTS = DIGITS + 2 * SLOTS,        /* slot k: its craft mark CRAFTS + k */
    HUB = CRAFTS + SLOTS,
    NEEDLES,                    /* slot k: NEEDLES + k */
    NAMES = NEEDLES + SLOTS,    /* slot k: its name's null NAMES + k */
    BIG = NAMES + SLOTS,        /* the big name's null */
    CHILDREN
};

struct cell {
    u32 u, v, w, h;             /* floats, 0-1 */
};

struct draw_data {              /* radial_draw_data (radial_draw.py draw_data) */
    u32 group;                  /* name hash of the group */
    u32 index;                  /* its slot in the GUI manager */
    u32 layer, priority;        /* its place in the draw order */
    u32 root;                   /* name hash of its null */
    u32 children[CHILDREN];     /* ... of the null's children, in order */
    u32 names[SLOTS];           /* ... of each name null's text */
    u32 big[BIG_TEXTS];         /* ... of the big name's texts */
    u32 place[MAX_TEXTS][POSITIONS][MAX_SIZES][3];      /* the null's x, y and scale (floats) by text size,
                                                           position and size */
    u32 slot_at[SLOTS][2];      /* each slot's middle in the null (floats) */
    u32 name_at[MAX_TEXTS][SLOTS][2];   /* each slot's name null by text size (floats) */
    u32 big_at[MAX_TEXTS][SLOTS][2];    /* the big name's null at each slot by text size (floats) */
    u32 text_scale[MAX_TEXTS];  /* floats: the names' nulls' scale at each text size */
    struct cell digits[10];
    u32 marked_scale;           /* float: the chosen slot's picture */
    u32 reserve;                /* free places the pane pool must have */
    u32 look;                   /* the stick's magnitude from which a slot is chosen */
    u32 count_tint[2];          /* the quantity's colour word: carried, not carried */
    u32 dark;                   /* of 256: the share of red, green and blue a picture keeps when not carried */
    u8 sector_to_slot[8];
    u8 big_text[SLOTS];         /* the big name's text at each slot (its alignment) */
    u32 menu_group;             /* Edit Slots: name hash of ui020's big list frame group */
    u32 menu_frame;             /* ... of its frame's null */
    u32 menu_body[BODY_PANES];  /* ... of the frame's sides and middle, the null's children */
    u32 menu_strips;            /* ... of the rows' strips' null, the group's child */
    u32 menu_place[MAX_TEXTS][MENU_LAYOUTS][MAX_SIZES][3];      /* the root null's x, y and scale (floats) by text
                                                                   size: centred, small at the left, by size */
};

struct draw_state {             /* radial_draw_state and the start of radial_menu_state, written here only */
    u32 group;                  /* the group the fields below were painted into, 0 none */
    u32 hunter;                 /* the hunter the input update saw this frame */
    u16 item[SLOTS];            /* the item each slot shows, 0 none */
    u8 count[SLOTS];            /* the quantity each slot shows, NO_COUNT none */
    u16 big_item;               /* the item the big name holds */
    u8 grey;                    /* bit k: slot k's item is not carried (its picture darker, its 0 grey) */
    u8 marked;                  /* the chosen slot, or NO_SLOT */
    u8 place;                   /* where the null was put: the text size * QUEST_PLACES + the position * MAX_SIZES +
                                   the size, or a menu layout's (MENU_PLACE) */
    u8 painted;                 /* the group's panes hold the fields above (0: paint everything) */
    u8 open;                    /* the input update saw the wheel open this frame */
    u8 big_text;                /* the big name's text shown, NO_SLOT none */
    u8 craft;                   /* bit k: the wheel said slot k's item can be combined (radial_mark_craftable) */
    u8 craft_drawn;             /* bit k: slot k's craft mark is shown */
    u16 refusals;               /* frames a change was left undone for lack of room in the pane pool */
    u16 paints;                 /* slots drawn */
};

struct menu_state {             /* radial_menu_state, written here only */
    struct draw_state draw;     /* what the menu's panes hold (its group, hunter, open and craft fields unused) */
    u8 layout;                  /* the layout last asked for, LAYOUT_HIDDEN none */
    u8 hidden;                  /* bit k: the frame's part k (its body sprites, then the strips) hidden by the wheel */
    u8 cached;                  /* the group had its cache flag when the wheel cleared it */
    u8 shown;                   /* the root null is shown */
};

_Static_assert(sizeof(struct draw_data) == 3092, "blocks.py RADIAL_DRAW_DATA_SIZE, radial_draw.py DATA");
_Static_assert(sizeof(struct draw_state) == 48, "blocks.py radial_draw_state");
_Static_assert(sizeof(struct menu_state) == 52, "blocks.py radial_menu_state");

extern const struct draw_data radial_draw_data;
extern struct draw_state radial_draw_state;
extern struct menu_state radial_menu_state;
extern u32 gui_control, pad_control, item_control, game_control, health_binder;
extern char start_list_ui[];                                    /* the START menu's list binder */
extern char start_menu[];                                       /* the START menu's object */

GAME void item_icon(u32 unused, u32 data, u32 item);            /* FUN_00c0de18: cell and colour into data + 0x20.. */
GAME void item_name(const u32 *ref, u32 item);                  /* FUN_005a86f8: the name into {group, pane} */
GAME s32 pouch_count(u32 control, u32 hunter, u32 item, u32 flag);       /* FUN_005e588c */
GAME void group_show(u32 group, u32 visible);                   /* FUN_00ae53e0 */
GAME void gui_group_order(u32 group, u32 layer, u32 priority);  /* FUN_00ae63c8 */
GAME void pane_redraw(u32 group, u32 pane);                     /* FUN_00ae6bcc */
GAME void gui_group_changed(u32 group);                         /* FUN_00ae65b0: + 0x42 = 3, the lists recorded again */
GAME void text_show(u32 data, u32 visible);                     /* FUN_00ae7618: the text and its holder null */
GAME void start_list_group(char *binder, u32 group, u32 shown);  /* FUN_00d94358: the binder's mask, applied each frame */
int radial_choices(struct choices *out);                        /* radial_wheel.c: the character's choices */

#define W(base, off) (*(volatile u32 *)((base) + (off)))
#define H(base, off) (*(volatile u16 *)((base) + (off)))
#define B(base, off) (*(volatile u8 *)((base) + (off)))

#define PLAYER_STATUS 0xE30             /* hunter -> p, as in radial_wheel.c */
#define P_ACTIONS 0x3CC
#define ITEM_MODE 0x800u
#define PAD_ANGLE 0x32E
#define PAD_MAGNITUDE 0x33A
#define GAME_MODE 0x2B                  /* sGameControl: 1 in a quest */
#define QUEST_MODE 1
#define LIST_FRAME_GROUP 0xD            /* start_list_ui's group of the big list's frame (mod_settings.c GROUP_FRAME) */
#define M_CONTEXT 0x5                   /* the START menu's object: u8, 1 in a quest, 2 in town */
#define M_POUCH 0x1D4                   /* ... its pouch's places ({u16 item, s16 quantity}), set by FUN_005e7a24 */
#define CONTEXT_QUEST 1
#define POUCH_PLACES_QUEST 38           /* the quest pouch: its 32 items, 4 wystones and 2 more (radial_editor.c) */
#define POUCH_PLACES_TOWN 24

#define GUI_MANAGER 0x100
#define GROUP_LIST 0x154
#define GROUP_COUNT 0x160
#define GROUP_HASH 0x00
#define GROUP_PANES 0x08
#define GROUP_CONTEXT 0x14
#define GROUP_FLAGS 0x44
#define GROUP_SHOWN 0x400u
#define GROUP_CACHED 0x100u
#define POOL_COUNT 0x08                 /* a pool: + 8 its size, + 0xC the places taken */
#define POOL_USED 0x0C
#define PANE_HASH 0x00
#define PANE_DATA 0x08
#define PANE_NODE 0x0C
#define PANE_NEXT 0x14
#define PANE_CHILD 0x20
#define NODE_DIRTY 0x12
#define DIRTY 3
#define NULL_X 0x00
#define NULL_Y 0x04
#define NULL_SCALE 0x10
#define NULL_FLAGS 0x24
#define NULL_SHOWN 1u
#define SPRITE_X 0x10
#define SPRITE_Y 0x14
#define SPRITE_SCALE 0x28
#define SPRITE_CELL 0x10                /* FUN_00c0de18 takes the data + 0x10 and writes at + 0x20 */
#define SPRITE_UV 0x30
#define SPRITE_TINT 0x40
#define SPRITE_FLAGS 0x58
#define SPRITE_SHOWN 0x80u

#define NO_SLOT 0xFF
#define NO_COUNT 0xFF
#define MAX_COUNT 99                    /* two digits */
#define ITEM_LIMIT 0x790                /* the game's ids from here are placeholders, not items */
#define ONE 0x3f800000u                 /* 1.0f */
#define ALPHA 0xFF000000u               /* a colour word's alpha byte */

struct panes {                          /* the group's panes this frame */
    u32 root;
    u32 child[CHILDREN];
    u32 name[SLOTS];                    /* each slot's text */
    u32 big[BIG_TEXTS];
};

struct want {                           /* what the wheel should show now */
    u16 item[SLOTS];
    u8 count[SLOTS];
    u8 grey;
    u8 marked;
    u8 place;
    u8 craft;                           /* bit k: slot k shows its craft mark */
    u8 targets;                         /* a slot with no item keeps its diamond (Edit Slots: where an item goes) */
};

/* ---- the input update's half */

void radial_seen(u32 hunter, const struct choices *choices)
{
    struct draw_state *state = &radial_draw_state;
    u32 status = hunter ? W(hunter, PLAYER_STATUS) : 0;
    state->hunter = hunter;
    state->open = status && choices && (W(status, P_ACTIONS) & ITEM_MODE) && choices->enabled ? 1 : 0;
}

/* The wheel's step says, before radial_seen each frame, which slots (bit k) hold an item that can be combined from what
 * the hunter carries; their craft marks show over the pictures. Never said, the mask stays 0 and no mark shows. */
void radial_mark_craftable(u32 mask)
{
    radial_draw_state.craft = mask & ((1u << SLOTS) - 1);
}

/* ---- the group and its panes */

static int is_shown(u32 group)
{
    return W(group, GROUP_FLAGS) & GROUP_SHOWN ? 1 : 0;
}

static u32 group_find(void)
{
    const struct draw_data *data = &radial_draw_data;
    u32 gui = gui_control, manager = gui ? W(gui, GUI_MANAGER) : 0;
    if (!manager || !W(manager, GROUP_LIST) || data->index >= W(manager, GROUP_COUNT))
        return 0;
    u32 group = W(W(manager, GROUP_LIST), 4 * data->index);
    return group && W(group, GROUP_HASH) == data->group ? group : 0;
}

static int in_quest(void)
{
    u32 control = game_control, hud = health_binder;
    return control && B(control, GAME_MODE) == QUEST_MODE && hud && (W(hud, GROUP_FLAGS) & GROUP_SHOWN);
}

static u32 pane_find(u32 pane, u32 hash)
{
    for (; pane; pane = W(pane, PANE_NEXT))
        if (W(pane, PANE_HASH) == hash)
            return pane;
    return 0;
}

/* The wheel's panes under `root`, each checked by its name: 0 for a file the wheel's panes were not made in */
static int panes_find(u32 root, struct panes *out)
{
    const struct draw_data *data = &radial_draw_data;
    if (!root || W(root, PANE_HASH) != data->root)
        return 0;
    out->root = root;
    u32 pane = W(root, PANE_CHILD);
    for (u32 i = 0; i < CHILDREN; i++, pane = W(pane, PANE_NEXT)) {
        if (!pane || W(pane, PANE_HASH) != data->children[i])
            return 0;
        out->child[i] = pane;
    }
    for (u32 k = 0; k < SLOTS; k++)
        if (!(out->name[k] = pane_find(W(out->child[NAMES + k], PANE_CHILD), data->names[k])))
            return 0;
    for (u32 t = 0; t < BIG_TEXTS; t++)
        if (!(out->big[t] = pane_find(W(out->child[BIG], PANE_CHILD), data->big[t])))
            return 0;
    return 1;
}

/* The pane pool has the free places a change may take */
static int has_room(u32 group)
{
    u32 context = W(group, GROUP_CONTEXT), pool = context ? W(context, 0) : 0;
    return pool && W(pool, POOL_USED) + radial_draw_data.reserve <= W(pool, POOL_COUNT);
}

static void redraw(u32 group, u32 pane)
{
    u32 node = W(pane, PANE_NODE);
    if (node)
        B(node, NODE_DIRTY) = DIRTY;
    else
        pane_redraw(group, pane);
}

/* ---- writing panes */

static void sprite_show(u32 pane, int on)
{
    u32 data = W(pane, PANE_DATA);
    W(data, SPRITE_FLAGS) = on ? W(data, SPRITE_FLAGS) | SPRITE_SHOWN : W(data, SPRITE_FLAGS) & ~SPRITE_SHOWN;
}

static void sprite_at(u32 pane, const u32 *at)
{
    u32 data = W(pane, PANE_DATA);
    W(data, SPRITE_X) = at[0];
    W(data, SPRITE_Y) = at[1];
}

static void sprite_scale(u32 pane, u32 scale)
{
    u32 data = W(pane, PANE_DATA);
    W(data, SPRITE_SCALE) = scale;
    W(data, SPRITE_SCALE + 4) = scale;
}

static void null_show(u32 pane, int on)
{
    u32 data = W(pane, PANE_DATA);
    W(data, NULL_FLAGS) = on ? W(data, NULL_FLAGS) | NULL_SHOWN : W(data, NULL_FLAGS) & ~NULL_SHOWN;
}

/* A text shown or hidden, its string set first to `item`'s name when `item` is not 0 */
static void text_paint(u32 group, u32 text, u32 item, int on)
{
    if (item) {
        u32 ref[2];
        ref[0] = group;
        ref[1] = text;
        item_name(ref, item);
    }
    text_show(W(text, PANE_DATA), on);
    u32 holder = W(text, PANE_NEXT);
    if (holder)
        redraw(group, holder);
}

/* The text size of a place */
static u32 place_text(u32 place)
{
    return (place >= MENU_PLACE ? (place - MENU_PLACE) / MENU_PLACES : place / QUEST_PLACES) % MAX_TEXTS;
}

static void null_place(u32 pane, const u32 *at, u32 scale)
{
    u32 data = W(pane, PANE_DATA);
    W(data, NULL_X) = at[0];
    W(data, NULL_Y) = at[1];
    W(data, NULL_SCALE) = scale;
    W(data, NULL_SCALE + 4) = scale;
}

/* The null's place and size: the centre, the right or the bottom left of the screen, at the chosen size; or one of
 * Edit Slots' layouts; and the names' nulls at the place's text size (the big name's moves to its slot in paint_mark) */
static void paint_place(const struct panes *panes, u32 place)
{
    const struct draw_data *draw = &radial_draw_data;
    u32 text = place_text(place), menu = (place - MENU_PLACE) % MENU_PLACES, quest = place % QUEST_PLACES;
    const u32 *at = place >= MENU_PLACE ? draw->menu_place[text][menu / MAX_SIZES][menu % MAX_SIZES]
                                        : draw->place[text][quest / MAX_SIZES < POSITIONS ? quest / MAX_SIZES : 0]
                                                     [quest % MAX_SIZES];
    null_place(panes->root, at, at[2]);
    for (u32 slot = 0; slot < SLOTS; slot++)
        null_place(panes->child[NAMES + slot], draw->name_at[text][slot], draw->text_scale[text]);
    u32 big = W(panes->child[BIG], PANE_DATA);
    W(big, NULL_SCALE) = draw->text_scale[text];
    W(big, NULL_SCALE + 4) = draw->text_scale[text];
}

/* A colour word with its red, green and blue kept at `dark` of 256, its alpha as it was */
static u32 darker(u32 colour, u32 dark)
{
    u32 out = colour & ALPHA;
    for (u32 shift = 0; shift < 24; shift += 8)
        out |= ((colour >> shift & 0xFF) * dark >> 8) << shift;
    return out;
}

/* A slot's picture: hidden for no item; else the item's, its colour darker when not carried */
static void paint_icon(u32 icon, u32 item, u32 grey)
{
    u32 data = W(icon, PANE_DATA);
    sprite_show(icon, item != 0);
    if (!item)
        return;
    item_icon(0, data + SPRITE_CELL, item);
    if (grey)
        for (u32 corner = 0; corner < 4; corner++)
            W(data, SPRITE_TINT + 4 * corner) = darker(W(data, SPRITE_TINT + 4 * corner), radial_draw_data.dark);
}

static void digit_paint(u32 pane, u32 digit, u32 tint)
{
    const struct cell *cell = &radial_draw_data.digits[digit];
    u32 data = W(pane, PANE_DATA);
    W(data, SPRITE_UV) = cell->u;
    W(data, SPRITE_UV + 4) = cell->v;
    W(data, SPRITE_UV + 8) = cell->w;
    W(data, SPRITE_UV + 12) = cell->h;
    for (u32 corner = 0; corner < 4; corner++)
        W(data, SPRITE_TINT + 4 * corner) = tint;
    sprite_show(pane, 1);
}

/* A slot's quantity in its two digits (the first only from 10), in the grey of an item not carried or the count's
 * colour; or none */
static void paint_count(u32 tens, u32 units, u32 count, u32 grey)
{
    if (count == NO_COUNT) {
        sprite_show(tens, 0);
        sprite_show(units, 0);
        return;
    }
    u32 tint = radial_draw_data.count_tint[grey ? 1 : 0];
    u32 high = (count * 205) >> 11;     /* count / 10, exact up to 1028: the ARM11 has no divide */
    digit_paint(units, count - 10 * high, tint);
    if (high)
        digit_paint(tens, high, tint);
    else
        sprite_show(tens, 0);
}

/* ---- what the wheel should show */

/* The slots' items, no quantity yet */
static void want_items(struct want *want, const struct choices *choices)
{
    for (u32 slot = 0; slot < SLOTS; slot++) {
        u32 item = choices->slots[slot];
        if (item >= ITEM_LIMIT)
            item = 0;
        want->item[slot] = item;
        want->count[slot] = NO_COUNT;
    }
    want->grey = 0;
    want->craft = 0;
    want->targets = 0;
}

/* A slot's quantity: at most 99, or a grey 0 for an item not carried */
static void want_count(struct want *want, u32 slot, s32 count)
{
    if (count <= 0) {
        want->grey |= 1u << slot;
        want->count[slot] = 0;
    } else {
        want->count[slot] = count > MAX_COUNT ? MAX_COUNT : count;
    }
}

static void observe(struct want *want, u32 hunter, const struct choices *choices)
{
    want_items(want, choices);
    for (u32 slot = 0; slot < SLOTS; slot++)
        if (want->item[slot])
            want_count(want, slot, pouch_count(item_control, hunter, want->item[slot], 1));
    for (u32 slot = 0; slot < SLOTS; slot++)
        if (want->item[slot])
            want->craft |= radial_draw_state.craft & (1u << slot);
    want->place = (choices->text < MAX_TEXTS ? choices->text : 0) * QUEST_PLACES +
                  (choices->position < POSITIONS ? choices->position : 0) * MAX_SIZES +
                  (choices->size < MAX_SIZES ? choices->size : 0);
    u32 pad = pad_control;
    u32 angle = pad ? H(pad, PAD_ANGLE) : 0, magnitude = pad ? H(pad, PAD_MAGNITUDE) : 0;
    u32 slot = radial_draw_data.sector_to_slot[((angle + 0x1000) >> 13) & 7] & 7;
    want->marked = magnitude >= radial_draw_data.look && want->item[slot] ? slot : NO_SLOT;
}

static int slot_changed(const struct draw_state *state, const struct want *want, u32 slot)
{
    return state->item[slot] != want->item[slot] || state->count[slot] != want->count[slot] ||
           ((state->grey ^ want->grey) >> slot & 1) || (state->marked == slot) != (want->marked == slot) ||
           ((state->craft_drawn ^ want->craft) >> slot & 1);
}

static int anything_changed(const struct draw_state *state, const struct want *want)
{
    for (u32 slot = 0; slot < SLOTS; slot++)
        if (slot_changed(state, want, slot))
            return 1;
    return state->place != want->place || state->marked != want->marked;
}

/* ---- painting */

/* Slot `slot`: what differs from `state` (everything with `fresh`) */
static void paint_slot(u32 group, const struct panes *panes, const struct draw_state *state, const struct want *want,
                       u32 slot, int fresh)
{
    u32 item = want->item[slot], grey = want->grey >> slot & 1, chosen = want->marked == slot;
    int new_item = fresh || state->item[slot] != item;
    int new_mark = new_item || (state->marked == slot) != chosen;
    if (new_item || ((state->grey >> slot & 1) != grey))
        paint_icon(panes->child[ICONS + slot], item, grey);
    if (new_item || state->count[slot] != want->count[slot] || ((state->grey >> slot & 1) != grey))
        paint_count(panes->child[DIGITS + 2 * slot], panes->child[DIGITS + 2 * slot + 1], want->count[slot], grey);
    if (new_item || ((state->craft_drawn ^ want->craft) >> slot & 1))
        sprite_show(panes->child[CRAFTS + slot], want->craft >> slot & 1);
    if (new_mark) {
        u32 diamond = (item || want->targets) && !chosen;
        sprite_show(panes->child[RHOMBI + 2 * slot], diamond);
        sprite_show(panes->child[RHOMBI + 2 * slot + 1], diamond);
        if (item)
            sprite_scale(panes->child[ICONS + slot], chosen ? radial_draw_data.marked_scale : ONE);
        text_paint(group, panes->name[slot], new_item ? item : 0, item && !chosen);
    }
}

/* The chosen slot's gold diamond and glow, its needle and its big name (none for a slot with no item: Edit Slots');
 * none at rest */
static void paint_mark(u32 group, const struct panes *panes, struct draw_state *state, const struct want *want,
                       int fresh)
{
    const struct draw_data *data = &radial_draw_data;
    u32 slot = want->marked, shown = slot != NO_SLOT;
    for (u32 k = 0; k < SLOTS; k++)
        if (fresh || k == state->marked || k == slot)
            sprite_show(panes->child[NEEDLES + k], k == slot);
    for (u32 pane = HALO; pane <= GOLD_EDGE; pane++) {
        if (shown)
            sprite_at(panes->child[pane], data->slot_at[slot]);
        sprite_show(panes->child[pane], shown);
    }
    u32 big = panes->child[BIG], named = shown && want->item[slot];
    null_show(big, named);
    if (shown && !named)
        state->big_item = 0;            /* the slot's next item lays its name out and shows the null again */
    if (!named)
        return;
    u32 data_big = W(big, PANE_DATA), text = data->big_text[slot] < BIG_TEXTS ? data->big_text[slot] : 0;
    const u32 *big_at = data->big_at[place_text(want->place)][slot];
    W(data_big, NULL_X) = big_at[0];
    W(data_big, NULL_Y) = big_at[1];
    for (u32 t = 0; t < BIG_TEXTS; t++)
        if (t != text && (fresh || state->big_text == NO_SLOT || t == state->big_text))
            text_paint(group, panes->big[t], 0, 0);
    if (fresh || state->big_text != text || state->big_item != want->item[slot])
        text_paint(group, panes->big[text], want->item[slot], 1);
    state->big_text = text;
    state->big_item = want->item[slot];
}

static void paint(u32 group, const struct panes *panes, struct draw_state *state, const struct want *want, int fresh)
{
    int moved = fresh || state->place != want->place;
    if (moved)
        paint_place(panes, want->place);
    for (u32 slot = 0; slot < SLOTS; slot++) {
        if (!fresh && !slot_changed(state, want, slot))
            continue;
        paint_slot(group, panes, state, want, slot, fresh);
        state->paints++;
    }
    if (moved || state->marked != want->marked ||
        (want->marked != NO_SLOT && state->big_item != want->item[want->marked]))
        paint_mark(group, panes, state, want, fresh);
    for (u32 slot = 0; slot < SLOTS; slot++) {
        state->item[slot] = want->item[slot];
        state->count[slot] = want->count[slot];
    }
    state->grey = want->grey;
    state->craft_drawn = want->craft;
    state->marked = want->marked;
    state->place = want->place;
}

/* What differs from `state` painted (everything the first time), when the pane pool has room for it; else the
 * picture stays as it is and the frame is counted */
static void draw(u32 group, const struct panes *panes, struct draw_state *state, const struct want *want)
{
    int fresh = !state->painted;
    if (!fresh && !anything_changed(state, want))
        return;
    if (!has_room(group)) {
        if (state->refusals != 0xFFFF)
            state->refusals++;
        return;
    }
    if (fresh) {
        state->marked = NO_SLOT;
        state->big_text = NO_SLOT;
    }
    paint(group, panes, state, want, fresh);
    state->painted = 1;
}

/* ---- the quest's frame */

ARM void radial_frame(void)
{
    const struct draw_data *data = &radial_draw_data;
    struct draw_state *state = &radial_draw_state;
    int open = state->open;
    state->open = 0;
    u32 group = group_find();
    if (group != state->group) {        /* a new quest's group, or none */
        state->group = group;
        state->painted = 0;
        if (group)
            W(group, GROUP_FLAGS) &= ~GROUP_CACHED;
    }
    if (!group)
        return;
    struct choices choices;
    if (!open || !in_quest() || !radial_choices(&choices) || !choices.enabled) {
        if (is_shown(group))            /* the panes keep what they hold for the next opening */
            group_show(group, 0);
        return;
    }
    struct panes panes;
    if (!panes_find(W(group, GROUP_PANES), &panes))
        return;
    struct want want;
    observe(&want, state->hunter, &choices);
    draw(group, &panes, state, &want);
    if (state->painted && !is_shown(group)) {   /* never the file's own picture: shown once painted */
        group_show(group, 1);
        gui_group_order(group, data->layer, data->priority);
    }
}

/* ---- Edit Slots, the START menu's (radial_editor.c) */

/* ui020's big list frame group, bound by the START menu's list binder for the whole game (a common layout), checked
 * by its name: 0 before the binder has it */
static u32 menu_group(void)
{
    u32 group = W((u32)start_list_ui, 4 * LIST_FRAME_GROUP);
    return group && W(group, GROUP_HASH) == radial_draw_data.menu_group ? group : 0;
}

/* What the pouch the START menu shows holds of `item`, over its places: 38 in a quest, 24 in town */
static s32 menu_count(u32 item)
{
    u32 menu = (u32)start_menu, pouch = W(menu, M_POUCH);
    u32 places = B(menu, M_CONTEXT) == CONTEXT_QUEST ? POUCH_PLACES_QUEST : POUCH_PLACES_TOWN;
    s32 total = 0;
    if (!pouch)
        return 0;
    for (u32 k = 0; k < places; k++) {
        s32 quantity = (short)H(pouch, 4 * k + 2);
        if (H(pouch, 4 * k) == item && quantity > 0)
            total += quantity;
    }
    return total;
}

/* The saved items with the pouch's quantities, every slot a target, `marked` in gold whatever it holds, and the
 * marked slot showing `preview_item` with `preview_count` instead when that names an item */
static void observe_menu(struct want *want, const struct choices *choices, u32 layout, u32 marked, u32 preview_item,
                         u32 preview_count)
{
    want_items(want, choices);
    want->targets = 1;
    want->marked = marked < SLOTS ? marked : NO_SLOT;
    if (want->marked != NO_SLOT && preview_item && preview_item < ITEM_LIMIT)
        want->item[want->marked] = preview_item;
    for (u32 slot = 0; slot < SLOTS; slot++)
        if (want->item[slot])
            want_count(want, slot, slot == want->marked && preview_item && preview_item < ITEM_LIMIT
                                       ? (s32)(preview_count > MAX_COUNT ? MAX_COUNT : preview_count)
                                       : menu_count(want->item[slot]));
    want->place = MENU_PLACE + (choices->text < MAX_TEXTS ? choices->text : 0) * MENU_PLACES +
                  (layout - LAYOUT_CENTRED) * MAX_SIZES + (choices->size < MAX_SIZES ? choices->size : 0);
}

static int pane_shown(u32 pane, int null)
{
    u32 data = W(pane, PANE_DATA);
    return null ? (W(data, NULL_FLAGS) & NULL_SHOWN) != 0 : (W(data, SPRITE_FLAGS) & SPRITE_SHOWN) != 0;
}

/* The list's frame body (its sides and middle) and its rows' strips: hidden under the centred wheel (only what was
 * shown, each remembered), or each part the wheel hid shown again */
static void menu_body(u32 group, int hide)
{
    struct menu_state *menu = &radial_menu_state;
    const struct draw_data *data = &radial_draw_data;
    if (!hide && !menu->hidden)
        return;
    u32 first = W(group, GROUP_PANES), frame = pane_find(first, data->menu_frame);
    for (u32 k = 0; k <= BODY_PANES; k++) {
        int null = k == BODY_PANES;
        u32 pane = null ? pane_find(first, data->menu_strips)
                        : frame ? pane_find(W(frame, PANE_CHILD), data->menu_body[k]) : 0;
        if (!pane)
            continue;
        if (hide && !(menu->hidden >> k & 1) && pane_shown(pane, null))
            menu->hidden |= 1u << k;
        else if (hide || !(menu->hidden >> k & 1))
            continue;
        if (null)
            null_show(pane, !hide);
        else
            sprite_show(pane, !hide);
        redraw(group, pane);
    }
    if (!hide)
        menu->hidden = 0;
}

/* Off the top screen: the root hidden, the frame's parts back, the group's cache flag back and the group marked
 * changed; the next showing paints everything (the pouch and the choices may change meanwhile). Uncached, the game's
 * group draw (FUN_00ae6d24) walks the panes and drops every redraw mark without touching the command lists it cached
 * before the wheel showed, so with the flag back alone it would replay those lists (the game's own writes to the
 * group meanwhile lost); marked changed, it records them again from the panes, one draw buffer a frame. */
static void menu_hide(u32 group, u32 root)
{
    struct menu_state *menu = &radial_menu_state;
    if (root && menu->shown) {
        null_show(root, 0);
        redraw(group, root);
    }
    menu->shown = 0;
    menu_body(group, 0);
    if (menu->cached) {
        W(group, GROUP_FLAGS) |= GROUP_CACHED;
        gui_group_changed(group);
    }
    menu->cached = 0;
    menu->draw.painted = 0;
}

/* Edit Slots' picture, once a frame while one of its two levels is open and once with LAYOUT_HIDDEN on every way out
 * (radial_choices.h). The wheel's tree is the last child of ui020's big list frame group (radial_draw.py
 * build_menu_layout), drawn with that group's draw order: above the menu's background and the list's frame, below
 * the list's cursor and rows, the pager and the game's dialogs. The editor hides the big list's groups at the wheel
 * level, so the frame group is shown again (its title strip, title bar and title stay); the centred wheel hides the
 * frame's body and strips, which the small one beside the pouch list shows again. The group's cache flag is cleared
 * while the wheel shows (plain writes show at once) and set back when it leaves, the group marked changed. */
ARM void radial_menu_wheel(const struct choices *c, u32 layout, u32 marked, u32 preview_item, u32 preview_count)
{
    struct menu_state *menu = &radial_menu_state;
    struct draw_state *state = &menu->draw;
    u32 group = menu_group();
    if (group != state->group) {        /* first use, or the binder's group changed: nothing of ours is in it */
        state->group = group;
        state->painted = 0;
        menu->hidden = menu->cached = menu->shown = 0;
    }
    if (!group)
        return;
    struct panes panes;
    u32 root = pane_find(W(group, GROUP_PANES), radial_draw_data.root);
    if (!panes_find(root, &panes))
        return;
    if (!c || layout == LAYOUT_HIDDEN || layout > LAYOUT_SMALL) {
        if (menu->layout != LAYOUT_HIDDEN || menu->shown || menu->hidden || menu->cached)
            menu_hide(group, root);
        menu->layout = LAYOUT_HIDDEN;
        return;
    }
    start_list_group(start_list_ui, LIST_FRAME_GROUP, 1);
    if (W(group, GROUP_FLAGS) & GROUP_CACHED) {
        W(group, GROUP_FLAGS) &= ~GROUP_CACHED;
        menu->cached = 1;
    }
    struct want want;
    observe_menu(&want, c, layout, marked, preview_item, preview_count);
    menu->layout = layout;
    if (!has_room(group)) {             /* a redraw mark may take a place too: nothing changes */
        if ((!state->painted || anything_changed(state, &want)) && state->refusals != 0xFFFF)
            state->refusals++;
        return;
    }
    draw(group, &panes, state, &want);
    menu_body(group, layout == LAYOUT_CENTRED);
    if (state->painted && !menu->shown) {       /* never the file's own picture: shown once painted */
        null_show(root, 1);
        redraw(group, root);
        menu->shown = 1;
    }
}
