"""Pictures of the game's two screens from a recorder snapshot and the game's files:
as recorded (each root group on its own screen), or arranged (each block of the arrangement moved by its final
placement through geometry.py, the same map the engine applies, and the arrangement's fixes.json made as the build
makes them: its hidden panes left out, its nudged ones moved, its backdrop stretched over the screen, the blocks
measured on the fixed file).

* **What is drawn**: every shown root group's sprites (texture region, size, scale down the tree, the four corner
  colours, alpha, rotation, visibility) and its texts: the glyphs the game laid out (the "text parts" under the null it
  adds after each text, cut from the font's pages), else the string in a plain font in the text's box when a reader
  gives it. Boundaries draw nothing.
* **Values**: a pane's recorded field wins over its layout file's; a value the reader does not give is the file's
  (the sprites' origin, the texts' boxes). A null's colour multiplies everything under it (the game tints a text's
  glyphs by its null's colour). Textures come from the layout's own ARC first, then any ARC of the folders.
* **Order**: layer, then priority (higher in front), then the game's draw list (`draw_links`), then the tree.
* **Pixels**: a pixel is covered when its centre is in the quad (as the 3DS GPU does); textures are read bilinearly,
  multiplied by the corner colours (interpolated), and laid over the picture by their alpha.

Pictures are numpy arrays (height, width, 3) of bytes; `to_qimage` / `save_png` turn them into images (QImage,
offscreen). The numbers (background, font pages, outline colours, zoom) are `data/curated/game_gui/render.json`."""

import json
import os
import struct
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np

from ..arc.arc import ArcFormatError, parse_arc
from ..exefs.titles import MH4U_EUR, MH4U_USA
from ..hud.lyt import LYT_TYPE_HASH, LytFormatError, parse_lyt
from ..hud.single_screen import LayoutSetting, place_layout
from ..hud.tex import TEX_TYPE_HASH, TexFormatError, parse_tex
from . import geometry
from . import strings as S
from .config import ARRANGEMENT_DIR, Arrangement, Block, Placement, Screen
from .recorder.checks import LayoutIndex, file_values, layout_folders, pair_group
from .snapshot import Group, Pane, Snapshot

RENDER_SETTINGS = ARRANGEMENT_DIR / "render.json"
TEXTURE_AT = 0x04            # a sprite's data object: its texture's index in the layout's table (the file's, measured)
FONT_TEXTURE = 0x80000000    # a text part's texture word with this bit: a page of the font (the low byte)
TEXT_ALIGN = {0: 0, 1: 2, 2: 1}   # a text's alignment (0 left, 1 right, 2 centred) -> its column in the box


@dataclass(frozen=True)
class RenderSettings:
    background: tuple[int, int, int]
    font_textures: tuple[str, ...]
    text_font: str
    outline: dict
    label: dict
    zoom: int
    fidelity: dict


def load_render_settings(path: Path = RENDER_SETTINGS) -> RenderSettings:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("description", None)
    names = set(RenderSettings.__dataclass_fields__)
    if set(data) != names:
        raise ValueError(f"{path}: missing {sorted(names - set(data))}, unknown {sorted(set(data) - names)}")
    if not isinstance(data["zoom"], int) or data["zoom"] < 1:
        raise ValueError(f"{path}: zoom must be a whole number, 1 or more")
    return RenderSettings(**{**data, "background": tuple(data["background"]),
                             "font_textures": tuple(data["font_textures"])})


class Assets:
    """The game's layouts and textures from ARC archives, the first given first: the installed mod's, then the RomFS
    dump's (`from_local`), as the recorder's checks name the groups."""

    def __init__(self):
        self.layouts = LayoutIndex()
        self.sources: list[str] = []
        self._arc_of: dict[int, str] = {}
        self._arc_layouts: dict[str, dict[str, object]] = {}    # ARC -> its layouts by name (a fill's template)
        self._textures: dict[str, list[tuple[str, object]]] = {}
        self._decoded: dict[tuple[str, str], np.ndarray | None] = {}
        self._pairs: dict[int, tuple] = {}
        self._fixed: dict[tuple[int, str], object] = {}

    def add_arc(self, label: str, arc) -> None:
        for entry in arc.entries:
            if entry.type_hash == LYT_TYPE_HASH:
                try:
                    layout = parse_lyt(entry.data)
                except LytFormatError:
                    continue
                self.layouts.add(entry.name, layout)
                self._arc_of[id(layout)] = label
                self._arc_layouts.setdefault(label, {})[entry.name.replace("/", "\\").split("\\")[-1]] = layout
            elif entry.type_hash == TEX_TYPE_HASH:
                self._textures.setdefault(entry.name, []).append((label, entry))

    @classmethod
    def from_folders(cls, folders: Iterable[Path]) -> "Assets":
        assets = cls()
        for folder in folders:
            assets.sources.append(str(folder))
            for path in sorted(Path(folder).glob("*.arc")):
                try:
                    arc = parse_arc(path.read_bytes())
                except (ArcFormatError, OSError):
                    continue
                assets.add_arc(str(path), arc)
        assets.layouts.sources = list(assets.sources)
        return assets

    @classmethod
    def from_local(cls, language: str = "spa", emulator_dir: Path | None = None, romfs: Path | None = None,
                   installed: bool = True) -> "Assets":
        """The installed mod's ARCs (unless `installed` is false, or the mod has single-screen mode on: its files are
        already arranged, the recordings are of the game's own GUI) and the RomFS dump's, in `language`: local.ini's
        `emulator_dir` and `mh4u_romfs` unless given."""
        from .. import local_config
        from .recorder.identity import gui_mode, installed_mod
        config = local_config.load()
        emulator_dir = emulator_dir or (config.get("emulator_dir") if installed else None)
        if emulator_dir and any(gui_mode(installed_mod(emulator_dir, title)) != "normal"
                                for title in (MH4U_EUR, MH4U_USA)):
            emulator_dir = None
        romfs = romfs or config.romfs_dir
        return cls.from_folders(layout_folders(emulator_dir, romfs, language))

    def pair(self, group: Group):
        """(layout name, root pane, {id(runtime pane): (file pane or None, role)}) of the file root `group` is, the
        one the recorder's checks named it from; None when it is in no file."""
        cached = self._pairs.get(id(group))
        if cached is None or cached[0] is not group:        # an id is reused once its group is gone
            found = pair_group(group, self.layouts)
            cached = (group, None if found is None else (
                found[0], found[1], {id(pane): (target, role) for pane, target, role in found[2]}, found[2]))
            self._pairs[id(group)] = cached
        return cached[1]

    def arc_of(self, layout) -> str | None:
        return self._arc_of.get(id(layout))

    def fixed(self, layout, setting: LayoutSetting | None):
        """`layout` with `setting`'s fixes made (fixes.json, as the build makes them before the engine measures the
        blocks; a fill's template may be another layout of its ARC); `layout` itself without a setting."""
        if setting is None:
            return layout
        key = (id(layout), repr(setting))           # a setting holds mappings: no hash of its own
        if key not in self._fixed:
            copy = parse_lyt(layout.to_bytes())
            place_layout(copy, [], setting, self._arc_layouts.get(self._arc_of.get(id(layout)), {}))
            self._fixed[key] = copy
        return self._fixed[key]

    def texture(self, name: str, near: str | None = None) -> np.ndarray | None:
        """The texture `name` as RGBA (height, width, 4): the copy in the ARC `near` first, else the first found; None
        when no ARC holds it or its format is not read."""
        found = self._textures.get(name)
        if not found:
            return None
        label, entry = next(((lab, e) for lab, e in found if lab == near), found[0])
        key = (name, label)
        if key not in self._decoded:
            try:
                self._decoded[key] = parse_tex(entry.data).to_array()
            except TexFormatError:
                self._decoded[key] = None
        return self._decoded[key]


@dataclass
class Item:
    """One quad to draw: a sprite, a glyph or a text's box."""
    group: Group
    screen: str
    corners: list[tuple[float, float]]          # top-left, top-right, bottom-right, bottom-left (texture order)
    colors: np.ndarray                          # (4, 4) RGBA 0-1 of the corners: top-left, top-right, bottom-left,
    #                                             bottom-right (the layout's order), tint above included
    layer: int
    priority: int
    rank: int                                   # the group's place in the draw list
    index: int                                  # the pane's place in the group's tree
    texture: np.ndarray | None = None           # None: a solid quad of the corner colours
    uv: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)   # u, v, width, height of the texture region (0-1)
    pane: Pane | None = None
    turn: int = 0                               # how the texture is turned in the quad (geometry.turned)
    block: str | None = None                    # the block that placed it (arrange; a part block for its panes)

    @property
    def key(self) -> tuple:
        return self.layer, self.priority, self.rank, self.index


def draw_ranks(groups: Iterable[Group]) -> dict[int, int]:
    """id(group) -> its place in the game's draw list of shown groups (`draw_links`: the next group drawn first); the
    shown groups the list does not reach follow, by slot."""
    shown = sorted((g for g in groups if g.shown), key=lambda g: g.slot)
    by_address = {g.address: g for g in shown}
    rank: dict[int, int] = {}
    for head in shown:
        links = head.fields.get("draw_links")
        if not links or links[1] in by_address:
            continue
        group = head
        while group is not None and id(group) not in rank:
            rank[id(group)] = len(rank)
            links = group.fields.get("draw_links") or (0, 0)
            group = by_address.get(links[0])
    for group in shown:
        rank.setdefault(id(group), len(rank))
    return rank


def _runtime_texture(pane: Pane) -> int | None:
    if "texture" in pane.fields:
        return pane.fields["texture"]
    raw = bytes.fromhex(pane.raw) if pane.raw else b""
    return struct.unpack_from("<I", raw, TEXTURE_AT)[0] if len(raw) >= TEXTURE_AT + 4 else None


def _colors(corners, tint: np.ndarray) -> np.ndarray:
    return np.asarray(corners, np.float64).reshape(4, 4) / 255.0 * tint


class _Scene:
    def __init__(self, assets: Assets, settings: RenderSettings):
        self.assets, self.settings = assets, settings
        self._fonts: dict[int, np.ndarray | None] = {}
        self.missing: set[str] = set()      # textures sprites name that no ARC holds (not drawn)

    def sprite_texture(self, pane: Pane, role: str, layout, near: str | None) -> tuple[np.ndarray | None, str]:
        """(the texture a sprite draws from, "") or (None, what is missing): a text part's font page, else the
        layout's texture of the sprite's index. Render targets and textures the code makes (the 3D scene behind a
        menu, a word outside the table) are not in the files: such sprites are left out."""
        word = _runtime_texture(pane)
        if role == "text part":
            if word is not None and word & FONT_TEXTURE:
                page = word & 0xFF
                return self.font(page), S.tr(S.FONT_PAGE, page=page)
            return None, S.tr(S.TEXT_TEXTURE, word=f"{word:#x}") if word is not None else S.tr(S.TEXT_TEXTURE_ANY)
        if layout is None or word is None or word >= len(layout.textures):
            return None, S.tr(S.TEXTURE_NOT_IN_TABLE, word=f"{word:#x}") if word is not None else S.tr(S.TEXTURE)
        name = layout.textures[word]
        return self.assets.texture(name, near), name

    def font(self, page: int) -> np.ndarray | None:
        if page not in self._fonts:
            names = self.settings.font_textures
            self._fonts[page] = self.assets.texture(names[page]) if page < len(names) else None
        return self._fonts[page]

    def group_items(self, group: Group, rank: int) -> list[Item]:
        paired = self.assets.pair(group)
        files: dict = paired[2] if paired else {}
        root = paired[1] if paired else None
        layout = root.layout if root is not None else None
        near = self.assets.arc_of(layout) if layout is not None else None
        screen = geometry.screen_of(group.screen)
        position = group.fields.get("position") or (root.position if root is not None else (0.0, 0.0))
        items: list[Item] = []
        counter = [0]

        def add(corners, colors, texture=None, uv=(0.0, 0.0, 1.0, 1.0), pane=None, turn=0):
            counter[0] += 1
            if colors[:, 3].max() <= 0:
                return
            items.append(Item(group, screen, corners, colors, group.layer, group.priority, rank, counter[0],
                              texture, tuple(uv), pane, turn))

        def walk(panes: list[Pane], frame: geometry.Frame, tint: np.ndarray) -> None:
            for at, pane in enumerate(panes):
                target, role = files.get(id(pane), (None, pane.role))
                values = file_values(target) if target is not None else {}

                def get(name, default=None, _pane=pane, _values=values):
                    value = _pane.fields.get(name)
                    return value if value is not None else _values.get(name, default)

                if pane.kind == "null":
                    shown = pane.fields.get("visible", target.visible if target is not None else True)
                    if not shown:
                        counter[0] += 1
                        continue
                    color = np.asarray(get("color", (255, 255, 255, 255)), np.float64) / 255.0
                    walk(pane.children, frame.child(get("position", (0.0, 0.0)), get("scale", (1.0, 1.0))),
                         tint * color)
                elif pane.kind == "sprite":
                    size, scale = get("size", (0.0, 0.0)), get("scale", (1.0, 1.0))
                    if not get("visible", True) or not (size[0] * scale[0] and size[1] * scale[1]):
                        counter[0] += 1
                        continue
                    texture, missing = self.sprite_texture(pane, role, layout, near)
                    if texture is None:
                        self.missing.add(missing)
                        counter[0] += 1
                        continue
                    origin = target.origin if target is not None else (
                        geometry.GLYPH_ORIGIN if role == "text part" else 0)
                    corners = geometry.quad(screen, frame, get("position", (0.0, 0.0)), size, scale,
                                            get("rotation", 0.0) or 0.0, origin)
                    add(corners, _colors(get("colors", [(255, 255, 255, 255)] * 4), tint), texture,
                        get("uv", (0.0, 0.0, 1.0, 1.0)), pane, geometry.texture_turn(origin))
                elif pane.kind == "text":
                    following = panes[at + 1] if at + 1 < len(panes) else None
                    glyphs = following is not None and following.role == "text null" and following.children
                    if pane.text and not glyphs and target is not None:
                        self.text_item(pane, target, frame, tint, add, screen)
                    else:
                        counter[0] += 1

        walk(group.panes, geometry.Frame().child(position), np.ones(4))
        return items

    def text_item(self, pane: Pane, target, frame: geometry.Frame, tint: np.ndarray, add, screen: str) -> None:
        """A text the reader gives as a string and no glyphs: the string in the plain font, in the text's box."""
        position = pane.fields.get("position") or target.position
        corners = geometry.quad(screen, frame, position, target.size, (1.0, 1.0), 0.0,
                                target.text_origin)
        width = max(1, round(abs(target.size[0] * frame.scale_x)))
        height = max(1, round(abs(target.size[1] * frame.scale_y)))
        size = abs(target.font_size[1] * frame.scale_y) or height
        picture = text_picture(pane.text, width, height, size, TEXT_ALIGN.get(target.text_align, 0),
                               self.settings.text_font)
        add(corners, _colors(target.colors, tint), picture, (0.0, 0.0, 1.0, 1.0), pane)


def text_picture(text: str, width: int, height: int, size: float, column: int, family: str) -> np.ndarray:
    """`text` in white on transparent, `width` x `height` pixels, lines `size` pixels high, left (`column` 0),
    centred (1) or right (2) in the box, from its top."""
    _qt()
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(QColor(255, 255, 255, 0))
    painter = QPainter(image)
    font = QFont(family)
    font.setPixelSize(max(1, round(size)))
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255, 255))
    flags = (Qt.AlignmentFlag.AlignLeft, Qt.AlignmentFlag.AlignHCenter, Qt.AlignmentFlag.AlignRight)[column]
    painter.drawText(QRect(0, 0, width, height), int(flags | Qt.AlignmentFlag.AlignTop), text)
    painter.end()
    return _array(image, 4)


def _qt():
    """A Qt application for fonts and painting when none runs (it opens no window). Windows' own platform: its
    offscreen one has no system fonts; elsewhere the offscreen one."""
    from PySide6.QtGui import QGuiApplication
    if QGuiApplication.instance() is None:
        if sys.platform != "win32":
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _qt.app = QGuiApplication([])


def _array(image, channels: int) -> np.ndarray:
    from PySide6.QtGui import QImage
    image = image.convertToFormat(QImage.Format.Format_RGBA8888 if channels == 4 else QImage.Format.Format_RGB888)
    width, height = image.width(), image.height()
    data = np.frombuffer(image.constBits(), np.uint8, count=image.bytesPerLine() * height)
    return data.reshape(height, image.bytesPerLine())[:, :width * channels].reshape(height, width, channels).copy()


def _sample(texture: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bilinear samples (n, 4) of `texture` at u, v (0-1 from its top-left; pixel centres at + 0.5), repeating past
    its edges (the HUD's bars run u from 0 to 5)."""
    height, width = texture.shape[:2]
    x, y = u * width - 0.5, v * height - 0.5
    x0, y0 = np.floor(x), np.floor(y)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    x0i, y0i = x0.astype(np.int64), y0.astype(np.int64)
    xs = np.mod((x0i, x0i + 1), width)
    ys = np.mod((y0i, y0i + 1), height)
    def texels(row, column):
        return texture[ys[row], xs[column]].astype(np.float64)

    return ((texels(0, 0) * (1 - fx) + texels(0, 1) * fx) * (1 - fy)
            + (texels(1, 0) * (1 - fx) + texels(1, 1) * fx) * fy) / 255.0


def draw(canvas: np.ndarray, item: Item) -> None:
    """Lays `item` over `canvas` (height, width, 3) floats 0-1."""
    height, width = canvas.shape[:2]
    corners = np.asarray(item.corners, np.float64)
    left, top = max(int(np.floor(corners[:, 0].min())), 0), max(int(np.floor(corners[:, 1].min())), 0)
    right = min(int(np.ceil(corners[:, 0].max())), width)
    bottom = min(int(np.ceil(corners[:, 1].max())), height)
    if left >= right or top >= bottom:
        return
    e1, e2 = corners[1] - corners[0], corners[3] - corners[0]
    det = e1[0] * e2[1] - e1[1] * e2[0]
    if abs(det) < 1e-9:
        return
    ys, xs = np.mgrid[top:bottom, left:right]
    dx, dy = xs + 0.5 - corners[0, 0], ys + 0.5 - corners[0, 1]
    s = (dx * e2[1] - dy * e2[0]) / det
    t = (e1[0] * dy - e1[1] * dx) / det
    inside = (s >= 0) & (s < 1) & (t >= 0) & (t < 1)
    if not inside.any():
        return
    s, t = s[inside][:, None], t[inside][:, None]
    c = item.colors
    color = (1 - s) * (1 - t) * c[0] + s * (1 - t) * c[1] + (1 - s) * t * c[2] + s * t * c[3]
    if item.texture is not None:
        u0, v0, du, dv = item.uv
        ts, tt = geometry.turned(item.turn, s[:, 0], t[:, 0])
        color = color * _sample(item.texture, u0 + ts * du, v0 + tt * dv)
    alpha = np.clip(color[:, 3:4], 0.0, 1.0)
    region = canvas[top:bottom, left:right]
    region[inside] = region[inside] * (1 - alpha) + np.clip(color[:, :3], 0.0, 1.0) * alpha


def paint(items: Iterable[Item], screen: str, settings: RenderSettings) -> np.ndarray:
    """`screen`'s picture (height, width, 3) of bytes: the items on it in draw order over the background."""
    width, height = geometry.SCREEN_SIZES[screen]
    canvas = np.empty((height, width, 3), np.float64)
    canvas[:] = np.asarray(settings.background, np.float64) / 255.0
    for item in sorted((i for i in items if i.screen == screen), key=lambda i: i.key):
        draw(canvas, item)
    return np.round(canvas * 255).astype(np.uint8)


@dataclass
class BlockPlace:
    """A block as an arranged picture shows it: its number ("07.2"), where it went and the map that moved it."""
    block: Block
    number: str
    placement: Placement
    own_screen: str
    screen: str
    box: geometry.Box | None                    # its reference box moved to `screen`; None when nothing of it shows
    affine: geometry.Affine | None = None


@dataclass
class Picture:
    screens: dict[str, np.ndarray]
    items: list[Item] = field(default_factory=list)
    screen: Screen | None = None                # the arrangement's screen the snapshot matched (arranged only)
    blocks: list[BlockPlace] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def scene(snapshot: Snapshot, assets: Assets, settings: RenderSettings) -> tuple[list[Item], list[str]]:
    """Every item of the snapshot's shown root groups, each on its own screen, and what could not be drawn (in
    Spanish: the gallery shows it)."""
    builder = _Scene(assets, settings)
    out: list[Item] = []
    warnings: list[str] = []
    for manager in snapshot.managers:
        ranks = draw_ranks(manager.groups)
        for group in manager.groups:
            if not group.shown:
                continue
            if assets.pair(group) is None:
                warnings.append(S.tr(S.GROUP_IN_NO_LAYOUT, label=group.label))
                continue
            out += builder.group_items(group, ranks[id(group)])
    if builder.missing:
        warnings.append(S.tr(S.NOT_IN_FILES, items=", ".join(sorted(builder.missing))))
    return out, warnings


def render_recorded(snapshot: Snapshot, assets: Assets, settings: RenderSettings | None = None) -> Picture:
    """Both screens as the snapshot recorded them."""
    settings = settings or load_render_settings()
    items, warnings = scene(snapshot, assets, settings)
    return Picture({screen: paint(items, screen, settings) for screen in geometry.SCREEN_SIZES}, items,
                   warnings=warnings)


def block_numbers(screen: Screen | None, block_ids: Iterable[str], arrangement: Arrangement) -> dict[str, str]:
    """Block id -> "07.2": the screen's number and the block's place, the screen's own blocks first in its order,
    then the other blocks shown in blocks.json's order ("?" for the number when no screen matches)."""
    wanted = set(block_ids)
    order = [b for b in (screen.blocks if screen else {}) if b in wanted]
    order += [b for b in arrangement.blocks if b in wanted and b not in order]
    prefix = screen.number if screen else "?"
    return {block: f"{prefix}.{n}" for n, block in enumerate(order, start=1)}


def _layout_name(group: Group) -> str:
    return (group.layout or "").replace("/", "\\").split("\\")[-1]


def _hidden_panes(group: Group, names: set[str]) -> set[int]:
    """id() of the panes of `group` a fix hides and of everything under them (a text's glyphs are under the null the
    game adds after it); all of them when the root group itself is named."""
    out: set[int] = set()

    def take(pane: Pane) -> None:
        out.add(id(pane))
        for child in pane.children:
            take(child)

    def walk(panes: list[Pane], hidden: bool) -> None:
        for at, pane in enumerate(panes):
            if hidden or pane.name in names:
                take(pane)
                following = panes[at + 1] if at + 1 < len(panes) else None
                if pane.kind == "text" and following is not None and following.role == "text null":
                    take(following)
            else:
                walk(pane.children, False)

    walk(group.panes, group.name in names)
    return out


def _nudged_panes(group: Group, nudge: dict[str, tuple[float, float]]) -> dict[int, tuple[float, float]]:
    """id() of the panes a fix nudges and of everything under them -> the (right, down) pixels they move by
    (fixes.json `nudge`: the file's units, which the build divides by the nulls above the pane, so the root group's
    pixels); every pane of the group when the root group itself is named."""
    out: dict[int, tuple[float, float]] = {}

    def take(pane: Pane, shift: tuple[float, float]) -> None:
        out[id(pane)] = shift
        for child in pane.children:
            take(child, shift)

    def walk(panes: list[Pane]) -> None:
        for at, pane in enumerate(panes):
            if pane.name in nudge:
                take(pane, nudge[pane.name])
                following = panes[at + 1] if at + 1 < len(panes) else None
                if pane.kind == "text" and following is not None and following.role == "text null":
                    take(following, nudge[pane.name])
            else:
                walk(pane.children)

    if group.name in nudge:
        for pane in group.panes:
            take(pane, nudge[group.name])
    else:
        walk(group.panes)
    return out


def _stretch(items: list[Item], screen: str) -> tuple[float, float, float, float] | None:
    """(centre x, centre y, scale x, scale y) that spreads what `items` show of themselves on `screen` over the whole
    screen they end on (fixes.json `backdrop`: the build stretches the group by its visible extent); None when they
    show nothing there."""
    width, height = geometry.SCREEN_SIZES[screen]
    xs = [min(max(x, 0.0), width) for i in items if i.screen == screen for x, _ in i.corners]
    ys = [min(max(y, 0.0), height) for i in items if i.screen == screen for _, y in i.corners]
    if not xs or max(xs) <= min(xs) or max(ys) <= min(ys):
        return None
    top_width, top_height = geometry.SCREEN_SIZES["top"]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, top_width / (max(xs) - min(xs)),
            top_height / (max(ys) - min(ys)))


def arrange(items: list[Item], snapshot: Snapshot, assets: Assets, arrangement: Arrangement,
            mode: str = "single_screen") -> tuple[list[Item], Screen | None, list[BlockPlace], list[str]]:
    """The items moved by the arrangement: the screen the shown groups match, each block shown at its final
    placement (hidden blocks left out), what is in no block left where the game put it; the fixes made first (their
    hidden panes left out, their nudged ones moved, a backdrop stretched over the top screen, as the build does)."""
    shown = [g for g in snapshot.groups() if g.shown]
    names = {g.name for g in shown if g.name}
    warnings: list[str] = []
    hidden: set[int] = set()
    nudged: dict[int, tuple[float, float]] = {}
    stretched: dict[int, tuple[float, float, float, float]] = {}
    fixes = arrangement.fixes if mode == "single_screen" else {}      # the single-screen build's, as the defaults
    for group in shown:
        setting = fixes.get(_layout_name(group))
        if setting is None:
            continue
        hidden |= _hidden_panes(group, set(setting.hide))
        nudged |= _nudged_panes(group, dict(setting.nudge))
        if group.name == setting.backdrop:
            found = _stretch([i for i in items if i.group is group], geometry.screen_of(group.screen))
            if found is None:
                warnings.append(S.tr(S.BACKDROP_EMPTY, name=group.name))
            else:
                stretched[id(group)] = found
    matching = arrangement.matching(names, mode)
    screen = matching[0] if matching else None              # the engine's choice: the first by number
    competing = [s for s in matching if not arrangement.is_overlay(s)] or matching
    if len(competing) > 1:
        warnings.append(S.tr(S.SHOWN_MATCH_SEVERAL, count=len(competing), ids=", ".join(s.id for s in competing)))
    owner = arrangement.owners()
    by_block: dict[str, list[Group]] = {}
    part_of: dict[int, str] = {}                            # id() of a part block's panes -> the part block
    for group in shown:
        if group.name in owner:
            by_block.setdefault(owner[group.name], []).append(group)
            for part in arrangement.parts_of(owner[group.name]):
                found = _hidden_panes(group, set(part.part)) if part.groups[0] == group.name else set()
                if found:
                    part_of |= dict.fromkeys(found, part.id)
                    by_block.setdefault(part.id, []).append(group)
    numbers = block_numbers(screen, by_block, arrangement)
    places: list[BlockPlace] = []
    moved: dict[int, tuple[geometry.Affine | None, Placement, str]] = {}
    affines: dict[str, geometry.Affine | None] = {}
    part_places: dict[str, Placement] = {}                  # a part block's final placement (its own hiding)
    # the whole blocks first: a part block that sets no x, y or scale takes its whole block's map
    for block_id in sorted(by_block, key=lambda b: (bool(arrangement.blocks[b].part),
                                                    [int(p) if p.isdigit() else p for p in numbers[b].split(".")])):
        block, groups = arrangement.blocks[block_id], by_block[block_id]
        placement = arrangement.final(screen, block_id, mode)
        if block.part:
            whole = arrangement.final(screen, arrangement.whole_of(block_id).id, mode)
            placement = replace(placement, screen=whole.screen, priority=whole.priority,
                                hidden=arrangement.hides(screen, block_id, mode))
            part_places[block_id] = placement
        own = geometry.screen_of(groups[0].screen)
        paired = assets.pair(groups[0])
        only, skip = arrangement.box_panes(block_id)
        box = geometry.reference_box(assets.fixed(paired[1].layout, fixes.get(block.layout)), block.groups,
                                     own, only, skip) if paired else None
        affine = None
        if box is None:
            warnings.append(S.tr(S.BLOCK_NO_BOX, id=block_id))
        elif arrangement.follows(screen, block_id, mode):
            affine = affines.get(arrangement.whole_of(block_id).id)
        else:
            affine = geometry.placement_transform(box, own, placement.x, placement.y, placement.scale,
                                                  placement.screen)
        affines[block_id] = affine
        target = affine.target if affine else (placement.screen or own)
        places.append(BlockPlace(block, numbers[block_id], placement, own, target,
                                 affine.box(box) if affine and box else None, affine))
        if not block.part:
            for group in groups:
                moved[id(group)] = (affine, placement, block_id)
    out: list[Item] = []
    for item in items:
        if item.pane is not None and id(item.pane) in hidden:
            continue
        if item.pane is not None and id(item.pane) in nudged:
            dx, dy = nudged[id(item.pane)]
            item = replace(item, corners=[(x + dx, y + dy) for x, y in item.corners])
        if id(item.group) in stretched:
            cx, cy, sx, sy = stretched[id(item.group)]
            item = replace(item, corners=[(cx + sx * (x - cx), cy + sy * (y - cy)) for x, y in item.corners])
        change = moved.get(id(item.group))
        if change is None:
            out.append(item)
            continue
        affine, placement, block_id = change
        in_part = item.pane is not None and id(item.pane) in part_of
        hides = part_places[part_of[id(item.pane)]].hidden if in_part else placement.hidden
        if hides:
            continue
        if in_part:
            block_id = part_of[id(item.pane)]
            affine = affines[block_id]
        corners = [affine.apply(*corner) for corner in item.corners] if affine else item.corners
        out.append(replace(item, corners=corners, screen=affine.target if affine else item.screen,
                           priority=item.priority if placement.priority is None else placement.priority,
                           block=block_id))
    return out, screen, places, warnings


def render_arranged(snapshot: Snapshot, assets: Assets, arrangement: Arrangement, mode: str = "single_screen",
                    settings: RenderSettings | None = None) -> Picture:
    """Both screens with the arrangement applied (in single-screen mode the top screen is what the player sees)."""
    settings = settings or load_render_settings()
    items, missing = scene(snapshot, assets, settings)
    items, screen, places, warnings = arrange(items, snapshot, assets, arrangement, mode)
    return Picture({name: paint(items, name, settings) for name in geometry.SCREEN_SIZES}, items, screen, places,
                   missing + warnings)


def to_qimage(picture: np.ndarray, zoom: int = 1):
    """A picture as a QImage, each pixel `zoom` x `zoom` (no smoothing)."""
    from PySide6.QtGui import QImage
    if zoom > 1:
        picture = picture.repeat(zoom, axis=0).repeat(zoom, axis=1)
    picture = np.ascontiguousarray(picture)
    height, width = picture.shape[:2]
    return QImage(picture.tobytes(), width, height, 3 * width, QImage.Format.Format_RGB888).copy()


def outlined(picture: np.ndarray, blocks: Iterable[BlockPlace], screen: str, settings: RenderSettings,
             zoom: int | None = None):
    """The picture as a QImage, zoomed, with the outline and number of every block on `screen`."""
    _qt()
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QColor, QFont, QPainter, QPen
    zoom = zoom or settings.zoom
    image = to_qimage(picture, zoom)
    painter = QPainter(image)
    font = QFont(settings.text_font)
    font.setPixelSize(settings.label["size"])
    painter.setFont(font)
    for place in blocks:
        if place.box is None or place.screen != screen or place.placement.hidden:
            continue
        x0, y0, x1, y1 = (v * zoom for v in place.box)
        color = settings.outline["backdrop_color" if place.block.backdrop else "color"]
        painter.setPen(QPen(QColor(*color), settings.outline["width"]))
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        text = f"{place.number} {place.block.name}"
        metrics = painter.fontMetrics()
        label = QRectF(x0, y0, metrics.horizontalAdvance(text) + 4, metrics.height())
        painter.fillRect(label, QColor(*settings.label["back"]))
        painter.setPen(QColor(*settings.label["color"]))
        painter.drawText(label.adjusted(2, 0, 0, 0), text)
    painter.end()
    return image


def save_png(image, path: Path, zoom: int = 1) -> Path:
    """Saves a picture (numpy array or QImage) as a PNG."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(image, np.ndarray):
        image = to_qimage(image, zoom)
    if not image.save(str(path), "PNG"):
        raise OSError(f"could not write {path}")
    return path


def read_png(path: Path) -> np.ndarray:
    """An image file as a picture (height, width, 3) of bytes."""
    from PySide6.QtGui import QImage
    image = QImage(str(path))
    if image.isNull():
        raise OSError(f"not an image: {path}")
    return _array(image, 3)
