/* Single-screen mode: the town minimap's place name on the top screen (emulator only).
 *
 * The town's name ("Val Habar": the balloon `ui421_midasi_mura` of the lobby's ui421, loaded on the touch screen) goes
 * to the top screen with the minimap: the minimap's block (single_screen_minimap.s) lists its group among the groups it
 * moves with the map. This unit only gives it the place and the size: the layout side put everything under the group in
 * one null, `<group>_frame` (hud/single_screen_minimap.py, add_label_frame), and every frame, while the group is on the
 * top screen, this unit scales that null and moves it to the map's top left, as the frames block does for the Palico
 * menus (`frame_null`, single_screen_frames.c). On the touch screen the null is kept at (0, 0), scale 1.
 *
 * Called by the frames block's entry (single_screen_frames.c, after the minimap's block has moved the groups), every
 * frame:
 *  1. nothing at all with an empty table (the curated label is missing: group 0), or without the GUI, its manager or
 *     its group list;
 *  2. the group is looked up afresh, never kept: the first of the GUI manager's list (*(*(gui + 0x100) + 0x154), 0x600
 *     pointers) whose name hash (group + 0) is the table's; none: nothing;
 *  3. on the top screen (bits 14-17 of group + 0x44 are *(gui + 0x245)) the null gets the table's cx, cy, scale and
 *     k (the patcher's: cx = 200 (1 - s) - at x, cy = 120 (1 - s) - at y, k = s - 1, so every point of the group goes
 *     from (x, y) to (s x + at x, s y + at y) whatever the group's translate); on any other screen the identity. Only a
 *     value that differs is written, and then the pane is redrawn (`frame_null`); a group whose first pane is not the
 *     null (the layout was not wrapped) is left alone;
 *  4. the table's `hidden` pane (the touch screen's shop-name bar, a null among the frame null's children: a chain of
 *     sibling records, record + 0x14, from the first child, record + 0x20; at most 16 are looked at) gets scale 0 on
 *     the top screen, where it would land over the small map's bottom edge, and its own scale 1 on any other
 *     (`null_scale`, the frames' unit); no table entry, no such child, no wrapper: nothing.
 *
 * Build: tools/build_code_space.py, as a unit of the frames block; the game's variable is named in
 * blocks.py GAME_SYMBOLS, the table is the block single_screen_label_table (exefs/single_screen_frames.py writes it).
 */

typedef unsigned int u32;
typedef unsigned char u8;

#define SLOTS 0x600                 /* the GUI manager's group list */
#define SCREEN_BITS 0xF
#define SCREEN_SHIFT 14             /* group + 0x44: bits 14-17, the screen the group is drawn on */
#define MAX_CHILDREN 16             /* the frame null's children looked at (the place name's group has ten) */

struct label {
    u32 group;                      /* the group's name hash; 0: no label */
    u32 wrapper;                    /* its frame null's name hash */
    float cx, cy, scale, k;         /* the null's parameters on the top screen (the frames table's) */
    u32 hidden;                     /* the name hash of the frame null's child that has no room on the top screen; 0: none */
};

extern const struct label single_screen_label_table;  /* the block single_screen_label_table, the patcher's */
extern u8 *gui_control;                                /* the game's GUI (its variable) */
void frame_null(u8 *group, u32 wrapper, float cx, float cy, float scale, float k);   /* single_screen_frames.c */
void null_scale(u8 *group, u8 *record, float scale);                                  /* single_screen_frames.c */

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define B(p, off) (*(volatile u8 *)((p) + (off)))
#define P(p, off) (*(u8 *volatile *)((p) + (off)))

/* The group's `hidden` pane, a child of its frame null (the group's first pane), gets `scale`. */
static void hide(u8 *group, const struct label *t, float scale)
{
    u8 *wrapper = P(group, 0x08);
    if (!t->hidden || !wrapper || W(wrapper, 0) != t->wrapper)
        return;
    u8 *child = P(wrapper, 0x20);
    for (u32 i = 0; child && i < MAX_CHILDREN; i++) {
        if (W(child, 0) == t->hidden) {
            null_scale(group, child, scale);
            return;
        }
        child = P(child, 0x14);
    }
}

void label_update(void)
{
    const struct label *t = &single_screen_label_table;
    if (!t->group)
        return;
    u8 *gui = gui_control;
    if (!gui)
        return;
    u8 *manager = P(gui, 0x100);
    if (!manager)
        return;
    u8 *list = P(manager, 0x154);
    if (!list)
        return;
    for (u32 i = 0; i < SLOTS; i++) {
        u8 *group = P(list, 4 * i);
        if (!group || W(group, 0) != t->group)
            continue;
        if (((W(group, 0x44) >> SCREEN_SHIFT) & SCREEN_BITS) == (B(gui, 0x245) & SCREEN_BITS)) {
            frame_null(group, t->wrapper, t->cx, t->cy, t->scale, t->k);
            hide(group, t, 0.0f);
        } else {
            frame_null(group, t->wrapper, 0.0f, 0.0f, 1.0f, 0.0f);
            hide(group, t, 1.0f);
        }
        return;
    }
}
