/* Single-screen mode: the players' box on the top screen (emulator only).
 *
 * In a hall with other hunters the game lists its members in `ui500` (the lobby's member list: four cards, one per
 * hunter, with the weapon icon, the name, the Hunter Rank and the quest ticket), but only while the touch menu's first
 * button has it open (hub state 0x14, which shows the group and calls FUN_00a6eea0(scene), the refresh of the four
 * cards, every frame). With the layout re-placed as four compact rows at the top left of the top screen
 * (interface/single_screen/layout/single_screen_players.py) and its screen moved to the top (interface/single_screen/executable/single_screen_multiplayer.py), this unit keeps
 * the box up while the hunter walks: it does for the free hub what the game does for the list.
 *
 * Called by the frames block's entry (single_screen_frames.c, after the frames' pass), every frame:
 *  1. nothing at all unless the game control and the lobby scene exist, the game control's byte +0x2B is 2 (the lobby:
 *     its layouts are loaded), the hub machine is set up (scene + 0x172D4: its setup binds the owners; until then
 *     scene + 0x171C0 holds whatever the heap had, a float 1.0 back from a quest), the member list's owner
 *     (*(scene + 0x171C0)) and its group (*owner) exist and the group is on the top screen (bits 14-17 of group + 0x44
 *     are *(gui + 0x245); otherwise the layout was not moved and the game's list on the touch screen is not ours to
 *     show);
 *  2. nothing while the hub machine is in state 0x13 or 0x14: the game opens, shows and refreshes its own list there
 *     (FUN_009fc5fc, FUN_00a6eea0 in the hub update), and hides it when it closes;
 *  3. WANTED is 1 when the machine is in state 2 (free walking) or 0x12 (the first button's panel), scene + 0x9788
 *     (the interaction mode: no talk, menu, box or map) and the halfword +0x97D6 (the input lock) are 0 and the hall
 *     is up: FUN_002b5ac8(game control) (+0x5D) is not 0 and FUN_002b1040() (the session's mode) is 1 or 2, the two
 *     values the game accepts to open the list (local room and online). Each is asked only after the previous held;
 *  4. WANTED and hidden: the group is shown as FUN_009fc5fc does (FUN_00ae53e0(group, 1), the stereo depth
 *     FUN_0028beac(group, 0xff)); WANTED: the cards are refreshed with FUN_00a6eea0(scene) (it needs the owner, the
 *     group and the session; it writes the slot structs and the box's own panes). Not WANTED and shown: hidden
 *     (FUN_00ae53e0(group, 0)); not WANTED and hidden: nothing.
 * The draw priority is the game's (10, set by the hub's setup FUN_009B2744), behind every top-screen group of a hall.
 * The group is never kept between frames.
 *
 * Build: tools/build/build_code_space.py, as a unit of the frames block; the game functions and
 * variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;
typedef unsigned short u16;

#define LOBBY 2                     /* game control + 0x2B */
#define SHOWN 0x400u                /* group + 0x44: the group is shown */
#define HUB_READY 0x172D4           /* scene: the hub machine is set up (byte) */
#define HUB_STATE 0x172D5           /* ... its state (byte) */
#define OWNER 0x171C0               /* ... the member list's owner (pointer; *owner is the group) */
#define INTERACTION 0x9788          /* ... 0 while the hunter is free (byte) */
#define LOCK 0x97D6                 /* ... the input lock (halfword) */
#define FREE_HUB 2                  /* hub state: free walking */
#define FREE_HUB_PANEL 0x12         /* ... with the first button's panel open */
#define LIST_ENTRY 0x13             /* ... the game opening its member list */
#define LIST_OPEN 0x14              /* ... its member list open (a hall idles here) */
#define DEPTH_OF_GAME 0xFF          /* FUN_0028beac's argument for "the game's own depth" */

extern u8 *game_control;            /* the game control (its variable) */
extern u8 *lobby_scene;             /* the lobby scene (its variable) */
extern u8 *gui_control;             /* the GUI (its variable) */
u32 game_online_4u(u8 *control);    /* FUN_002b5ac8: control + 0x5D != 0 */
u32 online_mode(void);              /* FUN_002b1040: the session's mode (0, 1 local room, 2 online) */
void gui_group_show(u8 *group, u32 shown);      /* FUN_00ae53e0 */
void group_depth(u8 *group, u32 depth);         /* FUN_0028beac: the group's stereo depth */
void members_refresh(u8 *scene);                /* FUN_00a6eea0: fills the four cards from the session */

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define H(p, off) (*(volatile u16 *)((p) + (off)))
#define B(p, off) (*(volatile u8 *)((p) + (off)))
#define P(p, off) (*(u8 *volatile *)((p) + (off)))

/* The box is wanted: the hunter walks free in a hall (the scene's fields; the session functions come last). */
static u32 wanted(u8 *scene)
{
    u32 state = B(scene, HUB_STATE);
    if (state != FREE_HUB && state != FREE_HUB_PANEL)
        return 0;
    if (B(scene, INTERACTION) || H(scene, LOCK))
        return 0;
    if (!game_online_4u(game_control))
        return 0;
    u32 mode = online_mode();
    return mode == 1 || mode == 2;
}

void players_update(void)
{
    u8 *control = game_control;
    u8 *scene = lobby_scene;
    u8 *gui = gui_control;
    if (!control || !scene || !gui || B(control, 0x2B) != LOBBY || !B(scene, HUB_READY))
        return;
    u8 *owner = P(scene, OWNER);
    if (!owner)
        return;
    u8 *group = P(owner, 0);
    if (!group)
        return;
    if (((W(group, 0x44) >> 14) & 0xF) != (B(gui, 0x245) & 0xF))
        return;
    if (B(scene, HUB_STATE) == LIST_ENTRY || B(scene, HUB_STATE) == LIST_OPEN)
        return;
    u32 shown = (W(group, 0x44) & SHOWN) != 0;
    if (!wanted(scene)) {
        if (shown)
            gui_group_show(group, 0);
        return;
    }
    if (!shown) {
        gui_group_show(group, 1);
        group_depth(group, DEPTH_OF_GAME);
    }
    members_refresh(scene);
}
