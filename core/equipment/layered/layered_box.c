/* Layered Gear from the item box: a unit of the block
 * layered_selector.
 *
 * Every item box FUN_009ec82c opens gets a last line, Layered Gear: the box's line count (menu + 0xA) one more, the line
 * itself in layered_box.line. Its panes are copies the layout holds hidden (box_row.py): at the line's place, and a
 * frame one row taller when the game's has no room for it; the box menu's commands (FUN_00a55a20, run as the cursor
 * moves and when the menu is built) show them, and the line's help. A on the line opens the Layered Gear screens' entry
 * in a state of the box's own, BOX_STATE, equip only (layered_ui.from_box: layered_selector.c); B from the entry comes
 * back to the box's menu on the line.
 *
 * Hooks (ARM, below; layered_equipment.py BOX_CALLS, BOX_JUMPS, BOX_WORDS):
 *   layered_box_opened  0x9EC8B0  "bl FUN_00589bf0", FUN_009ec82c after the count's store: the line added
 *   layered_box_other   0xA20690  "strb r0, [r4, #0xA]", FUN_00a20634 (the menu set up for another screen): no line
 *   layered_box_key     0xA4672C  "cmp sb, #7", FUN_00a46694's A: the line takes the switch's default, which the word
 *                       at 0xA4673C sends where lines 0 and 1 go (the choice taken: return 1)
 *   layered_box_pick    0x9CA0B0  "ldrsb r0, [r4, #6]", FUN_009c9ee0's choice: the line -> 7, the switch's default
 *   layered_box_open    0x9CA0C0  "b 0x9CA31C", that default: the line opens the screens
 *   layered_box_state   0x9C9F64  "b 0x9CA580", FUN_009c9ee0's states past the game's: BOX_STATE runs the screens
 *   layered_box_out     0xA9A398  "bx lr", FUN_00a9a38c's default, the box's way out of a state (back to its menu, or
 *                       closed by force): BOX_STATE's takes the screens down (layered_box_down)
 *   layered_box_menu    0x9FD8C8  "bl FUN_00a55a20", the box menu's commands: then the line's panes and help
 *
 * Two blocks: this file is resident (a unit of layered_selector): the
 * stubs, which stay where the game's hooks point, the line's place and the line count's store. The line's panes and
 * help (layered_box_commands) and the screens' setup and teardown (box_screens_open, box_screens_close) are layered_menu.c,
 * in the town block layered_town: layered_box_menu and the stubs below call it, and layered_box_entry, layered_box_frame
 * and layered_box_down.
 */

#include "layered.h"

GAME void box_frame_setup(u32 frame, u32 box);       /* FUN_00589bf0 */

struct box_line_state { u8 line, pad[3]; };   /* the variable layered_box */
_Static_assert(sizeof(struct box_line_state) == 4, "layered_box size (game/executable/blocks.py)");
extern struct box_line_state layered_box;

/* Our line's place in a box of that kind, with that many lines before it; 0 when the layout has none there. */
static const struct fg_box_line *place_of(u32 kind, u32 line)
{
    for (u32 i = 0; i < BOX_PLACES; i++)
        if (BR->lines[i].line == line && BR->lines[i].kind == (kind != 0))
            return &BR->lines[i];
    return 0;
}

/* The line of this menu, or 0: set by its opener, and still the last of its lines. */
const struct fg_box_line *box_line_of(const u8 *menu)
{
    u32 line = layered_box.line;
    if (line == NO_LINE || menu[MENU_COUNT] != line + 1)
        return 0;
    return place_of(menu[MENU_KIND], line);
}

ARM u32 layered_box_is_line(const u8 *menu, u32 line)
{
    return box_line_of(menu) && line == layered_box.line;
}

/* FUN_009ec82c, after the line count's store: our line after the game's, where the layout has a place for it. */
ARM void layered_box_opened(u32 frame, u32 box)
{
    u8 *menu = (u8 *)frame - MENU_FRAME;
    box_frame_setup(frame, box);
    u32 count = menu[MENU_COUNT];
    layered_box.line = NO_LINE;
    if (place_of(menu[MENU_KIND], count)) {
        layered_box.line = count;
        menu[MENU_COUNT] = count + 1;
    }
}

/* ----- the hooks ------------------------------------------------------------------------------------------------ */

__asm__(
    "   .section .text.layered_hooks, \"ax\", %progbits\n"
    "   .arm\n"
    "   .global layered_box_other, layered_box_key, layered_box_pick, layered_box_open, layered_box_state\n"
    "   .global layered_box_out, layered_box_menu\n"
    /* FUN_009fd87c's call of the box menu's commands (r0 the scene, r1 the menu): on to the town block's, with the game's
       return address (it is a call: r12 is free) */
    "layered_box_menu:\n"
    "   ldr     r12, =layered_box_commands\n"
    "   bx      r12\n"
    /* FUN_00a9a38c's default (its `bx lr`): r0 the scene, r1 the menu, r2 its state; ours takes the screens down */
    "layered_box_out:\n"
    "   cmp     r2, #" STR(BOX_STATE) "\n"
    "   bxne    lr\n"
    "   b       layered_box_down\n"
    /* FUN_00a20634's count store (r0 the count, r4 the menu; the function returns next): the store, and no line */
    "layered_box_other:\n"
    "   strb    r0, [r4, #" STR(MENU_COUNT) "]\n"
    "   ldr     r12, =layered_box\n"
    "   mvn     r0, #0\n"
    "   strb    r0, [r12]\n"
    "   ldrb    r0, [r4, #" STR(MENU_COUNT) "]\n"
    "   bx      lr\n"
    /* FUN_00a46694's A on the lines' column: sb the line, r4 the menu -> the flags of "cmp sb, #7", the line as 7 */
    "layered_box_key:\n"
    "   push    {r0-r3, r12, lr}\n"
    "   mov     r0, r4\n"
    "   mov     r1, sb\n"
    "   bl      layered_box_is_line\n"
    "   cmp     r0, #0\n"
    "   movne   sb, #7\n"
    "   pop     {r0-r3, r12, lr}\n"
    "   cmp     sb, #7\n"
    "   bx      lr\n"
    /* FUN_009c9ee0's choice taken: r4 the menu -> r0 the line, 7 for ours */
    "layered_box_pick:\n"
    "   push    {r1-r4, r12, lr}\n"
    "   mov     r0, r4\n"
    "   ldrsb   r1, [r4, #" STR(MENU_LINE) "]\n"
    "   bl      layered_box_is_line\n"
    "   cmp     r0, #0\n"
    "   ldrsb   r0, [r4, #" STR(MENU_LINE) "]\n"
    "   movne   r0, #7\n"
    "   pop     {r1-r4, r12, lr}\n"
    "   bx      lr\n"
    /* the choice's default case: r0 the line (7: ours), r4 the menu, r5 the scene; on to the game's end of the choice */
    "layered_box_open:\n"
    "   cmp     r0, #7\n"
    "   bne     box_menu_done\n"
    "   mov     r0, r5\n"
    "   mov     r1, r4\n"
    "   bl      layered_box_entry\n"
    "   b       box_menu_done\n"
    /* a state past the game's: r1 the state, r4 the menu, r5 the scene; r0 to the states' end (2: back to the menu) */
    "layered_box_state:\n"
    "   mov     r0, #0\n"
    "   cmp     r1, #" STR(BOX_STATE) "\n"
    "   bne     box_states_done\n"
    "   mov     r0, r5\n"
    "   mov     r1, r4\n"
    "   bl      layered_box_frame\n"
    "   b       box_states_done\n"
    "   .ltorg\n"
);
