/* The options a player changes during play (interface/mod_settings/mod_options.py): where each lives, what it does each
frame, and what the hooks of
 * mod_options_stub.s read.
 *
 * Each option has a value: a place in its list of values. It is a byte of the character's save zone (0: no choice yet,
 * else the place + 1), and without a choice, a save, or on the title screen, the default the mod was installed with
 * (mod_options_data, from the curated gui_defaults.json). mod_frame, which the application's update calls first of all
 * each frame (FUN_00af52a0's call of FUN_00644320), reads every option into mod_options_state.values, where the hooks
 * of the game's functions find them, and does what only a write can do:
 *   - 3D, the frame rate and the camera's field of view are values the game rewrites, so they are written into the
 *     game's objects every frame (the draw object's display mode word, the main object's frame rate, the camera's
 *     field of view). The game's own value is kept the first time the option writes and put back when its value is
 *     "game's own" again;
 *   - the online waits, the camera's literals and the true attack's table are read by the hooks from the variable.
 * The values the writes use are in the option's payload, two words per value.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, ARM, a unit of the block mod_settings_code, linked with
 * mod_settings.ld); the game's variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define MOD_OPTIONS 12          /* mod_options.py MAX_OPTIONS */
#define MOD_VALUES 16           /* mod_options.py MAX_VALUES */
#define SAVE_DATA 0x5C          /* the save object's data starts here */
#define ZONE_WORDS 12           /* the save zone's size in words (curated mod_settings.json) */
#define ZONE_VERSION 4          /* its u16 */

/* mod_options.py OPTION_IDS */
enum {
    OPT_3D, OPT_BLOOM, OPT_FPS, OPT_FOV, OPT_NET, OPT_RAW, OPT_LOCK, OPT_HOLD_A, OPT_FAST_TEXT, OPT_FAST_GATHERING
};

#define SLOT_3D 0               /* mod_options_state.saved: the game's word an option overwrites */
#define SLOT_FPS 1
#define SLOT_FOV 2

#define DISPLAY_MODE 0x6BA8     /* MtGX's draw object: the display mode word */
#define FRAME_RATE 0x30         /* the main object: the frame rate the limiter aims at */
#define FIELD_OF_VIEW 0xED0     /* sCamera: the camera's field of view */

struct mod_option {             /* mod_options.py options_data */
    u8 count;                   /* its values; 0: the mod does not have the option */
    u8 default_value;           /* the place the mod was installed with */
    u8 byte;                    /* its byte of the save zone */
    u8 pad;
    u16 names[MOD_VALUES];      /* the message of each value's name */
    u32 payload[MOD_VALUES][2]; /* what each value writes or hands to a hook */
};

struct mod_options_data {
    u32 zone_at;                /* the save zone in the save data */
    u32 magic;                  /* what marks it written */
    u16 version;                /* the zone's */
    u16 help, row, marked;      /* the value list's texts: its description, a row, the row in use */
    struct mod_option options[MOD_OPTIONS];
};

struct mod_options_state {      /* mod_options_stub.s has the offsets */
    u8 values[16];              /* 0: each option's value this frame */
    u32 net_waits;              /* 16: the online waits (frames, polls) */
    u32 net_polls;              /* 20 */
    u32 fov_one;                /* 24: the camera's literal in the reset case with the flags "not equal", and the other */
    u32 fov_other;              /* 28: and in the case "equal" */
    u32 raw_base;               /* 32: the weapon classes' table the menus read */
    u32 saved[3];               /* 36: the game's words (SLOT_*) */
    u32 live;                   /* 48: bit n set while the option writes into slot n */
    u32 hide_face;              /* 52: the mod has the lock-on and it is off: no target face (hud/target_face.c) */
};

_Static_assert(__builtin_offsetof(struct mod_options_state, net_waits) == 16, "mod_options_stub.s NET_WAITS");
_Static_assert(__builtin_offsetof(struct mod_options_state, net_polls) == 20, "mod_options_stub.s NET_POLLS");
_Static_assert(__builtin_offsetof(struct mod_options_state, fov_one) == 24, "mod_options_stub.s FOV_ONE");
_Static_assert(__builtin_offsetof(struct mod_options_state, fov_other) == 28, "mod_options_stub.s FOV_OTHER");
_Static_assert(__builtin_offsetof(struct mod_options_state, raw_base) == 32, "mod_options_stub.s RAW_BASE");
_Static_assert(__builtin_offsetof(struct mod_options_state, hide_face) == 52, "hud/target_face.c HIDE_FACE");

extern const struct mod_options_data mod_options_data;
extern struct mod_options_state mod_options_state;
extern const u32 mod_raw_table[16];
extern const u32 class_multipliers[16];
extern u32 save_control, gx_main, game_main, camera_control;

/* The save zone of the character in play, 0 without a save */
static u8 *save_zone(void)
{
    return save_control != 0 ? (u8 *)save_control + SAVE_DATA + mod_options_data.zone_at : 0;
}

int mod_option_saved(void)
{
    return save_zone() != 0;
}

/* The value of an option: the character's choice, else the default */
static int value_of(int id)
{
    const struct mod_option *option = &mod_options_data.options[id];
    const u8 *zone = save_zone();

    if (option->count == 0)
        return 0;
    if (zone != 0 && *(const u32 *)zone == mod_options_data.magic) {
        int chosen = zone[option->byte];

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

int mod_option_name(int id, int value)
{
    return mod_options_data.options[id].names[value];
}

/* The value list's texts: 0 its description, 1 a row, 2 the row in use */
int mod_option_text(int which)
{
    return which == 0 ? mod_options_data.help : which == 1 ? mod_options_data.row : mod_options_data.marked;
}

/* The character's choice, used from the next frame. A new character's zone is zeros */
void mod_option_choose(int id, int value)
{
    u8 *zone = save_zone();
    int word;

    if (zone == 0)
        return;
    if (*(u32 *)zone != mod_options_data.magic) {
        for (word = 0; word < ZONE_WORDS; word++)
            ((u32 *)zone)[word] = 0;
        *(u32 *)zone = mod_options_data.magic;
        *(u16 *)(zone + ZONE_VERSION) = mod_options_data.version;
    }
    zone[mod_options_data.options[id].byte] = value + 1;
    mod_options_state.values[id] = value;
}

/* A word of one of the game's objects: written while the option is on, the game's own put back when it goes off */
static void write_word(u32 object, int offset, int active, u32 word, int slot)
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
        *at = mod_options_state.saved[slot];
        mod_options_state.live &= ~(1u << slot);
    }
}

static const u32 *payload_of(int id)
{
    return mod_options_data.options[id].payload[mod_options_state.values[id]];
}

/* FUN_00644320's caller, once per frame in every scene, before the engine's timing update */
void mod_frame(void)
{
    struct mod_options_state *state = &mod_options_state;
    int id;

    for (id = 0; id < MOD_OPTIONS; id++)
        state->values[id] = value_of(id);
    write_word(gx_main, DISPLAY_MODE, state->values[OPT_3D] != 0, payload_of(OPT_3D)[0], SLOT_3D);
    write_word(game_main, FRAME_RATE, state->values[OPT_FPS] != 0, payload_of(OPT_FPS)[0], SLOT_FPS);
    write_word(camera_control, FIELD_OF_VIEW, state->values[OPT_FOV] != 0, payload_of(OPT_FOV)[0], SLOT_FOV);
    state->fov_one = payload_of(OPT_FOV)[0];
    state->fov_other = payload_of(OPT_FOV)[1];
    state->net_waits = payload_of(OPT_NET)[0];
    state->net_polls = payload_of(OPT_NET)[1];
    state->raw_base = state->values[OPT_RAW] != 0 ? (u32)mod_raw_table : (u32)class_multipliers;
    state->hide_face = mod_options_data.options[OPT_LOCK].count != 0 && state->values[OPT_LOCK] == 0;
}
