/* Which rank the player has reached, for the Wyporium's code (rare_exchange.c, trade_rows.c). Included after u32 / u16
 * and GAME are defined. A rank's list holds up to UNLOCK_ROOM entries, 0 ends it: a quest id opens the rank when it is
 * cleared, an entry with UNLOCK_FLAG a story flag. The lists are data of each block (the curated rank_unlocks of
 * layered_looks.json), the rank 0 (low) is always open. */

#define RANKS 3
#define UNLOCK_ROOM 4
#define UNLOCK_FLAG 0x8000
#define UNLOCK_OPEN 0xFFFF   /* always holds: every rank open from the start (layered_by_rank off) */

GAME u32 quest_cleared(u32 save, u32 quest);                            /* FUN_00c21fe0 */
GAME u32 story_flag(u32 save, u32 flag);                                /* FUN_00c1c278 */
extern u32 save_control;

/* The highest rank open: the first list that holds opens high, the second G. */
static u32 rank_unlocked(const u16 (*lists)[UNLOCK_ROOM])
{
    u32 rank = 0;
    for (u32 list = 0; list < RANKS - 1; list++)
        for (u32 i = 0; i < UNLOCK_ROOM && lists[list][i]; i++) {
            u32 entry = lists[list][i];
            u32 done = entry == UNLOCK_OPEN ? 1
                     : entry & UNLOCK_FLAG ? story_flag(save_control, entry & ~UNLOCK_FLAG)
                                           : quest_cleared(save_control, entry);
            if (done && list + 1 > rank)
                rank = list + 1;
        }
    return rank;
}
