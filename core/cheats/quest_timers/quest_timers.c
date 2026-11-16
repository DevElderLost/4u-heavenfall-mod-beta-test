/* The cheats of the quest's timers (cheats/quest_timers/quest_timers.py), each turned on and off during play by its own
option of the START menu's Mod
 * Settings (interface/mod_settings/mod_options.c). From the players' Gateway codes for the USA update; here as a block
 * of the code space, which quest_timers_stub.s calls:
 *
 *   quest_end_delta     FUN_0065c1b4, the quest's end (step 2 of FUN_0065af38: the countdown before the hunters
 *                       leave), counts its quest object's +0x3C down by the main object's frame time (+0x5C, a float
 *                       in 60ths of a second). The time it counts: the game's, times `skip_speed` while A and B are
 *                       held with Skip Quest End Timer on;
 *   rewards_timer_add   FUN_00accd24, the quest result scene, adds the frame time to its timer's fraction (scene +
 *                       0x18; the seconds left are +0x14). With No Time Limit on, the fraction stays as it is on the
 *                       scene's steps 1 and 2 (scene + 4), so the timer stops there; on the other steps, and with the
 *                       option off, it is the game's sum;
 *   rewards_no_limit    whether No Time Limit is on: FUN_00ab88f4 then does not show the countdown's number
 *                       (its call of FUN_002ed5d0).
 *
 * An option off gives the game's own value, so the game runs as without the hooks.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with quest_timers.ld);
 * the game's pad variable is named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned char u8;

#define NO_OPTION 0xFF          /* quest_timers.py NO_OPTION: the cheat is not hooked */
#define MAIN_FRAME_TIME 0x5C    /* the main object: the frame's time (a float, in 60ths of a second) */
#define PAD_HELD 0x8C           /* the pad object: the raw buttons held */
#define BUTTON_A 0x2000
#define BUTTON_B 0x4000
#define SCENE_STEP 4            /* the quest result scene: its step */
#define FROZEN_FIRST 1          /* the steps whose timer stops (the Gateway code's) */
#define FROZEN_LAST 2

struct quest_timers_data {      /* the block quest_timers_data (quest_timers.py timers_data) */
    u8 skip_end_option;         /* mod_options.py OPTION_IDS: Skip Quest End Timer, NO_OPTION: none */
    u8 rewards_option;          /* No Time Limit on Rewards Screen */
    u8 unused[2];
    float skip_speed;           /* how many times faster the end's countdown runs (curated tuning.json) */
};

_Static_assert(sizeof(struct quest_timers_data) == 8, "blocks.py QUEST_TIMERS_DATA_SIZE");

extern const struct quest_timers_data quest_timers_data;
extern u8 *const pad_control;           /* the variable holding the pad object */
extern int mod_option_value(int id);    /* interface/mod_settings/mod_options.c */
extern int mod_option_count(int id);

union word {
    u32 bits;
    float number;
};

static int option_on(u32 id)
{
    return id != NO_OPTION && mod_option_count((int)id) != 0 && mod_option_value((int)id) != 0;
}

/* The frame time FUN_0065c1b4 counts its countdown by: the main object's, times skip_speed while A and B are held */
__attribute__((used, section(".text.entry"))) u32 quest_end_delta(const u8 *main)
{
    const u8 *pad = pad_control;
    union word time;

    time.bits = *(const volatile u32 *)(main + MAIN_FRAME_TIME);
    if (pad != 0 && (*(const volatile u32 *)(pad + PAD_HELD) & (BUTTON_A | BUTTON_B)) == (BUTTON_A | BUTTON_B) &&
        option_on(quest_timers_data.skip_end_option))
        time.number *= quest_timers_data.skip_speed;
    return time.bits;
}

/* The result scene's timer fraction after this frame: `fraction` + `time`, or `fraction` on a frozen step */
u32 rewards_timer_add(const u8 *scene, u32 fraction, u32 time)
{
    union word sum, add;
    u32 step = (u8)(scene[SCENE_STEP] - FROZEN_FIRST);

    sum.bits = fraction;
    add.bits = time;
    if (step <= FROZEN_LAST - FROZEN_FIRST && option_on(quest_timers_data.rewards_option))
        return fraction;
    sum.number += add.number;
    return sum.bits;
}

/* No Time Limit on Rewards Screen is on: the result scene shows no countdown */
int rewards_no_limit(void)
{
    return option_on(quest_timers_data.rewards_option);
}
