"""The arrangement checker (`python tools/ui/ui.py check`): what must hold
before an arrangement goes into the game, each check returning `Problem`s with a message in the tools' language
(interface/game_gui/strings.py) and fields for scripts (`Report.to_json`).

* **Screens** (`check_matches`): every recorded screen (recorded.py, each screen once over the sessions) matches
  exactly one screen of each mode of check.json's `required_modes`, or none on purpose (its `unarranged` list, per
  mode); in the other modes at most one. A listed screen that matches one, or a listed signature never recorded, is
  stale. An overlay screen (`Arrangement.is_overlay`: a window opened over another screen) does not count beside
  another screen (the engine tries it after every other, `Arrangement.screens_of`).
* **Pixels** (`check_pictures`): on the arranged pictures of every recorded screen that shows a block the arrangement
  moves (render.py, the same map as the engine), a moved block shares no more than `overlap_pixels` pixels with
  another block or with a root group in no block, unless one of the two is a declared backdrop or an overlay drawn
  wholly over the other (a window or menu opened on top of another screen); a pixel is a thing's
  when its own alpha there reaches `coverage_alpha` (painted alone over black and over white, so the alpha is
  measured, not guessed from boxes). A moved block's drawn quads pass no edge of its screen by more than
  `outside_pixels`. In single-screen mode only the top screen counts (the player sees no other).
* **Names** (`check_names`): every group a block or a rule names is a root group of the game's layouts, a block's of
  its own layout.
* **Pools and depth** (`check_pools`): with the engine's wrapper nulls added (engine.wrap_layout, as the build does)
  and check.json's `pool_reserve` for the mod's other layouts, every scene of the game (the layout lists of each stage
  kind, as tests/interface/single_screen/test_single_screen_pools.py reads them) fits each pool of the GUI manager
  (interface/single_screen/executable/single_screen_pools, the null pool at single_screen.json's size); a block whose
  group cannot take one more level (lyt.MAX_DEPTH) is a problem. The engine's table holds at most `engine.MAX_NAMES`
  names (`check_table`).
* **English names** (`english_name_warnings`): a screen, block or screen to record without its English name
  (names_en.json) is a warning, not a problem: the arrangement still goes into the game."""

import json
import struct
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields, replace
from pathlib import Path

import numpy as np

from core.game.files.arc.arc import parse_arc
from core.interface.single_screen.executable import single_screen_pools
from core.game.executable.code_space import BASE_ADDRESS
from core.game.files.gui.lyt import LYT_TYPE_HASH, LytFormatError, PaneKind, parse_lyt
from core.interface.game_gui import engine, geometry, render
from core.interface.game_gui import strings as S
from core.interface.game_gui.config import ARRANGEMENT_DIR, MODES, Arrangement, Placement
from core.interface.game_gui.recorded import RecordedScreen, recorded_screens
from core.interface.game_gui.snapshot import SnapshotFormatError, load

CHECK_SETTINGS = ARRANGEMENT_DIR / "check.json"
POOLS = ("groups", "nulls", "sprites", "texts", "boundaries", "panes")
RESERVED = POOLS[:-1]                 # the pools check.json reserves; the pane pool follows from them
# the loaders' layout path lists and the stage kinds'
# table
COMMON_LIST, LOBBY_LIST, STAGE_LISTS = 0xEFDC60, 0xEFDF44, 0xFB8088
STAGE_KINDS = 17                      # entries of the stage list table, 8 bytes each


@dataclass(frozen=True)
class Problem:
    kind: str                         # sin_pantalla, varias_pantallas, lista, solape, fuera, nombre, pool,
    message: str                      # envoltorio, nombres, ilegible; the message in the tools' language
    mode: str = ""
    screen: str = ""                  # the arrangement screen's number, when one matched
    signature: str = ""               # the recorded screen's
    blocks: tuple[str, ...] = ()
    names: tuple[str, ...] = ()
    pool: str = ""
    pixels: int = 0

    def to_json(self) -> dict:
        return {f.name: list(v) if isinstance(v := getattr(self, f.name), tuple) else v for f in fields(self)}


@dataclass
class Report:
    problems: list[Problem]
    notes: list[str] = field(default_factory=list)     # what could not be checked (the tools' language)
    screens: int = 0                                   # recorded screens checked
    warnings: list[str] = field(default_factory=list)  # what does not stop the arrangement (english_name_warnings)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_json(self) -> dict:
        return {"ok": self.ok, "screens": self.screens, "problems": [p.to_json() for p in self.problems],
                "not_checked": self.notes, "warnings": self.warnings}

    def text(self) -> str:
        count = len(self.problems)
        if count:
            lines = [S.tr(S.CHECK_ONE_PROBLEM, screens=self.screens) if count == 1 else
                     S.tr(S.CHECK_PROBLEMS, count=count, screens=self.screens)]
            lines += [f"- {p.message}" for p in self.problems]
        else:
            lines = [S.tr(S.CHECK_OK, screens=self.screens)]
        lines += [S.tr(S.CHECK_NOT_CHECKED, note=note) for note in self.notes]
        lines += [S.tr(S.CHECK_WARNING, warning=warning) for warning in self.warnings]
        return "\n".join(lines)


@dataclass(frozen=True)
class CheckSettings:
    required_modes: tuple[str, ...]
    unarranged: dict[str, dict[str, str]]       # mode -> {signature: why}
    coverage_alpha: float
    overlap_pixels: int
    outside_pixels: float
    pool_reserve: dict[str, int]


def load_check_settings(path: Path = CHECK_SETTINGS) -> CheckSettings:
    """check.json, checked (ValueError naming the key)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("description", None)
    names = set(CheckSettings.__dataclass_fields__)
    if set(data) != names:
        raise ValueError(f"{path}: missing {sorted(names - set(data))}, unknown {sorted(set(data) - names)}")
    modes = data["required_modes"]
    if not isinstance(modes, list) or not set(modes) <= set(MODES):
        raise ValueError(f"{path}: required_modes must be a list of {MODES}")
    listed = data["unarranged"]
    if not isinstance(listed, dict) or not set(listed) <= set(MODES):
        raise ValueError(f"{path}: unarranged must be an object of mode -> list")
    unarranged = {}
    for mode, entries in listed.items():
        if not isinstance(entries, list) or not all(isinstance(e, dict) and isinstance(e.get("signature"), str)
                                                    and isinstance(e.get("why"), str) for e in entries):
            raise ValueError(f"{path}: unarranged.{mode} must be a list of {{signature, why}}")
        unarranged[mode] = {e["signature"]: e["why"] for e in entries}
    alpha = data["coverage_alpha"]
    if not isinstance(alpha, (int, float)) or not 0 < alpha <= 1:
        raise ValueError(f"{path}: coverage_alpha must be above 0 and at most 1")
    for key in ("overlap_pixels", "outside_pixels"):
        if not isinstance(data[key], (int, float)) or isinstance(data[key], bool) or data[key] < 0:
            raise ValueError(f"{path}: {key} must be a number of pixels, 0 or more")
    reserve = data["pool_reserve"]
    if (not isinstance(reserve, dict) or set(reserve) != set(RESERVED)
            or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in reserve.values())):
        raise ValueError(f"{path}: pool_reserve must give a whole number, 0 or more, for each of {RESERVED}")
    return CheckSettings(tuple(modes), unarranged, float(alpha), int(data["overlap_pixels"]),
                         float(data["outside_pixels"]), dict(reserve))


def _names(groups: Iterable[str]) -> set[str]:
    """Recorded group labels as the rules name them (a second instance's `#1` left out)."""
    return {group.split("#")[0] for group in groups}


# ---- every recorded screen matches exactly one screen of its mode ----

def check_matches(arrangement: Arrangement, recorded: list[RecordedScreen], settings: CheckSettings) -> list[Problem]:
    problems: list[Problem] = []
    for mode in MODES:
        listed = settings.unarranged.get(mode, {})
        required = mode in settings.required_modes
        seen: set[str] = set()
        where = S.mode_name(mode)
        for screen in recorded:
            found = arrangement.matching(_names(screen.groups), mode)
            base = [s for s in found if not arrangement.is_overlay(s)]
            competing = base if base else found
            listed_as = screen.aliases & set(listed)
            seen |= listed_as
            sig = screen.signature
            if len(competing) > 1:
                problems.append(Problem(
                    "varias_pantallas", S.tr(S.SEVERAL_SCREENS, sig=sig, where=where, count=len(competing),
                                             titles=", ".join(S.title(s) for s in competing)),
                    mode, competing[0].number, sig))
            elif not found and required and not listed_as:
                shown = ", ".join(screen.groups[:6]) + (", ..." if len(screen.groups) > 6 else "")
                problems.append(Problem(
                    "sin_pantalla", S.tr(S.NO_SCREEN, sig=sig, where=where, shown=shown), mode, "", sig))
            elif found and listed_as:
                problems.append(Problem(
                    "lista", S.tr(S.LISTED_BUT_MATCHES, sig=sig, where=where, title=S.title(found[0])), mode,
                    found[0].number, sig))
        for sig in sorted(set(listed) - seen):
            problems.append(Problem("lista", S.tr(S.LISTED_NOT_RECORDED, where=where, sig=sig), mode, "", sig))
    return problems


# ---- overlaps on the pictures' pixels, and leaving the screen ----

def _moves(placement: Placement) -> bool:
    return any(getattr(placement, key) is not None for key in ("x", "y", "scale", "screen"))


def moved_blocks(arrangement: Arrangement, mode: str) -> set[str]:
    """The blocks that some screen of `mode` (or their default, in single-screen mode) moves."""
    out = {block_id for block_id in arrangement.blocks if _moves(arrangement.final(None, block_id, mode))}
    for screen in arrangement.screens_of(mode):
        out |= {block_id for block_id, placement in screen.blocks.items() if _moves(placement)}
    return out


def coverage(items: list[render.Item], screen: str, alpha: float, settings: render.RenderSettings) -> np.ndarray:
    """Where `items` cover `screen` with an alpha of `alpha` or more: painted over black and over white, the
    difference is what shows through."""
    black = render.paint(items, screen, replace(settings, background=(0, 0, 0))).astype(np.float64)
    white = render.paint(items, screen, replace(settings, background=(255, 255, 255))).astype(np.float64)
    return 1.0 - (white - black).mean(axis=2) / 255.0 >= alpha - 1e-9


def _outside(items: list[render.Item], screen: str) -> float:
    """How far (pixels) the drawn quads of `items` pass the edges of `screen` (0 inside)."""
    width, height = geometry.SCREEN_SIZES[screen]
    worst = 0.0
    for item in items:
        if item.screen != screen or float(np.max(item.colors[:, 3])) <= 0:
            continue
        xs, ys = [c[0] for c in item.corners], [c[1] for c in item.corners]
        worst = max(worst, -min(xs), -min(ys), max(xs) - width, max(ys) - height)
    return worst


def check_pictures(arrangement: Arrangement, recorded: list[RecordedScreen], assets: render.Assets,
                   settings: CheckSettings, picture_settings: render.RenderSettings | None = None) -> list[Problem]:
    picture_settings = picture_settings or render.load_render_settings()
    owner = arrangement.owners()
    problems: list[Problem] = []
    scenes: dict[str, tuple] = {}
    for mode in MODES:
        moved = moved_blocks(arrangement, mode)
        if not moved:
            continue
        wanted = {group for block_id in moved for group in arrangement.blocks[block_id].groups}
        views = ["top"] if mode == "single_screen" else list(geometry.SCREEN_SIZES)
        for recorded_screen in recorded:
            if not wanted & _names(recorded_screen.groups):
                continue
            sig = recorded_screen.signature
            if sig not in scenes:
                try:
                    snapshot = load(recorded_screen.snapshot)
                except (OSError, SnapshotFormatError) as error:
                    problems.append(Problem("ilegible", S.tr(S.UNREADABLE, sig=sig, error=error), signature=sig))
                    scenes[sig] = None
                    continue
                scenes[sig] = (snapshot, render.scene(snapshot, assets, picture_settings)[0])
            if scenes[sig] is None:
                continue
            snapshot, items = scenes[sig]
            items, screen, places, _warnings = render.arrange(items, snapshot, assets, arrangement, mode)
            problems += _picture_problems(arrangement, mode, views, items, screen, places, owner, moved, sig,
                                          settings, picture_settings)
    return problems


def picture_problems(arrangement: Arrangement, mode: str, items: list[render.Item], screen, places, signature: str,
                     settings: CheckSettings, picture_settings: render.RenderSettings) -> list[Problem]:
    """The pixel problems (`solape`, `fuera`) of one arranged picture (render.arrange's items, screen and places of the
    recorded screen `signature`) as check_pictures finds them."""
    owner = arrangement.owners()
    views = ["top"] if mode == "single_screen" else list(geometry.SCREEN_SIZES)
    return _picture_problems(arrangement, mode, views, items, screen, places, owner, moved_blocks(arrangement, mode),
                             signature, settings, picture_settings)


def _picture_problems(arrangement, mode, views, items, screen, places, owner, moved, sig, settings,
                      picture_settings) -> list[Problem]:
    problems: list[Problem] = []
    numbers = {place.block.id: place.number for place in places}
    number = screen.number if screen else ""
    where = S.mode_name(mode)

    def label(thing: tuple[str, str]) -> str:
        kind, name = thing
        if kind == "block":
            return f"{numbers.get(name, '?')} {S.named(arrangement.blocks[name])}"
        return S.tr(S.LOOSE_GROUP, name=name)

    by_thing: dict[tuple[str, str], list[render.Item]] = {}
    for item in items:
        block = item.block or owner.get(item.group.name or "")
        by_thing.setdefault(("block", block) if block else ("group", item.group.label), []).append(item)
    for view in views:
        here = {thing: [i for i in group if i.screen == view] for thing, group in by_thing.items()}
        here = {thing: group for thing, group in here.items() if group}
        movers = [thing for thing in here if thing[0] == "block" and thing[1] in moved
                  and not arrangement.blocks[thing[1]].backdrop]
        if not movers:
            continue
        masks: dict[tuple[str, str], np.ndarray] = {}

        def mask(thing, masks=masks, here=here, view=view):
            if thing not in masks:
                masks[thing] = coverage(here[thing], view, settings.coverage_alpha, picture_settings)
            return masks[thing]

        def covers(top, under, here=here) -> bool:
            """`top` is an overlay drawn wholly over `under` (each item of it after every item of the other)."""
            return (top[0] == "block" and arrangement.blocks[top[1]].overlay
                    and min(i.key for i in here[top]) > max(i.key for i in here[under]))

        pairs: set[frozenset] = set()
        for mover in movers:
            for other in here:
                pair = frozenset((mover, other))
                if other == mover or pair in pairs or (other[0] == "block" and arrangement.blocks[other[1]].backdrop):
                    continue
                pairs.add(pair)
                if covers(mover, other) or covers(other, mover):
                    continue
                both = mask(mover) & mask(other)
                count = int(np.count_nonzero(both))
                if count > settings.overlap_pixels:
                    blocks = tuple(sorted(t[1] for t in pair if t[0] == "block"))
                    names = tuple(sorted(t[1] for t in pair if t[0] == "group"))
                    problems.append(Problem(
                        "solape", S.tr(S.OVERLAP, a=label(mover), b=label(other), count=count,
                                       side=S.side_name(view), where=where, sig=sig), mode, number, sig, blocks, names,
                        pixels=count))
    for place in places:
        if place.block.id not in moved or place.placement.hidden:
            continue
        if place.screen not in views:
            continue
        excess = _outside(by_thing.get(("block", place.block.id), []), place.screen)
        if excess > settings.outside_pixels:
            problems.append(Problem(
                "fuera", S.tr(S.OUTSIDE, a=label(("block", place.block.id)), excess=f"{excess:.0f}",
                              side=S.side_name(place.screen), where=where, sig=sig), mode, number, sig,
                (place.block.id,), pixels=int(np.ceil(excess))))
    return problems


# ---- names ----

def _short(layout_name: str) -> str:
    return layout_name.replace("/", "\\").split("\\")[-1]


def added_groups() -> set[str]:
    """Root groups single-screen mode adds to the game's layouts that a rule may name: in no file of the game, and in
    the installed mod's only when that one is a single-screen mod. The town minimap's on state
    (interface/single_screen/layout/single_screen_minimap, `minimap.state_group`): screen 10."""
    from core.interface.single_screen.layout.single_screen_minimap import minimap_settings
    return {minimap_settings().state_group}


def check_names(arrangement: Arrangement, layouts) -> list[Problem]:
    """`layouts`: a recorder LayoutIndex (render.Assets.layouts) of the game's files; its fallback is read too. A rule
    may also name `added_groups`."""
    layouts.widen()
    roots: dict[str, set[str]] = {}
    for found in layouts.roots.values():
        for layout_name, root in found:
            roots.setdefault(_short(layout_name), set()).add(root.name)
    every = (set().union(*roots.values()) if roots else set()) | added_groups()
    panes: dict[tuple[str, str], set[str]] = {}
    for found in layouts.roots.values():
        for layout_name, root in found:
            panes.setdefault((_short(layout_name), root.name), set()).update(
                p.name for p in getattr(root, "walk", lambda: ())())
    problems: list[Problem] = []
    for block in arrangement.blocks.values():
        for group in block.groups:
            if group not in roots.get(block.layout, set()):
                problems.append(Problem(
                    "nombre", S.tr(S.BLOCK_GROUP_MISSING, id=block.id, name=S.named(block), group=group,
                                   layout=block.layout), blocks=(block.id,), names=(group,)))
            elif block.part:
                for pane in sorted(set(block.part) - panes.get((block.layout, group), set())):
                    problems.append(Problem(
                        "nombre", S.tr(S.BLOCK_PANE_MISSING, id=block.id, name=S.named(block), pane=pane,
                                       group=group), blocks=(block.id,), names=(group,)))
    for screen in arrangement.screens:
        for group in sorted(screen.when.groups() - every):
            problems.append(Problem(
                "nombre", S.tr(S.RULE_GROUP_MISSING, title=S.title(screen), mode=S.mode_name(screen.mode),
                               group=group), screen.mode, screen.number, names=(group,)))
        for group in sorted(set(screen.photo or ()) - every):
            problems.append(Problem(
                "nombre", S.tr(S.PHOTO_GROUP_MISSING, title=S.title(screen), mode=S.mode_name(screen.mode),
                               group=group), screen.mode, screen.number, names=(group,)))
    return problems


def english_name_warnings(arrangement: Arrangement, coverage=()) -> list[str]:
    """The screens, blocks and `coverage` entries (the recorder's screens to record) with no English name in
    names_en.json: one warning per kind."""
    missing = [(S.SCREENS_WORD, [s.id for s in arrangement.screens if not s.name_en]),
               (S.BLOCKS_WORD, [b.id for b in arrangement.blocks.values() if not b.name_en]),
               (S.TO_RECORD_WORD, [c.id for c in coverage if not c.name_en])]
    return [S.tr(S.NO_ENGLISH_NAMES, things=f"{S.tr(word)} {', '.join(ids)}") for word, ids in missing if ids]


def check_table(arrangement: Arrangement) -> list[Problem]:
    """The engine's table names every group of a block or a rule; it holds at most engine.MAX_NAMES."""
    names = {g for block in arrangement.blocks.values() for g in block.groups}
    names |= {g for screen in arrangement.screens for g in screen.when.groups()}
    if len(names) <= engine.MAX_NAMES:
        return []
    return [Problem("nombres", S.tr(S.TOO_MANY_NAMES, count=len(names), limit=engine.MAX_NAMES))]


# ---- pools and the loader's depth ----

def pool_use(layouts: Iterable) -> dict[str, int]:
    """What `layouts` ask of the GUI manager's pools: every text takes a null too, and the pane pool holds every null,
    sprite, text (twice: its own and its null) and boundary
    (tests/interface/single_screen/test_single_screen_pools.py)."""
    use = Counter(pane.kind for layout in layouts for pane in layout.panes)
    out = {"groups": use[PaneKind.GROUP], "nulls": use[PaneKind.NULL] + use[PaneKind.TEXT],
           "sprites": use[PaneKind.SPRITE], "texts": use[PaneKind.TEXT], "boundaries": use[PaneKind.BOUNDARY]}
    out["panes"] = out["nulls"] + out["sprites"] + out["texts"] + out["boundaries"]
    return out


def check_pools(arrangement: Arrangement, layouts: Mapping[str, bytes], scenes: Mapping[str, list[str]],
                sizes: Mapping[str, int], reserve: Mapping[str, int]) -> list[Problem]:
    """`layouts`: layout name -> the game's bytes; `scenes`: a scene's name -> the layouts it loads; `sizes`: each
    pool's size (`POOLS`); `reserve`: what the mod's other layouts take (check.json)."""
    owner = arrangement.owners()
    problems: list[Problem] = []
    wrapped = {}
    parts = engine.wanted_parts(arrangement)
    for name, groups in engine.wanted_groups(arrangement).items():
        if name not in layouts:
            continue
        layout = parse_lyt(layouts[name])
        roots = {root.name for root in layout.roots}
        for group in groups:
            if group not in roots:
                continue                                    # check_names reports it
            try:
                engine.wrap_layout(layout, [group], parts.get(name))
            except (KeyError, ValueError, LytFormatError) as error:
                block = arrangement.blocks[owner[group]]
                problems.append(Problem(
                    "envoltorio", S.tr(S.CANNOT_WRAP, id=block.id, name=S.named(block), group=group, error=error),
                    blocks=(block.id,), names=(group,)))
        wrapped[name] = layout
    plain: dict[str, object] = {}
    reserved = dict(reserve)
    reserved["panes"] = sum(reserve[pool] for pool in ("nulls", "sprites", "texts", "boundaries"))
    over: dict[str, list[tuple[str, int]]] = {}
    for scene, names in scenes.items():
        chosen = []
        for name in names:
            if name in wrapped:
                chosen.append(wrapped[name])
            elif name in layouts:
                plain.setdefault(name, parse_lyt(layouts[name]))
                chosen.append(plain[name])
        use = pool_use(chosen)
        for pool in POOLS:
            asked = use[pool] + reserved[pool]
            if asked > sizes[pool]:
                over.setdefault(pool, []).append((scene, asked))
    for pool in POOLS:
        if pool in over:
            scene, asked = max(over[pool], key=lambda pair: pair[1])
            problems.append(Problem(
                "pool", S.tr(S.POOL_FULL, pool=pool, count=len(over[pool]), scene=scene, asked=asked,
                             size=sizes[pool]), pool=pool, pixels=0))
    return problems


def _cstring(code: bytes, address: int) -> str:
    start = address - BASE_ADDRESS
    return code[start:code.index(b"\0", start)].decode("latin1")


def _path_list(code: bytes, address: int) -> list[str]:
    names = []
    while pointer := struct.unpack_from("<I", code, address - BASE_ADDRESS + 4 * len(names))[0]:
        names.append(_short(_cstring(code, pointer)))
    return names


def game_pools(code: bytes, romfs: Path, language: str) -> tuple[dict[str, bytes], dict[str, list[str]],
                                                                  dict[str, int]]:
    """(layout name -> bytes, scene -> layout names, pool -> size) of the game: the layouts of the RomFS dump's
    `language` (its core and map ARCs), each stage kind's lists from the canonical executable `code`, and the pool
    sizes with the null pool as single-screen mode sets it."""
    folder = Path(romfs) / language / "data"
    layouts: dict[str, bytes] = {}
    for path in sorted(folder.glob("core_*.arc")) + sorted(folder.glob("*_map.arc")):
        for entry in parse_arc(path.read_bytes()).entries:
            if entry.type_hash == LYT_TYPE_HASH:
                layouts[_short(entry.name)] = entry.data
    scenes = {}
    common = _path_list(code, COMMON_LIST) + _path_list(code, LOBBY_LIST)
    for kind in range(STAGE_KINDS):
        pointer = struct.unpack_from("<I", code, STAGE_LISTS + 8 * kind - BASE_ADDRESS)[0]
        if pointer:
            scenes[S.tr(S.SCENE, kind=kind)] = common + _path_list(code, pointer)
    patched = single_screen_pools.patch_pools(code, single_screen_pools.gui_pool_nulls())
    table = struct.unpack_from("<7I", patched, single_screen_pools.TABLE - BASE_ADDRESS)
    sizes = {"groups": table[0], "nulls": table[1], "sprites": table[2], "texts": table[4], "boundaries": table[5],
             "panes": sum(table[1:])}
    return layouts, scenes, sizes


# ---- the whole check ----

def run(arrangement: Arrangement, root: Path, settings: CheckSettings | None = None,
        assets: render.Assets | None = None, pools: tuple | None = None,
        picture_settings: render.RenderSettings | None = None, coverage=()) -> Report:
    """Every check on the screens recorded under `root` (work/ui). Without `assets` (the game's layouts) the names and
    pixels are not checked, without `pools` (`game_pools`' three) neither are the pools: the report says so. The
    English names of the arrangement and of `coverage` (the recorder's screens to record) are warnings."""
    settings = settings or load_check_settings()
    recorded = recorded_screens(root)
    problems = check_matches(arrangement, recorded, settings) + check_table(arrangement)
    notes: list[str] = []
    if assets is None or not len(assets.layouts):
        notes.append(S.tr(S.NO_GAME_FILES))
    else:
        problems += check_names(arrangement, assets.layouts)
        problems += check_pictures(arrangement, recorded, assets, settings, picture_settings)
    if pools is None:
        notes.append(S.tr(S.NO_POOL_INPUTS))
    else:
        problems += check_pools(arrangement, *pools, settings.pool_reserve)
    return Report(problems, notes, len(recorded), english_name_warnings(arrangement, coverage))
