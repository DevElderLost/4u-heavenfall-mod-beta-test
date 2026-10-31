"""Edits of the arrangement from the command line (`tools/ui/ui.py
show | set`): find a screen by its number or id, describe a screen or a recorded screen, and set a block's placement on
a screen.

`set_placement` takes absolute values only (`x=30`, `scale=0.75`, `screen=top`, `hidden=true`, `priority=12`;
`key=none` leaves the field to the block's default): a relative form (`+5`, `x+=5`, `5+3`) is refused, and the theme
file is written through `config.save_screens`, which writes nothing the loader would refuse."""

from dataclasses import fields, replace
from pathlib import Path

from core.interface.game_gui import render
from core.interface.game_gui import strings as S
from core.interface.game_gui.config import MODES, Arrangement, Placement, Screen, load_arrangement, save_screens
from core.interface.game_gui.recorded import RecordedScreen, find_recorded, recorded_screens
from core.interface.game_gui.requests import read_requests

KEYS = tuple(f.name for f in fields(Placement))
_NUMBER_CHARS = set("0123456789.-")


class EditError(ValueError):
    """A request the arrangement's format refuses (the message says why)."""


def find_screen(arrangement: Arrangement, ref: str, mode: str | None = None) -> Screen:
    """The screen whose id is `ref`, else whose number is `ref` (in `mode` when given)."""
    by_id = [s for s in arrangement.screens if s.id == ref]
    if by_id:
        return by_id[0]
    found = [s for s in arrangement.screens if s.number == ref and (mode is None or s.mode == mode)]
    if len(found) == 1:
        return found[0]
    if found:
        raise EditError(f"screen {ref} exists in modes {sorted(s.mode for s in found)}: give --mode or the id "
                        f"({', '.join(s.id for s in found)})")
    raise EditError(f"no screen {ref}" + (f" in mode {mode}" if mode else ""))


def _number(key: str, text: str, whole: bool = False) -> float | int:
    body = text[1:] if text.startswith("-") else text
    if not body or not set(body) <= _NUMBER_CHARS - {"-"} or body.count(".") > (0 if whole else 1) \
            or body.startswith(".") or body.endswith("."):
        raise EditError(f"{key}={text}: only absolute values (a plain number such as 30 or -4.5), nothing relative")
    return int(text) if whole else float(text)


def parse_values(pairs: list[str]) -> dict[str, object]:
    """`key=value` pairs -> {key: value}, None for `none` (the field left to the default)."""
    out: dict[str, object] = {}
    for pair in pairs:
        key, sep, text = pair.partition("=")
        key, text = key.strip(), text.strip()
        if not sep or key not in KEYS:
            raise EditError(f"{pair}: write key=value with an absolute value, key one of {', '.join(KEYS)}")
        if text.lower() == "none":
            out[key] = None
        elif key in ("x", "y", "scale"):
            out[key] = _number(key, text)
        elif key == "priority":
            out[key] = _number(key, text, whole=True)
        elif key == "hidden":
            if text not in ("true", "false"):
                raise EditError(f"{pair}: hidden is true or false")
            out[key] = text == "true"
        elif key == "screen":
            if text not in ("top", "bottom"):
                raise EditError(f"{pair}: screen is top or bottom")
            out[key] = text
    return out


def set_placement(folder: Path, ref: str, block_id: str, pairs: list[str],
                  mode: str | None = None) -> tuple[Placement, Placement]:
    """Sets `pairs` on block `block_id`'s placement in screen `ref` (the arrangement in `folder`) and writes its theme
    file; returns the screen's placement before and after (its own fields, not the default's)."""
    folder = Path(folder)
    arrangement = load_arrangement(folder)
    screen = find_screen(arrangement, ref, mode)
    if block_id not in arrangement.blocks:
        raise EditError(f"no block {block_id} in blocks.json")
    changes = parse_values(pairs)
    old = screen.blocks.get(block_id, Placement())
    new = replace(old, **changes)
    blocks = dict(screen.blocks)
    if new.to_json():
        blocks[block_id] = new
    else:
        blocks.pop(block_id, None)
    theme = [replace(s, blocks=blocks) if s.id == screen.id else s for s in arrangement.screens
             if s.theme == screen.theme]
    try:
        save_screens(folder / "screens" / f"{screen.theme}.json", theme, arrangement)
    except ValueError as error:
        raise EditError(str(error)) from None
    return old, new


# ---- describing ----

def placement_text(placement: Placement, box=None) -> str:
    if placement.hidden:
        return S.tr(S.HIDDEN)
    parts = []
    if box is not None:
        parts.append(f"x {box[0]:.0f}, y {box[1]:.0f}")
    else:
        if placement.x is not None:
            parts.append(f"x {placement.x:g}")
        if placement.y is not None:
            parts.append(f"y {placement.y:g}")
    if placement.scale is not None:
        parts.append(S.tr(S.SCALE, scale=f"{placement.scale:g}"))
    if placement.screen is not None:
        parts.append(S.side_name(placement.screen))
    if placement.priority is not None:
        parts.append(S.tr(S.PRIORITY, priority=placement.priority))
    return ", ".join(parts) or S.tr(S.GAMES_PLACE)


def _rule_text(screen: Screen) -> str:
    parts = [f"{S.tr(word)} {', '.join(getattr(screen.when, key))}" for key, word in S.RULE_WORDS.items()
             if getattr(screen.when, key)]
    return "; ".join(parts)


def _names(groups) -> set[str]:
    return {group.split("#")[0] for group in groups}


def _blocks_text(arrangement: Arrangement, screen: Screen | None, block_ids) -> list[str]:
    numbers = render.block_numbers(screen, block_ids, arrangement)
    lines = []
    for block_id in sorted(numbers, key=lambda b: [int(p) if p.isdigit() else p for p in numbers[b].split(".")]):
        block = arrangement.blocks[block_id]
        final = arrangement.final(screen, block_id)
        own = S.tr(S.OWN_PLACE if screen and block_id in screen.blocks else S.DEFAULT_PLACE)
        lines.append(f"  {numbers[block_id]} {block_id} {S.named(block)} ({', '.join(block.groups)}"
                     + (S.tr(S.BACKDROP) if block.backdrop else "") + f"): {placement_text(final)} [{own}]")
    return lines


def _pictures(pictures: Path, signature: str) -> list[str]:
    out = []
    for name in ("top", "bottom", "arranged_top", "arranged_bottom"):
        path = Path(pictures) / f"{signature}_{name}.png"
        command = f"tools/ui/ui.py render {signature}{' --arranged' if 'arranged' in name else ''}"
        out.append(f"    {path}" + ("" if path.is_file() else S.tr(S.PICTURE_MISSING, command=command)))
    return out


def _recorded_lines(screen: RecordedScreen, pictures: Path) -> list[str]:
    lines = [S.tr(S.RECORDED_LINE, sig=screen.signature, sessions=", ".join(screen.sessions),
                  variants=screen.variants),
             S.tr(S.SNAPSHOTS, paths=", ".join(str(p) for p in screen.snapshots))]
    return lines + _pictures(pictures, screen.signature)


def owned_blocks(arrangement: Arrangement, groups) -> list[str]:
    names = _names(groups)
    return [b.id for b in arrangement.blocks.values() if names & set(b.groups)]


def show(arrangement: Arrangement, ref: str, root: Path, pictures: Path, mode: str | None = None) -> str:
    """`ref` (a screen's id or number, else a recorded screen's signature or its start) described in the tools'
    language: for a
    screen its rule, its blocks' final places, the recorded screens it matches and their pictures; for a recorded
    screen its groups, the screens it matches per mode, its blocks, the requests about it and its pictures."""
    recorded = recorded_screens(root)
    try:
        screen = find_screen(arrangement, ref, mode)
    except EditError as error:
        found = find_recorded(recorded, ref)
        if len(found) != 1:
            raise EditError(f"{error}; {len(found)} recorded screens are named {ref}") from None
        return _show_recorded(arrangement, found[0], root, pictures)
    lines = [S.tr(S.SHOW_SCREEN, title=S.title(screen), id=screen.id, mode=S.mode_name(screen.mode),
                  theme=screen.theme), S.tr(S.SHOW_RULE, rule=_rule_text(screen))]
    matching = [r for r in recorded if screen in arrangement.matching(_names(r.groups), screen.mode)]
    shown = set(screen.blocks)
    for r in matching:
        shown |= set(owned_blocks(arrangement, r.groups))
    lines.append(S.tr(S.SHOW_BLOCKS))
    lines += _blocks_text(arrangement, screen, shown) or [S.tr(S.NONE_ITEM)]
    lines.append(S.tr(S.SHOW_MATCHING, count=len(matching)))
    for r in matching:
        lines += _recorded_lines(r, pictures)
    return "\n".join(lines)


def _show_recorded(arrangement: Arrangement, screen: RecordedScreen, root: Path, pictures: Path) -> str:
    lines = [S.tr(S.SHOW_RECORDED, sig=screen.signature, count=len(screen.groups), groups=", ".join(screen.groups)),
             S.tr(S.SHOW_ALIASES, aliases=", ".join(sorted(screen.aliases)))]
    first = None
    for mode in MODES:
        found = arrangement.matching(_names(screen.groups), mode)
        first = first or (found[0] if found else None)
        lines.append(f"{S.mode_name(mode)}: " + (", ".join(f"{S.title(s)} (id {s.id})" for s in found)
                                                 or S.tr(S.NO_SCREEN_MATCHED)))
    lines.append(S.tr(S.SHOW_SHOWN_BLOCKS))
    lines += _blocks_text(arrangement, first, owned_blocks(arrangement, screen.groups)) or [S.tr(S.NONE_ITEM)]
    asked = [r for r in read_requests(root)
             if any(w.get("signature") in screen.aliases for w in r.windows.values())]
    if asked:
        lines.append(S.tr(S.SHOW_REQUESTS, requests=", ".join(
            f"{r.id} ({S.tr(S.ANSWERED if r.answer is not None else S.PENDING)})" for r in asked)))
    lines.append(S.tr(S.SHOW_RECORDINGS))
    lines += _recorded_lines(screen, pictures)
    return "\n".join(lines)


def screens_of_groups(arrangement: Arrangement, groups) -> dict[str, list[str]]:
    """Mode -> the screens ("07 Cantina", "07 Canteen" in English) that `groups` match."""
    return {mode: [S.title(s) for s in arrangement.matching(_names(groups), mode)] for mode in MODES}


