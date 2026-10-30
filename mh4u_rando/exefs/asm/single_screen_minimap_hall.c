/* Single-screen mode: the town minimap in a Gathering Hall (exefs/single_screen_minimap.py; emulator only).
 *
 * In a hall the lobby's hub machine (FUN_009bba14, state at scene + 0x172D5) does not stay in state 2, where the game
 * shows the map while the hunter walks: online it goes 0 -> 0x13 -> 0x14 (FUN_009fc5fc), the member list open, and the
 * first touch button gives 0x11 -> 0x12 offline (FUN_00a09d70). On the way into both the game hides the map's five groups
 * and ui420's second group (FUN_00aab4dc) and the place name (ui421's second group), and only state 1 shows them again.
 * So the minimap block, which moves the groups the game shows, had nothing to move there and L was left dead.
 *
 * minimap_hall(on), called by the minimap block every frame with what it wants (on: its state group shown and no talk),
 * does in states 0x12 and 0x14 what the game does in the others:
 *   - on, the map hidden: what state 1 does to show it (FUN_00a2e76c's sequence): FUN_00a407f8(scene) shows the groups,
 *     then FUN_00a13270, FUN_00a136c0 and FUN_009dabb8 (scene, the stage's kind FUN_002b5ad8(game)) set the place,
 *     the name and the icons; the place name group is shown. The minimap block then puts them on the top screen;
 *   - off, the map shown (by this function: the game never shows it in those states): FUN_00aab4dc(scene), the game's
 *     own hide, and the place name hidden, as the game had them; ui420's second group, which FUN_00aab4dc also hides,
 *     is shown again when it was shown.
 * Nothing is done in any other state, out of the lobby or without the hub machine or the map's owner; the label and
 * ui420's owners may be missing. The groups' owners are the lobby scene's: + 0x171BC ui422's (the map first), + 0x171B8
 * ui421's, + 0x171B4 ui420's (second group each at + 4).
 *
 * Build: tools/build_code_space.py (arm-none-eabi-gcc, linked with single_screen_minimap_hall.ld where it places the
 * block); the game functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;

#define LOBBY 2                     /* the game control's byte + 0x2B in the lobby */
#define SHOWN 0x400u                /* a group's shown bit (group + 0x44) */
#define GROUP_FLAGS 0x44
#define HUB_READY 0x172D4           /* the lobby scene: the hub machine is set up (not 0) */
#define HUB_STATE 0x172D5           /* ... its state */
#define MENU_HUB 0x12               /* ... the town's first touch button, offline */
#define LIST_HUB 0x14               /* ... a hall's member list, online */
#define MAP_OWNER 0x171BC           /* ... ui422's groups: the map first */
#define LABEL_OWNER 0x171B8         /* ... ui421's: the place name second */
#define MENU_OWNER 0x171B4          /* ... ui420's: the group FUN_00aab4dc hides second */

extern u8 *game_control;            /* the game control (its variable) */
extern u8 *lobby_scene;             /* the lobby scene (its variable) */
void gui_group_show(u8 *group, u32 shown);      /* FUN_00ae53e0 */
u32 lobby_stage(u8 *game);                      /* FUN_002b5ad8: the stage's kind */
void town_map_show(u8 *scene);                  /* FUN_00a407f8 */
void town_map_place(u8 *scene, u32 kind);       /* FUN_00a13270 */
void town_map_label(u8 *scene, u32 kind);       /* FUN_00a136c0 */
void town_map_icons(u8 *scene, u32 kind);       /* FUN_009dabb8 */
void town_map_hide(u8 *scene);                  /* FUN_00aab4dc */

#define W(p, off) (*(volatile u32 *)((p) + (off)))
#define B(p, off) (*(volatile u8 *)((p) + (off)))
#define P(p, off) (*(u8 *volatile *)((p) + (off)))

/* The second group of the owner at scene + `at`, or 0. */
static u8 *second(u8 *scene, u32 at)
{
    u8 *owner = P(scene, at);
    return owner ? P(owner, 4) : 0;
}

__attribute__((section(".text.entry"))) void minimap_hall(u32 on)
{
    u8 *game = game_control;
    u8 *scene = lobby_scene;
    if (!game || !scene || B(game, 0x2B) != LOBBY || !B(scene, HUB_READY))
        return;
    u32 hub = B(scene, HUB_STATE);
    if (hub != MENU_HUB && hub != LIST_HUB)
        return;
    u8 *owner = P(scene, MAP_OWNER);
    u8 *map = owner ? P(owner, 0) : 0;
    if (!map)
        return;
    u8 *label = second(scene, LABEL_OWNER);
    u32 shown = W(map, GROUP_FLAGS) & SHOWN;
    if (on && !shown) {
        u32 kind = lobby_stage(game);
        town_map_show(scene);
        town_map_place(scene, kind);
        town_map_label(scene, kind);
        town_map_icons(scene, kind);
        if (label)
            gui_group_show(label, 1);
    } else if (!on && shown) {
        u8 *bar = second(scene, MENU_OWNER);
        u32 kept = bar && (W(bar, GROUP_FLAGS) & SHOWN);
        town_map_hide(scene);
        if (kept)
            gui_group_show(bar, 1);
        if (label)
            gui_group_show(label, 0);
    }
}
