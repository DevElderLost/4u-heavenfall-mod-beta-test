/* The Smithy's weapon tree (option weapon_tree): the data block the patcher writes
 * (interface/weapon_tree/weapon_tree.py, data_block) and the state the screen keeps (the variable weapon_tree_state).
 * The pane indices follow interface/weapon_tree/panes.py hash_names(); test_weapon_tree_patch.py checks that they
 * agree. */

#ifndef WEAPON_TREE_H
#define WEAPON_TREE_H

#define GAME __attribute__((long_call))
#define ARM __attribute__((target("arm"), noinline))
#define STR2(x) #x
#define STR(x) STR2(x)

#include "../screen_kit/screen_kit.h"

typedef signed short s16;

/* ----- the panes (panes.py hash_names: the groups, then each group's panes) ---------------------------------- */

#define WT_GROUPS 6
enum { G_FRAME, G_ROWS, G_NODES, G_CURSOR, G_KEYS, G_CHOICE };
#define TREE_GROUPS 5            /* the first ones: the screen's (panes.py TREE_GROUPS); G_CHOICE only while it asks */
#define MAX_ROWS 7               /* panes.py MAX_ROWS, MAX_COLUMNS: the cells the layout holds */
#define MAX_COLUMNS 7
#define BAND_PIECES 3
enum { P_PLATE, P_LINK, P_TRUNK, P_TRUNK_LOW, P_ICON, P_FORGE, P_WORN, P_BOX, P_ELEMENT, P_NEW, CELL_PIECES };  /* panes.py */
#define FRAME_PANES 7
#define H_FRAME WT_GROUPS                        /* the frame's four sides, its inside, the header's two bars */
#define H_BANDS (H_FRAME + FRAME_PANES)          /* BAND_PIECES a row */
#define H_CELLS (H_BANDS + MAX_ROWS * BAND_PIECES)   /* piece by piece, each row by row, each column by column */
#define H_NAME (H_CELLS + CELL_PIECES * MAX_ROWS * MAX_COLUMNS)
#define H_COUNT (H_NAME + 1)
#define H_BRACKET (H_COUNT + 1)                  /* 2: the game's bracket, left and right halves */
#define H_LINES (H_BRACKET + 2)                  /* 4: the thin frame, top, bottom, left, right */
#define H_KEY_BAR (H_LINES + 4)
#define H_HINT (H_KEY_BAR + 1)
#define H_ARROWS (H_HINT + 1)                    /* 4: left, right, up, down */
#define H_CHOICE (H_ARROWS + 4)                  /* the window "upgrade or craft" (panes.py choice_panes) */
#define CHOICE_OPTIONS 2                         /* row 0 upgrade, row 1 craft */
#define CH_BACK 0                                /* its fill, */
#define CH_EDGE (CH_BACK + 1)                    /* 4: the thin edge, */
#define CH_HEAD (CH_EDGE + 4)                    /* 2: the title's bar, */
#define CH_ROWS (CH_HEAD + 2)                    /* BAND_PIECES an option: its row bar, */
#define CH_CURSOR (CH_ROWS + CHOICE_OPTIONS * BAND_PIECES)   /* BAND_PIECES an option: the cursor bar over it, */
#define CH_TITLE (CH_CURSOR + CHOICE_OPTIONS * BAND_PIECES)  /* the title, */
#define CH_WORDS (CH_TITLE + 1)                  /* and each option's word */
#define WT_HASHES (H_CHOICE + CH_WORDS + CHOICE_OPTIONS)
_Static_assert(WT_HASHES == 560, "panes.py hash_names()");

/* ----- the data block weapon_tree_data (weapon_tree.py data_block) -------------------------------------------- */

enum { C_BAND, C_BAND_ALT, C_PLATE, C_PLATE_LIT, C_PLATE_OWNED, C_LINK, C_LINK_LIT, C_WORN, C_CURSOR, C_KEY_BAR, C_HINT,
       C_COUNT, C_ARROW, C_UNPAYABLE, C_FORGE, C_CHOICE_ON, C_CHOICE_OFF, C_ELEMENT, C_ELEMENT_HIDDEN, C_BOX,
       WT_COLOURS };                                 /* weapon_tree.py COLOURS */
#define ELEMENT_ICONS 9          /* the stats panel's element and status icons (node_marks.py ELEMENTS) */
/* The game's messages the tree shows from its own copies with the verb in capitals (tree_texts.py CAPS_SOURCES): the
   forge's help line and price question, then Upgrade's. */
enum { CAPS_FORGE_OK, CAPS_FORGE_SHORT, CAPS_FORGE_MONEY, CAPS_FORGE_BOTH, CAPS_FORGE_FULL, CAPS_FORGE_PRICE,
       CAPS_UPGRADE_OK, CAPS_UPGRADE_DECOS, CAPS_UPGRADE_SHORT, CAPS_UPGRADE_MONEY, CAPS_UPGRADE_BOTH,
       CAPS_UPGRADE_PRICE, CAPS_MESSAGES };
enum { CHOICE_TITLE, CHOICE_UPGRADE, CHOICE_FORGE };     /* tree_texts.py CHOICE: from msg_choice */
enum { REVEAL_ALL, REVEAL_DISCOVERED };              /* weapon_tree.py REVEALS */
enum { STYLE_BRACKET, STYLE_FRAME };                 /* weapon_tree.py STYLES */
#define HOLD_STEPS 4
#define PULSE_KEYS 3             /* the "NEW" marks' clip (weapon_tree.py PULSE_KEYS): its keys, the last one's frame its
                                    length */
#define PULSE_STEPS 4            /* wt_state.pulse counts the clip's time in quarter frames */

struct wt_data {
    u32 magic;                   /* WT_MAGIC */
    u8 priority[WT_GROUPS];      /* each group's in front of the GUI's (curated `priority`) */
    u8 reveal, columns, rows;    /* REVEAL_*; the window's columns and rows (at most MAX_COLUMNS, MAX_ROWS) */
    u8 style, pack;              /* the cursor's STYLE_*; the most lone roots in a row */
    u8 unpayable_mix;            /* the grey's share (percent) in the colour of a weapon that cannot be bought now */
    u16 origin_x, origin_y;      /* the icon of cell (0, 0), top screen pixels */
    u16 pitch_x, pitch_y;        /* from a cell to the next */
    s16 icon_x, icon_y;          /* the icon's box in its cell (the thin frame goes round it) */
    u16 icon_w, icon_h;
    s16 bracket[4];              /* the bracket's two halves: x, y of each from the icon's cell */
    u16 bracket_w, bracket_h;
    u16 frame_pad, frame_thickness;
    float pulse[PULSE_KEYS][2];  /* the "NEW" marks' brightness: each key's frame and value (curated `new_pulse`) */
    u32 colours[WT_COLOURS];     /* as the panes hold them: R in the low byte, alpha in the high one */
    u16 hold[HOLD_STEPS][2];     /* up or down held: from [0] frames on, [1] rows a step; 0 frames ends the steps */
    u16 msg_count, msg_hint;     /* E_makeshop: the counter "row/rows" (string slot 0 alone), the key bar's words */
    u16 text_file, name_files;   /* the lobby file of those (E_makeshop); the common file of the first class's names */
    u16 msg_caps, msg_choice;    /* E_makeshop: the first of the CAPS_* copies; the first of the CHOICE_* words */
    u32 element_uv[ELEMENT_ICONS][2];   /* each icon's corner in the marks' texture: u, v as float bits */
    u32 hashes[WT_HASHES];
};
#define WT_MAGIC 0x31525457u     /* "WTR1" */
#define WT_DATA_HEAD 252
_Static_assert(__builtin_offsetof(struct wt_data, hashes) == WT_DATA_HEAD, "weapon_tree.py DATA_HEAD");
_Static_assert(sizeof(struct wt_data) == WT_DATA_HEAD + 4 * WT_HASHES, "game/executable/blocks.py WEAPON_TREE_DATA_SIZE");

extern const struct wt_data weapon_tree_data __attribute__((aligned(4)));
#define WD (&weapon_tree_data)

/* ----- the state: the variable weapon_tree_state ---------------------------------------------------------------- */

#define MAX_IDS 336              /* the ids of a class the tree reads (weapon_tree.py MAX_IDS) */
#define NO_ID 0xFFFF
#define NO_ROW 0xFF              /* a weapon not placed */
#define MAX_PLACED_ROWS 255
#define MAX_DEPTH 32             /* the steps of a line the placing follows */

/* weapon.flags */
#define W_REAL 0x01              /* the flags' low two bits 1 or 2 */
#define W_SHOWN 0x02             /* discovered (or every weapon in a line or with a recipe, REVEAL_ALL) */
#define W_OWNED 0x04             /* a copy in the box */
#define W_WORN 0x08
#define W_NEW 0x10               /* the save's "new" bit */
#define W_UPGRADE 0x20           /* a copy in the box upgrades into it now (money and materials held) */
#define W_LIT 0x40               /* on the lineage from its root to the cursor */
#define W_LISTED 0x80            /* its create recipe is listed by the forge */
/* weapon.info */
#define I_RARITY 0x0F            /* the rarity index (0-9) */
#define I_RECIPE 0x10            /* it has a create recipe */
#define I_CHILD 0x20             /* a real weapon upgrades into it */
#define I_HAD 0x40               /* the hunter has had it once */
#define I_FORGE 0x80             /* its create recipe can be paid now */

struct weapon {                  /* one id of the class */
    u16 parent;                  /* the shown weapon it hangs from (the lowest id); NO_ID: none, a root if placed */
    u8 row, column;              /* where it is placed; row NO_ROW: not */
    u8 info, flags;
};
_Static_assert(sizeof(struct weapon) == 6, "weapon_tree.py STATE_SIZE");

enum { CLOSED, BUILT, OPEN };    /* wt_state.open: the first frame of state 7 draws a BUILT tree */
/* wt_state.sub: what state 7 is doing (the forge's sub-states) */
enum { T_LIST, T_PROMPT, T_SCENE_START, T_SCENE, T_EQUIP, T_BOX, T_CHOICE };
enum { BUY_FORGE, BUY_UPGRADE }; /* wt_state.buy */

struct wt_state {
    u8 open, type, melee, remember;   /* CLOSED / BUILT / OPEN; the class's equipment type; the column Up / Down keep */
    u16 held, count;             /* the frames up or down has been held; the class's ids read */
    u16 rows, columns;           /* rows placed; the widest row's columns */
    u16 cursor, top;             /* the cursor's id; the window's first row */
    u16 left;                    /* the window's first column */
    u16 fixed;                   /* entered from Upgrade: the box slot chosen there (its weapon's upgrades take it), and
                                    B goes back to the box; NO_SLOT from Forge Weapons */
    u16 recipe[12];              /* an upgrade's materials at + 4 (as a create recipe holds them): the status view's */
    u16 count_text[12];          /* "999/999" and its end: the string slot keeps the address */
    u8 sub, buy;                 /* T_*; BUY_* of the purchase shown, asked or made */
    u8 chosen;                   /* 1: the purchase asked went through the window "upgrade or craft" */
    u8 pulse;                    /* the "NEW" marks' clip time, in 1 / PULSE_STEPS of its frames */
    u16 copy;                    /* the box slot upgraded (BUY_UPGRADE) */
    u16 bought, index;           /* the weapon bought; the create recipe's index in the table (BUY_FORGE) */
    u16 price_text[8];           /* the price, for the prompt's string slot */
    struct weapon w[MAX_IDS];
};
#define WT_STATE_HEAD 94
#define WT_STATE_SIZE (WT_STATE_HEAD + 6 * MAX_IDS)
_Static_assert(__builtin_offsetof(struct wt_state, w) == WT_STATE_HEAD, "weapon_tree.py STATE_HEAD");
_Static_assert(sizeof(struct wt_state) == WT_STATE_SIZE, "game/executable/blocks.py WEAPON_TREE_STATE_SIZE");

extern struct wt_state weapon_tree_state;
#define S (&weapon_tree_state)

#endif
