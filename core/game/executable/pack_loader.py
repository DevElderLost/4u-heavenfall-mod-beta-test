"""The packs' loader (monsters/porting/pack_loader.c): its block,
its table and its hooks, placed by whichever run has a pack.

new_id_quest_flags (new_id.c, built with new_id_data.LOADER_DEFINES) calls `pack_quest_load` at quest load. This module
places the block and points FUN_0068fd94's call of FUN_00682cc8 (a monster's resource set) at
`pack_resource_set_load`, which loads a pack still out first: the in-quest reload's way in (FUN_0065c1b4 does not call
new_id_quest_flags). It also places the scene gate ("As built: code manager step 2"): FUN_00642c64 (sMhArea's move)
asks each unstarted area's slot 0x18 whether it can start through `blx r1` at GATE_SITE, which becomes `bl scene_gate`;
on the way to the town or the title the gate holds the loading screen until the quest's packs can go, and frees them.
Step 3 ("As built: code manager step 3") adds the town's side: the gate loads the town's pack on the way to aVillage,
aEvent or aArena once the quest's side is out, and frees it with the screens' packs on the way to aQuest once nothing
of them lives; a screen's pack loads at its screen's opening (pack_open, through an opening entry stub). On a New 3DS
none of it acts: `pack_boot` (FUN_001046d0's call of the main loop, BOOT_CALL) reads every pack before the first frame
and nothing lets one go ("As built: New 3DS without the manager"). Only a run with packs places any of it: the ported
monsters' run through `place` (product.patch_ported), any other through `place_run`, once the patchers have placed
their blocks (a run with no pack changes nothing); the town's patchers run after the ported monsters' patch, so
`place_run` completes the placed table with their packs (`complete`).
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.game.executable import packs, session
from core.game.executable.blocks import ENTRY_STUBS, GAME_SYMBOLS, PACK_BUSY, PACK_SLOTS
from core.game.executable.code_space import BASE_ADDRESS, Layout, load_layout
from core.monsters.porting.new_id_data import FIRST_NEW_ID, NEW_IDS

if TYPE_CHECKING:
    from core.game.files.mib import Quest

BLOCK = "pack_loader"
BLOCKS = (BLOCK, ENTRY_STUBS)
QUEST_ENTRY = "pack_quest_load"              # pack_quest_load(flags): new_id.c's call
RESOURCE_ENTRY = "pack_resource_set_load"    # pack_resource_set_load(manager, set, id): the hook's target
RESOURCE_SET_CALL = 0x68FE20                 # FUN_0068fd94's `bl FUN_00682cc8`, the only call of FUN_00682cc8
GATE_ENTRY = "scene_gate"                    # scene_gate(area, ready): the gate's hook's target
GATE_SITE = 0x642CA0                         # FUN_00642c64's `blx r1` (r0 the area, r1 its slot 0x18)
GATE_ORIGINAL = bytes.fromhex("31ff2fe1")    # blx r1
GATE_STATE = "scene_gate_state"
BOOT_ENTRY = "pack_boot"                     # pack_boot(system): the boot hook's target
BOOT_CALL = 0x104700                         # FUN_001046d0's `bl FUN_00105acc` (the main loop), its only call
QUEST_LARGE_SLOTS = 5                        # the quest load's archive slots for large monsters (memory_manager.md)


def patch(code: bytearray, layout: Layout) -> None:
    """The loader's block and the entries' stubs into `code` (the extended executable), FUN_0068fd94's call of
    FUN_00682cc8 through the loader, the scene gate at GATE_SITE and the boot's read at BOOT_CALL, with their
    variables. Refuses an executable whose instructions are not there (already patched, or not the update's)."""
    layout.place(code, BLOCK)
    if ENTRY_STUBS in layout.blocks:
        layout.place(code, ENTRY_STUBS)
    layout.reserve(code, PACK_BUSY, GATE_STATE)
    layout.hook(code, RESOURCE_SET_CALL, layout.symbol(BLOCK, RESOURCE_ENTRY),
                calls=GAME_SYMBOLS["enemy_resource_set_load"])
    layout.hook(code, GATE_SITE, layout.symbol(BLOCK, GATE_ENTRY), original=GATE_ORIGINAL)
    layout.hook(code, BOOT_CALL, layout.symbol(BLOCK, BOOT_ENTRY), calls=GAME_SYMBOLS["game_main_loop"])


def place(code: bytearray, layout: Layout, plans: dict[str, packs.PackPlan], id_packs: dict[int, str] | None = None
          ) -> None:
    """The state bytes, the loader's table for `plans` (the run's packs; `id_packs`: the pack of each new monster id)
    and the loader with the gate (`patch`)."""
    layout.reserve(code, packs.STATE)
    layout.place(code, packs.TABLE, packs.pack_table(layout, plans, id_packs or {}, FIRST_NEW_ID, NEW_IDS))
    patch(code, layout)


def run_plans(layout: Layout, notes: session.Session | None) -> dict[str, packs.PackPlan]:
    """The packs the run's patchers placed blocks in (`notes.packs`), each with its size in this layout and no pack
    that must come first or with it."""
    return {pack: packs.PackPlan(layout.pack_size(pack)) for pack in (notes.packs if notes is not None else ())}


def placed(notes: session.Session | None) -> bool:
    """Whether the run already has its loader (`place`)."""
    return notes is not None and BLOCK in notes.placed


def place_run(code: bytearray, layout: Layout, notes: session.Session | None) -> bool:
    """The loader, its table and the gate for a run whose patchers placed blocks in packs (`notes.packs`, the run's
    session), after they have: returns whether it placed them. A run with no pack changes nothing; one that has the
    loader (the ported monsters' patch placed it, before the town's patchers ran) gets the packs its table lacks
    (`complete`)."""
    if notes is None or not notes.packs:
        return False
    if placed(notes):
        return complete(code, layout, notes)
    place(code, layout, run_plans(layout, notes))
    return True


def complete(code: bytearray, layout: Layout, notes: session.Session) -> bool:
    """The placed table (`place`, the ported monsters' plans) with the run's other packs (`notes.packs`: the town's,
    the screens'), each as `run_plans` gives it; the table's own entries and new ids keep what they say. Returns
    whether it changed the table."""
    from core.game.executable.blocks import PACK_SLOTS
    from core.game.executable.code_space import BASE_ADDRESS
    start = layout.address(packs.TABLE) - BASE_ADDRESS
    size = len(layout.block(packs.TABLE).data)
    first_id, id_slots, entries = packs.read_table(bytes(code[start:start + size]), NEW_IDS)
    names = {slot: pack for pack, slot in PACK_SLOTS.items()}
    plans = {names[entry.slot]: packs.PackPlan(entry.size, names.get(entry.needs), names.get(entry.with_pack))
             for entry in entries if entry.size}
    missing = {pack: plan for pack, plan in run_plans(layout, notes).items() if pack not in plans}
    if not missing:
        return False
    id_packs = {first_id + k: names[slot] for k, slot in enumerate(id_slots) if slot in names}
    code[start:start + size] = packs.pack_table(layout, plans | missing, id_packs, first_id, NEW_IDS)
    return True


def patch_run(code: bytes, notes: session.Session | None, layout: Layout | None = None) -> bytes:
    """`code` with the loader for the run's packs (`place_run`), or itself when there is nothing to place; `layout`
    defaults to the committed one."""
    if notes is None or not notes.packs:
        return code
    out = bytearray(code)
    if not place_run(out, layout or load_layout(), notes):
        return code
    return bytes(out)


# ---- the packs' window: what the loader commits at once
@dataclass(frozen=True)
class PacksNeed:
    """The most memory a run's loader commits at once (its packs' window, which the boot keeps out of the root heap:
    memory_boot's rows, `packs`), in bytes, and what asks for it (a quest and its packs, or the town's side)."""
    size: int
    what: str


def quest_ids(quest: Quest) -> set[int]:
    """The ids the quest's load flags (FUN_006a74f8, which new_id_quest_flags hands pack_quest_load): every monster of
    its large waves, its intruders and its three small groups."""
    return ({m.monster_id for wave in quest.large_monsters for m in wave}
            | {u.monster.monster_id for u in quest.unstable_monsters}
            | {m.monster_id for group in quest.small_monsters for area in group for m in area})


def table_of(code: bytes, layout: Layout | None = None) -> tuple[int, tuple[int, ...], tuple[packs.TableEntry, ...]]:
    """The loader's table as the executable `code` holds it (`packs.read_table`): no entry with a size when the run
    placed none (or the layout has no table)."""
    layout = layout or load_layout()
    if packs.TABLE not in layout.blocks:
        return 0, (), ()
    block = layout.block(packs.TABLE)
    at = block.address - BASE_ADDRESS
    data = bytes(code[at:at + len(block.data)])
    if len(data) < len(block.data):
        data += bytes(len(block.data) - len(data))
    return packs.read_table(data, NEW_IDS)


def _names() -> dict[int, str]:
    return {slot: pack for pack, slot in PACK_SLOTS.items()}


def town_need(entries: Iterable[packs.TableEntry]) -> PacksNeed:
    """The window's town side: the town's packs (the table's side 1) and the largest screen's (side 2; the loader keeps
    one screen's pack at a time)."""
    entries = [entry for entry in entries if entry.size]
    town = [entry for entry in entries if entry.side == packs.SIDES["town"]]
    screens = sorted((entry for entry in entries if entry.side == packs.SIDES["screen"]), key=lambda e: -e.size)
    chosen = town + screens[:1]
    names = _names()
    return PacksNeed(sum(entry.size for entry in chosen),
                     "the town: packs " + ", ".join(names[entry.slot] for entry in chosen) if chosen else "no pack")


def quest_need(ids: Iterable[int], first_id: int, id_slots: tuple[int, ...], entries: Iterable[packs.TableEntry],
               label: str = "a quest") -> PacksNeed:
    """The window's quest side for a quest flagging `ids`: each new id's pack, with the packs it needs first and those
    that come in with it (pack_need: a Deviant's base, the port machinery, the small monsters a leader calls), each
    once, as the table (`table_of`) gives them."""
    by_slot = {entry.slot: entry for entry in entries if entry.size}
    todo = [id_slots[i - first_id] for i in ids if 0 <= i - first_id < len(id_slots)]
    needed: set[int] = set()
    while todo:
        slot = todo.pop()
        entry = by_slot.get(slot)
        if entry is None or slot in needed:
            continue
        needed.add(slot)
        todo += [entry.needs, entry.with_pack]
    names = _names()
    return PacksNeed(sum(by_slot[slot].size for slot in needed),
                     f"{label}: packs " + ", ".join(sorted(names[slot] for slot in needed)) if needed else label)


def worst_quest_need(first_id: int, id_slots: tuple[int, ...], entries: Iterable[packs.TableEntry]) -> PacksNeed:
    """The largest quest side the table allows: any QUEST_LARGE_SLOTS of its ids, with every id a leader calls (an
    entry's `with_pack`: a small group may hold it without its leader). It covers a quest the run did not write (an
    event quest, a quest added after the run, as a probe's) and a run's quests changed later (fix mode)."""
    entries = [entry for entry in entries if entry.size]
    sized = {entry.slot for entry in entries}
    ids = [first_id + k for k, slot in enumerate(id_slots) if slot in sized]
    called = {entry.with_pack for entry in entries}
    smalls = {i for i in ids if id_slots[i - first_id] in called}
    need = PacksNeed(0, "no pack")
    for chosen in itertools.combinations(ids, min(QUEST_LARGE_SLOTS, len(ids))):
        side = quest_need(set(chosen) | smalls, first_id, id_slots, entries, "any quest of the table")
        if side.size > need.size:
            need = side
    return need


def resident_need(code: bytes, layout: Layout | None = None) -> PacksNeed:
    """A New 3DS's packs (the executable `code`, its loader's table placed): every pack of the table, which pack_boot
    reads at boot and nothing lets go ("As built: New 3DS without the manager"). 0 for a run with no pack."""
    chosen = [entry for entry in table_of(code, layout)[2] if entry.size]
    return PacksNeed(sum(entry.size for entry in chosen), f"every pack of the table ({len(chosen)})")


def run_need(code: bytes, quests: Iterable[Quest] = (), layout: Layout | None = None) -> PacksNeed:
    """The packs' window of a run (the executable `code`, its loader's table placed, and the quests it writes): the
    larger of the town's side (`town_need`) and the largest quest's side (`quest_need`; the worst its table allows,
    `worst_quest_need`, or a written quest flagging more), never both at once (the scene gate lets one side go before
    the other comes in: "As built: code manager step 3"). 0 for a run with no pack."""
    first_id, id_slots, entries = table_of(code, layout)
    need = town_need(entries)
    worst = worst_quest_need(first_id, id_slots, entries)
    if worst.size > need.size:
        need = worst
    for quest in quests:
        side = quest_need(quest_ids(quest), first_id, id_slots, entries, f"quest {quest.quest_id}")
        if side.size > need.size:
            need = side
    return need
