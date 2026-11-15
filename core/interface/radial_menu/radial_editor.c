/* The Radial Menu's screen, which the Radial Menu row of Mod Settings'
 * Interface list opens, on the game's big list through mod_settings.c's mod_list_* functions and the wheel's own picture
 * (radial_menu_wheel, radial_draw.c). The block radial_editor, the item wheel's (a mod without the wheel has no row that
 * opens it); its texts and numbers are the block radial_editor_data (radial_editor.py editor_data), its state the
 * variable radial_editor_state.
 *
 * Three levels share the widget:
 *   - the menu level, under the row's title: the switch (Enabled / Disabled, first as every feature's switch),
 *     Edit Slots, Trigger, Autocombine, Position and Size, the switch and the settings with their values. Up and Down
 *     walk them, A changes the row's value to the next one (Trigger: Tilt, Flick, Release; Position: centre, right,
 *     bottom left; Size: the next size), from the last back to the first, or opens Edit Slots; B goes back to the small
 *     list. It draws no wheel;
 *   - Edit Slots, the wheel level: the big list is hidden and the wheel is shown centred (radial_menu_wheel, layout 1)
 *     with the cursor's slot in gold. The C-stick points at a slot at once (the angle's sector, as the wheel's use reads
 *     it, from a curated magnitude), the D-pad's Left and Right turn the cursor one slot, anticlockwise and clockwise;
 *     the cursor stays where it is left, and a visit starts on the slot last edited. A opens the pouch level on the
 *     slot, Y empties the slot, B goes back to the menu level on Edit Slots;
 *   - the pouch level, under Edit Slots' title (the gold slot shows which one is edited): what the pouch holds that the
 *     game's item bar could select, in the pouch's order, 8 a page (the rows that have an item's picture) on as many
 *     pages as it needs, the list shown over the wheel, now small at the left (layout 2) with the gold slot showing the
 *     current row's item and its quantity. A stores the item's id in the slot, Y empties the slot, B goes back without a
 *     change; each goes back to the wheel level on the same slot.
 *
 * The wheel is asked once a frame at the two levels of Edit Slots and, with layout 0, at every way out of them (B, a save
 * gone, START or a forced close: radial_editor_leave, from mod_menu_closed).
 *
 * In a quest the hunter walks with the START menu open, so Edit Slots leaves the Circle Pad to the walk: its two
 * levels read the D-pad alone (the menu's words carry the Circle Pad's digital directions too) and only the C-stick
 * points; and they hold the C-stick from the camera (radial_stick_hold, radial_choices.h), renewed each frame.
 *
 * A choice is written to the save zone at once (radial_choose), which the wheel and its picture read each frame; the
 * screens show the choices as the wheel reads them (radial_choices), so a choice never made shows its default. The game's
 * own save carries them.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef short s16;

#include "radial_choices.h"

#define SLOTS 8
#define PAGE_ROWS 8             /* the big list's rows with an item's picture (FUN_0061ae20; ui020's two more have none) */
#define ROW_WHEEL 0             /* the menu level's rows, the switch first */
#define ROW_EDIT 1
#define ROW_TRIGGER 2
#define ROW_AUTOCRAFT 3
#define ROW_POSITION 4
#define ROW_SIZE 5
#define MENU_ROWS 6

#define KEY_UP 1
#define KEY_DOWN 2
#define KEY_LEFT 4
#define KEY_RIGHT 8
#define KEY_A 0x10
#define KEY_B 0x20
#define KEY_Y 0x80

#define NO_SLOT 0xFF            /* radial_menu_wheel's `marked`: no gold slot */
#define LAYOUT_HIDDEN 0         /* radial_menu_wheel's layouts */
#define LAYOUT_CENTRED 1
#define LAYOUT_SMALL 2

/* The pad object */
#define PAD_RAW 0x8C            /* u32: the raw buttons held; its D-pad bits are the D-pad's alone */
#define PAD_STICK_ANGLE 0x32E   /* u16 each: the C-stick's angle and magnitude */
#define PAD_STICK_MAGNITUDE 0x33A
#define RAW_DPAD_UP 0x10        /* the raw word's D-pad bits (the Circle Pad's digital directions are other bits) */
#define RAW_DPAD_RIGHT 0x20
#define RAW_DPAD_DOWN 0x40
#define RAW_DPAD_LEFT 0x80

#define SOUND_DECIDE 1          /* FUN_0031294c */
#define SOUND_CANCEL 2
#define SOUND_ERROR 3
#define SOUND_PAGE 7            /* the game's page turn in a big list */

/* The menu's object */
#define M_CONTEXT 0x5           /* u8: 1 in a quest, 2 in town */
#define M_POUCH 0x1D4           /* the pouch's places, set by FUN_005e7a24 */
#define CONTEXT_QUEST 1
#define POUCH_PLACES_TOWN 24    /* the town pouch */
#define POUCH_PLACES_QUEST 38   /* the quest pouch from here: its 32 items, 4 wystones and 2 more */

#define ITEM_LIMIT 0x790        /* from here an id names no item */
#define ITEM_BAR_FLAG 8         /* the item record's flag of what the item bar selects (FUN_005e5964) */


struct pouch_place {
    u16 item;
    s16 quantity;
};

struct radial_editor_data {     /* radial_editor.py editor_data */
    u16 directions[SLOTS];      /* the slots' directions: they fill the slot of slot_help */
    u16 slot_help, position_help, wheel_help, pouch_help;
    u16 position_values[POSITIONS];     /* 0 centre, 1 right, 2 bottom left */
    u16 wheel_values[2];        /* 0 off, 1 on */
    u16 size_help;
    u16 autocraft_help, trigger_help;
    u16 autocraft_values[2];    /* 0 off, 1 on */
    u16 trigger_values[TRIGGERS];       /* 0 Tilt, 1 Flick, 2 Release */
    u16 edit_slots, edit_help;  /* the Edit Slots row, its description and its levels' title */
    u16 size_values[MAX_SIZES]; /* the Size row's text at each size */
    u8 sizes;                   /* how many sizes there are (1 to MAX_SIZES) */
    u8 point;                   /* the least magnitude of a stick that points at a slot */
    u8 sector_to_slot[8];       /* the slot each of the stick's 8 sectors uses, as the wheel's use reads it */
};

_Static_assert(sizeof(struct radial_editor_data) == 80, "blocks.py RADIAL_EDITOR_DATA_SIZE, radial_editor.py");

enum { LEVEL_SLOTS, LEVEL_POUCH, LEVEL_MENU };

struct radial_editor_state {
    u16 title;                  /* the menu level's title, the row's */
    u8 level;
    u8 row;                     /* the cursor's slot, or the menu level's row */
    u8 pouch_row;
    u8 pouch_count;             /* the rows the pouch list has */
    u8 last_slot;               /* the slot last edited: Edit Slots opens on it (0 before any) */
    u8 reserved;
};

extern const struct radial_editor_data radial_editor_data;
extern struct radial_editor_state radial_editor_state;

extern void *sound_control;
extern u32 pad_control;                                         /* the variable holding the pad object */

int radial_choices(struct choices *out);                        /* radial_wheel.c: 0 without a save */
void radial_choose(u32 which, u32 value);
int item_flags(int any, int item, int mask);                    /* FUN_005e5964 */
int start_step(int value, int count, u32 keys, u32 minus, u32 plus);    /* FUN_005e70bc: wraps, with the move sound */
void sound_play(void *control, int sound);                      /* FUN_0031294c */

/* mod_settings.c */
void mod_list_open(void);
void mod_list_shown(int shown);
void mod_list_title(int message);
void mod_list_help(int message);
void mod_list_slot_help(int message, int text);
void mod_list_text(int row, int message);
void mod_list_item(int row, int item);
void mod_list_blank(int row);
void mod_list_placeholder(int row);
void mod_list_frame(int row_on_page, int page, int pages);
void mod_list_turned(int right);

static void play(int sound)
{
    sound_play(sound_control, sound);
}

static int pages_of(int rows)
{
    return rows == 0 ? 1 : (rows + PAGE_ROWS - 1) / PAGE_ROWS;
}

/* The row a page turn lands on: the same place of the next or previous page, or that page's last row */
static int turned_row(int row, int rows, int right)
{
    int pages = pages_of(rows);
    int page = row / PAGE_ROWS;
    int place = row % PAGE_ROWS;
    int first;

    if (right)
        page = page + 1 == pages ? 0 : page + 1;
    else
        page = page == 0 ? pages - 1 : page - 1;
    first = page * PAGE_ROWS;
    return first + place < rows ? first + place : rows - 1;
}

/* ---- the pouch */

static const struct pouch_place *pouch_places(const char *menu, int *places)
{
    *places = menu[M_CONTEXT] == CONTEXT_QUEST ? POUCH_PLACES_QUEST : POUCH_PLACES_TOWN;
    return *(const struct pouch_place *const *)(menu + M_POUCH);
}

static int offered(const struct pouch_place *place)
{
    return place->item != 0 && place->item < ITEM_LIMIT && place->quantity > 0 &&
           item_flags(0, place->item, ITEM_BAR_FLAG) != 0;
}

static int pouch_count(const char *menu)
{
    int places, count = 0, k;
    const struct pouch_place *place = pouch_places(menu, &places);

    if (place != 0)
        for (k = 0; k < places; k++)
            count += offered(&place[k]);
    return count;
}

/* The item of a row of the pouch list, 0 if it has none now: a menu open in a quest does not stop the game */
static int pouch_item(const char *menu, int row)
{
    int places, k;
    const struct pouch_place *place = pouch_places(menu, &places);

    if (place != 0)
        for (k = 0; k < places; k++)
            if (offered(&place[k]) && row-- == 0)
                return place[k].item;
    return 0;
}

/* What the pouch holds of an item, over all the places that hold it */
static int pouch_quantity(const char *menu, int item)
{
    int places, k, total = 0;
    const struct pouch_place *place = pouch_places(menu, &places);

    if (place != 0)
        for (k = 0; k < places; k++)
            if (offered(&place[k]) && place[k].item == item)
                total += place[k].quantity;
    return total;
}

static void draw_pouch_page(const char *menu)
{
    int first = radial_editor_state.pouch_row / PAGE_ROWS * PAGE_ROWS;
    int shown = 0;

    if (radial_editor_state.pouch_count == 0) {
        mod_list_placeholder(0);
        shown = 1;
    }
    for (; shown < PAGE_ROWS; shown++) {
        int item = first + shown < radial_editor_state.pouch_count ? pouch_item(menu, first + shown) : 0;

        if (item != 0)
            mod_list_item(shown, item);
        else
            mod_list_blank(shown);
    }
}

/* ---- the wheel's picture */

static const struct choices no_choices = {{0}, 0, 0, 0, 0, 0, 0};

/* The picture off the top screen: every way out of Edit Slots */
static void wheel_hide(void)
{
    radial_menu_wheel(&no_choices, LAYOUT_HIDDEN, NO_SLOT, 0, 0);
}

/* Once a frame at the two levels with the wheel: the centred wheel, or the small one previewing the pouch row */
static void wheel_frame(const char *menu, const struct choices *choices)
{
    int slot = radial_editor_state.row;

    if (radial_editor_state.level == LEVEL_SLOTS) {
        radial_menu_wheel(choices, LAYOUT_CENTRED, slot, 0, 0);
    } else if (radial_editor_state.level == LEVEL_POUCH) {
        int item = pouch_item(menu, radial_editor_state.pouch_row);

        radial_menu_wheel(choices, LAYOUT_SMALL, slot, item, item != 0 ? pouch_quantity(menu, item) : 0);
    }
}

/* ---- Edit Slots, the wheel level */

static void show_menu(int row);

static void show_slot_help(void)
{
    mod_list_slot_help(radial_editor_data.slot_help, radial_editor_data.directions[radial_editor_state.row]);
}

static void show_slots(void)
{
    radial_editor_state.level = LEVEL_SLOTS;
    mod_list_shown(0);
    mod_list_title(radial_editor_data.edit_slots);
    show_slot_help();
}

static void open_pouch(const char *menu)
{
    radial_editor_state.level = LEVEL_POUCH;
    radial_editor_state.pouch_row = 0;
    radial_editor_state.pouch_count = pouch_count(menu);
    mod_list_shown(1);
    mod_list_title(radial_editor_data.edit_slots);     /* the gold slot says which one is edited */
    draw_pouch_page(menu);
    mod_list_help(radial_editor_data.pouch_help);
}

/* The slot the C-stick points at, NO_SLOT when it is not out: its angle's sector as the wheel's use reads it
 * (radial_wheel.c). The Circle Pad walks the hunter in a quest and points at nothing. */
static int pointed_slot(void)
{
    u32 pad = pad_control, angle, magnitude;

    if (pad == 0)
        return NO_SLOT;
    angle = *(const u16 *)(pad + PAD_STICK_ANGLE);
    magnitude = *(const u16 *)(pad + PAD_STICK_MAGNITUDE);
    if (magnitude < radial_editor_data.point)
        return NO_SLOT;
    return radial_editor_data.sector_to_slot[((angle + 0x1000) >> 13) & 7] & 7;
}

/* The menu's words with only the D-pad's own directions: the words the game's lists read (+0x558, +0x56C) carry the
 * Circle Pad's digital directions as well, which would turn the wheel's cursor or walk the pouch list while the hunter
 * walks; the pad object's raw word has a bit of the D-pad alone for each direction */
static u32 dpad_keys(u32 keys)
{
    u32 raw = pad_control != 0 ? *(const u32 *)(pad_control + PAD_RAW) : 0;

    return keys & (((raw & RAW_DPAD_UP) ? KEY_UP : 0) | ((raw & RAW_DPAD_DOWN) ? KEY_DOWN : 0) |
                   ((raw & RAW_DPAD_LEFT) ? KEY_LEFT : 0) | ((raw & RAW_DPAD_RIGHT) ? KEY_RIGHT : 0));
}

static void slots_frame(const char *menu, struct choices *choices, u32 pressed, u32 keys)
{
    int slot = radial_editor_state.row, pointed;
    u32 turns = dpad_keys(keys) & (KEY_LEFT | KEY_RIGHT);

    if (pressed & KEY_B) {          /* back to the menu level on Edit Slots, the wheel off the top screen */
        play(SOUND_CANCEL);
        wheel_hide();
        show_menu(ROW_EDIT);
    } else if (pressed & KEY_A) {
        play(SOUND_DECIDE);
        open_pouch(menu);
    } else if (pressed & KEY_Y) {
        play(SOUND_DECIDE);
        radial_choose(slot, 0);
        radial_choices(choices);
        radial_editor_state.last_slot = slot;
    } else {
        pointed = pointed_slot();
        if (turns)
            slot = start_step(slot, SLOTS, turns, KEY_LEFT, KEY_RIGHT);
        else if (pointed != NO_SLOT)
            slot = pointed;
        if (slot != radial_editor_state.row) {
            radial_editor_state.row = slot;
            show_slot_help();
        }
    }
}

/* ---- the menu level */

static void draw_values(const struct choices *choices)
{
    mod_list_text(ROW_WHEEL, radial_editor_data.wheel_values[choices->enabled != 0]);
    mod_list_text(ROW_EDIT, radial_editor_data.edit_slots);
    mod_list_text(ROW_TRIGGER, radial_editor_data.trigger_values[choices->trigger < TRIGGERS ? choices->trigger : 0]);
    mod_list_text(ROW_AUTOCRAFT, radial_editor_data.autocraft_values[choices->autocraft != 0]);
    mod_list_text(ROW_POSITION, radial_editor_data.position_values[choices->position < POSITIONS ? choices->position : 0]);
    mod_list_text(ROW_SIZE, radial_editor_data.size_values[choices->size < MAX_SIZES ? choices->size : 0]);
}

static void show_menu_help(void)
{
    int row = radial_editor_state.row;
    mod_list_help(row == ROW_WHEEL       ? radial_editor_data.wheel_help
                  : row == ROW_EDIT      ? radial_editor_data.edit_help
                  : row == ROW_TRIGGER   ? radial_editor_data.trigger_help
                  : row == ROW_AUTOCRAFT ? radial_editor_data.autocraft_help
                  : row == ROW_POSITION  ? radial_editor_data.position_help
                                         : radial_editor_data.size_help);
}

/* The menu level with its cursor on `row` (the list shown again after Edit Slots hid it) */
static void show_menu(int row)
{
    struct choices choices;
    int blank;

    radial_choices(&choices);
    radial_editor_state.level = LEVEL_MENU;
    radial_editor_state.row = row;
    mod_list_shown(1);
    mod_list_title(radial_editor_state.title);
    draw_values(&choices);
    for (blank = MENU_ROWS; blank < PAGE_ROWS; blank++)
        mod_list_blank(blank);
    show_menu_help();
}

/* 1 when B leaves the screen */
static int menu_frame(struct choices *choices, u32 pressed, u32 keys)
{
    int row = radial_editor_state.row;

    if (pressed & KEY_B)
        return 1;
    if (pressed & KEY_A) {
        play(SOUND_DECIDE);
        if (row == ROW_EDIT) {
            radial_editor_state.row = radial_editor_state.last_slot < SLOTS ? radial_editor_state.last_slot : 0;
            show_slots();
            return 0;
        }
        if (row == ROW_WHEEL)
            radial_choose(CHOOSE_ENABLED, !choices->enabled);
        else if (row == ROW_TRIGGER)
            radial_choose(CHOOSE_TRIGGER, choices->trigger + 1u < TRIGGERS ? choices->trigger + 1u : 0);
        else if (row == ROW_AUTOCRAFT)
            radial_choose(CHOOSE_AUTOCRAFT, !choices->autocraft);
        else if (row == ROW_POSITION)
            radial_choose(CHOOSE_POSITION, choices->position + 1u < POSITIONS ? choices->position + 1u : 0);
        else
            radial_choose(CHOOSE_SIZE, choices->size + 1u < radial_editor_data.sizes ? choices->size + 1u : 0);
        radial_choices(choices);
        draw_values(choices);
    } else if (keys & (KEY_UP | KEY_DOWN)) {
        radial_editor_state.row = start_step(row, MENU_ROWS, keys, KEY_UP, KEY_DOWN);
        show_menu_help();
    }
    return 0;
}

/* ---- the pouch list's frame, and the screens' */

static void pouch_frame(const char *menu, struct choices *choices, u32 pressed, u32 keys)
{
    int row = radial_editor_state.pouch_row;
    int count = radial_editor_state.pouch_count;
    int slot = radial_editor_state.row;

    keys = dpad_keys(keys);
    if (pressed & KEY_B) {
        play(SOUND_CANCEL);
        show_slots();
    } else if (pressed & KEY_Y) {
        play(SOUND_DECIDE);
        radial_choose(slot, 0);
        radial_choices(choices);
        radial_editor_state.last_slot = slot;
        show_slots();
    } else if (pressed & KEY_A) {
        int item = pouch_item(menu, row);

        if (count == 0 || item == 0) {
            play(SOUND_ERROR);
        } else {
            play(SOUND_DECIDE);
            radial_choose(slot, item);
            radial_choices(choices);
            radial_editor_state.last_slot = slot;
            show_slots();
        }
    } else if (count > 1 && (keys & (KEY_UP | KEY_DOWN))) {
        int page = row / PAGE_ROWS;

        row = start_step(row, count, keys, KEY_UP, KEY_DOWN);
        radial_editor_state.pouch_row = row;
        if (row / PAGE_ROWS != page)
            draw_pouch_page(menu);
    } else if (count > PAGE_ROWS && (keys & (KEY_LEFT | KEY_RIGHT))) {
        play(SOUND_PAGE);
        mod_list_turned((keys & KEY_RIGHT) != 0);
        radial_editor_state.pouch_row = turned_row(row, count, (keys & KEY_RIGHT) != 0);
        draw_pouch_page(menu);
    }
}

/* What the big list needs each frame: not at the wheel level, where it is hidden */
static void widget_frame(void)
{
    if (radial_editor_state.level == LEVEL_POUCH)
        mod_list_frame(radial_editor_state.pouch_row % PAGE_ROWS, radial_editor_state.pouch_row / PAGE_ROWS,
                       pages_of(radial_editor_state.pouch_count));
    else if (radial_editor_state.level == LEVEL_MENU)
        mod_list_frame(radial_editor_state.row, 0, 1);
}

/* A on the Radial Menu row: 0 without a save, and nothing has opened */
int radial_editor_open(int title)
{
    struct choices choices;

    if (!radial_choices(&choices))
        return 0;
    mod_list_open();
    radial_editor_state.title = title;
    show_menu(ROW_WHEEL);
    widget_frame();
    return 1;
}

/* The menu closes, START or forced, with an Edit Slots level open: the wheel goes off the top screen and the camera has
 * the C-stick back (mod_menu_closed) */
void radial_editor_leave(void)
{
    radial_stick_hold = 0;
    if (radial_editor_state.level != LEVEL_MENU)
        wheel_hide();
}

/* Each frame of the screen: 1 goes back to the small list */
int radial_editor_frame(char *menu, u32 pressed, u32 keys)
{
    struct choices choices;

    if (!radial_choices(&choices)) {
        radial_editor_leave();
        return 1;
    }
    if (radial_editor_state.level == LEVEL_POUCH)
        pouch_frame(menu, &choices, pressed, keys);
    else if (radial_editor_state.level == LEVEL_SLOTS)
        slots_frame(menu, &choices, pressed, keys);
    else if (menu_frame(&choices, pressed, keys)) {
        radial_stick_hold = 0;
        return 1;
    }
    radial_stick_hold = radial_editor_state.level == LEVEL_MENU ? 0 : STICK_HOLD;
    widget_frame();
    wheel_frame(menu, &choices);
    return 0;
}
