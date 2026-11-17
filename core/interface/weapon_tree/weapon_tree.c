/* The Smithy's weapon tree (option weapon_tree): a weapon class chosen in Forge Weapons
 * opens one tree of the class's weapons instead of the game's list, and so does a box weapon chosen in Upgrade: the tree
 * is drawn and moved through, with the game's stats panel and materials box for the weapon under the cursor; A forges
 * or upgrades it as the game does (a weapon with both ways first asks which, in a window whose cursor the materials
 * shown follow), X goes round the forge's views (stats, try on, compare), L / R turn the stats view's page.
 *
 * Hooks (ARM, at the end of this file; interface/weapon_tree/weapon_tree.py points the game at them):
 *   weapon_tree_entry          0x9ADCCC  "b 0x9ADC1C" of FUN_009ad59c's state 2, A on a weapon class (the class stored at
 *                                        obj + 0xB70F): the tree is built (weapon_tree_enter) and, when it has a row, the
 *                                        state byte becomes 7; the forge's own entry (0x9ADC1C) runs on in every case
 *   weapon_tree_smithy_update  0x9AD684  word 7 of the Smithy's state jump table (0x9AD668), which the game never sets:
 *                                        weapon_tree_update every frame of state 7, then the switch's end (0x9AE280)
 *   weapon_tree_smithy_end     0x9BB1B4  FUN_009bb1ac's first call (the Smithy's end): the tree taken down first
 *   weapon_tree_upgrade        0x9BDC70  "bl FUN_00a02048" of Upgrade's A on a box weapon: the tree on that copy
 *                                        (weapon_tree_from_box), else the game's list
 *
 * Nothing is computed at install: when the screen opens, the class's count (FUN_002f457c), each weapon's stats
 * (FUN_002f4694), upgrade record (FUN_002f1340; the glaive's FUN_002f4ac0) and the create recipes (FUN_002f210c,
 * FUN_009be7bc) are read with the game's readers, which the new weapons extend. The panes are six root groups of ui401
 * (tree_layout.py: the screen's five and the window "upgrade or craft"), each in panes.py's order: a group's panes are walked as its sibling list, checking each name's hash
 * (a lookup by hash when one is not where it should be). The tree is placed as tree_model.py's twin places it, and drawn
 * whole on every move; nothing is drawn on a frame without a key. A node's icon is the class's 24 px icon of the
 * forge's stats panel (FUN_00c0e8ec's shape, drawn by FUN_00c117d8), in its rarity's colour (FUN_00c0e170) when it can
 * be forged or upgraded into now, else in the curated grey; a weapon with a create recipe has the forge mark, one in the
 * box and not worn the box mark (the worn one the E), and one with an element or a status its icon at the upper right
 * (the stats panel's, moved to its place in the marks' texture: element_of).
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with weapon_tree.ld where it places the block).
 */

#include "weapon_tree.h"

/* ----- the game's calls ----------------------------------------------------------------------------------- */

GAME u32 weapon_count(u32 equipment, u32 type);                        /* FUN_002f457c */
GAME const u8 *weapon_stats(u32 equipment, u32 type, u32 id);          /* FUN_002f4694 */
GAME u32 weapon_melee(u32 equipment, u32 type);                        /* FUN_002f2170 */
GAME const u8 *upgrade_record(u32 equipment, u32 type, u32 id);        /* FUN_002f1340: record 0 past the table */
GAME const u8 *glaive_record(u32 equipment, u32 id);                   /* FUN_002f4ac0: record 0 past the table */
GAME const u8 *create_recipe(u32 equipment, u32 kind, u32 index);      /* FUN_002f210c */
GAME u32 recipe_state(u32 obj, u32 type, u32 index, u32 mode);        /* FUN_009be7bc: the recipe's index in the table */
GAME u32 gear_flag(u32 save, u32 type, u32 id, u32 array);             /* FUN_00c1fe40 */
GAME u32 box_slots(u32 save, const u8 *data);                          /* FUN_00c1e804(save, save + 0x5C) */
GAME u32 class_icon(u32 gui, u32 type);                                /* FUN_00c0e8ec: a type's 24 px shape */
GAME void rarity_colour(u32 *rgba, u32 gui, u32 rarity);               /* FUN_00c0e170 */
GAME void icon24_draw(u32 gui, void *sprite, u32 shape, const u32 *colour);    /* FUN_00c117d8: UV corner, colours */
GAME u32 item_count(u32 save, u32 item);                               /* FUN_00c21b18 */
GAME void sound_play(u32 manager, u32 sound);                          /* FUN_0031294c */
GAME u32 facility_pressed(u32 obj, u32 bits);                          /* FUN_009ac3a4 */
GAME u32 facility_dirs(u32 obj);                                       /* FUN_009b3830: pressed or repeating */
GAME void text_slot(u32 slot, const u16 *text, u32 length);            /* FUN_005a99a8 */
GAME void text_lobby(void *ref, u32 file, u32 message);                /* FUN_005a882c */
GAME void text_common(void *ref, u32 file, u32 message);               /* FUN_005a9164 */
GAME void forge_hide(u32 obj);                                         /* FUN_00a1c640 */
GAME void money_write(u32 obj, u32 money, u32 one);                    /* FUN_00a52860 */
GAME void money_show(u32 obj, u32 shown, u32 zero);                    /* FUN_00a5d424 */
GAME void preview_frame_close(u32 frame);                              /* FUN_0059f680 */
GAME void viewport_close(u32 viewport);                                /* FUN_00c00ec8 */
GAME void forge_row_show(u32 obj, u8 *st);                             /* FUN_00a38488: the list's row into the view */
GAME void status_draw(u32 obj, u8 *view, u32 one, u32 one_b);          /* FUN_009f95c0: panels, materials, page */
GAME void panels_hide(void);                                           /* FUN_00283290 */
GAME void forge_menu_close(u32 obj);                                   /* FUN_009e6be4 */
GAME void gui_anim_end(u32 anim);                                      /* FUN_002ed7a4 */
/* buying: the forge's own calls (FUN_009ca7e8's create, FUN_009fa2bc / FUN_009e5cc8's upgrade) */
GAME u32 forge_price(u32 equipment, u32 type, u32 id);                 /* FUN_002f77f0: the stat price x 1.5 */
GAME void gear_new_clear(u32 save, u32 type, u32 id, u32 array);       /* FUN_00c23604 */
GAME u32 box_add(u32 save, u8 *data, u32 type, u32 id);                /* FUN_00c243a8: the slot, 0xFFFF full */
GAME void forge_tally(u32 save, const u8 *ref);                        /* FUN_00c1e618 */
GAME void make_record(u32 equipment, u8 *out, u32 type, u32 id);       /* FUN_002f2aa4 */
GAME void view_kind(u32 obj, u8 *view, u32 kind);                      /* FUN_00a140a8 */
GAME void forge_tabs(u32 obj, u8 *st, u32 shown);                      /* FUN_00a6dae4 */
GAME void status_reset(u32 obj, u8 *st, u32 one);                      /* FUN_009ff2d0 */
GAME void lobby_anim_step(u32 anim, u32 step);                         /* FUN_002ed840 */
GAME void window_open(u32 kind, u32 slot, u32 type, u32 first);        /* FUN_002921cc: type 4 yes / no */
GAME void window_update(void);                                         /* FUN_002a2414 */
GAME void window_close(u32 kind, u32 slot);                            /* FUN_0029e5bc */
GAME u32 window_input(u32 obj);                                        /* FUN_00aa6480 */
GAME u32 window_answer(u32 obj, u32 at, u32 input, u32 mask);          /* FUN_00a66e60: 1 yes, 2 no */
GAME void facility_help(u32 kind, u32 file, u32 message);              /* FUN_00298560: the help line */
GAME void hammer_scene(u32 scene, u32 kind);                           /* FUN_009d61e4 */
GAME u32 hammer_scene_busy(u32 scene);                                 /* FUN_009bf778: not 0 once ended */
GAME u32 hammer_kind(u32 obj);                                         /* FUN_00a92af0 */
GAME void smithy_panel(u32 obj, u32 shown, u32 zero);                  /* FUN_00296248 */
GAME void smithy_panel_b(u32 obj, u32 shown, u32 zero);                /* FUN_0029e484 */
GAME void smithy_panel_c(u32 obj, u32 shown);                          /* FUN_00a8e230 */
GAME void money_add(u32 save, int amount);                             /* FUN_00c27764 */
GAME void item_take(u32 obj, u32 item, int quantity);                  /* FUN_00aab06c */
GAME void trade_buttons(u32 obj, u32 layout, u32 flags);               /* FUN_00a51a24 */
GAME void box_view(u32 obj, u32 cell, u32 page);                       /* FUN_00a740ec */
GAME void box_hide(u32 obj);                                           /* FUN_00a980c4 */
GAME void panels_bind(void);                                           /* FUN_0027fc9c */
GAME void panels_release(void);                                        /* FUN_0027ff58 */
GAME void box_menu(u32 obj, u32 menu);                                 /* FUN_00aa1b60: the box shown again */
GAME void model_open(u32 obj, const u8 *ref, u32 mode);                /* FUN_009edcec: the try-on view's model */
GAME void model_input(u32 obj);                                        /* FUN_00a272b0: the model frame's touch */
GAME void model_camera(u32 obj, u8 *st, u32 kind);                     /* FUN_009fc74c: turns, zooms in view 3 */
GAME u32 model_ready(u32 obj, u32 model);                              /* FUN_00a64e9c: its parts loaded */
GAME void model_wear(u32 model, const u8 *ref, u32 one);               /* FUN_00b0af84: a weapon on it */
GAME u32 weapon_look(u32 equipment, const u8 *ref, u32 one, u32 a, u32 b);    /* FUN_002f98b4 */
GAME u32 gear_armor(u32 equipment, u32 type);                          /* FUN_002f1020: 0 for weapons */
GAME void wear_new(u32 obj);                                           /* FUN_009ff3ec */
GAME void smithy_cue(u32 obj, u32 cue);                                /* FUN_009bc944 */
GAME void box_count_show(u32 obj, u32 count);                          /* FUN_00a8c1b8 */
GAME u32 box_used(u32 save, const u8 *data);                           /* FUN_00c1ae68 */
GAME void money_panel(u32 obj, u32 shown);                             /* FUN_00a90190 */
GAME void start_pager_hide(void);                                      /* FUN_005edcbc */
GAME void upgrade_apply(u32 save, u8 *data, u32 slot, const u8 *ref);  /* FUN_00c25824 */
GAME void hunter_refresh(u32 save, u32 hunter, u8 *data, u32 one);     /* FUN_00b0aaec */
GAME u32 slot_worn(u32 save, const u8 *data, u32 slot);                /* FUN_00c1ad38 */
GAME u32 customized(u32 equipment, const u8 *ref);                     /* FUN_002f3e84 */
GAME u32 deco_count(u32 equipment, const u8 *ref);                     /* FUN_002f2cac */
GAME void deco_ids(u32 equipment, const u8 *ref, u16 *out, u32 one);   /* FUN_002f2260 */
GAME const u16 *deco_record(u32 equipment, u32 decoration);            /* FUN_002f0ebc: the item at + 0 */
GAME void item_give(u32 save, u32 item, u32 quantity, void *out);      /* FUN_00c1ea50 */
GAME u32 item_seen(u32 save, const u8 *data, u32 item);                /* FUN_00c1bef8: obtained once */
GAME int pager_step(int value, int count, u32 input, u32 back, u32 next, int sound, u32 *way);   /* FUN_005ed674 */
GAME void pager_left(void);                                            /* FUN_0026f3f4 */
GAME void pager_right(void);                                           /* FUN_00271334 */

extern u32 sound_control, save_control, equipment_control, camera_control;
extern u8 *pad_control;
extern u8 *game_main;              /* the main object: + 0x5C the frame's time */
extern u8 *preview_mode;           /* + 0x6C: 1 / 2 while a preview is shown */
extern u8 lobby_gui_anim[];        /* the lobby GUI's animation the forge's entry starts */
extern u32 screens_open;           /* non-zero while a forge-style screen is on: single_screen.py HELP_FLAGS */
extern const u32 materials_groups[];   /* ui402's groups: the materials box */

/* ----- the game's facts ----------------------------------------------------------------------------------- */

#define FIRST_TYPE 7             /* the Great Sword's equipment type; the classes follow */
#define CLASSES 14
#define GLAIVE 0x13              /* the Insect Glaive: its own upgrade records */
#define MELEE_PRICE 0x04         /* FUN_002f4694's record: a melee weapon's */
#define MELEE_RARITY 0x13
#define MELEE_FLAGS 0x16
#define RANGED_RARITY 0x04       /* a bow's or bowgun's */
#define RANGED_PRICE 0x08
#define RANGED_FLAGS 0x1C
#define RARITIES 10
#define UPGRADE_KIDS 4           /* an upgrade record: 4 materials, then the 4 weapons it upgrades into */
#define UPGRADE_CHILDREN 0x10
#define GLAIVE_MATERIALS 2       /* the glaive's: 2 materials, then its one child */
#define GLAIVE_CHILD 0x08
#define RECIPE_WEAPON 1          /* FUN_002f210c's kind */
#define RECIPE_END 0xFF          /* a recipe's type byte after the last */
#define RECIPE_ID 2
#define RECIPE_MATERIALS 4
#define MAX_RECIPES 4096
#define RECIPE_HIDDEN 0x10       /* FUN_009be7bc: not listed; in mode 0 also 8 materials, 4 money, 2 box room */
#define RECIPE_SHORT 0x08
#define GEAR_HAD 0               /* FUN_00c1fe40's arrays */
#define GEAR_NEW 2
#define SAVE_DATA 0x5C           /* the save object: its data, */
#define SAVE_MONEY 0x90          /* zenny, */
#define SAVE_WORN 0x9C           /* the weapon worn's reference (as FUN_00a38488 reads it) */
#define BOX_AT 0x173E            /* the save data: the equipment box, a reference a slot */
#define REF_SIZE 0x1C            /* a reference: + 0 type, + 2 id */
#define REF_ID 2
#define ST_TYPE 7                /* st = obj + 0xB708, the Smithy's state block: the class chosen, */
#define ST_ROW 0x10              /* the forge list's row (s16), */
#define ST_PAGE_ROWS 0x1C        /* its rows on the page, */
#define ST_LIST 0x434            /* its rows: type, + 2 flags, + 4 id, + 8 price, + 0xC the recipe (materials at + 4) */
#define ST_VIEW 0x1BC            /* the status view (obj + 0xB8C4): + 0 its kind */
#define VIEW_STATS 1
#define OBJ_FRAME 0x104E8        /* the preview's frame widget */
#define PREVIEW_SHOWN 0x6C
#define STATE_MENU 2             /* the Smithy's states: the class menu; ours */
#define STATE_TREE 7
#define PAD_HELD 0x340           /* in the pad object: the GUI's buttons held, */
#define PAD_PRESSED 0x348        /* and those pressed this frame */
#define BUTTON_A 0x10
#define BUTTON_B 0x20
#define BUTTON_X 0x4000
#define BUTTON_L 0x100
#define BUTTON_R 0x200
#define DIR_UP 1
#define DIR_DOWN 2
#define DIR_LEFT 4
#define DIR_RIGHT 8
#define DIR_VERTICAL (DIR_UP | DIR_DOWN)
#define SOUND_DECIDE 1
#define SOUND_CANCEL 2
#define SOUND_ERROR 3
#define SOUND_CURSOR 4
#define TEXT_SLOT 0              /* the text renderer's string slot of the counter */
#define PANE_KIND 0x10           /* a pane's node: its kind, 0 a sprite */
#define SP_BRIGHT 21             /* a sprite's data, in words: its brightness, a float (the clips' property 0x0C; 1.0 the
                                    art's own, the engine keeps it within 0 .. 2: FUN_00ae7ed0) */
#define MAIN_DELTA 0x5C          /* the main object: the frame's time, a float (2.0 at 30 frames a second, 1.0 at 60),
                                    by which the game's animation players go on (FUN_00ae1ddc) */
#define HELD_MAX 0xFFFF
#define MATERIAL_GROUPS 10
/* buying */
#define ST_CHOSEN 0x1A           /* st: the list's row A was pressed on (obj + 0xB722) */
#define ST_ANSWER 0x254          /* the yes / no window's answer word (obj + 0xB95C) */
#define ST_FORGER 0x260          /* the smith (obj + 0xB968): + 0xE2C its status, + 0x2C 'H' when it hammers alone */
#define SMITH_STATUS 0xE2C
#define SMITH_KIND 0x2C
#define SMITH_HAMMER 'H'
#define OBJ_TAB 0xB8A0           /* the forge's tab (s16), */
#define OBJ_TAB_KINDS 0xB891     /* the view kind of each tab, */
#define OBJ_PAGER 0xB8CC         /* the way the status view's page last went (FUN_005ed674's last argument), */
#define OBJ_PAGE 0xB8D0          /* the status view's page (s16), */
#define OBJ_PAGES 0xB8D2         /* its pages (s16), */
#define SOUND_STATS_PAGE 0x1B    /* FUN_005ee9a0's in the forge's L / R */
#define OBJ_NEW_SLOT 0xB958      /* the box slot "Equip now?" wears (u16, 0xFFFF none), */
#define OBJ_HUNTER 0xB960        /* the hunter whose gear the Smithy shows, */
#define OBJ_GEAR_CHANGED 0x97CD  /* set when a worn piece changed */
#define VIEW_COMPARE 2
/* the views X goes round, as the forge's tabs (FUN_009ca7e8 at 0x9CAA6C) */
#define VIEW_MODEL 3             /* try on: the hunter's model */
#define VIEW_DETAIL 4            /* the forge's detail view: X does nothing there */
#define OBJ_TAB_COUNT 0xB8AA     /* the tabs (s16) */
#define ST_X 5                   /* st: 1 on the frame X changed the tab (obj + 0xB70D) */
#define ST_WORN_SHOWN 8          /* st: 1 once the model wears the piece shown (obj + 0xB710) */
#define OBJ_MODEL 0xB964         /* the try-on model (0 none) */
#define HUNTER_GEAR 0xE30        /* the hunter: its gear block, + 0x1C0 the weapon's reference, + 0x31 its look */
#define GEAR_REF 0x1C0
#define GEAR_LOOK 0x31
#define OBJ_LOOK_A 0xC120        /* FUN_002f98b4's last two arguments, as FUN_009ca7e8 passes them */
#define OBJ_LOOK_B 0xC1C8
#define MODEL_WEAPON 2           /* FUN_009edcec's mode for a weapon (1 armor) */
#define SOUND_VIEW 6             /* FUN_005e91ac's in the forge's X */
/* entered from Upgrade (FUN_009bdb58, the Smithy's state 8) */
#define STATE_UPGRADE 8
#define ST_SUB 1                 /* st: the state's sub-state (0 the box), */
#define ST_SUB_FLAG 2
#define ST_MODE 4                /* Upgrade's mode: 1 upgrades (2 strengthens customized pieces) */
#define MODE_UPGRADE 1
#define OBJ_BOX_SLOT 0xBC78      /* the box slot A was pressed on (s16), */
#define OBJ_BOX_MENU 0xD3F4      /* the box's menu FUN_00aa1b60 shows again */
#define LIGHT_BOWGUN 0x0B        /* bowguns: the game's upgrade list also sells their attachments */
#define HEAVY_BOWGUN 0x0C
#define ANSWER_ANY 0xFFFF
#define NO_SLOT 0xFFFF
#define WINDOW_YES_NO 4
#define SOUND_PAY 10             /* FUN_00aa6b3c's: the payment, */
#define SOUND_DONE 6             /* the scene's end, */
#define SOUND_BOX 0x1F           /* the box shown after "Equip now?" No */
#define CUE_WORN 0x65
#define BUTTONS_LIST 2           /* FUN_00a51a24's layouts: the list's, the box's */
#define BUTTONS_BOX 9
#define BUTTONS_FLAGS 4
#define BOX_PAGE 100             /* FUN_00a740ec: a slot as its cell in a page of 100 */
#define BUTTON_AB (BUTTON_A | BUTTON_B)
#define FILE_SMITHY 6            /* the help line's files (FUN_00298560): E_makeshop, */
#define FILE_FORGE 7             /* and the forge's other one */
/* the help line's messages, as the game's state 4 (FUN_009e5734) and state 8 (FUN_009d8614) choose them */
/* the help lines and the price questions are our copies of the game's (weapon_tree.h CAPS_*, from WD->msg_caps) */
#define MSG_FORGE_EQUIP 0x10     /* FILE_FORGE: "Equip now?" */
#define MSG_FORGE_BOX 0x12       /* FILE_FORGE: the box after it */
#define MSG_UPGRADE_EQUIP 0x2C
#define BUYING 1                 /* A buys (0: A only buzzes) */
#define RECIPE_MONEY 0x04
#define RECIPE_FULL 0x02
#define DECOS 3

/* A cell of the window (struct view): what it holds, as bits. */
#define V_NODE 0x001
#define V_LINK 0x002             /* a link in, from its parent */
#define V_UPPER 0x004            /* the trunk's upper half (top to mid height), */
#define V_LOWER 0x008            /* and its lower half */
#define V_WORN 0x010
#define V_NEW 0x020
#define V_LINK_LIT 0x040         /* each of the three on the lineage, lit */
#define V_UPPER_LIT 0x080
#define V_LOWER_LIT 0x100
#define V_LIT_SHIFT 5            /* V_LINK, V_UPPER, V_LOWER -> their lit bits */
#define V_FORGE 0x200            /* it has a create recipe */
#define V_BOX 0x400              /* a copy in the box, none worn: the box mark in the worn mark's corner */

/* Per cell piece (panes.py CELL_PIECES): the bit that shows it, and the bit that lights it. */
static const u16 piece_shown[CELL_PIECES] = {V_NODE, V_LINK, V_UPPER, V_LOWER, V_NODE, V_FORGE, V_WORN, V_BOX, V_NODE,
                                             V_NEW};     /* the element mark: also its weapon's element_of */
static const u16 piece_lit[CELL_PIECES] = {0, V_LINK_LIT, V_UPPER_LIT, V_LOWER_LIT, 0, 0, 0, 0, 0, 0};

/* The weapon's element or status icon: FUN_002729b8's cut of the stats
   panel, by the record's element type (1 fire, 2 water, 3 thunder, 4 dragon, 5 ice; the game's table 0xDF013C) or else
   its status type s (1 poison ... 4 blast: icon 4 + s); ELEMENT_HIDDEN when its value is negative (it needs Awaken). */
#define MELEE_ELEMENT 0x0C       /* the record's element type, value / 10, status type, value / 10 */
#define RANGED_ELEMENT 0x12      /* a bow's (a bowgun's panel has no element row) */
#define ELEMENTS 5
#define STATUSES 4
#define NO_ELEMENT 0xFF
#define ELEMENT_HIDDEN 0x80
static const u8 element_icon[ELEMENTS] = {0, 1, 3, 4, 2};

struct view {                    /* the window's cells, (row, column) from its corner */
    u16 id[MAX_ROWS][MAX_COLUMNS];   /* NO_ID: empty */
    u16 bits[MAX_ROWS][MAX_COLUMNS];
    u8 root[MAX_ROWS];               /* the row begins with a root: its tree's first row */
    u8 alt[MAX_ROWS];                /* the row is of an odd tree (tree_model.py Placement.row_trees): band_alt */
};

/* ----- small helpers -------------------------------------------------------------------------------------- */

static u32 rd16(const u8 *p)
{
    return p[0] | p[1] << 8;
}

static u32 rd32(const u8 *p)
{
    return p[0] | p[1] << 8 | p[2] << 16 | (u32)p[3] << 24;
}

static void play(u32 sound)
{
    sound_play(sound_control, sound);
}

static u32 pad_word(u32 at)
{
    return *(const u32 *)(pad_control + at);
}

static int real(u32 id)
{
    return id < S->count && S->w[id].flags & W_REAL;
}

/* ----- reading the class ---------------------------------------------------------------------------------- */

/* The upgrade record of `id` (the glaive's for an Insect Glaive), and its materials' count; 0 past the class's records,
   where the readers give record 0. */
static const u8 *upgrade_of(u32 id, u32 *materials)
{
    const u8 *record;
    if (S->type == GLAIVE) {
        record = glaive_record(equipment_control, id);
        if (id && record == glaive_record(equipment_control, 0))
            return 0;
        *materials = GLAIVE_MATERIALS;
    } else {
        record = upgrade_record(equipment_control, S->type, id);
        if (id && record == upgrade_record(equipment_control, S->type, 0))
            return 0;
        *materials = 4;
    }
    return record;
}

/* The real weapons `id` upgrades into, in its record's order. */
static u32 children_of(u32 id, u16 *out)
{
    u32 materials, n = 0;
    const u8 *record = upgrade_of(id, &materials);
    if (!record)
        return 0;
    u32 kids = S->type == GLAIVE ? 1 : UPGRADE_KIDS;
    const u8 *at = record + (S->type == GLAIVE ? GLAIVE_CHILD : UPGRADE_CHILDREN);
    for (u32 i = 0; i < kids; i++) {
        u32 child = rd16(at + 2 * i);
        if (child && child != id && real(child))
            out[n++] = child;
    }
    return n;
}

static const u8 *stats_of(u32 id)
{
    return weapon_stats(equipment_control, S->type, id);
}

static u32 price_of(u32 id)
{
    const u8 *stats = stats_of(id);
    return stats ? rd32(stats + (S->melee ? MELEE_PRICE : RANGED_PRICE)) : 0;
}

/* The class's create recipe `index` (counting only the class's), or 0 after the last. */
static const u8 *class_recipe(u32 *index)
{
    for (; *index < MAX_RECIPES; (*index)++) {
        const u8 *recipe = create_recipe(equipment_control, RECIPE_WEAPON, *index);
        if (!recipe || recipe[0] == RECIPE_END)
            return 0;
        if (recipe[0] == S->type && real(rd16(recipe + RECIPE_ID)))
            return recipe;
    }
    return 0;
}

/* Each id: real, its rarity, had once, new. */
static void read_weapons(void)
{
    u32 count = weapon_count(equipment_control, S->type);
    S->count = count < MAX_IDS ? count : MAX_IDS;
    S->melee = weapon_melee(equipment_control, S->type) != 0;
    for (u32 id = 0; id < S->count; id++) {
        struct weapon *w = &S->w[id];
        const u8 *stats = stats_of(id);
        u32 flags = stats ? stats[S->melee ? MELEE_FLAGS : RANGED_FLAGS] & 3 : 0;
        u32 rarity = stats ? stats[S->melee ? MELEE_RARITY : RANGED_RARITY] : 0;
        w->parent = NO_ID;
        w->row = NO_ROW;
        w->column = 0;
        w->info = rarity < RARITIES ? rarity : RARITIES - 1;
        w->flags = flags == 1 || flags == 2 ? W_REAL : 0;
        if (!w->flags)
            continue;
        if (gear_flag(save_control, S->type, id, GEAR_HAD))
            w->info |= I_HAD;
        if (gear_flag(save_control, S->type, id, GEAR_NEW))
            w->flags |= W_NEW;
    }
}

/* The children of real weapons, and the create recipes: listed by the forge, payable now. */
static void read_links(u32 obj)
{
    u16 kids[UPGRADE_KIDS];
    for (u32 id = 0; id < S->count; id++) {
        if (!real(id))
            continue;
        u32 n = children_of(id, kids);
        for (u32 i = 0; i < n; i++)
            S->w[kids[i]].info |= I_CHILD;
    }
    u32 index = 0;
    for (const u8 *recipe; (recipe = class_recipe(&index)) != 0; index++) {
        struct weapon *w = &S->w[rd16(recipe + RECIPE_ID)];
        u32 state = recipe_state(obj, S->type, index, 0);
        w->info |= I_RECIPE;
        if (!(state & RECIPE_HIDDEN))
            w->flags |= W_LISTED;
        if (!state)
            w->info |= I_FORGE;
    }
}

/* Copies in the box, and the one worn. */
static void read_box(void)
{
    const u8 *data = (const u8 *)save_control + SAVE_DATA;
    u32 slots = box_slots(save_control, data);
    for (u32 i = 0; i < slots; i++) {
        const u8 *slot = data + BOX_AT + i * REF_SIZE;
        u32 id = rd16(slot + REF_ID);
        if (slot[0] == S->type && real(id))
            S->w[id].flags |= W_OWNED;
    }
    const u8 *worn = (const u8 *)save_control + SAVE_WORN;
    if (worn[0] == S->type && real(rd16(worn + REF_ID)))
        S->w[rd16(worn + REF_ID)].flags |= W_WORN;
}

static int materials_held(const u8 *pairs, u32 n)
{
    for (u32 i = 0; i < n; i++) {
        u32 item = rd16(pairs + 4 * i), need = rd16(pairs + 4 * i + 2);
        if (item && item_count(save_control, item) < need)
            return 0;
    }
    return 1;
}

static u8 *box_slot(u32 slot)
{
    return (u8 *)save_control + SAVE_DATA + BOX_AT + slot * REF_SIZE;
}

/* A box slot holding a copy of the class the tree may upgrade: not a customized weapon (the game strengthens those
   instead, FUN_009e5cc8; the tree leaves them to the game's Upgrade). */
static int upgradable(u32 slot)
{
    const u8 *ref = box_slot(slot);
    return ref[0] == S->type && real(rd16(ref + REF_ID)) && !customized(equipment_control, ref);
}

static int is_child(u32 parent, u32 child)
{
    u16 kids[UPGRADE_KIDS];
    u32 n = children_of(parent, kids);
    for (u32 i = 0; i < n; i++)
        if (kids[i] == child)
            return 1;
    return 0;
}

/* The box slot `child` is upgraded from: a copy of one of its parents, the one chosen in Upgrade first, then the one
   worn, else the first in the box; NO_ID if none. */
static u32 copy_of(u32 child)
{
    const u8 *data = (const u8 *)save_control + SAVE_DATA;
    u32 slots = box_slots(save_control, data), found = NO_ID;
    if (S->fixed < slots && upgradable(S->fixed) && is_child(rd16(box_slot(S->fixed) + REF_ID), child))
        return S->fixed;
    for (u32 slot = 0; slot < slots; slot++) {
        if (!upgradable(slot) || !is_child(rd16(box_slot(slot) + REF_ID), child))
            continue;
        if (slot_worn(save_control, data, slot))
            return slot;
        if (found == NO_ID)
            found = slot;
    }
    return found;
}

/* The money and the upgrade record's materials into `id` are held. */
static int upgrade_paid(u32 id)
{
    u32 materials;
    const u8 *record = upgrade_of(id, &materials);
    return record && *(const u32 *)((const u8 *)save_control + SAVE_MONEY) >= price_of(id)
           && materials_held(record, materials);
}

/* A weapon a copy in the box upgrades into, with the money and its record's materials, is payable. */
static void read_upgrades(void)
{
    u16 kids[UPGRADE_KIDS];
    const u8 *data = (const u8 *)save_control + SAVE_DATA;
    u32 slots = box_slots(save_control, data);
    for (u32 slot = 0; slot < slots; slot++) {
        if (!upgradable(slot))
            continue;
        u32 n = children_of(rd16(box_slot(slot) + REF_ID), kids);
        for (u32 i = 0; i < n; i++)
            if (!(S->w[kids[i]].flags & W_UPGRADE) && upgrade_paid(kids[i]))
                S->w[kids[i]].flags |= W_UPGRADE;
    }
}

/* ----- discovered and placed (tree_model.py discovered, place) ------------------------------------------------- */

/* The first material of the upgrade into `id` has been obtained once: the test the forge lists a create recipe by
   (FUN_009e6c3c's gate, FUN_00c1bef8). A record with no material is not known by anything. */
static int upgrade_known(u32 id)
{
    u32 materials;
    const u8 *record = upgrade_of(id, &materials);
    for (u32 i = 0; record && i < materials; i++) {
        u32 item = rd16(record + 4 * i);
        if (item)
            return item_seen(save_control, (const u8 *)save_control + SAVE_DATA, item) != 0;
    }
    return 0;
}

#define REACHES 1                /* weapon.column until the placing: a shown weapon is at it or below it */

/* The children of shown weapons that `known` says (the upgrade's material known; or REACHES: between two shown
   weapons) are shown too, and theirs, until no more. Not 0 if any was. */
static u32 grow(u32 known)
{
    u16 kids[UPGRADE_KIDS];
    u32 grown = 0;
    for (u32 more = 1; more;) {
        more = 0;
        for (u32 id = 0; id < S->count; id++) {
            if (!(S->w[id].flags & W_SHOWN))
                continue;
            u32 n = children_of(id, kids);
            for (u32 i = 0; i < n; i++) {
                struct weapon *child = &S->w[kids[i]];
                if (child->flags & W_SHOWN || !(known ? upgrade_known(kids[i]) : child->column & REACHES))
                    continue;
                child->flags |= W_SHOWN;
                more = grown = 1;
            }
        }
    }
    return grown;
}

/* REACHES on every weapon with a shown weapon at it or below it. */
static void mark_reaches(void)
{
    u16 kids[UPGRADE_KIDS];
    for (u32 id = 0; id < S->count; id++)
        S->w[id].column = S->w[id].flags & W_SHOWN ? REACHES : 0;
    for (u32 more = 1; more;) {
        more = 0;
        for (u32 id = 0; id < S->count; id++) {
            if (S->w[id].column & REACHES || !real(id))
                continue;
            u32 n = children_of(id, kids);
            for (u32 i = 0; i < n; i++)
                if (S->w[kids[i]].column & REACHES) {
                    S->w[id].column = REACHES;
                    more = 1;
                    break;
                }
        }
    }
}

/* Listed, had once, or a child of one had once; then, until nothing more comes, the children of a shown weapon whose
   upgrade's material is known and the weapons between two shown ones (a line is never drawn cut in two). REVEAL_ALL:
   also every weapon that can be forged or upgraded into (a weapon with neither, as a ported monster's retired step,
   only once had). */
static void discover(void)
{
    u16 kids[UPGRADE_KIDS];
    for (u32 id = 0; id < S->count; id++) {
        struct weapon *w = &S->w[id];
        if (!(w->flags & W_REAL))
            continue;
        if (w->flags & W_LISTED || (WD->reveal == REVEAL_ALL && w->info & (I_CHILD | I_RECIPE)))
            w->flags |= W_SHOWN;
        if (w->info & I_HAD) {
            w->flags |= W_SHOWN;
            u32 n = children_of(id, kids);
            for (u32 i = 0; i < n; i++)
                S->w[kids[i]].flags |= W_SHOWN;
        }
    }
    for (u32 more = 1; more;) {
        grow(1);
        mark_reaches();
        more = grow(0);              /* what came between may lead to more known upgrades */
    }
    for (u32 id = 0; id < S->count; id++)
        S->w[id].column = 0;
    /* each shown weapon hangs from its shown parent of the lowest id */
    for (u32 id = 0; id < S->count; id++) {
        if (!(S->w[id].flags & W_SHOWN))
            continue;
        u32 n = children_of(id, kids);
        for (u32 i = 0; i < n; i++) {
            struct weapon *child = &S->w[kids[i]];
            if (child->flags & W_SHOWN && child->parent == NO_ID)
                child->parent = id;
        }
    }
}

/* The shown children hanging from `id`, in its record's order, not placed yet. */
static u32 kids_of(u32 id, u16 *out)
{
    u16 kids[UPGRADE_KIDS];
    u32 n = children_of(id, kids), m = 0;
    for (u32 i = 0; i < n; i++)
        if (S->w[kids[i]].parent == id && S->w[kids[i]].row == NO_ROW)
            out[m++] = kids[i];
    return m;
}

/* `id` at (row, column) and its line after it: the first child on its row, each other on the row after the last the
   line before it took. The last row used. */
static u32 place_line(u32 id, u32 row, u32 column, u32 depth)
{
    u16 kids[UPGRADE_KIDS];
    S->w[id].row = row;
    S->w[id].column = column;
    if (column + 1 > S->columns)
        S->columns = column + 1;
    u32 last = row;
    if (depth >= MAX_DEPTH)
        return last;
    u32 n = kids_of(id, kids), placed = 0;
    for (u32 i = 0; i < n; i++) {
        if (S->w[kids[i]].row != NO_ROW)
            continue;                    /* named twice by the record: placed already */
        u32 at = placed++ ? last + 1 : row;
        if (at >= MAX_PLACED_ROWS)
            break;
        last = place_line(kids[i], at, column + 1, depth + 1);
    }
    return last;
}

struct lone { u32 row, count; };   /* the row childless roots share, and how many it holds */

static void place_root(u32 id, struct lone *lone)
{
    u16 kids[UPGRADE_KIDS];
    struct weapon *w = &S->w[id];
    if (!(w->flags & W_SHOWN) || w->parent != NO_ID || w->row != NO_ROW || S->rows >= MAX_PLACED_ROWS)
        return;
    if (kids_of(id, kids)) {
        lone->row = NO_ROW;
        S->rows = place_line(id, S->rows, 0, 0) + 1;
    } else if (lone->row != NO_ROW && lone->count < WD->pack) {
        w->row = lone->row;
        w->column = lone->count++;
        if (w->column + 1u > S->columns)
            S->columns = w->column + 1;
    } else {
        lone->row = S->rows++;
        lone->count = 1;
        w->row = lone->row;
        w->column = 0;
        if (!S->columns)
            S->columns = 1;
    }
}

/* Roots in the create recipes' order, then the others by id. */
static void place(void)
{
    struct lone lone = {NO_ROW, 0};
    S->rows = S->columns = 0;
    u32 index = 0;
    for (const u8 *recipe; (recipe = class_recipe(&index)) != 0; index++)
        place_root(rd16(recipe + RECIPE_ID), &lone);
    for (u32 id = 0; id < S->count; id++)
        place_root(id, &lone);
}

/* ----- the cursor ------------------------------------------------------------------------------------------- */

/* The placed node of `row` nearest to `column` (the left one of two as near); NO_ID if none. */
static u32 nearest(u32 row, u32 column)
{
    u32 best = NO_ID, gap = 0x100;
    for (u32 id = 0; id < S->count; id++) {
        const struct weapon *w = &S->w[id];
        if (w->row != row)
            continue;
        u32 d = w->column > column ? w->column - column : column - w->column;
        if (d < gap || (d == gap && w->column < S->w[best].column)) {
            best = id;
            gap = d;
        }
    }
    return best;
}

/* The node of the cursor's row before (way < 0) or after it; NO_ID if none. */
static u32 beside(int way)
{
    const struct weapon *c = &S->w[S->cursor];
    u32 best = NO_ID;
    for (u32 id = 0; id < S->count; id++) {
        const struct weapon *w = &S->w[id];
        if (w->row != c->row || w->column == c->column || (way < 0) != (w->column < c->column))
            continue;
        if (best == NO_ID || (way < 0 ? w->column > S->w[best].column : w->column < S->w[best].column))
            best = id;
    }
    return best;
}

/* The window on the cursor, on both axes. */
static void follow(void)
{
    const struct weapon *w = &S->w[S->cursor];
    if (w->row < S->top)
        S->top = w->row;
    else if (w->row >= S->top + WD->rows)
        S->top = w->row - WD->rows + 1;
    if (w->column < S->left)
        S->left = w->column;
    else if (w->column >= S->left + WD->columns)
        S->left = w->column - WD->columns + 1;
}

/* The lineage: the cursor's node and every node up to its root. */
static void light(void)
{
    for (u32 id = 0; id < S->count; id++)
        S->w[id].flags &= ~W_LIT;
    u32 id = S->cursor;
    for (u32 steps = 0; steps < MAX_IDS && id != NO_ID; steps++) {
        S->w[id].flags |= W_LIT;
        id = S->w[id].parent;
    }
}

/* ----- drawing ---------------------------------------------------------------------------------------------- */

static u32 group_of(u32 g)
{
    return kit_group(WD->hashes[g]);
}

/* The screen's groups shown or hidden; the window "upgrade or craft" hidden in both cases. */
static void groups_show(u32 shown)
{
    for (u32 g = 0; g < TREE_GROUPS; g++)
        kit_group_show(group_of(g), shown, WD->priority[g]);
    kit_group_show(group_of(G_CHOICE), 0, WD->priority[G_CHOICE]);
}

struct walk { struct ref r; u32 group; };

/* The sprite named `hash`: the node after the last one walked when it is that one (the layout keeps a group's panes in
   panes.py's order), else the lookup by hash. */
static u32 *walk_sprite(struct walk *k, u32 hash)
{
    u8 *node = k->r.node ? *(u8 **)(k->r.node + NODE_NEXT) : 0;
    if (node && *(const u32 *)node == hash && !node[PANE_KIND]) {
        k->r.node = node;
        return *(u32 **)(node + NODE_DATA);
    }
    return kit_sprite(&k->r, k->group, hash);
}

/* A sprite shown or hidden, in `colour` (0: its own); redrawn only when that changes. */
static void sprite_set(const struct ref *r, u32 *sprite, u32 shown, u32 colour)
{
    u32 flags = sprite[SP_FLAGS], want = shown ? flags | SP_SHOWN : flags & ~SP_SHOWN;
    u32 changed = flags != want;
    if (shown && colour && sprite[SP_COLOURS] != colour) {
        kit_sprite_colour(sprite, colour);
        changed = 1;
    }
    sprite[SP_FLAGS] = want;
    if (changed)
        kit_sprite_changed(r);
}

static u32 rarity_rgba(u32 id)
{
    u32 colour = 0;
    rarity_colour(&colour, gui_control, S->w[id].info & I_RARITY);
    return colour;
}

/* A weapon that cannot be bought now: its rarity's colour greyed, each channel (rarity * (100 - mix) + grey * mix) / 100
   (curated `unpayable_mix`), the alpha kept. x / 100 as (x * 5243) >> 19, exact for x < 43699: no library. */
static u32 greyed(u32 colour)
{
    u32 grey = WD->colours[C_UNPAYABLE], mix = WD->unpayable_mix, out = colour & 0xFF000000u;
    for (u32 shift = 0; shift < 24; shift += 8) {
        u32 sum = (colour >> shift & 0xFF) * (100 - mix) + (grey >> shift & 0xFF) * mix;
        out |= (sum * 5243 >> 19) << shift;
    }
    return out;
}

static void view_mark(struct view *v, u32 row, u32 column, u32 bits)
{
    if (row >= S->top && row < S->top + WD->rows && column >= S->left && column < S->left + WD->columns)
        v->bits[row - S->top][column - S->left] |= bits;
}

/* The window's cells: their nodes, links and trunks, lit or not (tree_model.py Placement.cells and lit). */
static void view_build(struct view *v)
{
    volatile u16 *ids = &v->id[0][0], *bits = &v->bits[0][0];   /* volatile: no memset call */
    for (u32 i = 0; i < MAX_ROWS * MAX_COLUMNS; i++) {
        ids[i] = NO_ID;
        bits[i] = 0;
    }
    for (u32 r = 0; r < MAX_ROWS; r++)
        ((volatile u8 *)v->root)[r] = 0;
    u32 trees = 0;                   /* the trees begun above the window */
    for (u32 id = 0; id < S->count; id++) {
        const struct weapon *w = &S->w[id];
        if (w->row == NO_ROW)
            continue;
        u32 lit = w->flags & W_LIT, r = w->row - S->top, c = w->column - S->left;
        if (w->column == 0 && w->parent == NO_ID) {
            if (r < WD->rows)
                v->root[r] = 1;
            else if (w->row < S->top)
                trees++;
        }
        if (r < WD->rows && c < WD->columns) {
            v->id[r][c] = id;
            u32 worn = w->flags & W_WORN;
            v->bits[r][c] |= V_NODE | (worn ? V_WORN : w->flags & W_OWNED ? V_BOX : 0)
                             | (w->flags & W_NEW ? V_NEW : 0) | (w->info & I_RECIPE ? V_FORGE : 0);
            if (w->parent != NO_ID)
                v->bits[r][c] |= lit ? V_LINK | V_LINK_LIT : V_LINK;
        }
        if (w->parent == NO_ID || w->row <= S->w[w->parent].row)
            continue;
        /* a later child: the trunk from its parent's row down to its own */
        u32 from = S->w[w->parent].row, to = w->row;
        if (from < S->top)
            from = S->top;
        if (to >= S->top + WD->rows)
            to = S->top + WD->rows - 1;
        for (u32 row = from; row <= to; row++) {
            u32 half = row == S->w[w->parent].row ? V_LOWER : row == w->row ? V_UPPER : V_UPPER | V_LOWER;
            view_mark(v, row, w->column, lit ? half | half << V_LIT_SHIFT : half);
        }
    }
    for (u32 r = 0; r < MAX_ROWS; r++) {
        trees += v->root[r];
        v->alt[r] = (trees + 1) & 1;     /* tree index trees - 1, odd */
    }
}

static void draw_bands(const struct view *v)
{
    struct walk k = {{0, 0}, group_of(G_ROWS)};
    u32 rows = S->rows - S->top;
    for (u32 r = 0; r < MAX_ROWS; r++)
        for (u32 p = 0; p < BAND_PIECES; p++) {
            u32 *sprite = walk_sprite(&k, WD->hashes[H_BANDS + r * BAND_PIECES + p]);
            if (sprite)
                sprite_set(&k.r, sprite, r < rows && r < WD->rows, WD->colours[v->alt[r] ? C_BAND_ALT : C_BAND]);
        }
}

/* The icon index (0 to 8, node_marks.py ELEMENTS) of weapon `id`'s element or status, with ELEMENT_HIDDEN, or
   NO_ELEMENT. */
static u32 element_of(u32 id)
{
    const u8 *stats = stats_of(id);
    if (!stats || S->type == LIGHT_BOWGUN || S->type == HEAVY_BOWGUN)
        return NO_ELEMENT;
    const u8 *e = stats + (S->melee ? MELEE_ELEMENT : RANGED_ELEMENT);
    if (e[0] >= 1 && e[0] <= ELEMENTS)
        return element_icon[e[0] - 1] | ((signed char)e[1] < 0 ? ELEMENT_HIDDEN : 0);
    if (e[2] >= 1 && e[2] <= STATUSES)
        return (ELEMENTS - 1 + e[2]) | ((signed char)e[3] < 0 ? ELEMENT_HIDDEN : 0);
    return NO_ELEMENT;
}

/* An element pane's region moved to icon `icon` of the marks' texture (its size is every icon's). */
static void element_region(const struct ref *r, u32 *sprite, u32 icon)
{
    const u32 *corner = WD->element_uv[icon];
    if (sprite[SP_U] == corner[0] && sprite[SP_U + 1] == corner[1])
        return;
    sprite[SP_U] = corner[0];
    sprite[SP_U + 1] = corner[1];
    kit_sprite_changed(r);
}

static void draw_cells(const struct view *v)
{
    struct walk k = {{0, 0}, group_of(G_NODES)};
    u32 icon = class_icon(gui_control, S->type), at = H_CELLS;
    for (u32 piece = 0; piece < CELL_PIECES; piece++)
        for (u32 r = 0; r < MAX_ROWS; r++)
            for (u32 c = 0; c < MAX_COLUMNS; c++, at++) {
                u32 *sprite = walk_sprite(&k, WD->hashes[at]);
                if (!sprite)
                    continue;
                u32 bits = v->bits[r][c], id = v->id[r][c];
                u32 shown = bits & piece_shown[piece], colour = 0;
                const struct weapon *w = &S->w[shown ? id : 0];
                if (piece == P_ELEMENT) {
                    u32 element = shown ? element_of(id) : NO_ELEMENT;
                    shown = element != NO_ELEMENT;
                    if (shown)
                        element_region(&k.r, sprite, element & ~ELEMENT_HIDDEN);
                    colour = WD->colours[element & ELEMENT_HIDDEN ? C_ELEMENT_HIDDEN : C_ELEMENT];
                    sprite_set(&k.r, sprite, shown, colour);
                    continue;
                }
                if (shown && piece == P_ICON) {
                    /* payable now, by forging or upgrading: its rarity's colour; else the grey */
                    colour = w->info & I_FORGE || w->flags & W_UPGRADE ? rarity_rgba(id) : greyed(rarity_rgba(id));
                    icon24_draw(gui_control, (u8 *)sprite + SP_ICON, icon, &colour);
                    sprite[SP_FLAGS] |= SP_SHOWN;
                    kit_sprite_changed(&k.r);
                    continue;
                }
                if (piece_lit[piece])
                    colour = WD->colours[bits & piece_lit[piece] ? C_LINK_LIT : C_LINK];
                else if (shown && piece == P_PLATE)
                    colour = WD->colours[w->flags & W_OWNED ? C_PLATE_OWNED : w->flags & W_LIT ? C_PLATE_LIT : C_PLATE];
                else if (shown && piece == P_FORGE)
                    colour = WD->colours[C_FORGE];   /* never grey: the icon says whether it can be bought now */
                else if (shown && piece == P_BOX)
                    colour = WD->colours[C_BOX];
                sprite_set(&k.r, sprite, shown, colour);
            }
}

static void place_sprite(u32 group, u32 hash, int x, int y, u32 w, u32 h, u32 colour)
{
    struct ref r;
    u32 *sprite = kit_sprite_place(&r, group, hash, x, y, w, h);
    if (!sprite)
        return;
    if (colour)
        kit_sprite_colour(sprite, colour);
    kit_sprite_changed(&r);
}

/* The cursor's set (curated `cursor.style`) round the cursor's cell; the other set hidden. */
static void draw_cursor(void)
{
    const struct weapon *w = &S->w[S->cursor];
    u32 group = group_of(G_CURSOR);
    int x = WD->origin_x + (w->column - S->left) * WD->pitch_x, y = WD->origin_y + (w->row - S->top) * WD->pitch_y;
    int bracket = WD->style == STYLE_BRACKET;
    for (u32 i = 0; i < 2; i++)
        if (bracket)
            place_sprite(group, WD->hashes[H_BRACKET + i], x + WD->bracket[2 * i], y + WD->bracket[2 * i + 1],
                         WD->bracket_w, WD->bracket_h, 0);
        else
            kit_sprite_hide(group, WD->hashes[H_BRACKET + i]);
    int left = x + WD->icon_x - WD->frame_pad, top = y + WD->icon_y - WD->frame_pad;
    u32 wide = WD->icon_w + 2 * WD->frame_pad, tall = WD->icon_h + 2 * WD->frame_pad, thick = WD->frame_thickness;
    int xs[4] = {left, left, left, left + (int)(wide - thick)}, ys[4] = {top, top + (int)(tall - thick), top, top};
    u32 ws[4] = {wide, wide, thick, thick}, hs[4] = {thick, thick, tall, tall};
    for (u32 i = 0; i < 4; i++)
        if (bracket)
            kit_sprite_hide(group, WD->hashes[H_LINES + i]);
        else
            place_sprite(group, WD->hashes[H_LINES + i], xs[i], ys[i], ws[i], hs[i], WD->colours[C_CURSOR]);
}

/* The arrows at the window's edges where the tree goes on. */
static void draw_arrows(void)
{
    u32 group = group_of(G_KEYS);
    u32 more[4] = {S->left > 0, S->columns > S->left + WD->columns, S->top > 0, S->rows > S->top + WD->rows};
    for (u32 i = 0; i < 4; i++) {
        struct ref r;
        u32 *sprite = kit_sprite(&r, group, WD->hashes[H_ARROWS + i]);
        if (sprite)
            sprite_set(&r, sprite, more[i], 0);
    }
}

/* The header: the weapon's name in its rarity's colour, and "row/rows". */
static void draw_header(void)
{
    struct ref r;
    u32 group = group_of(G_NODES);
    u32 *text = kit_text(&r, group, WD->hashes[H_NAME]);
    if (text) {
        kit_text_colour(text, rarity_rgba(S->cursor));
        text_common(&r, WD->name_files + S->type - FIRST_TYPE, S->cursor);
        text_show((u32)text, 1);
        kit_text_changed(&r);
    }
    text = kit_text(&r, group, WD->hashes[H_COUNT]);
    if (text) {
        u32 length = kit_number_text(S->count_text, S->w[S->cursor].row + 1u);
        S->count_text[length++] = '/';
        length += kit_number_text(S->count_text + length, S->rows);
        text_slot(TEXT_SLOT, S->count_text, length);
        text_lobby(&r, WD->text_file, WD->msg_count);
        text_show((u32)text, 1);
        kit_text_changed(&r);
    }
}

static void draw_hint(void)
{
    struct ref r;
    u32 *text = kit_text(&r, group_of(G_KEYS), WD->hashes[H_HINT]);
    if (text) {
        text_lobby(&r, WD->text_file, WD->msg_hint);
        text_show((u32)text, 1);
        kit_text_changed(&r);
    }
}

static void draw(void)
{
    struct view v;
    view_build(&v);
    draw_bands(&v);
    draw_cells(&v);
    draw_cursor();
    draw_arrows();
    draw_header();
}

/* ----- the game's panels ------------------------------------------------------------------------------------- */

/* The create recipe of `id` (its first in the table) and its index there, or 0. */
static const u8 *recipe_of(u32 id, u32 *at)
{
    u32 index = 0;
    for (const u8 *recipe; (recipe = class_recipe(&index)) != 0; index++)
        if (rd16(recipe + RECIPE_ID) == id) {
            *at = index;
            return recipe;
        }
    return 0;
}

/* What the panels show for `id` and A buys: an upgrade when a copy of a parent is in the box and the upgrade can be
   paid, or the weapon has no create recipe, or that recipe cannot be paid; else the create recipe. A weapon with both
   ways (both_ways) asks which in its window, where the player changes it. */
static u32 choice(u32 id)
{
    const struct weapon *w = &S->w[id];
    if (!(w->info & I_RECIPE))
        return BUY_UPGRADE;
    if (w->flags & W_UPGRADE || (!(w->info & I_FORGE) && copy_of(id) != NO_ID))
        return BUY_UPGRADE;
    return BUY_FORGE;
}

/* The view of the forge's tab (stats, try on, compare: FUN_009ff2d0's kinds at obj + 0xB891). */
static u32 tab_kind(u32 obj)
{
    return *((const u8 *)obj + OBJ_TAB_KINDS + *(const s16 *)((const u8 *)obj + OBJ_TAB));
}

/* Both ways to get `id` are open: the forge lists its create recipe and a copy of a parent is in the box. */
static int both_ways(u32 id)
{
    return S->w[id].flags & W_LISTED && copy_of(id) != NO_ID;
}

/* The forge list's row 0 (what FUN_00a38488 shows: the stats panel and the materials box) filled with the cursor's
   weapon as S->buy gets it: its create recipe, else its upgrade record's materials, copied to the state's own recipe.
   The row's bits say what is missing, as FUN_009be7bc's: with no copy to upgrade, the materials. */
static void row_fill(u32 obj, u8 *st)
{
    u32 id = S->cursor, flags, materials, index, price;
    const u8 *recipe = S->buy == BUY_UPGRADE ? 0 : recipe_of(id, &index);
    if (recipe) {
        /* a recipe the forge does not list is hidden while its first material was never obtained: short of it */
        flags = recipe_state(obj, S->type, index, 0);
        if (flags & RECIPE_HIDDEN)
            flags = (flags & ~RECIPE_HIDDEN) | RECIPE_SHORT;
        price = forge_price(equipment_control, S->type, id);     /* the forge list's own (FUN_002f77f0) */
    } else {
        price = price_of(id);
        volatile u16 *out = S->recipe;   /* volatile: no memset call */
        const u8 *record = upgrade_of(id, &materials);
        for (u32 i = 0; i < sizeof S->recipe / 2; i++)
            out[i] = 0;
        for (u32 i = 0; record && i < 2 * materials; i++)
            out[RECIPE_MATERIALS / 2 + i] = rd16(record + 2 * i);
        recipe = (const u8 *)S->recipe;
        flags = 0;
        if (!record || copy_of(id) == NO_ID || !materials_held(record, materials))
            flags |= RECIPE_SHORT;
        if (*(const u32 *)((const u8 *)save_control + SAVE_MONEY) < price)
            flags |= RECIPE_MONEY;
    }
    u8 *row = st + ST_LIST;
    row[0] = S->type;
    row[1] = 0;
    *(u16 *)(row + 2) = flags;
    *(u16 *)(row + 4) = id;
    *(u16 *)(row + 6) = 0;
    *(u32 *)(row + 8) = price;
    *(const u8 **)(row + 0xC) = recipe;
    *(s16 *)(st + ST_ROW) = 0;
    *(u16 *)(st + ST_PAGE_ROWS) = 1;
}

static void show_stats(u32 obj, u8 *st)
{
    if (S->sub == T_LIST)
        S->buy = choice(S->cursor);
    row_fill(obj, st);
    st[ST_VIEW] = tab_kind(obj);     /* the view X chose stays as the cursor moves */
    forge_row_show(obj, st);
}

static void draw_money(u32 obj)
{
    money_write(obj, *(const u32 *)((const u8 *)save_control + SAVE_MONEY), 1);
    money_show(obj, 1, 0);
}

/* ----- buying ------------------------------------------------------ */

static u8 *save_data(void)
{
    return (u8 *)save_control + SAVE_DATA;
}

static u32 row_flags(const u8 *st)
{
    return *(const u16 *)(st + ST_LIST + 2);
}

static u32 row_price(const u8 *st)
{
    return *(const u32 *)(st + ST_LIST + 8);
}

/* The help line of our copy `message` (CAPS_*) of a message of the game's: the same words, the verb in capitals. */
static void help(u32 message)
{
    facility_help(1, WD->text_file, WD->msg_caps + message);
}

/* The help line on the list and on the window "upgrade or craft", as the forge's (FUN_009e5734) and the upgrade's
   (FUN_009d8614) say why a row cannot be bought; the upgrade's shows the decorations' warning when the copy has some.
   It names what the materials shown are for: to CRAFT or to UPGRADE. */
static void list_help(const u8 *st)
{
    u32 flags = row_flags(st), short_of = flags & RECIPE_SHORT, money = flags & RECIPE_MONEY, message;
    if (S->buy == BUY_FORGE) {
        message = flags & RECIPE_FULL ? CAPS_FORGE_FULL : short_of && money ? CAPS_FORGE_BOTH
                  : money ? CAPS_FORGE_MONEY : short_of ? CAPS_FORGE_SHORT : CAPS_FORGE_OK;
    } else {
        u32 slot = copy_of(S->cursor);
        message = short_of && money ? CAPS_UPGRADE_BOTH : money ? CAPS_UPGRADE_MONEY : short_of ? CAPS_UPGRADE_SHORT
                  : slot != NO_ID && deco_count(equipment_control, box_slot(slot)) ? CAPS_UPGRADE_DECOS
                  : CAPS_UPGRADE_OK;
    }
    help(message);
}

static void windows_open(void)
{
    window_open(3, 0, WINDOW_YES_NO, 1);
    window_open(6, 1, WINDOW_YES_NO, 1);
}

static void windows_close(void)
{
    window_close(3, 0);
    window_close(6, 1);
}

static u32 answer(u32 obj, u8 *st)
{
    return window_answer(obj, (u32)(st + ST_ANSWER), window_input(obj), ANSWER_ANY);
}

static void preview_close(u32 obj)
{
    preview_frame_close(obj + OBJ_FRAME);
    preview_mode[PREVIEW_SHOWN] = 0;
    viewport_close(camera_control);
}

/* A on a node: the forge's refusal (sound 3) when it cannot be bought; else its yes / no window, as FUN_009ca7e8's A
   (create) and FUN_009fa2bc's (upgrade) open it. The row 0 of the forge's list already holds the node (show_stats). */
static void buy_ask(u32 obj, u8 *st)
{
    u32 id = S->cursor, index;
    if (S->buy == BUY_FORGE) {
        if (!recipe_of(id, &index) || recipe_state(obj, S->type, index, 0)) {
            play(SOUND_ERROR);
            return;
        }
        S->index = index;
        *(u16 *)(st + ST_CHOSEN) = 0;
    } else {
        u32 slot = copy_of(id);
        if (slot == NO_ID || !upgrade_paid(id)) {
            play(SOUND_ERROR);
            return;
        }
        S->copy = slot;
    }
    S->bought = id;
    *(u32 *)(st + ST_ANSWER) = 0;
    windows_open();
    *(s16 *)((u8 *)obj + OBJ_PAGE) = 0;
    view_kind(obj, st + ST_VIEW, VIEW_COMPARE);
    if (S->buy == BUY_FORGE)
        forge_tabs(obj, st, 0);
    forge_row_show(obj, st);
    play(SOUND_DECIDE);
    lobby_anim_step((u32)lobby_gui_anim, 1);
    S->sub = T_PROMPT;
    screens_open = 0;
}

/* ----- the window "upgrade or craft" ------------------------------------------------------------------------- */

/* The window's rows: the cursor bar on the option S->buy is, each word bright when that way can be paid now. */
static void choice_draw(void)
{
    struct ref r;
    u32 group = group_of(G_CHOICE), on = S->buy == BUY_FORGE;     /* row 0 upgrade, row 1 craft */
    const struct weapon *w = &S->w[S->cursor];
    u32 *text = kit_text(&r, group, WD->hashes[H_CHOICE + CH_TITLE]);
    if (text) {
        text_lobby(&r, WD->text_file, WD->msg_choice + CHOICE_TITLE);
        text_show((u32)text, 1);
        kit_text_changed(&r);
    }
    for (u32 option = 0; option < CHOICE_OPTIONS; option++) {
        for (u32 piece = 0; piece < BAND_PIECES; piece++) {
            u32 *sprite = kit_sprite(&r, group, WD->hashes[H_CHOICE + CH_CURSOR + option * BAND_PIECES + piece]);
            if (sprite)
                sprite_set(&r, sprite, option == on, 0);
        }
        text = kit_text(&r, group, WD->hashes[H_CHOICE + CH_WORDS + option]);
        if (!text)
            continue;
        u32 payable = option ? w->info & I_FORGE : w->flags & W_UPGRADE;
        kit_text_colour(text, WD->colours[payable ? C_CHOICE_ON : C_CHOICE_OFF]);
        text_lobby(&r, WD->text_file, WD->msg_choice + CHOICE_UPGRADE + option);
        text_show((u32)text, 1);
        kit_text_changed(&r);
    }
}

/* The panels on the way S->buy says, and the window's cursor on it: one never shows without the other. */
static void choice_show(u32 obj, u8 *st)
{
    row_fill(obj, st);
    forge_row_show(obj, st);
    choice_draw();
}

/* A on a weapon with both ways: the window over the tree, the cursor on the way the panels were showing (choice); the
   status view on its stats' first page, the one with the materials box, whatever X or L / R had chosen, and try on's
   model away (FUN_00a6dae4, as the forge's own A). */
static void choice_open(u32 obj, u8 *st)
{
    S->sub = T_CHOICE;
    S->chosen = 1;
    *(s16 *)((u8 *)obj + OBJ_PAGE) = 0;
    view_kind(obj, st + ST_VIEW, VIEW_STATS);
    forge_tabs(obj, st, 0);
    choice_show(obj, st);
    kit_group_show(group_of(G_CHOICE), 1, WD->priority[G_CHOICE]);
    play(SOUND_DECIDE);
}

/* The tab's own view again, with try on's model. */
static void view_back(u32 obj, u8 *st)
{
    view_kind(obj, st + ST_VIEW, tab_kind(obj));
    forge_tabs(obj, st, 1);
}

/* Every frame of the window: Up / Down change the way, and the panels with it; A asks its price (buy_ask: the forge's
   refusal when it cannot be paid, and the window stays); B goes back to the tree. Not inlined, as keys. */
static __attribute__((noinline)) void choice_keys(u32 obj, u8 *st)
{
    if (facility_pressed(obj, BUTTON_B)) {
        kit_group_show(group_of(G_CHOICE), 0, WD->priority[G_CHOICE]);
        S->sub = T_LIST;
        view_back(obj, st);
        show_stats(obj, st);
        play(SOUND_CANCEL);
    } else if (facility_pressed(obj, BUTTON_A)) {
        buy_ask(obj, st);
        if (S->sub == T_PROMPT)
            kit_group_show(group_of(G_CHOICE), 0, WD->priority[G_CHOICE]);
    } else if (facility_dirs(obj) & DIR_VERTICAL) {
        S->buy = S->buy == BUY_FORGE ? BUY_UPGRADE : BUY_FORGE;
        choice_show(obj, st);
        play(SOUND_CURSOR);
    }
}

/* A on a node. Any A clears the weapon's "new" bit and its node's "NEW" (round 9): the game clears it only on an A it
   takes (a payable create recipe), so on a tree whose weapons mostly cannot be bought yet the marks stayed for good. */
static void ask(u32 obj, u8 *st)
{
    u32 id = S->cursor;
    S->chosen = 0;
    gear_new_clear(save_control, S->type, id, GEAR_NEW);
    if (S->w[id].flags & W_NEW) {
        S->w[id].flags &= ~W_NEW;
        draw();
    }
    if (both_ways(id))
        choice_open(obj, st);
    else
        buy_ask(obj, st);
}

/* No: the tab's own view again, as the forge's No (after the window "upgrade or craft", with the model it put away). */
static void buy_refused(u32 obj, u8 *st)
{
    windows_close();
    trade_buttons(obj, BUTTONS_LIST, BUTTONS_FLAGS);
    if (S->buy == BUY_FORGE || S->chosen)
        view_back(obj, st);
    else
        view_kind(obj, st + ST_VIEW, tab_kind(obj));
    forge_row_show(obj, st);
    play(SOUND_CANCEL);
    lobby_anim_step((u32)lobby_gui_anim, 0);
    S->sub = T_LIST;
    screens_open = 1;
}

/* The smith's hammer scene, as FUN_009ca7e8's Yes asks for it before the purchase: the status view as at the entry,
   the preview closed, FUN_009d61e4 with the smith's kind (3 for the smith 'H', 2 when FUN_00a92af0, else 1). Both
   ways start it on the tree, though the game's own upgrade has no scene. */
static void scene_start(u32 obj, u8 *st)
{
    status_reset(obj, st, 1);
    preview_close(obj);
    S->sub = T_SCENE_START;
    u32 kind;
    if (*(u8 *)(*(u32 *)(*(u32 *)(st + ST_FORGER) + SMITH_STATUS) + SMITH_KIND) == SMITH_HAMMER)
        kind = 3;
    else
        kind = hammer_kind(obj) ? 2 : 1;
    hammer_scene((u32)preview_mode, kind);
}

/* The Smithy's panels and our groups put away while the scene plays, as FUN_009ca7e8's Yes ends. */
static void scene_panels(u32 obj)
{
    forge_hide(obj);
    smithy_panel(obj, 0, 0);
    smithy_panel_b(obj, 0, 0);
    smithy_panel_c(obj, 0);
    groups_show(0);
}

/* Yes on a create recipe: FUN_009ca7e8's sub-state 1, call by call. The box has room (recipe_state's bit 2 was 0). */
static void forge_buy(u32 obj, u8 *st)
{
    u8 ref[REF_SIZE];
    u32 id = S->bought;
    const u8 *recipe = create_recipe(equipment_control, RECIPE_WEAPON, S->index);
    scene_start(obj, st);
    make_record(equipment_control, ref, S->type, id);
    *(u16 *)((u8 *)obj + OBJ_NEW_SLOT) = NO_SLOT;
    *(u16 *)((u8 *)obj + OBJ_NEW_SLOT) = box_add(save_control, save_data(), ref[0], rd16(ref + REF_ID));
    money_add(save_control, -(int)row_price(st));
    play(SOUND_PAY);
    for (u32 i = 0; i < 4; i++)
        item_take(obj, rd16(recipe + RECIPE_MATERIALS + 4 * i), (s16)rd16(recipe + RECIPE_MATERIALS + 4 * i + 2));
    forge_tally(save_control, ref);
    scene_panels(obj);
}

/* Yes on an upgrade: FUN_009e5cc8 for a weapon not customized, call by call, on the copy chosen. An Insect Glaive is
   upgraded as any class, with its record's two materials; the kinsect (the reference's [1], [4..5]) is not touched:
   FUN_00c25824 copies only the id and the decorations between two glaives, and the game's FUN_002f764c after it is
   not called. obj + 0xB958 is the slot even when it is worn (the game writes 0xFFFF and asks nothing): "Equip now?"
   is asked after every upgrade on the tree, and Yes on a worn copy wears that slot again (FUN_00c1e064: no change). */
static void upgrade_buy(u32 obj, u8 *st)
{
    u8 child[REF_SIZE];
    u16 decos[DECOS + 1];
    u32 out, materials, id = S->bought, slot = S->copy;
    u8 *data = save_data(), *copy = box_slot(slot);
    u32 n = deco_count(equipment_control, copy);
    deco_ids(equipment_control, copy, decos, 1);
    for (u32 i = 0; i < n && i < DECOS; i++)
        item_give(save_control, *deco_record(equipment_control, decos[i]), 1, &out);
    volatile u8 *zero = child;   /* volatile: no memset call */
    for (u32 i = 0; i < REF_SIZE; i++)
        zero[i] = 0;
    child[0] = S->type;
    *(u16 *)(child + REF_ID) = id;
    const u8 *record = upgrade_of(id, &materials);
    for (u32 i = 0; record && i < materials; i++) {
        u32 item = rd16(record + 4 * i);
        int quantity = (s16)rd16(record + 4 * i + 2);
        if (item && quantity > 0)
            item_take(obj, item, quantity);
    }
    forge_tally(save_control, child);
    money_add(save_control, -(int)price_of(id));
    play(SOUND_PAY);
    upgrade_apply(save_control, data, slot, child);
    hunter_refresh(save_control, *(u32 *)((u8 *)obj + OBJ_HUNTER), data, 1);
    if (slot_worn(save_control, data, slot))
        *((u8 *)obj + OBJ_GEAR_CHANGED) = 1;
    st[ST_TYPE] = S->type;
    *(u16 *)((u8 *)obj + OBJ_NEW_SLOT) = slot;
}

/* The tree read again after a purchase, the cursor on the weapon bought (its children show now). */
static void rebuild(u32 obj, u8 *st, u32 id);

/* "Equip now?" in the same window, after the scene (the forge's and, on the tree, the upgrade's). Until it is answered
   S->buy stays the way bought. */
static void equip_ask(void)
{
    windows_open();
    S->sub = T_EQUIP;
    screens_open = 0;
}

/* Back on the tree after a purchase: the panels on the node's own way again (show_stats in T_LIST: the copy upgraded
   may be gone, so the way bought may not be the node's now). */
static void list_again(u32 obj, u8 *st)
{
    S->sub = T_LIST;
    screens_open = 1;
    show_stats(obj, st);
}

static __attribute__((noinline)) void prompt(u32 obj, u8 *st)      /* not inlined, as keys */
{
    u32 length = kit_number_text(S->price_text, row_price(st));
    text_slot(TEXT_SLOT, S->price_text, length);
    help(S->buy == BUY_FORGE ? CAPS_FORGE_PRICE : CAPS_UPGRADE_PRICE);
    window_update();
    u32 said = answer(obj, st);
    if (said == 2) {
        buy_refused(obj, st);
        if (S->buy != choice(S->cursor))
            show_stats(obj, st);     /* the other way was chosen in the window: the node's own in the row again */
    } else if (said == 1 && S->buy == BUY_FORGE) {
        forge_buy(obj, st);
    } else if (said == 1) {
        upgrade_buy(obj, st);            /* FUN_009fa2bc's Yes: the windows closed after FUN_009e5cc8 */
        *(u32 *)(st + ST_ANSWER) = 0;
        windows_close();
        trade_buttons(obj, BUTTONS_LIST, BUTTONS_FLAGS);
        scene_start(obj, st);            /* then the forge's scene, and "Equip now?" at its end */
        scene_panels(obj);
    }
}

/* The money and the forge's pager hidden while the scene plays, as FUN_009e5734 does in sub-states 2 to 4. */
static void scene_hide(u32 obj)
{
    money_panel(obj, 0);
    money_show(obj, 0, 0);
    start_pager_hide();
}

static void scene_end(u32 obj, u8 *st)
{
    scene_hide(obj);
    if (!hammer_scene_busy((u32)preview_mode))
        return;
    smithy_panel(obj, 1, 0);
    smithy_panel_c(obj, 1);
    groups_show(1);
    rebuild(obj, st, S->bought);
    equip_ask();
    play(SOUND_DONE);
}

/* Yes wears it (FUN_009ff3ec, the slot at obj + 0xB958); No: the forge shows the box at the new piece, the upgrade goes
   back to the list. */
static void equip(u32 obj, u8 *st)
{
    if (S->buy == BUY_FORGE) {
        scene_hide(obj);
        facility_help(1, FILE_FORGE, MSG_FORGE_EQUIP);
    } else {
        facility_help(1, FILE_SMITHY, MSG_UPGRADE_EQUIP);
        window_update();
    }
    u32 said = answer(obj, st);
    if (said == 1) {
        wear_new(obj);
        if (S->buy == BUY_FORGE)
            status_reset(obj, st, 1);
        windows_close();
        trade_buttons(obj, BUTTONS_LIST, BUTTONS_FLAGS);
        smithy_cue(obj, CUE_WORN);
        lobby_anim_step((u32)lobby_gui_anim, 0);
        rebuild(obj, st, S->bought);
        list_again(obj, st);
    } else if (said == 2 && S->buy == BUY_FORGE) {
        u32 cell = *(u16 *)((u8 *)obj + OBJ_NEW_SLOT), page = 0;
        for (; cell >= BOX_PAGE; cell -= BOX_PAGE)   /* no division: the block has no library */
            page++;
        windows_close();
        trade_buttons(obj, BUTTONS_LIST, BUTTONS_FLAGS);
        panels_release();
        box_view(obj, cell, page);
        trade_buttons(obj, BUTTONS_BOX, BUTTONS_FLAGS);
        play(SOUND_BOX);
        groups_show(0);
        S->sub = T_BOX;
    } else if (said == 2) {
        windows_close();
        trade_buttons(obj, BUTTONS_LIST, BUTTONS_FLAGS);
        preview_close(obj);
        lobby_anim_step((u32)lobby_gui_anim, 0);
        list_again(obj, st);
    }
}

/* The box after "Equip now?" No: FUN_009e5734's sub-state 8 drawing, until A or B; then back, as the forge comes back. */
static void box_shown(u32 obj, u8 *st)
{
    box_count_show(obj, box_used(save_control, save_data()));
    money_panel(obj, 1);
    money_write(obj, *(const u32 *)((const u8 *)save_control + SAVE_MONEY), 1);
    money_show(obj, 1, 0);
    facility_help(1, FILE_FORGE, MSG_FORGE_BOX);
    if (!facility_pressed(obj, BUTTON_AB))
        return;
    play(SOUND_DECIDE);
    box_hide(obj);
    panels_bind();
    trade_buttons(obj, BUTTONS_LIST, BUTTONS_FLAGS);
    lobby_anim_step((u32)lobby_gui_anim, 0);
    groups_show(1);
    S->sub = T_LIST;
    screens_open = 1;
    rebuild(obj, st, S->cursor);
}

/* ----- the screen ------------------------------------------------------------------------------------------- */

static void move_to(u32 obj, u8 *st, u32 id, u32 sound, u32 remember)
{
    S->cursor = id;
    if (remember)
        S->remember = S->w[id].column;
    follow();
    light();
    draw();
    show_stats(obj, st);
    play(sound);
}

/* The first frame of state 7: the forge's own panels off, ours on, the cursor on the box weapon chosen in Upgrade, else
   the weapon worn, else the first. */
static void tree_show(u32 obj, u8 *st)
{
    forge_hide(obj);
    groups_show(1);
    screens_open = 1;
    S->open = OPEN;
    S->sub = T_LIST;
    S->top = S->left = 0;
    S->held = 0;
    u32 start = nearest(0, 0);
    for (u32 id = 0; id < S->count; id++)
        if (S->w[id].flags & W_WORN && S->w[id].row != NO_ROW)
            start = id;
    if (S->fixed != NO_SLOT && S->w[rd16(box_slot(S->fixed) + REF_ID)].row != NO_ROW)
        start = rd16(box_slot(S->fixed) + REF_ID);
    draw_hint();
    S->cursor = start;
    S->remember = S->w[start].column;
    follow();
    light();
    draw();
    show_stats(obj, st);
}

/* B, as the forge's B from state 4: the preview closed, everything hidden, back to the class menu (state 2 shows it
   again on its page and row by itself). */
static void tree_close(u32 obj, u8 *st)
{
    groups_show(0);
    screens_open = 0;
    S->open = CLOSED;
    S->sub = T_LIST;
    preview_close(obj);
    if (S->fixed != NO_SLOT) {       /* from Upgrade: back to the box, as the upgrade list's B (FUN_009fa2bc) */
        st[ST_SUB] = st[ST_SUB_FLAG] = 0;
        view_kind(obj, st + ST_VIEW, VIEW_COMPARE);
        play(SOUND_CANCEL);
        st[0] = STATE_UPGRADE;
        panels_release();
        box_menu(obj, *((u8 *)obj + OBJ_BOX_MENU));
        return;
    }
    play(SOUND_CANCEL);
    st[0] = STATE_MENU;
    forge_hide(obj);
    forge_menu_close(obj);
    gui_anim_end((u32)lobby_gui_anim);
}

/* The rows a step of Up / Down moves: one, then the curated steps' once it has been held that many frames. */
static u32 held_rows(void)
{
    if (!(pad_word(PAD_HELD) & DIR_VERTICAL) || pad_word(PAD_PRESSED) & DIR_VERTICAL)
        S->held = 0;
    else if (S->held < HELD_MAX)
        S->held++;
    u32 rows = 1;
    for (u32 i = 0; i < HOLD_STEPS && WD->hold[i][0]; i++)
        if (S->held >= WD->hold[i][0])
            rows = WD->hold[i][1];
    return rows;
}

static void vertical(u32 obj, u8 *st, int rows)
{
    int row = S->w[S->cursor].row + rows;
    if (row < 0)
        row = 0;
    if (row >= S->rows)
        row = S->rows - 1;
    if (row == S->w[S->cursor].row)
        return;
    u32 id = nearest(row, S->remember);
    if (id != NO_ID)
        move_to(obj, st, id, SOUND_CURSOR, 0);
}

/* X: the forge's next tab, as FUN_009ca7e8's X (0x9CAA6C): the tab steps on (FUN_005e91ac's wrap and sound, made
   here: the forge passes it no seventh argument), its view kind set, the row shown again; the model opened on entering
   try on, the preview closed on any other. */
static void next_view(u32 obj, u8 *st)
{
    if (st[ST_VIEW] == VIEW_DETAIL)
        return;
    st[ST_X] = 1;
    u32 old = tab_kind(obj);
    s16 *tab = (s16 *)((u8 *)obj + OBJ_TAB), count = *(const s16 *)((const u8 *)obj + OBJ_TAB_COUNT);
    if (count > 1) {
        play(SOUND_VIEW);
        *tab = *tab + 1 >= count ? 0 : *tab + 1;
    }
    view_kind(obj, st + ST_VIEW, tab_kind(obj));
    forge_row_show(obj, st);
    u32 kind = tab_kind(obj);
    if (kind == VIEW_MODEL && kind != old) {
        u8 ref[REF_SIZE];
        make_record(equipment_control, ref, S->type, S->cursor);
        model_open(obj, ref, gear_armor(equipment_control, ref[0]) ? 1 : MODEL_WEAPON);
    } else {
        preview_close(obj);
    }
}

/* Every frame of the list, as FUN_009ca7e8's sub-state 0 after its keys: the model frame's touch and camera; once the
   model is loaded, the piece under the cursor on it while the preview is shown, else the hunter's own look. */
static void model_frame(u32 obj, u8 *st)
{
    model_input(obj);
    model_camera(obj, st, MODEL_WEAPON);
    u32 model = *(const u32 *)((const u8 *)obj + OBJ_MODEL);
    if (!model_ready(obj, model))
        return;
    if (!preview_mode[PREVIEW_SHOWN] || !model) {
        u8 *gear = *(u8 **)(*(const u32 *)((const u8 *)obj + OBJ_HUNTER) + HUNTER_GEAR);
        gear[GEAR_LOOK] = weapon_look(equipment_control, gear + GEAR_REF, 1, obj + OBJ_LOOK_A, obj + OBJ_LOOK_B);
    } else {
        u8 ref[REF_SIZE];
        make_record(equipment_control, ref, S->type, S->cursor);
        model_wear(model, ref, 1);
        st[ST_WORN_SHOWN] = 1;
    }
}

/* L / R: the status view's page ("L 1/2 R" on the stats panel), as the forge list's own L / R (FUN_009ca7e8, 0x9CAB..:
   nothing in the detail view; FUN_005ee9a0 = FUN_005ed674(page, pages, input, L, R, sound 0x1B, obj + 0xB8CC), then the
   page mark's arrow of that way). In try on the camera zooms with them held besides, as in the forge. */
static void stats_page(u32 obj, const u8 *st)
{
    if (st[ST_VIEW] == VIEW_DETAIL)
        return;
    u32 input = window_input(obj);
    s16 *page = (s16 *)((u8 *)obj + OBJ_PAGE);
    *page = pager_step(*page, *(const s16 *)((const u8 *)obj + OBJ_PAGES), input, BUTTON_L, BUTTON_R, SOUND_STATS_PAGE,
                       (u32 *)((u8 *)obj + OBJ_PAGER));
    if (input & BUTTON_L)
        pager_left();
    else if (input & BUTTON_R)
        pager_right();
}

/* The keys of the tree, the same in every view: the D-pad moves the cursor in try on too (the forge's list moves with
   it there; the camera turns with the stick and zooms with L / R held, FUN_009fc74c). Not inlined: update would outgrow
   Thumb's b. */
static __attribute__((noinline)) void keys(u32 obj, u8 *st)
{
    u32 dirs = facility_dirs(obj), rows = held_rows(), id;
    st[ST_X] = 0;
    if (facility_pressed(obj, BUTTON_B)) {
        tree_close(obj, st);
    } else if (facility_pressed(obj, BUTTON_A)) {
        if (BUYING)
            ask(obj, st);
        else
            play(SOUND_ERROR);
    } else if (facility_pressed(obj, BUTTON_X)) {
        next_view(obj, st);
    } else if (facility_pressed(obj, BUTTON_L | BUTTON_R)) {
        stats_page(obj, st);
    } else if (dirs & DIR_UP) {
        vertical(obj, st, -(int)rows);
    } else if (dirs & DIR_DOWN) {
        vertical(obj, st, rows);
    } else if (dirs & DIR_LEFT) {
        id = beside(-1);
        if (id == NO_ID)
            id = S->w[S->cursor].parent;
        if (id != NO_ID)
            move_to(obj, st, id, SOUND_CURSOR, 1);
    } else if (dirs & DIR_RIGHT) {
        id = beside(1);
        if (id != NO_ID)
            move_to(obj, st, id, SOUND_CURSOR, 1);
    }
}

/* ----- the entries ------------------------------------------------------------------------------------------ */

/* A weapon class chosen in Forge Weapons (st + 7 its equipment type): the tree read and placed; 1 if it has a row, and
   state 7 shows it from the next frame. */
static __attribute__((noinline)) u32 enter(u32 obj, u8 *st)
{
    S->open = CLOSED;
    S->type = st[ST_TYPE];
    S->rows = S->columns = 0;
    S->count = 0;
    if (S->type < FIRST_TYPE || S->type >= FIRST_TYPE + CLASSES)
        return 0;
    read_weapons();
    read_links(obj);
    read_box();
    read_upgrades();
    discover();
    place();
    if (!S->rows)
        return 0;
    S->open = BUILT;
    return 1;
}

static void rebuild(u32 obj, u8 *st, u32 id)
{
    u32 top = S->top, left = S->left;
    enter(obj, st);
    S->open = OPEN;
    S->top = top;
    S->left = left;
    S->cursor = S->w[id].row != NO_ROW ? id : nearest(0, 0);
    S->remember = S->w[S->cursor].column;
    follow();
    light();
    draw();
    show_stats(obj, st);
}

/* As FUN_009e5734 draws state 4's list: the materials box and the panels hidden, then the status view and the money. */
static void status_frame(u32 obj, u8 *st)
{
    for (u32 g = 0; g < MATERIAL_GROUPS; g++)
        gui_group_show(materials_groups[g], 0);
    panels_hide();
    status_draw(obj, st + ST_VIEW, 1, 1);
    draw_money(obj);
}

/* Every frame of the Smithy's state 7. No jump table: Thumb's needs a library function the block does not have. */
__attribute__((noinline, optimize("no-jump-tables"))) static void update(u32 obj, u8 *st)
{
    if (S->open == CLOSED) {         /* no tree built: back to the class menu */
        tree_close(obj, st);
        return;
    }
    if (S->open == BUILT)
        tree_show(obj, st);
    u32 sub = S->sub;
    if (sub == T_LIST) {
        keys(obj, st);
        if (S->open != OPEN)
            return;
        if (S->sub == T_LIST)
            model_frame(obj, st);
        status_frame(obj, st);
        if (S->sub == T_LIST || S->sub == T_CHOICE)
            list_help(st);           /* the window's first frame too: its line is the way its cursor opens on */
    } else if (sub == T_CHOICE) {
        choice_keys(obj, st);
        model_camera(obj, st, MODEL_WEAPON);     /* as the prompt: a model try on left is put away */
        status_frame(obj, st);
        if (S->sub != T_PROMPT)
            list_help(st);           /* of the way under the window's cursor */
    } else if (sub == T_PROMPT) {
        model_camera(obj, st, MODEL_WEAPON);     /* as FUN_009ca7e8's sub-state 1 */
        status_frame(obj, st);
        prompt(obj, st);
    } else if (sub == T_SCENE_START) {
        scene_hide(obj);
        S->sub = T_SCENE;            /* the scene's state settles first, as the forge's sub-state 2 */
    } else if (sub == T_SCENE) {
        scene_end(obj, st);
    } else if (sub == T_EQUIP) {
        if (S->buy == BUY_UPGRADE)
            status_frame(obj, st);
        equip(obj, st);
    } else if (sub == T_BOX) {
        box_shown(obj, st);
    }
}

/* The Smithy ends (FUN_009bb1ac), also closed by force while state 7 is on: our groups hidden and the screen closed, so
   nothing of the tree stays up on the next screen. Nothing else: the game is tearing the Smithy down itself. */
static __attribute__((noinline)) void smithy_end(void)
{
    if (S->open == CLOSED)
        return;
    groups_show(0);
    screens_open = 0;
    S->open = CLOSED;
    S->sub = T_LIST;
}

ARM void weapon_tree_end(void)
{
    smithy_end();
}

/* A on a box weapon in Upgrade (FUN_009bdb58's sub-state 0, where FUN_00a02048 would list its upgrades; st + 7 its
   type, obj + 0xBC78 its slot): the class's tree on that weapon, whose upgrades then take that copy. Left to the game:
   another mode, a customized piece, a bowgun (its list also sells attachments), a weapon with no upgrade (the game's
   refusal). Taken: the status view as the forge's entry sets it, state 7 from the next frame, the decide sound; the
   game's own path on then hides the box and binds the stats panels (0x9BDD5C, st[1] not 0). */
static __attribute__((noinline)) u32 from_box(u32 obj, u8 *st, const u8 *ref)
{
    u16 kids[UPGRADE_KIDS];
    u32 type = ref[0], id = rd16(ref + REF_ID);
    if (st[ST_MODE] != MODE_UPGRADE || type == LIGHT_BOWGUN || type == HEAVY_BOWGUN
        || customized(equipment_control, ref))
        return 0;
    S->fixed = NO_SLOT;
    if (!enter(obj, st) || id >= S->count || S->w[id].row == NO_ROW || !children_of(id, kids)) {
        S->open = CLOSED;
        return 0;
    }
    S->fixed = *(u16 *)((u8 *)obj + OBJ_BOX_SLOT);
    status_reset(obj, st, 1);
    st[0] = STATE_TREE;
    st[ST_SUB] = 1;
    play(SOUND_DECIDE);
    return 1;
}

/* Every frame of an open tree: each "NEW" shown takes the brightness of the forge list's own "NEW" (curated `new_pulse`:
   ui407's clip on ui407_n_icon, its keys joined by straight lines and looped), the clip's time going on by the frame's
   time as the game's players go, so it pulses as fast at any frame rate. The marks are the group's P_NEW panes, one
   after the other (walk_sprite); a hidden one is left as it is. ARM: it computes with floats. */
ARM static void new_pulse(void)
{
    const float (*key)[2] = WD->pulse;
    float end = key[PULSE_KEYS - 1][0], t = S->pulse * (1.0f / PULSE_STEPS) + *(const float *)(game_main + MAIN_DELTA);
    while (t >= end)
        t -= end;
    S->pulse = (u8)(t * PULSE_STEPS);
    u32 k = 1;
    while (k < PULSE_KEYS - 1 && t >= key[k][0])
        k++;
    union { float f; u32 bits; } bright = {key[k - 1][1] + (key[k][1] - key[k - 1][1]) * (t - key[k - 1][0])
                                                            / (key[k][0] - key[k - 1][0])};
    struct walk w = {{0, 0}, group_of(G_NODES)};
    u32 at = H_CELLS + P_NEW * MAX_ROWS * MAX_COLUMNS;
    for (u32 cell = 0; cell < MAX_ROWS * MAX_COLUMNS; cell++, at++) {
        u32 *sprite = walk_sprite(&w, WD->hashes[at]);
        if (sprite && sprite[SP_FLAGS] & SP_SHOWN && sprite[SP_BRIGHT] != bright.bits) {
            sprite[SP_BRIGHT] = bright.bits;
            kit_sprite_changed(&w.r);
        }
    }
}

/* The ARM entries of the hooks (the rest is Thumb, but new_pulse). */
ARM u32 weapon_tree_enter(u32 obj, u8 *st)
{
    S->fixed = NO_SLOT;
    return enter(obj, st);
}

ARM u32 weapon_tree_from_box(u32 obj, u8 *st, const u8 *ref)
{
    return from_box(obj, st, ref);
}

ARM void weapon_tree_update(u32 obj, u8 *st)
{
    update(obj, st);
    if (S->open == OPEN)
        new_pulse();
}

/* ----- the hooks -------------------------------------------------------------------------------------------- */

__asm__(
    "   .section .text.entry, \"ax\", %progbits\n"
    "   .arm\n"
    "   .global weapon_tree_smithy_update, weapon_tree_entry\n"
    /* word 7 of the Smithy's state table: r4 = st, r5 = obj; leaves by the switch's end */
    "weapon_tree_smithy_update:\n"
    "   mov     r0, r5\n"
    "   mov     r1, r4\n"
    "   bl      weapon_tree_update\n"
    "   b       smithy_done\n"
    /* "b 0x9ADC1C" of state 2's A on a weapon class: r4 = st, r5 = obj, r0-r3, r12 and lr free. State 7 when the tree
       has a row; the forge's entry runs on in every case */
    "weapon_tree_entry:\n"
    "   mov     r0, r5\n"
    "   mov     r1, r4\n"
    "   bl      weapon_tree_enter\n"
    "   cmp     r0, #0\n"
    "   ldrb    r0, [r4]\n"
    "   movne   r0, #" STR(STATE_TREE) "\n"
    "   strb    r0, [r4]\n"
    "   b       forge_join\n"
    /* "bl FUN_0027ff58" at 0x9BB1B4, FUN_009bb1ac's first call (the Smithy's end): the tree closed, then that call with
       the registers and the return as they were */
    "   .global weapon_tree_smithy_end\n"
    "weapon_tree_smithy_end:\n"
    "   push    {r0-r3, r12, lr}\n"
    "   bl      weapon_tree_end\n"
    "   pop     {r0-r3, r12, lr}\n"
    "   b       panels_release\n"
    /* "bl FUN_00a02048" at 0x9BDC70, Upgrade's A on a box weapon: r0-r3 that call's arguments, r4 = st, r6 = the box
       reference, r8 = obj; r12 and lr free (FUN_009bdb58 saved lr). The tree when it takes the weapon, then the game's
       own path on at 0x9BDD5C; else the game's call and back after it */
    "   .global weapon_tree_upgrade\n"
    "weapon_tree_upgrade:\n"
    "   push    {r0-r3}\n"
    "   mov     r0, r8\n"
    "   mov     r1, r4\n"
    "   mov     r2, r6\n"
    "   bl      weapon_tree_from_box\n"
    "   cmp     r0, #0\n"
    "   pop     {r0-r3}\n"
    "   beq     1f\n"
    "   b       upgrade_shown\n"
    "1: bl      upgrade_list\n"
    "   b       upgrade_listed\n"
);
