"""The quest's layouts of our own: three sites of the game serve
every feature that draws a layout of its own in a quest (Damage Numbers, the Hunting Horn's songs), so two features
never hook one instruction. Each feature's patch adds its entry (add_quest_layout): its frame function, the index of its
group in the GUI manager and its layout's path in core_quest.arc. The first one also places the shared stub and code
(quest_layouts_stub.s, quest_layouts.c) and hooks the sites; the others only fill the table.

These functions change, in the update's executable (canonical):

- FUN_00af52a0 (sMhMain::frame): its `ldr r0, [r4, #0x2bc]` after every system's move and before the render
  (FRAME_HOOK) goes through the stub, which runs each feature's frame first;
- FUN_00c1017c (the quest's layouts' loader): its `mov r4, #0` right after the stage map's load (LOAD_HOOK) loads each
  feature's layout too, and FUN_00c0f110 (frees the GUI layouts): its `mov r10, r1` (FREE_HOOK) frees them. The target
  face takes the instructions next to them (interface/hud/code_patch.py LOADER_HOOK, FREE_HOOK), so both can be in a
  mod.
Update's executable only; the version maps carry it to the base games.
"""

import struct
from dataclasses import dataclass

from core.game.executable.blocks import QUEST_LAYOUTS_DATA_SIZE
from core.game.executable.code_space import BASE_ADDRESS, CodeSpaceError, Layout, bl_target

STUB, CODE, DATA = "quest_layouts_stub", "quest_layouts_code", "quest_layouts_data"
ENTRIES, PATH = 4, 24           # quest_layouts.c ENTRIES, PATH
ENTRY = struct.Struct(f"<2I{PATH}s")

# The hooks: (address, the word the game has, the stub's label)
FRAME_HOOK, FRAME_WORD = 0xAF554C, bytes.fromhex("bc0294e5")   # FUN_00af52a0: ldr r0, [r4, #0x2bc]
LOAD_HOOK, LOAD_WORD = 0xC10434, bytes.fromhex("0040a0e3")    # FUN_00c1017c: mov r4, #0 (after the stage map)
FREE_HOOK, FREE_WORD = 0xC0F118, bytes.fromhex("01a0a0e1")    # FUN_00c0f110: mov r10, r1
WORDS = ((FRAME_HOOK, FRAME_WORD, "quest_frame_hook"), (LOAD_HOOK, LOAD_WORD, "quest_loader"),
         (FREE_HOOK, FREE_WORD, "quest_free"))

# The GUI manager's slots that are free in every scene: the game's layouts take 20-721 and FUN_00c105f4's 1526-1535,
# the target face's copy 0x5C0-0x5C2
FREE_INDICES = range(722, 1526)


@dataclass(frozen=True)
class QuestLayout:
    """A feature's entry: its frame function (an address of its code block), its group's slot in the GUI manager and
    its layout's path in core_quest.arc without the language (the entry's name is "<lang>\\" + it)."""
    frame: int
    index: int
    path: str

    def pack(self) -> bytes:
        encoded = self.path.encode("ascii")
        if len(encoded) >= PATH or not self.frame:
            raise CodeSpaceError(f"{self.path}: a path of at most {PATH - 1} characters and a frame function")
        return ENTRY.pack(self.frame, self.index, encoded)


def _word(code: bytes | bytearray, at: int) -> bytes:
    return bytes(code[at - BASE_ADDRESS:at - BASE_ADDRESS + 4])


def supports_quest_layouts(code: bytes) -> bool:
    """`code` (the update's executable, canonical, not patched yet) has every instruction the hooks replace."""
    return all(_word(code, site) == word for site, word, _ in WORDS)


def hooked(code: bytes | bytearray, layout: Layout) -> bool:
    """The shared hooks are in `code` already (an earlier feature's patch placed them)."""
    return bl_target(code, FRAME_HOOK) == layout.symbol(STUB, "quest_frame_hook")


def entries(code: bytes | bytearray, layout: Layout) -> list[QuestLayout]:
    """The table's entries in `code`, empty ones left out."""
    at = layout.address(DATA) - BASE_ADDRESS
    found = []
    for i in range(ENTRIES):
        frame, index, path = ENTRY.unpack_from(code, at + i * ENTRY.size)
        if frame:
            found.append(QuestLayout(frame, index, path.split(b"\x00")[0].decode("ascii")))
    return found


def add_quest_layout(code: bytearray, entry: QuestLayout, layout: Layout) -> None:
    """`entry` in the table of `code` (the update's executable): the first feature places the shared blocks and hooks
    the sites. Refuses an index outside FREE_INDICES or taken by another entry, a full table, and an executable whose
    sites are neither the game's words nor our hooks."""
    if entry.index not in FREE_INDICES:
        raise CodeSpaceError(f"{entry.path}: index {entry.index:#x} is not free in every scene")
    if not hooked(code, layout):
        layout.place(code, STUB)
        layout.place(code, CODE)
        layout.place(code, DATA, bytes(QUEST_LAYOUTS_DATA_SIZE))
        at = lambda label: layout.symbol(STUB, label)  # noqa: E731
        for site, word, label in WORDS:
            layout.hook(code, site, at(label), original=word)
    present = entries(code, layout)
    if any(e.index == entry.index for e in present):
        raise CodeSpaceError(f"{entry.path}: index {entry.index:#x} is taken already")
    if len(present) >= ENTRIES:
        raise CodeSpaceError(f"the quest's layouts hold {ENTRIES} entries")
    at = layout.address(DATA) - BASE_ADDRESS + len(present) * ENTRY.size
    code[at:at + ENTRY.size] = entry.pack()


__all__ = ["CODE", "DATA", "ENTRIES", "FRAME_HOOK", "FREE_HOOK", "FREE_INDICES", "LOAD_HOOK", "PATH", "QuestLayout",
           "STUB", "WORDS", "add_quest_layout", "entries", "hooked", "supports_quest_layouts"]
