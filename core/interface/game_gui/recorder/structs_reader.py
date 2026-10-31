"""The recorder's GUI reader, on the GUI's structures (interface/game_gui/structs.py): every GUI manager (the main GUI's
and the scenes' own: the Meownster Hunters' trip,
the keyboard's rows), each root group with its pane tree, every pane's data by kind and the texts' strings (read back
from their glyph sprites through the font).

The recorder's interface: `read_gui(view) -> [Manager]` reads everything from `view` (an exact copy, image.py) and
refuses a tree whose links disagree; `regions(memory) -> [(address, size)]` lists the running addresses to copy for it.
Names come from the layout files (checks.py), not from memory, so a copy stays a few regions."""

import struct

from core.interface.game_gui import structs
from core.interface.game_gui.snapshot import Group, Manager, Pane
from core.interface.game_gui.recorder.image import TracingView

NAME = "structs"
MAIN = "main"


class ReadError(ValueError):
    """The copy does not hold the GUI as the structures know it (a link that disagrees, a loop, a list too long)."""


def _rgba(word: int) -> list[int]:
    return list(struct.pack("<I", word))


def _detail_fields(detail) -> dict:
    """A pane's data by kind, named as checks.file_values names the layout file's."""
    if isinstance(detail, structs.Sprite):
        # "texture": the +0x04 word, the layout's texture index (a text part's font page in its low byte; render.py);
        # "texture_ref": the +0x00 word (the font texture with flags on a glyph)
        return {"position": list(detail.position[:2]), "z": detail.position[2], "size": list(detail.size),
                "scale": list(detail.scale), "uv": list(detail.uv), "colors": [_rgba(c) for c in detail.colors],
                "origin": detail.origin, "visible": detail.visible, "primitive": detail.primitive,
                "texture": detail.cell, "texture_ref": detail.texture[0]}
    if isinstance(detail, structs.Null):
        return {"position": list(detail.position[:2]), "z": detail.position[2], "scale": list(detail.scale),
                "color": _rgba(detail.color), "visible": detail.visible}
    if isinstance(detail, structs.Text):
        return {"position": list(detail.position[:2]), "z": detail.position[2], "font_size": list(detail.font_size),
                "spacing": list(detail.spacing), "box": list(detail.box), "colors": [_rgba(c) for c in detail.colors],
                "align": detail.align, "origin": detail.origin, "font": detail.font, "layers": detail.layers,
                "length": detail.length, "glyphs": detail.glyphs, "font_texture": detail.font_texture}
    if isinstance(detail, structs.Boundary):
        return {"position": list(detail.position), "size": list(detail.size), "scale": list(detail.scale),
                "origin": detail.origin, "rect": list(detail.rect)}
    return {}


def _check_links(view, panes, depth: int, parent: int, seen: set, limit: int) -> None:
    """Every pane once, its depth, previous sibling and parent as its place in the tree says."""
    previous = 0
    for pane in panes:
        if pane.address in seen:
            raise ReadError(f"pane {pane.address:#x} is reached twice (a loop in the tree)")
        if len(seen) >= limit:
            raise ReadError(f"a group's tree passes {limit} panes")
        seen.add(pane.address)
        before, up = struct.unpack("<2I", view.read_raw(pane.address + structs.PANE_PREVIOUS, 8))
        if pane.depth != depth or before != previous or up != parent:
            raise ReadError(f"pane {pane.address:#x}: depth {pane.depth}, previous {before:#x}, parent {up:#x}; its "
                            f"place in the tree says {depth}, {previous:#x}, {parent:#x}")
        _check_links(view, pane.children, depth + 1, pane.address, seen, limit)
        previous = pane.address


def _pane(view, node, fonts) -> Pane:
    size = structs.DATA_SIZES.get(node.kind)
    raw = view.read_raw(node.data, size) if node.data and size else b""
    out = Pane(node.address, node.name_hash, structs.KIND_NAMES.get(node.kind, f"kind {node.kind}"), node.depth,
               fields={"data": node.data, **_detail_fields(node.detail)}, raw=raw.hex())
    if node.kind == structs.TEXT and fonts:
        out.text = structs.decode_text(view, node, fonts)
    out.children = [_pane(view, child, fonts) for child in node.children]
    return out


def read_group(view, address: int, slot: int, manager: int, limit: int, fonts) -> Group:
    head = structs.read_group(view, address, manager, panes=False, names=False)
    first = view.word(address + structs.GROUP_FIRST_PANE)
    try:
        nodes = structs.read_pane_tree(view, first, budget=[limit + 1], names=False) if first else []
    except structs.BrokenTree as error:
        raise ReadError(f"group {address:#x}: {error}") from error
    _check_links(view, nodes, 1, 0, set(), limit)
    following, before = struct.unpack("<2I", view.read_raw(address + structs.GROUP_NEXT, 8))
    group = Group(address, slot, head.name_hash, head.view, head.shown, head.layer, head.priority,
                  fields={"position": list(head.position[:2]), "z": head.position[2], "index": head.index,
                          "flags": head.flags, "color": _rgba(head.color), "revision": head.revision,
                          "first_pane": first, "draw_links": [following, before]})
    group.panes = [_pane(view, node, fonts) for node in nodes]
    return group


def _fonts(view) -> dict:
    """The GUI's fonts, none when the copy does not hold them (a save state without the linear heap: the link's
    LinkRefused is a RuntimeError)."""
    try:
        return structs.read_fonts(view)
    except (ValueError, LookupError, OSError, RuntimeError):
        return {}


def read_gui(view, max_slots: int = 8192, max_panes: int = 4096) -> list[Manager]:
    """Every GUI manager in `view` (the main one first, named "main"; the others by their class), their root groups and
    pane trees with the texts' strings. No GUI yet (at boot): no manager."""
    main = structs.main_manager(view)
    if not main:
        return []
    found = structs.read_managers(view)
    if not any(manager.address == main for manager in found):      # sMhUnit not readable: the main one alone
        found.insert(0, structs.Manager(main, "uLayout", -1, 0, {}, view.word(main + structs.GROUP_LIST),
                                        view.word(main + structs.GROUP_COUNT), view.word(main + structs.DRAW_LIST),
                                        view.word(main + structs.MANAGER_FLAGS)))
    found.sort(key=lambda manager: manager.address != main)
    fonts = _fonts(view)
    out, named = [], {}
    for manager in found:
        if manager.group_count > max_slots:
            raise ReadError(f"a manager's list holds {manager.group_count} slots (more than {max_slots})")
        if manager.address == main:
            name = MAIN
        else:
            named[manager.class_name] = named.get(manager.class_name, 0) + 1
            name = manager.class_name + (f"#{named[manager.class_name] - 1}" if named[manager.class_name] > 1 else "")
        groups = [read_group(view, address, slot, manager.address, max_panes, fonts)
                  for slot, address in structs.group_addresses(view, manager)]
        out.append(Manager(name, manager.address, groups))
    return out


def regions(memory, merge_gap: int = 0x10000, max_slots: int = 8192, max_panes: int = 4096) -> list[tuple[int, int]]:
    """The running addresses `read_gui` reads in `memory` now, as a few large regions."""
    trace = TracingView(memory)
    read_gui(trace, max_slots, max_panes)
    return trace.runs(merge_gap)
