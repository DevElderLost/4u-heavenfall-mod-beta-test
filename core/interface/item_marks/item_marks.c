/* Item marks (interface/item_marks/item_marks.py): the upgrade stars on item icons and
 * the rare materials' highlight on the quest rewards screen. Three halves:
 *
 *   - item_marks_icon(data + 0x10, item), from the stubs after every write of an item's icon into a sprite (the item
 *     setters FUN_00c0de18 / FUN_00c0e268 and the 13 inline sites of FUN_00c118f4): an upgrade's level goes into the
 *     low 7 bits of the sprite's u (+ 0x30), a signature and the level (MARK | level), which the GPU's float24
 *     drops: the texture does not move. The game writes u whole each
 *     time, so the mark follows the item; nothing but the vertex builder reads u, and it never compares it.
 *   - item_marks_seen(group, pane), from the stubs in the vertex builder's two calls, for each drawn sprite whose u
 *     carries the signature: noted for the next frame (the render runs after the frame below).
 *   - item_marks_frame(), a frame-only entry of the quest's shared frame hook (interface/quest_layouts/: sMhMain::frame
 *     after every move, before the render):
 *       * each marked icon seen keeps one or two stars inside its square, coloured by the row Star Colour, sprites of
 *         the icon's own sheet made at run time and
 *         linked as the last children of the icon's parent null (the lists step from the first child: one after the
 *         icon would be taken for the next row), or as the group's last top panes for an icon that is a top pane;
 *         each frame they take the icon's place, size, alpha and visibility;
 *         an icon no longer marked, or the row off, hides them (kept for reuse; freed with their group);
 *       * on the quest rewards screen (pages 1 and 2), each cell of the 8 x 6 grid holding a rare item gets a halo,
 *         a top-level sprite of the group linked just before the grid's null (so under every icon), its opacity
 *         pulsing, and three small stars twinkling in turn over the icon (the null's last children).
 *     The new sprites are taken from the GUI manager's pools by hand, as FUN_00ae3f14 takes a text's glyphs: a pane
 *     and a sprite (whose primitive, bits 8-31 of + 0x58, is its own slot and is kept), only with `reserve` free places
 *     left in each pool (the game takes from them without checking); then FUN_00ae65b0 has the group's draw lists
 *     made again. A changed sprite of a cached group gets its redraw mark (node + 0x12 = 3, or FUN_00ae6bcc with room).
 *     Nothing is kept from one frame to the next but pointers checked again before use: the group at its index in its
 *     manager with its hash, a star with our hash, its owner and its parent.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM: the stubs call into it; item_marks.ld).
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define SIZES 4                 /* the stars' cells: 5, 7, 9, 11 texels */
#define STAR_COLOURS 2          /* Star Colour's values: Yellow, White (data.py STAR_COLOURS) */
#define TWINKLES 3
#define PHASES 64               /* the rare effect's tables: one cycle */
#define MAX_UPGRADES 64
#define MAX_RARE 128
#define SEEN 64                 /* marked sprites noted in one render */
#define TRACKED 96              /* marked icons with their stars */
#define CELLS 48                /* the rewards grid: 8 x 6 */
#define PAGES 2

/* item_marks.py data_block */
struct marks_data {
    u32 upgrade_option, rare_option;    /* mod_options.py OPTION_IDS: the switches, */
    u32 colour_option;                  /* ... Star Colour */
    u32 star_hash[2];                   /* our panes' names: the front star, the back one, */
    u32 twinkle_hash, halo_hash;        /* the rare effect's */
    u32 star_uv[SIZES][4];              /* each star cell's u, v, width, height (floats) */
    u32 halo_uv[4];
    u32 gold, glow;                     /* RGB words (red in the low byte), alpha 0: the twinkles', the halo's */
    u32 star_rgb[STAR_COLOURS];         /* ... the upgrade stars', by Star Colour's value */
    float side[2];                      /* the upgrade star's side on a 16-px and on a 24-px cell */
    u32 side_cell[2];                   /* ... which cell of star_uv it uses */
    float shift[2];                     /* two stars: the back one's shift right (px), by cell */
    float inset, lift, halo_side;       /* the stars' box from the top-left corner; the back one's lift (px) */
    float twinkle_x[TWINKLES], twinkle_y[TWINKLES];     /* their middles from a 16-px icon's top-left corner */
    float cycle;                        /* frames of 1/30 s in a cycle */
    u32 pane_reserve, sprite_reserve;   /* free places a pool keeps */
    u32 rewards_group, rewards_null;    /* name hashes: ui209_l_housyu, ui209_icon_s_housyu */
    u16 page_cells[PAGES];              /* the scene's offsets of page 1's and page 2's cells */
    u16 upgrades, rares;                /* counts */
    u8 halo_alpha[PHASES];              /* the halo's alpha by phase */
    u8 twinkle_cell[PHASES];            /* a twinkle's cell by phase (index in star_uv), 0xFF hidden */
    u16 upgrade_id[MAX_UPGRADES];       /* sorted */
    u8 upgrade_level[MAX_UPGRADES];
    u16 rare_id[MAX_RARE];              /* sorted */
};

_Static_assert(sizeof(struct marks_data) == 788, "blocks.py ITEM_MARKS_DATA_SIZE, item_marks.py data_block");

struct tracked {
    u32 group, hash;
    u32 icon;                           /* the marked icon's pane */
    u32 star[2];                        /* its stars' panes, 0 unknown */
};

struct cell_marks {
    u32 icon;                           /* the cell's icon pane when they were made */
    u32 halo, twinkle[TWINKLES];
};

struct marks_state {                    /* item_marks_state (blocks.py ITEM_MARKS_STATE_SIZE) */
    u32 seen_count;
    u32 seen[SEEN][2];                  /* group, pane */
    u32 count;
    struct tracked tracked[TRACKED];
    u32 rewards_group, rewards_hash;    /* the grid's group last found, and its hash then */
    struct cell_marks cell[CELLS];
    float phase;                        /* the rare effect's, 0-1 */
    u32 refusals;                       /* sprites left unmade for want of room */
    u32 lost;                           /* marked icons left out: table full */
    u32 made;                           /* sprites made */
};

_Static_assert(sizeof(struct marks_state) == 3424, "blocks.py ITEM_MARKS_STATE_SIZE");

extern const struct marks_data item_marks_data;
extern struct marks_state item_marks_state;
extern u32 gui_control, game_main, result_scene_object;
extern int mod_option_value(int id);    /* mod_options.c */
extern int mod_option_count(int id);
void pane_redraw(u32 group, u32 pane);  /* FUN_00ae6bcc */
void gui_group_changed(u32 group);       /* FUN_00ae65b0 */

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define F(p, off) (*(volatile float *)((p) + (off)))
#define H(p, off) (*(volatile u16 *)((p) + (off)))
#define B(p, off) (*(volatile u8 *)((p) + (off)))

#define MARK_MASK 0x7Cu         /* the stubs' MARK_MASK, MARK: bits 2-5 the signature, bit 6 clear */
#define MARK 0x28u
#define LEVEL_BITS 0x3u
#define LOW_BITS 0x7Fu          /* what float24 (the GPU's) drops, rounding down while bit 6 is clear */
#define ZERO_U 0x35800000u      /* 2^-20: a u of 0 with a mark (never a denormal) */
#define ITEM_LIMIT 0x1000u      /* ids past it are junk */

/* the GUI's objects */
#define G_HASH 0x00
#define G_PANES 0x08
#define G_CONTEXT 0x14          /* the manager's + 0x104: its pools' addresses */
#define G_FLAGS 0x44
#define G_SHOWN 0x400u
#define G_CACHED 0x100u
#define G_INDEX_SHIFT 18
#define MANAGER_OF_CONTEXT 0x104
#define M_GROUPS 0x154
#define M_COUNT 0x160
#define POOL_COUNT 0x08
#define POOL_USED 0x0C
#define POOL_ARRAY 0x10
#define P_HASH 0x00
#define P_NAME 0x04
#define P_DATA 0x08
#define P_NODE 0x0C
#define P_KIND 0x10             /* byte; + 0x11 depth, + 0x12 dirty */
#define P_DEPTH 0x11
#define P_NEXT 0x14
#define P_PREV 0x18
#define P_PARENT 0x1C
#define P_CHILD 0x20
#define PANE_SIZE 0x24
#define KIND_SPRITE 0
#define KIND_NULL 1
#define KIND_TEXT 2
#define NODE_DIRTY 0x12
#define DIRTY 3
#define S_X 0x10                /* a sprite's data */
#define S_Y 0x14
#define S_Z 0x18
#define S_OWNER 0x1C            /* read by nobody: our stars' owner */
#define S_W 0x20
#define S_H 0x24
#define S_SX 0x28
#define S_SY 0x2C
#define S_U 0x30
#define S_V 0x34
#define S_UW 0x38
#define S_VH 0x3C
#define S_COLOURS 0x40
#define S_ANGLE 0x50
#define S_FLAGS 0x58            /* bits 0-3 origin, 7 shown, 8-31 the primitive (the slot) */
#define SPRITE_SIZE 0x68
#define SHOWN 0x80u
#define ORIGIN_MASK 0xFu
#define CENTRE_ORIGIN 4u
#define PRIMITIVE 0xFFFFFF00u
#define N_X 0x00                /* a null's data */
#define N_Y 0x04
#define N_SX 0x10
#define N_SY 0x14
#define N_FLAGS 0x24
#define N_SHOWN 1u
#define FRAME_DELTA 0x5C        /* game_main: the frame's time, 1.0 a 30th of a second */
#define SCENE_PAGE 4
#define SHEET 256.0f            /* the icon sheet's width in texels */
#define GRID_ROWS 8             /* cells per row (column + row * 8) */
#define WALK_LIMIT 512          /* a null's children walked at most */

static const struct marks_data *const D = &item_marks_data;
#define ST (&item_marks_state)

/* ---- the mark ------------------------------------------------------------------------------------------- */

static int upgrade_level(u32 item)
{
    int low = 0, high = (int)D->upgrades - 1;

    if (item >= ITEM_LIMIT || high >= MAX_UPGRADES)
        return 0;
    while (low <= high) {
        int mid = (low + high) >> 1;
        u32 id = D->upgrade_id[mid];
        if (id == item)
            return D->upgrade_level[mid];
        if (id < item)
            low = mid + 1;
        else
            high = mid - 1;
    }
    return 0;
}

static int is_rare(u32 item)
{
    int low = 0, high = (int)D->rares - 1;

    if (item >= ITEM_LIMIT || item == 0 || high >= MAX_RARE)
        return 0;
    while (low <= high) {
        int mid = (low + high) >> 1;
        u32 id = D->rare_id[mid];
        if (id == item)
            return 1;
        if (id < item)
            low = mid + 1;
        else
            high = mid - 1;
    }
    return 0;
}

void item_marks_icon(u32 data10, u32 item)
{
    int level = upgrade_level(item);
    u32 u;

    if (data10 == 0 || level == 0)
        return;
    u = W(data10, S_U - 0x10);
    W(data10, S_U - 0x10) = (u == 0 ? ZERO_U : u & ~LOW_BITS) | MARK | (u32)level;
}

/* The level a sprite's u carries: the signature, a level of 1 or 2, and the rest an exact cell of the sheet (a
 * multiple of 1/32, or the marked 0), so that a game sprite whose u has those bits by chance is never taken. */
static int mark_level(u32 data)
{
    u32 u = W(data, S_U), base = u & ~LOW_BITS;
    int level = (int)(u & LEVEL_BITS), exponent;

    if ((u & MARK_MASK) != MARK || level < 1 || level > 2)
        return 0;
    if (base == ZERO_U)
        return level;
    exponent = (int)((base >> 23) & 0xFF) - 127;
    if ((base >> 31) != 0 || exponent >= 0 || exponent < -8)
        return 0;
    return (base & ((1u << (18 - exponent)) - 1u)) == 0 ? level : 0;
}

static int ours(u32 pane)
{
    u32 hash = W(pane, P_HASH);

    return hash == D->star_hash[0] || hash == D->star_hash[1] || hash == D->twinkle_hash || hash == D->halo_hash;
}

void item_marks_seen(u32 group, u32 pane)
{
    struct marks_state *st = ST;

    if (group == 0 || pane == 0 || st->seen_count >= SEEN || ours(pane))
        return;
    st->seen[st->seen_count][0] = group;
    st->seen[st->seen_count][1] = pane;
    st->seen_count++;
}

/* ---- the GUI ---------------------------------------------------------------------------------------------- */

static int option_on(u32 id)
{
    return mod_option_count((int)id) != 0 && mod_option_value((int)id) != 0;
}

/* The group is still its manager's at its index, with the hash it had */
static int group_alive(u32 group, u32 hash)
{
    u32 context, manager, index;

    if (group == 0 || W(group, G_HASH) != hash)
        return 0;
    context = W(group, G_CONTEXT);
    if (context < MANAGER_OF_CONTEXT)
        return 0;
    manager = context - MANAGER_OF_CONTEXT;
    index = W(group, G_FLAGS) >> G_INDEX_SHIFT;
    return index < W(manager, M_COUNT) && W(W(manager, M_GROUPS), index * 4) == group;
}

static int pool_room(u32 pool, u32 reserve)
{
    return W(pool, POOL_USED) + 1 + reserve <= W(pool, POOL_COUNT);
}

static u32 pool_take(u32 pool)
{
    u32 used = W(pool, POOL_USED), element = W(W(pool, POOL_ARRAY), used * 4);

    W(pool, POOL_USED) = used + 1;
    return element;
}

/* A changed sprite redrawn by a cached group: its node marked, or one queued while the pane pool has room */
static void touch(u32 group, u32 pane)
{
    u32 node;

    if ((W(group, G_FLAGS) & G_CACHED) == 0)
        return;
    node = W(pane, P_NODE);
    if (node != 0)
        B(node, NODE_DIRTY) = DIRTY;
    else if (pool_room(W(W(group, G_CONTEXT), 0), D->pane_reserve))
        pane_redraw(group, pane);
}

/* A new sprite of the group: a copy of `icon`'s data with our name and owner, linked nowhere yet; 0 without room */
static u32 make_sprite(u32 group, u32 icon, u32 hash, u32 owner)
{
    u32 context = W(group, G_CONTEXT), panes = W(context, 0), sprites = W(context, 4);
    u32 pane, data, slot, from = W(icon, P_DATA);
    int i;

    if (!pool_room(panes, D->pane_reserve) || !pool_room(sprites, D->sprite_reserve)) {
        ST->refusals++;
        return 0;
    }
    pane = pool_take(panes);
    data = pool_take(sprites);
    slot = W(data, S_FLAGS) & PRIMITIVE;
    for (i = 0; i < SPRITE_SIZE; i += 4)
        W(data, i) = W(from, i);
    W(data, S_U) = W(from, S_U) & ~LOW_BITS;                    /* never taken for a marked icon */
    W(data, S_FLAGS) = slot | CENTRE_ORIGIN;                    /* hidden until placed */
    W(data, S_OWNER) = owner;
    W(data, S_ANGLE) = 0;
    for (i = 0; i < PANE_SIZE; i += 4)
        W(pane, i) = 0;
    W(pane, P_HASH) = hash;
    W(pane, P_DATA) = data;
    B(pane, P_DEPTH) = B(icon, P_DEPTH);
    ST->made++;
    return pane;
}

/* The first of `parent`'s children, or of the group's top panes when `parent` is 0 */
static u32 first_child(u32 group, u32 parent)
{
    return parent != 0 ? W(parent, P_CHILD) : W(group, G_PANES);
}

/* `pane` as the last child of `parent` (0: the last top pane of `group`) */
static void link_last(u32 group, u32 parent, u32 pane)
{
    u32 last = first_child(group, parent), steps = 0;

    while (last != 0 && W(last, P_NEXT) != 0 && steps++ < WALK_LIMIT)
        last = W(last, P_NEXT);
    W(pane, P_PARENT) = parent;
    W(pane, P_PREV) = last;
    W(pane, P_NEXT) = 0;
    if (last != 0)
        W(last, P_NEXT) = pane;
    else if (parent != 0)
        W(parent, P_CHILD) = pane;
    else
        W(group, G_PANES) = pane;
}

/* `pane` just before `before`, a child of `parent` (0: a top pane of `group`) */
static void link_before(u32 group, u32 parent, u32 before, u32 pane)
{
    u32 prev = W(before, P_PREV);

    W(pane, P_PARENT) = parent;
    W(pane, P_PREV) = prev;
    W(pane, P_NEXT) = before;
    if (prev != 0)
        W(prev, P_NEXT) = pane;
    else if (parent != 0)
        W(parent, P_CHILD) = pane;
    else
        W(group, G_PANES) = pane;
    W(before, P_PREV) = pane;
}

/* Our sprite `hash` owned by `owner` among `parent`'s children (a cached pointer checked first), or 0 */
static u32 find_ours(u32 first, u32 cached, u32 parent, u32 hash, u32 owner)
{
    u32 pane = first, steps = 0;

    if (cached != 0 && W(cached, P_HASH) == hash && W(cached, P_PARENT) == parent &&
            W(W(cached, P_DATA), S_OWNER) == owner)
        return cached;
    while (pane != 0 && steps++ < WALK_LIMIT) {
        if (W(pane, P_HASH) == hash && B(pane, P_KIND) == KIND_SPRITE && W(W(pane, P_DATA), S_OWNER) == owner)
            return pane;
        pane = W(pane, P_NEXT);
    }
    return 0;
}

/* Write a word that differs; say so */
static int put(u32 data, u32 off, u32 value)
{
    if (W(data, off) == value)
        return 0;
    W(data, off) = value;
    return 1;
}

static u32 bits(float value)
{
    union { float f; u32 u; } v;

    v.f = value;
    return v.u;
}

/* Where a sprite is, in its parent's space: its top-left corner (screen terms: layout x grows to the left, y up) and
 * how many of its parent's units a texel of its cell takes. */
struct box {
    float left, top, kx, ky;
    float cell;                         /* its cell's side in texels: 16 or 24 */
};

/* An origin's point as a share of the width and the height from the top-left corner: a cell of a 3 x 3 grid, column
 * by column (core/interface/game_gui/geometry.py origin_point); past the grid, the corner */
static const float ORIGIN_X[16] = {0.0f, 0.0f, 0.0f, 0.5f, 0.5f, 0.5f, 1.0f, 1.0f, 1.0f};
static const float ORIGIN_Y[16] = {0.0f, 0.5f, 1.0f, 0.0f, 0.5f, 1.0f, 0.0f, 0.5f, 1.0f};

/* x * y / 255 for bytes, without a divide (the ARM11 has none) */
static u32 scale255(u32 x, u32 y)
{
    return (x * y * 0x8081u) >> 23;
}

static void icon_box(u32 data, struct box *box)
{
    u32 origin = W(data, S_FLAGS) & ORIGIN_MASK;
    float w = F(data, S_W) * F(data, S_SX), h = F(data, S_H) * F(data, S_SY);
    float fx = ORIGIN_X[origin], fy = ORIGIN_Y[origin];

    box->cell = F(data, S_UW) * SHEET > 20.0f ? 24.0f : 16.0f;
    box->left = F(data, S_X) + fx * w;
    box->top = F(data, S_Y) + fy * h;
    box->kx = w / box->cell;
    box->ky = h / box->cell;
}

/* A star's sprite at (dx, dy) texels from the icon's top-left corner (right, down), `side` texels across in cell
 * `cell` of star_uv, coloured `rgb` with the icon's alpha times `alpha` / 255; shown or not. Returns a change. */
static int place(u32 icon_data, u32 data, const struct box *box, float dx, float dy, float side, u32 cell, u32 rgb,
                 u32 alpha, int shown)
{
    u32 colour = rgb | scale255(W(icon_data, S_COLOURS) >> 24, alpha) << 24;
    u32 flags = (W(data, S_FLAGS) & PRIMITIVE) | CENTRE_ORIGIN | (shown ? SHOWN : 0u);
    int changed = 0, i;

    changed |= put(data, S_FLAGS, flags);
    if (!shown)
        return changed;
    changed |= put(data, S_X, bits(box->left - dx * box->kx));
    changed |= put(data, S_Y, bits(box->top - dy * box->ky));
    changed |= put(data, S_Z, W(icon_data, S_Z));
    changed |= put(data, S_W, bits(side));
    changed |= put(data, S_H, bits(side));
    changed |= put(data, S_SX, bits(box->kx));
    changed |= put(data, S_SY, bits(box->ky));
    for (i = 0; i < 4; i++) {
        changed |= put(data, S_U + 4 * i, D->star_uv[cell][i]);
        changed |= put(data, S_COLOURS + 4 * i, colour);
    }
    return changed;
}

/* ---- the upgrade stars ------------------------------------------------------------------------------------- */

/* A tracked icon let go of: its stars hidden first (a star left shown would stay over whatever item the icon gets
 * next, since an unmarked icon is never noted) */
static void forget(struct tracked *t)
{
    int k;

    if (!group_alive(t->group, t->hash))
        return;
    for (k = 0; k < 2; k++) {
        u32 star = t->star[k], data;
        if (star == 0 || W(star, P_HASH) != D->star_hash[k])
            continue;
        data = W(star, P_DATA);
        if (W(data, S_OWNER) == (t->icon | (u32)k) && put(data, S_FLAGS, W(data, S_FLAGS) & ~SHOWN))
            touch(t->group, star);
    }
}

/* A place in the table: a free one, else one whose group is gone or hidden (forgotten first); TRACKED: none */
static u32 table_place(void)
{
    struct marks_state *st = ST;
    u32 i;

    if (st->count < TRACKED)
        return st->count++;
    for (i = 0; i < TRACKED; i++) {
        struct tracked *t = &st->tracked[i];
        if (!group_alive(t->group, t->hash) || (W(t->group, G_FLAGS) & G_SHOWN) == 0) {
            forget(t);
            return i;
        }
    }
    return TRACKED;
}

static void note_seen(void)
{
    struct marks_state *st = ST;
    u32 i, j;

    for (i = 0; i < st->seen_count && i < SEEN; i++) {
        u32 group = st->seen[i][0], pane = st->seen[i][1];
        for (j = 0; j < st->count; j++)
            if (st->tracked[j].icon == pane && st->tracked[j].group == group)
                break;
        if (j < st->count)
            continue;
        j = table_place();
        if (j >= TRACKED) {
            st->lost++;
            continue;
        }
        st->tracked[j].group = group;
        st->tracked[j].hash = W(group, G_HASH);
        st->tracked[j].icon = pane;
        st->tracked[j].star[0] = 0;
        st->tracked[j].star[1] = 0;
    }
    st->seen_count = 0;
}

/* Where the icon's stars hang: its parent null, or TOP_LEVEL for a top pane of its group (a selected item's big
 * icon often is: ui021_icon_b00); NO_PARENT when they cannot (a text's holder: its glyph walk counts the children) */
#define TOP_LEVEL 0u
#define NO_PARENT 1u
static u32 star_parent(u32 icon)
{
    u32 parent, prev;

    if (B(icon, P_KIND) != KIND_SPRITE)
        return NO_PARENT;
    parent = W(icon, P_PARENT);
    if (parent == 0)
        return B(icon, P_DEPTH) == 1 ? TOP_LEVEL : NO_PARENT;
    if (B(parent, P_KIND) != KIND_NULL)
        return NO_PARENT;
    prev = W(parent, P_PREV);
    if (prev != 0 && B(prev, P_KIND) == KIND_TEXT)
        return NO_PARENT;
    return parent;
}

/* The upgrade stars' RGB: Star Colour's value in use (its first value when the page has no row for it) */
static u32 star_colour(void)
{
    int id = (int)D->colour_option, value = mod_option_count(id) != 0 ? mod_option_value(id) : 0;

    return D->star_rgb[value >= 0 && value < STAR_COLOURS ? value : 0];
}

/* One icon's stars: made, placed, hidden, inside the icon's square: one star at its top-left corner (`inset` in);
 * two, the back one `shift` to the right at the top and the front one `lift` lower. Returns 0 when the entry is to be
 * dropped (gone, or nothing left shown). */
static int keep_stars(struct tracked *t, int on, int *changed_group)
{
    u32 icon = t->icon, parent, icon_data, rgb = star_colour();
    int level, k;
    struct box box;

    if (!group_alive(t->group, t->hash))
        return 0;
    parent = star_parent(icon);
    if (parent == NO_PARENT)
        return 0;
    icon_data = W(icon, P_DATA);
    level = on ? mark_level(icon_data) : 0;
    icon_box(icon_data, &box);
    for (k = 1; k >= 0; k--) {          /* the back star first: it is drawn under the front one */
        u32 owner = icon | (u32)k, star, data;
        int big = box.cell > 20.0f, shown;
        float dx, dy;

        star = find_ours(first_child(t->group, parent), t->star[k], parent, D->star_hash[k], owner);
        if (star == 0 && level > k) {
            star = make_sprite(t->group, icon, D->star_hash[k], owner);
            if (star == 0)
                continue;
            if (k == 1 && (t->star[0] = find_ours(first_child(t->group, parent), t->star[0], parent,
                                                  D->star_hash[0], icon)) != 0)
                link_before(t->group, parent, t->star[0], star);
            else
                link_last(t->group, parent, star);
            *changed_group = 1;
        }
        t->star[k] = star;
        if (star == 0)
            continue;
        data = W(star, P_DATA);
        shown = level > k && (W(icon_data, S_FLAGS) & SHOWN) != 0;
        dx = D->inset + 0.5f * D->side[big] + (k == 1 ? D->shift[big] : 0.0f);
        dy = D->inset + 0.5f * D->side[big] + (k == 0 && level > 1 ? D->lift : 0.0f);
        if (place(icon_data, data, &box, dx, dy, D->side[big], D->side_cell[big], rgb, 255u, shown))
            touch(t->group, star);
    }
    return level > 0;
}

static void upgrade_stars(int on)
{
    struct marks_state *st = ST;
    u32 i = 0, changed_at = 0;

    note_seen();
    while (i < st->count) {
        int changed = 0;
        if (keep_stars(&st->tracked[i], on, &changed)) {
            if (changed && changed_at != st->tracked[i].group) {
                gui_group_changed(st->tracked[i].group);
                changed_at = st->tracked[i].group;
            }
            i++;
            continue;
        }
        if (changed)
            gui_group_changed(st->tracked[i].group);
        st->tracked[i] = st->tracked[--st->count];  /* dropped: its stars stay hidden in its group */
    }
}

/* ---- the rare rewards ----------------------------------------------------------------------------------------- */

static u32 find_group(u32 hash)
{
    u32 gui = gui_control, manager, list, count, i, group;

    if (gui == 0)
        return 0;
    manager = W(gui, 0x100);
    if (manager == 0)
        return 0;
    list = W(manager, M_GROUPS);
    count = W(manager, M_COUNT);
    for (i = 0; i < count; i++) {
        group = W(list, i * 4);
        if (group != 0 && W(group, G_HASH) == hash)
            return group;
    }
    return 0;
}

static u32 top_pane(u32 group, u32 hash)
{
    u32 pane = W(group, G_PANES), steps = 0;

    while (pane != 0 && steps++ < WALK_LIMIT) {
        if (W(pane, P_HASH) == hash)
            return pane;
        pane = W(pane, P_NEXT);
    }
    return 0;
}

static u32 phase_index(float phase)
{
    int i = (int)(phase * (float)PHASES);

    return (u32)(i < 0 ? 0 : i >= PHASES ? PHASES - 1 : i);
}

/* The grid's cell `i`: its halo (before the null) and its three twinkles (after the icons) */
static int rare_cell(u32 group, u32 grid, u32 icon, struct cell_marks *c, int rare)
{
    u32 icon_data = W(icon, P_DATA), null_data = W(grid, P_DATA);
    int shown = rare && (W(icon_data, S_FLAGS) & SHOWN) != 0 && (W(null_data, N_FLAGS) & N_SHOWN) != 0;
    int changed_group = 0, k;
    struct box box;

    if (c->icon != icon)
        c->halo = c->twinkle[0] = c->twinkle[1] = c->twinkle[2] = 0;
    c->icon = icon;
    c->halo = find_ours(W(group, G_PANES), c->halo, 0, D->halo_hash, icon);
    if (c->halo == 0 && shown) {
        c->halo = make_sprite(group, icon, D->halo_hash, icon);
        if (c->halo != 0) {
            B(c->halo, P_DEPTH) = 1;
            link_before(group, 0, grid, c->halo);
            changed_group = 1;
        }
    }
    icon_box(icon_data, &box);
    if (c->halo != 0) {
        u32 data = W(c->halo, P_DATA), alpha = D->halo_alpha[phase_index(ST->phase)], i, colour;
        float nsx = F(null_data, N_SX), nsy = F(null_data, N_SY);
        float cx = box.left - box.cell * 0.5f * box.kx, cy = box.top - box.cell * 0.5f * box.ky;
        int changed = put(data, S_FLAGS, (W(data, S_FLAGS) & PRIMITIVE) | CENTRE_ORIGIN | (shown ? SHOWN : 0u));

        if (shown) {
            colour = D->glow | scale255(W(icon_data, S_COLOURS) >> 24, alpha) << 24;
            changed |= put(data, S_X, bits(F(null_data, N_X) + nsx * cx));
            changed |= put(data, S_Y, bits(F(null_data, N_Y) + nsy * cy));
            changed |= put(data, S_Z, W(icon_data, S_Z));
            changed |= put(data, S_W, bits(D->halo_side));
            changed |= put(data, S_H, bits(D->halo_side));
            changed |= put(data, S_SX, bits(box.kx * nsx));
            changed |= put(data, S_SY, bits(box.ky * nsy));
            for (i = 0; i < 4; i++) {
                changed |= put(data, S_U + 4 * i, D->halo_uv[i]);
                changed |= put(data, S_COLOURS + 4 * i, colour);
            }
        }
        if (changed)
            touch(group, c->halo);
    }
    for (k = 0; k < TWINKLES; k++) {
        u32 owner = icon | (u32)k, cell;
        float phase = ST->phase - (float)k / (float)TWINKLES;
        u32 twinkle;

        if (phase < 0.0f)
            phase += 1.0f;
        cell = D->twinkle_cell[phase_index(phase)];
        twinkle = find_ours(W(grid, P_CHILD), c->twinkle[k], grid, D->twinkle_hash, owner);
        if (twinkle == 0 && shown) {
            twinkle = make_sprite(group, icon, D->twinkle_hash, owner);
            if (twinkle != 0) {
                link_last(group, grid, twinkle);
                changed_group = 1;
            }
        }
        c->twinkle[k] = twinkle;
        if (twinkle != 0 && place(icon_data, W(twinkle, P_DATA), &box, D->twinkle_x[k], D->twinkle_y[k],
                                  cell < SIZES ? 5.0f + 2.0f * (float)cell : 0.0f, cell < SIZES ? cell : 0,
                                  D->gold, 255u, shown && cell < SIZES))
            touch(group, twinkle);
    }
    return changed_group;
}

static void rare_rewards(int on)
{
    struct marks_state *st = ST;
    u32 scene = result_scene_object, group = st->rewards_group, grid, icon;
    u32 page = 0, i, cells = 0;
    int changed = 0;

    if (scene != 0)
        page = B(scene, SCENE_PAGE);
    if (!group_alive(group, st->rewards_hash)) {
        group = 0;
        st->rewards_group = 0;
        for (i = 0; i < CELLS; i++)
            st->cell[i].icon = 0;
        if (on && (page == 1 || page == 2)) {
            group = find_group(D->rewards_group);
            st->rewards_group = group;
            st->rewards_hash = D->rewards_group;
        }
    }
    if (group == 0)
        return;
    grid = top_pane(group, D->rewards_null);
    if (grid == 0 || B(grid, P_KIND) != KIND_NULL)
        return;
    if (page == 1 || page == 2)
        cells = scene + D->page_cells[page - 1];
    icon = W(grid, P_CHILD);
    for (i = 0; i < CELLS && icon != 0; i++, icon = W(icon, P_NEXT)) {
        int rare;
        if (B(icon, P_KIND) != KIND_SPRITE || W(icon, P_HASH) == D->twinkle_hash || W(icon, P_HASH) == D->star_hash[0] ||
                W(icon, P_HASH) == D->star_hash[1])
            break;
        rare = on && cells != 0 && (W(group, G_FLAGS) & G_SHOWN) != 0 && is_rare(H(cells, i * 4));
        if (!rare && st->cell[i].icon != icon)
            continue;                                   /* nothing made for it yet */
        changed |= rare_cell(group, grid, icon, &st->cell[i], rare);
    }
    if (changed)
        gui_group_changed(group);
}

void item_marks_frame(void)
{
    struct marks_state *st = ST;
    u32 main = game_main;
    float delta = main != 0 ? F(main, FRAME_DELTA) : 1.0f;

    if (!(delta > 0.0f && delta < 8.0f))
        delta = 1.0f;
    st->phase += delta / D->cycle;
    while (st->phase >= 1.0f)
        st->phase -= 1.0f;
    upgrade_stars(option_on(D->upgrade_option));
    rare_rewards(option_on(D->rare_option));
}
