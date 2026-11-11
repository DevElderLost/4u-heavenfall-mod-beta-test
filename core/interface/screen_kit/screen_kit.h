/* The screen kit: finding a pane of a group by the hash of its
 * name, placing it, colouring it, writing numbers, and showing the groups. It is a unit of each block that draws a
 * screen of the facility menu (layered_selector, rare_exchange): every function below is compiled into the block that
 * uses it, and none keeps a state, so two blocks never meet. */

#ifndef SCREEN_KIT_H
#define SCREEN_KIT_H

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#ifndef GAME
#define GAME __attribute__((long_call))
#endif

struct ref { u32 group; u8 *node; };   /* a pane of a group: node + NODE_DATA its data */

GAME void gui_group_show(u32 group, u32 shown);                        /* FUN_00ae53e0 */
GAME void gui_group_order(u32 group, u32 layer, u32 priority);         /* FUN_00ae63c8 */
GAME u32 group_find(u32 manager, const u32 *key);                      /* FUN_00b045a8 */
GAME u32 group_at(u32 manager, u32 index);                             /* FUN_00b048f0 */
GAME void group_sprite_ref(struct ref *ref, u32 group, const u32 *key);  /* FUN_00ae5b2c */
GAME void group_text_ref(struct ref *ref, u32 group, const u32 *key);  /* FUN_00ae5d34 */
GAME void pane_redraw(u32 ref_a, u32 node);                            /* FUN_00ae6bcc */
GAME void text_show(u32 pane, u32 visible);                            /* FUN_00ae7618 */
extern u32 gui_control;

#define GUI_LAYOUTS 0x100        /* the GUI object -> the layout manager */
#define NODE_DATA 8              /* a pane's node: its data, */
#define NODE_DIRTY 0xC           /* its redraw entry (+ DIRTY_MARK: 3 redraws it), */
#define DIRTY_MARK 0x12
#define NODE_NEXT 0x14           /* its next sibling: a text's holder null */
#define SP_X 4                   /* a sprite's data, in words: position, */
#define SP_W 8                   /* size, */
#define SP_U 12                  /* texture cell, */
#define SP_COLOURS 16            /* corners' colours, */
#define SP_FLAGS 22              /* and flags */
#define SP_SHOWN 0x80
#define SP_ICON 0x10             /* FUN_00c118f4 takes the sprite's data from here, in bytes */
#define TX_X 6                   /* a text's data, in words: position, box width, colours; word 0 its holder null's data */
#define TX_W 12
#define TX_COLOURS 14
#define HALF_WIDTH 200           /* layout units: x grows to the left, y upwards, from the screen's centre */
#define HALF_HEIGHT 120
#define GUI_LAYER 1

u32 kit_float_bits(int value);
/* The group of a layout (ui401's) by the hash of its name: 0 when it is not there. */
u32 kit_group(u32 hash);
/* The data of the sprite / text pane of `group` named by `hash`; `r` is its ref (r->node 0: none). */
u32 *kit_sprite(struct ref *r, u32 group, u32 hash);
u32 *kit_text(struct ref *r, u32 group, u32 hash);
void kit_sprite_changed(const struct ref *r);
void kit_text_changed(const struct ref *r);
/* The sprite on, its top left corner at the screen pixel (x, y), the size w x h. */
u32 *kit_sprite_place(struct ref *r, u32 group, u32 hash, int x, int y, u32 w, u32 h);
void kit_sprite_hide(u32 group, u32 hash);
void kit_sprite_colour(u32 *sprite, u32 colour);
/* A text's colour goes before its string: the glyphs take it when laid out. */
void kit_text_colour(u32 *text, u32 colour);
void kit_text_hide(u32 group, u32 hash);
/* A text moved to the screen pixel (x, y) with the box width `w`. */
void kit_text_place(u32 *text, int x, int y, u32 w);
/* A group shown (in front at `priority`) or hidden. */
void kit_group_show(u32 group, u32 shown, u32 priority);
/* `value` in decimal into `out`, NUL ended; its length. */
u32 kit_number_text(u16 *out, u32 value);

#endif
