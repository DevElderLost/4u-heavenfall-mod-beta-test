/* The C-stick turns the camera analogically (option modern_camera; gameplay/modern_camera/modern_camera.py).
 *
 * The game turns the camera by four buttons: FUN_00b3cc64 (the hunter's camera buttons) gives the D-pad's and the
 * C-stick's directions as the actions 2 / 4 (up / down) and 6 / 8 (left / right), and FUN_00bfd028
 * (sMhCamera::turnByInput) turns the camera's input angles by them, one axis a frame, speeding up while a button is
 * held. The two entries make the C-stick a stick again:
 *
 *   modern_camera_stick(hunter, stick)   instead of FUN_00b3cc64's call of the hunter's vtable + 0x98 ("is the
 *       C-stick tilted"; through the START menu's gate gate_modern_stick, which makes the game's call while the option
 *       is off). It answers what the vtable's function answers, so FUN_00b3cc64 sets the C-stick's camera buttons as
 *       the game does. When the game takes the C-stick for the camera (it answers for the stick pushed all the way;
 *       FUN_00b41e44 does not while a gunner looks through the scope), it also keeps the stick's direction and length
 *       and the camera buttons set before it (the D-pad's up and down), for the cameras of this frame. FUN_00b3cc64
 *       reaches that call only when the hunter takes input and the D-pad does not turn the camera left or right, so
 *       the camera gets the stick exactly when the game would have turned it by the stick.
 *   modern_camera_turn(camera, input, flags)   instead of the three calls of FUN_00bfd028 (FUN_00c009ac, the quest
 *       camera; FUN_00bfe11c and FUN_00c01608, the special cameras; through gate_modern_turn). It makes that call with
 *       the C-stick's camera buttons hidden while a kept stick is fresh (the D-pad keeps the game's turn, the stick
 *       does not turn the camera twice; the buttons are back for everything after the call), then turns the input's
 *       yaw and pitch by the stick kept for that camera's hunter:
 *       a dead zone, a response curve, a top speed per axis (the game's slower pairs of an input's mode, Camera Turn
 *       Speed's factor), speeding up and slowing down toward it with the frame's time, the game's pitch limit and the
 *       game's invert settings (`flags`). With `direct` the quest camera's rig turns as its input did, so the turn
 *       shows in the same frame instead of being eased in a second time by the game.
 *
 * Each camera input (the quest camera's, the special cameras') has its own speeds: FUN_00c06e54 can turn both in one
 * frame. A kept stick is used once per input. State in modern_camera_state (the extension's variables: written each
 * frame, so never in the block); tuning in modern_camera_data (curated modern_camera.json).
 *
 * The aims are not the camera's: FUN_00b2041c (the hunter's aim) turns the aim's yaw and pitch by digital commands, one
 * fixed step a frame. Three more entries, inside FUN_00b2041c (`frame` its stack), make the C-stick turn them
 * analogically with the camera's dead zone and each aim's own curve, smoothing and top speeds:
 *
 *   aim_commands_hook   its `ldr r0, [r2, #0x3e4]`, the commands over the shoulder (bowguns, mode 0) and the Bow's
 *       (mode 3): modern_aim_commands takes out the bit the C-stick set (FUN_00ca51c0's or FUN_00cb4140's sectors),
 *       not the D-pad's or the circle pad's, and turns the aim by the stick.
 *   aim_scope_hook   its `tst r0, #0x3c`, the scope's C-stick bits: modern_aim_scope hides them (the test sees none)
 *       and turns the aim by the stick, slower with the scope's zoom as the game's steps are.
 * The first two leave another console's hunter (FUN_00d04fbc) to the game.
 *   modern_aim_view   its calls of FUN_00b1ea04 (modes 0 and 3: the pitch's angle the aim shows): the game's call,
 *       then the angle from the whole pitch, not its integer part, so a slow turn does not show in steps.
 *
 * The yaw goes into FUN_00b2041c's own yaw (stored only when its `turn` is set), the pitch into the weapon's work
 * within FUN_00b1e684's limit; the game's Aim Speed and invert options and the aim's "moving" mark apply as for the
 * game's commands. The speeds start again from rest when the aim was not turned in the last frame (mod_options_state's
 * frame count).
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with modern_camera.ld where it places the block);
 * the game functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef short s16;

/* The hunter and its input object */
#define HUNTER_INPUT      0xE30     /* the hunter: its input object */
#define HUNTER_STICK      0x98      /* the hunter's vtable: (hunter, stick) "is the stick tilted" (FUN_00b41e44) */
#define STICK_ANGLES      0x3C0     /* the input object: each stick's direction (u16, 0x10000 a turn), 1 the C-stick */
#define STICK_LENGTHS     0x3C4     /* each stick's length, 0 to 127 (0 inside the pad's own dead zone) */
#define STICK_ALL_THE_WAY 127
#define STICK_FULL        127.0f
#define INPUT_ACTIONS     0x3CC     /* the hunter's actions: bit n is FUN_00b0d768(hunter, n) */
#define TURN_ACTIONS      0x1FE     /* bits 1 to 8: the camera buttons' presses and holds (up 1, 2; down 3, 4; left 5,
                                       6; right 7, 8), the D-pad's and the C-stick's */

/* sMhCamera */
#define CAMERA_HUNTER     0xE18     /* the hunter it follows */
#define CAMERA_FRAME      0xE2C     /* float: the frame's time, 1.0 for 1/60 s */
#define CAMERA_RIG        0xE40     /* the quest camera's rig */
#define CAMERA_MAIN       0xE80     /* the quest camera's input (FUN_00c009ac) */
#define CAMERA_FORCED     0xF44     /* u8: the quest camera's rig follows other angles and its input is overwritten */

/* An input of FUN_00bfd028 */
#define INPUT_PITCH       0x08      /* u32: a u16 angle, within +-PITCH_LIMIT */
#define INPUT_YAW         0x0C      /* u32: a u16 angle */
#define INPUT_MODE        0x10      /* u8: bit 0, bit 1: the turn's slower pairs of speeds */
#define INPUT_TURNED      0x11      /* u8: bit 0 the pitch, bit 1 the yaw turned by a button this frame */
#define TURNED_PITCH      1
#define TURNED_YAW        2

/* The rig's angles, eased toward the input's by FUN_00c009ac */
#define RIG_PITCH         0x80
#define RIG_YAW           0x84
#define RIG_PITCH_COPY    0x88
#define RIG_YAW_COPY      0x8C

#define PITCH_LIMIT       0x3F00    /* FUN_00bfd028's limit, both ways */
#define INVERT_PITCH      1         /* `flags` (the game's camera options) */
#define INVERT_YAW        2
#define TURN_NONE         0xFF      /* FUN_00bfd028's result: no button, the pitch turned, the yaw turned */
#define TURN_PITCH        0
#define TURN_YAW          1
#define SLOTS             2         /* the quest camera's input, the special cameras' */

/* The aim: FUN_00b2041c(hunter, motion, mode, turn) and the hunter's weapon */
#define AIM_YAW           0x18      /* FUN_00b2041c's stack: the aim's yaw (word), stored into the work's when `turn` */
#define AIM_MODE          0x5C      /* its arguments on its stack: mode (0 the bowguns, 3 the Bow), turn */
#define AIM_TURN          0x60
#define MODE_BOW          3
#define HUNTER_TIME       0x14      /* float: the hunter's frame time, 1.0 for 1/60 s */
#define HUNTER_WEAPON     0xA29C    /* the hunter: its weapon's work */
#define WORK_MOVED        0x50C     /* u8: not 0 while the aim moves (FUN_00b2041c: 5 by its pitch, 10 by its yaw) */
#define WORK_PITCH        0xDC      /* float: the aim's pitch, within +-AIM_PITCH_LIMIT */
#define WORK_PITCH_COPY   0xE0      /* float: its copy (FUN_00b1e684), the over-the-shoulder camera's */
#define WORK_PITCH_ANGLE  0x50E     /* s16: the pitch's angle (FUN_00b1ea04), the aim's view */
#define AIM_PITCH_LIMIT   100.0f    /* FUN_00b1e684 */
#define MOVED_PITCH       5
#define MOVED_YAW         10
#define INPUT_HELD        0x3A0     /* the input object: buttons held (D-pad 0x2000 up, 0x1000 down, 0x800 left, 0x400
                                       right) */
#define INPUT_FLAGS       0x3D4     /* bit 28: the hunter aims (FUN_00b248a4(hunter, 0x1C)) */
#define AIMING            (1u << 28)
#define C_STICK           1
#define DPAD_COMMANDS     12        /* the bowguns' commands: bits 12-15 the D-pad's (and the circle pad's FUN_00b24634
                                       turns), set with bits 0-3 */
#define GUNNER_BOWGUN     0         /* FUN_00d04dd4's kinds: the bowguns (weapon classes 4, 5, 6, 0xF), the Bow (10) */
#define GUNNER_BOW        2
#define MOD_FRAME         63        /* mod_options_state: the frame count (mod_options.c) */
#define SETTINGS_BYTES    100       /* sGameControl: + 100 + n the settings byte n */
#define PERCENT           0.01f     /* FUN_00b1ea04: the pitch's hundredths of its span, a turn's units, a degree */
#define TURN_UNITS        65536.0f
#define PER_DEGREE        (1.0f / 360.0f)

enum aim { AIM_SHOULDER, AIM_SCOPE, AIM_BOW, AIMS };

struct modern_camera_data {         /* modern_camera.py data_block */
    float dead_zone;                /* the stick's length (0 to 1) under which it does nothing */
    float full_tilt;                /* the length that counts as pushed all the way */
    float expo;                     /* the camera's curve: (1 - expo) t + expo t^3 of the tilt t past the dead zone */
    float yaw_speed;                /* the top speeds at full tilt, angle units per 1/60 s */
    float pitch_speed;
    float speed_up;                 /* the camera's time constants, in 1/60 s: toward a faster turn */
    float slow_down;                /* toward a slower one, a stop or the other way */
    float stop_speed;               /* with the stick released, a turn slower than this stops */
    float longest_frame;            /* the frame's time taken at most, in 1/60 s */
    u32 direct;                     /* the quest camera's rig turns too */
    u32 speed_option;               /* the option numbers of Max Speed and Acceleration (mod_options.py OPTION_IDS): */
    u32 accel_option;               /* the first payload word of the value in use is a float, the factor */
    struct {
        float yaw;                  /* the aim's top speeds at full tilt, the game's middle Aim Speed and the scope's */
        float pitch;                /* widest view: angle units and pitch steps (WORK_PITCH) per 1/60 s */
        float pitch_stop;           /* stop_speed's turn in the aim's pitch steps per 1/60 s */
        float expo;                 /* the aim's response curve and time constants, as the camera's */
        float speed_up;
        float slow_down;
    } aims[AIMS];
};

struct turn {
    float yaw, pitch;               /* the speeds, angle units per 1/60 s */
    float rest_yaw, rest_pitch;     /* the part of a unit not turned yet */
};

struct modern_camera_state {
    u32 hunter;                     /* the hunter whose C-stick was kept */
    u16 angle;                      /* its direction and length */
    u16 length;
    u32 fresh;                      /* bit n: slot n has not used it yet */
    u32 held;                       /* the camera buttons set before the C-stick's (TURN_ACTIONS: the D-pad's) */
    struct turn turns[SLOTS];
    u32 aim_hunter;                 /* the hunter whose aim turns, its kind (enum aim) and the frame it last turned */
    u8 aim_kind;
    u8 aim_frame;
    u16 spare;
    struct turn aim;                /* the aim's speeds (pitch steps for the pitch) */
};

/* Each aim's rules from the game: FUN_00b3fe50's kind (the Aim Speed option's factor) and its middle factor, the
   game's settings byte of the aim's invert option, the first of the four commands (up, down, left, right) FUN_00b2041c
   reads */
static const struct {
    u8 speed_kind, invert, first;
    float normal;
} AIM_RULES[AIMS] = {
    {1, 0xB, 0, 1.4f},              /* over the shoulder: commands 0-3 */
    {0, 9, 0, 1.0f},                /* the scope (reads the stick's bits itself) */
    {2, 0xB, 7, 0.5f},              /* the Bow: commands 7-10 */
};

/* The scope's speed for the C-stick (the first row of the game's table at 0x100C51C): from the zoomed-in end to the
   widest view (FUN_00c00038's zoom, 0 to 1) */
static const float SCOPE_PITCH_STEPS[2] = {2.0f, 6.0f};
static const float SCOPE_YAW_STEPS[2] = {128.0f, 512.0f};

/* The C-stick's sectors of FUN_00ca51c0 and FUN_00cb4140 (FUN_00b25200: from, to): up, down, left, right */
static const u16 SECTORS[4][2] = {{0x2AAB, 0x5555}, {0xAAAB, 0xD555}, {0x5555, 0xAAAB}, {0xD555, 0x2AAB}};

_Static_assert(sizeof(struct modern_camera_data) == DATA_SIZE, "blocks.py MODERN_CAMERA_DATA_SIZE");
_Static_assert(sizeof(struct modern_camera_state) <= STATE_SIZE, "blocks.py MODERN_CAMERA_STATE_SIZE");

extern const struct modern_camera_data modern_camera_data;
extern struct modern_camera_state modern_camera_state;
extern const volatile u8 mod_options_state[];       /* interface/mod_settings/mod_options.c: values first */
extern int mod_option_count(int id);                /* mod_options.c: 0 when the page has no row for the option */
extern const u32 *mod_option_payload(int id);       /* the words of the value in use */
extern u8 *const game_control;                      /* the variable holding sGameControl */
extern u8 *const camera_control;                    /* the variable holding sCamera */

/* Game functions */
u32 camera_turn_by_input(u8 *camera, u8 *input, u32 flags);    /* FUN_00bfd028 (sMhCamera::turnByInput) */
u32 is_gunner(u8 *hunter, u32 kind);                            /* FUN_00d04dd4: a bowgun (kind 0), the Bow (2) */
u32 hunter_is_local(u8 *hunter);                                /* FUN_00d04fbc: the hunter this console plays */
__attribute__((pcs("aapcs-vfp"))) float aim_speed(u8 *hunter, u32 kind);   /* FUN_00b3fe50: the Aim Speed's factor */
u32 camera_zoom(u8 *camera, u8 *zooming, float *zoom);         /* FUN_00c00038: the scope's zoom, 0 to 1 (1 widest) */
__attribute__((pcs("aapcs-vfp"))) void aim_pitch_view(u8 *hunter, int pitch, float up, float down);  /* FUN_00b1ea04 */

#define U32(p, off) (*(volatile u32 *)((p) + (off)))
#define U16(p, off) (*(volatile u16 *)((p) + (off)))
#define S16(p, off) (*(volatile s16 *)((p) + (off)))
#define U8(p, off)  (*(volatile u8 *)((p) + (off)))
#define F32(p, off) (*(volatile float *)((p) + (off)))

/* FUN_00bfd028's steps at the top of the turn for the input's mode: normal, bit 0, bit 1 (the game's literals) */
static const u16 PITCH_STEPS[3] = {0x180, 0xF0, 0x120};
static const u16 YAW_STEPS[3] = {0x400, 0x2E0, 0x340};

static float absolute(float x)
{
    return x < 0.0f ? -x : x;
}

/* The sine of a u16 angle: the parabola through 0, +-1 at a quarter turn and 0 at half a turn, corrected (an error
   under 0.001) */
static float sine(u32 angle)
{
    float t = (float)(s16)angle * (1.0f / 32768.0f);   /* -1 to 1 for half a turn either way */
    float y = 4.0f * t - 4.0f * t * absolute(t);
    return y + 0.225f * (y * absolute(y) - y);
}

/* The stick's tilt past the dead zone, 0 to 1, through the response curve `expo` */
static float tilt(u32 length, const struct modern_camera_data *data, float expo)
{
    float t = ((float)length / STICK_FULL - data->dead_zone) / (data->full_tilt - data->dead_zone);

    if (!(t > 0.0f))
        return 0.0f;
    if (t > 1.0f)
        t = 1.0f;
    return (1.0f - expo) * t + expo * t * t * t;
}

/* The factor of the option's value in use (Max Speed's multiplier, Acceleration's share): 1 without the row */
static float option_factor(u32 id)
{
    union { u32 word; float number; } value;

    if (mod_option_count((int)id) == 0)
        return 1.0f;
    value.word = mod_option_payload((int)id)[0];
    return value.number > 0.0f ? value.number : 1.0f;
}

/* A speed one frame closer to `target`: an exponential approach with the time constant of speeding up (`up`) or of
   slowing down (`down`), the same over any frame's time; with the stick released, under `stop` (the axis's own units)
   it stops */
static float approach(float speed, float target, float frame, float stop, float up, float down)
{
    int faster = target > 0.0f ? speed >= 0.0f && target > speed : target < 0.0f && speed <= 0.0f && target < speed;
    float time = faster ? up : down;

    speed += (target - speed) * frame / (time + frame);
    if (target == 0.0f && absolute(speed) < stop)
        speed = 0.0f;
    return speed;
}

/* The whole units of `amount` and what was left over before */
static int whole(float *rest, float amount)
{
    float total = *rest + amount;
    int step = (int)total;

    *rest = total - (float)step;
    return step;
}

static u32 add_pitch(u32 pitch, int step)
{
    int value = (s16)pitch + step;

    if (value > PITCH_LIMIT)
        value = PITCH_LIMIT;
    if (value < -PITCH_LIMIT)
        value = -PITCH_LIMIT;
    return (u32)value & 0xFFFF;
}

static void turn_angles(u8 *at, u32 pitch, u32 yaw, int pitch_step, int yaw_step)
{
    U32(at, pitch) = add_pitch(U32(at, pitch), pitch_step);
    U32(at, yaw) = (U32(at, yaw) + (u32)yaw_step) & 0xFFFF;
}

typedef u32 (*stick_question)(u8 *hunter, u32 stick);

/* The hunter's own answer to "is this stick tilted" for a stick of `length` (the input object's is put back) */
static u32 game_answer(u8 *hunter, u8 *input, u32 stick, u32 length)
{
    stick_question ask = (stick_question)U32((u8 *)U32(hunter, 0), HUNTER_STICK);
    u32 kept = U16(input, STICK_LENGTHS + 2 * stick), answer;

    U16(input, STICK_LENGTHS + 2 * stick) = length;
    answer = ask(hunter, stick);
    U16(input, STICK_LENGTHS + 2 * stick) = kept;
    return answer;
}

/* FUN_00b3cc64's question "is the C-stick tilted": the game's answer, and the stick kept for the camera when the game
   takes it */
u32 modern_camera_stick(u8 *hunter, u32 stick)
{
    struct modern_camera_state *state = &modern_camera_state;
    u8 *input = hunter ? (u8 *)U32(hunter, HUNTER_INPUT) : 0;
    u32 length;

    if (input == 0)
        return 0;
    length = U16(input, STICK_LENGTHS + 2 * stick);
    state->fresh = 0;
    if (game_answer(hunter, input, stick, STICK_ALL_THE_WAY) != 0) {
        state->hunter = (u32)hunter;
        state->angle = U16(input, STICK_ANGLES + 2 * stick);
        state->length = length;
        state->held = U32(input, INPUT_ACTIONS) & TURN_ACTIONS;
        state->fresh = (1u << SLOTS) - 1;
    }
    return game_answer(hunter, input, stick, length);
}

__attribute__((used, section(".text.entry"))) u32 modern_camera_turn(u8 *camera, u8 *input, u32 flags)
{
    const struct modern_camera_data *data = &modern_camera_data;
    struct modern_camera_state *state = &modern_camera_state;
    int slot = input == camera + CAMERA_MAIN ? 0 : 1;
    int ours = state->fresh & (1u << slot) && state->hunter != 0 && state->hunter == U32(camera, CAMERA_HUNTER);
    u8 *actions = ours ? (u8 *)U32((u8 *)state->hunter, HUNTER_INPUT) : 0;
    u32 hidden = actions ? U32(actions, INPUT_ACTIONS) & TURN_ACTIONS & ~state->held : 0, result;
    struct turn *turn = &state->turns[slot];
    float frame = F32(camera, CAMERA_FRAME), yaw_target = 0.0f, pitch_target = 0.0f;
    float quick = option_factor(data->accel_option);   /* Acceleration: the time constants shrink by it */
    int yaw, pitch, moved;

    /* the game's turn by the D-pad: the C-stick's buttons of this frame are the stick's, turned below */
    if (hidden)
        U32(actions, INPUT_ACTIONS) &= ~hidden;
    result = camera_turn_by_input(camera, input, flags);
    if (hidden)
        U32(actions, INPUT_ACTIONS) |= hidden;
    if (ours) {
        float amount = tilt(state->length, data, data->expo);

        if (amount > 0.0f) {
            u32 mode = U8(input, INPUT_MODE);
            int pace = mode & 2 ? 2 : mode & 1 ? 1 : 0;
            float top = amount * option_factor(data->speed_option);

            /* the game's "camera left" (direction 0x8000) adds to the yaw, its "camera up" (0x4000) to the pitch */
            yaw_target = -sine(state->angle + 0x4000) * top * data->yaw_speed * YAW_STEPS[pace] / YAW_STEPS[0];
            pitch_target = sine(state->angle) * top * data->pitch_speed * PITCH_STEPS[pace] / PITCH_STEPS[0];
            if (flags & INVERT_YAW)
                yaw_target = -yaw_target;
            if (flags & INVERT_PITCH)
                pitch_target = -pitch_target;
        }
    }
    state->fresh &= ~(1u << slot);
    if (!(frame > 0.0f))
        return result;
    if (frame > data->longest_frame)
        frame = data->longest_frame;
    turn->yaw = approach(turn->yaw, yaw_target, frame, data->stop_speed, data->speed_up / quick,
                         data->slow_down / quick);
    turn->pitch = approach(turn->pitch, pitch_target, frame, data->stop_speed, data->speed_up / quick,
                           data->slow_down / quick);
    yaw = whole(&turn->rest_yaw, turn->yaw * frame);
    pitch = whole(&turn->rest_pitch, turn->pitch * frame);
    if (yaw_target != 0.0f)
        U8(input, INPUT_TURNED) |= TURNED_YAW;
    if (pitch_target != 0.0f)
        U8(input, INPUT_TURNED) |= TURNED_PITCH;
    if (yaw == 0 && pitch == 0)
        return result;
    moved = (s16)U32(input, INPUT_PITCH);
    turn_angles(input, INPUT_PITCH, INPUT_YAW, pitch, yaw);
    moved = (s16)U32(input, INPUT_PITCH) - moved;     /* the pitch's turn within the limit */
    if (slot == 0 && data->direct && U8(camera, CAMERA_FORCED) == 0) {
        turn_angles(camera + CAMERA_RIG, RIG_PITCH, RIG_YAW, moved, yaw);
        turn_angles(camera + CAMERA_RIG, RIG_PITCH_COPY, RIG_YAW_COPY, moved, yaw);
    }
    if (result == TURN_NONE)
        result = yaw != 0 ? TURN_YAW : TURN_PITCH;
    return result;
}

/* ----- the aims ------------------------------------------------------------------------------------------------- */

static int in_sector(u32 angle, const u16 *sector)
{
    return (u16)(angle - sector[0]) <= (u16)(sector[1] - sector[0]);
}

/* The commands (up 1, down 2, left 4, right 8) the C-stick's direction gives in FUN_00ca51c0 and FUN_00cb4140 */
static u32 stick_commands(u32 angle)
{
    u32 bits = in_sector(angle, SECTORS[0]) ? 1 : in_sector(angle, SECTORS[1]) ? 2 : 0;

    return bits | (in_sector(angle, SECTORS[2]) ? 4 : in_sector(angle, SECTORS[3]) ? 8 : 0);
}

/* The Bow's D-pad commands (FUN_00cb4140), as stick_commands' */
static u32 dpad_commands(u32 held)
{
    return (held >> 13 & 1) | (held >> 11 & 2) | (held >> 9 & 4) | (held >> 7 & 8);
}

/* One frame of the aim's turn by the C-stick (`live`: the game takes the C-stick for this aim) */
static void aim_turn(u8 *hunter, u8 *frame, u32 kind, int live)
{
    const struct modern_camera_data *data = &modern_camera_data;
    struct modern_camera_state *state = &modern_camera_state;
    struct turn *turn = &state->aim;
    u8 *input = (u8 *)U32(hunter, HUNTER_INPUT), *work = (u8 *)U32(hunter, HUNTER_WEAPON);
    u32 now = mod_options_state[MOD_FRAME];
    float time = F32(hunter, HUNTER_TIME), yaw_target = 0.0f, pitch_target = 0.0f;
    float quick = option_factor(data->accel_option);   /* Acceleration: the time constants shrink by it */
    float amount = live ? tilt(U16(input, STICK_LENGTHS + 2 * C_STICK), data, data->aims[kind].expo) : 0.0f, pitch;
    int yaw;

    if (state->aim_hunter != (u32)hunter || state->aim_kind != kind || (u8)(now - state->aim_frame) > 1)
        turn->yaw = turn->pitch = turn->rest_yaw = turn->rest_pitch = 0.0f;
    state->aim_hunter = (u32)hunter;
    state->aim_kind = kind;
    state->aim_frame = now;
    if (amount > 0.0f) {
        u32 angle = U16(input, STICK_ANGLES + 2 * C_STICK);
        u32 invert = game_control ? U8(game_control, SETTINGS_BYTES + AIM_RULES[kind].invert) : 0;
        float yaw_top = amount * aim_speed(hunter, AIM_RULES[kind].speed_kind) / AIM_RULES[kind].normal *
            option_factor(data->speed_option);
        float pitch_top = yaw_top;

        if (kind == AIM_SCOPE && camera_control) {
            u8 zooming;
            float zoom = 1.0f;          /* the game's own start: no zoom, the widest view */

            camera_zoom(camera_control, &zooming, &zoom);
            yaw_top *= (SCOPE_YAW_STEPS[0] + (SCOPE_YAW_STEPS[1] - SCOPE_YAW_STEPS[0]) * zoom) / SCOPE_YAW_STEPS[1];
            pitch_top *= (SCOPE_PITCH_STEPS[0] + (SCOPE_PITCH_STEPS[1] - SCOPE_PITCH_STEPS[0]) * zoom) /
                SCOPE_PITCH_STEPS[1];
        }
        /* the aim's "left" (direction 0x8000) adds to its yaw, its "up" (0x4000) to its pitch */
        yaw_target = -sine(angle + 0x4000) * yaw_top * data->aims[kind].yaw;
        pitch_target = sine(angle) * pitch_top * data->aims[kind].pitch;
        if (invert == 2 || invert == 3)
            yaw_target = -yaw_target;
        if (invert == 1 || invert == 3)
            pitch_target = -pitch_target;
    }
    if (!(time > 0.0f))
        return;
    if (time > data->longest_frame)
        time = data->longest_frame;
    /* the pitch in its own steps: the yaw's stop in angle units would stop it dead */
    turn->yaw = approach(turn->yaw, yaw_target, time, data->stop_speed, data->aims[kind].speed_up / quick,
                         data->aims[kind].slow_down / quick);
    turn->pitch = approach(turn->pitch, pitch_target, time, data->aims[kind].pitch_stop,
                           data->aims[kind].speed_up / quick, data->aims[kind].slow_down / quick);
    yaw = whole(&turn->rest_yaw, turn->yaw * time);
    pitch = turn->pitch * time;
    /* as the game's commands: the pitch marks the aim moved, then the yaw (when FUN_00b2041c turns it) */
    if (pitch != 0.0f) {
        pitch += F32(work, WORK_PITCH);
        if (pitch > AIM_PITCH_LIMIT)
            pitch = AIM_PITCH_LIMIT;
        if (pitch < -AIM_PITCH_LIMIT)
            pitch = -AIM_PITCH_LIMIT;
        F32(work, WORK_PITCH) = pitch;
        F32(work, WORK_PITCH_COPY) = pitch;
        U8(work, WORK_MOVED) = MOVED_PITCH;
    }
    if (yaw != 0 && U32(frame, AIM_TURN) != 0) {
        U32(frame, AIM_YAW) += (u32)yaw;
        U8(work, WORK_MOVED) = MOVED_YAW;
    }
}

/* FUN_00b2041c's commands over the shoulder (mode 0) or the Bow's (mode 3), without the C-stick's; the stick turns
   the aim instead */
u32 modern_aim_commands(u8 *hunter, u32 commands, u8 *frame)
{
    int bow = U32(frame, AIM_MODE) == MODE_BOW;
    u32 kind = bow ? AIM_BOW : AIM_SHOULDER;
    u8 *input = (u8 *)U32(hunter, HUNTER_INPUT);
    int live;

    if (input == 0 || !hunter_is_local(hunter))     /* another console's hunter aims as that console turns it */
        return commands;
    live = is_gunner(hunter, bow ? GUNNER_BOW : GUNNER_BOWGUN) &&
        game_answer(hunter, input, C_STICK, STICK_ALL_THE_WAY) != 0 && (!bow || U32(input, INPUT_FLAGS) & AIMING);

    if (live && game_answer(hunter, input, C_STICK, U16(input, STICK_LENGTHS + 2 * C_STICK)) != 0) {
        u32 others = bow ? dpad_commands(U32(input, INPUT_HELD)) : commands >> DPAD_COMMANDS;

        commands &= ~((stick_commands(U16(input, STICK_ANGLES + 2 * C_STICK)) & ~others & 0xF) <<
                      AIM_RULES[kind].first);
    }
    aim_turn(hunter, frame, kind, live);
    return commands;
}

/* The scope's C-stick bits FUN_00b2041c tests (`bits`; it reads them only where the game aims by them): none, and the
   stick turns the aim; another console's hunter keeps them */
u32 modern_aim_scope(u8 *hunter, u8 *frame, u32 bits)
{
    if (U32(hunter, HUNTER_INPUT) == 0 || !hunter_is_local(hunter))
        return bits;
    aim_turn(hunter, frame, AIM_SCOPE, 1);
    return 0;
}

/* FUN_00b2041c's calls of FUN_00b1ea04(hunter, pitch, up, down) (modes 0, 3; `pitch` the integer part of the aim's):
   the game's angle, then, for a pitch with a fraction, the same steps from the whole pitch */
__attribute__((pcs("aapcs-vfp"))) void modern_aim_view(u8 *hunter, int pitch, float up, float down)
{
    u8 *work = (u8 *)U32(hunter, HUNTER_WEAPON);
    float whole_pitch = F32(work, WORK_PITCH), part = whole_pitch * PERCENT;

    aim_pitch_view(hunter, pitch, up, down);
    if ((int)whole_pitch == pitch && whole_pitch != (float)pitch) {
        float angle = (part >= 0.0f ? up : down) * part * TURN_UNITS;

        S16(work, WORK_PITCH_ANGLE) = (s16)(int)(0.5f + angle * PER_DEGREE);
    }
}

/* The hooks inside FUN_00b2041c (r4 its hunter; its stack is `frame`, 24 bytes above the registers pushed here) */
__asm__(
    "   .section .text.modern_aim, \"ax\", %progbits\n"
    "   .arm\n"
    /* `ldr r0, [r2, #0x3e4]` (r2 the input object): r0 the commands, without the C-stick's */
    "   .global aim_commands_hook\n"
    "aim_commands_hook:\n"
    "   push    {r1-r4, r12, lr}\n"
    "   ldr     r1, [r2, #0x3e4]\n"
    "   mov     r0, r4\n"
    "   add     r2, sp, #24\n"
    "   bl      modern_aim_commands\n"
    "   pop     {r1-r4, r12, lr}\n"
    "   bx      lr\n"
    /* `tst r0, #0x3c` (r0 the sticks' direction bits): the test of the bits modern_aim_scope leaves, r0 kept */
    "   .global aim_scope_hook\n"
    "aim_scope_hook:\n"
    "   push    {r0-r3, r12, lr}\n"
    "   mov     r2, r0\n"
    "   mov     r0, r4\n"
    "   add     r1, sp, #24\n"
    "   bl      modern_aim_scope\n"
    "   tst     r0, #0x3c\n"
    "   pop     {r0-r3, r12, lr}\n"
    "   bx      lr\n"
);
