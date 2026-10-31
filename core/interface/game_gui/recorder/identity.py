"""What a live snapshot says about the game it came from: the installed mod (its marker file, which the edition may
have named differently before; and its executable's hash) and the emulator's
system language, which the game uses.
Read only; a save state gets neither (the mod installed now may not be the one that ran)."""

import hashlib
import json
import struct
from pathlib import Path

from core.app.edition import edition

# The system settings save of Citra / Azahar's NAND (the 3DS's CFG): its block 0x000A0002 is the language.
CFG_SAVE = Path("nand/data/00000000000000000000000000000000/sysdata/00010017/00000000/config")
LANGUAGE_BLOCK = 0x000A0002
LANGUAGES = {0: "jpn", 1: "eng", 2: "fre", 3: "ger", 4: "ita", 5: "spa", 6: "chi", 7: "kor", 8: "dut", 9: "por",
             10: "rus", 11: "twn"}
MARKER_KEYS = ("kind", "version", "checksum", "seed")


def installed_mod(emulator_dir: Path | None, title: str | None) -> dict | None:
    """The mod in `<emulator_dir>/load/mods/<title>`: its marker's identity, whether its single-screen mode is on
    (`single_screen`: the marker's settings, else those of the newest settings_<seed>.json beside it, which a run
    written straight into the folder leaves without a marker) and its executable's SHA-256; None when nothing is
    installed."""
    if not emulator_dir or not title:
        return None
    folder = Path(emulator_dir) / "load" / "mods" / title
    if not folder.is_dir():
        return None
    out: dict = {"title": title}
    marker = next((folder / name for name in edition().marker_names if (folder / name).is_file()), None)
    if marker is not None:      # the marker, or the file it was called before
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
            out.update({key: data.get(key) for key in MARKER_KEYS})
            if isinstance(data.get("settings"), dict):
                out["single_screen"] = bool(data["settings"].get("single_screen"))
        except (OSError, ValueError):
            out["marker"] = "unreadable"
    if "single_screen" not in out:      # no marker (a run written straight into the folder): its settings_<seed>.json
        runs = sorted(folder.glob("settings_*.json"), key=lambda path: path.stat().st_mtime)
        try:
            data = json.loads(runs[-1].read_text(encoding="utf-8-sig")) if runs else None
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            out["single_screen"] = bool(data.get("single_screen"))
    for name in ("code.bin", "code.ips"):
        code = folder / "exefs" / name
        if code.is_file():
            out[f"exefs_{name.replace('.', '_')}_sha256"] = hashlib.sha256(code.read_bytes()).hexdigest()
    return out


def gui_mode(mod: dict | None) -> str:
    """The GUI the game shows with `mod` installed (`installed_mod`): "single_screen" when the mod arranges it, else
    "normal", the game's own (no mod, or a marker without settings)."""
    return "single_screen" if mod and mod.get("single_screen") else "normal"


def cfg_block(data: bytes, block: int) -> bytes | None:
    """A block's bytes in a CFG save: u16 count, u16 data offset, then (u32 id, u32 offset or inline data, u16 size,
    u16 flags) per block; data of 4 bytes or fewer is inline."""
    if len(data) < 4:
        return None
    count = struct.unpack_from("<H", data)[0]
    for at in range(4, min(4 + 12 * count, len(data) - 11), 12):
        found, where, size, _flags = struct.unpack_from("<IIHH", data, at)
        if found == block:
            if size <= 4:
                return data[at + 4:at + 4 + size]
            return data[where:where + size] if where + size <= len(data) else None
    return None


def system_language(emulator_dir: Path | None) -> str | None:
    if not emulator_dir:
        return None
    path = Path(emulator_dir) / CFG_SAVE
    try:
        value = cfg_block(path.read_bytes(), LANGUAGE_BLOCK)
    except OSError:
        return None
    return LANGUAGES.get(value[0]) if value else None
