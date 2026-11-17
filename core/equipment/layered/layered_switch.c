/* Layered Gear's switch in the game: a unit of the block
 * layered_selector.
 *
 * Mod Settings' row "Layered Gear" (Yes / No, per character) says whether the looks are shown: No draws everyone's real
 * gear, the local hunter's, its cats' and the other players', and sends the others our real gear. Nothing worn, bought
 * or dyed changes: layered_state, the cats' look words, the owned bits and the save stay as they are, and Yes shows them
 * again. The forge-style screens stay open with No (buying, trying on and dyeing are not showing; the preview shows
 * what it tries on).
 *
 * The row's value is the option's byte of mod_options_state.values (interface/mod_settings/mod_options.c fills it each
 * frame from the character's save zone), read only when the mod has the row: layered_switch_option is its place in
 * mod_options.py OPTION_IDS, written by the patcher (equipment/layered/layered_equipment.py, `switch`), NO_SWITCH
 * without the row, and then the looks always show.
 *
 * When a change acts:
 *   town   at once. layered_town_frame (layered_online.c) calls layered_switch_frame each frame: the local hunter is
 *          dressed again (hunter_reload, as the screens do when they close; retried while it loads), the own cats too
 *          (felyne_redress) and the others are told (layered_net_state_left: the hash below changed). The other
 *          players' hunters and cats follow by themselves: their entries stop counting (layered_remote_by_slot,
 *          cat_word), and the hall's re-dressing sees that.
 *   quest  at the next quest. The quest's models are loaded beforehand by the preloader, so the value the preload
 *          took (layered_switch_latch, at its first look asked or its snapshot) holds until the game is back in the
 *          town; a model asked for that was never loaded would leave the hunter undrawn. Back in town, a hunter made
 *          with the quest's value is dressed again if the row says otherwise now.
 *
 * Build: tools/build/build_code_space.py, with the rest of the block (layered_selector.c).
 */

#include "layered.h"

#define NO_SWITCH 0xFF           /* layered_switch_option without the row */
#define SHOWN 1                  /* struct layered_switch's values: 0 none */
#define HIDDEN 2
#define GAME_HUB 2               /* game_control + 0x2B in the village and the Gathering Hall (FUN_0065e31c) */

/* The patcher writes it (layered_equipment.py SWITCH_LABEL): volatile, so that the compiler never takes the default. */
__attribute__((used, section(".rodata.layered_switch"))) const volatile u8 layered_switch_option = NO_SWITCH;

extern const volatile u8 mod_options_state[];   /* interface/mod_settings/mod_options.c: values[] first, a byte each */

struct layered_switch {          /* the variable layered_switch */
    u8 town;                     /* the value the town's hunters were last dressed with: 0 none yet, SHOWN, HIDDEN */
    u8 quest;                    /* the value the quest's preload took: 0 none (in town, or before any preload) */
    u8 pending;                  /* the local hunter is to be dressed again once it has loaded */
    u8 pad;
};
_Static_assert(sizeof(struct layered_switch) == 4, "layered_switch size (game/executable/blocks.py)");
extern struct layered_switch layered_switch;

/* What the row says now: SHOWN or HIDDEN (SHOWN without the row). */
static u32 row_value(void)
{
    u32 option = layered_switch_option;
    return option == NO_SWITCH || mod_options_state[option] ? SHOWN : HIDDEN;
}

int layered_shown(void)
{
    u32 quest = layered_switch.quest;
    return (quest ? quest : row_value()) == SHOWN;
}

void layered_switch_latch(void)
{
    if (!layered_switch.quest)
        layered_switch.quest = row_value();
}

/* Every frame in the town (layered_town_frame, before the hall's re-dressing of the others). `local` is the local
   hunter's lobby index (game_control + 0x2F), `town` the town object (*0xEDBE90, the Smithy's obj). */
void layered_switch_frame(u32 town, u32 local)
{
    struct layered_switch *s = &layered_switch;
    const u8 *game = game_control;
    if (!game || game[0x2B] != GAME_HUB)
        return;
    u32 now = row_value(), worn = s->quest ? s->quest : s->town;
    s->quest = 0;
    s->town = now;
    if (worn && worn != now) {
        s->pending = 1;
        felyne_redress(town);
        layered_net_state_left();
    }
    if (s->pending && layered_redress_index(local))
        s->pending = 0;
}
