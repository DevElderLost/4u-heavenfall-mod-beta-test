/* The World-style sharpness gauge (interface/world_sharpness/world_sharpness.py),
 * adapted from Jamo's mod "MH4U MH4G World Style Sharpness Indicator" (v1.1), used with Jamo's permission. While Mod
 * Settings' World Sharpness row is on, in a quest with a blade, on the HUD's sharpness gauge (the group ui202_kireaji):
 *   - the bar (ui202_color00) shrinks with the sharpness left in its colour, its left end kept in place (Jamo's
 *     formula: the bar's scale x is that share, and its x moves by the scale's change times its width times `slide`);
 *   - it has its level's World colour at a steady alpha (Jamo's animation's; the game's pulses);
 *   - the three frames (ui202_kire00..02) are darkened by a tint (the mod darkened their texture).
 * With the row off, what it changed goes back: the bar's scale to 1 with its x where it was, the frames' own colour; the
 * game's animation gives the bar its colours again.
 *
 * Jamo's mod did the bar from a hook in FUN_00b6b2ac (the hunter's sharpness changes by a delta), at its `cmp r7, #0`
 * after the level byte is stored, through a code cave; this runs from the quest's shared frame hook instead
 * (interface/quest_layouts/: sMhMain::frame, after every system's move and before the render), so its writes come after
 * the game's animation of the same frame and the row acts at once. It reads, all from the game:
 *   - the gauge: the sharpness group in ui202's binder (sharpness_binder, the group FUN_00b9d0f0 places), checked by its
 *     name hash; its sprites by their name hashes among its top panes;
 *   - the hunter: player_get(*sPlayer, sGameControl +0x2F); a blade, FUN_00d04dd4(hunter, 1) == 0 (FUN_00b6b2ac's own
 *     test); its work (+0xA29C): the sharpness (+0x294, s16), the most it can reach (+0x296, 0: no cap) and the level
 *     the game keeps (+0x293, 0-6);
 *   - the weapon's sharpness: FUN_002f0f34(*equipment, status + 0x1C0), seven s16, where each colour ends.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM; world_sharpness.ld).
 */

typedef unsigned int u32;
typedef signed char s8;
typedef unsigned char u8;
typedef short s16;

#define LEVELS 7                /* the sharpness colours, red to purple */
#define FRAMES 3                /* the gauge's frames */
#define MOST_PANES 32           /* a walk of the group's top panes stops here */

/* the game's objects (blocks.py GAME_SYMBOLS) */
extern u32 health_binder, game_control, player_manager, equipment_control, sharpness_binder;
extern int mod_option_value(int id);    /* mod_options.c */
extern int mod_option_count(int id);
u32 player_get(u32 manager, int index);                 /* FUN_00af9ab0 */
u32 is_gunner(u32 hunter, u32 kind);                    /* FUN_00d04dd4 */
const s16 *sharpness_ends(u32 equipment, u32 weapon);   /* FUN_002f0f34 */
void pane_redraw(u32 group, u32 node);                  /* FUN_00ae6bcc */

struct world_data {             /* the block world_sharpness_data (world_sharpness.py data_block) */
    u32 option;                 /* mod_options.py OPTION_IDS */
    u32 group_hash;             /* ~crc32 of the names: ui202_kireaji, */
    u32 frame_hash[FRAMES];     /* ui202_kire00..02, */
    u32 bar_hash;               /* ui202_color00 */
    u32 colour[LEVELS];         /* the bar's at each level: RGBA bytes */
    u32 tint;                   /* the frames' with the row on */
    u32 frame_colour;           /* and their own (the layout's) */
    float slide;                /* the bar's x change for its scale's, times its width */
};

_Static_assert(sizeof(struct world_data) == 64, "blocks.py WORLD_SHARPNESS_DATA_SIZE, world_sharpness.py data_block");

extern const struct world_data world_sharpness_data;

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define F(p, off) (*(volatile float *)((p) + (off)))
#define B(p, off) (*(volatile u8 *)((p) + (off)))
#define S(p, off) (*(volatile s16 *)((p) + (off)))

#define SHOWN 0x400             /* group + 0x44: drawn */
#define GROUP_PANES 0x08        /* a group's first top pane */
#define GAME_MODE 0x2B          /* sGameControl: 1 in a quest */
#define QUEST_MODE 1
#define LOCAL_INDEX 0x2F        /* sGameControl: this console's player */
#define HUNTER_STATUS 0xE30     /* uPlayer: its status */
#define HUNTER_WORK 0xA29C      /* uPlayer: its work */
#define RANGED 1                /* is_gunner's kind: a bowgun or a bow */
#define WEAPON 0x1C0            /* status: the weapon (its type, then its id) */
#define LEVEL 0x293             /* work: the sharpness level, 0-6 */
#define SHARPNESS 0x294         /* work: the sharpness (s16) */
#define CAP 0x296               /* work: the most it can reach (s16; 0: no cap) */
#define NODE_DATA 0x08          /* a pane's node: its data, */
#define NODE_DIRTY 0x0C         /* its redraw entry (+ DIRTY_MARK: 3 redraws it), */
#define DIRTY_MARK 0x12
#define NODE_NEXT 0x14          /* its next sibling */
#define SP_X 0x10               /* a sprite's data: x, */
#define SP_WIDTH 0x20           /* its width, */
#define SP_SCALE_X 0x28         /* its scale x, */
#define SP_COLOURS 0x40         /* its corners' colours */

static int in_quest(void)
{
    u32 control = game_control, hud = health_binder;

    return control != 0 && B(control, GAME_MODE) == QUEST_MODE && hud != 0 && (W(hud, 0x44) & SHOWN) != 0;
}

static int option_on(void)
{
    int id = (int)world_sharpness_data.option;

    return mod_option_count(id) != 0 && mod_option_value(id) != 0;
}

/* The sharpness gauge's group, shown; 0 otherwise */
static u32 gauge(void)
{
    u32 group = sharpness_binder;

    if (group == 0 || W(group, 0) != world_sharpness_data.group_hash || (W(group, 0x44) & SHOWN) == 0)
        return 0;
    return group;
}

static u32 top_pane(u32 group, u32 hash)
{
    u32 node = W(group, GROUP_PANES);
    int i;

    for (i = 0; node != 0 && i < MOST_PANES; i++, node = W(node, NODE_NEXT))
        if (W(node, 0) == hash)
            return node;
    return 0;
}

/* This console's hunter, with a blade: its work, and its status in `*status`; 0 otherwise */
static u32 blade_work(u32 *status)
{
    u32 control = game_control, manager = player_manager, hunter, work;

    if (control == 0 || manager == 0)
        return 0;
    hunter = player_get(manager, (s8)B(control, LOCAL_INDEX));
    if (hunter == 0 || (*status = W(hunter, HUNTER_STATUS)) == 0 || (work = W(hunter, HUNTER_WORK)) == 0)
        return 0;
    return is_gunner(hunter, RANGED) == 0 ? work : 0;
}

/* Jamo's share of the level's colour left, in `*share` (0-1): 0 when there is none (no level, no sharpness table,
 * a colour of no length below the cap) */
static int colour_left(u32 status, u32 work, float *share)
{
    u32 equipment = equipment_control, level = B(work, LEVEL);
    const s16 *ends;
    int low, high, cap, span, left;

    if (level >= LEVELS || equipment == 0 || (ends = sharpness_ends(equipment, status + WEAPON)) == 0)
        return 0;
    high = ends[level];
    low = level > 0 ? ends[level - 1] : 0;
    cap = S(work, CAP);
    if (cap == 0)
        cap = high;
    if (high > cap)
        high = cap;
    span = high - low;
    if (span <= 0)
        return 0;
    left = S(work, SHARPNESS) - low;
    if (left < 0)
        left = 0;
    if (left > span)
        left = span;
    *share = (float)left / (float)span;
    return 1;
}

static void changed(u32 group, u32 node)
{
    u32 dirty = W(node, NODE_DIRTY);

    if (dirty != 0)
        B(dirty, DIRTY_MARK) = 3;
    else
        pane_redraw(group, node);
}

static int coloured(u32 data, u32 colour)
{
    int i;

    for (i = 0; i < 4; i++)
        if (W(data, SP_COLOURS + 4 * i) != colour)
            return 0;
    return 1;
}

static void colour_all(u32 group, u32 node, u32 colour)
{
    u32 data = W(node, NODE_DATA);
    int i;

    if (coloured(data, colour))
        return;
    for (i = 0; i < 4; i++)
        W(data, SP_COLOURS + 4 * i) = colour;
    changed(group, node);
}

/* A sprite whose four corners are `from` gets `to`; one any other way (an animation's) is left alone */
static void recolour(u32 group, u32 node, u32 from, u32 to)
{
    if (coloured(W(node, NODE_DATA), from))
        colour_all(group, node, to);
}

/* The bar's scale x to `share`, its x moved by the change times its width times slide (Jamo's formula) */
static void bar_scale(u32 group, u32 node, float share)
{
    u32 data = W(node, NODE_DATA);
    float old = F(data, SP_SCALE_X);

    if (old == share)
        return;
    F(data, SP_X) = F(data, SP_X) + (share - old) * F(data, SP_WIDTH) * world_sharpness_data.slide;
    F(data, SP_SCALE_X) = share;
    changed(group, node);
}

/* the quest's shared frame hook: sMhMain::frame, after every system's move and before the render */
void world_sharpness_frame(void)
{
    const struct world_data *data = &world_sharpness_data;
    u32 group, bar, status = 0, work = 0;
    float share = 1.0f;
    int i;

    if (!in_quest() || (group = gauge()) == 0)
        return;
    if (option_on())
        work = blade_work(&status);
    for (i = 0; i < FRAMES; i++) {
        u32 frame = top_pane(group, data->frame_hash[i]);

        if (frame != 0)
            recolour(group, frame, work != 0 ? data->frame_colour : data->tint,
                     work != 0 ? data->tint : data->frame_colour);
    }
    if ((bar = top_pane(group, data->bar_hash)) == 0)
        return;
    if (work != 0) {
        if (B(work, LEVEL) < LEVELS)
            colour_all(group, bar, data->colour[B(work, LEVEL)]);
        if (!colour_left(status, work, &share))
            return;             /* as Jamo's code: the bar stays as it is */
    }
    bar_scale(group, bar, share);
}
