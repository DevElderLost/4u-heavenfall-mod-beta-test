/* The Cheats group's damage multipliers (cheats/damage_multipliers/damage_multipliers.py), each set during play by its
own row of Mod Settings: the factor is the payload of the row's
 * value (a float; the first value, x1, changes nothing). damage_multipliers_stub.s hands the game's numbers here:
 *
 *   damage_dealt: FUN_00921f74 (a hit's damage into the monster's damage of the frame, em + 0x4B4 + 2 * region) has
 *     the hit's final damage from FUN_0092bf98 (the hit's value times the monster's rate). A hit of this player's
 *     (hit_owner.h: the hunter, the kinsect, a shot or thrown thing; never a Felyne's, a monster's or nobody's) takes
 *     the factor, rounded to the nearest, and never brings the region's s16 past 32767 (it would wrap and heal);
 *   damage_taken: the hunter's health change (FUN_00b6b4bc, called by FUN_00b1ac40, the damage with Guts and the
 *     death, and by the others): a loss of this console's hunter (the game's own test, FUN_00d04fbc) takes the factor.
 *     What a loss leaves below one point is carried to the next one, so the whole is exact and a poison tick of one
 *     point still adds up. A heal, another console's hunter and x1 are the game's own.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with damage_multipliers.ld; docs/develop/
 * code_space.md); the game's functions and variables are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef signed int s32;
typedef signed short s16;
typedef unsigned char u8;
typedef signed char s8;

#include "../../interface/damage_numbers/hit_owner.h"

#define NO_OPTION 0xFF          /* damage_multipliers.py NO_OPTION: the multiplier is not in the mod */
#define EM 0xE28                /* uEnemy: its em */
#define REGION_DAMAGE 0x4B4     /* em: the frame's damage of each region, s16 */
#define FRAME_DAMAGE_MAX 0x7FFF

struct damage_multipliers_data {        /* damage_multipliers.py multipliers_data */
    u8 dealt;                   /* mod_options.py OPTION_IDS of each row, NO_OPTION: none */
    u8 taken;
    u8 unused[2];
};

_Static_assert(sizeof(struct damage_multipliers_data) == 4, "blocks.py DAMAGE_MULTIPLIERS_DATA_SIZE");

extern const struct damage_multipliers_data damage_multipliers_data;
extern const volatile u8 mod_options_state[];   /* interface/mod_settings/mod_options.c: values[] first, a byte each */
extern const u32 *mod_option_payload(int id);   /* mod_options.c: the value in use's two words */
extern int hunter_is_local(u32 hunter);         /* FUN_00d04fbc */
extern float damage_taken_carry;                /* blocks.py: what the last losses left below one point */

/* The factor of the row `id`; 1 at its first value (x1) and in a mod without the row */
static float factor(u32 id)
{
    union { u32 word; float value; } payload;

    if (id == NO_OPTION || mod_options_state[id] == 0)
        return 1.0f;
    payload.word = mod_option_payload((int)id)[0];
    return payload.value > 0.0f ? payload.value : 1.0f;
}

/* damage_dealt_hook: `damage` is FUN_0092bf98's answer for the hit `hit` by `hunter` on `enemy`'s `region` */
s32 damage_dealt(s32 damage, u32 enemy, u32 region, u32 hit, u32 hunter)
{
    float by = factor(damage_multipliers_data.dealt);
    s32 scaled, room;
    u32 em;

    if (by == 1.0f || damage <= 0 || enemy == 0 || hit == 0 || hit_owner(hit, hunter) != HIT_THIS_PLAYER)
        return damage;
    em = *(volatile u32 *)(enemy + EM);
    if (em == 0)
        return damage;
    scaled = (s32)((float)damage * by + 0.5f);
    if (scaled < 1)
        scaled = 1;
    room = FRAME_DAMAGE_MAX - *(volatile s16 *)(em + REGION_DAMAGE + 2 * region);
    if (scaled > room)
        scaled = room > damage ? room : damage;
    return scaled;
}

/* damage_taken_check, damage_taken_add: the change `change` to `hunter`'s health */
s32 damage_taken(u32 hunter, s32 change)
{
    float by = factor(damage_multipliers_data.taken), owed;
    s32 whole;

    if (by == 1.0f) {
        damage_taken_carry = 0.0f;
        return change;
    }
    if (change >= 0 || hunter == 0 || !hunter_is_local(hunter))
        return change;
    owed = (float)(-change) * by + damage_taken_carry;
    whole = (s32)owed;
    damage_taken_carry = owed - (float)whole;
    return -whole;
}
