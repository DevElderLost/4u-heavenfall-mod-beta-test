/* Single-screen mode: the touch-panel layout B on every save
(interface/single_screen/executable/single_screen_layout.py; emulator only).
 *
 * The quest HUD's init (FUN_00b892f0, from FUN_00b823d4 when a quest loads) copies the saved touch panels into the
 * runtime object: it asks FUN_00c1cc9c(save, 0) for the saved record (six halfwords of panel kinds, then a byte) and
 * copies the record's twelve bytes to the object at +0x7A. Layout A keeps the Map (kind 6) on the touch screen, where
 * the mode has no use for it; layout B moves it to the top HUD. The new game's choice takes B
 * (single_screen_layout.py), but a save made before holds whatever its player picked or arranged.
 *
 * panels_record(save, index) takes the place of that call (the same arguments and result). For record 0, when its six
 * halfwords are not layout B's, it writes layout B the way the game's own choice does, FUN_00c26754(save, 1) (which also
 * resets the panels' defaults after the record), and sets the story flag 0x9AD that the choice of B sets and the reset to
 * the default layout (FUN_002902e0) reads. A layout arranged by hand is replaced. Then it returns FUN_00c1cc9c's result.
 * Any other record, or a save that is null, goes straight to the game's function.
 *
 * FUN_00c26754 stores r4 as the byte after the record (the callers keep the cursor, 0 for A and 1 for B, in r4 as well as
 * in r1), so the call is made by a short stub that sets r4 to 1.
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with single_screen_panels.ld where it places the
 * block); the game functions are named in blocks.py GAME_SYMBOLS.
 */

typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned char u8;

#define RECORD_ZERO 0                 /* the record the runtime panels are copied from */
#define LAYOUT_B_FLAG 0x9AD           /* the story flag of layout B */
#define PANELS 6                      /* halfwords of panel kinds in a record */

u8 *panel_record(u8 *save, u32 index);          /* FUN_00c1cc9c: the saved record, 16 bytes each from record 0 */
void panel_layout_write(u8 *save, u32 layout);  /* FUN_00c26754: record 0 as layout 0 (A) or 1 (B); r4 = layout */
void set_story_flag(u8 *save, u32 flag);        /* FUN_00c1b0e8 */

/* Layout B's panel kinds, as FUN_00c26754 writes them for layout 1. */
static const u16 LAYOUT_B[PANELS] = {0xD, 0xB, 0x11, 1, 1, 0x11};

/* FUN_00c26754(save, 1) with r4 = 1, as the choice of B calls it (save stays in r0). */
__attribute__((naked, noinline)) static void write_layout_b(__attribute__((unused)) u8 *save)
{
    __asm__ volatile(
        "push   {r4, lr}\n\t"
        "mov    r4, #1\n\t"
        "mov    r1, #1\n\t"
        "bl     panel_layout_write\n\t"
        "pop    {r4, pc}\n\t");
}

static int is_layout_b(const u8 *record)
{
    const u16 *kinds = (const u16 *)record;
    for (u32 n = 0; n < PANELS; n++)
        if (kinds[n] != LAYOUT_B[n])
            return 0;
    return 1;
}

__attribute__((section(".text.entry"))) u8 *panels_record(u8 *save, u32 index)
{
    u8 *record = panel_record(save, index);
    if (!save || index != RECORD_ZERO || is_layout_b(record))
        return record;
    write_layout_b(save);
    set_story_flag(save, LAYOUT_B_FLAG);
    return panel_record(save, index);
}
