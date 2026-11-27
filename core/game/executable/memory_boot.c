/* The heap sizes at boot, chosen by the application's memory (game/executable/memory_boot.py).
 *
 * FUN_001047c0, which the executable's entry calls once (0x10000C), splits the application's memory in two: the device
 * memory (the literal 0x3063000 at 0x104828, 0xA00000 more on a New 3DS; svcControlMemory op 0x10003, linear) and the
 * root heap (what is left after the executable, the main thread's stack and the device memory; op 3 at 0x08000000,
 * which the root allocator takes whole). FUN_0010612c then cuts the heap table (heap_table: nine entries of 0x18
 * bytes, flags at +8, size at +0xC) into fixed heaps: a flags 9 heap from the device memory, a flags 8 heap from the
 * root heap. It adds 0x500000 to Resource's size (the third entry) on a New 3DS: the byte +0x244C of the system object,
 * which FUN_00105b48 sets to FUN_001067a8's answer.
 *
 *   memory_boot_sizes(app, avail, new3ds, device)   called by memory_boot_hook (memory_boot_hook.s) in place of
 *       FUN_001047c0's `sub r0, r4, r5`: app = min(APPMEMALLOC, cap), avail = app less what the process already uses,
 *       new3ds = FUN_001067a8's answer, *device = the game's device memory (the literal, plus 0xA00000 on a New 3DS).
 *       For the row of `app` in memory_boot_rows it writes the row's heap sizes into the table (Resource's less what
 *       FUN_0010612c adds back on a New 3DS, so the heap gets the row's size on both consoles), sets *device to the
 *       sum of the device heaps and returns the root heap's size: avail less the device memory and the row's packs
 *       budget, which no one commits but the packs' loader (on an Old 3DS its window; on a New 3DS, where the packs'
 *       manager does not exist, every pack's pages: pack_loader.c pack_boot reads them all at boot and keeps them).
 *       Without a row for `app`, or with a row that does not fit (a heap under a page or off a page, more than
 *       `avail`), it writes nothing and returns the game's own root heap (avail - *device).
 *
 * Build: tools/build/build_code_space.py (arm-none-eabi-gcc, linked with memory_boot.ld where it places the block);
 * heap_table is named in blocks.py GAME_SYMBOLS, memory_boot_rows is a data block the
 * patcher fills.
 */

typedef unsigned int u32;
typedef unsigned short u16;

#define HEAPS          9          /* the heap table's entries */
#define ROWS           2          /* memory_boot_rows: one row a memory size (memory_boot.py ROWS) */
#define DEVICE_FLAGS   9          /* the flags of a heap in the device memory */
#define RESOURCE       2          /* the table's third entry, "Resource" */
#define NEW3DS_EXTRA   (5u << 20) /* 5 MB, a size: what FUN_0010612c adds to Resource on a New 3DS (0x106238) */
#define PAGE_MASK      0xFFF      /* svcControlMemory takes whole pages; size 0 makes FUN_0010612c skip a heap */

struct heap_entry {               /* FUN_0010612c's table */
    const char *name;
    u32 index;                    /* the heap's slot in the heaps' array */
    u16 flags;
    u16 pad;
    u32 size;
    u32 rest[2];
};

struct memory_row {               /* memory_boot.py ROW_FORMAT */
    u32 app;                      /* min(APPMEMALLOC, cap) this row is for; 0: no row */
    u32 packs;                    /* bytes left out of the root heap, uncommitted: the packs' room */
    u32 sizes[HEAPS];             /* each heap's size, as it is made; 0 keeps the game's */
};

extern struct heap_entry heap_table[HEAPS];
extern const struct memory_row memory_boot_rows[ROWS];

static u32 extra_of(u32 heap, u32 new3ds)
{
    return heap == RESOURCE && new3ds ? NEW3DS_EXTRA : 0;
}

__attribute__((used, section(".text.entry"))) u32 memory_boot_sizes(u32 app, u32 avail, u32 new3ds, u32 *device)
{
    const struct memory_row *row = 0;
    u32 sizes[HEAPS];
    u32 sum = 0;
    u32 i;
    for (i = 0; i < ROWS; i++)
        if (memory_boot_rows[i].app == app)
            row = &memory_boot_rows[i];
    if (!row)
        return avail - *device;
    for (i = 0; i < HEAPS; i++) {
        u32 extra = extra_of(i, new3ds);
        u32 size = row->sizes[i] ? row->sizes[i] : heap_table[i].size + extra;
        if (size <= extra || (size & PAGE_MASK))
            return avail - *device;
        sizes[i] = size;
        if (heap_table[i].flags == DEVICE_FLAGS)
            sum += size;
    }
    if ((row->packs & PAGE_MASK) || sum >= avail || row->packs >= avail - sum)
        return avail - *device;
    for (i = 0; i < HEAPS; i++)
        heap_table[i].size = sizes[i] - extra_of(i, new3ds);
    *device = sum;
    return avail - sum - row->packs;
}
