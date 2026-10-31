/* Single-screen mode: the frames of the Palico menus (interface/single_screen/executable/single_screen_frames.py;
emulator only).
 *
 * Some layouts the Palico menus show on the top screen are shared with other scenes (the Palico's status ui035, the
 * lists ui475, the arrows ui026): the files cannot make them smaller for these menus alone. The layout side puts
 * everything under each framed root group in one null, its first pane (`<group>_frame`, at (0, 0), scale 1:
 * interface/single_screen/layout/single_screen_frames.py), and this block gives that null a scale and a position every frame:
 *  1. one pass over the GUI manager's group list (*(*(gui + 0x100) + 0x154), 0x600 pointers): each group is looked up
 *     by its name hash (group + 0) in the table's names; a shown group (bit 0x400 of group + 0x44) ors its rule bits,
 *     a group of a frame set is noted (up to MAX_NAMES);
 *  2. the scene is the first of the table's scenes whose `all` bits are all set, whose `any` bits (0: no condition)
 *     have one set and whose `none` bits have none; no scene fits: none;
 *  3. each noted group whose first pane record (group + 8) is its frame null (record + 0 is the null's hash; another
 *     copy of the layout, unwrapped, has another first pane and is left alone) gets, hidden or shown (a page the game
 *     shows later is in place already), the null object's (record + 8) position (+0, +4) cx + k * tx, cy + k * ty
 *     (tx, ty: the group's translate, group + 0x28 / + 0x2C, which the code may write) and scale (+0x10, +0x14) s, from
 *     the table's parameters of its set in that scene (the patcher's: cx = 200 (1 - s) - at x, cy = 120 (1 - s) - at y,
 *     k = s - 1, so every point of the group goes from (x, y) to (s x + at x, s y + at y) on the screen); no scene, or
 *     a set the scene leaves out: (0, 0), scale 1; also a set marked PROMPT_OFF while a yes / no prompt is open (ui006's
 *     owner: the buttons' kinds "Yes" and "No" in its slots 0 and 1, the same test as single_screen_prompt.s: the
 *     description panel's question and the buttons stay together at the game's place). Only a value that differs is
 *     written, and then the pane is redrawn: byte 3 at +0x12 of its draw node (record + 0xC), or FUN_00ae6bcc(group,
 *     record) without one.
 *
 * After the frames' pass the entry runs the players' box (single_screen_players.c, a unit of this block: it keeps the
 * hall's member list up while the hunter walks) and the minimap's place
 * name (single_screen_label.c, another unit: it scales and moves the frame null of the name's group, with `frame_null`
 * below, while the group is on the top screen).
 *
 * The block also replaces FUN_00ae5e68, the game's ref to a root group's first pane ({group, group + 8}), with
 * `frames_first_pane`: where that pane is a null single-screen mode put under the group (named the group's name and
 * "_frame", or the engine's "_gg"), the ref gets the null's first child, the pane the game's file has first. The item
 * lists take their first row's text that way; with our null there the ref was null. The hook is a `b` over the
 * function's first instruction (0xAE5E68): the game's
 * callers come back from here.
 *
 * The pad update's call (0x694CE0, FUN_00694ccc: `bl FUN_005b8284`) is this block's entry, which first makes the call
 * the chain had there (the town minimap's block, which runs the hint, world map and prompt blocks and the pad read).
 * Live at the hook: r0 the call's argument (passed on); r0-r3 and ip are dead after it (0x694CE4 reloads r0 and r1).
 * The entry keeps r4-r11 (the C code's own saves) and s0-s15 (d0-d7: the frame code computes in VFP registers and the
 * game's caller may keep floats across the call it replaced); the stack stays 8-aligned.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with single_screen_frames.ld where it places the
 * block).
 */

typedef unsigned int u32;
typedef unsigned char u8;

#define SLOTS 0x600                 /* the GUI manager's group list */
#define SHOWN 0x400u                /* group + 0x44: the group is shown */
#define NULL_KIND 1                 /* pane record + 0x10: a null */
#define NAME_LIMIT 64               /* bytes of a name compared (the layouts' names are shorter) */
#define MAX_SCENES 16               /* the table's room (interface/single_screen/executable/single_screen_frames.py) */
#define MAX_SETS 16
#define MAX_NAMES 160
#define PROMPT_OFF 0x100            /* in a name's set field: the set is left alone while a yes / no prompt is open */
#define SET_MASK 0xFF
#define KIND_YES 3                  /* ui006's button kinds of a yes / no prompt (single_screen_prompt.s) */
#define KIND_NO 6

struct scene { u32 all, any, none; };
struct param { float cx, cy, scale, k; };
struct name { u32 hash, rules, set, wrapper; };     /* set: 1 + the frame set's index, 0 for a rule name only */
struct table {
    u32 count;                                      /* scenes */
    struct scene scenes[MAX_SCENES];
    struct param params[MAX_SETS * MAX_SCENES];     /* [set * MAX_SCENES + scene] */
    struct name names[MAX_NAMES + 1];               /* a 0 hash after the last */
};

extern const struct table single_screen_frame_table;  /* the block single_screen_frame_table, the patcher's */
extern u8 *gui_control;                                /* the game's GUI (its variable) */
extern u8 prompt_owner[];                              /* ui006's owner: button kinds at +0x1F8 + 2 * slot, bound at +0x21F */
void pane_redraw(u8 *group, u8 *record);               /* FUN_00ae6bcc */
void minimap_pad(u32 pad);                             /* the next block of the pad update's chain */
void frames_update(void);
void players_update(void);                             /* single_screen_players.c, linked into this block */
void label_update(void);                               /* single_screen_label.c, linked into this block */

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define F(p, off) (*(volatile float *)((p) + (off)))
#define P(p, off) (*(u8 *volatile *)((p) + (off)))

/* The entry: the chain's call, then the frames; d0-d7 kept for the caller. */
__attribute__((naked, section(".text.entry"))) void frames_pad(void)
{
    __asm__ volatile(
        "push   {r4, lr}\n\t"
        "vpush  {d0-d7}\n\t"
        "bl     minimap_pad\n\t"
        "bl     frames_update\n\t"
        "bl     players_update\n\t"
        "bl     label_update\n\t"
        "vpop   {d0-d7}\n\t"
        "pop    {r4, pc}\n\t");
}

static const struct name *find(u32 hash)
{
    for (const struct name *n = single_screen_frame_table.names; n->hash; n++)
        if (n->hash == hash)
            return n;
    return 0;
}

static u32 bits_of(float value)
{
    union { float f; u32 u; } v;
    v.f = value;
    return v.u;
}

/* Write `value` at `at` when its bits differ; returns 1 if it wrote. */
static u32 put(u8 *at, float value)
{
    if (W(at, 0) == bits_of(value))
        return 0;
    F(at, 0) = value;
    return 1;
}

static u32 scene_of(u32 shown)
{
    const struct table *t = &single_screen_frame_table;
    for (u32 j = 0; j < t->count && j < MAX_SCENES; j++) {
        const struct scene *s = &t->scenes[j];
        if ((shown & s->all) == s->all && (!s->any || (shown & s->any)) && !(shown & s->none))
            return j;
    }
    return MAX_SCENES;
}

/* Gives the frame null of `group` (its first pane: record + 0 is the null's hash `wrapper`; another copy of the layout,
 * unwrapped, has another first pane and is left alone) the position (cx + k * tx, cy + k * ty) (tx, ty: the group's
 * translate) and the scale `scale`, and redraws it if anything changed. Also called by the label unit. */
void frame_null(u8 *group, u32 wrapper, float cx, float cy, float scale, float k)
{
    u8 *record = P(group, 0x08);
    if (!record || W(record, 0) != wrapper)
        return;
    u8 *pane = P(record, 0x08);
    if (!pane)
        return;
    u32 changed = put(pane + 0x00, cx + k * F(group, 0x28));
    changed |= put(pane + 0x04, cy + k * F(group, 0x2C));
    changed |= put(pane + 0x10, scale);
    changed |= put(pane + 0x14, scale);
    if (!changed)
        return;
    u8 *node = P(record, 0x0C);
    if (node)
        node[0x12] = 3;
    else
        pane_redraw(group, record);
}

/* Gives the null `record` of `group` (any pane record of it, found by the label unit) the scale `scale` and redraws it
 * if it changed: the label unit's shrinking of the touch screen's shop-name bar to nothing on the top screen. */
void null_scale(u8 *group, u8 *record, float scale)
{
    u8 *pane = P(record, 0x08);
    if (!pane)
        return;
    u32 changed = put(pane + 0x10, scale);
    changed |= put(pane + 0x14, scale);
    if (!changed)
        return;
    u8 *node = P(record, 0x0C);
    if (node)
        node[0x12] = 3;
    else
        pane_redraw(group, record);
}

/* 1 while a yes / no prompt of ui006 is open (bound, slot 0 "Yes", slot 1 "No"). */
static u32 prompt_open(void)
{
    return prompt_owner[0x21F] && prompt_owner[0x1F8] == KIND_YES && prompt_owner[0x1FA] == KIND_NO;
}

static void frame(u8 *group, const struct name *n, u32 scene, u32 prompt)
{
    float cx = 0.0f, cy = 0.0f, scale = 1.0f, k = 0.0f;
    u32 set = n->set & SET_MASK;
    if (scene < MAX_SCENES && set <= MAX_SETS && !(prompt && (n->set & PROMPT_OFF))) {
        const struct param *p = &single_screen_frame_table.params[(set - 1) * MAX_SCENES + scene];
        cx = p->cx;
        cy = p->cy;
        scale = p->scale;
        k = p->k;
    }
    frame_null(group, n->wrapper, cx, cy, scale, k);
}

/* 1 if `name` is `group` followed by exactly `suffix`. */
static u32 named_after(const char *name, const char *group, const char *suffix)
{
    u32 n = 0;
    while (n < NAME_LIMIT && group[n] && name[n] == group[n])
        n++;
    if (n >= NAME_LIMIT || group[n])
        return 0;
    for (u32 i = 0; n + i < NAME_LIMIT; i++) {
        if (name[n + i] != suffix[i])
            return 0;
        if (!suffix[i])
            return 1;
    }
    return 0;
}

/* 1 if `record`, the first pane of `group`, is a null single-screen mode put there: the frames' (and the label's)
 * "<group>_frame" or the engine's "<group>_gg" (interface/single_screen/layout/single_screen_frames.py, interface/game_gui/engine.py). No layout of the game
 * has a group whose first pane is named so (its own "..._frame" nulls, ui414's, are named after no group). */
static u32 our_wrapper(const u8 *group, const u8 *record)
{
    const char *group_name = (const char *)P(group, 0x04);
    const char *name = (const char *)P(record, 0x04);
    if (record[0x10] != NULL_KIND || !group_name || !name || !P(record, 0x20))
        return 0;
    return named_after(name, group_name, "_frame") || named_after(name, group_name, "_gg");
}

/* FUN_00ae5e68's replacement: ref = {group, its first pane}, the first pane under our null when there is one. */
void frames_first_pane(u8 **ref, u8 *group)
{
    u8 *record = P(group, 0x08);
    if (record && our_wrapper(group, record))
        record = P(record, 0x20);
    ref[0] = group;
    ref[1] = record;
}

__attribute__((used)) void frames_update(void)
{
    u8 *gui = gui_control;
    if (!gui)
        return;
    u8 *manager = P(gui, 0x100);
    if (!manager)
        return;
    u8 *list = P(manager, 0x154);
    if (!list)
        return;
    u8 *groups[MAX_NAMES];
    const struct name *names[MAX_NAMES];
    u32 count = 0, shown = 0;
    for (u32 i = 0; i < SLOTS; i++) {
        u8 *group = P(list, 4 * i);
        if (!group)
            continue;
        const struct name *n = find(W(group, 0));
        if (!n)
            continue;
        if (W(group, 0x44) & SHOWN)
            shown |= n->rules;
        if (n->set && count < MAX_NAMES) {
            groups[count] = group;
            names[count++] = n;
        }
    }
    u32 scene = scene_of(shown);
    u32 prompt = prompt_open();
    for (u32 i = 0; i < count; i++)
        frame(groups[i], names[i], scene, prompt);
}
