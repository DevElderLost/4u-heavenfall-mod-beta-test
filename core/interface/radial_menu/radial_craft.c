/* The item wheel's Auto-Combine.
 *
 * A unit of the wheel's block (radial_wheel.c). With Auto-Combine on, a slot whose item the hunter has none of and
 * that the game would let him combine from what he carries is craftable: radial_craftable says those slots (the
 * picture's marks), and the pick of one combines it once (radial_craft), where the use would give the error sound.
 *
 * Craftable means the checks of the game's combining (the START menu's Combine and the touch Combo List) pass, and
 * two more on the hunter it spends from:
 *   - the hunter can act on an item: use_ready (FUN_00b08f94, the test of both rows), pw + 0x594 not 1 (the touch
 *     panel's), the pouch-full swap dialog closed (its u8 at +4), the hunter FUN_0064199c spends from is this one
 *     (FUN_00af79a4) and it does spend (FUN_00b0861c): without those two the game gives the result, or Garbage, for
 *     nothing;
 *   - the slot's item is a real item and none of it is carried (FUN_005e588c over the 46 slots);
 *   - a recipe makes it (the tables combine_index and combine_records, walked as FUN_00641d20 walks them) with both
 *     ingredients carried and combinable (FUN_00641d20 finds the recipe of the two only when both have flag 0x20);
 *   - room, so the game's swap dialog is never needed: FUN_005e59f4 (the touch panel's test, which asks the ammo pouch
 *     first for ammo and coatings) is not 0 for the result nor for Garbage (a failure's), and where it is -1 (no stack,
 *     no free slot) the combine spends the last piece of an ingredient from one of the 32 item slots, which frees a
 *     slot any item fits. (The menu checks only a learned recipe's result; the wheel checks both, always.)
 * Of a result's two recipes, the one FUN_00641f48 gives the higher chance (the one the menu shows), the first in the
 * tables on a tie.
 *
 * The combine is FUN_0062450c's body without the menu's object: FUN_0064199c(&qty, a, b, 0, ...) rolls the chance
 * and the quantity and spends one of each ingredient. On success FUN_006422b4 marks the recipe learned and sound 0xB
 * plays; on failure the result is Garbage x1 and sound 0xC plays, and the game's Dialog message "[item] obtained."
 * says it with Garbage's name (FUN_005a9fd0, as FUN_00b8dac8 says an item obtained). FUN_00b6d4d4 adds the result
 * (the ammo pouch, the item bar's selection and the quest's gather objectives as the game's own add do); a result
 * capped or at its limit gets "[item] at maximum.", as the game's combine shows it. The weapon may be drawn: the
 * game's combining does not ask.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, Thumb, a unit of radial_wheel.c's block; the game's
 * functions, variables and tables are named in blocks.py GAME_SYMBOLS).
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;
typedef int s32;

#include "radial_craft.h"

#define GAME __attribute__((long_call))

extern u32 item_control, sound_control, player_manager;
extern const u8 combine_index[], combine_records[];
extern u8 swap_dialog[];                /* the game's, changing: read once per call */

GAME s32 pouch_count(u32 control, u32 hunter, u32 item, u32 flag);      /* FUN_005e588c */
GAME u32 item_slot(u32 hunter, u32 item);                               /* FUN_00b1093c: the pouch slot or 0xFFFF */
GAME s32 use_ready(u32 hunter);                                         /* FUN_00b08f94 */
GAME void sound_play(u32 manager, u32 sound);                           /* FUN_0031294c */
GAME s32 combine_roll(u8 *quantity, u32 a, u32 b, u32 mode, u32 slot_a, u32 slot_b);  /* FUN_0064199c */
GAME void combine_learn(u32 recipe);                                    /* FUN_006422b4 */
GAME u32 combine_find(u32 a, u32 b);                                    /* FUN_00641d20 */
GAME s32 combine_chance(u32 recipe, u32 mode);                          /* FUN_00641f48 */
GAME s32 pouch_add(u32 hunter, u32 item, s32 quantity);                 /* FUN_00b6d4d4 */
GAME s32 pouch_room(u32 control, u32 hunter, u32 item, u32 flag);       /* FUN_005e59f4 */
GAME u32 hud_message(u32 message, u32 item, u32 quantity);              /* FUN_005a9fd0 */
GAME u32 local_hunter(u32 manager);                                     /* FUN_00af79a4 */
GAME u32 spend_ready(u32 hunter);                                       /* FUN_00b0861c */

#define B(base, off) (*(const u8 *)((u32)(base) + (off)))
#define H(base, off) (*(const u16 *)((u32)(base) + (off)))
#define W(base, off) (*(const u32 *)((u32)(base) + (off)))

#define PLAYER_WORK 0xA29C              /* hunter -> pw */
#define PW_FORBID 0x594                 /* 1 forbids items */
#define SWAP_OPEN 4                     /* the swap dialog's u8 set while it is open */
#define POUCH 0                         /* FUN_0064199c's and FUN_00641f48's mode: the pouch (1 the box) */
#define ALL_SLOTS 1                     /* FUN_005e588c's and FUN_005e59f4's flag: the whole pouch */
#define NO_SLOT 0xFFFF                  /* FUN_0064199c's slots, used by the box only */
#define FIRSTS 68                       /* combine_index's entries */
#define INDEX_SIZE 4                    /* the first ingredient (u16), its count of records and the first (u8 each) */
#define INDEX_COUNT 2
#define INDEX_FIRST 3
#define RECORD_SIZE 8                   /* the second ingredient (u16), the result (u16), ... */
#define RECORD_RESULT 2
#define ITEM_SLOTS 8                    /* the pouch's slots: 0-7 the ammo pouch, 8-39 the items */
#define ITEM_SLOTS_END 40
#define GARBAGE 0xAA
#define SOUND_MADE 0xB
#define SOUND_FAILED 0xC
#define DIALOG_OBTAINED 0xB             /* "[item] obtained." */
#define DIALOG_AT_MAXIMUM 0xF           /* "[item] at maximum." */
#define ADD_NEW 0                       /* FUN_00b6d4d4: a new stack, added to one, capped, already at the limit */
#define ADD_MORE 1
#define ADD_CAPPED 2
#define ADD_AT_LIMIT 3

struct pick {
    u32 recipe;                         /* the record FUN_00641d20 found */
    u16 a, b;                           /* its ingredients: a the index's (the smaller id) */
};

static s32 carried(u32 hunter, u32 item)
{
    return pouch_count(item_control, hunter, item, ALL_SLOTS);
}

/* The checks that do not depend on the item; *garbage gets the room for Garbage */
static int gate(u32 hunter, s32 *garbage)
{
    u32 pw = W(hunter, PLAYER_WORK);
    if (!pw || !use_ready(hunter) || B(pw, PW_FORBID) == 1 || swap_dialog[SWAP_OPEN])
        return 0;
    if (local_hunter(player_manager) != hunter || !spend_ready(hunter))
        return 0;
    *garbage = pouch_room(item_control, hunter, GARBAGE, ALL_SLOTS);
    return *garbage != 0;
}

/* The combine spends the last piece of `item` from one of the 32 item slots: a slot every item fits */
static int frees_slot(u32 hunter, u32 item)
{
    if (carried(hunter, item) != 1)
        return 0;
    u32 slot = item_slot(hunter, item) & 0xFFFF;
    return slot >= ITEM_SLOTS && slot < ITEM_SLOTS_END;
}

/* The recipe `item` is combined with (the gate passed, `garbage` the room for Garbage); 0 when none */
static int recipe_pick(u32 hunter, u32 item, s32 garbage, struct pick *out)
{
    if (item == 0 || item == 0x790 || item == 0x791 || carried(hunter, item) > 0)
        return 0;
    s32 room = pouch_room(item_control, hunter, item, ALL_SLOTS);
    if (room == 0)
        return 0;
    int full = room < 0 || garbage < 0;
    s32 best = -1;
    for (u32 entry = 0; entry < FIRSTS; entry++) {
        const u8 *first = combine_index + INDEX_SIZE * entry;
        u32 a = H(first, 0), record = B(first, INDEX_FIRST), end = record + B(first, INDEX_COUNT);
        for (; record < end; record++) {
            const u8 *at = combine_records + RECORD_SIZE * record;
            if (H(at, RECORD_RESULT) != item)
                continue;
            u32 b = H(at, 0);
            if (carried(hunter, a) < 1 || carried(hunter, b) < 1)
                continue;
            if (full && !frees_slot(hunter, a) && !frees_slot(hunter, b))
                continue;
            u32 recipe = combine_find(a, b);
            if (!recipe)
                continue;
            s32 chance = combine_chance(recipe, POUCH);
            if (chance > best) {
                best = chance;
                out->recipe = recipe;
                out->a = a;
                out->b = b;
            }
        }
    }
    return best >= 0;
}

u32 radial_craftable(u32 hunter, const struct choices *choices)
{
    s32 garbage;
    struct pick pick;
    u32 mask = 0;
    if (!gate(hunter, &garbage))
        return 0;
    for (u32 slot = 0; slot < WHEEL_SLOTS; slot++)
        if (recipe_pick(hunter, choices->slots[slot], garbage, &pick))
            mask |= 1u << slot;
    return mask;
}

u32 radial_craft(u32 hunter, u32 item)
{
    s32 garbage;
    struct pick pick;
    if (!gate(hunter, &garbage) || !recipe_pick(hunter, item, garbage, &pick))
        return CRAFT_NONE;
    u8 quantity = 0;
    s32 got = combine_roll(&quantity, pick.a, pick.b, POUCH, NO_SLOT, NO_SLOT);
    int made = got >= 1;
    u32 result = made ? (u32)got : GARBAGE;
    if (made) {
        combine_learn(pick.recipe);
    } else {
        quantity = 1;
    }
    sound_play(sound_control, made ? SOUND_MADE : SOUND_FAILED);
    s32 code = pouch_add(hunter, result, quantity);
    if (code == ADD_CAPPED || code == ADD_AT_LIMIT)
        hud_message(DIALOG_AT_MAXIMUM, result, 0);
    else if (!made && (code == ADD_NEW || code == ADD_MORE))
        hud_message(DIALOG_OBTAINED, GARBAGE, quantity);
    return made ? CRAFT_MADE : CRAFT_FAILED;
}
