"""The one place for the geometry of the game's GUI on its two screens: the
pictures (render.py) and the engine's build use it, so what the pictures show and what the game does agree by
construction.

* **Screens.** The top screen is 400 x 240 pixels, the touch screen 320 x 240; a root group's runtime screen (bits
  14-17 of its +0x44) is 0 for the top one and 7 for the touch one.
* **Layout coordinates** grow to the left and up from the screen's centre: a point (x, y) of a layout is drawn at
  (200 - x, 120 - y) on the top screen, (160 - x, 120 - y) on the touch screen.
* **The tree.** Positions add down the tree, and a null's scale multiplies its children's positions and sizes (and
  their own scale); a sprite's size is its size times its own scale times the scale above it; a text's box is its
  size times the scale above it.
* **A sprite's origin** (the low byte of its record's word at 0x50) says which point of it its position is: a cell of
  a 3 x 3 grid in screen terms, column by column: 0 the top-left corner, 1 the middle of the left side, 2 the
  bottom-left corner, 3 the middle of the top, 4 the centre, ... 8 the bottom-right corner; a text's origin (bits 4-7
  of its flags) the same. Measured on kept save states from where the game lays out each text's
  glyphs for origins 0, 1, 4, 5, 6 and 7; 0 and 4 were seen in the game before. The
  glyphs the game lays out are placed by their centre (`GLYPH_ORIGIN`). Sizes keep their sign: a negative width mirrors
  the sprite around that point. The origin word's second byte turns the texture inside the quad (`turned`): mirrored,
  upside down, a quarter or half turn.
* **Rotation** is in the game's angle units (65536 a turn), around the origin point; a positive angle turns from the
  screen's x axis towards its y axis (clockwise as seen). The direction is not yet checked against the game.
* **A block's reference box** is the box around what its root groups show as the layout file loads (the panes
  `hud.single_screen.visible_boxes` counts, with the origin above), in its own screen's pixels, cut to that screen.
* **A placement** (`config.Placement`: `x`, `y` the box's top-left corner on the target screen, `scale`, `screen`)
  moves every pane of the block by one affine map of pixels: p -> scale * (p - box corner) + (x, y). The engine gets
  the same map as the values of a null wrapped around a root group's children (`wrapper_null`)."""

import math
from collections.abc import Iterable
from dataclasses import dataclass

from core.game.files.gui.lyt import Layout, Pane, PaneKind

SCREEN_SIZES = {"top": (400, 240), "bottom": (320, 240)}
RUNTIME_SCREENS = {0: "top", 7: "bottom"}       # a root group's screen bits -> the screen
ANGLE_UNITS = 65536                             # a full turn in the game's angle units
ORIGIN_GRID = 3                                 # an origin: a cell of a 3 x 3 grid, column by column
GLYPH_ORIGIN = 4                                # a text's glyphs (the game's sprites under its null): their centre
ORIGIN_MASK = 0xFF                              # the origin's byte of a sprite's word at 0x50

Box = tuple[float, float, float, float]          # (left, top, right, bottom) in a screen's pixels


def screen_of(code: int) -> str:
    """The screen ("top" or "bottom") of a root group's runtime screen bits; any value but 7 is the top screen's."""
    return RUNTIME_SCREENS.get(code, "top")


def screen_centre(screen: str) -> tuple[float, float]:
    width, height = SCREEN_SIZES[screen]
    return width / 2, height / 2


def to_pixels(screen: str, x: float, y: float) -> tuple[float, float]:
    """A layout point (x, y) as pixels of `screen` (x right, y down from its top-left corner)."""
    cx, cy = screen_centre(screen)
    return cx - x, cy - y


def to_layout(screen: str, px: float, py: float) -> tuple[float, float]:
    cx, cy = screen_centre(screen)
    return cx - px, cy - py


def origin_point(origin: int | None) -> tuple[float, float]:
    """Which point of a box its position is, as fractions of its width and height from its top-left corner (in screen
    terms): (0, 0) for origin 0, (0.5, 0.5) for 4. An origin outside the grid is read as 0."""
    cell = (origin or 0) & ORIGIN_MASK
    if cell >= ORIGIN_GRID * ORIGIN_GRID:
        cell = 0
    return (cell // ORIGIN_GRID) / (ORIGIN_GRID - 1), (cell % ORIGIN_GRID) / (ORIGIN_GRID - 1)


def texture_turn(origin: int | None) -> int:
    """How a sprite's texture is turned in its quad: the second byte of its origin word (`TEXTURE_TURNS`)."""
    return (origin or 0) >> 8 & 0xFF


def turned(turn: int, s, t):
    """The point (s, t) of a sprite's texture region (0-1 from its top-left) that its quad shows at (s, t): numbers or
    numpy arrays. Turns: 0 none, 1 mirrored left to right, 2 upside down, 3 a quarter turn clockwise, 4 half a turn,
    5 a quarter turn anticlockwise (measured on the files' four-corner frames: ui497's 0, 1, 2, 4 around a box,
    ui004's 0, 3, 4, 5); another value is read as none."""
    if turn == 1:
        return 1 - s, t
    if turn == 2:
        return s, 1 - t
    if turn == 3:
        return t, 1 - s
    if turn == 4:
        return 1 - s, 1 - t
    if turn == 5:
        return 1 - t, s
    return s, t


@dataclass(frozen=True)
class Frame:
    """Where a pane's children are: the layout point their positions start from and the scale above them."""
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0

    def point(self, position) -> tuple[float, float]:
        """A child's position as an absolute layout point."""
        return self.x + self.scale_x * position[0], self.y + self.scale_y * position[1]

    def child(self, position, scale=(1.0, 1.0)) -> "Frame":
        """The frame of a null at `position` with `scale` (a root group: its position, scale 1)."""
        x, y = self.point(position)
        return Frame(x, y, self.scale_x * scale[0], self.scale_y * scale[1])


def quad(screen: str, frame: Frame, position, size, scale=(1.0, 1.0), rotation: float = 0.0,
         origin: int | None = 0) -> list[tuple[float, float]]:
    """The four corners in `screen`'s pixels of a sprite (or a text's box) of `size` at `position` under `frame`:
    top-left, top-right, bottom-right, bottom-left as the texture's u, v run (u0 v0, u1 v0, u1 v1, u0 v1)."""
    px, py = to_pixels(screen, *frame.point(position))
    width = size[0] * scale[0] * frame.scale_x
    height = size[1] * scale[1] * frame.scale_y
    fx, fy = origin_point(origin)
    angle = 2 * math.pi * rotation / ANGLE_UNITS
    cos, sin = math.cos(angle), math.sin(angle)
    corners = []
    for s, t in ((0, 0), (1, 0), (1, 1), (0, 1)):
        dx, dy = (s - fx) * width, (t - fy) * height
        corners.append((px + dx * cos - dy * sin, py + dx * sin + dy * cos))
    return corners


def bounds(points: Iterable[tuple[float, float]]) -> Box:
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def union(boxes: Iterable[Box]) -> Box | None:
    boxes = list(boxes)
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def clip(box: Box, screen: str) -> Box | None:
    """`box` cut to `screen`; None when nothing of it is on the screen."""
    width, height = SCREEN_SIZES[screen]
    out = (max(box[0], 0.0), max(box[1], 0.0), min(box[2], float(width)), min(box[3], float(height)))
    return out if out[0] < out[2] and out[1] < out[3] else None


def file_boxes(layout: Layout, groups: Iterable[str], screen: str, cut: bool = True,
               only: Iterable[str] | None = None, skip: Iterable[str] = ()) -> list[tuple[Pane, Box]]:
    """(pane, box in `screen`'s pixels) of every sprite and text of the root groups `groups` that shows as the layout
    file loads: the panes `visible_boxes` counts (no boundaries, nothing under a hidden null, no hidden sprite, no
    fully transparent one, no empty one), each by its origin; cut to the screen unless `cut` is false. `only`: just the
    panes named there and what is under them (a part block's, config.Arrangement.box_panes); `skip`: those left out."""
    wanted = set(groups)
    only = None if only is None else set(only)
    skip = set(skip)
    out: list[tuple[Pane, Box]] = []

    def walk(pane: Pane, frame: Frame, inside: bool) -> None:
        for child in pane.children:
            if child.kind == PaneKind.BOUNDARY or child.visible is False or child.name in skip:
                continue
            here = inside or (only is not None and child.name in only)
            if child.kind == PaneKind.NULL:
                walk(child, frame.child(child.position, child.scale), here)
                continue
            if not here or child.kind not in (PaneKind.SPRITE, PaneKind.TEXT) or all(c[3] == 0 for c in child.colors):
                continue
            if child.kind == PaneKind.SPRITE:
                corners = quad(screen, frame, child.position, child.size, child.scale, 0.0, child.origin)
            else:
                corners = quad(screen, frame, child.position, child.size, (1.0, 1.0), 0.0, child.text_origin)
            box = bounds(corners)
            if box[0] == box[2] or box[1] == box[3]:
                continue
            if cut:
                box = clip(box, screen)
                if box is None:
                    continue
            out.append((child, box))

    for root in layout.roots:
        if root.name in wanted:
            walk(root, Frame().child(root.position), only is None)
    return out


def reference_box(layout: Layout, groups: Iterable[str], screen: str, only: Iterable[str] | None = None,
                  skip: Iterable[str] = ()) -> Box | None:
    """A block's reference box: the box around what its root groups `groups` show as `layout` loads (`only` and `skip`
    as file_boxes'), in its own `screen`'s pixels, cut to that screen; None when nothing of them shows there."""
    return union(box for _, box in file_boxes(layout, groups, screen, only=only, skip=skip))


@dataclass(frozen=True)
class Affine:
    """A map of pixels from screen `source` to screen `target`: p -> scale * p + (dx, dy)."""
    scale: float = 1.0
    dx: float = 0.0
    dy: float = 0.0
    source: str = "top"
    target: str = "top"

    def apply(self, x: float, y: float) -> tuple[float, float]:
        return self.scale * x + self.dx, self.scale * y + self.dy

    def box(self, box: Box) -> Box:
        x0, y0 = self.apply(box[0], box[1])
        x1, y1 = self.apply(box[2], box[3])
        return x0, y0, x1, y1


def placement_transform(box: Box, own_screen: str, x: float | None = None, y: float | None = None,
                        scale: float | None = None, screen: str | None = None) -> Affine:
    """The map a placement applies to a block whose reference box is `box` on `own_screen`: the box's top-left corner
    goes to (`x`, `y`) of `screen`, every size times `scale`. A value left None is the game's own (the box's corner,
    scale 1, its own screen)."""
    scale = 1.0 if scale is None else float(scale)
    x = box[0] if x is None else float(x)
    y = box[1] if y is None else float(y)
    return Affine(scale, x - scale * box[0], y - scale * box[1], own_screen, screen or own_screen)


def wrapper_null(affine: Affine, group_position) -> tuple[tuple[float, float], float]:
    """(position, scale) of a null wrapped around a root group's children, under the group at its own
    `group_position` (the game's translate, layout units) and shown on `affine.target`, that draws them where `affine`
    puts them: the values the engine writes every frame."""
    ox, oy = screen_centre(affine.source)
    tx, ty = screen_centre(affine.target)
    s = affine.scale
    gx, gy = group_position
    return (tx - affine.dx - s * ox - (1 - s) * gx, ty - affine.dy - s * oy - (1 - s) * gy), s
