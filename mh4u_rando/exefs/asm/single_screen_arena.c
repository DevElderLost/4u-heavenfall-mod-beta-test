/* Single-screen mode: the Arena's team and weapon choice on the pad (exefs/single_screen_arena.py; emulator only).
 *
 * The select scene (ui497, FUN_00654850) is meant for the touch screen: its four big buttons (items, equipment, status,
 * skill info: touch-list indices 5-8, the modes 1-4 of FUN_006526b8) are touched, and the pad only steps the weapon set
 * (left / right in the weapon choice, mode 0: FUN_00650c44). With the layout on the top screen there is nothing to touch,
 * so this block gives the pad a cursor over the choice, run in the three places the weapon choice (kind 1, phase 1)
 * calls into every frame:
 *
 *  - arena_touch, in place of the call of the touch list's handler FUN_0065178c(scene) (0x64F8E4: the call, then
 *    `cmp r0, #0; movne r8, #0` clears the frame's pad word when the handler answers 1, then the result it left at
 *    scene + 0x1B48 (index + 1 of the pressed pane: 1-5 a weapon set, 6-9 a button) is acted on). It runs the handler
 *    and, unless it saw a touch, does the pad's part:
 *      mode 0 (the choice): up on the weapon choice puts the cursor on the curated button above the set; on a button
 *        left / right move it (no wrap), down gives it back to the weapon choice, A writes the button's result
 *        (5 + the button) at scene + 0x1B48 and answers 1, so the game does what a touch on the button does (the
 *        click, mode toggled, scene rebuilt) and A does not also confirm the weapon;
 *      mode 1-4 (a panel open): B asks for mode 0 (scene + 0x1A24 = 0, which the game's own check applies the same frame
 *        and answers 1) and leaves the cursor on the button the mode was opened from; no other key is taken.
 *  - arena_pad, in place of the call of the per-mode pad FUN_00650c44(scene) (0x64FA10): the same call with left and
 *    right hidden from the game's pad word while the cursor is on a button (the weapon choice would step the set), the
 *    word given back after.
 *  - arena_frame_hook, in place of the `sub r0, r0, #1` that gives the frame ui497_sel_flame_00 its table entry (mode -
 *    1) in FUN_0065303c (0x653064, run every frame by FUN_006531f4): in the weapon choice the cursor's button, so the
 *    game's own selection frame is the cursor; in a mode panel the game's (the open mode's button).
 *
 * The cursor lives in the scene, in the padding after the touch list's flag bytes (scene + 0x1B39 the button, 0 the weapon
 * choice; + 0x1B3A the high half of the countdown float at + 0x120 seen last: a float's high half grows with its value, so
 * a countdown that is higher than the last one is a new visit, which starts on the weapon choice). The touch list's
 * members are +0x1B30 (pointer), +0x1B34 (halfword), +0x1B36 / +0x1B37 / +0x1B38 (bytes) and +0x1B3C (pointer): the
 * game's code reads and writes only those; no state is kept anywhere else.
 *
 * Build: tools/build_code_space.py (arm-none-eabi-gcc, linked with single_screen_arena.ld where it places the block);
 * the game functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define MODE 0x1A20                 /* scene: the mode shown (0 the choice, 1-4 the panels) */
#define REQUEST 0x1A24              /* ... the mode asked for: the game applies it when it differs from MODE */
#define SET 0xF4                    /* ... the weapon set (0-4) */
#define TIMER 0x120                 /* ... the countdown (float, seconds left) */
#define PRESSED 0x1B48              /* ... the touch list's pressed pane: index + 1 */
#define FOCUS 0x1B39                /* ... the cursor: 0 the weapon choice, 1-4 a button (padding of the touch list) */
#define STAMP 0x1B3A                /* ... the high half of the countdown at the last look (padding too) */
#define PAD_PRESSED 0x348           /* the pad object: the GUI keys pressed this frame */
#define BUTTONS 4
#define SETS 5
#define FIRST_BUTTON_RESULT 5       /* a button's result at PRESSED: 5 + its number (indices 5-8, plus one) */

#define KEY_UP 0x01u
#define KEY_DOWN 0x02u
#define KEY_LEFT 0x04u
#define KEY_RIGHT 0x08u
#define KEY_A 0x10u
#define KEY_B 0x20u
#define KEYS 0xFFFFu                /* the game's own mask on the pad word */

#define SOUND_CANCEL 2              /* the game's sounds (FUN_0031294c(*sound control, id)) */
#define SOUND_CURSOR 4

extern u8 *pad_control;             /* the pad object (its variable) */
extern u8 *sound_control;           /* the sound control (its variable) */
extern const u8 single_screen_arena_up[];   /* the block single_screen_arena_up, the patcher's: a button per weapon set */
u32 arena_touch_original(u8 *scene);        /* FUN_0065178c: 1 when a touch left a result */
void arena_pad_original(u8 *scene);         /* FUN_00650c44 */
void sound_play(u8 *control, u32 sound);    /* FUN_0031294c */

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define H(p, off) (*(volatile u16 *)((p) + (off)))
#define B(p, off) (*(volatile u8 *)((p) + (off)))

static volatile u32 *pad_word(void)
{
    u8 *pad = pad_control;
    return pad ? (volatile u32 *)(pad + PAD_PRESSED) : 0;
}

static void play(u32 sound)
{
    if (sound_control)
        sound_play(sound_control, sound);
}

/* The cursor moves to `to`, with the game's cursor sound. */
static void move(u8 *scene, u32 to)
{
    B(scene, FOCUS) = to;
    play(SOUND_CURSOR);
}

__attribute__((used)) u32 arena_touch(u8 *scene)
{
    u32 touched = arena_touch_original(scene);
    u32 stamp = W(scene, TIMER) >> 16, focus = B(scene, FOCUS);
    if (stamp > H(scene, STAMP) || focus > BUTTONS)
        focus = 0;
    H(scene, STAMP) = stamp;
    B(scene, FOCUS) = focus;
    volatile u32 *pad = pad_word();
    if (touched || !pad)
        return touched;
    u32 keys = *pad & KEYS, mode = W(scene, MODE);
    if (mode) {
        if (!(keys & KEY_B))
            return 0;
        W(scene, REQUEST) = 0;
        B(scene, FOCUS) = mode <= BUTTONS ? mode : 0;
        play(SOUND_CANCEL);
        return 1;
    }
    if (!focus) {
        if (keys & KEY_UP) {
            u32 set = W(scene, SET), button = single_screen_arena_up[set < SETS ? set : SETS - 1];
            if (button >= 1 && button <= BUTTONS)
                move(scene, button);
        }
        return 0;
    }
    if (keys & KEY_A) {
        W(scene, PRESSED) = FIRST_BUTTON_RESULT + focus;
        return 1;
    }
    if ((keys & KEY_LEFT) && focus > 1)
        move(scene, focus - 1);
    else if ((keys & KEY_RIGHT) && focus < BUTTONS)
        move(scene, focus + 1);
    else if (keys & KEY_DOWN)
        move(scene, 0);
    return 0;
}

__attribute__((used)) void arena_pad(u8 *scene)
{
    volatile u32 *pad = pad_word();
    if (!pad || W(scene, MODE) || !B(scene, FOCUS)) {
        arena_pad_original(scene);
        return;
    }
    u32 saved = *pad;
    *pad = saved & ~(KEY_LEFT | KEY_RIGHT);
    arena_pad_original(scene);
    *pad = saved;
}

__attribute__((used)) u32 arena_frame(u32 mode, u8 *scene)
{
    u32 focus = B(scene, FOCUS);
    return mode == 0 && focus >= 1 && focus <= BUTTONS ? focus - 1 : mode - 1;
}

/* The hook of 0x653064, `sub r0, r0, #1` (r0 the mode, r6 the scene; r1 the table, r5 and r7 literals the code after it
 * reads): the index the frame's table is read at. r1-r4, ip and lr are kept; six registers keep the stack 8-aligned. */
__attribute__((naked, section(".text.entry"))) void arena_frame_hook(void)
{
    __asm__ volatile(
        "push   {r1-r4, r12, lr}\n\t"
        "mov    r1, r6\n\t"
        "bl     arena_frame\n\t"
        "pop    {r1-r4, r12, lr}\n\t"
        "bx     lr\n\t");
}
