"""Skip the intro (option skip_intro): a new character starts in Val Habar, registered with the Guild.

Without it a new character plays the prologue on the sand ship (quest 100), arrives in Val Habar and must
register with the Guildmaster before the Gathering Hall and online play open. The routine
gameplay/new_game_skip/new_game_skip.s, hooked at the end of the character creation, leaves the new save as the
retail game leaves it after the registration: the story flags those steps set, quest 100 cleared, the
1500z and the armor the prologue gives, and hunter rank 1. Saves created before the mod, or with the
option off, are not affected. Patched in the update's executable only. Findings, and how the values below
were measured:

With skip_caravan_tutorial as well, the character also has what the Caravaneer's talk and his two first
deliveries leave (gameplay/new_game_skip/new_game_tutorial.s, in the extension): quests 11-24, 101 and 102 cleared,
their story flags and the first Palico, equipped. The cat is equipped only then, never with skip_intro alone.
"""

import struct

from core.game.executable.code_space import BASE_ADDRESS, Layout, bl_target, load_layout

# FUN_00b7961c (character creation), state 5: the last call, FUN_00c25b50(save, profile).
HOOK = 0xB79B2C
NEW_PROFILE = 0xC25B50
# First bytes of the game functions the routine calls (blocks.GAME_SYMBOLS): the update's executable.
SIGNATURES = {
    0xC25B50: "70402de95c4090e2",  # FUN_00c25b50, new profile
    0xC1B0E8: "5c2090e21eff2f01",  # FUN_00c1b0e8, set story flag
    0xC1F170: "5cc090e21eff2f01",  # FUN_00c1f170, set quest cleared
    0xC25918: "10402de9ac409fe5",  # FUN_00c25918, first free equipment box slot
    0xC1E274: "f0472de960d04de2",  # FUN_00c1e274, mark equipment obtained
    0xC1B26C: "f0472de9015c81e2",  # FUN_00c1b26c, worn pieces from their box indices
}

FUNDS = 1500      # zenny after the prologue (a new save has 0)
HUNTER_RANK = 1   # set by the registration (0 before)
# The prologue's armor (type, id, word 4): the five pieces of armor 1, in the order the game adds them.
ARMOR = tuple((armor_type, 1, 0xFFBC) for armor_type in (5, 1, 2, 3, 4))
QUESTS_CLEARED = (100,)  # the prologue ("???", rank 1, type 3)
# Story flags set from the character creation to the first visit of the Gathering Hall, measured on save states. Not
# listed: 0x514-0x51B (set whenever a save loads).
STORY_FLAGS = (
    0x000,  # prologue started (FUN_00a661a4 starts quest 100 while it is off)
    0x001, 0x002, 0x1B8, 0x2E1,  # Val Habar arrival events
    0x1B9, 0x21E,  # Guild registration
    0x522, 0x523, 0x524, 0x527, 0x528, 0x529, 0x52A, 0x52B, 0x52C, 0x52D, 0x52E, 0x534, 0x535,
    0x538, 0x539, 0x53D,  # prologue tutorial prompts (cleared whenever quest 100 starts)
    0x581, 0x5B6,  # talks during the prologue
    0x5BA,  # arrival in Val Habar seen (FUN_00a661a4 plays it while it is off)
    0x8B4,  # Gathering Hall visited (its introduction; online play waits for it)
)
DATA_SIZE = 0x64  # blocks.py, new_game_data
# A skip that stops at the arrival in Val Habar (prologue_only) leaves these to the town, which plays their events from
# them: the arrival (the Caravaneer's first talk), the registration with the Guild (which gives hunter rank 1) and the
# Gathering Hall's introduction. The arrival seen (0x5BA) stays set: the character creation's load then takes the
# town's own path (FUN_00b7e290 asks FUN_009ed0b8), and no quest's return plays the arrival later (0xB7D994).
ARRIVAL_FLAGS = (0x001, 0x002, 0x1B8, 0x2E1, 0x1B9, 0x21E, 0x8B4)

# ---- The caravan tutorial (option skip_caravan_tutorial) ----
# Measured on a retail character right after the Caravaneer's deliveries (a save and two emulator states). Training
# quests 11-24, then quests 101 and 102.
TUTORIAL_QUESTS = (*range(11, 25), 101, 102)
# Story flags of the opening of the caravan.
TUTORIAL_FLAGS = (
    0x003, 0x004,  # the steak and the Mega Potion delivered (FUN_009e1194 sets each with 0x2D2 / 0x2D3)
    0x005, 0x006,  # the next steps of the same hint chain (FUN_00a3e7b8 stage 1: 3 -> 4 -> 5 -> 6)
    0x008, 0x009,  # copies of 3 and 4 (FUN_00a05358 sets 8 / 9 with the next event flag)
    0x00A, 0x00E,  # early story flags set in the same stretch (read by event scripts only)
    0x1BA, 0x1BD,  # Val Habar events after the registration
    0x2D2, 0x2D3,  # steak delivered, Mega Potion delivered
    0x2D4, 0x2D5,  # a steak / a Mega Potion was in the pouch (FUN_00a05b68)
    0x41B,         # set by FUN_00a2b6dc once 0xE is set
    0x44C, 0x44D, 0x44E, 0x453, 0x51D, 0x51E,  # undetermined: set in the retail character at that point
)
# Offsets in the save data (save + 0x5C).
PALICO_GEAR_BOX = 0xBB4E  # the Palico equipment box: 600 x (u16 type, u16 id), a new save has 0xFF in each first byte
MAIN_PALICO = 0xC4B0      # the main Palico's 0xE8 bytes (exists when u8 +0x30 is 1)
STRINGER_SLOTS = 0xF1DC   # 5 x u8 index in the Palico list of the stringer cats, 0xFF = none (a new save has 0)
MAIN_PALICO_SIZE = 0xE8
PALICO_NAME = "Meow"      # up to 12 UTF-16 characters at +0x00; the player can rename the cat in the game
PALICO_STATUS_EQUIPPED = 0x0001  # u16 at +0x32, bit 1: goes on quests (FUN_00a051a0: the others rest and recover)
# The first Palico's gear (Felyne body 2, head 2, weapon 2): (type, id) as the box lists them, and the pieces
# worn, in the order of the record's (type, id) pairs at +0x34 (body, weapon, head) with their box indices at +0x40.
PALICO_GEAR = ((2, 2), (1, 2), (0, 2))
PALICO_WORN = ((2, 2), (0, 2), (1, 2))
PALICO_WORN_INDICES = (0, 2, 1)
PALICO_COLORS = bytes.fromhex("f0f0f0ff8ba150ff")  # +0x20: the game's default fur colors (the same in a late save)
PALICO_ENTHUSIASM = 99  # u8 at +0x48: the cat is rested (a quest it stays out of gives it 25)
TUTORIAL_DATA_SIZE = 0x180  # blocks.py, new_game_tutorial_data
END_OF_POKES = 0xFFFFFFFF


class NewGameSkipError(ValueError):
    pass


def new_game_data(prologue_only: bool = False) -> bytes:
    """The data block the routine reads (gameplay/new_game_skip/new_game_skip.s). `prologue_only`: what the sand ship
    leaves, without the arrival's, the registration's and the Gathering Hall's flags (ARRIVAL_FLAGS) and the hunter
    rank."""
    data = struct.pack("<IH", FUNDS, 0 if prologue_only else HUNTER_RANK)
    data += b"".join(struct.pack("<3H", *piece) for piece in ARMOR) + struct.pack("<H", 0)
    data += b"".join(struct.pack("<H", quest) for quest in QUESTS_CLEARED) + struct.pack("<H", 0xFFFF)
    flags = [flag for flag in STORY_FLAGS if not (prologue_only and flag in ARRIVAL_FLAGS)]
    data += b"".join(struct.pack("<H", flag) for flag in flags) + struct.pack("<H", 0xFFFF)
    if len(data) > DATA_SIZE:
        raise NewGameSkipError(f"new_game_data is {len(data)} bytes, its block {DATA_SIZE}")
    return data.ljust(DATA_SIZE, b"\0")


def main_palico() -> bytes:
    """The first Palico's 0xE8-byte record as the retail game leaves it after the tutorial (the fields measured on a
    retail character), equipped, with no experience: a name, the default fur, one cat, and the three starting
    pieces of Felyne gear worn."""
    record = bytearray(MAIN_PALICO_SIZE)
    name = PALICO_NAME.encode("utf-16-le")
    record[:len(name)] = name
    record[0x20:0x28] = PALICO_COLORS
    record[0x2F] = 0xFF
    struct.pack_into("<HH", record, 0x30, 1, PALICO_STATUS_EQUIPPED)  # exists, status
    struct.pack_into("<6H", record, 0x34, *(value for piece in PALICO_WORN for value in piece))
    struct.pack_into("<3H", record, 0x40, *PALICO_WORN_INDICES)
    record[0x48] = PALICO_ENTHUSIASM
    struct.pack_into("<H", record, 0x68, 1)
    return bytes(record)


def tutorial_pokes() -> tuple[tuple[int, bytes], ...]:
    """(offset in the save data, bytes) the tutorial writes: the Palico gear box's first pieces, the main Palico, the
    stringer slots (all free)."""
    gear = b"".join(struct.pack("<HH", *piece) for piece in PALICO_GEAR)
    return ((PALICO_GEAR_BOX, gear), (MAIN_PALICO, main_palico()), (STRINGER_SLOTS, b"\xff" * 5))


def caravan_tutorial_data() -> bytes:
    """The data block new_game_tutorial reads (gameplay/new_game_skip/new_game_tutorial.s): the pokes (u32 offset, u32
    length, bytes padded to 4), 0xFFFFFFFF, the quests cleared and the story flags set (u16 lists ending in 0xFFFF)."""
    data = b""
    for offset, content in tutorial_pokes():
        data += struct.pack("<II", offset, len(content)) + content.ljust(-(-len(content) // 4) * 4, b"\0")
    data += struct.pack("<I", END_OF_POKES)
    data += b"".join(struct.pack("<H", quest) for quest in TUTORIAL_QUESTS) + struct.pack("<H", 0xFFFF)
    data += b"".join(struct.pack("<H", flag) for flag in TUTORIAL_FLAGS) + struct.pack("<H", 0xFFFF)
    if len(data) > TUTORIAL_DATA_SIZE:
        raise NewGameSkipError(f"new_game_tutorial_data is {len(data)} bytes, its block {TUTORIAL_DATA_SIZE}")
    return data.ljust(TUTORIAL_DATA_SIZE, b"\0")


def supports_new_game_skip(code: bytes) -> bool:
    """`code` is the update's executable: the hooked call and the functions the routine calls are there."""
    if len(code) < HOOK - BASE_ADDRESS + 4 or bl_target(code, HOOK) != NEW_PROFILE:
        return False
    return all(code[va - BASE_ADDRESS:va - BASE_ADDRESS + 8] == bytes.fromhex(signature)
               for va, signature in SIGNATURES.items())


def patch_new_game_skip(code: bytes, layout: Layout | None = None, caravan_tutorial: bool = False,
                        prologue_only: bool = False) -> bytes:
    """`code` (the update's) with the routine in its free space and the character creation calling it.
    `caravan_tutorial` (option skip_caravan_tutorial): the creation calls new_game_tutorial instead, which runs the
    routine and then leaves the caravan tutorial done and the first Palico equipped (blocks in the extension).
    `prologue_only`: the skip stops at the arrival in Val Habar (new_game_data), where the Caravaneer's first talk and
    the registration play; the caravan tutorial's skip needs the whole one."""
    if caravan_tutorial and prologue_only:
        raise NewGameSkipError("the caravan tutorial's skip needs the skip of the arrival and the registration")
    if not supports_new_game_skip(code):
        raise NewGameSkipError("unexpected bytes in the character creation: skipping the intro needs the update's "
                               "executable")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, "new_game_skip")
    layout.place(out, "new_game_data", new_game_data(prologue_only))
    entry = "new_game_skip"
    if caravan_tutorial:
        layout.place(out, "new_game_tutorial")
        layout.place(out, "new_game_tutorial_data", caravan_tutorial_data())
        entry = "new_game_tutorial"
    layout.hook(out, HOOK, entry, calls=NEW_PROFILE)
    return bytes(out)
