/* The talk windows at the HUD size only in a quest, for the HUD size option (interface/hud/code_patch.py
 * patch_talk_size).
 *
 * The talk windows (ui005_kaiwa00, 01, 02, 04 of core_common.arc) are one layout for the towns, the Gathering Hall and
 * the quests, loaded once into the GUI's layout manager. The data side (build.HUD_IN_QUEST) puts every pane of each
 * window under one null, <group>_frame, at (0, 0) and scale 1, so the file draws them at full size. Every frame this
 * block gives each such null the HUD size while the game is in a quest: the null's position (x, y) and scale (s, s)
 * of talk_size_data, the scaled layout's shift towards the window's corner; in any other game mode (0, 0) and 1.
 *
 * Hook: sMhMain::frame (FUN_00af52a0) calls FUN_005a805c(), the GUI's per-frame update of its pop-up groups, once a
 * frame in every scene; that call is a `bl` to talk_size, which makes it and then places the nulls. The game mode is
 * the game control's byte +0x2B (1 a quest, 5 its results, 2 the Gathering Hall); bit n of talk_size_data.modes says
 * mode n is a quest's (curated tuning.json, interface.talk_window_quest_modes).
 *
 * Runtime structures: the GUI object's + 0x100 is the layout manager, whose
 * + 0x154 / + 0x160 are its group list and length; a group's + 0x00 is its name hash and + 0x08 its first pane; a
 * pane's + 0x00 is its name hash, + 0x08 its data and + 0x0C its redraw node; a null's data has the position at
 * + 0x00 and the scale at + 0x10. A value is written only when its bits differ, then the pane is redrawn (node
 * + 0x12 = 3, else FUN_00ae6bcc), as the game GUI engine does.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with talk_size.ld where it places the block); the
 * game's functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;

#define TALKS 4

struct talk {
    u32 group;          /* the window's name hash */
    u32 wrapper;        /* its null's, <group>_frame */
    u32 x, y, scale;    /* floats: the null's place and scale in a quest */
};

struct talk_size_data {
    u32 modes;          /* bit n: game mode n is a quest's */
    struct talk talks[TALKS];
};

extern const struct talk_size_data talk_size_data;
extern u32 gui_control;
extern const u8 *game_control;
extern void gui_popup_update(void);     /* FUN_005a805c */
extern void pane_redraw(u32 group, u32 pane);  /* FUN_00ae6bcc */

#define W(p, off) (*(u32 *)((p) + (off)))
#define ONE 0x3f800000u                 /* 1.0f */
#define GAME_MODE 0x2B

static int in_quest(void)
{
    const u8 *game = game_control;
    return game && game[GAME_MODE] < 32 && (talk_size_data.modes >> game[GAME_MODE] & 1);
}

static int set(u32 data, u32 offset, u32 value)
{
    if (W(data, offset) == value)
        return 0;
    W(data, offset) = value;
    return 1;
}

static void place(u32 group, const struct talk *talk, int quest)
{
    u32 pane = W(group, 8);
    if (!pane || W(pane, 0) != talk->wrapper)
        return;     /* not our null: the file was not made by the HUD size option */
    u32 data = W(pane, 8);
    u32 scale = quest ? talk->scale : ONE;
    int changed = set(data, 0x00, quest ? talk->x : 0);
    changed |= set(data, 0x04, quest ? talk->y : 0);
    changed |= set(data, 0x10, scale);
    changed |= set(data, 0x14, scale);
    if (!changed)
        return;
    u32 node = W(pane, 0x0C);
    if (node)
        *(u8 *)(node + 0x12) = 3;
    else
        pane_redraw(group, pane);
}

__attribute__((used, section(".text.entry"))) void talk_size(void)
{
    gui_popup_update();
    u32 gui = gui_control, manager = gui ? W(gui, 0x100) : 0;
    if (!manager)
        return;
    u32 slots = W(manager, 0x154), count = W(manager, 0x160);
    int quest = in_quest();
    for (u32 i = 0; i < count; i++) {
        u32 group = W(slots, i * 4);
        if (!group)
            continue;
        for (int t = 0; t < TALKS; t++)
            if (W(group, 0) == talk_size_data.talks[t].group)
                place(group, &talk_size_data.talks[t], quest);
    }
}
