/* Capture Guru and Autotracker always on (cheats/map_skills/map_skills.py), each turned on and off during play by its
own option of the START menu's Mod
 * Settings (interface/mod_settings/mod_options.c). From the players' Gateway codes for the USA update, which make the
 * minimap's question "does the hunter have the skill" answer yes; map_skills_stub.s asks map_skill_on first:
 *
 *   0 Capture Guru (skill 0xBF): FUN_00b9b390, a large monster's mark on the minimap, which blinks when the monster
 *     can be captured;
 *   1 Autotracker (skill 0xBD): FUN_00b9651c, whether the minimap shows the large monsters.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with map_skills.ld).
 */

typedef unsigned int u32;
typedef unsigned char u8;

#define NO_OPTION 0xFF          /* map_skills.py NO_OPTION: the cheat is not hooked */
#define SKILLS 2                /* map_skills.py CHEATS */

struct map_skills_data {        /* the block map_skills_data (map_skills.py skills_data) */
    u8 option[SKILLS];          /* mod_options.py OPTION_IDS of each cheat, NO_OPTION: none */
    u8 unused[2];
};

_Static_assert(sizeof(struct map_skills_data) == 4, "blocks.py MAP_SKILLS_DATA_SIZE");

extern const struct map_skills_data map_skills_data;
extern int mod_option_value(int id);    /* interface/mod_settings/mod_options.c */
extern int mod_option_count(int id);

/* The cheat `which` (0 Capture Guru, 1 Autotracker) is on */
__attribute__((used, section(".text.entry"))) int map_skill_on(u32 which)
{
    u32 id = which < SKILLS ? map_skills_data.option[which] : NO_OPTION;

    return id != NO_OPTION && mod_option_count((int)id) != 0 && mod_option_value((int)id) != 0;
}
