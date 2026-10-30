"""Per-layout fixes that are no placement: edits of a layout file the engine's absolute places cannot make, applied to
the files before the engine
wraps the blocks' groups and measures their reference boxes (gamegui/build.py).

`fixes.json`, `layouts`: layout name -> its fixes, each a key of `hud/single_screen.py`'s layout settings with the
same meaning, made by the same code (`place_layout` without an anchor: nothing is scaled or moved):

* `hide`: panes made clear (alpha 0); a whole root group is hidden by its block's `hidden` instead (the engine);
* `backdrop`: a root group stretched over the whole top screen (the touch screen's 320 x 240 ground made 400 wide),
  which a uniform scale cannot do;
* `nudge`: panes inside a root group moved by [right, down] pixels at the layout's own size (the file's units; the
  block's scale then scales them with everything else): a pane the block's one place cannot move apart from its group
  (the Arena's four buttons in one row, ui497). A whole root group moves by its own block instead.
* `fill`: a copy of a sprite (`template`, "otherlayout:sprite" for another layout of the ARC) inserted as the first
  child of a root group, over the whole top screen or over the box around some root groups (`over`, `margin`), with
  single_screen.json's record and checks; its block places it with the group (the title's rug in `ui803_bg`: a
  backdrop block at the top screen's corner). Today's mechanism runs first in the run and may have made the template
  clear (its `hide`): a fill whose template another record hides names its own `color`.

Fit and layers (sprites sized to a placed box) join when a theme that uses them is migrated."""

import json
from collections.abc import Mapping
from pathlib import Path

from ..hud.single_screen import OFFSET_LIMIT, LayoutSetting, _load_fill, patch_arc
from .config import ARRANGEMENT_DIR

FIXES_FILE = ARRANGEMENT_DIR / "fixes.json"
KEYS = ("hide", "backdrop", "nudge", "fill")


def load_fixes(path: Path = FIXES_FILE) -> dict[str, LayoutSetting]:
    """Layout name -> its fixes as a layout setting without an anchor. Raises ValueError naming the file and the
    layout for anything else."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    layouts = data.get("layouts", {})
    if not isinstance(layouts, dict):
        raise ValueError(f"{path.name}: layouts must map layout names to their fixes")
    out = {}
    for name, record in layouts.items():
        where = f"{path.name}, {name}"
        if not isinstance(record, dict) or not record:
            raise ValueError(f"{where}: an object of fixes")
        unknown = set(record) - set(KEYS)
        if unknown:
            raise ValueError(f"{where}: unknown keys {sorted(unknown)} (a fix is one of {', '.join(KEYS)})")
        hide = record.get("hide", [])
        if not isinstance(hide, list) or not all(isinstance(p, str) and p.startswith(name + "_") for p in hide):
            raise ValueError(f"{where}: hide must list panes of {name}")
        backdrop = record.get("backdrop")
        if backdrop is not None and (not isinstance(backdrop, str) or not backdrop.startswith(name + "_")):
            raise ValueError(f"{where}: backdrop must be a root group of {name}")
        nudge = record.get("nudge", {})
        if not isinstance(nudge, dict) or not all(
                isinstance(pane, str) and pane.startswith(name + "_") and isinstance(shift, list) and len(shift) == 2
                and all(isinstance(v, int | float) and not isinstance(v, bool) and abs(v) <= OFFSET_LIMIT
                        for v in shift) for pane, shift in nudge.items()):
            raise ValueError(f"{where}: nudge must map panes of {name} to [right, down], two numbers of pixels (at "
                             f"most {OFFSET_LIMIT})")
        fill = None
        if "fill" in record:
            try:
                fill = _load_fill(record["fill"], name)
            except ValueError as error:
                raise ValueError(f"{where}: {str(error).split(': ', 1)[-1]}") from None
            if not fill.group.startswith(name + "_"):
                raise ValueError(f"{where}: fill's group must be a root group of {name}")
        out[name] = LayoutSetting(hide=tuple(hide), backdrop=backdrop, fill=fill,
                                  nudge={pane: (float(dx), float(dy)) for pane, (dx, dy) in nudge.items()})
    return out


def fix_arc(raw: bytes, fixes: Mapping[str, LayoutSetting], arc_name: str = "") -> bytes:
    """The ARC with the fixes of every layout of `fixes` it holds made; unchanged when it holds none. A fix naming a
    pane its layout lacks raises KeyError with the layout's name."""
    return patch_arc(raw, fixes, None, arc_name)
