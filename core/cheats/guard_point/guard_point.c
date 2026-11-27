/* The cheat Charge Blade Guard Point (cheats/guard_point/guard_point.py): the Charge Blade's morph from guarding (R + X
while guarding) becomes the morph after a sword attack, whose
 * motion has the guard point. From the players' Gateway codes for the USA update ("CB Fix Guard Point", parts 1 and
 * 2), which rewrite the action of the hunter at a heap address every frame; here the number is changed as the action
 * starts, so the morph from guarding never runs and the game sends the other one to the other hunters.
 *
 * FUN_00b1c6f0(hunter, group, number, flags) starts every action of the hunter (act_st p + 0x371, act_no p + 0x372,
 * the phase p + 5 back to 0). guard_point_stub.s sends its first instruction here: guard_point_action(hunter, group,
 * number) answers the number the game then starts.
 *   - The Charge Blade's group 4 frame (vt + 0xD4, FUN_00cc30c0) runs four actions as one function,
 *     FUN_00cc73cc(hunter, from_guard, lunge): 0x06 (0, 0), 0x0B (1, 0), 0x1B (0, 1) and 0x1C (1, 1). The Gateway
 *     codes turn 0x0B into 0x06 (part 1, no stick) and 0x1C into 0x1B (part 2, the stick tilted: the farther lunge).
 *   - Only the hunter this console plays (FUN_00d04fbc), with a Charge Blade (weapon class p + 0x31 = 0xE), while the
 *     option of Mod Settings has a value other than its first (mod_option_value; guard_point_data holds its id,
 *     NO_OPTION for none). Any other start is the game's own number.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with guard_point.ld);
 * the game's functions are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;

#define H_PLAYER       0xE30    /* the hunter's player record p */
#define P_CLASS        0x31     /* u8: the weapon class */
#define CHARGE_BLADE   0xE
#define WEAPON_GROUP   4        /* act_st of the weapon's own actions */
#define MORPH          0x06     /* the morph after a sword attack: FUN_00cc73cc(hunter, 0, 0) */
#define GUARD_MORPH    0x0B     /* ... from guarding: (1, 0) */
#define LUNGE          0x1B     /* the farther lunge after a sword attack: (0, 1) */
#define GUARD_LUNGE    0x1C     /* ... from guarding: (1, 1) */
#define NO_OPTION      0xFF     /* guard_point.py NO_OPTION: the cheat is not hooked */

struct guard_point_data {       /* the block guard_point_data (guard_point.py guard_point_data) */
    u8 option;                  /* mod_options.py OPTION_IDS of the cheat's row, NO_OPTION: none */
    u8 unused[3];
};

_Static_assert(sizeof(struct guard_point_data) == 4, "blocks.py GUARD_POINT_DATA_SIZE");

extern const struct guard_point_data guard_point_data;
extern int mod_option_value(int id);    /* interface/mod_settings/mod_options.c */
extern int mod_option_count(int id);
extern int hunter_is_local(void *hunter);

static int option_on(void)
{
    u32 id = guard_point_data.option;

    return id != NO_OPTION && mod_option_count((int)id) != 0 && mod_option_value((int)id) != 0;
}

/* The action FUN_00b1c6f0 starts for (group, number): it stores the group's low byte and the number's low half */
__attribute__((used, section(".text.entry"))) u32 guard_point_action(void *hunter, u32 group, u32 number)
{
    const u8 *p;
    u32 action = number & 0xFFFF;

    if ((group & 0xFF) != WEAPON_GROUP || (action != GUARD_MORPH && action != GUARD_LUNGE) || !option_on())
        return number;
    p = *(const u8 *const *)((const u8 *)hunter + H_PLAYER);
    if (p == 0 || p[P_CLASS] != CHARGE_BLADE || !hunter_is_local(hunter))
        return number;
    return action == GUARD_MORPH ? MORPH : LUNGE;
}
