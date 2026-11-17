/* The jukebox's block in the card file, a unit of the block
 * jukebox (jukebox.h; the hooks' stubs are jukebox_save_stub.s, their patch music/jukebox/save_patch.py):
 *
 *   - jukebox_store(card), from FUN_002adedc (the card file's writer) after its last copy into the plain file and before
 *     its sum: the copy in memory is first made the card's hunter's (jukebox_owner with the id the writer put at the
 *     card's +0x10: another hunter's copy becomes the defaults), then written at the card's +0x78878 with its header
 *     (magic, version, the sum of the bytes after the header). The game's sum and cipher then cover it.
 *   - jukebox_load(card), from FUN_002ae018 (the card file's read step) when the game's reader FUN_002adc98 accepted
 *     the file: the card's id becomes the owner, the copy the defaults, then the file's block when its magic, version
 *     and sum are right; then jukebox_loaded.
 *   - jukebox_check_owner, at the start of jukebox_tick and from the menu: the copy is made the loaded hunter's
 *     (jukebox_hunter). A load whose card was missing, had a bad sum or another hunter's id never reaches
 *     jukebox_load, so a copy of another hunter is reset there before it is played or edited.
 *
 * Build: tools/build/build_code_space.py (devkitARM), which places and links it.
 */
#include "jukebox.h"

/* the game's variables (blocks.py GAME_SYMBOLS) */
extern u32 save_control;                /* the variable holding the save object */
extern u32 game_control;                /* the variable holding the game control */

/* the card file */
#define CARD_HUNTER_ID 0x10             /* 8 bytes: the id of the hunter whose card it is (FUN_002adedc) */
#define CARD_BLOCK 0x78878              /* the file's tail, after the game's last copy: the jukebox's block */
#define HEADER 8                        /* magic u32, version u16, sum u16 */
/* the loaded hunter (FUN_002adedc, FUN_002adc98, FUN_005dd674) */
#define LOADED_SLOT 0xA4                /* s8 in the game control: the slot loaded, 0-2 */
#define SLOTS 3
#define HUNTER_IDS (0x15260 + 0x7098C)  /* save + this + slot x HUNTER_STRIDE: the 8 bytes of the slot's hunter id */
#define HUNTER_STRIDE 0x1200

#define S (&jukebox_state)

static u32 get(const u8 *at, int bytes)
{
    u32 value = 0;
    for (int i = bytes - 1; i >= 0; i--)
        value = value << 8 | at[i];
    return value;
}

static void put(volatile u8 *at, u32 value, int bytes)
{
    for (int i = 0; i < bytes; i++)
        at[i] = (u8)(value >> 8 * i);
}

/* the u16 sum of a block's bytes after its header */
static u32 block_sum(const u8 *block)
{
    u32 sum = 0;
    for (u32 i = HEADER; i < sizeof(struct jukebox_save); i++)
        sum += block[i];
    return sum & 0xFFFF;
}

const u8 *jukebox_hunter(void)
{
    u8 *save = (u8 *)save_control, *control = (u8 *)game_control;
    if (!save || !control)
        return 0;
    int slot = (s8)control[LOADED_SLOT];
    if (slot < 0 || slot >= SLOTS)
        return 0;
    return save + HUNTER_IDS + slot * HUNTER_STRIDE;
}

void jukebox_check_owner(void)
{
    const u8 *hunter = jukebox_hunter();
    if (hunter)
        jukebox_owner(hunter);
}

void jukebox_store(u8 *card)
{
    if (!card)
        return;
    jukebox_owner(card + CARD_HUNTER_ID);
    volatile u8 *out = card + CARD_BLOCK;       /* volatile: no memcpy call (no library is linked) */
    const u8 *in = (const u8 *)&S->save;
    for (u32 i = HEADER; i < sizeof S->save; i++)
        out[i] = in[i];
    put(out, JUKEBOX_MAGIC, 4);
    put(out + 4, JUKEBOX_VERSION, 2);
    put(out + 6, block_sum(in), 2);     /* the bytes just copied */
}

void jukebox_load(const u8 *card)
{
    if (!card)
        return;
    for (int i = 0; i < 8; i++)
        S->owner[i] = card[CARD_HUNTER_ID + i];
    S->owned = 1;
    jukebox_reset();
    const u8 *block = card + CARD_BLOCK;
    if (get(block, 4) == JUKEBOX_MAGIC && get(block + 4, 2) == JUKEBOX_VERSION
            && get(block + 6, 2) == block_sum(block)) {
        volatile u8 *copy = (u8 *)&S->save;     /* volatile: no memcpy call (no library is linked) */
        for (u32 i = 0; i < sizeof S->save; i++)
            copy[i] = block[i];
    }
    jukebox_loaded();
}
