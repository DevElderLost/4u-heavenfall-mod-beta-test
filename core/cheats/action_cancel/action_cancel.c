/* The cheats Interruptible Flex and Whetstone Sharpening Cancel (cheats/action_cancel/action_cancel.py): the hunter's
flex after a drink or a
 * meal, and his sharpening, end at once on the player's input. From the players' Gateway codes for the USA update
 * (one cave called from the hunter's update, which both codes share, each switched on by a literal of its own); here
 * as a block of the code space.
 *
 * FUN_00b1471c, the hunter's update, calls FUN_00b670c0(hunter), the frame of the hunter's action, at 0xB14A98. That
 * call comes here (action_cancel_update): the cancel first, then the game's call.
 *   - Only the hunter this console plays (FUN_00d04fbc), in group 0 (act_st, p + 0x371) and
 *       action 0x57 (act_no, p + 0x372), the flex: the drink's and the meal's action (FUN_00b57b7c) starts it when
 *         their motion ends, unless the item was a Cleanser; or
 *       action 0x5A, the sharpening: the whetstone's action (FUN_00b580dc);
 *     each while its Mod Settings option has a value other than its first (mod_options_state.values, read as the
 *     gates of mod_options_stub.s read them; the options' ids are in action_cancel_data, NO_OPTION for none).
 *   - The pad (*pad_control), raw bits: held at + 0x8C, pressed this frame at + 0x94.
 *     The flex ends on a tilt of the Circle Pad or the C-stick held, or on a press of A, B, X or Y while L is not held;
 *     the sharpening on a press of B.
 *   - The end is the game's own: with a stick tilted the hunter's heading first turns to it (FUN_00b3d128: pw + 0xB0,
 *     the camera's angle plus the stick's, p + 0x3C0), then
 *     FUN_00b1d7b4(hunter, pl_st, 4, 0, 0) takes him back to the neutral action, the call the flex and the sharpening
 *     make themselves when their motion is over (0xB57F68, 0xB5848C), and the new action's first frame runs at once
 *     (FUN_00b670c0). After the sharpening, the two checks the update makes before the action's frame (0xB14960:
 *     FUN_00b18618, then FUN_00b0d784 when the first started nothing) run again, so the press of B is read in the same
 *     frame. Then the update's own call of the action's frame.
 * The Gateway cave has one more branch, taken while a byte of a variable of the cheat device's own is set; none of
 * these codes sets it, so it never runs and is left out.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with action_cancel.ld);
 * the game's functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define ENTRY __attribute__((used, section(".text.entry")))

#define H_PLAYER    0xE30       /* the hunter's player record p */
#define P_STANCE    0x370       /* u8: pl_st, which the neutral action comes back with */
#define P_GROUP     0x371       /* u8: act_st, the action's group */
#define P_ACTION    0x372       /* u16: act_no, the action */
#define ACT_FLEX    0x57
#define ACT_SHARPEN 0x5A

#define PAD_HELD    0x8C        /* the pad's raw buttons held */
#define PAD_PRESSED 0x94        /* ... and pressed this frame */
#define STICKS      0xFF0000    /* the Circle Pad (0xF0000) and the C-stick (0xF00000) tilted */
#define BUTTON_L    0x100
#define FACE        0xF000      /* X 0x1000, A 0x2000, B 0x4000, Y 0x8000 */
#define BUTTON_B    0x4000

#define END_BLEND   4           /* FUN_00b1d7b4's blends, as the actions' own ends pass them */
#define NO_OPTION   0xFF        /* action_cancel.py NO_OPTION */

struct action_cancel_data {     /* action_cancel.py action_cancel_data */
    u32 flex_option;            /* mod_options.py OPTION_IDS: the option that turns the flex's cancel on */
    u32 sharpen_option;         /* ... and the sharpening's */
};

extern const struct action_cancel_data action_cancel_data;
extern const volatile u8 mod_options_state[];       /* interface/mod_settings/mod_options.c: the values first */
extern u32 pad_control;
extern int hunter_is_local(void *hunter);
extern void hunter_run_action(void *hunter);
extern void hunter_end_action(void *hunter, u32 stance, u32 blend, u32 blend_2, u32 zero);
extern void hunter_face_stick(void *hunter);
extern int hunter_update_check(void *hunter);
extern void hunter_update_check_more(void *hunter);

static int option_on(u32 id)
{
    return id != NO_OPTION && mod_options_state[id] != 0;
}

static void cancel(void *hunter)
{
    const u8 *p = *(const u8 *const *)((const u8 *)hunter + H_PLAYER);
    const u8 *pad;
    u32 held, pressed;
    int flex, act;

    if (p == 0 || p[P_GROUP] != 0)
        return;
    act = *(const u16 *)(p + P_ACTION);
    flex = act == ACT_FLEX;
    if (!(flex ? option_on(action_cancel_data.flex_option)
               : act == ACT_SHARPEN && option_on(action_cancel_data.sharpen_option)))
        return;
    if (!hunter_is_local(hunter) || pad_control == 0)
        return;
    pad = (const u8 *)pad_control;
    held = *(const u32 *)(pad + PAD_HELD);
    pressed = *(const u32 *)(pad + PAD_PRESSED);
    if (flex ? !(held & STICKS) && ((held & BUTTON_L) || !(pressed & FACE)) : !(pressed & BUTTON_B))
        return;
    if (held & STICKS)
        hunter_face_stick(hunter);
    hunter_end_action(hunter, p[P_STANCE], END_BLEND, 0, 0);
    hunter_run_action(hunter);
    if (!flex && !hunter_update_check(hunter))
        hunter_update_check_more(hunter);
}

ENTRY void action_cancel_update(void *hunter)
{
    cancel(hunter);
    hunter_run_action(hunter);
}
