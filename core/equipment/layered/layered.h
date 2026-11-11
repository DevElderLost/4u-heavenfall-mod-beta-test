/* Layered gear: what the units of the block layered_selector share (layered_selector.c, layered_forge.c, felyne_looks.c):
 * the variables, the data blocks and the game's calls more than one of them makes. */

#ifndef LAYERED_H
#define LAYERED_H

#include "felyne_looks.h"

#define GAME __attribute__((long_call))
#define ARM __attribute__((target("arm"), noinline))
#define STR2(x) #x
#define STR(x) STR2(x)

#include "../../interface/screen_kit/screen_kit.h"

/* ----- the game's calls --------------------------------------------------------------------------------- */

GAME void facility_menu_set(u32 obj, u32 menu, u32 row, u32 bright);   /* FUN_00a1ea8c */
GAME void facility_help(u32 kind, u32 file, u32 message);              /* FUN_00298560 */
GAME void sound_play(u32 manager, u32 sound);                          /* FUN_0031294c */
/* FUN_0010ed68, the game's word copy: ldm / stm with no alignment handling, so `dst` and `src` must be on a word (a real
   3DS faults otherwise; the emulators do not). Called only in place of the game's own call, with its arguments; every
   other copy goes through layered_copy. */
GAME void mem_copy(void *dst, const void *src, u32 size);
GAME void preview_frame_close(u32 frame);                              /* FUN_0059f680 */
GAME void text_slot(u32 slot, const u16 *text, u32 length);            /* FUN_005a99a8 */
GAME void text_lobby(void *ref, u32 file, u32 message);                /* FUN_005a882c */

extern u32 sound_control;
extern const u8 *game_control;
extern u32 save_control;           /* the variable holding the save object; its data starts SAVE_DATA in */
extern u32 equipment_control;
extern u32 preview_hunter;
extern u8 lobby_hunter_loader[];

#define SAVE_DATA 0x5C
#define MAKESHOP 6               /* E_makeshop among the lobby's message files */
#define COMMON 0x100             /* a common message file (layered_text_kind) */
#define LAYERED_STATE 3          /* the Smithy's state the screens run in */
#define LAYERED_MENU 18          /* the facility menu the block adds: its lines are layered_ui.lines */
#define NO_MENU 0xFF             /* facility_menu_set: FUN_00a0a708 hides ui401's own groups */
#define NO_ARMOR 0xFFFE          /* an armor value of layered_state that is no model: the part is drawn as armor id 0
                                    (equipment/layered/layered_equipment.py NO_ARMOR) */
#define OBJ_HUNTER 0xB960        /* the facility object's real hunter, and the preview hunter */
#define OBJ_PREVIEW 0xB964
#define OBJ_FRAME 0x104E8        /* the preview's frame widget */
#define OBJ_MENU 0x98CC          /* the facility menu to show: menu, row, bright lines */
#define OBJ_SHOWN 0x9A7C         /* the menu drawn; another value redraws it */
#define HUNTER_STATUS 0xE30      /* hunter -> its status: +0x30 kind, +0x33 player index, records below */
#define ST_ARMOR 0x70            /* 5 armor records: body, arms, waist, legs, head */
#define ST_WEAPON 0x1C0
#define RECORD 0x1C
#define WEAPON_TYPE 7            /* equipment type of the first weapon class */
#define CLASSES 14

#define BUTTON_X 0x4000           /* FUN_00694ccc's table at 0xFB8140: the X button's only bit */
#define BUTTON_Y 0x2080
#define BUTTON_L 0x100
#define BUTTON_R 0x200
#define BUTTON_A 0x10
#define BUTTON_B 0x20
#define BUTTON_START 0x40
#define DIR_UP 1
#define DIR_DOWN 2
#define DIR_LEFT 4
#define DIR_RIGHT 8
#define SOUND_DECIDE 1
#define SOUND_CANCEL 2
#define SOUND_ERROR 3
#define SOUND_CURSOR 4
#define SOUND_DONE 6
#define SOUND_PAGE 7
#define SOUND_PAY 10

/* ----- the variables ------------------------------------------------------------------------------------ */

struct cursor {                  /* FUN_009bc954 / FUN_009bc9b4 */
    u8 col, row, cols, rows;
    u16 index, pad;
    u32 a_sound, v_sound, h_sound, disabled;
};

struct layered_state {           /* the contract with the render hook */
    u8 enabled, reserved;
    u16 armor[5][2];             /* equipment type - 1: body, arms, waist, legs, head; male, female model */
    u16 weapon[CLASSES];         /* equipment type - 7 */
    u16 dye[5];                  /* the colour of each part's look: DYE_OWN, else RGB565 (an equipment reference's +4) */
};
#define DYE_OWN 0                /* a dye: the look's own colour */
#define DYE_BLACK 1              /* pure black (RGB565 0) as a dye holds it: blue's lowest step */

enum { ENTRY, CLASSES_MENU, CATS, FORGE, RELICS };   /* layered_ui.level */
enum { M_ARMOR, M_WEAPON, M_FELYNE };         /* layered_ui.mode, on FORGE */
enum { F_LIST, F_PROMPT, F_SCENE_START, F_SCENE, F_CAMERA, F_EQUIP, F_DYE };   /* layered_ui.sub, on FORGE */
enum { FOCUS_ROW, FOCUS_GAME, FOCUS_RANK };   /* layered_ui.focus: the list, or one of the filters */
enum { RANK_LOW, RANK_HIGH, RANK_G, RANK_ALL, RANK_VALUES };   /* layered_ui.rank */
#define RANKS 3
#define UNLOCK_ROOM 4            /* layered_rules.py: entries per rank of struct rules' unlock */
#define UNLOCK_FLAG 0x8000       /* an unlock entry with this bit is a story flag, else a quest id */
#define UNLOCK_OPEN 0xFFFF       /* an unlock entry that always holds (layered_rules.py; layered_by_rank off) */
enum { GAME_MH4U, GAME_GEN, GAME_ALL, GAME_VALUES };           /* layered_ui.game */

/* The colour window of the Armor screen (layered_forge.c, "the colour window"): its whole state. It lives in the room
   of struct ui's two strings, which nothing draws while the window is on (bss_tail has no room for more). */
struct dye_window {
    u8 target, row, col, picking;   /* the target: 0 the whole set, else the armor row's button; the cursor's row and
                                       column; non-zero while the scale's point moves (A on the scale) */
    u8 x, y, held, pad;          /* the scale's point; the frames a direction has been held since it was pressed */
    u16 colour, pad2;            /* what the cursor's cell gives, as a dye */
    u16 before[5];               /* layered_preview.state.dye when the window opened */
};

struct ui {                      /* the variable layered_ui: a screen's whole state, as nothing is cached */
    u8 level, mode, sub, class_index;
    u8 smithy_menu, smithy_row, rank, game;
    u8 focus, button, count, box_cut;   /* the game's box: bit 0 cut, from bit 1 which of its last lines were on */
    u16 grey;                    /* bit rank * GAME_VALUES + game: that filter pair has no row */
    u16 index, top, total;       /* the cursor's and the first shown row, among the rows of the filter pair; how many */
    struct cursor cursor;        /* of the entry list, the classes and the cats */
    u16 lines[4][2];             /* (file, message) of menu 18 */
    union {
        struct {
            u16 counter_text[8]; /* "999/999": the string slot keeps its address */
            u16 price_text[8];   /* a price's six digits at most (kit_number_text, layered_rules.py MAX_ZENNY) */
        };
        struct dye_window dye;   /* while the colour window is on (F_DYE), which draws neither string */
    };
    u8 unlocked;                 /* the highest rank open (RANK_LOW, RANK_HIGH, RANK_G): set when a screen opens */
    u8 hover;                    /* the frames the cursor has rested on a weapon's row, up to the preview's wait */
    u16 held;                    /* the frames up or down has been held since it was pressed */
    u8 relics, pad[3];           /* non-zero from the entry's Relics line on: its screens list the relics alone */
};
#define UI_LEVEL 0
#define UI_COUNT 0xA
#define UI_LINES 0x2C
_Static_assert(__builtin_offsetof(struct ui, level) == UI_LEVEL, "UI_LEVEL");
_Static_assert(__builtin_offsetof(struct ui, count) == UI_COUNT, "UI_COUNT");
_Static_assert(__builtin_offsetof(struct ui, lines) == UI_LINES, "UI_LINES");
_Static_assert(sizeof(struct ui) == 0x64, "layered_ui size (game/executable/blocks.py)");
_Static_assert(sizeof(struct dye_window) <= 2 * 8 * sizeof(u16) && __builtin_offsetof(struct ui, dye) == 0x3C,
               "the colour window: in the strings' room (test_layered_dye_window.py UI_DYE)");
_Static_assert(__builtin_offsetof(struct ui, hover) == 0x5D && __builtin_offsetof(struct ui, held) == 0x5E,
               "test_layered_forge_cursor.py UI_HOVER, UI_HELD");
_Static_assert(__builtin_offsetof(struct ui, relics) == 0x60, "test_layered_selector_run.py ui()");
_Static_assert(__builtin_offsetof(struct layered_state, weapon) == 0x16
               && __builtin_offsetof(struct layered_state, dye) == 0x32 && sizeof(struct layered_state) == 0x3C,
               "layered_state: the contract (0x3C bytes, weapon at +0x16, dye at +0x32)");

struct preview {                 /* the variable layered_preview */
    u32 status, part;            /* noted by the model stubs for layered_*_model */
    u8 active, pad1;             /* the preview hunter wears `state` */
    u16 pushed;                  /* 1: the model must be reloaded once the last load has ended */
    u32 loader;                  /* the quest preloader, noted by its stubs */
    struct layered_state state;  /* what the preview hunter wears: the looks worn and the try-ons, their colours */
    union {
        u8 record[RECORD];       /* the weapon the preview hunter holds */
        u32 cat_numbers;         /* what the preview cat wears: the look word's numbers */
    } on;
};
#define P_STATUS 0
#define P_PART 4
#define P_LOADER 0xC
_Static_assert(__builtin_offsetof(struct preview, part) == P_PART, "P_PART");

_Static_assert(__builtin_offsetof(struct preview, loader) == P_LOADER, "P_LOADER");
_Static_assert(sizeof(struct preview) == 0x68 && __builtin_offsetof(struct preview, state) == 0x10,
               "layered_preview size (game/executable/blocks.py)");

extern struct layered_state layered_state;
extern struct ui layered_ui;
extern struct preview layered_preview;
extern u32 screens_open;         /* non-zero while a forge-style screen is on: single_screen.py HELP_FLAGS */

/* ----- the looks the other players wear (layered_online.c) ------ */

#define REMOTE_ENTRIES 4
#define REMOTE_USED 0x80         /* an entry's flags: bit 7 set when the entry holds a hunter (bits 0-2 as on the wire) */
#define REMOTE_LOOKS 1           /* flags bit 0: the hunter wears its looks */
#define REMOTE_CAT 2             /* bit 1: `cat` is valid */
#define REMOTE_KNOWN 4           /* bit 2 (kept apart from the wire's): this build has every look the hunter wears */
struct layered_remote_entry {    /* what one hunter last sent */
    u8 id[8];                    /* the hunter's id, as in the player info (+0x187) */
    u16 armor[5];                /* the models of its gender, in layered_state order (0 none, NO_ARMOR) */
    u8 weapon[CLASSES];          /* the model of each class (0 none) */
    u8 cat[4];                   /* the Felyne look word, little endian (valid when REMOTE_CAT) */
    u8 flags, gender, seq;
    u8 changed;                  /* grows each time the looks change: the render re-dresses the hunter when it moves */
    u8 cat_changed, pad;         /* grows each time the cat's word (or its validity) changes: the cat is dressed again */
    u16 dye[5];                  /* the colours of its looks (layered_state.dye; 0 from a sender of an earlier build) */
};
_Static_assert(sizeof(struct layered_remote_entry) == 52, "layered_remote entry (game/executable/blocks.py)");
/* The looks of the member in session slot `slot`, or 0: nothing heard, looks off, the member gone, or a look this build
   lacks (the hunter then shows all of its real gear). The entry's `id` is for the render to compare with the info's
   +0x187: a mismatch is a stale entry (no looks). */
const struct layered_remote_entry *layered_remote_by_slot(u32 slot);
/* What the render reads (layered_online.c). Each fills `out` (the getters' own shape: the sender's gender column only)
   and returns it, or returns 0: the hunter shows its real gear. */
const struct layered_state *layered_hall_looks(const u8 *status, struct layered_state *out);   /* a remote hall hunter */
const struct layered_state *layered_quest_looks(u32 player, struct layered_state *out);       /* the quest's snapshot */
int known_armor(u32 part, u32 female, u32 model);     /* layered_selector.c: is it a look this build has */
int known_weapon(u32 index, u32 model);
/* The Felyne look word of the member in session slot `slot` (the mark included), or 0: no cat look, a look this build lacks,
   the member gone or another hunter's entry. Judged apart from the hunter's looks. */
u32 layered_remote_cat(u32 slot);
/* The word the cat of the compact record `compact` (a session member's: S + slot * 0x208 + 0x8980) is to wear, or 0. */
u32 layered_cat_of_compact(const u8 *compact);
/* The word of the other player's cat in the quest's snapshot, if `owner` (a player index) is that player; else 0. */
u32 layered_quest_cat(u32 owner);
/* The screens are left (layered_selector.c back()): tell the other players when the looks changed. */
void layered_net_state_left(void);
/* The preview hunter takes the colours of layered_preview.state again, at once (layered_selector.c; colours only, no
   model is loaded). The game puts every hunter's colours on again each frame anyway: this saves that frame. */
void layered_dye_refresh(void);

/* ----- the block layered_data (equipment/layered/layered_equipment.py) ------------------------------------- */

#define SET_WHOLE 1              /* a set's flags: bit 0 worn as a whole (2 parts or more), bits 1-2 its rank (1-3) */
#define SET_RANK_SHIFT 1
struct set { u16 male, female, message; u8 parts, flags; };
struct parts { u16 models[5][2]; };                 /* an XX set's models per part */
struct weapon { u16 model, name, id; u8 rank, pad; };
_Static_assert(sizeof(struct set) == 8 && sizeof(struct parts) == 20 && sizeof(struct weapon) == 8, "records");
struct catalog {                 /* one game's looks (layered_equipment.py, CATALOG) */
    u32 sets_offset, parts_offset, weapon_offset[CLASSES];   /* parts_offset 0: a set has one model pair for all */
    u16 weapon_count[CLASSES], set_count;
    u16 colours_offset;          /* the sets' own colours, a byte per set (below); 0: none */
};
/* A set's byte: below struct data's palette_count, the palette entry of every part and gender; from there on, the
   struct colours (byte - palette_count) after the palette; NO_COLOUR, none known (the real piece's colour shows). */
#define NO_COLOUR 0xFF
struct colours { u8 entry[5][2]; };                 /* a set whose parts or genders differ: a palette entry each */

/* The numbers of a screen (equipment/layered/menu_layout.py, forge_screen_data): all from the curated `forge_screen`. */
struct fg_mode {
    u8 rows, pitch, first_y, name_dy;
    u16 name_x;
    u8 name_w, name_h;
    u8 buttons, button_pitch, button_dy, pad;
    u16 button_x, pad2;
};
struct fg_rect { u16 x, y, w, h; };
/* The panes the code moves, in forge_screen.hashes (menu_layout.py, pane_hashes). */
#define H_ROW 0                  /* 3 per row, 9 rows */
#define H_NAME 27                /* 1 per row */
#define H_BUTTON 36              /* 3 per button: plate, icon, mark; 6 buttons on rows 0-4, 1 on rows 5-8 */
#define H_SELECTED 138           /* 2: behind the chosen value of each filter */
#define H_FILTER 140             /* the rank row's words, then the game row's */
#define H_CURSOR 147             /* the row's bar: 3; the button's bracket: 2 */
#define H_HINT 152
#define H_COUNT 153
#define H_CUE 154                /* START's cue: the plate, the key, the word */
#define H_TRY_ON 157             /* the buttons' try-on marks, one per button, in the order of the buttons */
#define H_BOX_GROUPS 191         /* the game's materials box (ui402): its 5 root groups, frame and title first */
#define H_BOX_FRAME 196          /* 4 */
#define H_BOX_LINES 200          /* 5 */
#define H_BOX_TITLE 205          /* 2 */
#define H_BOX_ROWS 207           /* 4 per row, 3 rows: icon, count box, name, count */
#define FORGE_HASHES 219
/* The colour window's panes, in forge_screen.dye.hashes (menu_layout.py, dye_pane_names). */
#define DH_TARGET 0              /* 3 per target: plate, icon, swatch */
#define DH_TITLE 18
#define DH_CHIP 19
#define DH_DEFAULT 31            /* the plate, the word */
#define DH_FRAME 33
#define DH_SCALE 34
#define DH_POINT 35
#define DH_CURSOR 36             /* 2 halves */
#define DH_KEYS 38               /* L, R */
#define DH_SELECT 40             /* SELECT's cue: the plate, the key's left end, middle and right end, its word, "Color" */
#define DYE_HASHES 46
#define DYE_TARGETS 6            /* the whole set and the armor row's five pieces */
#define DYE_CHIPS 12             /* the pigment's palette (FUN_00c0e3c8) */
#define HOLD_STEPS 4             /* menu_layout.py HOLD_STEPS */
struct fg_dye {                  /* the colour window's numbers (menu_layout.py, DYE_SCREEN): from the curated `dye` */
    u32 group;                   /* ui401_fg_dye's hash */
    u16 priority, columns;       /* its priority; the chips of a row */
    struct fg_rect title, deflt, deflt_text, scale, keys[2];
    struct fg_rect cue[6];       /* SELECT's cue on the Armor list, as DH_SELECT (the key's three pieces never drawn) */
    struct fg_rect start_cue[3]; /* START's cue on the Armor list (above SELECT's): the plate, the key, the word */
    u16 target_x, target_y, target_pitch, swatch_dx, swatch_dy, swatch_w, swatch_h;
    u16 chip_x, chip_y, chip_dx, chip_dy, chip_w, chip_h;
    u16 range_x, range_y, start_x, start_y, cursor_w, cursor_h;   /* the scale's point: 0..range, where it starts */
    short bracket[4];            /* the cursor around a cell: dx, dy, dw, dh, in two halves */
    u16 steps[HOLD_STEPS][2];    /* a direction held on the scale: from [0] frames on, [1] units a step */
    u16 msg_keys, msg_select;    /* E_makeshop: the window's key bar, the word on SELECT's key */
    u32 key_word;                /* the colour of that word */
    u32 hashes[DYE_HASHES];
};
enum { C_MODEL, C_CHOSEN, C_FILTER, C_GREY, C_BOUGHT, C_NOT_BOUGHT, C_KEY_BAR, C_MARK, C_PLATE, C_DISABLED_PLATE,
       C_DISABLED_ICON, C_NOT_OWNED_ICON, FORGE_COLOURS };
struct forge_screen {
    u32 groups[6];               /* left, right, rows, keys, cursor, START's cue: the names' hashes */
    u8 priority[6], pad0[2];
    int camera[4];               /* the preview camera's rectangle: left, top, right, bottom */
    struct fg_mode modes[3];
    struct fg_rect filters[2][RANK_VALUES];   /* rank, game: the game row has one value less */
    u16 piece_x[3], piece_w[3];  /* the three pieces of a row's background, and of the cursor's bar */
    u16 bar_y[2], bar_h, selected_h;
    u8 plate_w, plate_h, icon_dx, icon_dy, mark_dx, mark_dy, icon_w, icon_h;
    signed char bracket[4];      /* from the plate: x, y of the bracket's two pieces */
    u8 bracket_w, bracket_h;
    u32 colours[FORGE_COLOURS];  /* as the panes hold them: R in the low byte */
    u8 armor_icons[6], felyne_icons[4], weapon_icons[CLASSES], mark_icon, pad4[3];
    u32 disabled_u, disabled_v;  /* the icon sheet's cell of a disabled button: floats */
    u8 try_on_dx, try_on_dy, try_on_w, try_on_h;   /* the try-on mark, from the plate */
    u16 box_cut;                 /* how much shorter the game's materials box is, in layout units; */
    u16 price_widen;             /* how much wider its price row's count is */
    int camera_full[4];          /* the camera mode's rectangle: the game's frame */
    struct fg_rect cue[2][3];    /* START's cue on the list and in the camera mode: the plate, the key, the word */
    u16 hold[HOLD_STEPS][2];     /* up or down held: from [0] frames on, [1] rows a step; 0 frames ends the steps */
    u16 preview_frames, pad5;    /* the frames on a weapon's row before the model shows its look */
    u32 hashes[FORGE_HASHES];
    struct fg_dye dye;
};
_Static_assert(sizeof(struct fg_mode) == 16, "menu_layout.py ROWS_RECORD");
_Static_assert(sizeof(struct fg_dye) == 200 + 4 * DYE_HASHES, "menu_layout.py DYE_SCREEN");
_Static_assert(sizeof(struct forge_screen) == 372 + 4 * FORGE_HASHES + sizeof(struct fg_dye), "menu_layout.py FORGE_SCREEN");

struct data {                    /* the block layered_data (layered_equipment.py, HEADER) */
    u32 magic;
    struct catalog catalogs[2];  /* MH4U's, XX's (empty without its pack) */
    u16 msg_desc, msg_blank, msg_counter, msg_weapons;
    u8 chooser_weapons[CLASSES];
    u16 msg_row_weapons;         /* the weapons' key bar: no Y there */
    u8 menu_icons[38], menu_text[19];
    u8 palette_count;            /* the palette's colours; the struct colours records follow them */
    u16 palette;                 /* the offset of the sets' colours: RGB, 3 bytes each */
    struct forge_screen screen;
};
#define DATA_MSG_DESC 0xC4
_Static_assert(__builtin_offsetof(struct data, msg_desc) == DATA_MSG_DESC, "DATA_MSG_DESC");
_Static_assert(__builtin_offsetof(struct data, palette_count) == 0x115 && __builtin_offsetof(struct data, palette) == 0x116
               && sizeof(struct colours) == 10,
               "layered_equipment.py HEADER, COLOUR_RECORD");
_Static_assert(__builtin_offsetof(struct data, menu_icons) == 0xDC && __builtin_offsetof(struct data, screen) == 0x118,
               "layered_equipment.py HEADER");
/* Both data blocks start 4-aligned (blocks.py BlockSpec.align): word and halfword fields are read whole, not by bytes. */
extern const u8 layered_data[] __attribute__((aligned(4)));
#define D ((const struct data *)layered_data)

/* ----- the block layered_rules (equipment/layered/layered_rules.py) ---------------------------------------- */

#define RULE_ALWAYS 0xFFFF       /* a condition word: the list holds */
#define RULE_GEAR 0x8000         /* the low 15 bits: a bit of "had it once", as FUN_00c1fe40 reads it */
#define RULE_MALE 0x4000         /* else an item in bits 0-12, which counts for that gender only */
#define RULE_FEMALE 0x2000
#define RULE_ITEM 0x1FFF
struct recipe { struct { u16 item, quantity; } materials[4]; };   /* *(obj + 0xB8FC) takes it directly; the zenny is
                                                                     the look's own (struct rules' *_zenny) */
struct felyne_row { u16 number, message; u8 parts, rank, game, pad; };    /* game: 0 MH4U, 1 Generations (a filter's) */
enum { MSG_RANK_LOW, MSG_RANK_HIGH, MSG_RANK_G, MSG_GAME_MH4U, MSG_GAME_GEN, MSG_GAME_ALL, MSG_ARMOR, MSG_HELP_WEAPONS,
       MSG_HELP_ARMOR, MSG_HELP_FELYNE, MSG_HELP_ROW, MSG_HELP_FILTER, RULE_MESSAGES };
struct rules {
    u32 magic;
    u32 armor_rules[2];                  /* parallel to each catalog's sets */
    u32 weapon_rules[2][CLASSES];        /* parallel to each catalog's weapons of the class */
    u32 armor_recipes[2];                /* u16 indexes into `recipes`, in the same order */
    u32 weapon_recipes[2][CLASSES];
    u32 felyne_rows, felyne_rules, felyne_recipes, conds, recipes;
    u16 armor_count[2], weapon_count[2][CLASSES], rows_count, recipes_count, conds_count, pad;
    u32 zone_at;                         /* the owned bits, in the game's data; the zones in it: */
    u16 zone_armor[2], zone_weapons[CLASSES], zone_felyne, zone_size;
    u16 messages[RULE_MESSAGES];
    u16 unlock[RANKS - 1][UNLOCK_ROOM];  /* what opens rank 2 (high), rank 3 (G): quests, UNLOCK_FLAG story flags; 0 ends */
    u32 armor_zenny[2];                  /* u32 zenny of each look, parallel to the rules (layered_rules.py, zenny.py) */
    u32 weapon_zenny[2][CLASSES];
    u32 felyne_zenny;
    u32 armor_order;                     /* the lists' order (look_order.py): u16 entries, a position over both */
    u32 weapon_order[CLASSES];           /* catalogs (look_at's), ORDER_EVERY: under every rank and game filter */
    u32 felyne_order;
    u32 armor_bits[2];                   /* u16 owned bit of each armor look, parallel to the rules: a model, never a
                                            place (layered_rules.py armor_bits) */
    u16 zone_format_at, zone_format;     /* the zone's format byte: where in it, and what each purchase writes there */
    u16 msg_relics, msg_help_relics;     /* E_makeshop: the entry's Relics line, its help */
};
#define ORDER_EVERY 0x8000
#define ORDER_RELIC 0x4000       /* a relic: on the Relics screens (layered_ui.relics) and no other */
#define ORDER_POSITION 0x3FFF
_Static_assert(__builtin_offsetof(struct rules, zone_at) == 332, "layered_rules.py HEADER");
_Static_assert(__builtin_offsetof(struct rules, messages) == 372, "layered_rules.py HEADER");
_Static_assert(__builtin_offsetof(struct rules, unlock) == 396 && __builtin_offsetof(struct rules, armor_bits) == 600
               && sizeof(struct rules) == 616, "layered_rules.py HEADER");
_Static_assert(sizeof(struct recipe) == 16 && sizeof(struct felyne_row) == 8, "records");
extern const u8 layered_rules[] __attribute__((aligned(4)));
#define R ((const struct rules *)layered_rules)

/* ----- layered_selector.c <-> layered_forge.c --------------------------------------------------------------- */

/* A lobby hunter puts its pieces on again (as FUN_0065e31c does), so the getters run with the looks of now. */
void hunter_reload(u32 hunter, const u8 *weapon);
/* a / b for the small numbers here: the ARM11 has no divide instruction and no library is linked. */
u32 small_divide(u32 a, u32 b);
void layered_clear(void *at, u32 size);
/* A byte copy, for addresses that need not be on a word (mem_copy needs them there). */
void layered_copy(void *to, const void *from, u32 size);
/* The screens: `mode`'s opens in the Smithy's state 3 (1 if it did); every frame, and the key presses, while on FORGE. */
int forge_open(u32 obj, u32 mode);
void forge_update(u32 obj);
/* The level to go back to has just been shown again (layered_selector.c): the screen is closed. */
void forge_back_to_menu(u32 obj);
u32 help_message(void);

static inline void play(u32 sound)
{
    sound_play(sound_control, sound);
}

#endif
