/* The packs' loader: it reads into memory the packs a quest's
 * monsters need and lets go of the loaded packs the quest does not need, over the table `pack_table` and the state
 * bytes `pack_state` (game/executable/pack_table.h). core/game/executable/pack_loader.py places it and hooks the game:
 *
 * - pack_quest_load: new_id_quest_flags (new_id.c) calls it at quest load with the quest's monsters, before the em
 *   data of the new ids load. It first lets go of every loaded pack the quest does not need, when that is safe (below),
 *   then loads every pack the quest needs and lacks: for each, the pack it needs first (a Deviant's base), itself, and
 *   the pack that comes in with it (the small monsters its monster calls).
 * - pack_resource_set_load replaces FUN_0068fd94's call of FUN_00682cc8 (a monster's resource set, read through the
 *   id's entry of the em resources' table, which for a new id lies in his pack): a pack of that id still out loads
 *   first. It covers the in-quest reload (FUN_0065c1b4), which does not call new_id_quest_flags. It only loads.
 *
 * Loading a pack (the same code on every platform), on the main thread:
 *   svc 0x01 COMMIT, read-write, over the pack's bytes; its file `rom:/<file>` read whole through the game's FileStream
 *   (its entry, so the split title's `mod:` comes first and LayeredFS applies); svc 0x54 (the data cache out to
 *   memory), svc 0x70 read+execute (through a duplicated handle of the process), svc 0x94 (the whole instruction
 *   cache); then its state byte, which the entry stubs read. Only the commit and the read decide failure: svc 0x70
 *   fails on Azahar and Citra while the pages run anyway, svc 0x94 is Luma3DS's. Never Luma3DS's range call 0x93: on a
 *   console every core runs it by address in the process it is running, and a core in another process (the file
 *   system's, just done with the pack's read) faults and stops the kernel.
 * Letting go (only here, at quest load): the state byte cleared, svc 0x70 read-write, svc 0x01 FREE (a FREE that fails
 * leaves the pack in). A pack is let go only while no effect core lives, when nothing of it lives (no side of a monster
 * of its ids or of its classes, no live shell of its classes, no shell file of the manager in it), and after
 * proof_shell_mgr_release_files when nothing lives at all (no side, no live shell): the normal case at quest load.
 *
 * - scene_gate replaces FUN_00642c64's `blx r1` (sMhArea's move asking an unstarted area's slot 0x18 whether it can
 *   start): on the way to the town or the title (an area that is not aQuest, with no aQuest on the stack) while a
 *   quest's pack is in, it answers "not yet" (the loading screen stays up) until the quest's last units are deleted,
 *   then ends the effect player's managers (proof_4u_end, the machinery's), waits for their units again, clears the
 *   packs' state bytes, waits for the network's guarded calls (pack_busy, pack_guard.s) and lets go of every quest
 *   pack; then it asks the area. When something of the packs still lives, or past tuning's frames, it keeps them.
 *
 *   The town's side ("As built: code manager step 3"): as a town area (aVillage, aEvent, aArena) is about to start
 *   with no quest's pack in (the quest's let go first, above), the gate loads the town's pack (TOWN_PACK_SLOT); as
 *   aQuest is about to start, it answers "not yet" until the town's last units are deleted, then lets go of the town's
 *   pack and the screen's (past tuning's frames, or with a unit of their classes alive, they stay). The two sides are
 *   never loaded together: a town area while a quest's pack stays gets no town pack (its features do what the game
 *   does), and pack_quest_load lets go of a town's pack that stayed before it loads a quest's.
 * - pack_open: a screen's opening stub (pack_guard.s pack_opening; game/executable/packs.py opening_stub) calls it on
 *   the main thread as its screen opens: a screen's pack still out loads, the other screen's let go first (at most one
 *   screen's pack is in), never while a quest's pack is in.
 * - pack_boot replaces FUN_001046d0's call of the main loop (FUN_00105acc): on a New 3DS every pack in (below).
 *
 * A pack's variables (the table's ranges) are zeroed each time it loads. The port machinery (PORT_PACK_SLOT) lives
 * while the effect player's managers do: it is let go at a quest's load only once they are gone.
 *
 * Only on an Old 3DS. On a New 3DS (the
 * game's own check, FUN_001067a8, whose answer FUN_00105b48 keeps at the system object's +0x244C) nothing of the
 * above lets go or waits: pack_boot (in place of FUN_001046d0's call of the main loop, FUN_00105acc, after the
 * system's set-up) reads every pack of the table once, then runs the game; the scene gate asks the area at once (no
 * wait, no unit killed, no manager ended, no read, no free), a quest's load lets nothing go (its packs are in, so it
 * reads none) and pack_free keeps every pack. memory_boot.c leaves every pack's room out of the root heap there.
 *
 * Failure: a pack that cannot be committed or read stops the game, here, before anything reads it: the range is freed,
 * its state byte stays 0, the game's panic (FUN_0010b3c8) gets the pack's name and the step (on a console it writes
 * 0xDEADBEEF to address 0, Luma3DS's exception screen and dump; emulators go on), then svcBreak (emulators log it),
 * then the thread sleeps for ever. Going on would let the quest's load read the id's tables, which point into the pack.
 *
 * The budget: on a console the commit takes memory the boot left out of the heaps (memory_boot's rows, `packs`,
 * bytes): on an Old 3DS the build makes it the run's window, the larger of its town's side and its worst quest's side
 * with what each pack needs and brings (pack_loader.py run_need); on a New 3DS every pack of the table
 * (pack_loader.py resident_need). A commit past it fails on a console and the game stops.
 * Emulators do not hold a process to its memory limit, so there the commit does not fail.
 */
#include "sdk/types.h"
#include "sdk/enemy_4u.h"
#include "sdk/shell_api.h"
#include "../../game/executable/pack_table.h"

/* FIRST_NEW_ID and ID_LIMIT come from the build (-D: BlockSpec.defines, new_id_data.C_DEFINES) */
#if !defined(FIRST_NEW_ID) || !defined(ID_LIMIT)
#error "pack_loader.c is built with FIRST_NEW_ID and ID_LIMIT (new_id_data.C_DEFINES)"
#endif
#if !defined(PORT_PACK_SLOT) || !defined(TOWN_PACK_SLOT)
#error "pack_loader.c is built with PORT_PACK_SLOT and TOWN_PACK_SLOT (game/executable/blocks.py PACK_SLOTS)"
#endif
#define NEW_IDS (ID_LIMIT - FIRST_NEW_ID)

#define STREAM_WORDS 5              /* nn::fs::FileStream: {file | bit 0, u64 position, u64 size} */
#define OPEN_READ 1
#define PATH_DRIVE_CHARS 5          /* "rom:/" */
#define MEMOP_FREE 1
#define MEMOP_COMMIT 3
#define PERMISSION_RW 3
#define PERMISSION_RX 5
#define CURRENT_PROCESS 0xFFFF8001u
#define USERBREAK_PANIC 0
#define SLEEP_NS 1000000000u        /* the stopped thread's sleep, a second at a time */

s32 file_stream_open(u32 *stream, const u16 *path, u32 mode);       /* FUN_0010baf8: TryInitialize */
s32 file_stream_size(u32 *stream, u64 *size);                       /* FUN_00ceed70 */
s32 file_stream_read(u32 *stream, s32 *read, void *buffer, u32 size);   /* FUN_0047bfb4: bit 31 failure */
void file_stream_close(void *file);                                 /* FUN_0010bbf8: the file's slot 12 */
void game_panic(void *state, const char *format, ...);              /* FUN_0010b3c8 */
extern u8 game_panic_state[];                                       /* its first argument, the game's own */
void game_main_loop(u8 *system);    /* FUN_00105acc: the game's frames until it ends (FUN_001046d0 calls it once) */
extern u8 *game_system;             /* the variable holding the system object (FUN_00105b48 makes it) */
#define SYSTEM_NEW3DS 0x244C        /* its byte: FUN_001067a8's answer, 1 on a New 3DS (set at 0x105BBC) */
u32 enemy_resource_set_load(void *manager, void *set, u32 id);      /* FUN_00682cc8 */
/* the port machinery's, through their entry stubs (blocks.MACHINERY_ENTRIES: 0 while the machinery is out) */
void proof_shell_mgr_release_files(u8 *mgr);                        /* shell_mgr.c */
u32 proof_4u_end(u32 step);                                         /* hook_4u.c */
#define END_UNIT 0              /* proof_4u_end's steps: the registry's unit (0: none), */
#define END_KILL 1              /* that unit killed, */
#define END_MANAGERS 2          /* the managers ended */

extern const struct pack_table pack_table;      /* the blocks of game/executable/packs.py: TABLE */
extern u8 pack_state[PACK_STATE_BYTES];         /* and STATE */
extern u32 pack_busy[PACK_STATE_BYTES];         /* the guarded calls inside each slot's pack (pack_guard.s) */

/* The scene gate's state (blocks.SCENE_GATE_STATE_SIZE) */
struct gate_state {
    u16 phase;
    u16 frames;                 /* frames waited in this phase */
    const u8 *unit;             /* the registry's unit, killed: the gate waits until no line holds it */
    u16 town_phase;             /* the town's side on the way to a quest: TOWN_IDLE, TOWN_DONE */
    u16 town_frames;            /* frames waited for it */
};
extern struct gate_state scene_gate_state;
#define GATE_IDLE 0
#define GATE_UNIT 1             /* the registry's unit killed, waiting for its delete */
#define GATE_FREE 2             /* the managers ended, waiting for their units and the guarded calls */

/* sMhArea and sUnit as the gate reads them (GAME_SYMBOLS) */
extern u8 *mh_area;
extern const u8 quest_area_vtable[];
extern const u8 village_area_vtable[], event_area_vtable[], arena_area_vtable[];    /* the town's areas */
#define AREA_SLOTS 0x3820       /* the area stack's eight slots */
#define AREA_NEXT 0x381C        /* the area about to be pushed */
#define AREA_SLOT_COUNT 8
#define SUNIT_LINE_COUNT 0x614  /* u32: the lines (FUN_00645920) */
#define SUNIT_LINE_FLAGS(n) (0x1C + 0x18 * (n))
#define SUNIT_LINE_FIRST(n) (0x20 + 0x18 * (n))
#define LINE_PAUSED 2           /* a line FUN_0064521c skips */
#define UNIT_STATE 7            /* in the unit's flags (+4): 3 killed, 4 being deleted */
#define UNIT_KILLED 3
#define UNIT_DELETED 4
#define UNIT_NEXT 0x0C
/* the effect player's (sdk/proof_api.h, sdk/enemy_4u.h): proof_sides, proof_live_cores, proof_shell_mgr */

/* The system calls (each a stub: its registers as the kernel takes them) */
s32 pack_svc_memory(u32 op, u32 address, u32 size, u32 permissions);        /* 0x01 ControlMemory */
s32 pack_svc_duplicate(u32 *out, u32 handle);                               /* 0x27 DuplicateHandle */
s32 pack_svc_flush(u32 handle, u32 address, u32 size);                      /* 0x54 FlushProcessDataCache */
s32 pack_svc_protect(u32 handle, u32 address, u32 size, u32 permissions);   /* 0x70 ControlProcessMemory PROT */
s32 pack_svc_close(u32 handle);                                             /* 0x23 CloseHandle */
/* 0x94 Luma3DS: invalidate the whole I-cache (no address: B151); it ignores the range, which the Debug tab's RAM log
 * reads */
s32 pack_svc_icache(u32 address, u32 size);
void pack_svc_break(u32 reason);                                            /* 0x3C Break */
void pack_svc_sleep(u32 low, u32 high);                                     /* 0x0A SleepThread (ns) */

__asm__(
    "    .text\n"
    "    .arm\n"
    "pack_svc_memory:\n"
    "    push {r4, lr}\n"
    "    mov r4, r3\n"
    "    mov r3, r2\n"
    "    mov r2, #0\n"
    "    svc 0x01\n"
    "    pop {r4, pc}\n"
    "pack_svc_duplicate:\n"
    "    str r0, [sp, #-4]!\n"
    "    svc 0x27\n"
    "    ldr r2, [sp], #4\n"
    "    str r1, [r2]\n"
    "    bx lr\n"
    "pack_svc_flush:\n"
    "    svc 0x54\n"
    "    bx lr\n"
    "pack_svc_protect:\n"
    "    push {r4, r5}\n"
    "    mov r5, r3\n"
    "    mov r3, r2\n"
    "    mov r2, #0\n"
    "    mov r4, #6\n"                         /* MEMOP_PROT */
    "    svc 0x70\n"
    "    pop {r4, r5}\n"
    "    bx lr\n"
    "pack_svc_close:\n"
    "    svc 0x23\n"
    "    bx lr\n"
    "pack_svc_icache:\n"
    "    svc 0x94\n"
    "    bx lr\n"
    "pack_svc_break:\n"
    "    svc 0x3C\n"
    "    bx lr\n"
    "pack_svc_sleep:\n"
    "    svc 0x0A\n"
    "    bx lr\n");

static const struct pack_entry *entries(void)
{
    return (const struct pack_entry *)((const u8 *)&pack_table + PACK_ENTRIES_OFFSET(NEW_IDS));
}

static const struct pack_vars *pack_variables(u32 slot)
{
    return (const struct pack_vars *)((const u8 *)&pack_table + PACK_VARS_OFFSET(NEW_IDS, pack_table.count)) + slot;
}

static u32 gate_frames(void)
{
    return *(const u32 *)((const u8 *)&pack_table + PACK_GATE_OFFSET(NEW_IDS, pack_table.count));
}

/* a data memory barrier (ARM11: CP15 c7, c10, 5) */
static void barrier(void)
{
    __asm__ volatile("mcr p15, 0, %0, c7, c10, 5" : : "r"(0) : "memory");
}

static u32 slots(void)
{
    return pack_table.count < PACK_STATE_BYTES ? pack_table.count : PACK_STATE_BYTES;
}

/* the entry of `slot` while this run has a pack there, else 0 */
static const struct pack_entry *entry(u32 slot)
{
    const struct pack_entry *found;

    if (slot >= slots())
        return 0;
    found = entries() + slot;
    return found->size ? found : 0;
}

/* the slot monster id `id` needs, or PACK_NONE */
static u32 id_slot(u32 id)
{
    u32 index = id - pack_table.first_id;

    return id >= pack_table.first_id && index < NEW_IDS ? pack_table.id_pack[index] : PACK_NONE;
}

static u32 loaded(u32 slot)
{
    return pack_state[slot] & PACK_STATE_IN;
}

/* A New 3DS (the game's own check): the packs stay in from the boot, the manager does nothing */
static u32 resident(void)
{
    return game_system && FIELD(u8, game_system, SYSTEM_NEW3DS);
}

static u32 inside(u32 address, const struct pack_entry *pack)
{
    return address - pack->start < pack->room;
}

/* The game stopped with pack `pack`'s name: see the head of the file */
static void __attribute__((noreturn)) pack_stop(const struct pack_entry *pack, const char *step)
{
    game_panic(game_panic_state, "Heavenfall: pack %s could not load (%s)", pack->file, step);
    pack_svc_break(USERBREAK_PANIC);
    for (;;)
        pack_svc_sleep(SLEEP_NS, 0);
}

/* The pack's pages made `permissions` (the data cache flushed first when `flush`), through a duplicated handle of
 * the process as the extension's bootstrap does; the results are ignored */
static void pack_pages(const struct pack_entry *pack, u32 permissions, u32 flush)
{
    u32 handle = 0;

    if (pack_svc_duplicate(&handle, CURRENT_PROCESS) < 0) {
        if (flush)
            pack_svc_flush(CURRENT_PROCESS, pack->start, pack->size);
        return;
    }
    if (flush)
        pack_svc_flush(handle, pack->start, pack->size);
    pack_svc_protect(handle, pack->start, pack->size, permissions);
    pack_svc_close(handle);
}

static void pack_read(const struct pack_entry *pack)
{
    volatile u32 stream[STREAM_WORDS];   /* volatile: plain stores, no memset the block cannot link */
    u16 path[PATH_DRIVE_CHARS + PACK_FILE_SIZE + 1];
    const char *failed = 0;
    const struct pack_vars *vars;
    u64 size = 0;
    s32 got = 0, result;
    u32 file, k;

    if (pack_svc_memory(MEMOP_COMMIT, pack->start, pack->size, PERMISSION_RW) < 0)
        pack_stop(pack, "commit");
    for (k = 0; k < STREAM_WORDS; k++)
        stream[k] = 0;
    path[0] = 'r';
    path[1] = 'o';
    path[2] = 'm';
    path[3] = ':';
    path[4] = '/';
    for (k = 0; k < PACK_FILE_SIZE && pack->file[k]; k++)
        path[PATH_DRIVE_CHARS + k] = (u8)pack->file[k];
    path[PATH_DRIVE_CHARS + k] = 0;
    result = file_stream_open((u32 *)stream, path, OPEN_READ);
    file = stream[0] & ~1u;
    if (result < 0 || !file)
        failed = "open";
    else if (file_stream_size((u32 *)stream, &size) < 0 || size != pack->size)
        failed = "size";
    else if (file_stream_read((u32 *)stream, &got, (void *)pack->start, pack->size) < 0 || (u32)got != pack->size)
        failed = "read";
    if (file)
        file_stream_close((void *)file);
    if (failed) {
        pack_svc_memory(MEMOP_FREE, pack->start, pack->size, 0);
        pack_stop(pack, failed);
    }
    pack_pages(pack, PERMISSION_RX, 1);
    pack_svc_icache(pack->start, pack->size);
    vars = pack_variables(pack->slot);
    for (k = 0; k < vars->size; k++)                    /* its variables as at the game's start */
        ((volatile u8 *)vars->start)[k] = 0;
    pack_state[pack->slot] = PACK_STATE_IN;
}

#define FREED 0
#define BUSY 1                  /* a guarded call is inside: it stays in, ask again */
#define KEPT 2                  /* the FREE failed: it stays in */

/* The state byte cleared, then (no guarded call inside) read-write and FREE; a FREE that fails leaves it in. On a New
 * 3DS nothing is let go: KEPT, untouched */
static u32 pack_free(const struct pack_entry *pack)
{
    if (resident())
        return KEPT;
    pack_state[pack->slot] = PACK_STATE_OUT;
    barrier();
    if (pack_busy[pack->slot]) {
        pack_state[pack->slot] = PACK_STATE_IN;
        return BUSY;
    }
    pack_pages(pack, PERMISSION_RW, 0);
    if (pack_svc_memory(MEMOP_FREE, pack->start, pack->size, 0) < 0) {   /* still mapped: it stays in */
        pack_pages(pack, PERMISSION_RX, 0);
        pack_state[pack->slot] = PACK_STATE_IN;
        return KEPT;
    }
    return FREED;
}

/* Pack `slot` in: the pack it needs first, itself, the pack that comes in with it */
static void pack_need(u32 slot, u32 depth)
{
    const struct pack_entry *pack = entry(slot);

    if (!pack || depth >= slots())
        return;
    if (pack->needs != PACK_NONE)
        pack_need(pack->needs, depth + 1);
    if (!loaded(slot))
        pack_read(pack);
    if (pack->with != PACK_NONE)
        pack_need(pack->with, depth + 1);
}

static u32 live_shells(void)
{
    u32 i;

    if (proof_shell_mgr)
        for (i = 0; i < SMGR_LIVE_MAX; i++)
            if (FIELD(u8 *, proof_shell_mgr, SMGR_LIVE(i)))
                return 1;
    return 0;
}

/* Something of pack `pack` lives: a side of a monster of its ids or of its class, or a live shell of its classes; for
 * the port machinery, the effect player's managers (made at the first ported monster, ended by the scene gate) */
static u32 pack_live(const struct pack_entry *pack)
{
    const u8 *side = proof_sides.first, *monster, *em, *shell;
    u32 n, i;

    if (pack->slot == PORT_PACK_SLOT && (proof_registry || proof_budget || proof_mgr || proof_shell_mgr))
        return 1;
    for (n = 0; side && n < proof_sides.count; n++, side = FIELD(const u8 *, side, SIDE_NEXT)) {
        monster = FIELD(const u8 *, side, SIDE_MONSTER);
        if (!monster)
            continue;
        em = FIELD(const u8 *, monster, ENEMY_EM);
        if (inside(FIELD(u32, monster, 0), pack) || (em && id_slot(FIELD(u8, em, EM_ID)) == pack->slot))
            return 1;
    }
    if (proof_shell_mgr)
        for (i = 0; i < SMGR_LIVE_MAX; i++) {
            shell = FIELD(const u8 *, proof_shell_mgr, SMGR_LIVE(i));
            if (shell && inside(FIELD(u32, shell, 0), pack))
                return 1;
        }
    return 0;
}

/* A shell file of the manager is in pack `pack` */
static u32 pack_filed(const struct pack_entry *pack)
{
    u32 kind, file;

    if (proof_shell_mgr)
        for (kind = 0; kind < SHELL_KINDS; kind++) {
            file = FIELD(u32, proof_shell_mgr, SMGR_FILE(kind));
            if (file && inside(file, pack))
                return 1;
        }
    return 0;
}

static void keep_slot(volatile u8 *keep, u32 slot)
{
    if (entry(slot))
        keep[slot] = 1;
}

/* ---- the two sides (pack_table.h PACK_SIDE_*): a quest's packs, and the town's with the screens' ---- */

/* pack `pack` is on the town's side: the town's, or a screen's */
static u32 town_side(const struct pack_entry *pack)
{
    return pack->side == PACK_SIDE_TOWN || pack->side == PACK_SIDE_SCREEN;
}

/* the run's pack of `slot` on the side `town` (0: a quest's, 1: the town's) */
static const struct pack_entry *side_entry(u32 slot, u32 town)
{
    const struct pack_entry *pack = entry(slot);

    return pack && (town ? town_side(pack) : pack->side == PACK_SIDE_QUEST) ? pack : 0;
}

/* A pack of side `town` is in */
static u32 side_in(u32 town)
{
    u32 slot;

    for (slot = 0; slot < slots(); slot++)
        if (side_entry(slot, town) && loaded(slot))
            return 1;
    return 0;
}

static u32 quest_side_in(void)
{
    return side_in(0);
}

/* `address` lies in a pack of side `town` that is in */
static u32 in_side_pack(u32 address, u32 town)
{
    const struct pack_entry *pack;
    u32 slot;

    for (slot = 0; slot < slots(); slot++)
        if ((pack = side_entry(slot, town)) && loaded(slot) && inside(address, pack))
            return 1;
    return 0;
}

static u32 units_of_packs(u32 town, const u8 *except, const u8 *find);

/* The town's and the screen's packs let go (pack_free): FREED once none is in, BUSY or KEPT for one that stays */
static u32 town_free(void)
{
    const struct pack_entry *pack;
    u32 slot, result = FREED, freed;

    for (slot = 0; slot < slots(); slot++)
        if ((pack = side_entry(slot, 1)) && loaded(slot)) {
            freed = pack_free(pack);
            if (freed == BUSY || (freed == KEPT && result == FREED))
                result = freed;
        }
    return result;
}

/* The loaded packs the quest does not need let go, when safe; then the packs it needs in. `flags`: the quest's
 * monsters, ID_LIMIT bytes (non-zero: in the quest), as quest_monster_flags marks them. A town's pack that stayed past
 * the scene gate goes first, when no unit of its classes lives: the two sides are never in together. On a New 3DS
 * nothing is let go (and the quest's packs, read at boot, are in: none is read). */
void pack_quest_load(const u8 *flags)
{
    volatile u8 keep[PACK_STATE_BYTES];  /* volatile: plain stores, no memset the block cannot link */
    u32 count = slots(), slot, round, id, drop = 0;
    const struct pack_entry *pack;

    if (resident()) {
        for (id = FIRST_NEW_ID; id < ID_LIMIT; id++)
            if (flags[id])
                pack_need(id_slot(id), 0);
        return;
    }
    if (side_in(1) && !units_of_packs(1, 0, 0))
        town_free();

    for (slot = 0; slot < count; slot++)
        keep[slot] = 0;
    for (id = FIRST_NEW_ID; id < ID_LIMIT; id++)
        if (flags[id])
            keep_slot(keep, id_slot(id));
    for (slot = 0; slot < count; slot++)
        if ((pack = entry(slot)) && loaded(slot) && pack_live(pack))
            keep[slot] = 1;
    for (round = 0; round < count; round++)              /* what a kept pack needs, and what comes in with it */
        for (slot = 0; slot < count; slot++)
            if (keep[slot] && (pack = entry(slot))) {
                if (pack->needs != PACK_NONE)
                    keep_slot(keep, pack->needs);
                if (pack->with != PACK_NONE)
                    keep_slot(keep, pack->with);
            }
    for (slot = 0; slot < count; slot++)
        if (side_entry(slot, 0) && loaded(slot) && !keep[slot])
            drop = 1;
    if (drop && !proof_live_cores) {
        if (!proof_sides.count && !live_shells() && proof_shell_mgr)
            proof_shell_mgr_release_files(proof_shell_mgr);
        for (slot = 0; slot < count; slot++)
            if ((pack = side_entry(slot, 0)) && loaded(slot) && !keep[slot] && !pack_filed(pack))
                pack_free(pack);
    }
    for (id = FIRST_NEW_ID; id < ID_LIMIT; id++)
        if (flags[id])
            pack_need(id_slot(id), 0);
}

/* FUN_0068fd94's call of FUN_00682cc8: the id's pack in first */
u32 pack_resource_set_load(void *manager, void *set, u32 id)
{
    pack_need(id_slot(id), 0);
    return enemy_resource_set_load(manager, set, id);
}

/* ---- the scene gate ---- */

#define GATE_KEPT 3             /* the packs stay in until the next quest: the gate lets the areas start */
#define LINES_ROOM ((SUNIT_LINE_COUNT - SUNIT_LINE_FIRST(0)) / 0x18)
#define LINE_UNITS 0x4000       /* a line's units walked at most (a list the game broke ends the walk) */
#define UNIT_LINE(flags) (((flags) & 0x3FF) >> 3)

#define TOWN_IDLE 0
#define TOWN_DONE 1             /* the town's side let go, or kept: the gate lets aQuest start */

static u32 is_area(const u8 *area, const u8 *vtable)
{
    return area && FIELD(const void *, area, 0) == (const void *)vtable;
}

static u32 is_quest(const u8 *area)
{
    return is_area(area, quest_area_vtable);
}

/* aVillage (the Village, the Gathering Hall), aEvent or aArena */
static u32 is_town(const u8 *area)
{
    return is_area(area, village_area_vtable) || is_area(area, event_area_vtable) || is_area(area, arena_area_vtable);
}

/* Area `area` starts the town, an event, the Arena or the title: it is no quest, and no quest is on the stack */
static u32 leaving_quest(const u8 *area)
{
    u32 i;

    if (!mh_area || is_quest(area) || is_quest(FIELD(const u8 *, mh_area, AREA_NEXT)))
        return 0;
    for (i = 0; i < AREA_SLOT_COUNT; i++)
        if (is_quest(FIELD(const u8 *, mh_area, AREA_SLOTS + 4 * i)))
            return 0;
    return 1;
}

static u32 lines(void)
{
    u32 count = FIELD(u32, sunit, SUNIT_LINE_COUNT);

    return count < LINES_ROOM ? count : LINES_ROOM;
}

static u32 line_paused(u32 line)
{
    return line >= lines() || FIELD(u32, sunit, SUNIT_LINE_FLAGS(line)) & LINE_PAUSED;
}

/* A killed unit waits for its delete on a line the game passes (FUN_0064521c: killed, then deleted the next pass) */
static u32 units_pending(void)
{
    const u8 *unit;
    u32 line, k, state;

    for (line = 0; line < lines(); line++) {
        if (line_paused(line))
            continue;
        for (unit = FIELD(const u8 *, sunit, SUNIT_LINE_FIRST(line)), k = 0; unit && k < LINE_UNITS;
             unit = FIELD(const u8 *, unit, UNIT_NEXT), k++) {
            state = unit_flags(unit) & UNIT_STATE;
            if (state == UNIT_KILLED || state == UNIT_DELETED)
                return 1;
        }
    }
    return 0;
}

/* A unit of a class of a pack of side `town` (0: a quest's, 1: the town's or a screen's) lives, on any line, but
 * `except`; with `find`, whether `find` is on a line (its pointer only: it may be deleted) */
static u32 units_of_packs(u32 town, const u8 *except, const u8 *find)
{
    const u8 *unit;
    u32 line, k;

    for (line = 0; line < lines(); line++)
        for (unit = FIELD(const u8 *, sunit, SUNIT_LINE_FIRST(line)), k = 0; unit && k < LINE_UNITS;
             unit = FIELD(const u8 *, unit, UNIT_NEXT), k++) {
            if (find ? unit == find : unit != except && in_side_pack(FIELD(u32, unit, 0), town))
                return 1;
        }
    return 0;
}

static u32 packs_live(void)
{
    return proof_live_cores || proof_sides.count || live_shells();
}

static void gate_reset(void)
{
    scene_gate_state.phase = GATE_IDLE;
    scene_gate_state.frames = 0;
    scene_gate_state.unit = 0;
}

/* The packs stay in (something of them lives, or the wait is over): 1, the area may be asked */
static u32 gate_keep(void)
{
    if (scene_gate_state.phase == GATE_UNIT)        /* its unit killed: the managers end with it (its delete runs */
        proof_4u_end(END_MANAGERS);                 /* later, with the machinery in) */
    scene_gate_state.phase = GATE_KEPT;
    return 1;
}

/* One frame of the gate: 0 while it waits, 1 once the quest's packs are out or stay in */
static u32 gate_step(void)
{
    struct gate_state *gate = &scene_gate_state;
    const struct pack_entry *pack;
    const u8 *unit;
    u32 slot, busy = 0;

    if (gate->frames++ >= gate_frames())
        return gate_keep();
    if (gate->phase == GATE_IDLE) {
        if (units_pending())
            return 0;
        if (packs_live())
            return gate_keep();
        unit = (const u8 *)proof_4u_end(END_UNIT);
        if (units_of_packs(0, unit, 0) || (unit && line_paused(UNIT_LINE(unit_flags(unit)))))
            return gate_keep();
        if (unit) {
            proof_4u_end(END_KILL);
            gate->unit = unit;
            gate->phase = GATE_UNIT;
            return 0;
        }
        proof_4u_end(END_MANAGERS);
        gate->phase = GATE_FREE;
        return 0;
    }
    if (gate->phase == GATE_UNIT) {
        if (units_of_packs(0, 0, gate->unit))
            return 0;
        proof_4u_end(END_MANAGERS);
        gate->phase = GATE_FREE;
        return 0;
    }
    if (units_pending())                            /* GATE_FREE: the managers' own units, killed as they ended */
        return 0;
    if (packs_live() || units_of_packs(0, 0, 0))
        return gate_keep();
    for (slot = 0; slot < slots(); slot++)
        if ((pack = side_entry(slot, 0)) && loaded(slot) && !pack_filed(pack))
            busy |= pack_free(pack) == BUSY;
    if (busy)
        return 0;
    gate->phase = GATE_KEPT;                        /* done: what failed to go stays */
    return 1;
}

static void town_reset(void)
{
    scene_gate_state.town_phase = TOWN_IDLE;
    scene_gate_state.town_frames = 0;
}

/* One frame of the town's side on the way to a quest: 0 while it waits for the town's last units' delete, 1 once its
 * packs are out or stay in (a unit of their classes alive, the wait over, a FREE that failed) */
static u32 town_step(void)
{
    struct gate_state *gate = &scene_gate_state;

    if (gate->town_frames++ < gate_frames()) {
        if (units_pending())
            return 0;
        if (!units_of_packs(1, 0, 0) && town_free() == BUSY)
            return 0;
    }
    gate->town_phase = TOWN_DONE;
    return 1;
}

/* The town's pack in, as a town area starts with no quest's pack in */
static void town_load(void)
{
    const struct pack_entry *pack = side_entry(TOWN_PACK_SLOT, 1);

    if (pack && pack->side == PACK_SIDE_TOWN && !loaded(TOWN_PACK_SLOT))
        pack_read(pack);
}

/* FUN_00642c64's call of an unstarted area's slot 0x18 (`ready`: 0 while it cannot start); on a New 3DS the area is
 * asked at once */
u32 scene_gate(u8 *area, u32 (*ready)(u8 *))
{
    if (resident())
        return ready(area);
    if (is_quest(area)) {                           /* a quest: the town's side out first */
        gate_reset();
        if (!side_in(1))
            town_reset();
        else if (scene_gate_state.town_phase != TOWN_DONE && !town_step())
            return 0;
        return ready(area);
    }
    town_reset();
    if (!quest_side_in() || !leaving_quest(area))
        gate_reset();
    else if (scene_gate_state.phase != GATE_KEPT && !gate_step())
        return 0;
    if (is_town(area) && leaving_quest(area) && !quest_side_in())
        town_load();
    return ready(area);
}

/* A screen's opening stub (pack_guard.s pack_opening), on the main thread: its pack in when it is out, the other
 * screen's let go first; nothing while a quest's pack is in, or while the other screen's stays (a FREE that failed) */
void pack_open(u32 slot)
{
    const struct pack_entry *pack = entry(slot), *other;
    u32 k;

    if (!pack || pack->side != PACK_SIDE_SCREEN || loaded(slot) || quest_side_in())
        return;
    for (k = 0; k < slots(); k++)
        if (k != slot && (other = entry(k)) && other->side == PACK_SIDE_SCREEN && loaded(k) &&
            pack_free(other) != FREED)
            return;
    pack_read(pack);
}

/* FUN_001046d0's call of the game's main loop, once the system is set up (`rom:` mounted, the heaps cut, the
 * application made) and before its first frame: on a New 3DS every pack of the table in first, each read once and
 * never let go; on an Old 3DS nothing (the gate, a quest's load and a screen's opening read them) */
void pack_boot(u8 *system)
{
    const struct pack_entry *pack;
    u32 slot;

    if (resident())
        for (slot = 0; slot < slots(); slot++)
            if ((pack = entry(slot)) && !loaded(slot))
                pack_read(pack);
    game_main_loop(system);
}
