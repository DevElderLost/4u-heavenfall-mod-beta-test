/* One more item in the haul of every expedition of the Meownster Hunters.
 *
 * The game function it changes: FUN_00aab770, the claim of the expeditions' rewards (the lobby's facility function
 * FUN_009c715c calls it in its state 7). It rolls the haul of each quest of the route into a stack array of 24 entries
 * {s16 item, s16 count} (sp + 0x8) and counts them in a word (sp + 0x6C), then hands each entry to the claim list.
 * The hook replaces the instruction that loads that count (0xAABAA8, `ldr r0, [sp, #0x6c]`, right after the per-quest
 * loop and before the "nothing obtained" test) with a call to meownster_extra_hook, which adds one entry to the array
 * and reloads the count, so the game's own code goes on with the extra among the others.
 *
 * What it adds: the item of the level (the byte lobby + 0x9246: 0 low, 1 high) that the patcher wrote into
 * meownster_scrap_data, `count` of it, once per claim. A full haul (24, the game's maximum) gives its last entry up to
 * the extra. It draws no random number. Only the Meownster Hunters' own facility gets it: the lobby's facility byte
 * (lobby + 0x9788) is 0x21 there, while the Housekeeper's route (facility 0x22, FUN_00aa8298) reaches the same claim.
 *
 * Hook (ARM, below; gameplay/meownster_scrap/meownster_scrap.py points the game at it):
 *   meownster_extra_hook   0xAABAA8  "ldr r0, [sp, #0x6c]": r1-r3 and r12 are free there (the code after it sets r4,
 *                                    r5 before using them and reloads the rest); r4-r11 the C call keeps.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with meownster_scrap.ld).
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define ARM __attribute__((target("arm"), noinline))
#define STR2(x) #x
#define STR(x) STR2(x)

#define HAUL_MAX 24               /* the stack array and the claim list (lobby + 0xA234) */
#define FRAME_HAUL 0x8            /* FUN_00aab770's sp: the array of {s16 item, s16 count} */
#define FRAME_COUNT 0x6C          /* its entries' count, a word */
#define FRAME_LOBBY 0x118         /* the lobby, FUN_00aab770's r0 pushed at its entry */
#define LOBBY_LEVEL 0x9246        /* 0 low, 1 high */
#define LOBBY_FACILITY 0x9788     /* the facility the lobby is running */
#define FACILITY_MEOWNSTER 0x21   /* the Meownster Hunters' (the Housekeeper's is 0x22) */

struct extra {
    u16 low, high;                /* the item of each level (0: none) */
    u16 count, pad;               /* how many of it */
};
extern const struct extra meownster_scrap_data;

ARM void meownster_extra(u8 *frame)
{
    u8 *lobby = *(u8 **)(frame + FRAME_LOBBY);
    u16 *haul = (u16 *)(frame + FRAME_HAUL);
    u32 n = *(u32 *)(frame + FRAME_COUNT) & 0xFF;
    u16 item;

    if (lobby[LOBBY_FACILITY] != FACILITY_MEOWNSTER)
        return;
    item = lobby[LOBBY_LEVEL] ? meownster_scrap_data.high : meownster_scrap_data.low;
    if (item == 0)
        return;
    if (n >= HAUL_MAX)
        n = HAUL_MAX - 1;         /* a full haul: its last entry gives way */
    haul[2 * n] = item;
    haul[2 * n + 1] = meownster_scrap_data.count;
    *(u32 *)(frame + FRAME_COUNT) = n + 1;
}

/* ----- the hook ------------------------------------------------------------------------------------------- */

__asm__(
    "   .section .text.meownster_hooks, \"ax\", %progbits\n"
    "   .arm\n"
    "   .global meownster_extra_hook\n"
    /* sp is FUN_00aab770's here; the push keeps the stack 8-aligned for the call and moves it 8 bytes */
    "meownster_extra_hook:\n"
    "   push    {r4, lr}\n"
    "   add     r0, sp, #8\n"
    "   bl      meownster_extra\n"
    "   ldr     r0, [sp, #(8 + " STR(FRAME_COUNT) ")]\n"
    "   pop     {r4, pc}\n"
    "   .ltorg\n"
    "   .text\n");
