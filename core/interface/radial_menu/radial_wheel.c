/* The item wheel in a quest (interface/radial_menu/radial_menu.py).
 *
 * Hold L; the C-stick pushed into one of 8 sectors uses that slot's item at once; while L is held the stick does not
 * move the camera. An item that cannot be used gives the error sound and nothing else. With the weapon drawn (any
 * weapon but Sword and Shield) the pick sheathes it and the item waits, used as soon as the weapon is away.
 *
 * Hook: FUN_00b1cdf0, the local hunter's input update, calls FUN_00b3d160(hunter) once per frame; that `bl` goes to the
 * stub (radial_stub.s), which calls radial_wheel(hunter) and then FUN_00b3d160 with the registers it was entered with.
 * Everything the wheel does to the game is a write in the hunter's two structures, `p` = *(hunter + 0xE30) (status,
 * input and commands) and `pw` = *(hunter + 0xA29C) (work):
 *   - open: the actions word p + 0x3CC has bit 0x800 (action 11, the item mode: L held past the game's threshold;
 *     FUN_00b28f54 sets it, FUN_00b27fc8 clears it in the busy states, both before this call). Bit 0x200 is set later
 *     in the frame by FUN_00b3cc64 and says nothing. The wheel is off when the saved on / off byte is 0: nothing below
 *     runs and the game sees L and the stick as it would without the wheel;
 *   - stick: the pad object's angle (u16 at +0x32E) and magnitude (u16 at +0x33A, 0 under the game's dead zone of 30),
 *     the values the game copies into p + 0x3C2 / 0x3C6 at the top of FUN_00b1cdf0. The sector is
 *     ((angle + 0x1000) >> 13) & 7, 0 right, counter-clockwise. While open p + 0x3C6 is set to 0, so the actions of
 *     FUN_00b3cc64 and the tail of FUN_00b1cdf0 see a stick at rest and the camera stays. The same while Edit Slots holds
 *     the stick (radial_stick_hold, radial_choices.h): with the START menu open the update still runs, the buttons
 *     cleared and both sticks copied, so the hunter walks and the camera would turn;
 *   - firing: a use needs the stick under `rearm` since the wheel opened or last fired (a stick already out does
 *     nothing until it comes back), then `dwell` consecutive frames in one sector at `fire` or more; the character's
 *     trigger says when it goes. Tilt: at once, once, and the wheel disarms. Flick: that sector is aimed and a clock of
 *     `flick_limit` starts; the item goes when the stick falls under `rearm` before the clock ends, and the push is
 *     cancelled if the clock ends first (nothing more until the stick is back at rest). Release: the same with no
 *     clock. L let go first cancels an aim. The sector gives a slot (radial_data.sector_to_slot) and the slot an item
 *     (the save zone);
 *   - using: the game's own route of the touch shortcuts: the gate of
 *     FUN_00b9dc6c plus the transition list's record (0x80, 0xF4) and the timer pw + 0x204, then pw + 0x592 = the
 *     pouch slot, command 0x4B (p + 0x3DC |= 0x800) and, on weapon type 1 (Sword and Shield), the second set's bit
 *     0x1D (p + 0x3E4 |= 0x20000000). pw + 0x584, the bar's slot, is never written. A refusal is the error sound
 *     (FUN_0031294c(sound control, 3)); the frame after a request, if the game did not start the use (pw + 0x589 bit
 *     0x20), is the same sound once. The request remembers `pw`, so another hunter's frame (the next quest) drops it;
 *   - sheathing: a pick with the weapon drawn passes the item's part of the gate (a real item, in the pouch, carried,
 *     FUN_00b3d55c) and queues the item. Each frame while the weapon is out commands 13 and 14 are raised (p + 0x3D4 |=
 *     0x6000), as the Y button does: every weapon's idle and walking lists start the sheathe on them, (0, 2) / (0, 3),
 *     (0, 0xA1) / (0, 0xA2) on the Switch Axe's sword. That action lowers the weapon's flag (p + 0x6F9) on its first step;
 *     the frame the whole gate passes (the list of the idle after the motion) the item goes through the route above;
 *   - the queue's end: the item is used; or its time runs out (FUN_00b0709c, the game's timer, against the curated limit
 *     in the game's time, so in seconds at any frame rate): the error sound; or, silently, the wheel is switched off, the
 *     work structure changes (the next quest), or the hunter starts an action that is not the route's: when the action
 *     or the previous action (p + 0x377, kept by FUN_00b1c6f0: the same action started again) changes, the new one must
 *     be the idle (0, 0), walking (group 1) or a sheathe. A dodge, an attack, a flinch or a fall are none of those, so the
 *     item never follows them. A new pick replaces the queued item and restarts its time;
 *   - Auto-Combine (radial_craft.c), when the character has it on: the pick of an item the hunter has none of and can
 *     combine from what he carries (the game's checks and room for the result and for Garbage) combines it once, with
 *     the weapon drawn or not, where the use would give the error sound; nothing is used afterwards. Each frame the
 *     wheel is open the slots that can be combined go to the picture (radial_mark_craftable, before radial_seen).
 *
 * The choices are in Mod Settings' save zone, radial_data.zone_at bytes into the save data (the data starts 0x5C into the
 * save object; curated mod_settings.json save_zone): byte 6 the position in its low half and the size in its high
 * half (each 0 no choice yet, else the value + 1: 1 centre, 2 right, 3 bottom left, the size's index + 1), byte 7 three
 * fields of 2 bits, each 0 no choice yet: bits 0-1 on (1) / off (2), bits 2-3 Auto-Combine (1 on, 2 off), bits 4-5 the
 * trigger + 1 (1 Tilt, 2 Flick, 3 Release), byte 8 unused (the three are the zone's header bytes Mod Settings does not
 * use), bytes 37-47 the eight slots, 11 bits each from the low bits up (0 no choice yet, SLOT_EMPTY emptied, else the
 * item's id; the options' half bytes in bytes 10-35 are never touched, nor the byte after the zone). A zone written
 * before the size has 0 in its high half: the default size; one written before Auto-Combine and the trigger has 0 in
 * their bits (byte 7 = 1 or 2): their defaults. They count only in a zone with the magic and the mod's version (an
 * older zone holds no choice: nothing is carried over from an older save); a choice never made is radial_data's
 * default. Each frame the wheel reads them once (choices_read) for itself and its picture (radial_seen; the picture
 * reads them again in radial_frame); the editor (radial_editor.c) reads and writes them through radial_choices and
 * radial_choose. The first write of a zone that is not the mod's (no magic, or an older version) makes it as Mod
 * Settings makes it (zeros, the magic, the version).
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, Thumb, linked with radial_wheel.ld where it places the
 * block); the game's functions and variables are named in blocks.py GAME_SYMBOLS. The
 * comparisons of floats are on their bits, so no VFP register is used.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef int s32;

#define GAME __attribute__((long_call))
#define ARM __attribute__((target("arm"), noinline))

#include "radial_choices.h"
#include "radial_craft.h"

struct radial_data {            /* the curated numbers (radial_menu.py wheel_data) */
    u32 fire;                   /* the magnitude that counts as chosen */
    u32 rearm;                  /* the magnitude the stick must be under to arm again */
    u32 dwell;                  /* frames in one sector before a fire */
    u32 zone_at;                /* the zone's offset in the save data */
    u32 magic;
    u8 version;
    u8 position;                /* 0 centre, 1 right, 2 bottom left */
    u8 enabled;                 /* the default of a new character */
    u8 size;                    /* the default size: an index of the curated draw_sizes */
    u8 sector_to_slot[8];
    u16 items[8];               /* the default items */
    u32 queue_limit;            /* a float: the queue's limit in the game's time; it is copied, never computed */
    u8 sizes;                   /* how many sizes there are (1 to MAX_SIZES) */
    u8 trigger;                 /* the default trigger: 0 Tilt, 1 Flick, 2 Release */
    u8 autocraft;               /* the default of Auto-Combine */
    u8 pad;
    u32 flick_limit;            /* a float: a flick's window in the game's time; copied, never computed */
};


struct state {                  /* radial_state */
    u32 pending;                /* the pw of a request whose result is awaited, or 0 */
    u8 armed;                   /* the stick has been under `rearm` since the wheel opened or fired */
    u8 was_open;
    u8 dwell;                   /* frames the stick has held `held` */
    u8 held;                    /* that sector, or 0xFF */
    u32 queued;                 /* the pw an item waits for its sheathe in, or 0 */
    u32 queue_left;             /* a float: its time left, counted down by FUN_00b0709c */
    u32 seen_action;            /* the action and the previous action last seen (group << 16 | action) */
    u32 seen_before;
    u16 queued_item;
    u8 aim;                     /* AIM_NONE, AIM_AIMED (a push waits for the stick's return) or AIM_SPENT (cancelled) */
    u8 aimed;                   /* the aimed sector */
    u32 aim_left;               /* a float: the flick's time left, counted down by FUN_00b0709c */
};

struct debug {                  /* radial_debug, read from a save state (tools/inspect/citra_state.py) */
    u16 angle;
    u16 magnitude;
    u8 sector;
    u8 open;
    u16 pad;
    u32 fires;
    u32 refusals;
    u16 item;                   /* the last item asked for */
    u16 slot;                   /* its pouch slot, or 0xFFFF */
    u32 calls;
    u32 queue_picks;            /* picks that queued an item */
    u32 queue_used;             /* queued items sent to the use route */
    u32 queue_dropped;          /* queues ended by another action */
    u32 queue_expired;          /* queues that reached the limit */
    u32 last_drop;              /* the action that made the last drop (group << 16 | action) */
    u32 aims;                   /* pushes aimed by a flick or a release */
    u32 cancels;                /* flicks that ran past their window */
    u32 crafts;                 /* picks Auto-Combine combined */
    u32 craft_failures;         /* those whose roll failed (Garbage) */
    u8 craft_mask;              /* the craft mask of the last frame (bit k: slot k) */
    u8 pad2[3];
};

_Static_assert(sizeof(struct radial_data) == 0x3C, "blocks.py RADIAL_DATA_SIZE, radial_menu.py wheel_data");
_Static_assert(sizeof(struct state) == 32, "blocks.py radial_state");
_Static_assert(sizeof(struct debug) == 64, "blocks.py radial_debug");

extern const struct radial_data radial_data;
extern struct state radial_state;
extern struct debug radial_debug;
extern u32 pad_control;         /* the variables holding the pad object, the save object, the sound manager and the */
extern u32 save_control;        /* item manager */
extern u32 sound_control;
extern u32 item_control;

GAME u32 item_slot(u32 hunter, u32 item);                               /* FUN_00b1093c: the pouch slot or 0xFFFF */
GAME s32 pouch_count(u32 control, u32 hunter, u32 item, u32 flag);       /* FUN_005e588c */
GAME s32 weapon_drawn(u32 hunter);                                      /* FUN_00b08520 */
GAME s32 item_usable(u32 hunter, u32 item);                             /* FUN_00b3d55c */
GAME s32 list_has(u32 hunter, u32 group, u32 action);                   /* FUN_00b2adfc */
GAME s32 use_ready(u32 hunter);                                         /* FUN_00b08f94 */
GAME void sound_play(u32 manager, u32 sound);                           /* FUN_0031294c */
GAME u32 timer_step(u32 hunter, u32 *timer);                            /* FUN_00b0709c: 1 when the timer runs out */

#define B(base, off) (*(u8 *)((base) + (off)))
#define H(base, off) (*(u16 *)((base) + (off)))
#define W(base, off) (*(u32 *)((base) + (off)))

#define PLAYER_STATUS 0xE30             /* hunter -> p */
#define PLAYER_WORK 0xA29C              /* hunter -> pw */
#define P_WEAPON 0x31                   /* weapon type; 1 is Sword and Shield */
#define P_GROUP 0x371                   /* action group and action (u16) */
#define P_ACTION 0x372
#define P_GROUP_BEFORE 0x377            /* the previous action, kept by FUN_00b1c6f0 */
#define P_ACTION_BEFORE 0x378
#define P_STICK 0x3C6                   /* the stick's magnitude copy (u16) */
#define P_ACTIONS 0x3CC
#define P_SHEATHE 0x3D4                 /* the commands' first word: commands 13 and 14 are its bits 13 and 14 */
#define P_COMMANDS 0x3DC                /* the commands' third word: command 0x4B is its bit 11 */
#define P_SECOND_SET 0x3E4              /* the second command set's first word: 0x1D is its bit 29 */
#define PW_TIMER 0x204                  /* float; item use is refused while above 0 */
#define PW_STARTED 0x589                /* bit 0x20: an item use has started */
#define PW_SLOT 0x592                   /* the shortcut's slot (u16) */
#define PW_FORBID 0x594                 /* 1 forbids items */
#define PAD_ANGLE 0x32E
#define PAD_MAGNITUDE 0x33A
#define SAVE_DATA 0x5C                  /* the save data's start in the save object */

#define ITEM_MODE 0x800u
#define USE_COMMAND 0x800u
#define USE_SECOND_SET 0x20000000u
#define SHEATHE_COMMANDS 0x6000u
#define GROUP_BASIC 0                   /* the group of the idle and the sheathe actions */
#define GROUP_WALK 1                    /* the hunter walking or running */
#define SWORD_AND_SHIELD 1
#define STARTED 0x20
#define POUCH_SLOTS 0x2E
#define NO_SLOT 0xFFFFu
#define LIST_GROUP 0x80                 /* the transition list's use record: (0x80, 0xF4) */
#define LIST_ACTION 0xF4
#define DUNG_BOMB 0x41
#define SOUND_ERROR 3
#define NO_SECTOR 0xFF
#define ZONE_WORDS 12                   /* Mod Settings' zone: 48 bytes */
#define ZONE_VERSION 4                  /* its u16 */
#define ZONE_POSITION 6                 /* the wheel's bytes: the position's half and the size's (HALF bits each) */
#define HALF 4
#define HALF_MASK 0xFu
#define ZONE_FLAGS 7                    /* three fields of FIELD_BITS: on / off, Auto-Combine and the trigger */
#define FIELD_BITS 2
#define FIELD_MASK 3u
#define FIELD_ENABLED 0                 /* a field's first bit */
#define FIELD_AUTOCRAFT 2
#define FIELD_TRIGGER 4
#define TRIGGER_TILT 0
#define TRIGGER_FLICK 1
#define AIM_NONE 0
#define AIM_AIMED 1
#define AIM_SPENT 2
#define ZONE_SLOTS 37                   /* the slots' bytes, 37-47; the header's are 6-8 (8 unused) */
#define SLOT_BITS 11
#define SLOT_EMPTY 0x7FFu

static void error_sound(void)
{
    radial_debug.refusals++;
    sound_play(sound_control, SOUND_ERROR);
}

/* The zone in the save data, or 0 without a save object */
static u32 zone_address(void)
{
    u32 save = save_control;
    return save ? save + SAVE_DATA + radial_data.zone_at : 0;
}

/* The zone holds the mod's choices, the wheel's among them: the magic and the mod's version */
static int zone_has_wheel(u32 zone)
{
    return W(zone, 0) == radial_data.magic && H(zone, ZONE_VERSION) == radial_data.version;
}

/* A slot's bytes of the packed slots: the first and last byte its SLOT_BITS bits are in (never one past them) */
static u32 slot_first(u32 slot)
{
    return SLOT_BITS * slot >> 3;
}

static u32 slot_last(u32 slot)
{
    return (SLOT_BITS * slot + SLOT_BITS - 1) >> 3;
}

static u32 slot_code(u32 zone, u32 slot)
{
    u32 value = 0;
    for (u32 at = slot_last(slot) + 1; at-- > slot_first(slot);)
        value = value << 8 | B(zone, ZONE_SLOTS + at);
    return value >> (SLOT_BITS * slot & 7) & SLOT_EMPTY;
}

static void slot_store(u32 zone, u32 slot, u32 code)
{
    u32 value = 0, shift = SLOT_BITS * slot & 7;
    for (u32 at = slot_last(slot) + 1; at-- > slot_first(slot);)
        value = value << 8 | B(zone, ZONE_SLOTS + at);
    value = (value & ~(SLOT_EMPTY << shift)) | (code & SLOT_EMPTY) << shift;
    for (u32 at = slot_first(slot); at <= slot_last(slot); at++, value >>= 8)
        B(zone, ZONE_SLOTS + at) = value & 0xFF;
}

/* The character's choices, the defaults where none was made; 0 without a save object */
static int choices_read(struct choices *out)
{
    u32 zone = zone_address();
    if (!zone)
        return 0;
    int saved = zone_has_wheel(zone);
    u32 placing = saved ? B(zone, ZONE_POSITION) : 0, flags = saved ? B(zone, ZONE_FLAGS) : 0;
    u32 position = placing & HALF_MASK, size = placing >> HALF;
    u32 enabled = flags >> FIELD_ENABLED & FIELD_MASK, autocraft = flags >> FIELD_AUTOCRAFT & FIELD_MASK;
    u32 trigger = flags >> FIELD_TRIGGER & FIELD_MASK;
    out->position = position && position <= POSITIONS ? position - 1 : radial_data.position;
    out->size = size && size <= radial_data.sizes ? size - 1 : radial_data.size;
    out->enabled = enabled ? enabled == 1 : radial_data.enabled;
    out->autocraft = autocraft ? autocraft == 1 : radial_data.autocraft;
    out->trigger = trigger && trigger <= TRIGGERS ? trigger - 1 : radial_data.trigger;
    for (u32 slot = 0; slot < WHEEL_SLOTS; slot++) {
        u32 code = saved ? slot_code(zone, slot) : 0;
        out->slots[slot] = code == 0 ? radial_data.items[slot] : code == SLOT_EMPTY ? 0 : code;
    }
    out->pad = 0;
    return 1;
}

/* The zone ready for a choice: one that is not the mod's (no magic, or an older version) made as Mod Settings makes it
 * (zeros, the magic, the version) */
static u32 zone_for_write(void)
{
    u32 zone = zone_address();
    if (!zone)
        return 0;
    if (!zone_has_wheel(zone)) {
        for (u32 i = 0; i < ZONE_WORDS; i++)
            W(zone, 4 * i) = 0;
        W(zone, 0) = radial_data.magic;
        H(zone, ZONE_VERSION) = radial_data.version;
    }
    return zone;
}

/* For the editor (radial_editor.c), an ARM block's calls: the choices as the wheel reads them (0 without a save) */
ARM int radial_choices(struct choices *out)
{
    return choices_read(out);
}

/* One of the flags byte's (7) fields of FIELD_BITS (`code` 0 no choice yet, else the value + 1) */
static void field_store(u32 zone, u32 shift, u32 code)
{
    B(zone, ZONE_FLAGS) = (B(zone, ZONE_FLAGS) & ~(FIELD_MASK << shift)) | code << shift;
}

/* A choice: `which` 0-7 a slot (`value` the item, 0 empties it), CHOOSE_POSITION (0 centre, 1 right, 2 bottom left; past
 * the last, the default), CHOOSE_SIZE (an index of the sizes; past the last, the default), CHOOSE_ENABLED (0 off, 1 on),
 * CHOOSE_AUTOCRAFT (0 off, 1 on), CHOOSE_TRIGGER (0 Tilt, 1 Flick, 2 Release; past the last, the default). Nothing
 * without a save object */
ARM void radial_choose(u32 which, u32 value)
{
    u32 zone = zone_for_write();
    if (!zone)
        return;
    if (which < WHEEL_SLOTS)
        slot_store(zone, which, value ? value : SLOT_EMPTY);
    else if (which == CHOOSE_POSITION)
        B(zone, ZONE_POSITION) = (B(zone, ZONE_POSITION) & ~HALF_MASK) |
                                 ((value < POSITIONS ? value : radial_data.position) + 1);
    else if (which == CHOOSE_SIZE)
        B(zone, ZONE_POSITION) = (B(zone, ZONE_POSITION) & HALF_MASK) |
                                 ((value < radial_data.sizes ? value : radial_data.size) + 1) << HALF;
    else if (which == CHOOSE_ENABLED)
        field_store(zone, FIELD_ENABLED, value ? 1 : 2);
    else if (which == CHOOSE_AUTOCRAFT)
        field_store(zone, FIELD_AUTOCRAFT, value ? 1 : 2);
    else if (which == CHOOSE_TRIGGER)
        field_store(zone, FIELD_TRIGGER, (value < TRIGGERS ? value : radial_data.trigger) + 1);
}

/* The state the wheel has while closed: nothing armed or counted. */
static void at_rest(void)
{
    radial_state.was_open = 0;
    radial_state.armed = 0;
    radial_state.dwell = 0;
    radial_state.held = NO_SECTOR;
    radial_state.aim = AIM_NONE;
    radial_debug.open = 0;
}

/* The frame after a request: the error sound if the game did not start the use. A different hunter's work structure
 * (another quest) drops it unheard, and so does a wheel that is off. */
static void check_pending(u32 pw, const struct choices *choices)
{
    u32 waiting = radial_state.pending;
    radial_state.pending = 0;
    if (waiting != pw || (B(pw, PW_STARTED) & STARTED))
        return;
    if (choices && !choices->enabled)
        return;
    error_sound();
}

/* The part of the gate that does not depend on the weapon: a real item, in the pouch, carried, usable in this state. */
static int item_ready(u32 hunter, u32 item, u32 *slot)
{
    if (item == 0 || item == 0x790 || item == 0x791)
        return 0;
    *slot = item_slot(hunter, item) & 0xFFFF;
    if (*slot >= POUCH_SLOTS)
        return 0;
    if (pouch_count(item_control, hunter, item, 1) <= 0)
        return 0;
    return item_usable(hunter, item);
}

/* The recipe's gate: the touch panels' (FUN_00b9dc6c) plus the list's record and the timer. The panels' test of the
 * weapon is the caller's: only Sword and Shield comes here with the weapon drawn. */
static int can_start(u32 hunter, u32 p, u32 pw, u32 item, u32 *slot)
{
    if (!item_ready(hunter, item, slot))
        return 0;
    if (!list_has(hunter, LIST_GROUP, LIST_ACTION))
        return 0;
    u32 action = H(p, P_ACTION);
    int dung = item == DUNG_BOMB && B(p, P_GROUP) == 7 && action > 1 && action != 7 && action != 8;
    if (!use_ready(hunter) && !dung)
        return 0;
    if (B(pw, PW_FORBID) == 1)
        return 0;
    if ((s32)W(pw, PW_TIMER) > 0)
        return 0;
    return 1;
}

/* The game's use route: the shortcut's slot and command, and a request whose result the next frame checks. */
static void use_item(u32 p, u32 pw, u32 slot)
{
    H(pw, PW_SLOT) = slot;
    W(p, P_COMMANDS) |= USE_COMMAND;
    if (B(p, P_WEAPON) == SWORD_AND_SHIELD)
        W(p, P_SECOND_SET) |= USE_SECOND_SET;
    radial_state.pending = pw;
}

static u32 action_now(u32 p)
{
    return ((u32)B(p, P_GROUP) << 16) | H(p, P_ACTION);
}

static u32 action_before(u32 p)
{
    return ((u32)B(p, P_GROUP_BEFORE) << 16) | H(p, P_ACTION_BEFORE);
}

/* The actions the route to the item goes through: the idle and walking, weapon out or away, and the sheathe itself. */
static int on_the_route(u32 action)
{
    if ((action >> 16) == GROUP_WALK)
        return 1;
    if ((action >> 16) != GROUP_BASIC)
        return 0;
    action &= 0xFFFF;
    return action == 0 || action == 2 || action == 3 || action == 0xA1 || action == 0xA2;
}

/* Each frame with an item queued, L held or not. */
static void queue_frame(u32 hunter, u32 p, u32 pw, const struct choices *choices)
{
    u32 owner = radial_state.queued;
    if (!owner)
        return;
    if (owner != pw || (choices && !choices->enabled)) {
        radial_state.queued = 0;
        return;
    }
    u32 action = action_now(p), before = action_before(p);
    if (action != radial_state.seen_action || before != radial_state.seen_before) {
        radial_state.seen_action = action;
        radial_state.seen_before = before;
        if (!on_the_route(action)) {
            radial_state.queued = 0;
            radial_debug.queue_dropped++;
            radial_debug.last_drop = action;
            return;
        }
    }
    if (timer_step(hunter, &radial_state.queue_left)) {
        radial_state.queued = 0;
        radial_debug.queue_expired++;
        error_sound();
        return;
    }
    if (weapon_drawn(hunter)) {
        W(p, P_SHEATHE) |= SHEATHE_COMMANDS;
        return;
    }
    u32 slot;
    if (!can_start(hunter, p, pw, radial_state.queued_item, &slot))
        return;
    radial_state.queued = 0;
    radial_debug.queue_used++;
    radial_debug.slot = slot;
    use_item(p, pw, slot);
}

/* A pick that goes through the sheathe: it starts now, and queue_frame takes it from the next frame. */
static void queue_item(u32 p, u32 pw, u32 item)
{
    radial_state.queued = pw;
    radial_state.queued_item = item;
    radial_state.queue_left = radial_data.queue_limit;
    radial_state.seen_action = action_now(p);
    radial_state.seen_before = action_before(p);
    radial_debug.queue_picks++;
    W(p, P_SHEATHE) |= SHEATHE_COMMANDS;
}

/* Auto-Combine's pick (radial_craft.c): an item with none left that can be combined is combined once, weapon drawn or
 * not, in place of the use's refusal; like any pick it replaces a queued item. 0 when it is not craftable. */
static int craft(u32 hunter, u32 item, const struct choices *choices)
{
    if (!choices || !choices->autocraft)
        return 0;
    u32 done = radial_craft(hunter, item);
    if (done == CRAFT_NONE)
        return 0;
    radial_state.queued = 0;
    radial_debug.slot = NO_SLOT;
    radial_debug.crafts++;
    if (done == CRAFT_FAILED)
        radial_debug.craft_failures++;
    return 1;
}

static void fire(u32 hunter, u32 p, u32 pw, u32 sector, const struct choices *choices)
{
    u32 item = 0, slot = NO_SLOT;
    radial_debug.fires++;
    if (choices)
        item = choices->slots[radial_data.sector_to_slot[sector & 7] & 7];
    radial_debug.item = item;
    if (craft(hunter, item, choices))
        return;
    /* While an item waits the route is under way, weapon out or not: this pick takes its place */
    int sheathe = radial_state.queued || (B(p, P_WEAPON) != SWORD_AND_SHIELD && weapon_drawn(hunter));
    radial_state.queued = 0;
    int ready = choices && (sheathe ? item_ready(hunter, item, &slot) : can_start(hunter, p, pw, item, &slot));
    radial_debug.slot = slot;
    if (!ready) {
        error_sound();
        return;
    }
    if (sheathe)
        queue_item(p, pw, item);
    else
        use_item(p, pw, slot);
}

__attribute__((noinline)) static void wheel_frame(u32 hunter, const struct choices *choices)
{
    u32 p = W(hunter, PLAYER_STATUS), pw = W(hunter, PLAYER_WORK);
    radial_debug.calls++;
    if (!p || !pw)
        return;
    check_pending(pw, choices);
    queue_frame(hunter, p, pw, choices);
    if (radial_stick_hold != 0) {       /* Edit Slots points with the C-stick: the camera stays, on or off */
        radial_stick_hold--;
        H(p, P_STICK) = 0;
    }
    if (!(W(p, P_ACTIONS) & ITEM_MODE)) {
        at_rest();
        return;
    }
    if (choices && !choices->enabled) {
        at_rest();
        return;
    }
    if (!radial_state.was_open) {
        radial_state.was_open = 1;
        radial_state.armed = 0;
        radial_state.dwell = 0;
        radial_state.held = NO_SECTOR;
        radial_state.aim = AIM_NONE;
    }
    u32 pad = pad_control;
    u32 angle = pad ? H(pad, PAD_ANGLE) : 0, magnitude = pad ? H(pad, PAD_MAGNITUDE) : 0;
    u32 sector = ((angle + 0x1000) >> 13) & 7;
    radial_debug.angle = angle;
    radial_debug.magnitude = magnitude;
    radial_debug.sector = sector;
    radial_debug.open = 1;
    H(p, P_STICK) = 0;
    u32 trigger = choices ? choices->trigger : TRIGGER_TILT;
    if (trigger == TRIGGER_TILT)
        radial_state.aim = AIM_NONE;
    if (radial_state.aim == AIM_AIMED && trigger == TRIGGER_FLICK && timer_step(hunter, &radial_state.aim_left)) {
        radial_state.aim = AIM_SPENT;
        radial_debug.cancels++;
    }
    if (magnitude < radial_data.rearm) {
        u32 aimed = radial_state.aim == AIM_AIMED ? radial_state.aimed : NO_SECTOR;
        radial_state.armed = 1;
        radial_state.dwell = 0;
        radial_state.held = NO_SECTOR;
        radial_state.aim = AIM_NONE;
        if (aimed != NO_SECTOR)
            fire(hunter, p, pw, aimed, choices);
        return;
    }
    if (!radial_state.armed || magnitude < radial_data.fire) {
        radial_state.dwell = 0;
        radial_state.held = NO_SECTOR;
        return;
    }
    if (radial_state.held != sector) {
        radial_state.held = sector;
        radial_state.dwell = 0;
    }
    if (++radial_state.dwell < radial_data.dwell)
        return;
    radial_state.armed = 0;
    radial_state.dwell = 0;
    radial_state.held = NO_SECTOR;
    if (trigger == TRIGGER_TILT) {
        fire(hunter, p, pw, sector, choices);
        return;
    }
    radial_state.aim = AIM_AIMED;
    radial_state.aimed = sector;
    radial_state.aim_left = radial_data.flick_limit;
    radial_debug.aims++;
}

/* radial_draw.c: what the picture needs from the input update (the hunter, the wheel open); it draws from the quest's
   frame hook (radial_frame) */
void radial_seen(u32 hunter, const struct choices *choices);
void radial_mark_craftable(u32 mask);

/* The slots Auto-Combine would combine now (bit k: slot k), worked out only while the wheel is open and Auto-Combine
 * on; 0 otherwise */
static u32 craft_mask(u32 hunter, const struct choices *choices)
{
    u32 p = W(hunter, PLAYER_STATUS);
    if (!choices || !choices->enabled || !choices->autocraft || !p || !(W(p, P_ACTIONS) & ITEM_MODE))
        return 0;
    return radial_craftable(hunter, choices);
}

__attribute__((used, section(".text.entry"))) ARM void radial_wheel(u32 hunter)
{
    struct choices choices;
    const struct choices *read = choices_read(&choices) ? &choices : 0;
    wheel_frame(hunter, read);
    u32 mask = craft_mask(hunter, read);
    radial_debug.craft_mask = mask;
    radial_mark_craftable(mask);
    radial_seen(hunter, read);
}
