"""How faithful a picture is: a rendered screen against the emulator's own
screenshot of the same moment (the Ctrl+P marks, paired with an exact snapshot by the recorder).

* `split_screenshot`: the emulator's picture as native-size screens. A Ctrl+P picture of the default layout holds the
  top screen above the touch screen, both at one whole scale k (400k x 480k, the touch screen centred under the top
  one); of the top screen alone, 400k x 240k (single-screen mode). Each screen is brought back to native pixels by
  averaging k x k blocks.
* `compare`: the mean difference (0-255), the share of pixels whose largest channel difference passes the threshold,
  the shift (dx, dy) of the picture that matches the screenshot best within `search` pixels (a picture off by a few
  pixels shows here, not as noise), and per box (a block's, a pane's) the share of differing pixels inside it.

The threshold and the search come from render.json ("fidelity")."""

from dataclasses import dataclass, field

import numpy as np

from core.interface.game_gui.geometry import SCREEN_SIZES, Box


class ScreenshotError(ValueError):
    """A picture whose size is no layout of the emulator's screens this code knows."""


def downscale(picture: np.ndarray, factor: int) -> np.ndarray:
    """`picture` (height, width, channels) with each `factor` x `factor` block averaged into one pixel."""
    if factor == 1:
        return picture.astype(np.uint8)
    height, width, channels = picture.shape
    blocks = picture[:height // factor * factor, :width // factor * factor].astype(np.float64)
    blocks = blocks.reshape(height // factor, factor, width // factor, factor, channels)
    return np.round(blocks.mean(axis=(1, 3))).astype(np.uint8)


def split_screenshot(image: np.ndarray) -> dict[str, np.ndarray]:
    """The screens of an emulator screenshot (height, width, 3), each at native size: {"top", "bottom"} for the
    default layout, {"top"} for the top screen alone."""
    height, width = image.shape[:2]
    top_width, top_height = SCREEN_SIZES["top"]
    bottom_width, bottom_height = SCREEN_SIZES["bottom"]
    if width % top_width or height % top_height:
        raise ScreenshotError(f"a {width} x {height} picture is no whole scale of the emulator's screens")
    factor = width // top_width
    if height == factor * top_height:
        return {"top": downscale(image, factor)}
    if height != factor * (top_height + bottom_height):
        raise ScreenshotError(f"a {width} x {height} picture is neither both screens nor the top one")
    left = (top_width - bottom_width) // 2 * factor
    return {"top": downscale(image[:top_height * factor], factor),
            "bottom": downscale(image[top_height * factor:, left:left + bottom_width * factor], factor)}


@dataclass
class Fidelity:
    mean_difference: float                  # mean absolute difference of every channel, 0-255
    changed: float                          # share of pixels whose largest channel difference passes the threshold
    shift: tuple[int, int] = (0, 0)         # the picture's shift (dx, dy) that matches best
    shifted_changed: float = 0.0            # `changed` at that shift (over the pixels both cover)
    boxes: dict[str, float] = field(default_factory=dict)   # per box, `changed` inside it

    def summary(self) -> str:
        line = f"diferencia media {self.mean_difference:.1f}, píxeles distintos {100 * self.changed:.1f} %"
        if self.shift != (0, 0):
            line += (f"; desplazada ({self.shift[0]}, {self.shift[1]}) px encaja mejor: "
                     f"{100 * self.shifted_changed:.1f} %")
        return line


def _changed(a: np.ndarray, b: np.ndarray, threshold: int) -> np.ndarray:
    return np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2) > threshold


def compare(picture: np.ndarray, shot: np.ndarray, threshold: int, search: int = 0,
            boxes: dict[str, Box] | None = None) -> Fidelity:
    """`picture` against `shot`, both (height, width, 3) of one screen."""
    if picture.shape != shot.shape:
        raise ValueError(f"a {picture.shape} picture against a {shot.shape} screenshot")
    difference = np.abs(picture.astype(np.int16) - shot.astype(np.int16))
    changed = difference.max(axis=2) > threshold
    best, best_shift = float(changed.mean()), (0, 0)
    height, width = changed.shape
    for dy in range(-search, search + 1):
        for dx in range(-search, search + 1):
            if (dx, dy) == (0, 0):
                continue
            moved = picture[max(0, -dy):height - max(0, dy), max(0, -dx):width - max(0, dx)]
            under = shot[max(0, dy):height - max(0, -dy), max(0, dx):width - max(0, -dx)]
            share = float(_changed(moved, under, threshold).mean())
            if share < best:
                best, best_shift = share, (dx, dy)
    inside = {}
    for label, (x0, y0, x1, y1) in (boxes or {}).items():
        x0, y0 = max(int(np.floor(x0)), 0), max(int(np.floor(y0)), 0)
        x1, y1 = min(int(np.ceil(x1)), width), min(int(np.ceil(y1)), height)
        inside[label] = float(changed[y0:y1, x0:x1].mean()) if x0 < x1 and y0 < y1 else 0.0
    return Fidelity(float(difference.mean()), float(changed.mean()), best_shift, best, inside)
