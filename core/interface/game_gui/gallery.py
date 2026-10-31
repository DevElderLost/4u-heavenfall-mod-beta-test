"""The gallery: a local page with the pictures of every recorded screen,
to judge the arrangement by. Never published: it holds the game's pictures.

Per recorded screen (each screen once over the sessions, recorded.py; its latest recording's first snapshot),
in the order of the arrangement's numbers: its number and Spanish name from
the arrangement (the screen its shown groups match), else its signature; the original pair of screens; the arranged
top screen with every block's outline, number ("07.2") and name; the blocks' final places; the warnings; and
"changed since your last review" when its pictures differ from the ones marked reviewed (`mark_reviewed`, a small
JSON of picture digests in work/ui).

    output/ui/galeria/index.html          the page (Spanish)
    output/ui/galeria/img/<signature>_*.png
    output/ui/galeria/digests.json        the digests of this build's pictures
    work/ui/galeria_revisada.json         the digests last reviewed"""

import hashlib
import html
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.interface.game_gui import render
from core.interface.game_gui.config import Arrangement
from core.interface.game_gui import strings as S
from core.interface.game_gui.recorded import RecordedScreen, recorded_screens
from core.interface.game_gui.snapshot import SnapshotFormatError, load

REVIEW_FILE = "galeria_revisada.json"
DIGESTS_FILE = "digests.json"


@dataclass
class GalleryEntry:
    screen: RecordedScreen
    title: str
    images: dict[str, str] = field(default_factory=dict)    # what -> file name under img/
    blocks: list[render.BlockPlace] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    digest: str = ""
    changed: bool = True
    number: str = ""                                        # the arrangement screen's ("07"), "" when none matched


def _digest(*pictures) -> str:
    sha = hashlib.sha1()
    for picture in pictures:
        sha.update(str(picture.shape).encode())
        sha.update(picture.tobytes())
    return sha.hexdigest()[:16]


def _title(entry_screen, signature: str) -> str:
    return S.title(entry_screen) if entry_screen else S.tr(S.GALLERY_UNNAMED, sig=signature)


def build(root: Path, out: Path, assets: render.Assets, arrangement: Arrangement, mode: str = "single_screen",
          settings: render.RenderSettings | None = None) -> Path:
    """Renders every recorded screen under `root` into `out` and writes `out/index.html`; returns its path."""
    settings = settings or render.load_render_settings()
    out = Path(out)
    (out / "img").mkdir(parents=True, exist_ok=True)
    reviewed = _read_json(Path(root) / REVIEW_FILE)
    entries: list[GalleryEntry] = []
    digests: dict[str, str] = {}
    for recorded in recorded_screens(root):
        try:
            snapshot = load(recorded.snapshot)
        except (OSError, SnapshotFormatError) as error:
            entries.append(GalleryEntry(recorded, S.tr(S.GALLERY_UNNAMED, sig=recorded.signature),
                                        warnings=[S.tr(S.GALLERY_UNREADABLE, error=error)]))
            continue
        original = render.render_recorded(snapshot, assets, settings)
        arranged = render.render_arranged(snapshot, assets, arrangement, mode, settings)
        entry = GalleryEntry(recorded, _title(arranged.screen, recorded.signature), blocks=arranged.blocks,
                             warnings=arranged.warnings, number=arranged.screen.number if arranged.screen else "")
        stem = recorded.signature
        for name, picture in original.screens.items():
            entry.images[f"original_{name}"] = render.save_png(
                picture, out / "img" / f"{stem}_{name}.png", settings.zoom).name
        shown = ["top"] if mode == "single_screen" else ["top", "bottom"]
        for name in shown:
            image = render.outlined(arranged.screens[name], arranged.blocks, name, settings)
            entry.images[f"arranged_{name}"] = render.save_png(image, out / "img" / f"{stem}_ordenada_{name}.png").name
        entry.digest = _digest(*original.screens.values(), *(arranged.screens[name] for name in shown))
        entry.changed = reviewed.get(recorded.signature) != entry.digest
        digests[recorded.signature] = entry.digest
        entries.append(entry)
    entries.sort(key=lambda entry: (entry.number or "~", entry.screen.signature))
    _write_json(out / DIGESTS_FILE, digests)
    page = out / "index.html"
    page.write_text(_page(entries, mode), encoding="utf-8")
    return page


def mark_reviewed(root: Path, out: Path, signatures: list[str] | None = None) -> int:
    """Marks the pictures of the last build in `out` as reviewed (all, or only `signatures`); returns how many."""
    built = _read_json(Path(out) / DIGESTS_FILE)
    path = Path(root) / REVIEW_FILE
    reviewed = _read_json(path)
    chosen = {s: d for s, d in built.items() if signatures is None or s in signatures}
    reviewed.update(chosen)
    _write_json(path, reviewed)
    return len(chosen)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


def _place(place: render.BlockPlace) -> str:
    p = place.placement
    if p.hidden:
        return S.tr(S.HIDDEN)
    parts = [S.tr(S.SIDE_SCREEN, side=S.side_name(place.screen))]
    if place.box is not None:
        parts.append(f"x {place.box[0]:.0f}, y {place.box[1]:.0f}")
    parts.append(S.tr(S.SCALE, scale=f"{p.scale if p.scale is not None else 1:g}"))
    if p.priority is not None:
        parts.append(S.tr(S.PRIORITY, priority=p.priority))
    return ", ".join(parts)


def _page(entries: list[GalleryEntry], mode: str) -> str:
    e = html.escape
    changed = sum(entry.changed for entry in entries)
    rows = [
        "<!DOCTYPE html>", f'<html lang="{S.language()}"><head><meta charset="utf-8"><title>'
                           f"{e(S.tr(S.GALLERY_TITLE))}</title>",
        "<style>body{font-family:sans-serif;background:#222;color:#eee;margin:16px}"
        "section{border-top:1px solid #555;padding:8px 0}img{image-rendering:pixelated;margin:4px;"
        "border:1px solid #444}.cambio{color:#fc6;font-weight:bold}.aviso{color:#f88}"
        "figure{display:inline-block;margin:0 8px 0 0;vertical-align:top}figcaption{font-size:13px;color:#aaa}"
        "td{padding:0 12px 0 0}code{color:#9cf}</style></head><body>",
        f"<h1>{e(S.tr(S.GALLERY_TITLE))}</h1>",
        "<p>" + e(S.tr(S.GALLERY_SUMMARY, count=len(entries), changed=changed, mode=S.mode_name(mode),
                       when=time.strftime("%Y-%m-%d %H:%M"))) + "</p>",
    ]
    for entry in entries:
        rows.append(f'<section id="{e(entry.screen.signature)}"><h2>{e(entry.title)}'
                    + (f' <span class="cambio">{e(S.tr(S.GALLERY_CHANGED))}</span>' if entry.changed else "")
                    + "</h2>")
        sessions = entry.screen.sessions
        rows.append(f"<p>{e(S.tr(S.GALLERY_SIGNATURE))} <code>{e(entry.screen.signature)}</code>, "
                    f"{e(S.tr(S.GALLERY_SESSIONS if len(sessions) > 1 else S.GALLERY_SESSION))} "
                    f"{e(', '.join(sessions))}"
                    + (", " + e(S.tr(S.GALLERY_VARIANTS, count=entry.screen.variants)) if entry.screen.variants
                       else "") + "</p>")
        for key, text in S.GALLERY_CAPTIONS.items():
            caption = S.tr(text)
            if key in entry.images:
                rows.append(f'<figure><img src="img/{e(entry.images[key])}" alt="{e(caption)}">'
                            f"<figcaption>{e(caption)}</figcaption></figure>")
        if entry.blocks:
            rows.append("<table><tr>" + "".join(f"<th>{e(S.tr(header))}</th>" for header in S.GALLERY_HEADERS)
                        + "</tr>")
            for place in entry.blocks:
                rows.append(f"<tr><td>{e(place.number)}</td><td>{e(S.named(place.block))}</td>"
                            f"<td>{e(_place(place))}</td></tr>")
            rows.append("</table>")
        else:
            rows.append(f"<p>{e(S.tr(S.GALLERY_NO_BLOCKS))}</p>")
        for warning in entry.warnings:
            rows.append(f'<p class="aviso">{e(S.tr(S.CHECK_WARNING, warning=warning))}</p>')
        rows.append(f"<details><summary>{e(S.tr(S.GALLERY_GROUPS))}</summary><p>"
                    + ", ".join(e(g) for g in entry.screen.groups) + "</p></details></section>")
    rows.append("</body></html>")
    return "\n".join(rows) + "\n"
