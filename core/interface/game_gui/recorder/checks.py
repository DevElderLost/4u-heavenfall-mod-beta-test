"""The checks every copy passes before it is kept: each root group is one
of a layout file's (its hash), its pane tree is that root's in the file (every pane's hash and kind, siblings in any
order, the game's own null after each text being the only addition), and each pane's values are compared with the
file's: what differs is marked "placed by the game" (`placed_by_game`). A group the game relinked (a pane under another
parent) passes when every pane's name and kind is one of its file's. A group that matches no file fails the copy.

The layouts come from the installed mod's ARCs first, then the RomFS dump's (local.ini: `emulator_dir`,
`mh4u_romfs`), in one language folder (recorder.json, `layout_language`); a group none of them holds is looked for in
the other languages' folders and the software keyboard's (`fallback_folders`), read the first time one is needed."""

import struct
from collections.abc import Callable, Iterable
from pathlib import Path

from core.game.executable.titles import MH4U_EUR, MH4U_USA
from core.game.files.gui.lyt import LYT_TYPE_HASH, LytFormatError, PaneKind, name_hash, parse_lyt
from core.interface.game_gui.snapshot import Group, Manager, Pane

RUNTIME_KINDS = {PaneKind.SPRITE: "sprite", PaneKind.NULL: "null", PaneKind.TEXT: "text",
                 PaneKind.BOUNDARY: "boundary"}


class LayoutIndex:
    """Every root group of the layouts given, by its name's hash: [(layout name, root pane)], first given first.
    `fallback` gives more layouts ((name, layout) pairs), read once, the first time a group matches none of these."""

    def __init__(self, fallback: Callable[[], Iterable[tuple[str, object]]] | None = None):
        self.roots: dict[int, list[tuple[str, object]]] = {}
        self.sources: list[str] = []
        self.fallback = fallback

    def add(self, layout_name: str, layout) -> None:
        for root in layout.roots:
            self.roots.setdefault(name_hash(root.name), []).append((layout_name, root))

    def widen(self) -> bool:
        """Add the fallback's layouts (after every other); False when there is none left to add."""
        if self.fallback is None:
            return False
        fallback, self.fallback = self.fallback, None
        for layout_name, layout in fallback():
            self.add(layout_name, layout)
        return True

    def __len__(self) -> int:
        return len(self.roots)

    @classmethod
    def from_folders(cls, folders: Iterable[Path], fallback: Iterable[Path] = ()) -> "LayoutIndex":
        fallback = list(fallback)
        index = cls(fallback=(lambda: _folder_layouts(fallback)) if fallback else None)
        for folder in folders:
            index.sources.append(str(folder))
            for layout_name, layout in _folder_layouts([folder]):
                index.add(layout_name, layout)
        return index


def _folder_layouts(folders: Iterable[Path]):
    """(name, layout) of every layout in the ARCs of `folders` (not their subfolders)."""
    from core.game.files.arc.arc import ArcFormatError, parse_arc
    for folder in folders:
        for path in sorted(Path(folder).glob("*.arc")):
            try:
                entries = parse_arc(path.read_bytes()).entries
            except ArcFormatError:
                continue
            for entry in entries:
                if entry.type_hash == LYT_TYPE_HASH:
                    try:
                        yield entry.name, parse_lyt(entry.data)
                    except LytFormatError:
                        continue


def layout_folders(emulator_dir: Path | None, romfs: Path | None, language: str,
                   title: str | None = None) -> list[Path]:
    """The installed mod's layouts (`title`'s, else each MH4U title's) and the RomFS dump's, in `language`, those that
    exist."""
    return [root / language / "data" for root in _romfs_roots(emulator_dir, romfs, title)
            if (root / language / "data").is_dir()]


def fallback_folders(emulator_dir: Path | None, romfs: Path | None, language: str,
                     title: str | None = None) -> list[Path]:
    """Where the layouts `layout_folders` lacks may be, in the same places: the other languages' folders (the game
    loads some screens from another language's files) and the software keyboard's (`system/swkbd/archive_*`)."""
    out = []
    for root in _romfs_roots(emulator_dir, romfs, title):
        out += [folder for folder in sorted(root.glob("*/data")) if folder.parent.name != language]
        out += [folder for folder in sorted(root.glob("system/swkbd/archive_*")) if folder.is_dir()]
    return out


def _romfs_roots(emulator_dir: Path | None, romfs: Path | None, title: str | None) -> list[Path]:
    """The installed mod's RomFS (`title`'s, else each MH4U title's), then the dump's."""
    roots = []
    if emulator_dir:
        titles = (title,) if title else (MH4U_EUR, MH4U_USA)
        roots += [Path(emulator_dir) / "load" / "mods" / found / "romfs" for found in titles]
    if romfs:
        roots.append(Path(romfs))
    return roots


def _floats(pane, at: int, count: int) -> list[float]:
    return list(struct.unpack_from(f"<{count}f", pane.layout.data, pane.offset + at))


def file_values(pane) -> dict:
    """A layout file pane's values, named as the reader names the runtime's (structs_reader's pane fields)."""
    data = pane.layout.data
    if pane.kind == PaneKind.SPRITE:
        colors = data[pane.offset + 0x38:pane.offset + 0x48]
        return {"position": _floats(pane, 0x0C, 2), "size": _floats(pane, 0x18, 2), "scale": _floats(pane, 0x20, 2),
                "uv": _floats(pane, 0x28, 4), "colors": [list(colors[i:i + 4]) for i in range(0, 16, 4)],
                "visible": bool(struct.unpack_from("<I", data, pane.offset + 0x60)[0])}
    if pane.kind == PaneKind.NULL:
        return {"position": _floats(pane, 0x0C, 2), "scale": _floats(pane, 0x18, 2),
                "color": list(data[pane.offset + 0x20:pane.offset + 0x24])}
    if pane.kind == PaneKind.GROUP:
        return {"position": _floats(pane, 0x0C, 2)}
    return {}


def placed(fields: dict, values: dict) -> list[str]:
    """The names of `values` (the file's) that `fields` (the copy's) holds with another value."""
    return [name for name, value in values.items() if name in fields and fields[name] != value]


def _match(runtime: list[Pane], file: list, pairs: list) -> str | None:
    """None when `runtime` holds the panes of the list `file` (pairs appended), else why not. Siblings pair by name
    and kind in any order (the game relinks some, e.g. the loading screen's letters); same-named ones in order."""
    left, previous = list(file), None
    for pane in runtime:
        at = next((k for k, target in enumerate(left) if pane.hash == name_hash(target.name)
                   and pane.kind == RUNTIME_KINDS.get(target.kind)), None)
        if at is not None:
            target = left.pop(at)
            pairs.append((pane, target, ""))
            failure = _match(pane.children, target.children, pairs)
            if failure:
                return failure
        elif pane.kind == "null" and pane.hash == 0 and previous is not None and previous.kind == "text" \
                and not any(part.hash for part in pane.walk()):
            pairs += [(part, None, "text null" if part is pane else "text part") for part in pane.walk()]
        else:
            wanted = ", ".join(f"{target.kind.name.lower()} {target.name!r}" for target in left[:3]) or "nothing"
            return f"pane {pane.address:#x} ({pane.kind}, hash {pane.hash:08x}) where the file has {wanted}"
        previous = pane
    if left:
        return f"the file's {left[0].kind.name.lower()} {left[0].name!r} is missing"
    return None


def _match_names(runtime: list[Pane], root, pairs: list) -> str | None:
    """None when every pane of `runtime` (a tree the game relinked) is a pane of the file's tree under `root` by name
    and kind, wherever it is, or the game's own null after a text (pairs appended); else why not."""
    by_hash: dict[int, object] = {}
    stack = list(reversed(root.children))
    while stack:
        target = stack.pop()
        by_hash.setdefault(name_hash(target.name), target)
        stack += reversed(target.children)
    previous_of = {}
    for siblings in [runtime] + [pane.children for pane in _walk(runtime)]:
        for before, pane in zip([None] + siblings[:-1], siblings):
            previous_of[pane.address] = before
    for pane in _walk(runtime):
        target = by_hash.get(pane.hash)
        before = previous_of.get(pane.address)
        if target is not None and pane.kind == RUNTIME_KINDS.get(target.kind):
            pairs.append((pane, target, ""))
        elif pane.kind == "null" and pane.hash == 0 and before is not None and before.kind == "text" \
                and not any(part.hash for part in pane.walk()):
            pairs += [(part, None, "text null" if part is pane else "text part") for part in pane.walk()]
        elif any(pane is part for pair in pairs for part in [pair[0]]):
            continue                                   # a text part, already paired with its null
        else:
            return f"pane {pane.address:#x} ({pane.kind}, hash {pane.hash:08x}) is no pane of the file"
    return None


def _walk(panes: list[Pane]):
    for pane in panes:
        yield pane
        yield from _walk(pane.children)


def _pair(group: Group, index: LayoutIndex) -> tuple[str, object, list] | list[str]:
    """(layout name, root, pairs) of the first file root `group` matches: by tree in every candidate first, then by
    names; the index's fallback layouts when none does. Else the reasons, one per candidate."""
    while True:
        candidates = index.roots.get(group.hash, [])
        reasons = []
        for match in (_match, _match_names):
            for layout_name, root in candidates:
                pairs: list = []
                failure = match(group.panes, root.children if match is _match else root, pairs)
                if not failure:
                    return layout_name, root, pairs
                if match is _match:
                    reasons.append(f"{layout_name}: {failure}")
        if not index.widen():
            return reasons


def pair_group(group: Group, index: LayoutIndex) -> tuple[str, object, list] | None:
    """(layout name, root pane, [(runtime pane, file pane or None, role)]) of the first layout root `group` matches,
    the one `check_group` names it from; None when it matches none. Reads `group`, never changes it."""
    found = _pair(group, index)
    return found if isinstance(found, tuple) else None


def check_group(group: Group, index: LayoutIndex) -> str | None:
    """Names `group` and its panes from the first layout file whose root it matches; None, or why it matches none."""
    found = _pair(group, index)
    if isinstance(found, list):
        if not found:
            return f"group {group.hash:08x} (slot {group.slot}) is in no layout file"
        name = index.roots[group.hash][0][1].name
        return f"group {name} (slot {group.slot}) matches no file: " + "; ".join(found)
    layout_name, root, pairs = found
    group.name, group.layout = root.name, layout_name
    group.placed_by_game = placed(group.fields, file_values(root))
    for pane, target, role in pairs:
        if target is None:
            pane.name, pane.role = None, role
        else:
            pane.name = target.name
            pane.placed_by_game = placed(pane.fields, file_values(target))
    return None


def check(managers: list[Manager], index: LayoutIndex) -> dict:
    """Names every group and pane and counters what the game placed; {"ok", "failures", "groups", "panes", "placed"}."""
    failures, panes, moved = [], 0, 0
    for manager in managers:
        seen: dict[int, int] = {}
        for group in manager.groups:
            group.instance = seen.get(group.hash, 0)
            seen[group.hash] = group.instance + 1
            failure = check_group(group, index)
            if failure:
                failures.append(failure)
            for pane in group.walk():
                panes += 1
                moved += bool(pane.placed_by_game)
    groups = sum(len(manager.groups) for manager in managers)
    return {"ok": not failures and groups > 0, "failures": failures if groups else ["no GUI group in the copy"],
            "groups": groups, "panes": panes, "placed": moved, "layouts": index.sources}
