"""Shrink HUD layouts towards a screen corner (the HUD size option).

In-quest HUD layouts use layout coordinates with the origin at the centre of
the top screen and both axes reversed: screen = (200 - x, 120 - y) (confirmed in the game). Each root group is scaled by
`factor` around its anchor point:

* panes right under the root group: p' = anchor + (p - anchor) * factor
  (the root groups themselves are all at the origin). With Anchor.IN_PLACE
  they keep their position, so each one shrinks around itself (for things the
  code places, like prompts over the characters);
* deeper panes: p' = p * factor (positions are relative to the parent);
* sizes, font sizes and text spacing: * factor. Scale fields are left alone;
* animation keys of x / y (same rule as the pane) and width / height.

`unscaled` names nulls whose subtree keeps the file's numbers instead: the null takes the scale (its own scale times
`factor`, the engine multiplies its children's positions and sizes by it) and nothing under it is changed, tracks
included. For code that writes positions under that null in the layout's own units: what it writes is scaled by the
null.
"""

from collections.abc import Collection, Iterable, Mapping
from enum import Enum

from core.game.files.gui.lanl import Animations, Property
from core.game.files.gui.lyt import Layout, Pane, PaneKind, name_hash

SCREEN_HALF_WIDTH = 200.0
SCREEN_HALF_HEIGHT = 120.0


class Anchor(Enum):
    TOP_LEFT = (1, 1)
    TOP = (0, 1)
    TOP_RIGHT = (-1, 1)
    LEFT = (1, 0)
    CENTER = (0, 0)
    RIGHT = (-1, 0)
    BOTTOM_LEFT = (1, -1)
    BOTTOM = (0, -1)
    BOTTOM_RIGHT = (-1, -1)
    IN_PLACE = None

    @property
    def point(self) -> tuple[float, float] | None:
        """The anchor in layout coordinates (axes reversed: +x is the left edge, +y the top); None in place."""
        if self.value is None:
            return None
        return self.value[0] * SCREEN_HALF_WIDTH, self.value[1] * SCREEN_HALF_HEIGHT


# An Anchor, or any point in layout coordinates.
AnchorSpec = Anchor | tuple[float, float]


def anchor_point(anchor: AnchorSpec) -> tuple[float, float] | None:
    return anchor.point if isinstance(anchor, Anchor) else (float(anchor[0]), float(anchor[1]))


def _scaled(pair: tuple[float, float], factor: float) -> tuple[float, float]:
    return pair[0] * factor, pair[1] * factor


def _scale_pane(pane: Pane, factor: float, anchor: tuple[float, float] | None) -> None:
    x, y = pane.position
    if pane.depth != 1:
        pane.position = (x * factor, y * factor)
    elif anchor is not None:
        pane.position = (anchor[0] + (x - anchor[0]) * factor, anchor[1] + (y - anchor[1]) * factor)
    if pane.size is not None:
        pane.size = _scaled(pane.size, factor)
    if pane.kind == PaneKind.TEXT:
        pane.font_size = _scaled(pane.font_size, factor)
        pane.spacing = _scaled(pane.spacing, factor)


def _inside(pane: Pane, names: Collection[str]) -> bool:
    """Whether a pane named in `names` is above `pane` (not `pane` itself)."""
    parent = pane.parent
    while parent is not None:
        if parent.name in names:
            return True
        parent = parent.parent
    return False


def _check_unscaled(layout: Layout, names: Collection[str]) -> None:
    for name in names:
        pane = layout.find(name)     # KeyError: no such pane
        if pane.kind != PaneKind.NULL:
            raise ValueError(f"unscaled: {name} must be a null (only a null scales what is under it)")
        if _inside(pane, names):
            raise ValueError(f"unscaled: {name} is inside another unscaled null (it would be scaled twice)")


def scale_hud(layout: Layout, animations: Iterable[Animations], factor: float,
              anchors: Mapping[str, AnchorSpec], unscaled: Collection[str] = ()) -> int:
    """Scale the root groups named in `anchors` (and their animation tracks). Returns the tracks changed.

    `animations` can include files for other layouts: only tracks of the scaled groups are touched. `unscaled`: names
    of nulls that take the scale themselves and leave what is under them as the file has it (see the module's text);
    the animations of such a null may not change its scale."""
    unknown = set(anchors) - {group.name for group in layout.roots}
    if unknown:
        raise KeyError(f"no root group named {', '.join(sorted(unknown))}")
    _check_unscaled(layout, unscaled)
    targets: dict[int, tuple[dict[int, Pane], tuple[float, float] | None]] = {}
    for group in layout.roots:
        if group.name not in anchors:
            continue
        point = anchor_point(anchors[group.name])
        group.position = _scaled(group.position, factor)
        panes: dict[int, Pane] = {}
        for pane in group.walk():
            if _inside(pane, unscaled):
                continue            # the null above it scales it
            panes.setdefault(name_hash(pane.name), pane)
            if pane is not group:
                _scale_pane(pane, factor, point)
            if pane.name in unscaled:
                pane.scale = _scaled(pane.scale, factor)
        targets[name_hash(group.name)] = (panes, point)

    changed = 0
    for file in animations:
        for track in file.tracks:
            target = targets.get(track.group_hash)
            pane = target[0].get(track.pane_hash) if target else None
            if pane is None:
                continue
            if pane.name in unscaled and track.prop in (Property.SCALE_X, Property.SCALE_Y):
                raise ValueError(f"unscaled: an animation changes the scale of {pane.name}")
            if track.prop in (Property.X, Property.Y):
                point = target[1]
                if pane.depth != 1:
                    track.transform(factor)
                elif point is not None:
                    track.transform(factor, point[0 if track.prop == Property.X else 1] * (1 - factor))
                else:
                    continue  # stays in place, like the pane
            elif track.prop in (Property.WIDTH, Property.HEIGHT):
                track.transform(factor)
            else:
                continue
            changed += 1
    return changed


def anchor_all(layout: Layout, anchor: AnchorSpec) -> dict[str, AnchorSpec]:
    """The same anchor for every root group of a layout."""
    return {group.name: anchor for group in layout.roots}
