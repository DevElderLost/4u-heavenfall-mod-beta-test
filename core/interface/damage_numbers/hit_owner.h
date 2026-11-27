/* Whose a hit on a monster is, from the hit record FUN_00b700f8
 * fills and the attacker FUN_00be9c64 holds in r6. Shared by Damage Numbers (damage_numbers.c) and the damage
 * multiplier of the Cheats group (cheats/damage_multipliers/damage_multipliers.c), so both count the same hits as this
 * player's. The including file defines u32, s32, s8, u8 and links the variable game_control (blocks.py GAME_SYMBOLS).
 */

#ifndef HIT_OWNER_H
#define HIT_OWNER_H

#define HIT_OBJECT 0x10         /* the hit record: what made it */
#define HIT_OWNER_KIND 0x67     /* the owner of a shot or a kinsect */
#define HIT_OWNER 0x68
#define HUNTER_STATUS 0xE30     /* uPlayer: its status, +0x33 its player number */
#define PLAYER_NUMBER 0x2F      /* sGameControl: this console's player */

enum { BY_HUNTER, BY_MONSTER, BY_SHELL, BY_PALICO, BY_KINSECT = 7 };
/* THIS_PLAYER: this console's hunter, its kinsect or its shot; OTHER_PLAYER: another player's; FELYNE: any player's
   Felyne; NO_PLAYER: a monster's (on a monster, or its shot) or nobody's (the map's weapons) */
enum { HIT_THIS_PLAYER, HIT_OTHER_PLAYER, HIT_FELYNE, HIT_NO_PLAYER };

extern u32 game_control;

static int hit_this_player(s32 player)
{
    u32 control = game_control;

    return control != 0 && (s8)player == *(volatile s8 *)(control + PLAYER_NUMBER);
}

static int hit_this_players_hunter(u32 hunter)
{
    u32 status = hunter != 0 ? *(volatile u32 *)(hunter + HUNTER_STATUS) : 0;

    return status != 0 && hit_this_player(*(volatile s8 *)(status + 0x33));
}

/* Whose the hit `hit` by `hunter` (FUN_00be9c64's r6, the attacker when the hit is a hunter's own) is */
static int hit_owner(u32 hit, u32 hunter)
{
    switch (*(volatile u8 *)(hit + HIT_OBJECT)) {
    case BY_HUNTER:
        return hit_this_players_hunter(hunter) ? HIT_THIS_PLAYER : HIT_OTHER_PLAYER;
    case BY_KINSECT:
        return hit_this_players_hunter(*(volatile u32 *)(hit + HIT_OWNER)) ? HIT_THIS_PLAYER : HIT_OTHER_PLAYER;
    case BY_PALICO:
        return HIT_FELYNE;
    case BY_SHELL:
        if (*(volatile u8 *)(hit + HIT_OWNER_KIND) == BY_HUNTER)
            return hit_this_players_hunter(*(volatile u32 *)(hit + HIT_OWNER)) ? HIT_THIS_PLAYER : HIT_OTHER_PLAYER;
        if (*(volatile u8 *)(hit + HIT_OWNER_KIND) == BY_PALICO)
            return HIT_FELYNE;
        return HIT_NO_PLAYER;
    default:
        return HIT_NO_PLAYER;
    }
}

#endif
