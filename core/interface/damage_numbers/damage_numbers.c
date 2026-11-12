/* Damage Numbers (interface/damage_numbers/damage_numbers.py): a number over the
 * monster at each hit, in the style the player picks in Mod Settings (Wilds, Rise or Classic).
 *
 * The hooks of damage_numbers_stub.s hand the game's damage to this code:
 *   - dmg_hit: FUN_00be9c64 (a hit on a monster) called FUN_00921f74, which adds the hit's final damage to the
 *     monster's damage of the frame (em + 0x4B4 + 2 * region); the stub hands the difference it made, the hit record
 *     and the caller's frame (the hitzone record at +0x4C, the melee's impact choice at +0x7C);
 *   - dmg_status: FUN_00920104 (the monster's damage step) took a poison tick or the mount's finish off its health, or
 *     a blast went off (the damage it added to the frame's damage);
 *   - dmg_frame: sMhMain::frame (FUN_00af52a0), after every system's move and before the render.
 * A hit shows when this player made it (the hunter, the Insect Glaive's kinsect, a shot or a thing the hunter threw),
 * and always when a monster made it or nobody did (the map's weapons); with Show All Damage (the option
 * damage_numbers_other) another player's hits show too; a Felyne's never do (any player's); a status damage shows at the
 * monster. dmg_frame turns them into numbers:
 *   - a number takes a slot of the group `hf_dmg` (our own layout, which damage_numbers_stub.s loads with the quest's
 *     layouts at a fixed index of the GUI manager); when all are taken, the oldest number gives its slot up;
 *   - its colour: gold for a physical hitzone at or above the curated threshold, white below it or unknown, grey for
 *     a bounce and for poison, gold for blast and the mount's finish, white for the other damage;
 *   - each frame its world point goes through the top screen's camera (sCamera's slot 0: the view matrix at +0xB0,
 *     the projection at +0xF0, row vectors) into the top screen's layout units: x grows to the left, y up, by
 *     k = max(120 * P[5], 200 * P[0]) (the aspect ratio option's wider picture included). A point behind the camera
 *     or off the picture is hidden, and shows again if the camera turns to it before the number ends;
 *   - it pops in, rises and fades over the chosen duration; the game's pause stops its clock;
 *   - numbers that land on one spot one after another stack upwards;
 *   - with Show All Damage, the health a monster loses that no hit or status damage explains shows at the monster.
 * The group shows only in a quest with the HUD on (the health bar's group shown) and while the option is on; it is
 * not cached (its flag 0x100 cleared), so the GUI walks its panes every frame and plain writes show at once.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM; damage_numbers.ld).
 */

typedef unsigned int u32;
typedef signed int s32;
typedef signed short s16;
typedef unsigned char u8;
typedef signed char s8;

#define SLOTS 16                /* damage_numbers.py SLOTS: the layout's slot nulls */
#define EFFECTS 2               /* a slot's critical marks, its first sprites */
#define DIGITS 6                /* then its digits */
#define EVENTS 16               /* numbers a frame */
#define MONSTERS 32             /* sEnemy's slots */
#define STYLES 3
#define SHARED 4                /* species whose parts share one health (curated) */

enum { KIND_HIT, KIND_POISON, KIND_BLAST, KIND_MOUNT, KIND_OTHER };     /* damage_numbers.py KINDS */
#define FLAG_CRIT 1
#define FLAG_BOUNCE 2
#define FLAG_POSITION 4         /* the event carries where it landed */
#define NO_HITZONE (-1)

enum { WHITE, GOLD, GREY };

/* the game's objects (blocks.py GAME_SYMBOLS) */
extern u32 camera_control, gui_control, game_main, health_binder, game_control, sunit, monster_data_manager;
extern int mod_option_value(int id);                    /* mod_options.c */
extern int mod_option_count(int id);
extern const u32 *mod_option_payload(int id);
void gui_group_show(u32 group, u32 shown);               /* FUN_00ae53e0 */
void gui_group_order(u32 group, u32 layer, u32 priority); /* FUN_00ae63c8 */

struct dmg_cell { float u, v, w, h; };                  /* a picture of the atlas, 0-1 */

struct dmg_effect {             /* a critical mark of a style */
    struct dmg_cell cell;
    float anchor_x, anchor_y;   /* -1, 0, 1: the digits' left, centre, right (bottom, centre, top) */
    float dx, dy;               /* then this far, in digit heights (screen right and up) */
    float w, h;                 /* its size in digit heights */
    float grow;                 /* how much of the digits' width it adds to its own width (0 or 1) */
    u32 colour;                 /* its tint, RGBA bytes (a glow and its bright core are two marks) */
};

struct dmg_style {
    struct dmg_cell digits[10];
    float digit_w, digit_h;     /* a digit's sprite, in digit heights (the cell's shape) */
    float advance;              /* from one digit to the next, in digit heights */
    float weak_scale;           /* a weak spot's number is this much bigger (Rise) */
    u32 effects;                /* how many of `effect` a critical hit shows */
    struct dmg_effect effect[EFFECTS];
};

struct dmg_data {               /* the block damage_numbers_data (damage_numbers.py data_block) */
    u32 group_hash;             /* ~crc32 of the group's name */
    u32 group_index;            /* its slot in the GUI manager */
    u32 layer, priority;
    u32 option_on, option_other, option_style, option_size, option_duration;   /* mod_options.py OPTION_IDS */
    s32 weak_hitzone;           /* a physical hitzone at least this is a weak spot */
    u32 colours[3];             /* WHITE, GOLD, GREY: RGBA bytes */
    float digit_height;         /* a digit's height in layout units at size 1x */
    float frame_seconds;        /* the game's frame delta of 1.0 is this long */
    float pop_seconds, pop_scale;   /* a new number starts pop_scale big and settles in pop_seconds */
    float rise;                 /* how far it rises over its life, in layout units */
    float fade_from;            /* the part of its life after which it fades */
    float stack_radius, stack_seconds, stack_step;  /* a number within stack_radius units of one younger than
                                                       stack_seconds goes stack_step digit heights higher */
    u32 stack_max;
    float edge;                 /* how far past the picture's edge (in NDC) a number still shows */
    float monster_lift;         /* a number at the monster (no point of its own) goes this high over it */
    u8 shared[SHARED];          /* species whose parts share one health: no other damage for them (0: none) */
    struct dmg_style styles[STYLES];
};

struct dmg_event {
    float x, y, z;
    u32 em;
    s32 value;
    s32 hitzone;
    u8 kind, flags, pad[2];
};

struct dmg_slot {
    float x, y, z;              /* the world point */
    float age;                  /* seconds */
    float stack;                /* layout units above its point */
    s32 value;
    u8 live, colour, crit, weak;
    u8 style, pad[3];
};

struct dmg_monster {            /* sEnemy's slot, for the other damage */
    u32 em;
    s32 hp;                     /* its health last frame */
    s32 accounted;              /* this frame's damage the hooks saw */
    s32 carried;                /* last frame's, not seen in its health yet (the health may drop a frame later) */
};

struct dmg_state {              /* the variable damage_numbers_state */
    u32 group;                  /* the group found last, 0: none */
    u8 shown, events, pad[2];
    struct dmg_event event[EVENTS];
    struct dmg_slot slot[SLOTS];
    struct dmg_monster monster[MONSTERS];
};

_Static_assert(sizeof(struct dmg_data) == 932,"blocks.py DAMAGE_NUMBERS_DATA_SIZE, damage_numbers.py data_block");
_Static_assert(sizeof(struct dmg_state) == 1480, "blocks.py DAMAGE_NUMBERS_STATE_SIZE");

extern const struct dmg_data damage_numbers_data;
extern struct dmg_state damage_numbers_state;

static int option(u32 id);

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define F(p, off) (*(volatile float *)((p) + (off)))
#define B(p, off) (*(volatile u8 *)((p) + (off)))
#define H(p, off) (*(volatile s16 *)((p) + (off)))

#define SHOWN 0x400             /* group + 0x44: drawn */
#define CACHED 0x100            /* group + 0x44: its vertices are kept between frames */
#define EM 0xE28                /* uEnemy: its em */
#define EM_SET 0x140            /* em: set up (with EM_ON) */
#define EM_ON 0x143
#define EM_POSITION 0x198
#define EM_SPECIES 0x1C0
#define EM_HP 0x3E8
#define ENEMY_SLOTS 0x18        /* sEnemy: uEnemy *[MONSTERS] */
#define HIT_SPOT 0x20           /* the hit record: where it landed (the shapes' meeting point) */
#define HIT_QUALITY 0x06        /* 0 a melee hit that bounced */
#define HIT_OBJECT 0x10         /* what made it */
#define HIT_FLAGS 0x30          /* bit 0: a shot */
#define HIT_CRIT 0x4C           /* 2: a critical hit */
#define HIT_OWNER_KIND 0x67     /* the owner of a shot or a kinsect */
#define HIT_OWNER 0x68
#define FRAME_HITZONE 0x4C      /* FUN_00be9c64's frame: the hitzone record (cut, impact, shot, ...) */
#define FRAME_IMPACT 0x7C       /* 1: a melee hit took the impact value */
#define HUNTER_STATUS 0xE30     /* uPlayer: its status, +0x33 its player number */
#define PLAYER_NUMBER 0x2F      /* sGameControl: this console's player */
#define CRIT_UP 2
enum { BY_HUNTER, BY_MONSTER, BY_SHELL, BY_PALICO, BY_KINSECT = 7 };
#define CAMERA_SLOT 0x1A8       /* sCamera's slots */
#define VIEW 0xB0               /* a slot's view matrix */
#define PROJECTION 0xF0         /* its projection */
#define CAMERA 0x1C             /* its camera object */
#define NEAR 0x34               /* the camera's near plane */
#define GAME_MODE 0x2B          /* sGameControl: 1 in a quest */
#define QUEST_MODE 1
#define DELTA 0x5C              /* the main object's frame delta */
#define PAUSE_LINE 5            /* sUnit's move line of the monsters, whose flags have PAUSED in the quest's pause */
#define PAUSED 2

/* ---- events */

static void push(u32 em, const float *pos, s32 value, s32 hitzone, u32 kind, u32 flags)
{
    struct dmg_state *state = &damage_numbers_state;
    struct dmg_event *event;

    if (value <= 0 || state->events >= EVENTS)
        return;
    event = &state->event[state->events++];
    event->em = em;
    event->value = value;
    event->hitzone = hitzone;
    event->kind = (u8)kind;
    event->flags = (u8)flags;
    if (pos != 0) {
        event->x = pos[0], event->y = pos[1], event->z = pos[2];
        event->flags |= FLAG_POSITION;
    }
}

/* The hooks' damage counts against the health the monster loses (the other damage) */
static void account(u32 em, s32 value)
{
    struct dmg_state *state = &damage_numbers_state;
    int i;

    for (i = 0; i < MONSTERS; i++)
        if (state->monster[i].em == em && em != 0)
            state->monster[i].accounted += value;
}

static int this_player(s32 player)
{
    u32 control = game_control;

    return control != 0 && (s8)player == (s8)B(control, PLAYER_NUMBER);
}

static int this_players_hunter(u32 hunter)
{
    return hunter != 0 && W(hunter, HUNTER_STATUS) != 0 && this_player((s8)B(W(hunter, HUNTER_STATUS), 0x33));
}

enum { MINE, OTHERS, FELYNES };

/* Whose a hit is, by its object kind: this player's, another's (or a monster's, or nobody's: MINE, every player sees
 * those), or a Felyne's, any player's (never shown) */
static int whose(u32 hit, u32 hunter)
{
    switch (B(hit, HIT_OBJECT)) {
    case BY_HUNTER:
        return this_players_hunter(hunter) ? MINE : OTHERS;
    case BY_KINSECT:
        return this_players_hunter(W(hit, HIT_OWNER)) ? MINE : OTHERS;
    case BY_PALICO:
        return FELYNES;
    case BY_SHELL:
        if (B(hit, HIT_OWNER_KIND) == BY_HUNTER)
            return this_players_hunter(W(hit, HIT_OWNER)) ? MINE : OTHERS;
        if (B(hit, HIT_OWNER_KIND) == BY_PALICO)
            return FELYNES;
        return MINE;            /* a monster's, or the map's: every player sees it */
    default:
        return MINE;            /* a monster on a monster, or nobody's */
    }
}

/* The physical hitzone value the hit met: a shot's, a melee hit's cut or impact; NO_HITZONE for the others */
static s32 hitzone_of(u32 hit, u32 frame)
{
    u32 record = W(frame, FRAME_HITZONE);
    u32 by = B(hit, HIT_OBJECT);

    if (record == 0)
        return NO_HITZONE;
    if (W(hit, HIT_FLAGS) & 1)
        return B(record, 2);
    if (by == BY_HUNTER)        /* a Palico's melee hit never gets here (whose) */
        return B(record, B(frame, FRAME_IMPACT) == 1 ? 1 : 0);
    return NO_HITZONE;
}

/* damage_numbers_stub.s, after FUN_00be9c64's call of FUN_00921f74: `dealt` is what it added to the monster's damage of
 * the frame (the hit's final damage), `frame` FUN_00be9c64's stack frame */
void dmg_hit(u32 enemy, u32 region, s32 dealt, u32 hit, u32 hunter, u32 frame)
{
    u32 em = enemy != 0 ? W(enemy, EM) : 0, by, flags = 0;
    int owner;

    (void)region;
    dealt = (s16)dealt;
    if (em == 0 || hit == 0 || dealt <= 0)
        return;
    account(em, dealt);         /* counted whoever made it: it never comes back as damage no hit explains */
    owner = whose(hit, hunter);
    if (owner == FELYNES || (owner == OTHERS && option(damage_numbers_data.option_other) == 0))
        return;                 /* another player's: shown only with Show All Damage */
    by = B(hit, HIT_OBJECT);
    if (B(hit, HIT_CRIT) == CRIT_UP)
        flags |= FLAG_CRIT;
    if (by == BY_HUNTER && !(W(hit, HIT_FLAGS) & 1) && B(hit, HIT_QUALITY) == 0)
        flags |= FLAG_BOUNCE;
    push(em, (const float *)(hit + HIT_SPOT), dealt, hitzone_of(hit, frame), KIND_HIT, flags);
}

/* damage_numbers_stub.s: a poison tick, a blast or the mount's finish took `value` off the monster `enemy` */
void dmg_status(u32 enemy, s32 value, u32 kind)
{
    u32 em = enemy != 0 ? W(enemy, EM) : 0;

    if (em == 0 || value <= 0)
        return;
    account(em, value);
    push(em, 0, value, NO_HITZONE, kind, 0);
}

/* ---- the camera */

/* `p` in the top screen's layout units; 0 when it is behind the camera or off the picture. Without a camera, the
 * screen's centre. */
static int project(const float *p, float *x, float *y)
{
    const struct dmg_data *data = &damage_numbers_data;
    u32 slot = camera_control;
    const volatile float *v, *m;
    float vx, vy, vz, w, k, near, room;

    if (slot == 0 || W(slot, CAMERA) == 0) {
        *x = 0.0f, *y = 0.0f;
        return 1;
    }
    v = (const volatile float *)(slot + VIEW);
    m = (const volatile float *)(slot + PROJECTION);
    vx = p[0] * v[0] + p[1] * v[4] + p[2] * v[8] + v[12];
    vy = p[0] * v[1] + p[1] * v[5] + p[2] * v[9] + v[13];
    vz = p[0] * v[2] + p[1] * v[6] + p[2] * v[10] + v[14];
    w = -vz;
    near = F(W(slot, CAMERA), NEAR);
    if (w <= near)
        return 0;
    room = w * (1.0f + data->edge);
    if (m[0] * vx > room || m[0] * vx < -room || m[5] * vy > room || m[5] * vy < -room)
        return 0;
    k = 120.0f * m[5] > 200.0f * m[0] ? 120.0f * m[5] : 200.0f * m[0];
    *x = -k * vx / w;
    *y = k * vy / w;
    return 1;
}

/* ---- the game's state */

static u32 find_group(void)
{
    const struct dmg_data *data = &damage_numbers_data;
    u32 gui = gui_control, manager, group;

    if (gui == 0 || (manager = W(gui, 0x100)) == 0 || W(manager, 0x154) == 0)
        return 0;
    if (data->group_index >= W(manager, 0x160))
        return 0;
    group = W(W(manager, 0x154), 4 * data->group_index);
    return group != 0 && W(group, 0) == data->group_hash ? group : 0;
}

static int in_quest(void)
{
    u32 control = game_control, hud = health_binder;

    return control != 0 && B(control, GAME_MODE) == QUEST_MODE && hud != 0 && (W(hud, 0x44) & SHOWN) != 0;
}

static int paused(void)
{
    u32 unit = sunit, main = game_main;

    if (unit != 0 && (W(unit, 0x14 + 0x18 * PAUSE_LINE + 8) & PAUSED))
        return 1;
    return main != 0 && B(main, 0x57) != 0 && B(main, 0x50) == 0;
}

static int option(u32 id)
{
    return mod_option_count((int)id) != 0 ? mod_option_value((int)id) : 0;
}

static float option_float(u32 id, float otherwise)
{
    union { u32 word; float number; } value;

    if (mod_option_count((int)id) == 0)
        return otherwise;
    value.word = mod_option_payload((int)id)[0];
    return value.number;
}

/* ---- the other damage */

static int shares_health(u32 em)
{
    int i;

    for (i = 0; i < SHARED; i++)
        if (damage_numbers_data.shared[i] != 0 && damage_numbers_data.shared[i] == B(em, EM_SPECIES))
            return 1;
    return 0;
}

/* Each of sEnemy's monsters: the health it lost since last frame that no hook's damage explains */
static void other_damage(int on)
{
    struct dmg_state *state = &damage_numbers_state;
    u32 manager = monster_data_manager;
    int i;

    for (i = 0; i < MONSTERS; i++) {
        struct dmg_monster *m = &state->monster[i];
        u32 enemy = manager != 0 ? W(manager, ENEMY_SLOTS + 4 * i) : 0;
        u32 em = enemy != 0 ? W(enemy, EM) : 0;
        s32 hp, lost, explained;

        if (em == 0 || B(em, EM_SET) == 0 || B(em, EM_ON) == 0 || shares_health(em)) {
            m->em = 0;
            continue;
        }
        hp = *(volatile s32 *)(em + EM_HP);
        if (m->em != em) {      /* a monster new in this slot */
            m->em = em, m->hp = hp, m->accounted = 0, m->carried = 0;
            continue;
        }
        lost = m->hp > hp ? m->hp - hp : 0;
        m->hp = hp;
        explained = m->carried + m->accounted < lost ? m->carried + m->accounted : lost;
        /* last frame's damage first; what is left of this frame's waits one frame, last frame's is dropped */
        m->carried = m->accounted - (explained > m->carried ? explained - m->carried : 0);
        m->accounted = 0;
        if (on && lost > explained)
            push(em, 0, lost - explained, NO_HITZONE, KIND_OTHER, 0);
    }
}

/* ---- numbers */

static int colour_of(const struct dmg_event *event)
{
    switch (event->kind) {
    case KIND_POISON:
        return GREY;
    case KIND_BLAST:
    case KIND_MOUNT:
        return GOLD;
    case KIND_OTHER:
        return WHITE;
    default:
        if (event->flags & FLAG_BOUNCE)
            return GREY;
        return event->hitzone != NO_HITZONE && event->hitzone >= damage_numbers_data.weak_hitzone ? GOLD : WHITE;
    }
}

static float distance2(float ax, float ay, float bx, float by)
{
    return (ax - bx) * (ax - bx) + (ay - by) * (ay - by);
}

static void spawn(const struct dmg_event *event, int style)
{
    const struct dmg_data *data = &damage_numbers_data;
    struct dmg_state *state = &damage_numbers_state;
    struct dmg_slot *slot = 0;
    float sx, sy, ox, oy;
    u32 near = 0;
    int i, oldest = 0, seen;

    for (i = 0; i < SLOTS && slot == 0; i++)
        if (!state->slot[i].live)
            slot = &state->slot[i];
    if (slot == 0) {
        for (i = 1; i < SLOTS; i++)
            if (state->slot[i].age > state->slot[oldest].age)
                oldest = i;
        slot = &state->slot[oldest];
    }
    if (event->flags & FLAG_POSITION) {
        slot->x = event->x, slot->y = event->y, slot->z = event->z;
    } else if (event->em != 0) {
        slot->x = F(event->em, EM_POSITION);
        slot->y = F(event->em, EM_POSITION + 4) + data->monster_lift;
        slot->z = F(event->em, EM_POSITION + 8);
    } else {
        slot->x = slot->y = slot->z = 0.0f;
    }
    slot->live = 0;
    seen = project(&slot->x, &sx, &sy);
    for (i = 0; seen && i < SLOTS; i++) {   /* the numbers that just landed near it */
        struct dmg_slot *other = &state->slot[i];
        float p[3];

        if (!other->live || other->age >= data->stack_seconds)
            continue;
        p[0] = other->x, p[1] = other->y, p[2] = other->z;
        if (project(p, &ox, &oy) && distance2(sx, sy, ox, oy) <= data->stack_radius * data->stack_radius)
            near++;
    }
    if (near > data->stack_max)
        near = data->stack_max;
    slot->stack = (float)near * data->stack_step * data->digit_height;
    slot->age = 0.0f;
    slot->value = event->value;
    slot->colour = (u8)colour_of(event);
    slot->crit = (event->flags & FLAG_CRIT) != 0 && event->kind == KIND_HIT;
    slot->weak = slot->colour == GOLD && event->kind == KIND_HIT;
    slot->style = (u8)style;
    slot->live = 1;
}

/* ---- drawing */

static void sprite(u32 pane, const struct dmg_cell *cell, float x, float y, float w, float h, u32 colour, int shown)
{
    u32 data = W(pane, 8);
    int corner;

    if (data == 0)
        return;
    if (!shown) {
        W(data, 0x58) &= ~0x80u;
        return;
    }
    F(data, 0x10) = x, F(data, 0x14) = y, F(data, 0x18) = 0.0f;
    F(data, 0x20) = w, F(data, 0x24) = h;
    F(data, 0x28) = 1.0f, F(data, 0x2C) = 1.0f;
    F(data, 0x30) = cell->u, F(data, 0x34) = cell->v, F(data, 0x38) = cell->w, F(data, 0x3C) = cell->h;
    for (corner = 0; corner < 4; corner++)
        W(data, 0x40 + 4 * corner) = colour;
    W(data, 0x58) |= 0x80u;
}

static void null_place(u32 pane, float x, float y, float scale, u32 alpha, int shown)
{
    u32 data = W(pane, 8);

    if (data == 0)
        return;
    if (!shown) {
        W(data, 0x24) &= ~1u;
        return;
    }
    F(data, 0x00) = x, F(data, 0x04) = y, F(data, 0x08) = 0.0f;
    F(data, 0x10) = scale, F(data, 0x14) = scale;
    W(data, 0x18) = ~0u >> 8 | alpha << 24;          /* white, faded by its alpha */
    W(data, 0x24) |= 1u;
}

/* v / 10 without a division (the ARM11 has none): v * ceil(2^35 / 10) >> 35, exact for every u32 */
static u32 tenth(u32 v)
{
    return (u32)(((unsigned long long)v * 0xCCCCCCCDu) >> 35);
}

static float smooth(float t)
{
    return t >= 1.0f ? 1.0f : t <= 0.0f ? 0.0f : 1.0f - (1.0f - t) * (1.0f - t);
}

/* One slot's panes (its null; in it EFFECTS marks, drawn behind, then DIGITS digits) for its number this frame */
static void draw_slot(u32 null, const struct dmg_slot *slot, float life, float size)
{
    const struct dmg_data *data = &damage_numbers_data;
    const struct dmg_style *style = &data->styles[slot->style];
    u32 pane = W(null, 0x20);
    char digits[DIGITS];
    float x, y, p[3], t = slot->age / life, scale, box, half, fade;
    u32 value = (u32)slot->value;
    int count = 0, i;

    p[0] = slot->x, p[1] = slot->y, p[2] = slot->z;
    if (!slot->live || !project(p, &x, &y)) {
        null_place(null, 0.0f, 0.0f, 0.0f, 0, 0);
        return;
    }
    do {
        u32 rest = tenth(value);

        digits[count++] = (char)(value - 10 * rest);
        value = rest;
    } while (value > 0 && count < DIGITS);
    scale = data->digit_height * size * (slot->weak ? style->weak_scale : 1.0f);
    if (slot->age < data->pop_seconds)
        scale *= data->pop_scale + (1.0f - data->pop_scale) * smooth(slot->age / data->pop_seconds);
    fade = t <= data->fade_from ? 1.0f : 1.0f - (t - data->fade_from) / (1.0f - data->fade_from);
    fade = fade < 0.0f ? 0.0f : fade > 1.0f ? 1.0f : fade;
    y += slot->stack + data->rise * smooth(t);
    null_place(null, x, y, scale, (u32)(255.0f * fade + 0.5f), 1);

    /* in the null one digit height is 1; the screen's x grows to the right, the layout's to the left */
    box = (float)count * style->advance;
    half = box / 2.0f;
    for (i = 0; i < EFFECTS && pane != 0; i++, pane = W(pane, 0x14)) {
        const struct dmg_effect *effect = &style->effect[i];
        float ex = effect->anchor_x * half + effect->dx, ey = effect->anchor_y * 0.5f + effect->dy;

        sprite(pane, &effect->cell, -ex, ey, effect->w + effect->grow * box, effect->h, effect->colour,
               slot->crit && (u32)i < style->effects);
    }
    for (i = 0; i < DIGITS && pane != 0; i++, pane = W(pane, 0x14)) {
        float sx = -half + ((float)i + 0.5f) * style->advance;     /* the i-th digit from the left */

        sprite(pane, &style->digits[i < count ? (int)digits[count - 1 - i] : 0], -sx, 0.0f, style->digit_w,
               style->digit_h, data->colours[slot->colour], i < count);
    }
}

static void clear(struct dmg_state *state)
{
    int i;

    for (i = 0; i < SLOTS; i++)
        state->slot[i].live = 0;
    state->events = 0;
    if (state->group != 0 && state->shown) {
        gui_group_show(state->group, 0);
        state->shown = 0;
    }
}

/* sMhMain::frame, after every system's move and before the render */
void dmg_frame(void)
{
    const struct dmg_data *data = &damage_numbers_data;
    struct dmg_state *state = &damage_numbers_state;
    u32 group = find_group(), null;
    float dt, life, size;
    int i, style, on = option(data->option_on) != 0;

    if (group != state->group) {        /* a new quest's group, or none */
        state->group = group;
        state->shown = 0;
        for (i = 0; i < SLOTS; i++)
            state->slot[i].live = 0;
        if (group != 0)
            W(group, 0x44) &= ~CACHED;
    }
    other_damage(on && option(data->option_other) != 0);
    if (group == 0 || !on || !in_quest()) {
        clear(state);
        return;
    }
    style = option(data->option_style);
    if (style < 0 || style >= STYLES)
        style = 0;
    size = option_float(data->option_size, 1.0f);
    life = option_float(data->option_duration, 0.9f);
    if (life <= 0.0f)
        life = 0.9f;
    dt = paused() || game_main == 0 ? 0.0f : F(game_main, DELTA) * data->frame_seconds;
    for (i = 0; i < SLOTS; i++)
        if (state->slot[i].live && (state->slot[i].age += dt) >= life)
            state->slot[i].live = 0;
    for (i = 0; i < state->events; i++)
        spawn(&state->event[i], style);
    state->events = 0;
    if (!state->shown) {
        gui_group_show(group, 1);
        gui_group_order(group, data->layer, data->priority);
        state->shown = 1;
    }
    for (i = 0, null = W(group, 8); i < SLOTS && null != 0; i++, null = W(null, 0x14))
        draw_slot(null, &state->slot[i], life, size);
}
