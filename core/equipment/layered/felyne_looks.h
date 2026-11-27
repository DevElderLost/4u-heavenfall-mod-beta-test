/* The Felynes' looks of layered equipment: what the screens (layered_forge.c) ask of felyne_looks.c. */

#ifndef FELYNE_LOOKS_H
#define FELYNE_LOOKS_H

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

/* The town block (layered_town) calls the resident code by address, as it calls the game's: a long call. */
#ifdef LAYERED_TOWN
#define RESIDENT __attribute__((long_call))
#else
#define RESIDENT
#endif

enum { FELYNE_HEAD, FELYNE_BODY, FELYNE_WEAPON, FELYNE_PARTS };
#define FELYNE_MAX_ACTIVE 2
#define FELYNE_NUMBER_BITS 10
#define FELYNE_NUMBER_MASK 0x3FFu

#define FELYNE_KNOWN_BYTES 42    /* felyne_looks.py KNOWN_BYTES: a bit per model number */
#define FELYNE_CASES 10          /* felyne_looks.py CASES */
struct felyne_case {             /* a number of the game whose piece its code goes by the id of */
    u16 number;                  /* 0: an empty place */
    u8 part, piece;
};
struct felyne_data {             /* the block felyne_looks_data (felyne_looks.py, HEADER) */
    u32 magic;
    u16 total, ids;              /* the looks of the catalog; the numbers the bitmaps hold */
    u16 msg_felynes, msg_none, msg_choose, pad;
    u8 known[FELYNE_PARTS][FELYNE_KNOWN_BYTES];
    u8 pad2[2];
    struct felyne_case cases[FELYNE_CASES];
    u8 suits[FELYNE_KNOWN_BYTES];  /* a bit per body number: a whole suit of MH XX, its head the helm of its number */
    u8 pad3[2];
};
_Static_assert(sizeof(struct felyne_data) == 228, "felyne_looks.py HEADER");
extern const struct felyne_data felyne_looks_data;

struct felyne_ui {              /* the variable felyne_ui */
    u8 cat;                     /* the cat the screen is of: its place among felyne_active() */
    u8 pad;
    u8 dirty;                   /* a look changed since the screens opened */
    u8 preview;                 /* the screen's Felyne preview is on: its actor wears the numbers tried on */
    const u8 *select[3];        /* the hunter select screen's Felyne records, per slot (felyne_select_note) */
    const u8 *shown;            /* the actor FUN_00697348 is showing the parts of (felyne_show_note) */
};
_Static_assert(sizeof(struct felyne_ui) == 20, "felyne_ui size (game/executable/blocks.py)");
_Static_assert(__builtin_offsetof(struct felyne_ui, shown) == 16, "felyne_show_note, felyne_suit_show");
extern struct felyne_ui felyne_ui;

/* The active cats' records (at most FELYNE_MAX_ACTIVE), and how many. */
RESIDENT u32 felyne_active(const u8 **cats);
/* The numbers the chosen cat's look word holds (3 x FELYNE_NUMBER_BITS, none for what this build lacks), and writing
   them; 0 and nothing when the cat is gone. */
RESIDENT u32 felyne_numbers(void);
RESIDENT void felyne_set_numbers(u32 numbers);
/* The online half (layered_online.c): the word the main cat sends (0 none), whether a received word is wholly known, and a
   remote cat's record taking its owner's word. */
u32 felyne_online_word(void);
/* The town's own cats (`town` the town object) take their records' gear again: their looks follow the switch. */
void felyne_redress(u32 town);
int felyne_word_known(u32 word);
void felyne_give_word(u8 *record, u32 word);
/* The cats in the town take their looks (leaving the screens, when felyne_ui.dirty). */
RESIDENT void felyne_refresh(u32 obj);
/* The screen's Felyne preview: the chosen cat wearing `numbers`. */
RESIDENT void felyne_preview_open(u32 obj, u32 numbers);
RESIDENT int felyne_preview_loaded(u32 obj);
RESIDENT void felyne_preview_look(u32 obj, u32 numbers);
RESIDENT void felyne_preview_controls(u32 obj);
RESIDENT void felyne_preview_end(u32 obj);

#endif
