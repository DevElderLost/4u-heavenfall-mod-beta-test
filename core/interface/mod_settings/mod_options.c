/* The options a player changes during play (interface/mod_settings/mod_options.py): where each lives, what it does each
frame, and what the hooks of
 * mod_options_stub.s read.
 *
 * Each option has a value: a place in its list of values. It is half a byte of the character's save zone (0: no choice
 * yet, else the place + 1; option n in half 20 + n: byte 10 + n / 2, the high half for an odd n), which counts only
 * with the magic and the mod's version (an older zone holds no choice: nothing is carried over from an older save),
 * and without a choice, a save, or on the title screen, the default the mod was installed with
 * (mod_options_data, from the curated gui_defaults.json). mod_frame, which the application's update calls first of all
 * each frame (FUN_00af52a0's call of FUN_00644320), reads every option into mod_options_state.values, where the hooks
 * of the game's functions find them, and does what only a write can do:
 *   - 3D, the frame rate and the camera's field of view are values the game rewrites, so they are written into the
 *     game's objects every frame (the draw object's display mode word, the main object's frame rate, the camera's
 *     field of view). The game's own value is kept the first time the option writes and put back when its value is
 *     "game's own" again;
 *   - the online waits, the camera's literals, the cap of the camera's turn, an item box menu's lines and the true
 *     attack's table are read by the hooks from the variable.
 * The values the writes use are in the option's payload, two words per value.
 *
 * A 3DS title's Cheats group is gated (struct cheats_gate): its options are 0 in the variable, whatever the character
 * chose, until the launcher's flag file has allowed them (cheats_frame), and mod_settings.c leaves its row out of the
 * page until then. Every reader of an option (mod_option_value, the variable's bytes, the payload) sees that 0.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM, a unit of the block mod_settings_code, linked with
 * mod_settings.ld); the game's variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef int s32;

#define MOD_OPTIONS 52         /* mod_options.py MAX_OPTIONS */
#define MOD_POOL 256            /* mod_options.py VALUE_POOL: the values of all the options; the first is none */
#define SAVE_DATA 0x5C          /* the save object's data starts here */
#define ZONE_WORDS 12           /* the save zone's size in words (curated mod_settings.json) */
#define ZONE_VERSION 4          /* its u16 */

/* mod_options.py OPTION_IDS (a number the list skips is an option this code does not have: 27 is Layered Gear's;
   28 on is the Cheats group, whose own code reads its ids from its data block) */
enum {
    OPT_3D, OPT_BLOOM, OPT_FPS, OPT_FOV, OPT_NET, OPT_RAW, OPT_LOCK, OPT_HOLD_A, OPT_FAST_TEXT,
    OPT_CAMERA = 10, OPT_BOX, OPT_KEYBOARD, OPT_DEATH_CAMERA, OPT_DAMAGE_NUMBERS, OPT_DAMAGE_OTHER, OPT_DAMAGE_STYLE,
    OPT_DAMAGE_SIZE, OPT_DAMAGE_DURATION, OPT_MODERN_CAMERA, OPT_HORN_SONGS, OPT_INTRO_SKIP,
    OPT_CAMERA_MAX, OPT_CAMERA_ACCEL, OPT_HORN_COLOUR, OPT_DISTANCE, OPT_SMITHY_VIEW,
    OPT_LAYERED_LOOKS,
    OPT_FAST_GATHERING = 28, OPT_FLEX, OPT_WHETSTONE, OPT_QUEST_END, OPT_REWARDS, OPT_CAPTURE_GURU, OPT_AUTOTRACKER,
    OPT_WORLD_SHARPNESS = 35, OPT_UPGRADE_STARS, OPT_RARE_REWARDS, OPT_STARS_COLOUR, OPT_HONING_GLOW,
    OPT_TOWN_MAP, OPT_ASPECT_CHEAT, OPT_DAMAGE_DEALT, OPT_DAMAGE_TAKEN
};

#define SLOT_3D 0               /* mod_options_state.saved: the game's word an option overwrites */
#define SLOT_FPS 1
#define SLOT_FOV 2

#define DISPLAY_MODE 0x6BA8     /* MtGX's draw object: the display mode word */
#define FRAME_RATE 0x30         /* the main object: the frame rate the limiter aims at */
#define LIMITER_BASE 0x2C       /* the main object: the limiter's 60.0 (frames a second at rate 1), a float */
#define FIELD_OF_VIEW 0xED0     /* sCamera: the camera's field of view */

struct mod_option {             /* mod_options.py options_data */
    u8 count;                   /* its values; 0: the mod does not have the option */
    u8 default_value;           /* the place the mod was installed with */
    u8 first;                   /* its first value in the pool (0, the none value, without the option) */
    u8 half;                    /* its half byte of the save zone: byte half / 2, the high half when odd */
};

/* The Cheats group's gate (mod_options.py cheats_gate): a 3DS title has the
 * group's rows and hooks, but they show and act only once the launcher's flag file allows them. All zeros in every
 * other mod: no option is gated and the flag is never read. */
struct cheats_gate {
    u32 options[2];             /* bit n % 32 of word n / 32: option n is 0 while the cheats are not allowed */
    u16 retry;                  /* the frames between two reads of the flag that got no answer */
    u16 pad;
};

struct mod_options_data {
    u32 zone_at;                /* the save zone in the save data */
    u32 magic;                  /* what marks it written */
    u16 version;                /* the zone's: an older one holds no choice */
    u16 help, row, marked;      /* the value list's texts: its description, a row, the row in use */
    struct mod_option options[MOD_OPTIONS];
    u16 names[MOD_POOL];        /* the pool: the message of each value's name */
    u32 payload[MOD_POOL][2];   /* and what each value writes or hands to a hook */
    struct cheats_gate gate;
};

_Static_assert(sizeof(struct mod_options_data) == 16 + MOD_OPTIONS * 4 + MOD_POOL * 10 + 12,
               "blocks.py MOD_OPTIONS_DATA_SIZE");

struct cheats_allowed {         /* blocks.py: the variable cheats_allowed (a title with the gate reserves it) */
    u8 allowed;                 /* 1: the flag file allows the cheats */
    u8 answered;                /* 1: the answer is final; 0: the flag is read again once `wait` is 0 */
    u16 wait;                   /* the frames until the next read */
    s32 io;                     /* the last read's result (beta_sidecar.c beta_cheats_flag), for a save state's reader */
    u32 reads;                  /* the reads so far */
};

_Static_assert(sizeof(struct cheats_allowed) == 12, "blocks.py CHEATS_ALLOWED_SIZE");

struct mod_options_state {      /* mod_options_stub.s has the offsets */
    u8 values[MOD_OPTIONS];     /* 0: each option's value this frame */
    u16 net_waits;              /* 52: the online waits (frames, polls; mod_options.py NET_LIMIT) */
    u16 net_polls;              /* 54 */
    u32 fov_one;                /* 56: the camera's literal in the reset case with the flags "not equal", and the other */
    u32 fov_other;              /* 60: and in the case "equal" */
    u32 raw_base;               /* 64: the weapon classes' table the menus read */
    u32 saved[3];               /* 68: the game's words (SLOT_*) */
    u32 camera_cap;             /* 80: the cap of how long a camera turn has been held (FUN_00bfd028; a float) */
    u32 hide_face;              /* 84: the mod has the lock-on and it is off: no target face (hud/target_face.c) */
    u8 box_lines;               /* 88: a menu's count of lines at a box away from home without Change Appearance's
                                       layout (FUN_009ec82c, mod_box_count); 0: the game's */
    u8 box_away;                /* 89: the box being opened is not the house's (mod_box_kind keeps the game's box) */
    u8 live;                    /* 90: bit n set while the option writes into slot n */
    u8 frame;                   /* 91: the frames counted (mod_frame), for a block that must know one went by */
    u32 camera_rest;            /* 92: the camera's resting distance (FUN_00bfff70; a float, 0 the game's 490) */
    u32 camera_event;           /* 96: an event's zoom-out (FUN_00c056d4; 0 the game's 630) */
    u32 camera_state;           /* 100: the distance in a state of the hunter (FUN_00c009ac; 0 the game's 300) */
};

_Static_assert(__builtin_offsetof(struct mod_options_state, values) == 0, "equipment/layered/layered_switch.c reads values[]");
_Static_assert(__builtin_offsetof(struct mod_options_state, net_waits) == 52, "mod_options_stub.s NET_WAITS");
_Static_assert(__builtin_offsetof(struct mod_options_state, net_polls) == 54, "mod_options_stub.s NET_POLLS");
_Static_assert(__builtin_offsetof(struct mod_options_state, fov_one) == 56, "mod_options_stub.s FOV_ONE");
_Static_assert(__builtin_offsetof(struct mod_options_state, fov_other) == 60, "mod_options_stub.s FOV_OTHER");
_Static_assert(__builtin_offsetof(struct mod_options_state, raw_base) == 64, "mod_options_stub.s RAW_BASE");
_Static_assert(__builtin_offsetof(struct mod_options_state, camera_cap) == 80, "mod_options_stub.s CAMERA_CAP");
_Static_assert(__builtin_offsetof(struct mod_options_state, hide_face) == 84, "hud/target_face.c, face_show.s HIDE_FACE");
_Static_assert(__builtin_offsetof(struct mod_options_state, box_lines) == 88, "mod_options_stub.s BOX_LINES");
_Static_assert(__builtin_offsetof(struct mod_options_state, box_away) == 89, "mod_options_stub.s BOX_AWAY");
_Static_assert(__builtin_offsetof(struct mod_options_state, frame) == 91, "modern_camera.c MOD_FRAME");
_Static_assert(__builtin_offsetof(struct mod_options_state, camera_rest) == 92, "mod_options_stub.s CAMERA_REST");
_Static_assert(__builtin_offsetof(struct mod_options_state, camera_event) == 96, "mod_options_stub.s CAMERA_EVENT");
_Static_assert(__builtin_offsetof(struct mod_options_state, camera_state) == 100, "mod_options_stub.s CAMERA_STATE");
_Static_assert(sizeof(struct mod_options_state) <= 104, "blocks.py: the variable mod_options_state");

extern const struct mod_options_data mod_options_data;
extern struct mod_options_state mod_options_state;
extern struct cheats_allowed cheats_allowed;
int beta_cheats_flag(s32 *io);  /* save/beta_sidecar.c: 1 allowed, 0 not (final), -1 not now; only a title with the
                                   gate has Heavenfall Beta's sidecars and calls it */
int mod_settings_open(void);    /* mod_settings.c: 1 while the page's lists or screens are on the screen */
extern const u32 mod_raw_table[16];
extern const u32 class_multipliers[16];
extern u32 save_control, gx_main, game_main, camera_control;
extern float fps_carry_state;   /* blocks.py: the vsyncs' fraction frame_rate_word carries */
extern u32 gui_control;         /* the GUI object (+ GUI_LAYOUTS its layout manager) */
extern const u32 appearance_binds[];    /* FUN_005976a8's table of ui415's root groups: 12 bytes each, the hash first */
u32 group_find(u32 manager, const u32 *key);                /* FUN_00b045a8: a group's index by the name's hash */
u32 group_at(u32 manager, u32 index);                       /* FUN_00b048f0: that group, 0 for none */
void appearance_peek_frame(void);       /* interface/appearance_peek/appearance_peek.c: the cue's end */

#define GUI_LAYOUTS 0x100

/* The save zone of the character in play, 0 without a save */
static u8 *save_zone(void)
{
    return save_control != 0 ? (u8 *)save_control + SAVE_DATA + mod_options_data.zone_at : 0;
}

int mod_option_saved(void)
{
    return save_zone() != 0;
}

/* The zone holds the mod's choices: its magic and the mod's version (an older zone's bytes mean other things) */
static int zone_ours(const u8 *zone)
{
    return zone != 0 && *(const u32 *)zone == mod_options_data.magic &&
           *(const u16 *)(zone + ZONE_VERSION) == mod_options_data.version;
}

/* A mod with the Cheats group's gate (a 3DS title's): some option is gated */
static int cheats_gated(void)
{
    return (mod_options_data.gate.options[0] | mod_options_data.gate.options[1]) != 0;
}

/* The flag file has allowed the cheats this launch (always 0 in a mod without the gate, which never reads it) */
int mod_cheats_allowed(void)
{
    return cheats_gated() && cheats_allowed.answered && cheats_allowed.allowed;
}

/* Option `id` is one of the gated cheats and they are not allowed: it is off, whatever the character chose */
static int gated_off(int id)
{
    return (mod_options_data.gate.options[id >> 5] >> (id & 31) & 1) != 0 && !mod_cheats_allowed();
}

/* The value of an option: the character's choice, else the default; 0 for a gated cheat while not allowed (the choice
 * stays in the zone) */
static int value_of(int id)
{
    const struct mod_option *option = &mod_options_data.options[id];
    const u8 *zone = save_zone();

    if (option->count == 0 || gated_off(id))
        return 0;
    if (zone_ours(zone)) {
        int chosen = zone[option->half >> 1] >> ((option->half & 1) * 4) & 0xF;

        if (chosen != 0 && chosen <= option->count)
            return chosen - 1;
    }
    return option->default_value;
}

int mod_option_value(int id)
{
    return mod_options_state.values[id];
}

int mod_option_count(int id)
{
    return mod_options_data.options[id].count;
}

/* What the option's value in use writes or hands to a hook (two words; Damage Numbers reads its floats); zeros for an
 * option the mod does not have */
const u32 *mod_option_payload(int id)
{
    return mod_options_data.payload[mod_options_data.options[id].first + mod_options_state.values[id]];
}

int mod_option_name(int id, int value)
{
    return mod_options_data.names[mod_options_data.options[id].first + value];
}

/* The value list's texts: 0 its description, 1 a row, 2 the row in use */
int mod_option_text(int which)
{
    return which == 0 ? mod_options_data.help : which == 1 ? mod_options_data.row : mod_options_data.marked;
}

/* The character's choice, used from the next frame. A new character's zone is zeros; one that is not the mod's (no
 * magic, or an older version) is made anew first: zeros, the magic and the version */
void mod_option_choose(int id, int value)
{
    const struct mod_option *option = &mod_options_data.options[id];
    u8 *zone = save_zone();
    int word, shift = (option->half & 1) * 4;

    if (zone == 0)
        return;
    if (!zone_ours(zone)) {
        for (word = 0; word < ZONE_WORDS; word++)
            ((u32 *)zone)[word] = 0;
        *(u32 *)zone = mod_options_data.magic;
        *(u16 *)(zone + ZONE_VERSION) = mod_options_data.version;
    }
    zone[option->half >> 1] = (zone[option->half >> 1] & ~(0xF << shift)) | (value + 1) << shift;
    mod_options_state.values[id] = gated_off(id) ? 0 : value;
}

/* A word of one of the game's objects: written while the option is on, the game's own put back when it goes off */
static void write_word(u32 object, int offset, int active, u32 word, int slot, u32 own)
{
    u32 *at = (u32 *)(object + offset);

    if (object == 0)
        return;
    if (active) {
        if (!(mod_options_state.live & (1u << slot))) {
            mod_options_state.saved[slot] = *at;
            mod_options_state.live |= 1u << slot;
        }
        *at = word;
    } else if (mod_options_state.live & (1u << slot)) {
        *at = own != 0 ? own : mod_options_state.saved[slot];
        mod_options_state.live &= ~(1u << slot);
    }
}

static const u32 *payload_of(int id)
{
    return mod_option_payload(id);
}

/* The camera's own field of view: the literal FUN_00bff28c loads for the camera's state, 58.0 when the state byte
 * (+0xE34) is 8 and the next is 1, else 50.0. The camera object is built again with every scene, so no word kept from
 * another scene is the camera's now; 0 while the camera does not exist */
static u32 game_fov(void)
{
    const u8 *state = (const u8 *)(camera_control + 0xE34);

    if (camera_control == 0)
        return 0;
    return state[0] == 8 && state[1] == 1 ? 0x42680000 : 0x42480000;
}

/* The camera's literals of its distance from the hunter (FUN_00bfff70, FUN_00c056d4, FUN_00c009ac) */
#define CAMERA_REST 490.0f
#define CAMERA_EVENT 630.0f
#define CAMERA_STATE 300.0f

/* A distance of the camera, the game's `game` times the option's factor (a float word): 0, the game's own literal, at
 * the factor 1 or without one (a mod without the row reads a zero payload) */
static u32 camera_distance(float game, u32 factor_word)
{
    union { u32 bits; float number; } factor, out;

    factor.bits = factor_word;
    if (!(factor.number > 0.0f) || factor.number == 1.0f)
        return 0;
    out.number = game * factor.number;
    return out.bits;
}

/* The frame rate word the limiter (FUN_00644320) is given. The limiter sleeps until a frame lasted base / word (in 60ths
 * of a second) after the last one, and the GX wait (FUN_00bf5fec) ends every frame on a vsync, so a frame lasts a whole
 * number of vsyncs and a target between them sleeps the frame off its vsync (50 fps ran as 45 when drawing took four
 * fifths of one: the overshoot is the frame's time, never given back). Each frame is given 1 or more whole vsyncs instead, the fractions added up in
 * fps_carry_state: 45 fps is three frames in every four vsyncs. 0 again when the option is off. */
static u32 frame_rate_word(u32 rate_word, int active)
{
    union { u32 bits; float number; } in, out;
    float rate, base, vsyncs;
    int whole;

    in.bits = rate_word;
    rate = in.number;
    if (!active)
        fps_carry_state = 0.0f;
    if (!active || game_main == 0)
        return rate_word;
    base = *(float *)(game_main + LIMITER_BASE);
    if (!(rate > 0.0f) || !(base > 0.0f))
        return rate_word;
    vsyncs = fps_carry_state + base / rate;
    if (!(vsyncs >= 1.0f && vsyncs < 4.0f))         /* not a value this wrote: start again */
        vsyncs = 1.0f;
    whole = (int)vsyncs;
    fps_carry_state = vsyncs - (float)whole;
    out.number = base / (float)whole;
    return out.bits;
}

/* The flag file read for the gate until it gave a final answer (allowed, or not: a file missing or not allowing):
 * one read, then none for `retry` frames when it got none (the extdata not mounted yet, the file thread busy, the file
 * unreadable). Never while the page is open, so its rows never change under the player; a read never waits for the
 * file thread (beta_cheats_flag). Nothing in a mod without the gate. */
static void cheats_frame(void)
{
    struct cheats_allowed *gate = &cheats_allowed;
    int answer;

    if (!cheats_gated() || gate->answered)
        return;
    if (gate->wait != 0) {
        gate->wait--;
        return;
    }
    if (mod_settings_open())
        return;
    gate->reads++;
    answer = beta_cheats_flag(&gate->io);
    if (answer < 0) {
        gate->wait = mod_options_data.gate.retry;
        return;
    }
    gate->allowed = answer == 1;
    gate->answered = 1;
}

/* FUN_00644320's caller, once per frame in every scene, before the engine's timing update */
void mod_frame(void)
{
    struct mod_options_state *state = &mod_options_state;
    int id;

    cheats_frame();
    for (id = 0; id < MOD_OPTIONS; id++)
        state->values[id] = value_of(id);
    write_word(gx_main, DISPLAY_MODE, state->values[OPT_3D] != 0, payload_of(OPT_3D)[0], SLOT_3D, 0);
    write_word(game_main, FRAME_RATE, state->values[OPT_FPS] != 0,
               frame_rate_word(payload_of(OPT_FPS)[0], state->values[OPT_FPS] != 0), SLOT_FPS, 0);
    write_word(camera_control, FIELD_OF_VIEW, state->values[OPT_FOV] != 0, payload_of(OPT_FOV)[0], SLOT_FOV,
               game_fov());
    state->fov_one = payload_of(OPT_FOV)[0];
    state->fov_other = payload_of(OPT_FOV)[1];
    state->net_waits = (u16)payload_of(OPT_NET)[0];
    state->net_polls = (u16)payload_of(OPT_NET)[1];
    state->raw_base = state->values[OPT_RAW] != 0 ? (u32)mod_raw_table : (u32)class_multipliers;
    state->hide_face = mod_options_data.options[OPT_LOCK].count != 0 && state->values[OPT_LOCK] == 0;
    state->camera_cap = payload_of(OPT_CAMERA)[0];
    state->box_lines = (u8)payload_of(OPT_BOX)[0];
    state->camera_rest = camera_distance(CAMERA_REST, payload_of(OPT_DISTANCE)[0]);
    state->camera_event = camera_distance(CAMERA_EVENT, payload_of(OPT_DISTANCE)[0]);
    state->camera_state = camera_distance(CAMERA_STATE, payload_of(OPT_DISTANCE)[0]);
    state->frame++;
    appearance_peek_frame();
}

/* The hunter's edit screen (Change Appearance) binds ui415's root groups, which only some areas load (the rooms', and
   the Gathering Hall's with interface/mod_settings/box_appearance.py): 1 when its first group is loaded. */
static int appearance_loaded(void)
{
    u32 manager, key[2] = {appearance_binds[0], 0};

    if (gui_control == 0 || (manager = *(u32 *)(gui_control + GUI_LAYOUTS)) == 0)
        return 0;
    return group_at(manager, group_find(manager, key)) != 0;
}

/* mod_box_lines (FUN_009ec82c's store of an item box menu's count of lines): the count to store. At a box away from
   home (mod_box_kind kept the game's box) with the option on, `lines` is the house's (the box became the house's) and
   its last line, Change Appearance, stays only where its screen's layout is loaded; else the option's count, which
   leaves it out. Off, at home, or before mod_frame has
   run, the game's. */
u32 mod_box_count(u32 lines)
{
    const struct mod_options_state *state = &mod_options_state;

    if (state->box_away == 0 || state->box_lines == 0)
        return lines;
    return appearance_loaded() ? lines : state->box_lines;
}
