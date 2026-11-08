/* Select and Start follow the game's own option "START" (page 2 of the Options, "Menu" or "Kick"; settings index 0x11;
 * gameplay/select_kick/select_kick.py).
 *
 * The game gives Select no button of its own: the SDK's pad step (FUN_00485708) turns a held SELECT into START in the
 * 3DS pad status (FUN_00571e58). With the option at Kick the game takes START away from the Game Menu in a quest
 * (FUN_005ecf60) and turns it into the kick (FUN_00b169bc). Two entries, each a `bl` of the game replaced by a `bl` to
 * this block:
 *   select_kick_step(status)         0x4857F0 in FUN_00485708 (the `bleq` of FUN_00571e58, once per pad read, before the
 *       pad update FUN_00694ccc maps the buttons). At the title or with no save loaded it does nothing: Select stays a
 *       Select, which the game maps to no button. Otherwise:
 *       * option Menu: Select kicks and only Start opens the menu. It presses the kick in the game layout the way the
 *         touch panel does, bit 0x1 of the pad's word +0x3F0 (which the pad update turns into the held buttons and
 *         clears).
 *       * option Kick, in a town: Select opens the menu. It makes the original call, so Select is a second Start.
 *       * option Kick, in a quest: Select opens and closes the Game Menu. It only notes in select_kick_state that Select
 *         is held (HELD) and that the menu has seen it (SEEN); the kick stays on Start.
 *   select_kick_gate(settings, 0x11)  0x5ED0D0 in FUN_005ecf60 (the menu's per-frame logic), instead of the call of
 *       FUN_002b02fc, which reads the setting that stops Start from opening the menu in a quest. It reads the setting
 *       as the game does; when Select was pressed this frame in a quest with Kick it also sets Start (0x400) in the
 *       menu's copy of the pressed GUI buttons (menu + 0x558, which the line before the call filled) and returns 0, so
 *       the game's own test lets this press open or close the menu. Start keeps being refused.
 * Both entries keep the registers the calls they replace keep (r4 and up; r0-r3 and ip are scratch there). Nothing else
 * changes: START in the menus and in the town, and the touch panel's kick, do as before.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with select_kick.ld where it places the block); the
 * game functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;

/* The 3DS pad status given to FUN_00571e58 */
#define STATUS_HELD   0x8       /* u32: the buttons held (HID bits) */
#define HID_SELECT    0x4

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

/* Game functions */
void sdk_select_to_start(u8 *status);                       /* FUN_00571e58: Select becomes Start in the status */
u32 game_setting(u8 *control, u32 index);                   /* FUN_002b02fc: the settings byte `index` */

#define U32(p, off) (*(volatile u32 *)((p) + (off)))
#define U8(p, off)  (*(volatile u8 *)((p) + (off)))

__attribute__((used, section(".text.entry"))) void select_kick_step(u8 *status)
{
    u8 *game = game_control, *pad = pad_control;
    u32 select = U32(status, STATUS_HELD) & HID_SELECT, before = select_kick_state, state = 0;
    u32 mode = game ? U8(game, GAME_MODE) : 0;
    if (mode != MODE_QUEST && mode != MODE_TOWN) {          /* the title, a save not loaded: the option is not read */
        select_kick_state = 0;
        return;
    }
    if (game_setting(game, OPTION_START) == START_KICKS) {
        if (mode == MODE_TOWN)
            sdk_select_to_start(status);
        else if (select)
            state = HELD | (before & SEEN);
    } else if (select && pad) {
        U32(pad, PAD_PRESS) |= GAME_KICK;
    }
    select_kick_state = state;
}

__attribute__((used, section(".text.entry"))) u32 select_kick_gate(u8 *control, u32 index)
{
    u32 option = game_setting(control, index), state = select_kick_state;
    u32 pressed = (state & HELD) && !(state & SEEN);
    select_kick_state = (state & HELD) ? state | SEEN : 0;
    if (pressed && option == START_KICKS) {
        U32(start_menu, M_PRESSED) |= GUI_START;
        return 0;
    }
    return option;
}
