/* Hold A (option hold_a; gameplay/hold_a/hold_a.py): holding A repeats it where the game
 * wants a press for every thing, and in the two panels that take items one at a time A moves on to the next item.
 *
 * The game's own button repeat is the GUI set's: FUN_006949d4 fills the pad object's (*pad_control) word +0x35C with
 * the held buttons (A is bit 0x10 there) about 24 ticks after the held set stopped changing, then about every 4
 * ticks, and the menus' cursors already read `pressed | repeat` (+0x348 | +0x35C). Nothing below counts time.
 *
 * Three entries, each a `bl` of the game replaced by a `bl` to this block that makes the original call:
 *   hold_a_field(hunter)             0xB1D08C in FUN_00b1cdf0, the local hunter's input update (once per frame, after the
 *       pad was copied into the hunter's pressed / held words p + 0x3A4 / 0x3A0, p = *(hunter + 0xE30)), instead of the
 *       call to FUN_00b28f54 (item mode with L). In a quest, with the weapon sheathed (the bit 0 of *(hunter + 0xA29C)
 *       + 0xE8, which FUN_00b169bc tests to choose the sheathed A: draw and attack), A held and L not held, the
 *       circle pad not tilted and A's repeat tick this frame, it sets A (0x20) in the pressed words (p + 0x3A4 and the
 *       halfwords at p + 0x3AC / 0x3B4), so FUN_00b169bc and the gathering, picking up, mining and carving that read
 *       them see a new press.
 *   hold_a_rewards(scene, ...)       0x65CAA4 and 0x65CABC in FUN_0065c5b8, instead of the calls to FUN_00accd24 (the
 *       quest result scene, scene = *0xEF32B4: +4 the page, +5 the page's step, the cursor column +0x1CA and row
 *       +0x1CB of an 8 x 6 grid of {u16 item, s16 count} at +0x4A (page 1) or +0x10A). On the item pages' "Take Items"
 *       and "Send to Item Box" steps (+5 = 2 and 3) the A repeat tick is put into the pad's pressed word (+0x348) for
 *       the call and taken out after it; when the cell the cursor was on is empty afterwards (the whole stack was
 *       taken) and the step is the same, the cursor goes to the next cell with an item, in row order, wrapping.
 *   hold_a_claim(panel)              0xA0A350 and 0x9B74E4, instead of the calls to FUN_005e5cb8 (the Wyporium's "Claim
 *       Items" panel, panel = *0xED2E40: +0x5C the step, 1 "Take Items" and 2 "Send to Item Box", the cursor column
 *       +0x5D (byte) and row +0x6E (halfword), the cells' index +0x6C = row * columns + column, columns +0x94, cells +0x88,
 *       the cells {u16 item, s16 count} at *(panel + 0x80)). The same as the rewards, on those two steps.
 * Nothing else changes: the swap and exit menus always need a real press.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with hold_a.ld where it places the block); the game
 * functions and the pad's variable are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef int s32;
typedef unsigned short u16;
typedef short s16;
typedef unsigned char u8;
typedef signed char s8;

/* The pad object */
#define PAD_PRESSED  0x348      /* u32: the GUI buttons pressed this frame */
#define PAD_REPEAT   0x35C      /* u32: the GUI buttons held and repeating this frame (about 24 ticks, then every 4) */
#define GUI_A        0x10

/* The hunter */
#define H_PLAYER     0xE30      /* the hunter's player record p */
#define H_WORK       0xA29C     /* pw */
#define W_STATE      0xE8       /* pw: bit 0 the weapon is drawn */
#define P_HELD       0x3A0      /* u32: the held buttons, the game layout */
#define P_PRESSED    0x3A4      /* u32: the pressed buttons */
#define P_PRESSED16  0x3AC      /* u16 copies of the pressed buttons */
#define P_PRESSED16B 0x3B4
#define P_STICK      0x3C4      /* u16: how far the circle pad is tilted */
#define STICK_MOVING 0x32       /* FUN_00b41e44: a tilt from 0x32 on is walking */
#define GAME_A       0x20
#define GAME_L       0x8
#define GAME_MODE    0x2B       /* sGameControl: 1 in a quest */
#define MODE_QUEST   1

/* The quest result scene */
#define S_PAGE       4
#define S_STEP       5
#define S_REDRAW     9
#define S_CURSOR_COL 0x1CA
#define S_CURSOR_ROW 0x1CB
#define S_CELLS_1    0x4A
#define S_CELLS_2    0x10A
#define S_COLUMNS    8
#define S_CELLS      48
#define STEP_TAKE    2
#define STEP_SEND    3

/* The claim panel */
#define C_STEP       0x5C
#define C_COL        0x5D
#define C_INDEX      0x6C
#define C_ROW        0x6E
#define C_CELLS      0x80
#define C_COUNT      0x88
#define C_COLUMNS    0x94

extern u8 *const pad_control;           /* the variable holding the pad object */
extern u8 *const game_control;          /* the variable holding sGameControl */

/* Game functions */
void hunter_item_mode(u8 *hunter);                          /* FUN_00b28f54 */
s32 hunter_is_local(u8 *hunter);                            /* FUN_00d04fbc: the hunter this console plays */
u32 result_scene(u8 *scene, u32 b, u32 c);                  /* FUN_00accd24 */
u32 claim_scene(u8 *panel);                                 /* FUN_005e5cb8 */

#define U32(p, off) (*(volatile u32 *)((p) + (off)))
#define U16(p, off) (*(volatile u16 *)((p) + (off)))
#define S16(p, off) (*(volatile s16 *)((p) + (off)))
#define U8(p, off)  (*(volatile u8 *)((p) + (off)))

/* A's repeat tick of this frame, and A not already pressed */
static u32 a_repeats(const u8 *pad)
{
    return pad && (U32(pad, PAD_REPEAT) & GUI_A) && !(U32(pad, PAD_PRESSED) & GUI_A);
}

/* The cell after `from` (wrapping) with an item, or -1 */
static s32 next_item(const u8 *cells, s32 count, s32 from)
{
    s32 at = from;
    for (s32 step = 1; step < count; step++) {
        at = at + 1 < count ? at + 1 : 0;
        if (U16(cells, at * 4))
            return at;
    }
    return -1;
}

/* index / columns and index % columns, without the library's division (the block links with no library) */
static void split(s32 index, s32 columns, s32 *row, s32 *column)
{
    s32 r = 0;
    while (index >= columns) {
        index -= columns;
        r++;
    }
    *row = r;
    *column = index;
}

__attribute__((used, section(".text.entry"))) void hold_a_field(u8 *hunter)
{
    u8 *pad = pad_control, *game = game_control, *p = (u8 *)U32(hunter, H_PLAYER), *pw = (u8 *)U32(hunter, H_WORK);
    if (pad && game && p && pw && U8(game, GAME_MODE) == MODE_QUEST && hunter_is_local(hunter)
        && !(U32(pw, W_STATE) & 1) && (U32(p, P_HELD) & GAME_A) && !(U32(p, P_HELD) & GAME_L)
        && U16(p, P_STICK) < STICK_MOVING && a_repeats(pad)) {
        U32(p, P_PRESSED) |= GAME_A;
        U16(p, P_PRESSED16) |= GAME_A;
        U16(p, P_PRESSED16B) |= GAME_A;
    }
    hunter_item_mode(hunter);
}

__attribute__((used, section(".text.entry"))) u32 hold_a_rewards(u8 *scene, u32 b, u32 c)
{
    u8 *pad = pad_control;
    u32 page = scene ? U8(scene, S_PAGE) : 0, step = scene ? U8(scene, S_STEP) : 0, injected = 0;
    u8 *cells = scene ? scene + (page == 1 ? S_CELLS_1 : S_CELLS_2) : 0;
    s32 at = -1;
    if ((page == 1 || page == 2) && (step == STEP_TAKE || step == STEP_SEND)) {
        s32 column = (s8)U8(scene, S_CURSOR_COL), row = (s8)U8(scene, S_CURSOR_ROW);
        if (column >= 0 && column < S_COLUMNS && row >= 0 && column + row * S_COLUMNS < S_CELLS
            && U16(cells, (column + row * S_COLUMNS) * 4))
            at = column + row * S_COLUMNS;
        if (a_repeats(pad)) {
            U32(pad, PAD_PRESSED) |= GUI_A;
            injected = 1;
        }
    }
    u32 result = result_scene(scene, b, c);
    if (injected)
        U32(pad, PAD_PRESSED) &= ~GUI_A;
    if (at >= 0 && U8(scene, S_PAGE) == page && U8(scene, S_STEP) == step && !U16(cells, at * 4)) {
        s32 next = next_item(cells, S_CELLS, at);
        if (next >= 0) {
            U8(scene, S_CURSOR_COL) = next % S_COLUMNS;
            U8(scene, S_CURSOR_ROW) = next / S_COLUMNS;
            U8(scene, S_REDRAW) = 1;
        }
    }
    return result;
}

__attribute__((used, section(".text.entry"))) u32 hold_a_claim(u8 *panel)
{
    u8 *pad = pad_control;
    u32 step = panel ? U8(panel, C_STEP) : 0, injected = 0;
    u8 *cells = panel ? (u8 *)U32(panel, C_CELLS) : 0;
    s32 columns = panel ? S16(panel, C_COLUMNS) : 0, count = panel ? S16(panel, C_COUNT) : 0, at = -1;
    if (cells && (step == 1 || step == 2) && columns > 0) {
        s32 column = U8(panel, C_COL), row = S16(panel, C_ROW), index = row * columns + column;
        if (column < columns && row >= 0 && index < count && U16(cells, index * 4))   /* the game's own index */
            at = index;
        if (a_repeats(pad)) {
            U32(pad, PAD_PRESSED) |= GUI_A;
            injected = 1;
        }
    }
    u32 result = claim_scene(panel);
    if (injected)
        U32(pad, PAD_PRESSED) &= ~GUI_A;
    if (at >= 0 && U8(panel, C_STEP) == step && !U16(cells, at * 4)) {
        s32 next = next_item(cells, count, at);
        if (next >= 0) {
            s32 row, column;
            split(next, columns, &row, &column);
            U8(panel, C_COL) = column;
            S16(panel, C_ROW) = row;
            S16(panel, C_INDEX) = next;
        }
    }
    return result;
}
