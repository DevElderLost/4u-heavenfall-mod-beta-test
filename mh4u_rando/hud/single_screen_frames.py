"""Single-screen mode, the frames (emulator only): layouts the game shares
between scenes (the Palico's status ui035, the lists ui475, the arrows ui026) made smaller and moved in one scene only,
the Tablón de camaradas' Palico menus, where the touch screen's panels come up and leave no room.

A layout file is one for every scene that loads it, so the layout side cannot scale ui035 for the Palico menus alone.
Instead each root group named in a frame set gets one null right under it that holds everything the group had
(`<group>_frame`, at (0, 0), scale 1: nothing changes where no frame applies; `wrap_frames`), and the executable's block
`single_screen_frames` (exefs/single_screen_frames.py) writes that null's scale and position every frame: the first
curated scene whose groups are shown (`Frames.scene`) gives each set its `Frame`, every other group gets the null back
at (0, 0), scale 1.

The curated `frames` of single_screen.json:

* `sets`: name -> root groups that take one frame together (a panel made of several groups, e.g. a list's frame, its
  rows and its arrows);
* `only_in`: layout -> the ARCs whose copy of it gets the nulls (the rooms' ui415, not the title's);
* `prompt_off`: sets the block leaves at their own place (no frame) while a yes / no prompt is open: the touch menus'
  description panel shares ui006 with the prompt, whose question and buttons must stay together;
* `scenes`, in order: `all` (every one of these groups shown), `any` (one of them shown; empty: no condition), `none`
  (none of them shown), and `frames`: set -> `scale` and `at`, a point of the screen moves from (x, y) to
  (scale * x + at[0], scale * y + at[1]), top-screen pixels.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ..data.paths import CURATED_DIR
from .lyt import Layout, Pane

SETTINGS_FILE = CURATED_DIR / "single_screen.json"
FRAME_SUFFIX = "_frame"      # the null each framed root group holds everything in
MAX_SCENES = 16              # the block's tables (exefs/single_screen_frames.py)
MAX_SETS = 16
MAX_RULES = 32               # distinct group names the scenes read: one bit each
MAX_NAMES = 160              # distinct group names in the block's table (the scenes' and the sets')
SCALE_RANGE = (0.3, 1.0)     # a frame never grows a panel past the game's size
AT_LIMIT = 400               # pixels, one way or the other

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Frame:
    """A point (x, y) of the top screen goes to (scale * x + at[0], scale * y + at[1])."""
    scale: float
    at: tuple[float, float]

    def box(self, box: Box) -> Box:
        """`box` (left, top, right, bottom) moved by the frame."""
        s, (ax, ay) = self.scale, self.at
        return (s * box[0] + ax, s * box[1] + ay, s * box[2] + ax, s * box[3] + ay)


@dataclass(frozen=True)
class FrameScene:
    """A scene the block recognises by the groups shown, and the frame of each set in it."""
    name: str
    all: tuple[str, ...]
    any: tuple[str, ...]
    none: tuple[str, ...]
    frames: tuple[tuple[str, Frame], ...]

    def fits(self, shown) -> bool:
        shown = set(shown)
        return (set(self.all) <= shown and (not self.any or bool(shown & set(self.any)))
                and not shown & set(self.none))

    def frame(self, name: str) -> Frame | None:
        return dict(self.frames).get(name)


@dataclass(frozen=True)
class Frames:
    """The curated `frames`: the sets (name, root groups), the scenes in order, the layouts framed in some ARCs only,
    and the sets left alone while a yes / no prompt is open."""
    sets: tuple[tuple[str, tuple[str, ...]], ...] = ()
    scenes: tuple[FrameScene, ...] = ()
    only_in: tuple[tuple[str, tuple[str, ...]], ...] = ()
    prompt_off: tuple[str, ...] = ()

    def scene(self, shown) -> FrameScene | None:
        """The first scene that fits the groups `shown` (the block's choice), or None."""
        return next((scene for scene in self.scenes if scene.fits(shown)), None)

    def set_of(self, group: str) -> str | None:
        return next((name for name, groups in self.sets if group in groups), None)

    def groups(self) -> tuple[str, ...]:
        return tuple(group for _name, groups in self.sets for group in groups)

    def rules(self) -> tuple[str, ...]:
        """The distinct group names the scenes read, in order of first use: bit n of the block's masks is name n."""
        names: list[str] = []
        for scene in self.scenes:
            for name in (*scene.all, *scene.any, *scene.none):
                if name not in names:
                    names.append(name)
        return tuple(names)

    def roots(self, layout: str, arc: str) -> tuple[str, ...]:
        """The root groups of `layout` (its name: the groups' prefix) that the copy in the ARC `arc` frames."""
        only = dict(self.only_in).get(layout)
        if only is not None and arc not in only:
            return ()
        return tuple(group for group in self.groups() if layout_of(group) == layout)


def layout_of(group: str) -> str:
    """The layout a root group belongs to: its name's prefix (ui035_otomo_stu_1P -> ui035)."""
    return group.split("_")[0]


def _names(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(n, str) and n for n in value) or len(set(value)) != len(value):
        raise ValueError(f"{where}: a list of distinct names")
    return tuple(value)


def _frame(value: object, where: str) -> Frame:
    if not isinstance(value, dict) or set(value) != {"scale", "at"}:
        raise ValueError(f"{where}: scale and at, nothing else")
    scale, at = value["scale"], value["at"]
    if isinstance(scale, bool) or not isinstance(scale, int | float) or not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        raise ValueError(f"{where}, scale: {SCALE_RANGE[0]} to {SCALE_RANGE[1]}")
    if (not isinstance(at, list) or len(at) != 2
            or any(isinstance(n, bool) or not isinstance(n, int | float) or abs(n) > AT_LIMIT for n in at)):
        raise ValueError(f"{where}, at: [x, y] pixels (at most {AT_LIMIT})")
    return Frame(float(scale), (float(at[0]), float(at[1])))


def frame_settings(path: Path = SETTINGS_FILE) -> Frames:
    """The curated `frames` of single_screen.json (none: no frames)."""
    record = json.loads(Path(path).read_text(encoding="utf-8")).get("frames")
    if record is None:
        return Frames()
    where = "single_screen.json, frames"
    if not isinstance(record, dict) or not {"sets", "scenes"} <= set(record) <= {"sets", "scenes", "only_in",
                                                                                 "prompt_off"}:
        raise ValueError(f"{where}: sets and scenes (and only_in, prompt_off), nothing else")
    sets, seen = [], set()
    if not isinstance(record["sets"], dict) or not 0 < len(record["sets"]) <= MAX_SETS:
        raise ValueError(f"{where}, sets: 1 to {MAX_SETS} names -> root groups")
    for name, groups in record["sets"].items():
        groups = _names(groups, f"{where}, sets, {name}")
        if not groups or seen & set(groups):
            raise ValueError(f"{where}, sets, {name}: at least one group, none in another set")
        seen |= set(groups)
        sets.append((name, groups))
    only_in = record.get("only_in", {})
    if not isinstance(only_in, dict):
        raise ValueError(f"{where}, only_in: layout -> ARC names")
    only = tuple((layout, _names(arcs, f"{where}, only_in, {layout}")) for layout, arcs in only_in.items())
    scenes = []
    if not isinstance(record["scenes"], list) or not 0 < len(record["scenes"]) <= MAX_SCENES:
        raise ValueError(f"{where}, scenes: a list of 1 to {MAX_SCENES}")
    names = dict(sets)
    for item in record["scenes"]:
        if not isinstance(item, dict) or set(item) != {"name", "all", "any", "none", "frames"} or not isinstance(
                item["name"], str):
            raise ValueError(f"{where}, scenes: name, all, any, none and frames each")
        at = f"{where}, scene {item['name']}"
        if not isinstance(item["frames"], dict) or any(name not in names for name in item["frames"]):
            raise ValueError(f"{at}, frames: set name -> frame (the sets: {', '.join(names)})")
        scenes.append(FrameScene(item["name"], _names(item["all"], f"{at}, all"), _names(item["any"], f"{at}, any"),
                                 _names(item["none"], f"{at}, none"),
                                 tuple((name, _frame(value, f"{at}, frames, {name}"))
                                       for name, value in item["frames"].items())))
    prompt_off = _names(record.get("prompt_off", []), f"{where}, prompt_off")
    if any(name not in names for name in prompt_off):
        raise ValueError(f"{where}, prompt_off: set names (the sets: {', '.join(names)})")
    frames = Frames(tuple(sets), tuple(scenes), only, prompt_off)
    if len(frames.rules()) > MAX_RULES:
        raise ValueError(f"{where}: {len(frames.rules())} group names in the scenes, the block reads {MAX_RULES}")
    if len(set(frames.rules()) | set(frames.groups())) > MAX_NAMES:
        raise ValueError(f"{where}: more than {MAX_NAMES} group names, the block's table holds {MAX_NAMES}")
    return frames


def wrap_frames(layout: Layout, roots, template: Pane) -> tuple[str, ...]:
    """Put everything under each root group of `roots` (names) in its frame null, a copy of `template` (a plain null:
    scale 1, no tint; of another parse than `layout`, which every wrapping changes) at (0, 0); returns the nulls' names.
    A group without panes under it gets none (nothing to draw). Raises KeyError for a group the layout lacks."""
    made = []
    for name in roots:
        group = next((g for g in layout.roots if g.name == name), None)
        if group is None:
            raise KeyError(f"no root group {name!r}")
        if group.children:
            layout.wrap_children(group, name + FRAME_SUFFIX, template)
            made.append(name + FRAME_SUFFIX)
    return tuple(made)
