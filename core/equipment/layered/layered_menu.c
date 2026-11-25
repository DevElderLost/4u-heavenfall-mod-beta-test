/* Layered gear's screens in town (option layered_equipment): the main
 * source of the block layered_town, with layered_forge.c and screen_kit.c. The Smithy's entry and its menus, the cats'
 * names, the help line, and the item box's line's panes and screens; the forge-style screens themselves are
 * layered_forge.c. Only town runs them, and only they read the block layered_rules.
 *
 * Nothing here is a hook: the resident block layered_selector (and layered_box.c, its unit) keeps every stub the game
 * is pointed at, and each stub calls one of the functions below by its name (the resident-to-town calls, listed):
 *   layered_menu_names    from layered_menu_drawn     menu 18's cats' names, once drawn
 *   layered_open          from layered_smithy_open    the Smithy's Layered Gear line chosen
 *   layered_update        from layered_smithy_update  every frame of the Smithy's state 3 (and of the box's BOX_STATE)
 *   layered_box_commands  from layered_box_menu       the item box menu's commands, then the line's panes and help
 *   layered_box_entry     from layered_box_open       the item box's line chosen
 *   layered_box_frame     from layered_box_state      every frame of the box's BOX_STATE
 *   layered_box_down      from layered_box_out        the box's way out of BOX_STATE
 * Resident code is called by address (RESIDENT: a long call); build: tools/build/build_code_space.py (LAYERED_TOWN).
 */

#include "layered.h"

GAME u32 menu_cursor_init(u32 obj, void *cursor, u32 count, u32 rows, u32 disabled, u32 a_sound, u32 v_sound,
                          u32 h_sound);                                /* FUN_009bc954 */
GAME u32 menu_cursor_update(u32 obj, void *cursor, u32 extra);         /* FUN_009bc9b4: 1 A, 2 B */

extern const u8 menu_line_texts[];
#define STATE_ROW 0x21           /* row of the Smithy menu's cursor */
#define CLASS_ROWS 7
#define LINE_TEXTS menu_line_texts               /* per line (7: the cursor's copy): its first text pane */
#define MENU_TEXTS 0xC           /* the facility menu's panes (FUN_00a528e0): r6 = obj + 0x98D0 holds (a, node) refs */
#define CURSOR_LINE 7
#define NAME_SLOT 0              /* the text renderer's string slot the money uses too (FUN_00c0da68), shown by a
                                    number node (2, 100): our E_makeshop message msg_counter (Common's 0 adds "z") */
#define CAT_NAME 12              /* a Felyne's name at the start of its record: UTF-16, at most this many characters */

/* ----- the entry list, the classes, the cats --------------------------------------------------------------- */

static void open_cursor(u32 obj, u32 count, u32 rows, u32 index)
{
    struct cursor *c = &layered_ui.cursor;
    menu_cursor_init(obj, c, count, rows, 0, SOUND_DECIDE, SOUND_CURSOR, SOUND_PAGE);
    c->col = small_divide(index, rows);
    c->row = index - c->col * rows;
    c->index = index;
    *(u8 *)(obj + OBJ_SHOWN) = 0xFE;
}

/* Menu 18 shows `count` lines of `messages`, the cursor on `row`. */
static void show_lines(u32 obj, u32 level, const u16 *messages, u32 count, u32 row)
{
    struct ui *u = &layered_ui;
    u->level = level;
    u->count = count;
    for (u32 i = 0; i < count; i++) {
        u->lines[i][0] = MAKESHOP;
        u->lines[i][1] = messages[i];
    }
    open_cursor(obj, count, count, row);
}

/* The entry's last line, Relics: below Felyne, which is there with the Felynes' models in the run. */
static u32 relics_line(void)
{
    return felyne_looks_data.total ? 3 : 2;
}

/* Weapons, Armor, Felyne (with the Felynes' models in the run) and Relics; the normal screens from here. */
static void show_entry(u32 obj, u32 row)
{
    u16 messages[4] = {D->msg_weapons, R->messages[MSG_ARMOR], felyne_looks_data.msg_felynes, 0};
    u32 last = relics_line();
    messages[last] = R->msg_relics;
    layered_ui.relics = 0;
    show_lines(obj, ENTRY, messages, last + 1, row);
}

/* Relics' Weapons and Armor: the screens from here list the relics alone (layered_forge.c, on_screen). */
static void show_relics(u32 obj, u32 row)
{
    u16 messages[2] = {D->msg_weapons, R->messages[MSG_ARMOR]};
    layered_ui.relics = 1;
    show_lines(obj, RELICS, messages, 2, row);
}

/* The two active cats: blank lines, their names written once the menu is drawn (layered_menu_names). */
static void show_cats(u32 obj, u32 row)
{
    u16 blank[FELYNE_MAX_ACTIVE] = {D->msg_blank, D->msg_blank};
    show_lines(obj, CATS, blank, FELYNE_MAX_ACTIVE, row);
}

static void show_classes(u32 obj)
{
    layered_ui.level = CLASSES_MENU;
    open_cursor(obj, CLASSES, CLASS_ROWS, layered_ui.class_index);
}

/* The menu of the level shown, at the cursor. */
static u32 menu_shown(void)
{
    struct ui *u = &layered_ui;
    return u->level == CLASSES_MENU ? WEAPON_MENU + u->cursor.col : LAYERED_MENU;
}

/* The Felyne line chosen: none active stays here, one opens his screen, two ask which. */
static void open_felynes(u32 obj)
{
    const u8 *cats[FELYNE_MAX_ACTIVE];
    u32 count = felyne_active(cats);
    felyne_ui.cat = 0;
    if (!count)
        play(SOUND_ERROR);
    else if (count == 1)
        forge_open(obj, M_FELYNE);
    else
        show_cats(obj, 0);
}

static void choose(u32 obj, u32 index)
{
    struct ui *u = &layered_ui;
    if (u->level == ENTRY || u->level == RELICS) {
        if (index == 0)
            show_classes(obj);
        else if (index == 1)
            forge_open(obj, M_ARMOR);
        else if (index == relics_line())
            show_relics(obj, 0);
        else
            open_felynes(obj);
    } else if (u->level == CATS) {
        felyne_ui.cat = index;
        forge_open(obj, M_FELYNE);
    } else {
        u->class_index = index;
        forge_open(obj, M_WEAPON);
    }
}

static void back(u32 obj, u8 *state)
{
    struct ui *u = &layered_ui;
    if (u->level == CATS) {
        show_entry(obj, 2);
    } else if (u->level == RELICS) {
        show_entry(obj, relics_line());
    } else if (u->level == CLASSES_MENU) {
        if (u->relics)
            show_relics(obj, 0);
        else
            show_entry(obj, 0);
    } else {
        if (u->from_box) {
            u->box_state |= BOX_LEAVING;                /* the box's menu again (layered_box_frame, layered_box_down) */
        } else {
            state[0] = 1;  /* the Smithy's menu again, on our line */
            facility_menu_set(obj, u->smithy_menu, u->smithy_row, 0xFF);
        }
        if (*(u32 *)(obj + OBJ_HUNTER))
            hunter_reload(*(u32 *)(obj + OBJ_HUNTER), 0);   /* the real hunter wears the looks chosen */
        layered_net_state_left();                           /* and the other players see them */
        if (felyne_ui.dirty && felyne_looks_data.total)
            felyne_refresh(obj);                            /* and the cats in the area theirs */
    }
}

void forge_back_to_menu(u32 obj)
{
    struct ui *u = &layered_ui;
    const u8 *cats[FELYNE_MAX_ACTIVE];
    if (u->mode == M_WEAPON)
        show_classes(obj);
    else if (u->mode == M_FELYNE && felyne_active(cats) > 1)
        show_cats(obj, felyne_ui.cat);
    else if (u->relics)
        show_relics(obj, 1);
    else
        show_entry(obj, u->mode == M_FELYNE ? 2 : 1);
    /* The game shows ui401's groups again only on a change from no menu: open_cursor's redraw value would skip them. */
    *(u8 *)(obj + OBJ_SHOWN) = NO_MENU;
    facility_menu_set(obj, menu_shown(), u->cursor.row, 0xFF);
}


/* Facility menu line `line` shows a cat's name, by the text renderer's string slot and our message of that slot alone
   (as the counter): a name is no message of the game's. */
static void name_line(u32 menu, u32 line, const u8 *cat)
{
    struct ref *pane = (struct ref *)(menu + MENU_TEXTS) + LINE_TEXTS[line];
    u16 name[CAT_NAME + 1];
    u32 length = 0;
    while (length < CAT_NAME && (cat[2 * length] || cat[2 * length + 1])) {
        name[length] = cat[2 * length] | cat[2 * length + 1] << 8;
        length++;
    }
    name[length] = 0;
    text_slot(NAME_SLOT, name, length);
    text_lobby(pane, MAKESHOP, D->msg_counter);
    text_show(*(u32 *)(pane->node + 8), 1);
    u8 *node = *(u8 **)(pane->node + 0x14), *dirty = *(u8 **)(node + 0xC);
    if (dirty)
        dirty[0x12] = 3;
    else
        pane_redraw(pane->group, (u32)node);
}

/* layered_menu_drawn: menu 18 drawn (r6 = obj + 0x98D0): on the cats' level each line and the cursor's copy show their
   cat's name. */
ARM void layered_menu_names(u32 menu)
{
    const u8 *cats[FELYNE_MAX_ACTIVE];
    if (layered_ui.level != CATS)
        return;
    u32 count = felyne_active(cats), row = *(u8 *)(menu + DRAWN_MENU + 1);
    for (u32 i = 0; i < count; i++)
        name_line(menu, i, cats[i]);
    if (row < count)
        name_line(menu, CURSOR_LINE, cats[row]);
}

/* layered_smithy_open: the Smithy menu's Layered Gear line was chosen. */
ARM void layered_open(u32 obj, u8 *state)
{
    struct ui *u = &layered_ui;
    u->smithy_menu = *(u8 *)(obj + OBJ_MENU);
    u->smithy_row = state[STATE_ROW];
    u->from_box = 0;             /* the Smithy's screens sell, */
    u->box_state = 0;            /* and nothing a box left behind stops their menu */
    u->refused = 0;
    felyne_ui.dirty = 0;
    state[0] = LAYERED_STATE;
    play(SOUND_DECIDE);
    show_entry(obj, 0);
    facility_menu_set(obj, LAYERED_MENU, 0, 0xFF);
}

/* The help line: of the screen's mode, or of the entry's levels. */
u32 help_message(void)
{
    struct ui *u = &layered_ui;
    const u8 *cats[FELYNE_MAX_ACTIVE];
    if (u->level == FORGE)
        return R->messages[u->mode == M_WEAPON ? MSG_HELP_WEAPONS : u->mode == M_ARMOR ? MSG_HELP_ARMOR : MSG_HELP_FELYNE];
    if (u->refused)
        return R->msg_none[u->refused - 1];
    if (u->level == CATS)
        return felyne_looks_data.msg_choose;
    if (u->level == CLASSES_MENU || u->cursor.index == 0)
        return R->messages[MSG_HELP_WEAPONS];
    if (u->cursor.index == 1)
        return R->messages[MSG_HELP_ARMOR];
    if (u->cursor.index == relics_line())
        return R->msg_help_relics;
    return felyne_active(cats) ? R->messages[MSG_HELP_FELYNE] : felyne_looks_data.msg_none;
}

/* layered_smithy_update: every frame of the Smithy's state 3 (layered_box_frame: of the box's BOX_STATE, `state` the box
   menu). */
ARM void layered_update(u32 obj, u8 *state)
{
    struct ui *u = &layered_ui;
    if (u->level == FORGE) {
        forge_update(obj);
        return;
    }
    facility_help(1, MAKESHOP, help_message());
    u32 at = u->cursor.index;
    u32 result = menu_cursor_update(obj, &u->cursor, 0);
    if (result || u->cursor.index != at)
        u->refused = 0;          /* a refusal's help lasts until the cursor moves (choose may refuse again) */
    if (result == 2)
        back(obj, state);
    else if (result == 1)
        choose(obj, u->cursor.index);
    /* At a box, only leaving stops the menu (BOX_FRAME alone is the box's frame to bind again later); the Smithy never
       reads the box's flags */
    if (state[0] != (u->from_box ? BOX_STATE : LAYERED_STATE) || u->level == FORGE
        || (u->from_box && u->box_state & (BOX_LEAVING | BOX_DOWN)))
        return;
    facility_menu_set(obj, menu_shown(), u->cursor.row, 0xFF);
}

/* ----- from the item box (layered_box.c) ----------------------------------------------------------------------- */

#define FRAME_BOUND 0x50         /* the preview's frame widget (obj + OBJ_FRAME): 1 once FUN_0059e5d0 bound it */

/* layered_box_open: the item box's Layered Gear line was chosen (FUN_00a46694 played the decide sound, FUN_00a9a38c hid
   the box's menu); `menu` is the box menu, whose state byte the screens then run in. The facility menu is opened with
   FUN_00a5d584, which binds its panes (scene + 0x98D0) as the Smithy's first state does: a box of an area whose Smithy
   was never visited has them unbound. */
ARM void layered_box_entry(u32 obj, u8 *menu)
{
    struct ui *u = &layered_ui;
    u->from_box = 1;             /* equip only */
    u->box_state = *(u8 *)(obj + OBJ_FRAME + FRAME_BOUND) ? BOX_FRAME : 0;
    u->refused = 0;
    felyne_ui.dirty = 0;
    box_screens_open(obj);
    menu[0] = BOX_STATE;
    show_entry(obj, 0);
    facility_menu_open(obj, LAYERED_MENU, 0, 0xFF);
}

/* layered_box_state: every frame of the box's BOX_STATE: the screens, and the facility menu drawn as the Smithy's own tail
   draws it; 2 once the entry was left: the box takes the screens down (its FUN_00a9a38c: layered_box_down), then
   rebuilds its menu, the cursor still on the line. Nothing once they are down (the box closed by force keeps the state). */
ARM u32 layered_box_frame(u32 obj, u8 *menu)
{
    struct ui *u = &layered_ui;
    if (u->box_state & BOX_DOWN)
        return 0;
    layered_update(obj, menu);
    if (u->box_state & BOX_LEAVING)
        return 2;
    facility_menu_draw(obj);
    return 0;
}

/* FUN_00a9a38c, the box's way out of a state, with BOX_STATE: B on the entry, or the box closed by force (a quest, the
   network). The screens go, once. */
ARM void layered_box_down(u32 obj, u8 *menu)
{
    struct ui *u = &layered_ui;
    (void)menu;
    if (!u->from_box || u->box_state & BOX_DOWN)
        return;
    u->box_state |= BOX_DOWN;
    box_screens_close(obj);
}

/* ----- the item box's line: its panes and help --------------------------------------------------------------------- */

GAME void box_menu_update(u32 scene, u8 *menu);      /* FUN_00a55a20: the box menu's commands */

#define MENU_QUEUE 0x1D64        /* the commands of the box menu's frame: a byte each, then their words from + 8, */
#define MENU_QUEUED 0x1D8C       /* how many */
#define QUEUE_ROOM 8
#define CMD_SHOW 2               /* the menu and its frame shown (FUN_00588414) */
#define CMD_CURSOR 3             /* the cursor on its line and the line's help (FUN_00a920d0); word 1: the lines' column */
#define HELP_SHOWN 0x10
#define HELP_LINE 1              /* facility_help's kind of the box's help */

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
    const struct fg_box_line *at = box_line_of(menu);
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
ARM void layered_box_commands(u32 scene, u8 *menu)
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
