/* Debug cheat cheat_insta_kill (cheats/cheats.py): the hunter's attack is
 * multiplied and capped, so every hit takes a monster's health at once. From the players' Gateway code for the USA
 * update (a cave at 0xDEC7C0 called from the two sites below); here as a block of the code space.
 *
 * FUN_002f8f34(table, hunter, stat, flag) is a stat of the hunter's equipment; stat 6 is the weapon's attack. Two of
 * its calls are hooked, both a `bl` replaced by a `bl` to this block:
 *   0xB1EAC8 in FUN_00b1ea88(hunter, ..., out), the hunter's attack: the weapon's, with the skills, the charm and
 *       talon, Adrenaline and the other bonuses on top; what a hit is worth;
 *   0xAF8BB0 in FUN_00af8b80, the same attack as the equipment's status screen shows it.
 * The block calls FUN_002f8f34 with the same arguments and returns its value times `multiplier`, at most `cap`
 * (the data block `insta_kill_data`, which the patcher fills from curated data).
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with insta_kill.ld where it places the block); the
 * game function is named in blocks.py GAME_SYMBOLS.
 */

typedef int s32;

struct insta_kill_data {
    s32 multiplier;
    s32 cap;
};

extern const struct insta_kill_data insta_kill_data;
extern s32 hunter_gear_stat(void *table, void *hunter, s32 stat, s32 flag);

__attribute__((used, section(".text.entry"))) s32 insta_kill_attack(void *table, void *hunter, s32 stat, s32 flag)
{
    s32 value = hunter_gear_stat(table, hunter, stat, flag) * insta_kill_data.multiplier;
    return value < insta_kill_data.cap ? value : insta_kill_data.cap;
}
