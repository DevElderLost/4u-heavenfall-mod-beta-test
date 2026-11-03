"""Single-screen mode: the new game's touch-panel layout choice (A / B) is skipped and B is always taken, and a save
that holds another layout gets B when a quest loads.
B keeps the Map on the top HUD, which the mode needs.

The title scene's mode 2 (FUN_00b79b98) asks the question between the Felyne step and the save-slot list. Two sites
of the canonical executable, every word checked first:

* `CHOICE_SITE`, six words at the start of its sub-state 0: `cmp r5, #0` / `addne r1, r5, #0x93000` /
  `movne r0, #1` / `strne r0, [r1, #0xC8]` (the owner's cursor word = 1: B) / `b CHOICE_ENTRY` (the middle of the
  game's A press: saves the layout, sets the story flag of B and returns 1, mode 2 -> 3) / `nop`. A null owner skips
  the stores and still returns 1, as the A press does.
* `BACK_SITE`: the slot list's Back (-1) goes to the Felyne step through the "Start Over" path instead of to mode 2,
  which would answer by itself and bounce back to the list.

The A press is entered after its two releases and its click (`FUN_0029E5BC` x2, sound 6): sub-state 2, which makes
the registrations they undo, never runs. The branches are written by `encode_branch`, so a run carries them to the
player's version.
"""

import struct

from core.game.executable.code_space import (
    BASE_ADDRESS, COND_EQ, CodeSpaceError, Layout, bl_target, branch_word, encode_branch, load_layout
)

CHOICE_SITE = 0xB79C00               # sub-state 0 of FUN_00b79b98: six words
CHOICE_ENTRY = 0xB79D88              # the A press after its releases and click: `cmp r5, #0` ... `mov r7, #1`
BACK_SITE = 0xB7B9A8                 # `beq` on the slot list's -1 (Back): to mode 2
BACK_ORIGINAL_TARGET = 0xB7BA04
BACK_TARGET = 0xB7BA74               # the -2 path (Start Over): mode 1, sub-state 0

# ARM instructions, built from their fields
COND_NE, COND_ALWAYS = 0x1, 0xE
R1, R5 = 1, 5


def cmp_imm(rn: int, imm: int, cond: int = COND_ALWAYS) -> int:
    return cond << 28 | 0x3500000 | rn << 16 | imm


def mov_imm(rd: int, imm: int, cond: int = COND_ALWAYS) -> int:
    return cond << 28 | 0x3A00000 | rd << 12 | imm


def add_imm_high(rd: int, rn: int, imm8: int, shift: int, cond: int = COND_ALWAYS) -> int:
    """`add rd, rn, #(imm8 << shift)`, shift even from 4 to 30 (ARM's rotated immediate)."""
    return cond << 28 | 0x2800000 | rn << 16 | rd << 12 | ((32 - shift) // 2) << 8 | imm8


def str_imm(rt: int, rn: int, offset: int, cond: int = COND_ALWAYS) -> int:
    return cond << 28 | 0x5800000 | rn << 16 | rt << 12 | offset


NOP = 0xE320F000
CURSOR_OFFSET = 0xC8                 # owner + 0x93000 + 0xC8: the touch-panel owner's cursor word (0 = A, 1 = B)

# the update's words (retail), checked on the EUR and USA base games through the version maps
CHOICE_RETAIL = (
    cmp_imm(R5, 0),                                            # cmp r5, #0
    0x0A000003,                                                # beq +
    0xE59F1260,                                                # ldr r1, =0x9306E
    0xE7D11005,                                                # ldrb r1, [r1, r5]
    cmp_imm(R1, 0),                                            # cmp r1, #0
    0x0A000001,                                                # beq +
)
RETAIL = {**{CHOICE_SITE + 4 * n: word for n, word in enumerate(CHOICE_RETAIL)},
          BACK_SITE: int.from_bytes(branch_word(BACK_SITE, BACK_ORIGINAL_TARGET, cond=COND_EQ), "little")}


def _word(code: bytes, address: int) -> int:
    return struct.unpack_from("<I", code, address - BASE_ADDRESS)[0]


def supports_layout_choice(code: bytes) -> bool:
    """True if every word the skip changes is the game's own (the canonical executable, not yet patched)."""
    try:
        return all(_word(code, address) == word for address, word in RETAIL.items())
    except struct.error:
        return False


def patch_layout_choice(code: bytes) -> bytes:
    """`code` where the new game takes layout B without asking, and the slot list's Back returns to the Felyne step."""
    if not supports_layout_choice(code):
        raise CodeSpaceError("layout choice: the sites at "
                             f"{CHOICE_SITE:#x} / {BACK_SITE:#x} are not the update's (another executable, or "
                             "already patched)")
    out = bytearray(code)
    words = (
        cmp_imm(R5, 0),
        add_imm_high(R1, R5, 0x93, 12, COND_NE),               # addne r1, r5, #0x93000
        mov_imm(0, 1, COND_NE),                                # movne r0, #1
        str_imm(0, R1, CURSOR_OFFSET, COND_NE),                # strne r0, [r1, #0xC8]
        struct.unpack("<I", encode_branch(CHOICE_SITE + 16, CHOICE_ENTRY))[0],
        NOP,
    )
    struct.pack_into("<6I", out, CHOICE_SITE - BASE_ADDRESS, *words)
    out[BACK_SITE - BASE_ADDRESS:BACK_SITE - BASE_ADDRESS + 4] = encode_branch(BACK_SITE, BACK_TARGET, cond=COND_EQ)
    return bytes(out)


# ----- layout B on every save --------------------------------------------------------------------------------------
#
# The quest HUD's init, FUN_00b892f0 (from FUN_00b823d4 when a quest loads), asks FUN_00c1cc9c(save, 0) for the saved
# touch-panel record and copies it into the runtime object. A save made before the question was skipped may hold layout
# A (the Map on the touch screen) or an arrangement of the player's. The call goes through the block
# `single_screen_panels` (single_screen_panels.c), which writes layout B first when the record is not B.

LOAD_SITE = 0xB8931C                 # in FUN_00b892f0: bl FUN_00c1cc9c(save, 0)
LOAD_CALLEE = 0xC1CC9C


def supports_layout_load(code: bytes) -> bool:
    """True if the call of the saved record in the quest HUD's init is the game's own (the canonical executable,
    unpatched)."""
    try:
        return bl_target(code, LOAD_SITE) == LOAD_CALLEE
    except struct.error:
        return False


def patch_layout_load(code: bytes, layout: Layout | None = None) -> bytes:
    """`code` (extended) where the quest HUD's load of the saved touch panels takes layout B first when the saved one is
    not B (block `single_screen_panels`)."""
    layout = layout or load_layout()
    if not supports_layout_load(code):
        raise CodeSpaceError(f"layout load: the call at {LOAD_SITE:#x} is not the update's (another executable, or "
                             "already patched)")
    out = bytearray(code)
    layout.place(out, "single_screen_panels")
    layout.hook(out, LOAD_SITE, "single_screen_panels", calls=LOAD_CALLEE)
    return bytes(out)
