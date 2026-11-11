"""Where the executable depends on a monster id, and the blocks a new id needs: data
only, so that game/executable/blocks.py can declare the blocks. new_id.py patches these places.

The update knows ids 0-123. Every table indexed by a monster id has 124 entries (some 123); new ids are
FIRST_NEW_ID to ID_LIMIT - 1. ID_LIMIT is 200 (the hard ceiling is 254, the id being a
byte). The game's save keeps 128 hunt, capture and size records (SAVE_IDS): ids 128-199 never reach its arrays (the
save functions' bounds stay as they are).
"""

from __future__ import annotations

from dataclasses import dataclass

FIRST_NEW_ID = 124
ID_LIMIT = 200
SAVE_IDS = 128                 # the ids the game's save keeps hunt, capture and size records for
NEW_IDS = ID_LIMIT - FIRST_NEW_ID
NO_MONSTER = 0                 # id 0: the entry new ids get when they copy no monster
C_DEFINES = (f"FIRST_NEW_ID={FIRST_NEW_ID}", f"ID_LIMIT={ID_LIMIT}")     # new_id.c's macros (BlockSpec.defines)


@dataclass(frozen=True)
class IdTable:
    """A static table with one entry of `entry` bytes per monster id, read through the literal-pool
    words `refs` (each holds `address`, or an address inside its first FIRST_NEW_ID entries)."""
    name: str
    address: int
    entry: int
    refs: tuple[int, ...]
    what: str
    count: int = FIRST_NEW_ID      # entries the game has (123 for some)
    pointers: bool = False         # its entries are addresses of the game's data

    @property
    def size(self) -> int:
        return ID_LIMIT * self.entry


ID_TABLES = (
    IdTable("em_resources", 0xEFBD08, 4, (0x682FF8, 0x68D910, 0xC0BA48),
            "the monster's resource set (model, motion lists, command table, effects, sounds): "
            "FUN_00682cc8, FUN_0068d8fc, FUN_00c0b880", pointers=True),
    IdTable("em_data_paths", 0xEFC268, 4, (0x6895C0,),
            "the paths of its etd/emd (enemy\\emNNN\\data\\emNNN, shared by variants): FUN_006894b8",
            pointers=True),
    IdTable("crowns", 0xF32008, 16, (0x688848,), "the size thresholds of the crowns: FUN_006887a4"),
    IdTable("ui_textures", 0xFB7A70, 4, (0xC0BA3C,), "two counts of textures the UI loads: FUN_00c0b880"),
    IdTable("hud_kind", 0xDEEF04, 1, (0xB9B5DC,), "a byte the HUD reads: FUN_00b9b390"),
    IdTable("quest_points", 0xFC96DC, 1, (0x6A6BC4,), "points a hunt adds to the quest: FUN_006a6a18"),
    IdTable("sound_ranges", 0xFCD71C, 8, (0x30F6CC,), "two floats per monster for its sounds: FUN_0030f4f0",
            123),
    IdTable("part_sets", 0xFFEAA4, 4, (0x93F50C,),
            "per-part data, em+0x7731 entries: FUN_0093f388 (88 entries; other tables follow)", 88, pointers=True),
    # nine s16 tables of 123 entries each (id 123 reads the next table's first), one per quest rank
    # and use, next to em->mPerfectVirusWaitTimer (em+0x7AE0): Frenzy timers, read at `user`
    *(IdTable(f"frenzy_{n}", address, 2, (ref,), f"s16, Frenzy (em+{field}), read at {user:#x}", 123)
      for n, (address, ref, field, user) in enumerate((
          (0xFFECB8, 0x9482C0, "0x7AF4", 0x948198), (0xFFEDAE, 0x9482D0, "0x7AF4", 0x948284),
          (0xFFEEA4, 0x94C974, "0x7AE8", 0x94C8A8), (0xFFEF9A, 0x948374, "0x7AF4", 0x948348),
          (0xFFF090, 0x94CA20, "0x7AE8", 0x94C9F4), (0xFFF186, 0x9482CC, "0x7AF4", 0x948228),
          (0xFFF27C, 0x94C97C, "0x7AE8", 0x94C94C), (0xFFF372, 0x948370, "0x7AF4", 0x948328),
          (0xFFF468, 0x94CA1C, "0x7AE8", 0x94C9D4)))),
    IdTable("shell_sets", 0x1003BEC, 4, (0x684BA8, 0x92636C),
            "the monster's shell records (index into 0x1002A5C): FUN_00926044, FUN_00684b68", pointers=True),
    IdTable("effect_base_a", 0x1003DDC, 2, (0x912290,), "s16 index into 0x1002A5C: FUN_00911f58"),
    IdTable("effect_base_b", 0x1003ED4, 2, (0x9358F4,), "s16 index into 0x1002A5C: FUN_009357ec"),
    # reached from the quest's monster ids, not from em's
    IdTable("icons", 0xE06698, 1, (0xC0E260, 0xC0E884),
            "the monster's icon (0x7F: none); FUN_00c0e1b4 and FUN_00c0e850 read the moved table (ICON_READERS)"),
    IdTable("hunt_points", 0xE067F4, 2, (0x6968BC,), "u16 points of a hunt: FUN_006968ac, from FUN_006b4110"),
    IdTable("hunt_tier", 0xE070A4, 1, (0x6B87E4,), "a rank 0-4 (0xFF: none) the quest compares: 0x6B83E8"),
    IdTable("hunt_class", 0xE07120, 1, (0x6B464C,), "a class byte (17, 18, 20, 33, 36, 40): FUN_006b4110"),
    IdTable("quest_rewards", 0xE07708, 10, (0x6A2818, 0x6A28D4), "five u16 per monster: 0x6A2808"),
    IdTable("target_kind", 0xE0FE8C, 1, (0xC56F30,),
            "a flag byte the target camera reads; FUN_00c564ec copies it to the stack twice and reads the table "
            "instead (TABLE_INDEXES)"),
    IdTable("part_records", 0xF384D0, 4, (0x68F05C,), "an offset per monster (-1: none): FUN_0068effc"),
    IdTable("quest_monster", 0xFBF5C8, 30,
            (0x6A06A8, 0x6A2F9C, 0x6A6D28, 0x6A9AF4, 0x6A9AF8, 0x6B4644, 0x6B55EC, 0x6B6430, 0x6B799C, 0x6B7EFC,
             0x6BC144),
            "a flag mask (+0), the points of a hunt by rank (+2, +4), records from +6: FUN_006b4110 and the "
            "quest manager (0x6A9AF4 holds the table + 0x100)"),
    IdTable("quest_special", 0xFC07C9, 1, (0x6B55F0, 0x6B6434, 0x6BC148),
            "an index into 0xFC0846 (40-byte records; 0xFF: none): 0x6B62A8, 0x6BBF5C"),
)

# The em data (etd/emd) loaded per monster id: a pointer per id to two words (variants 0 and 1) that
# FUN_006894b8 fills and FUN_00688854 reads. The pointer array is reached through the .data word
# EM_DATA_SLOTS_CELL (FUN_00688854, FUN_006894b8) and the literal of FUN_0068dfa4 (the unload loop).
# The new ids' slots must be writable: extend_tables takes their address (the variable new_id_em_data).
EM_DATA_SLOTS = 0xF3A024
EM_DATA_SLOTS_CELL = 0xF3A020
EM_DATA_SLOTS_REFS = (0x68E088,)
EM_DATA_VARIANTS = 2

# `cmp rX, #0x7C` that must let the new ids through: the crown table's check, the sound ranges' check,
# the unload loop over the em data slots, the hunt notice. Not 0xAC93EC (FUN_00ac90c8, the quest end's loop that adds
# each id's hunts and captures to the save) nor 0x615BD8 (FUN_00615bd4, the hunting log's sizes): with them the save's
# arrays would be written past id 127; they keep their bound.
BOUND_RAISES = {
    0x6887A8: "FUN_006887a4: crowns",
    0x30F544: "FUN_0030f4f0: sound ranges",
    0x68E07C: "FUN_0068dfa4: unload loop over the em data slots",
    0xB9D700: "FUN_00b9d6f4: the hunt notice (count of the monster's kills in the quest)",
}
CMP_IMM_MASK, CMP_IMM = 0x0FF0FFFF, 0x0350007C   # cmp rX, #0x7C


@dataclass(frozen=True)
class IconReader:
    """FUN_00c0e850 (id in r4) and FUN_00c0e1b4 (id in r2) copied 0x7C bytes of the icons table to a frame of exactly
    0x80 bytes and indexed the copy; they read the moved table in place. r1 holds its address (the literal
    extend_tables retargets) from the copy's setup to the indexed load, with no call between once the copy's two
    words (`copy`: `mov r0, sp`, `bl memcpy`) are nops. `bound` is `cmp rI, #0x7C` (rI the id: `compare`), which becomes
    `cmp rI, #ID_LIMIT`; `load` is `ldrblt r0, [sp, rI]`, which becomes `ldrblt r0, [r1, rI]`."""
    name: str
    copy: tuple[int, int]
    bound: int
    compare: int
    load: int
    stack_load: int
    table_load: int


ICON_READERS = (
    IconReader("FUN_00c0e850: the icon", (0xC0E864, 0xC0E868), 0xC0E86C, 0xE354007C, 0xC0E874, 0xB7DD0004, 0xB7D10004),
    IconReader("FUN_00c0e1b4: the icon (sprite)", (0xC0E200, 0xC0E204), 0xC0E20C, 0xE355007C, 0xC0E214, 0xB7DD0002,
               0xB7D10002),
)
MOV_R0_SP = 0xE1A0000D                                  # mov r0, sp, the memcpy's destination
MOV_IMM_MASK, MOV_IMM = 0x0FFF0FFF, 0x03A0007C   # mov rX, #0x7C
# Where a stack copy of an id table is indexed, the copy's base `add r1, sp, #0xC` becomes `ldr r1, [pc, #x]`, the
# literal the copy was made from (the table's address, which extend_tables points at the copy in the extension):
# every id reads the extended table, whatever the copy's size. FUN_00c564ec (the target camera) copies target_kind,
# 0x7C bytes to sp+0xC, at 0xC56CD0 and at 0xC56DAC, and reads `ldrb r0, [r1, r0]` with r0 the monster's id;
# indexing the copy, a new id read stack bytes past it. Address of the `add` -> address of the literal.
TABLE_INDEXES = {
    0xC56CE4: 0xC56F30,
    0xC56DC0: 0xC56F30,
}
# The icon cells: the atlas' right block holds indices 99 to 99 + RIGHT_BLOCK_CELLS - 1 (cells 124-196 are free, 127 is
# the readers' "no icon"); FUN_00c0e8fc stops it at 0xC0E970 (`cmp r0, #0x19` after `sub r0, r1, #0x63`).
RIGHT_BLOCK_FIRST = 99
RIGHT_BLOCK_CELLS = 0x62
RIGHT_BLOCK_BOUND = 0xC0E970
RIGHT_BLOCK_WORD = 0xE3500019                     # cmp r0, #0x19
# The pictures of the quest board and the quest-info screen are icon indices, checked `< 124` (and not 98) at 17 places
# (`cmp rX, #0x7C`): they let the right block's indices through up to ICON_END - 1.
ICON_END = RIGHT_BLOCK_FIRST + RIGHT_BLOCK_CELLS
BOARD_PICTURE_BOUNDS = (
    0x224BCC,                                                         # FUN_00224b14: the quest-info screen
    0x9F4434, 0x9F444C, 0x9F446C, 0x9F448C, 0x9F44AC,
    0xA633DC, 0xA633F4, 0xA63414, 0xA63434, 0xA63454,
    0xA6E324, 0xA6E33C, 0xA6E35C, 0xA6E37C, 0xA6E39C,
    0xC0E580,
)
ADD_R1_SP_C = 0xE28D100C                          # add r1, sp, #0xC
LDR_R1_PC = 0xE59F1000                            # ldr r1, [pc, #+x]

# The quest manager's kill records: KILLS_ENTRY bytes per id at quest + KILLS (u16 largest size, smallest
# size, hunts, captures), ids 0-123; another array follows at once (quest+0xB2E4, 0x128 bytes). Every
# place that reaches an entry computes `add rD, rB, rI, lsl #3` (rI the id) and adds a constant; KILL_SITES
# maps each to the offset of the entry from rB (KILLS when rB is the quest manager, 0 when it is the array).
# Each such instruction goes to a stub (kill_stub) that leaves ids 0-123 as they were and sends the new
# ids to the variable new_id_kills. KILL_CLEARS: the two loops that clear the array (`mov rX, #0x7C`, the
# count), sent to a stub that clears new_id_kills too.
KILLS = 0xAF04
KILLS_ENTRY = 8
KILL_SITES = {
    0x6A28F4: KILLS, 0x6A2918: KILLS, 0x6A2940: KILLS, 0x6A2968: KILLS, 0x6A2990: KILLS,  # FUN_006a28d8: the
    # quest's targets hunted (its objectives)
    0x6A6A78: KILLS,    # FUN_006a6a18
    0x6B4120: KILLS,    # FUN_006b4110(quest, id, captured, size, ...): records a hunt or a capture
    0xAC90FC: 0,        # FUN_00ac90c8: quest end, the save's hunts and captures
    0xACA424: 0,        # 0xACA400: the quest's five monsters
    0xB9D714: 0,        # FUN_00b9d6f4: the hunt notice
}
KILL_CLEARS = (0x6BB098, 0x6BCF14)
ADD_LSL3_MASK, ADD_LSL3 = 0xFFF00FF0, 0xE0800180    # add rD, rB, rI, lsl #3
KILL_STUB = 12 * 4
CLEAR_STUB = 16 * 4

# The monster's theme: FUN_0030e16c(manager, id, u8 *queue, u32 *request), a switch on the id that writes the
# queue and the request and returns nothing. Its first instruction goes to a stub (theme_stub) that gives a new
# id the theme of another id (`themes`) or a request of the battle queue of its own (`requests`).
THEME = 0x30E16C
THEME_STUB = 13 * 4 + 2 * NEW_IDS
BATTLE_QUEUE = 2               # bgm_bat

# The factory (FUN_00690228): `cmp r8, #0x7C; ldrlo pc, [pc, r8, lsl #2]; b FACTORY_FAIL`.
FACTORY_DEFAULT = 0x6902A8
FACTORY_FAIL = 0x69144C

# The quest's monsters to load (FUN_006a74f8(quest, flags)): flags[id] = 1 for each id, no check, into
# a 124-byte array; its two callers then load the em data of each flagged id up to 123.
QUEST_FLAGS = 0x6A74F8
QUEST_FLAGS_CALLS = (0x65BD98, 0x65CC78)

# Functions that write a per-id array inside an object; a new id would write past it. The id is their
# GUARD_REGISTER and they return nothing: a stub at their entry (guard_stub) returns at once for a new id.
GUARDS = {
    0xC234B0: "save+0xF1B4+id, a byte the save counts when the monster carts the hunter: FUN_00b5535c",
    0x9868C4: "hunter work +0xB48+id, a byte (an item from a living monster, once or twice per quest): "
              "FUN_009a19d8",
}
GUARD_REGISTER = 1
GUARD_STUB = 4 * 4

# The engine's places that treat a species apart by comparing the monster's id with constants: each listed
# `cmp rX, #imm` (rX the id) goes to a stub (alias_stub) that first turns a new id into the id it stands for
# (`aliases`), so that the new id is treated as that one. Those of the Fatalis family outside its class.
ALIAS_SITES = {
    0x3090B4: "FUN_00308744: the music, the monsters whose theme starts with the fight (24, 33, 46, 77-79, ...)",
    0x392BA0: "FUN_00392508: the monster's events (78: case 0x1C)",
    0x943998: "FUN_009431f4: command condition 0x65 (78 only)",
    0x68B39C: "FUN_0068b394: the giant monsters (24, 46, 77-79, 83, 89, 110, 111, 117)",
}
# Sites where a new id aliased to one of the ids given skips the comparison: it runs the instructions given, then
# goes to the address (the other aliased ids compare as the id they stand for).
# The music (0x3090B4): the species whose theme starts with the fight (THEME_AT_FIGHT) go to 0x30915C, which plays
# nothing while the monster has just spotted the hunter (mMode 2). A new id standing for one sets the frame's mode
# ([sp, #0x28]) to 1, as if it fought, and goes on at 0x309168, which starts its theme at once (probe Z1: Alatreon's
# five seconds of silence on first sight; with mode 2 kept, the state would be 2, the discovery loop). A new id
# standing for another species (Mizutsune for Zinogre) keeps its discovery loop.
THEME_AT_FIGHT = frozenset({24, 33, 46, 77, 78, 79, 82, 83, 110, 111, 116, 117})
ALIAS_JUMPS = {
    0x3090B4: (0x309168, (0xE3A00001, 0xE58D0028), THEME_AT_FIGHT),     # mov r0, #1; str r0, [sp, #0x28]
}
ALIAS_TAIL = 3                                          # words after the comparison: ALIAS_JUMPS' and a branch
CMP_ANY_MASK, CMP_ANY = 0x0FF0F000, 0x03500000   # cmp rX, #imm
ALIAS_STUB = (2 + 2 * NEW_IDS + 2 + ALIAS_TAIL) * 4      # the guard of the game's ids, the new ids', the comparison

# The monster's name: FUN_005a91ac(text, id) sets `text` to entry `id` of emName (message file 6). A stub at its
# entry (name_stub) gives a new id the entry of `names` instead (an unused entry the mod rewrites). Its first
# instruction loads a literal (`ldr r2, [pc, #0x28]`): the stub loads the same value.
NAME_GETTER = 0x5A91AC
NAME_STUB = 7 * 4 + NEW_IDS

SOURCE = "monsters/porting/new_id.c"     # under core/


def block_specs() -> list[tuple[str, str | None, int]]:
    """(name, source, size) of every block new_id.patch places: its code (src/new_id.c, size 0), the factory's
    cases, the stubs and the extended tables. All are read-only once placed."""
    return [("new_id_code", SOURCE, 0),
            ("new_id_cases", None, 4 * NEW_IDS),
            ("new_id_em_data_slots", None, 4 * ID_LIMIT),
            ("new_id_kill_stubs", None, KILL_STUB * len(KILL_SITES) + CLEAR_STUB * len(KILL_CLEARS)),
            ("new_id_theme", None, THEME_STUB),
            ("new_id_guards", None, GUARD_STUB * len(GUARDS)),
            ("new_id_aliases", None, ALIAS_STUB * len(ALIAS_SITES)),
            ("new_id_name", None, NAME_STUB),
            *((f"new_id_{t.name}", None, t.size) for t in ID_TABLES)]
