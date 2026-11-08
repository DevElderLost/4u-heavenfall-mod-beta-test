"""Hold A (option hold_a): holding A repeats it where the game wants a press for every thing.

Three calls of the game go through the block `hold_a` (gameplay/hold_a/hold_a.c), each of
which makes the original call and uses the game's own button repeat (the GUI set's, `pad + 0x35C`):
  * the hunter's input update (FUN_00b1cdf0) calls the item mode (FUN_00b28f54): with the weapon sheathed in a quest,
    A held repeats as a new press, so gathering, picking up, mining and carving need no mashing;
  * the quest result scene (FUN_00accd24) and the Wyporium's claim panel (FUN_005e5cb8): on the steps that take items
    ("Take Items", "Send to Item Box") A held repeats, and the cursor goes on to the next item by itself.
Update's executable only.
"""

from core.game.executable.code_space import CodeSpaceError, Layout, bl_target, load_layout

BLOCK = "hold_a"

ITEM_MODE = 0xB28F54          # FUN_00b28f54(hunter): item mode, with L held
ITEM_MODE_CALL = 0xB1D08C     # in FUN_00b1cdf0, the local hunter's input update: after the pad was copied

RESULT_SCENE = 0xACCD24       # FUN_00accd24(scene, ?, ?): the quest result scene, once per frame
RESULT_SCENE_CALLS = (0x65CAA4, 0x65CABC)   # in FUN_0065c5b8, which runs the scene's pages

CLAIM_SCENE = 0x5E5CB8        # FUN_005e5cb8(panel): the Wyporium's claim items panel, once per frame
CLAIM_SCENE_CALLS = (0xA0A350, 0x9B74E4)    # in FUN_00a0a220 and in the function that redraws after a move

# (block label, the game function the call is to, the calls it replaces, the gate of the START menu's options)
HOOKS = (
    ("hold_a_field", ITEM_MODE, (ITEM_MODE_CALL,), "gate_hold_a_field"),
    ("hold_a_rewards", RESULT_SCENE, RESULT_SCENE_CALLS, "gate_hold_a_rewards"),
    ("hold_a_claim", CLAIM_SCENE, CLAIM_SCENE_CALLS, "gate_hold_a_claim"),
)


def supports_hold_a(code: bytes) -> bool:
    """True if every call is where the update's executable has it."""
    return all(bl_target(code, at) == callee for _, callee, calls, _ in HOOKS for at in calls)


def patch_hold_a(code: bytes, layout: Layout | None = None, gated: bool = False) -> bytes:
    """`code` (the update's executable) where holding A repeats it and the item panels go on to the next item. `gated`:
    each call goes through the gate of the START menu's options (interface/mod_settings/mod_options_stub.s), which makes
    the game's own call while the option is off."""
    if not supports_hold_a(code):
        raise CodeSpaceError("unexpected calls in the hunter's input and the item panels: hold A needs the update's "
                             "executable")
    layout = layout or load_layout()
    out = bytearray(code)
    layout.place(out, BLOCK)
    for label, callee, calls, gate in HOOKS:
        for at in calls:
            layout.hook(out, at, layout.symbol("mod_options_stub", gate) if gated else layout.symbol(BLOCK, label),
                        calls=callee)
    return bytes(out)
