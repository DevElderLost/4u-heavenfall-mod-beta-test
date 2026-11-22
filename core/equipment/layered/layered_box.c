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
 */

#include "layered.h"

GAME void box_frame_setup(u32 frame, u32 box);       /* FUN_00589bf0 */
GAME void box_menu_update(u32 scene, u8 *menu);      /* FUN_00a55a20: the box menu's commands */

#define MENU_STATE 0             /* the box menu (scene + 0xE8B8): FUN_009c9ee0's state, */
#define MENU_KIND 2              /* the box's kind (0 the 7-row frame, else the 4-row one), */
#define MENU_LINE 6              /* the cursor's line, */
#define MENU_COLUMN 9            /* the column the cursor is in (0 the lines, 1 a line's choices), */
#define MENU_COUNT 0xA           /* the lines, */
#define MENU_FRAME 0x1D54        /* the frame object FUN_00589bf0 sets up (+0: bit HELP_SHOWN, the help line drawn), */
#define MENU_QUEUE 0x1D64        /* and the commands of the frame: a byte each, then their words from + 8, */
#define MENU_QUEUED 0x1D8C       /* how many */
#define QUEUE_ROOM 8
#define CMD_SHOW 2               /* the menu and its frame shown (FUN_00588414) */
#define CMD_CURSOR 3             /* the cursor on its line and the line's help (FUN_00a920d0); word 1: the lines' column */
#define HELP_SHOWN 0x10
#define HELP_LINE 1              /* facility_help's kind of the box's help */
#define NO_LINE 0xFF
#define BR (&D->screen.box_row)

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
static const struct fg_box_line *line_of(const u8 *menu)
{
    u32 line = layered_box.line;
    if (line == NO_LINE || menu[MENU_COUNT] != line + 1)
        return 0;
    return place_of(menu[MENU_KIND], line);
}

ARM u32 layered_box_is_line(const u8 *menu, u32 line)
{
    return line_of(menu) && line == layered_box.line;
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

/* ----- the line's panes ---------------------------------------------------------------------------------------- */

static void sprite_shown(u32 group, u32 hash, u32 shown)
{
    struct ref r;
    u32 *sprite = kit_sprite(&r, group, hash);
    if (!sprite || !(sprite[SP_FLAGS] & SP_SHOWN) == !shown)
        return;
    sprite[SP_FLAGS] ^= SP_SHOWN;
    kit_sprite_changed(&r);
}

/* A text on or off; `message` (not 0) written first: the game's rows keep the one the box's build gave them. */
static void text_shown(u32 group, u32 hash, u32 shown, u32 message)
{
    struct ref r;
    u32 *text = kit_text(&r, group, hash);
    if (!text)
        return;
    if (shown && message)
        text_lobby(&r, MAKESHOP, message);
    text_show((u32)text, shown);
    kit_text_changed(&r);
}

/* A row: its plate pair in `plates`, its text in `texts`. */
static void row_shown(u32 plates, u32 texts, const u32 *panes, u32 shown, u32 message)
{
    sprite_shown(plates, panes[0], shown);
    sprite_shown(plates, panes[1], shown);
    text_shown(texts, panes[2], shown, message);
}

/* The panes as the menu wants them: our row at the line, the game's row there hidden under it, our taller frame in place
   of the game's when the line is one past it; with no line, the game's alone. Hidden panes of the frame the box does
   not show cost nothing: their null is hidden. */
static void panes_for(const u8 *menu)
{
    const struct fg_box_line *at = line_of(menu);
    u32 frames = kit_group(BR->groups[0]), plates = kit_group(BR->groups[1]), texts = kit_group(BR->groups[2]);
    if (!frames || !plates || !texts)
        return;
    for (u32 kind = 0; kind < 2; kind++) {
        u32 ours = at && at->kind == kind && at->own_frame;
        for (u32 i = 0; i < 3; i++) {
            sprite_shown(frames, BR->frames[kind][0][i], !ours);
            sprite_shown(frames, BR->frames[kind][1][i], ours);
        }
    }
    for (u32 row = 0; row < BOX_GAME_ROWS; row++)
        row_shown(plates, texts, BR->rows[row], !at || at->line != row, 0);
    for (u32 i = 0; i < BOX_PLACES; i++)
        row_shown(plates, texts, BR->lines[i].panes, &BR->lines[i] == at, BR->msg_entry);
}

/* FUN_009fd87c's box menu: the game's commands of this frame (the queue stays until FUN_00a46694 clears it next frame),
   then the line's: its panes when the menu was shown, its help when the cursor came to it. */
ARM void layered_box_menu(u32 scene, u8 *menu)
{
    u32 queued = *(u32 *)(menu + MENU_QUEUED), shown = 0, cursor = 0;
    box_menu_update(scene, menu);
    if (queued > QUEUE_ROOM)
        queued = QUEUE_ROOM;
    for (u32 i = 0; i < queued; i++) {
        u32 command = menu[MENU_QUEUE + i];
        shown |= command == CMD_SHOW;
        cursor |= command == CMD_CURSOR && *(u32 *)(menu + MENU_QUEUE + 8 + 4 * i) == 1;
    }
    if (shown)
        panes_for(menu);
    if (cursor && !menu[MENU_COLUMN] && layered_box_is_line(menu, menu[MENU_LINE]) && menu[MENU_FRAME] & HELP_SHOWN)
        facility_help(HELP_LINE, MAKESHOP, D->msg_desc);
}

/* ----- the screens at a box -------------------------------------------------------------------------------------- */

GAME void facility_gui_open(u32 scene);              /* FUN_009bb2b0 */
GAME void facility_gui_close(u32 scene);             /* FUN_009bb1ac */
GAME void preview_target_make(u32 scene);            /* FUN_009c32a0 */
GAME void preview_target_drop(u32 scene);            /* FUN_009c3180 */
GAME void preview_frame_bind(u32 frame);             /* FUN_0059e5d0 */
GAME void forge_hide(u32 obj);                       /* FUN_00a1c640 */
GAME void viewport_close(u32 viewport);              /* FUN_00c00ec8 */
extern u32 camera_control;

#define LOBBY_HUNTERS 0x123C     /* lobby_hunter_loader: the lobby's hunters, one per player index */
#define GAME_PLAYER 0x2F         /* the game manager: the local player's index */
#define OBJ_TARGET_WORK 0x1894C  /* the scene: the work area FUN_009e6bb8 clears before FUN_009c32a0 */
#define TARGET_WORK_SIZE 0x1E4

/* What the Smithy's entry (FUN_009ad484) sets up that the screens use, without its blacksmith (its FUN_009bcb90 plays the
   talking NPC's motion, which a box has not): the real hunter, the Smithy's GUI (FUN_009bb2b0: ui401's, ui402's and
   ui407's panes, and ten text objects that box_screens_close frees), the preview's camera target (FUN_009c32a0 makes it
   when there is none). The box's own code never uses the Smithy's work area (scene + 0xB708) nor the target's. */
void box_screens_open(u32 obj)
{
    *(u32 *)(obj + OBJ_HUNTER) = *(u32 *)(lobby_hunter_loader + LOBBY_HUNTERS + 4 * game_control[GAME_PLAYER]);
    facility_gui_open(obj);
    layered_clear((u8 *)obj + OBJ_TARGET_WORK, TARGET_WORK_SIZE);
    preview_target_make(obj);
}

/* All of it taken down, in the order proved at the house's, the Hall's and a village's boxes: the screens and the game's
   panels, the preview's frame and view, the facility menu, the camera target (FUN_009c3180 leaves the preview hunter's
   pointer behind), the Smithy's GUI, and the box's frame bound again if it was (FUN_009bb1ac closes it). */
void box_screens_close(u32 obj)
{
    forge_shut(obj);
    forge_hide(obj);
    preview_frame_close(obj + OBJ_FRAME);
    viewport_close(camera_control);
    facility_menu_set(obj, NO_MENU, 0, 0xFF);
    facility_menu_draw(obj);
    preview_target_drop(obj);
    *(u32 *)(obj + OBJ_PREVIEW) = 0;
    facility_gui_close(obj);
    if (layered_ui.box_state & BOX_FRAME)
        preview_frame_bind(obj + OBJ_FRAME);
}

/* ----- the hooks ------------------------------------------------------------------------------------------------ */

__asm__(
    "   .section .text.layered_hooks, \"ax\", %progbits\n"
    "   .arm\n"
    "   .global layered_box_other, layered_box_key, layered_box_pick, layered_box_open, layered_box_state\n"
    "   .global layered_box_out\n"
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
