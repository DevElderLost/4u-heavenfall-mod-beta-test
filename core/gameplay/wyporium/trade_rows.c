/* Whether a row of the Wyporium's "Trade Materials" table is open. The game asks FUN_00c21fe0(save, quest) at three
places, once per row (the list builder FUN_00a53160,
 * the hub build's obtained bits FUN_009dd4c8, the menu's bright line at 0x9B6F40): each `bl` goes to trade_row_open.
 * A game row keeps its quest, cleared or not. A row the mod adds carries the marker TRADE_RANK_QUEST + its rank
 * (trades.py): it opens when its rank does, as Layered Gear's looks of the rank do. */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define GAME __attribute__((long_call))
#define ARM __attribute__((target("arm"), noinline))

#include "rank_unlock.h"

#define TRADE_RANK_QUEST 0xFFF0          /* trades.py MARKER_QUEST */

extern const u16 wyporium_trade_rows_data[RANKS - 1][UNLOCK_ROOM];

ARM u32 trade_row_open(u32 save, u32 quest)
{
    if (quest - TRADE_RANK_QUEST < RANKS)
        return quest - TRADE_RANK_QUEST <= rank_unlocked(wyporium_trade_rows_data);
    return quest_cleared(save, quest);
}
