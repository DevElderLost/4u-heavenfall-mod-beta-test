"""The file a PC port's static recompiler reads beside our executable.

MH4UltimateDC recompiles the game's `.text` with the sections of the dump's exheader. Our new code is past it, in the
extension (code_space.py, "ext"), which our own `exheader.bin` declares. `recomp.json`, at the mod's root beside
`exheader.bin`, tells the recompiler which of that memory is code and where its functions start, so it recompiles our
code with the game's instead of trapping at the first jump into it:

    {"format": 1, "title": "0004000000126300", "version": "usa_update", "code_sha1": "<sha1 of exefs/code.bin>",
     "code": [["0x111e000", "<end>"]], "entries": [["0x111e000", "arm"], ...]}

`code`: [start, end) ranges past the game's own memory that hold our code (data too: only what an entry reaches is
decoded). `entries`: every function start of the blocks the mod places (code_space.Block.entries), with its
instruction set, and every target of a branch the mod wrote into the
game's code that leads into the extension: the stubs patchers write as machine code at build time have no labels.
Calls inside our code the recompiler follows by itself.

A run that writes packs (packs.py: files of the mod's RomFS that the game loads at a fixed address while the scene that
needs them runs; the town's, the screens', the port machinery's and every ported monster's code) writes format 2: the
same file with a `packs` list, one item per pack file, by address:

    "packs": [{"file": "romfs/packs/town.bin", "address": "0xc700000", "sha1": "<sha1 of the file as written>",
               "entries": [["0xc700000", "thumb"], ...]}, ...]

What the recompiler does with a pack: the file's bytes are code (and data) at `address`, the file's offset 0 being that
address; it recompiles the entries, and what they call, as it does the extension's. The game loads the file while its
scene runs, may unload it and loads it again later with the same bytes (the loader zeroes the pack's variables, which
are in the executable's memory, not in the file), so one recompiled copy serves every load. A pack's far calls out of it
(into the game or the extension) are ld's long-branch veneers inside the pack: `ldr pc, [pc, #-4]` followed by the
target's word, or `ldr ip, [pc]; bx ip` followed by it (the word is the player's version's address).
`entries` are all inside the file's image and none on zeros; each is
* a function start of a block the run placed in the pack (`Block.entries`, as the extension's; a block the run leaves
  out is zeros in the image and gives none);
* the target of an entry stub the run wrote into the executable (entry, opening and guarded stubs: what the game's hooks
  and the resident blocks' declared entries go through), read by `packs.stub_targets` in the executable as written.
Nothing else enters a pack (`packs.check` refuses any other word of the executable into one). A pointer a resident
table holds into a pack's code (the ported monsters' port records) is a function the pack's block lists, and a pack's
own pointers (vtables, tables of functions) name its functions the same way, so a pointer the list missed would only
send that call to the interpreter, as for the extension. The sha1 is of the bytes as `packs.write_files` writes them.
"""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Iterable, Mapping
from pathlib import Path

from core.game.executable import packs
from core.game.executable.canonical import arm_branch_target
from core.game.executable.code_space import (
    BASE_ADDRESS, EXT_START, EXT_VARS_START, PACK_REGIONS, REGIONS, Layout, load_layout,
)

PATH = Path("recomp.json")
FORMAT = 1          # a run with no pack
FORMAT_PACKS = 2    # a run with packs: the same file with their `packs` list
# The versions the port runs (its config/versions.json) and the title its mods folder is named after
TITLES = {"usa_update": "0004000000126300", "eur_update": "0004000000126100"}
# The port's mod library's description of a mod (its tools/mods.py read_manifest): its name and the game it is for
MOD_JSON = Path("mod.json")
MOD_NAME = "Heavenfall"
REGIONS_OF = {"usa_update": "USA", "eur_update": "Europe"}


def title(version: str) -> str:
    """The mods folder title of `version` (versions.VersionMap key), which must be one the port runs."""
    if version not in TITLES:
        raise ValueError(f"the PC port runs only the updates ({', '.join(TITLES)}), not {version}")
    return TITLES[version]


def jump_targets(code: bytes, original: bytes) -> dict[int, str]:
    """The targets in the extension of every ARM branch (b, bl, blx) in the game's own code of `code` (its .text, up to
    text_tail) that `original` (the player's own executable) does not have: the mod's hooks. Only words the mod wrote
    count, so no word of the game's own is taken for a branch. Neither the game's data (.rodata, .data), where a word
    the mod writes may look like one, nor text_tail, whose Thumb code does, is read (its blocks' entries are their
    labels); and a target must hold code the mod placed (not zeros)."""
    found = {}
    end = min(len(code), len(original), REGIONS["text_tail"].start - BASE_ADDRESS) & ~3
    for off in range(0, end, 4):
        if code[off:off + 4] == original[off:off + 4]:
            continue
        word = struct.unpack_from("<I", code, off)[0]
        target = arm_branch_target(word, BASE_ADDRESS + off)
        if target is not None and target >= EXT_START and any(code[target - BASE_ADDRESS:target - BASE_ADDRESS + 4]):
            found[target] = "thumb" if word >> 28 == 0xF else "arm"
    return found


def entries(layout: Layout, code: bytes, original: bytes) -> list[tuple[int, str]]:
    """Every entry of the code blocks `code` holds (address, "arm" | "thumb"), by address, and the targets of the
    mod's jumps into its code (jump_targets), inside code_ranges only: text_tail's blocks lie in the game's .text,
    which the port recompiles anyway. A block the mod leaves out is zeros in its executable: none of its entries is
    given."""
    found = jump_targets(code, original)
    for block in layout.blocks.values():
        if REGIONS[block.region].kind != "code" or not block.entries:
            continue
        start = block.address - BASE_ADDRESS
        if not any(code[start:start + len(block.data)]):
            continue
        for label, mode in block.entries.items():
            found[block.address + block.symbols[label]] = mode
    ranges = code_ranges(code)
    return sorted((at, mode) for at, mode in found.items() if any(s <= at < e for s, e in ranges))


def code_ranges(code: bytes) -> list[tuple[int, int]]:
    """The part of the extension `code` holds, never its variables (ext_vars, read-write)."""
    end = min(BASE_ADDRESS + len(code), EXT_VARS_START)
    return [(EXT_START, end)] if end > EXT_START else []


def pack_entries(layout: Layout, pack: str, image: bytes, targets: Iterable[int]) -> list[tuple[int, str]]:
    """Every address pack `pack`'s code can be entered at (address, "arm" | "thumb"), by address, all inside `image`:
    the function starts of the blocks the run placed in it (`Block.entries`; a block the run leaves out is zeros in the
    image: none of its entries is given), and `targets`, the addresses (bit 0 for Thumb) that the run's entry stubs hold
    (`packs.stub_targets`), those inside this image. A target that is also a block entry keeps the block's instruction
    set."""
    start = PACK_REGIONS[pack].start
    found: dict[int, str] = {}
    for target in targets:
        if start <= target & ~1 < start + len(image):
            found[target & ~1] = "thumb" if target & 1 else "arm"
    for block in layout.pack_blocks(pack):
        offset = block.address - start
        if block.entries and any(image[offset:offset + len(block.data)]):
            for label, mode in block.entries.items():
                found[block.address + block.symbols[label]] = mode
    return sorted(found.items())


def pack_manifest(layout: Layout, code: bytes, images: Mapping[str, bytes]) -> list[dict]:
    """The `packs` list of format 2: one item per pack of `images` (the run's pack files, its player's version's
    words), by address. `code` is the executable as written: its stubs name the targets the game enters the packs at."""
    targets = packs.stub_targets(code, layout).values()
    return [{"file": f"romfs/{packs.pack_file(pack)}", "address": f"{PACK_REGIONS[pack].start:#x}",
             "sha1": hashlib.sha1(bytes(image)).hexdigest(),
             "entries": [[f"{address:#x}", mode] for address, mode in pack_entries(layout, pack, image, targets)]}
            for pack, image in sorted(images.items(), key=lambda item: PACK_REGIONS[item[0]].start)]


def manifest(code: bytes, original: bytes, version: str, layout: Layout | None = None,
             images: Mapping[str, bytes] | None = None) -> dict:
    """The manifest of the mod's executable `code`, built on the player's `original` of `version`; with the run's pack
    files `images` (pack -> bytes as written to romfs/packs: packs.pack_files) it is format 2, with their `packs`."""
    layout = layout or load_layout()
    out = {"format": FORMAT if not images else FORMAT_PACKS, "title": title(version), "version": version,
           "code_sha1": hashlib.sha1(code).hexdigest(),
           "code": [[f"{start:#x}", f"{end:#x}"] for start, end in code_ranges(code)],
           "entries": [[f"{address:#x}", mode] for address, mode in entries(layout, code, original)]}
    if images:
        out["packs"] = pack_manifest(layout, code, images)
    return out


def write(mod_dir: Path, code: bytes, original: bytes, version: str, layout: Layout | None = None,
          images: Mapping[str, bytes] | None = None) -> Path | None:
    """`recomp.json` for the executable `code` (the mod's exefs/code.bin), built on the player's `original` of
    `version`, and `mod.json` naming its region for the port's mod library (its tools/mods.py reads the region only
    there or from a title folder). `images`: the run's pack files (RunResult.packs; their RomFS files are written by
    the caller, `packs.write_files`, with the same bytes). None, and no files, when `code` places nothing past the
    game's memory and the run has no pack: the port recompiles it all already."""
    remove(mod_dir)
    if not code_ranges(code) and not images:
        return None
    path = mod_dir / PATH
    text = json.dumps(manifest(code, original, version, layout, images), indent=1)
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    mod_json = {"name": MOD_NAME, "region": REGIONS_OF[version], "contains": ["code", "exheader", "recomp"]}
    (mod_dir / MOD_JSON).write_text(json.dumps(mod_json, indent=1) + "\n", encoding="utf-8", newline="\n")
    return path


def remove(mod_dir: Path) -> None:
    """A manifest left by an earlier run for the port (its code would not match this run's), and the mod.json that
    came with it (never another's)."""
    (mod_dir / PATH).unlink(missing_ok=True)
    try:
        ours = json.loads((mod_dir / MOD_JSON).read_text(encoding="utf-8")).get("name") == MOD_NAME
    except (OSError, ValueError, AttributeError):
        ours = False
    if ours:
        (mod_dir / MOD_JSON).unlink()
