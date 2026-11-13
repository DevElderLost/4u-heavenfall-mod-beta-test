/* Select and Start follow the game's own option "START" (page 2 of the Options, "Menu" or "Kick"; settings index 0x11;
 * gameplay/select_kick/select_kick.py).
 *
 * The game gives Select no button of its own: the SDK's pad step (FUN_00485708) turns a held SELECT into START in the
 * 3DS pad status. It reads the pad on one of two paths, each with its own call that does it: with an extra pad
 * answering (the New 3DS's ZL, ZR and C-stick, or a Circle Pad Pro) FUN_00571e58 on the status (held at +8), and
 * without one (an Old 3DS alone, or a New 3DS with its C-stick off) FUN_00571e4c on FUN_00485e30's own status (held at +0). With the option at Kick the
 * game takes START away from the Game Menu in a quest (FUN_005ecf60) and turns it into the kick (FUN_00b169bc). Three
 * entries, each a `bl` of the game replaced by a `bl` to this block:
 *   select_kick_step(status)          0x4857F0 in FUN_00485708 (the `bleq` of FUN_00571e58, once per pad read on the
 *   select_kick_step_hid(status)      extra pad's path, before the pad update FUN_00694ccc maps the buttons), and
 *       0x485F40 in FUN_00485e30 (the `bleq` of FUN_00571e4c, on the path without it). At the title or with no save
 *       loaded they do nothing: Select stays a Select, which the game maps to no button. Otherwise:
 *       * option Menu: Select kicks and only Start opens the menu. It presses the kick in the game layout the way the
 *         touch panel does, bit 0x1 of the pad's word +0x3F0 (which the pad update turns into the held buttons and
 *         clears).
 *       * option Kick, in a town: Select opens the menu. It makes the original call, so Select is a second Start.
 *       * in a town, with either value, Select also presses the kick's button: the Armor screen of Layered Gear
 *         reads it as Select (equipment/layered/layered_forge.c), and a town has no kick.
 *       * option Kick, in a quest: Select opens and closes the Game Menu. It only notes in select_kick_state that Select
 *         is held (HELD) and that the menu has seen it (SEEN); the kick stays on Start.
 *   select_kick_gate(settings, 0x11)  0x5ED0D0 in FUN_005ecf60 (the menu's per-frame logic), instead of the call of
 *       FUN_002b02fc, which reads the setting that stops Start from opening the menu in a quest. It reads the setting
 *       as the game does; when Select was pressed this frame in a quest with Kick it also sets Start (0x400) in the
 *       menu's copy of the pressed GUI buttons (menu + 0x558, which the line before the call filled) and returns 0, so
 *       the game's own test lets this press open or close the menu. Start keeps being refused. While a slain monster's
 *       death camera plays with its skip on (death_camera_skip_state, set by gameplay/death_camera_skip/
 *       death_camera_skip.c) it counts that state down and answers Kick: in a quest Start then ends the camera and
 *       does not open the menu.
 *   select_plain_step(status)         the two SDK calls instead of the kick's steps, in a mod without Select's kick
 *   select_plain_step_hid(status)     (Heavenfall Beta with its single-screen module off): Select stays the game's, a
 *       second Start everywhere (the original call is made as it was), and in a town it also presses the kick's
 *       button, which Layered Gear's Armor screen reads as Select (a town has no kick). select_kick_gate keeps the
 *       menu's call: select_kick_state stays 0, so it only answers Kick while the death camera plays with its skip on.
 * The entries keep the registers the calls they replace keep (r4 and up; r0-r3 and ip are scratch there). Nothing else
 * changes: START in the menus and in the town, and the touch panel's kick, do as before.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with select_kick.ld where it places the block); the
 * game functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;

/* The 3DS pad status given to FUN_00571e58 (the extra pad's path) and to FUN_00571e4c (the path without it) */
#define STATUS_HELD      0x8    /* u32: the buttons held (HID bits) */
#define HID_STATUS_HELD  0x0
#define HID_SELECT       0x4

/* sGameControl, the variable game_control holds: +0x2B the mode, +100 + n the settings byte n */
#define GAME_MODE     0x2B
#define MODE_QUEST    1
#define MODE_TOWN     2
#define OPTION_START  0x11      /* 0 Menu, 1 Kick */
#define START_KICKS   1

/* The pad object (*pad_control) */
#define PAD_PRESS     0x3F0     /* u32: game-layout buttons pressed for the next pad update (the touch panel's way) */
#define GAME_KICK     0x1

/* The Game Menu's object */
#define M_PRESSED     0x558     /* u32: the GUI buttons pressed this frame */
#define GUI_START     0x400

/* select_kick_state */
#define HELD          0x1       /* Select is held, in a quest, with the option at Kick */
#define SEEN          0x2       /* the menu's logic has run since Select was pressed */

extern u8 *const game_control;          /* the variable holding sGameControl */
extern u8 *const pad_control;           /* the variable holding the pad object */
extern u8 start_menu[];                 /* the Game Menu's object */
extern volatile u32 select_kick_state;  /* the variable */
/* Frames left in which START belongs to a slain monster's death camera (gameplay/death_camera_skip/death_camera_skip.c
 * keeps it set while the camera plays with its option on; 0 in a mod without it) */
extern volatile u32 death_camera_skip_state;

/* Game functions */
void sdk_select_to_start(u8 *status);                       /* FUN_00571e58: Select becomes Start, held at +8 */
void hid_select_to_start(u8 *status);                       /* FUN_00571e4c: the same, held at +0 */
u32 game_setting(u8 *control, u32 index);                   /* FUN_002b02fc: the settings byte `index` */

#define U32(p, off) (*(volatile u32 *)((p) + (off)))
#define U8(p, off)  (*(volatile u8 *)((p) + (off)))

/* The game's call of the SDK path `hid` (1: the path without the extra pad) */
static inline __attribute__((always_inline)) void select_to_start(u8 *status, u32 hid)
{
    if (hid)
        hid_select_to_start(status);
    else
        sdk_select_to_start(status);
}

static inline __attribute__((always_inline)) void kick_step(u8 *status, u32 hid)
{
    u8 *game = game_control, *pad = pad_control;
    u32 select = U32(status, hid ? HID_STATUS_HELD : STATUS_HELD) & HID_SELECT, before = select_kick_state, state = 0;
    u32 mode = game ? U8(game, GAME_MODE) : 0;
    if (mode != MODE_QUEST && mode != MODE_TOWN) {          /* the title, a save not loaded: the option is not read */
        select_kick_state = 0;
        return;
    }
    u32 kicks = game_setting(game, OPTION_START) == START_KICKS;
    if (select && pad && (!kicks || mode == MODE_TOWN))
        U32(pad, PAD_PRESS) |= GAME_KICK;
    if (kicks) {
        if (mode == MODE_TOWN)
            select_to_start(status, hid);
        else if (select)
            state = HELD | (before & SEEN);
    }
    select_kick_state = state;
}

static inline __attribute__((always_inline)) void plain_step(u8 *status, u32 hid)
{
    u8 *game = game_control, *pad = pad_control;
    if (game && pad && U8(game, GAME_MODE) == MODE_TOWN
        && (U32(status, hid ? HID_STATUS_HELD : STATUS_HELD) & HID_SELECT))
        U32(pad, PAD_PRESS) |= GAME_KICK;
    select_to_start(status, hid);
}

__attribute__((used, section(".text.entry"))) void select_kick_step(u8 *status)
{
    kick_step(status, 0);
}

__attribute__((used, section(".text.entry"))) void select_kick_step_hid(u8 *status)
{
    kick_step(status, 1);
}

__attribute__((used, section(".text.entry"))) void select_plain_step(u8 *status)
{
    plain_step(status, 0);
}

__attribute__((used, section(".text.entry"))) void select_plain_step_hid(u8 *status)
{
    plain_step(status, 1);
}

__attribute__((used, section(".text.entry"))) u32 select_kick_gate(u8 *control, u32 index)
{
    u32 option = game_setting(control, index), state = select_kick_state, camera = death_camera_skip_state;
    u32 pressed = (state & HELD) && !(state & SEEN);
    select_kick_state = (state & HELD) ? state | SEEN : 0;
    if (camera) {                       /* START ends the death camera: it does not open the menu in a quest */
        death_camera_skip_state = camera - 1;
        return START_KICKS;
    }
    if (pressed && option == START_KICKS) {
        U32(start_menu, M_PRESSED) |= GUI_START;
        return 0;
    }
    return option;
}
