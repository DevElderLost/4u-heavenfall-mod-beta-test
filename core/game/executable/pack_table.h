/* The packs' table and state bytes (game/executable/packs.py
 * builds them, tests/game/executable/test_packs.py compares this header with it).
 *
 * A pack is code and data kept out of the executable, at a fixed range of its own in the heap region, read from its
 * file into that range when a quest needs it. The resident block `pack_table` holds this table; the variable
 * `pack_state` holds one state byte per slot, which the entry stubs read: 0 while the pack is out (the stub does what
 * the game did), 1 once its bytes are in place and executable (the stub goes into the pack). */
#ifndef PACK_TABLE_H
#define PACK_TABLE_H

#include <stdint.h>

#define PACK_NONE 0xFF          /* no pack: a monster id without one, a pack that needs none */
#define PACK_FILE_SIZE 32       /* a pack's file name in the RomFS, NUL-padded */
#define PACK_STATE_BYTES 64     /* the state bytes: one per slot the packs' range has room for */
#define PACK_STATE_OUT 0
#define PACK_STATE_IN 1
#define PACK_SIDE_QUEST 0
#define PACK_SIDE_TOWN 1
#define PACK_SIDE_SCREEN 2

struct pack_entry {             /* 48 bytes: one per slot, the slot's number is its index */
    uint32_t start;             /* the slot's range: its first address */
    uint32_t room;              /* and its bytes; the file fills `size` of them */
    uint32_t size;              /* the file's bytes, whole pages; 0: no pack of this run in the slot */
    uint8_t slot;
    uint8_t needs;              /* the slot whose pack must be in first (a Deviant's base), or PACK_NONE */
    uint8_t with;               /* the slot whose pack comes in with this one (the small monsters he calls), or PACK_NONE */
    uint8_t side;               /* PACK_SIDE_QUEST (the port machinery's, the ported monsters'): the scene gate frees it
                                 * on the way to the town or the title; PACK_SIDE_TOWN (the town's: the gate loads it as
                                 * a town area starts) and PACK_SIDE_SCREEN (a screen's: loaded as its screen opens,
                                 * one at a time), which the gate frees on the way to a quest */
    char file[PACK_FILE_SIZE];  /* under the game's RomFS, e.g. "packs/alatreon.bin" */
};

struct pack_table {
    uint16_t count;             /* entries */
    uint16_t first_id;          /* the first new monster id */
    uint8_t id_pack[];          /* the slot each new monster id needs (PACK_NONE: none), from first_id, padded to a
                                 * word; the entries follow, PACK_ENTRIES_OFFSET(ids) bytes from the table's start */
};

/* where the entries start, for `ids` new monster ids (new_id.c's ID_LIMIT - FIRST_NEW_ID) */
#define PACK_ENTRIES_OFFSET(ids) (4 + (((ids) + 3) & ~3))

struct pack_vars {              /* 8 bytes: one per slot, after the `count` entries */
    uint32_t start;             /* the pack's variables (VariableSpec.scene the pack's), zeroed at each load */
    uint32_t size;              /* 0: none */
};

/* where the variables' ranges start, after `count` entries */
#define PACK_VARS_OFFSET(ids, count) (PACK_ENTRIES_OFFSET(ids) + (count) * sizeof(struct pack_entry))
/* and the last word: the frames the scene gate waits at most for the quest's last units (tuning.json,
 * memory.scene_gate_frames) */
#define PACK_GATE_OFFSET(ids, count) (PACK_VARS_OFFSET(ids, count) + (count) * sizeof(struct pack_vars))

#endif
