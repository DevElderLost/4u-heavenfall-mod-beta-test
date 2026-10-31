/* The game GUI engine: every frame
 * it applies the arrangement (game/data/curated/game_gui/, built into the table `game_gui_table` by
 * core/interface/game_gui/engine.py) to every GUI manager of the game, with absolute values only.
 *
 * Three hooks, three entries (each a short stub that calls the C):
 *  1. sMhMain::frame (FUN_00af52a0), 0xAF555C `ldr r0, [r4, #0x290]`, after every system's move and before the
 *     render: `gui_engine_frame_hook` runs `gui_engine_frame` and then the
 *     load it replaced. The instruction before it is a `blx` (another system's move), so r0-r3, ip, the flags and
 *     d0-d7 hold nothing the frame reads again; r4 (sMhMain) and the other callee-saved registers are kept by the C.
 *  2. uLayout::draw (FUN_00b047c4), 0xB0481C `lsl r1, r1, #0xe` before `cmp r5, r1, lsr #28` (the group's view
 *     against the view being drawn; A2, "the screen at draw time"): `gui_engine_view_hook` returns in r1 the view the
 *     group is drawn in, << 28 (`gui_engine_view`), and keeps r0 (the group). r2, r3 and ip are dead there (set
 *     before their next read), the flags too (the cmp sets them). Only the drawing changes: the group's own bits
 *     14-17 stay the game's, so touch answers where the game put it.
 *  3. the pad update's call (FUN_00694ccc, 0x694CE0 `bl FUN_005b8284`), where the guild card's block already hooked its
 *     entry: `gui_engine_pad_hook` calls that entry with r0 as it came, then `gui_engine_pad`, the photo mode's pad side
 *     (below). Only built into a single-screen run, which is where the guild card's block is.
 *
 * The photo mode: on a screen that has a photo
 * record (the table's photo section: the screens of the curated `photo` lists, with the group name hashes each keeps
 * drawn) a fresh press of the record's toggle button (the screen's own, else the settings') turns it on
 * (`game_gui_photo.on`) and a fresh press of any of the
 * dismiss buttons turns it off; the press is the mode's: `gui_engine_pad` clears it from the pad's words and keeps it
 * in `muted` until the button is released. While it is on, `gui_engine_view` sends every group but the screen's kept
 * ones to view 15 (drawn by no camera), whatever manager it is in or table it names; `gui_engine_frame` ends the mode
 * the frame the screen has no photo record any more. Nothing else of the arrangement changes.
 *
 * gui_engine_frame:
 *  1. walks every GUI manager (the uLayout family, told by its vtable) of sUnit's 32 move lines, and each manager's
 *     group list; a group is found in the table's names by its name hash (binary search: the names are sorted);
 *  2. the screen: the first of the table's screens (in the order the build wrote: by number) whose rule matches the
 *     names of the shown groups (bit 0x400 of group + 0x44): all of `all`, one of `any` (or none listed), none of
 *     `none`. Kept in game_gui_state for the draw's hook (index + 1; 0: none, the blocks' defaults);
 *  3. each group of a block gets its block's place on that screen (the screen's own entry, else the block's default):
 *     each of its targets (a pane right under the group, found by its name hash) gets the position
 *     cx[own] + (s - 1) * translate + s * q and the scale s * b, where translate is the group's own (+0x28, +0x2C:
 *     the game may move the group), own its own screen (bits 14-17: 7 the touch screen, else the top one), q and b
 *     the pane's file position and scale for a pane written directly (a null whose subtree fills the loader's six
 *     levels), 0 and 1 for the wrapper null the build put around the group's children. A target that names a block of
 *     its own (a part block: panes of the group the build split off under a null of their own) takes that block's
 *     place instead, the screen's entry else its default (the build writes a part's entry on every screen that places
 *     its group's block). A group with parts is drawn while one of its parts shows (below), so there every target
 *     whose place is hidden (a part hidden on its own, or the rest of a hidden block) gets the scale 0 instead: nothing
 *     under it draws. A value is written only when
 *     its bits differ, and then the pane is redrawn (its draw node's byte + 0x12 = 3, or FUN_00ae6bcc without one).
 *     The priority (bits 19-26 of group + 0x18) is written when the place sets one and it differs, then
 *     FUN_00ae65b0(group) as FUN_00ae63c8 does. A view the manager does not draw in is added to its mDrawView (bits
 *     16-25 of + 4: the keyboard's managers draw in the top screen's view only).
 *  Nothing is read back from what was written: every value is a function of the table, the group's translate and
 *  its own screen, so a frame that chose a wrong screen is right again the next one.
 *
 * gui_engine_view(group, flags): the group's view bits 14-17, unless the group's block's place on the current screen
 * sends it to a screen (0 top, 7 touch) or hides it (view 15, which no view draws); a hidden block's group with a part
 * that is not hidden on that screen is drawn all the same (its other targets are collapsed, above).
 *
 * The table (all little endian, offsets from its start; a table without the magic makes both entries do nothing):
 * a header, the names sorted by hash, their targets, the direct targets' file values, the screens, the rules' name
 * indices, a default place per block, each screen's places sorted by block and the photo screens (a record of the
 * screen, its first kept hash and their count each, then the hashes).
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with game_gui_engine.ld).
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define MAGIC 0x31454747u            /* "GGE1" */
#define SHOWN 0x400u                 /* group + 0x44: shown */
#define VIEW_SHIFT 14                /* group + 0x44: bits 14-17 the view (screen) */
#define VIEW_BOTTOM 7                /* the touch screen's view */
#define VIEW_NONE 15                 /* a view no camera draws: the group is hidden */
#define PRIORITY_SHIFT 19            /* group + 0x18: bits 19-26 */
#define DRAW_VIEWS 16                /* manager + 4: bit 16 + view, the views its unit draws in */
#define LINES 32                     /* sUnit's move lines: + 0x14, 0x18 each, + 0x0C the first unit */
#define UNIT_LIMIT 0x4000            /* units walked per line at most (a broken chain never hangs the frame) */
#define GROUP_LIMIT 0x2000           /* a manager's group list length at most */
#define MAX_NAMES 4096               /* the shown names' bits on the stack (the build refuses more names) */
#define NO_BLOCK 0xFFFFu
#define WRAPPER 0xFFFFu              /* a target's `direct`: the build's wrapper null */

#define PLACE_VIEW 0x0Fu             /* place flags: the view to draw in (0 top, 7 touch) ... */
#define PLACE_KEEP_VIEW 0x10u        /* ... or the group's own */
#define PLACE_PRIORITY 0x20u         /* the place sets the priority */
#define PLACE_HIDDEN 0x40u           /* the block is not drawn */

#define PAD_HELD 0x8C                /* the pad object's raw words: held, old, pressed, released, changed, repeat */
#define PAD_PRESSED 0x94
#define PAD_END 0xA4

struct header {
    u32 magic;
    u32 names, targets, directs, screens, terms, blocks, entries;
    u32 name_at, target_at, direct_at, screen_at, term_at, default_at, entry_at;
    float centre[2];                 /* unused by the code: the build's screen centres, for the record */
    u32 watch;                       /* a group's name hash whose + 0x44 the state copies (probes); 0: none */
    u32 photo_at, photos;            /* the photo screens' records (struct photo_screen), then the kept hashes */
    u32 toggle, dismiss;             /* the photo mode's raw pad bits: the settings' toggle (each record holds the one
                                        used), those that end it */
};
struct name { u32 hash; u16 block, target_first, target_count, pad; };
struct target { u32 hash; u16 direct, block; };        /* block: a part block's index, NO_BLOCK for the name's */
struct direct { float qx, qy, bx, by; };
struct screen { u16 all_first, all_count, any_first, any_count, none_first, none_count, entry_first, entry_count; };
struct place { u16 block; u8 flags, priority; float scale, cx[2], cy; };
struct state { u32 frames, screen, watch_flags, groups; };
/* a screen (index + 1) with the mode: its kept hashes, and the raw pad bit that turns it on there */
struct photo_screen { u16 screen, first, count, toggle; };
struct photo { u32 on, muted; };       /* the mode is on; the raw pad bits it hides from the game until released */

extern const u8 game_gui_table[];                      /* the block game_gui_table, the build's */
extern struct state game_gui_state;                    /* .bss */
extern struct photo game_gui_photo;                    /* .bss */
extern u8 *pad_control;                                /* the pad object (its variable) */
extern u8 *sunit;                                      /* the game's sUnit (the units' move lines) */
extern const u8 ulayout_vtable[], ulayout_monnyan_vtable[], uswkbd_layout_vtable[], ulayout_scheduler_vtable[],
    ulyt_anime_scheduler_vtable[], ulyt_message_scheduler_vtable[];
void pane_redraw(u8 *group, u8 *pane);                 /* FUN_00ae6bcc */
void gui_group_changed(u8 *group);                     /* FUN_00ae65b0 */
void card_info_pad(void);                              /* the pad update's chain before this entry (single_screen_card_info.s) */
void gui_engine_frame(void);
void gui_engine_pad(void);
u32 gui_engine_view(u8 *group, u32 flags);

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define F(p, off) (*(volatile float *)((p) + (off)))
#define P(p, off) (*(u8 *volatile *)((p) + (off)))
#define TABLE ((const struct header *)game_gui_table)
#define AT(type, off) ((const type *)(game_gui_table + (off)))

/* 0xAF555C: the engine, then the frame's load it replaced. */
__attribute__((naked, section(".text.entry"))) void gui_engine_frame_hook(void)
{
    __asm__ volatile(
        "push   {r4, lr}\n\t"
        "bl     gui_engine_frame\n\t"
        "pop    {r4, lr}\n\t"
        "ldr    r0, [r4, #0x290]\n\t"
        "bx     lr\n\t");
}

/* 0xB0481C: r1 = the view to draw the group r0 in, << 28; r0 kept. */
__attribute__((naked)) void gui_engine_view_hook(void)
{
    __asm__ volatile(
        "push   {r0, lr}\n\t"
        "bl     gui_engine_view\n\t"
        "mov    r1, r0\n\t"
        "pop    {r0, pc}\n\t");
}

/* The pad update's call (0x694CE0, hooked after the guild card's block): that chain first, with r0 as the game passed
 * it, then the photo mode. Nothing of d0-d7 is used here (the chain keeps them for its caller). */
__attribute__((naked)) void gui_engine_pad_hook(void)
{
    __asm__ volatile(
        "push   {r4, lr}\n\t"
        "bl     card_info_pad\n\t"
        "bl     gui_engine_pad\n\t"
        "pop    {r4, pc}\n\t");
}

static int is_manager(u32 vtable)
{
    return vtable == (u32)ulayout_vtable || vtable == (u32)ulayout_monnyan_vtable ||
           vtable == (u32)uswkbd_layout_vtable || vtable == (u32)ulayout_scheduler_vtable ||
           vtable == (u32)ulyt_anime_scheduler_vtable || vtable == (u32)ulyt_message_scheduler_vtable;
}

/* The name of `hash` and its index, or 0. */
static const struct name *find(u32 hash, u32 *index)
{
    const struct header *h = TABLE;
    const struct name *names = AT(struct name, h->name_at);
    u32 low = 0, high = h->names;
    while (low < high) {
        u32 mid = (low + high) >> 1;
        u32 at = names[mid].hash;
        if (at == hash) {
            *index = mid;
            return &names[mid];
        }
        if (at < hash)
            low = mid + 1;
        else
            high = mid;
    }
    return 0;
}

/* The place of `block` on screen `screen` (index + 1; 0: none): the screen's own entry, else the block's default. */
static const struct place *place_of(u32 screen, u32 block)
{
    const struct header *h = TABLE;
    if (screen && screen <= h->screens) {
        const struct screen *s = AT(struct screen, h->screen_at) + (screen - 1);
        const struct place *entries = AT(struct place, h->entry_at) + s->entry_first;
        u32 low = 0, high = s->entry_count;
        while (low < high) {
            u32 mid = (low + high) >> 1;
            if (entries[mid].block == block)
                return &entries[mid];
            if (entries[mid].block < block)
                low = mid + 1;
            else
                high = mid;
        }
    }
    return AT(struct place, h->default_at) + block;
}

/* The photo record of `screen` (index + 1), or 0: the screen has no photo mode (screen 0, none, never has). */
static const struct photo_screen *photo_of(u32 screen)
{
    const struct header *h = TABLE;
    const struct photo_screen *records = AT(struct photo_screen, h->photo_at);
    for (u32 i = 0; i < h->photos; i++)
        if (records[i].screen == screen)
            return &records[i];
    return 0;
}

/* Whether the photo screen keeps the group of the name hash `hash` drawn (the hashes follow the records). */
static u32 photo_keeps(const struct photo_screen *photo, u32 hash)
{
    const struct header *h = TABLE;
    const u32 *kept = AT(u32, h->photo_at + h->photos * sizeof(struct photo_screen)) + photo->first;
    for (u32 i = 0; i < photo->count; i++)
        if (kept[i] == hash)
            return 1;
    return 0;
}

static int any_set(const u32 *bits, const u16 *terms, u32 first, u32 count)
{
    for (u32 i = 0; i < count; i++) {
        u32 n = terms[first + i];
        if (bits[n >> 5] & 1u << (n & 31))
            return 1;
    }
    return 0;
}

static int all_set(const u32 *bits, const u16 *terms, u32 first, u32 count)
{
    for (u32 i = 0; i < count; i++) {
        u32 n = terms[first + i];
        if (!(bits[n >> 5] & 1u << (n & 31)))
            return 0;
    }
    return 1;
}

/* The first screen whose rule the shown names match: index + 1, or 0. */
static u32 screen_of(const u32 *bits)
{
    const struct header *h = TABLE;
    const struct screen *screens = AT(struct screen, h->screen_at);
    const u16 *terms = AT(u16, h->term_at);
    for (u32 j = 0; j < h->screens; j++) {
        const struct screen *s = &screens[j];
        if (all_set(bits, terms, s->all_first, s->all_count) &&
            (!s->any_count || any_set(bits, terms, s->any_first, s->any_count)) &&
            !any_set(bits, terms, s->none_first, s->none_count))
            return j + 1;
    }
    return 0;
}

static u32 bits_of(float value)
{
    union { float f; u32 u; } v;
    v.f = value;
    return v.u;
}

/* Write `value` at `at` when its bits differ; 1 if it wrote. */
static u32 put(u8 *at, float value)
{
    if (W(at, 0) == bits_of(value))
        return 0;
    F(at, 0) = value;
    return 1;
}

/* Whether a group of the name `n` has a part (a target that names a block of its own). */
static u32 has_part(const struct name *n)
{
    const struct target *targets = AT(struct target, TABLE->target_at) + n->target_first;
    for (u32 i = 0; i < n->target_count; i++)
        if (targets[i].block != NO_BLOCK)
            return 1;
    return 0;
}

/* Whether a part of the group is not hidden on `screen`: the group is then drawn whatever its block's place says. */
static u32 part_shown(const struct name *n, u32 screen)
{
    const struct target *targets = AT(struct target, TABLE->target_at) + n->target_first;
    for (u32 i = 0; i < n->target_count; i++)
        if (targets[i].block != NO_BLOCK && !(place_of(screen, targets[i].block)->flags & PLACE_HIDDEN))
            return 1;
    return 0;
}

/* A target pane of `group` (a null): its position and scale; `hide` collapses it (scale 0: nothing under it draws). */
static void write_target(u8 *group, u8 *pane, const struct place *p, const struct direct *d, u32 own, u32 hide)
{
    u8 *data = P(pane, 0x08);
    if (!data)
        return;
    float s = p->scale, k = s - 1.0f;
    float x = p->cx[own] + k * F(group, 0x28), y = p->cy + k * F(group, 0x2C), sx = s, sy = s;
    if (d) {
        x += s * d->qx;
        y += s * d->qy;
        sx = s * d->bx;
        sy = s * d->by;
    }
    if (hide) {
        sx = 0.0f;
        sy = 0.0f;
    }
    u32 changed = put(data + 0x00, x);
    changed |= put(data + 0x04, y);
    changed |= put(data + 0x10, sx);
    changed |= put(data + 0x14, sy);
    if (!changed)
        return;
    u8 *node = P(pane, 0x0C);
    if (node)
        node[0x12] = 3;
    else
        pane_redraw(group, pane);
}

static void apply(u8 *manager, u8 *group, const struct name *n, u32 screen)
{
    const struct header *h = TABLE;
    const struct place *p = place_of(screen, n->block);
    u32 flags = W(group, 0x44);
    u32 own = ((flags >> VIEW_SHIFT) & 0xF) == VIEW_BOTTOM ? 1 : 0;
    const struct target *targets = AT(struct target, h->target_at) + n->target_first;
    u32 parted = has_part(n);
    for (u32 i = 0; i < n->target_count; i++) {
        const struct direct *d = targets[i].direct == WRAPPER ? 0 : AT(struct direct, h->direct_at) + targets[i].direct;
        const struct place *tp = targets[i].block == NO_BLOCK ? p : place_of(screen, targets[i].block);
        /* a group with parts is drawn while one of them shows: what is hidden in it is collapsed instead */
        u32 hide = parted && (tp->flags & PLACE_HIDDEN);
        for (u8 *pane = P(group, 0x08); pane; pane = P(pane, 0x14))
            if (W(pane, 0) == targets[i].hash) {
                write_target(group, pane, tp, d, own, hide);
                break;
            }
    }
    if (p->flags & PLACE_PRIORITY) {
        u32 order = W(group, 0x18);
        if (((order >> PRIORITY_SHIFT) & 0xFF) != p->priority) {
            W(group, 0x18) = (order & ~(0xFFu << PRIORITY_SHIFT)) | (u32)p->priority << PRIORITY_SHIFT;
            gui_group_changed(group);
        }
    }
    if (!(p->flags & PLACE_KEEP_VIEW) && (!(p->flags & PLACE_HIDDEN) || parted))
        W(manager, 0x04) |= 1u << (DRAW_VIEWS + (p->flags & PLACE_VIEW));
}

/* Each group of each GUI manager: `pass` 0 notes the shown names, 1 applies the places. */
static void walk(u32 pass, u32 *bits, u32 screen)
{
    const struct header *h = TABLE;
    u8 *units = sunit;
    if (!units)
        return;
    for (u32 line = 0; line < LINES; line++) {
        u8 *unit = P(units, 0x14 + 0x18 * line + 0x0C);
        for (u32 seen = 0; unit && seen < UNIT_LIMIT; seen++, unit = P(unit, 0x0C)) {
            if (!is_manager(W(unit, 0)))
                continue;
            u8 *list = P(unit, 0x154);
            u32 count = W(unit, 0x160);
            if (!list)
                continue;
            if (count > GROUP_LIMIT)
                count = GROUP_LIMIT;
            for (u32 i = 0; i < count; i++) {
                u8 *group = P(list, 4 * i);
                if (!group)
                    continue;
                u32 hash = W(group, 0), index;
                if (pass == 0 && h->watch && hash == h->watch)
                    game_gui_state.watch_flags = W(group, 0x44);
                const struct name *n = find(hash, &index);
                if (!n)
                    continue;
                if (pass == 0) {
                    game_gui_state.groups++;
                    if (W(group, 0x44) & SHOWN)
                        bits[index >> 5] |= 1u << (index & 31);
                } else if (n->block != NO_BLOCK) {
                    apply(unit, group, n, screen);
                }
            }
        }
    }
}

__attribute__((used)) void gui_engine_frame(void)
{
    const struct header *h = TABLE;
    game_gui_state.frames++;
    game_gui_state.screen = 0;
    if (h->magic != MAGIC || h->names > MAX_NAMES)
        return;
    u32 bits[MAX_NAMES / 32];
    for (u32 i = 0; i < (h->names + 31) / 32; i++)
        bits[i] = 0;
    game_gui_state.groups = 0;
    walk(0, bits, 0);
    u32 screen = screen_of(bits);
    game_gui_state.screen = screen;
    if (game_gui_photo.on && !photo_of(screen))
        game_gui_photo.on = 0;            /* the card closed or on its monster page: the next one starts without it */
    walk(1, bits, screen);
}

/* The photo mode, after the pad update's chain: on a photo screen a fresh press of the
 * toggle button turns it on and, while it is on, a fresh press of any dismissing button turns it off; the press is the
 * mode's, so its bits are cleared from the held, pressed, released, changed and repeat words (the game derives its own
 * presses from the held word) and remembered in `muted` until the button is released: the raw read hands a cleared
 * button that is still down back as a fresh press the next frame, and that one is no press of anybody's. A bit that is
 * no button (the circle pad, the touch, the other blocks' marks) is left alone. */
__attribute__((used)) void gui_engine_pad(void)
{
    const struct header *h = TABLE;
    u8 *pad = pad_control;
    if (h->magic != MAGIC || !h->photos || !pad)
        return;
    u32 held = W(pad, PAD_HELD);
    u32 muted = game_gui_photo.muted & held, clear = muted, on = game_gui_photo.on;
    const struct photo_screen *photo = photo_of(game_gui_state.screen);
    if (photo) {
        u32 fresh = W(pad, PAD_PRESSED) & ~muted;
        u32 took = fresh & (on ? h->dismiss : photo->toggle);
        if (took) {
            on = !on;
            clear |= took;
            muted |= took;
        }
    } else {
        on = 0;
    }
    game_gui_photo.on = on;
    game_gui_photo.muted = muted;
    if (!clear)
        return;
    W(pad, PAD_HELD) = held & ~clear;
    for (u32 at = PAD_PRESSED; at < PAD_END; at += 4)
        W(pad, at) = W(pad, at) & ~clear;
}

__attribute__((used)) u32 gui_engine_view(u8 *group, u32 flags)
{
    u32 own = (flags >> VIEW_SHIFT) & 0xF;
    const struct header *h = TABLE;
    if (h->magic != MAGIC)
        return own << 28;
    if (game_gui_photo.on) {                   /* the photo mode: every group but the screen's kept ones draws nowhere */
        const struct photo_screen *photo = photo_of(game_gui_state.screen);
        if (photo && !photo_keeps(photo, W(group, 0)))
            return (u32)VIEW_NONE << 28;
    }
    u32 index;
    const struct name *n = find(W(group, 0), &index);
    if (!n || n->block == NO_BLOCK)
        return own << 28;
    const struct place *p = place_of(game_gui_state.screen, n->block);
    if ((p->flags & PLACE_HIDDEN) && !part_shown(n, game_gui_state.screen))
        return (u32)VIEW_NONE << 28;
    if (p->flags & PLACE_KEEP_VIEW)
        return own << 28;
    return (u32)(p->flags & PLACE_VIEW) << 28;
}
