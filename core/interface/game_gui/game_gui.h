/* MH4U's GUI objects (the Python readers are
 * core/interface/game_gui/structs.py, whose constants tests/interface/game_gui/test_gamegui_structs.py checks against the GG_ defines here).
 *
 * Addresses are canonical (the EUR update's executable); a patch built for another version gets them through its
 * version map like any other patch. Fields marked "?" are not understood; unnamed bytes are padding of unknown use.
 */
#ifndef GAME_GUI_H
#define GAME_GUI_H

#include <stddef.h>

typedef unsigned int gg_u32;
typedef unsigned short gg_u16;
typedef unsigned char gg_u8;

/* --- statics and functions (canonical) ---------------------------------------------------------------------------- */
#define GG_SLAYOUT_POINTER 0x1057534   /* sMhLayout *: the main GUI (sLayout's subclass) */
#define GG_SUNIT_POINTER 0x10572F8     /* sMhUnit *: the units' 32 move lines */
#define GG_ULAYOUT_VTABLE 0xE6BB40     /* uLayout (DTI 0x10E9118) */
#define GG_FN_LAYOUT_DRAW 0xB047C4 /* uLayout::draw (vtable slot 12): draws its draw list in the current view */
#define GG_FN_GROUP_SHOW 0xAE53E0 /* (group, shown): sets 0x400 and links / unlinks the draw list */
#define GG_FN_PANE_REDRAW 0xAE6BCC /* (group, pane): queues a pane whose data changed */
#define GG_FN_TEXT_SET 0xAE4EF0 /* (text pane, group, utf16, length, ...): lays out a string as glyph sprites */
#define GG_FN_PLAYER_UPDATE 0xAE1DDC /* an animation player's frame step */
#define GG_FRAME_HOOK 0xAF555C         /* sMhMain::frame: `ldr r0, [r4, #0x290]` before the render call */
#define GG_DRAW_VIEW_TEST 0xB0481C     /* uLayout::draw: `lsl r1, r1, #0xe` before `cmp r5, r1, lsr #28` */

/* --- views -------------------------------------------------------------------------------------------------------- */
#define GG_VIEW_TOP 0                  /* sMhLayout + 0x245 */
#define GG_VIEW_BOTTOM 7               /* sMhLayout + 0x246: the touch screen */

/* --- a pool (uLayout + 0x64 ... + 0xF0, sMhLayout + 0x220) -------------------------------------------------------- */
typedef struct gg_pool {
    gg_u32 slab;                       /* count elements of size, then the pointer array */
    gg_u32 size;
    gg_u32 count;
    gg_u32 used;                       /* the array's [used:] are free */
    gg_u32 array;
} gg_pool;

/* --- sMhLayout (0x248) -------------------------------------------------------------------------------------------- */
#define GG_SLAYOUT_DRAW_BUFFER 0xB0
#define GG_SLAYOUT_FONTS 0xDC
#define GG_SLAYOUT_MAIN 0x100
#define GG_SLAYOUT_TOP_VIEW 0x245
#define GG_SLAYOUT_BOTTOM_VIEW 0x246
#define GG_SLAYOUT_PLAYERS 0x220

/* --- uLayout (0x198), a cUnit ------------------------------------------------------------------------------------- */
typedef struct gg_layout {
    gg_u32 vtable;
    gg_u32 unit_flags;                 /* cUnit: bits 3-9 move line, 16-25 mDrawView (bit 16 + view) */
    gg_u32 unit_0x08;
    gg_u32 next_unit;                  /* cUnit: next unit of its move line */
    gg_u8 unit_0x10[0x20];
    gg_u32 buffers[6];                 /* +0x30: 2 vertex buffers, 2 null matrices, 2 window buffers (? the last) */
    gg_u8 _0x48[0x1C];
    gg_pool groups;                    /* +0x64: 0x50 each */
    gg_pool panes;                     /* +0x78: 0x24 */
    gg_pool sprites;                   /* +0x8C: 0x68 */
    gg_pool windows;                   /* +0xA0: 0x88 */
    gg_pool nulls;                     /* +0xB4: 0x30 */
    gg_pool texts;                     /* +0xC8: 0x80 */
    gg_pool boundaries;                /* +0xDC: 0x30 */
    gg_pool tracks;                    /* +0xF0: 0x18, animation tracks */
    gg_u32 pool_refs[7];               /* +0x104: the pools' addresses (a group's context points here) */
    gg_u32 draw_first;                 /* +0x120: the draw list (shown groups, ascending index) */
    gg_u32 draw_last;
    gg_u8 _0x128[0x2C];
    gg_u32 group_list;                 /* +0x154: group *[group_count] */
    gg_u32 texture_list;
    gg_u32 flags;                      /* +0x15C: 0-3 the view of new groups, 0x10 fill texts at load */
    gg_u32 group_count;                /* +0x160 */
    gg_u8 _0x164[0x28];
    gg_u32 slab;                       /* +0x18C: group list, texture lists, one allocation */
    gg_u32 slab_size;
    gg_u32 slab_used;
} gg_layout;

#define GG_LAYOUT_GROUPS 0x64
#define GG_LAYOUT_PANES 0x78
#define GG_LAYOUT_DRAW_LIST 0x120
#define GG_LAYOUT_GROUP_LIST 0x154
#define GG_LAYOUT_GROUP_COUNT 0x160
#define GG_LAYOUT_SLAB 0x18C

/* --- a root group (0x50) ------------------------------------------------------------------------------------------ */
typedef struct gg_group {
    gg_u32 hash;                       /* ~crc32 of the name (game/files/gui/lyt.py name_hash) */
    gg_u32 name;                       /* char * (in the layout resource) */
    gg_u32 first_pane;
    gg_u32 redraw_first, redraw_last;  /* panes queued for a redraw */
    gg_u32 context;                    /* &uLayout + 0x104 */
    gg_u32 order;                      /* +0x18: bits 27-31 layer, 19-26 priority */
    gg_u32 commands[2];                /* cached GPU command lists, one per draw buffer */
    gg_u32 textures;
    float x, y, z;                     /* +0x28 */
    gg_u32 _0x34, _0x38;               /* ? 0 */
    gg_u32 color;                      /* +0x3C: RGBA, alpha byte at + 0x3F */
    gg_u32 revision;                   /* +0x40: byte + 0x42 the buffers to rebuild */
    gg_u32 flags;                      /* +0x44: GG_SHOWN, view bits 14-17, index bits 18-31 */
    gg_u32 next, previous;             /* +0x48: the draw list */
} gg_group;

#define GG_GROUP_HASH 0x00
#define GG_GROUP_FIRST_PANE 0x08
#define GG_GROUP_ORDER 0x18
#define GG_GROUP_POSITION 0x28
#define GG_GROUP_FLAGS 0x44
#define GG_GROUP_NEXT 0x48
#define GG_SHOWN 0x400
#define GG_VIEW_SHIFT 14
#define GG_VIEW_MASK 0xF
#define GG_INDEX_SHIFT 18

/* --- a pane (0x24) ------------------------------------------------------------------------------------------------ */
typedef struct gg_pane {
    gg_u32 hash;
    gg_u32 name;
    gg_u32 data;                       /* the kind's data */
    gg_u32 redraw;                     /* its redraw node, if queued */
    gg_u8 kind;                        /* GG_SPRITE ... GG_WINDOW */
    gg_u8 depth;                       /* 1 under the group */
    gg_u8 dirty;
    gg_u8 _0x13;
    gg_u32 next, previous, parent, child;
} gg_pane;

#define GG_PANE_DATA 0x08
#define GG_PANE_KIND 0x10
#define GG_PANE_NEXT 0x14
#define GG_PANE_PARENT 0x1C
#define GG_PANE_CHILD 0x20
#define GG_SPRITE 0
#define GG_NULL 1
#define GG_TEXT 2
#define GG_BOUNDARY 3
#define GG_WINDOW 4

/* --- the kinds' data ---------------------------------------------------------------------------------------------- */
typedef struct gg_sprite {             /* 0x68 */
    gg_u32 texture;                    /* glyphs: the font's texture word, flags in the top byte */
    gg_u32 cell;                       /* +0x04, the texture's index: glyphs the page (low byte), icons the icon */
    gg_u32 _0x08, _0x0c;
    float x, y, z;                     /* +0x10 */
    gg_u32 _0x1c;
    float width, height;               /* +0x20 */
    float scale_x, scale_y;            /* +0x28 */
    float u, v, uw, vh;                /* +0x30 */
    gg_u32 colors[4];                  /* +0x40: RGBA corners */
    gg_u32 _0x50[2];
    gg_u32 _0x58_flags;                /* bits 0-3 origin, 7 visible, 8-31 primitive */
    gg_u32 _0x5c, _0x60, _0x64;
} gg_sprite;

typedef struct gg_null {               /* 0x30 */
    float x, y, z;
    gg_u32 _0x0c;
    float scale_x, scale_y;            /* +0x10 */
    gg_u32 color;                      /* +0x18 */
    gg_u32 _0x1c[2];
    gg_u32 flags;                      /* +0x24: bit 0 visible */
    gg_u32 _0x28, _0x2c;
} gg_null;

typedef struct gg_text {               /* 0x80 */
    gg_u32 null_data;                  /* its holder null's data */
    gg_u32 _0x04;
    float font_width, font_height;     /* +0x08 */
    float spacing_x, spacing_y;        /* +0x10 */
    float x, y, z;                     /* +0x18 */
    gg_u32 _0x24, _0x28, _0x2c;
    float box_width, box_height;       /* +0x30 */
    gg_u32 colors[4];                  /* +0x38 */
    gg_u32 _0x48[5];
    gg_u32 flags;                      /* +0x5C: 0-3 align, 4-7 origin, 8-15 font, 24-27 outline layers, 28 visible */
    gg_u32 font_texture[3];            /* +0x60 */
    gg_u32 length;                     /* +0x6C: characters of the last string set */
    gg_u32 glyphs;                     /* +0x70: glyph sprites held */
    gg_u32 capacity;                   /* +0x74 */
    gg_u32 _0x78, _0x7c;
} gg_text;

typedef struct gg_boundary {           /* 0x30 */
    float x, y, width, height, scale_x, scale_y;
    gg_u8 origin;                      /* +0x18 */
    gg_u8 _0x19[7];
    float left, top, right, bottom;    /* +0x20 */
} gg_boundary;

#define GG_TEXT_FLAGS 0x5C
#define GG_TEXT_LENGTH 0x6C

/* --- an animation player (0x30, sMhLayout + 0x220's pool; scenes embed their own) --------------------------------- */
typedef struct gg_player {
    gg_u32 resource, clip;
    gg_u32 active[2], finished[2];     /* track lists */
    float start, end, previous, frame, speed;
    gg_u32 flags;                      /* 0x10000 loop, 0x40000 paused, 0x8000000 reverse */
} gg_player;

_Static_assert(sizeof(gg_layout) == 0x198, "uLayout");
_Static_assert(offsetof(gg_layout, groups) == GG_LAYOUT_GROUPS, "uLayout groups");
_Static_assert(offsetof(gg_layout, draw_first) == GG_LAYOUT_DRAW_LIST, "uLayout draw list");
_Static_assert(offsetof(gg_layout, group_list) == GG_LAYOUT_GROUP_LIST, "uLayout group list");
_Static_assert(offsetof(gg_layout, group_count) == GG_LAYOUT_GROUP_COUNT, "uLayout group count");
_Static_assert(offsetof(gg_layout, slab) == GG_LAYOUT_SLAB, "uLayout slab");
_Static_assert(sizeof(gg_group) == 0x50 && offsetof(gg_group, flags) == GG_GROUP_FLAGS, "group");
_Static_assert(sizeof(gg_pane) == 0x24 && offsetof(gg_pane, child) == GG_PANE_CHILD, "pane");
_Static_assert(sizeof(gg_sprite) == 0x68 && offsetof(gg_sprite, colors) == 0x40, "sprite");
_Static_assert(sizeof(gg_null) == 0x30 && offsetof(gg_null, flags) == 0x24, "null");
_Static_assert(sizeof(gg_text) == 0x80 && offsetof(gg_text, flags) == GG_TEXT_FLAGS, "text");
_Static_assert(offsetof(gg_text, length) == GG_TEXT_LENGTH, "text length");
_Static_assert(sizeof(gg_boundary) == 0x30, "boundary");
_Static_assert(sizeof(gg_player) == 0x30, "player");

#endif
