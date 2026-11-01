"""Where the recorder keeps what it records: the main checkout's
`work/ui/`, never in git (it holds the game's texts).

    recordings/<session>/snapshots/<signature>_<n>.json.zst   exact snapshots: each screen once, then its variants
    recordings/<session>/index.json      the GUI mode; the screens: signature -> groups, count, first / last time,
                                         files, variants
    recordings/<session>_single_screen/  the same session's screens while the mod arranged the GUI
    recordings/<session>/transitions.json   [{from, to, count, first, last}]
    marks/<id>/                          the marks saved with Ctrl+P or the "Mark this screen" button (marks.py)
    recorder.log"""

import hashlib
import json
import time
from pathlib import Path

INDEX_FORMAT = 1


def ui_root() -> Path:
    """The main checkout's `work/ui` (local.ini's `work_dir`)."""
    from core.app import local_config
    return local_config.load().work_dir / "ui"


def signature_id(groups) -> str:
    """A short stable name for a set of shown groups."""
    return hashlib.sha1("\n".join(sorted(groups)).encode("utf-8")).hexdigest()[:12]


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    part.replace(path)


def session_name(label: str = "", when: float | None = None) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(time.time() if when is None else when))
    return f"{stamp}_{label}" if label else stamp


class Session:
    """One recording session's folder; the index is written after every change (a crash loses nothing kept). A session
    holds one GUI mode (`gui_mode`, identity.gui_mode): "normal", the game's own GUI, or "single_screen", the GUI the
    mod arranged; an index without it is "normal"."""

    def __init__(self, root: Path, name: str, gui_mode: str = "normal"):
        self.root = Path(root) / "recordings" / name
        self.name = name
        index = self.root / "index.json"
        if index.is_file():
            self.index = json.loads(index.read_text(encoding="utf-8"))
            self.transitions = json.loads((self.root / "transitions.json").read_text(encoding="utf-8")) \
                if (self.root / "transitions.json").is_file() else []
        else:
            self.index = {"format": INDEX_FORMAT, "session": name, "created": time.time(), "gui_mode": gui_mode,
                          "blinking": [], "signatures": {}}
            self.transitions = []

    @property
    def gui_mode(self) -> str:
        return self.index.get("gui_mode", "normal")

    def _save(self) -> None:
        write_json(self.root / "index.json", self.index)
        write_json(self.root / "transitions.json", self.transitions)

    def _file(self, signature: str, snapshot) -> str:
        entry = self.index["signatures"][signature]
        name = f"{signature}_{len(entry['snapshots']) + len(entry['variants']):03d}.json.zst"
        snapshot.save(self.root / "snapshots" / name)
        return f"snapshots/{name}"

    def add_screen(self, groups, snapshot, window: str | None = None, key: str = "") -> str:
        """Counts a stay on the screen whose shown groups are `groups`; its first stay keeps `snapshot`, whose variant
        key (screens.py) is `key`."""
        signature = signature_id(groups)
        entry = self.index["signatures"].setdefault(signature, {
            "groups": sorted(groups), "count": 0, "first": snapshot.time, "last": snapshot.time, "windows": [],
            "base_key": key, "snapshots": [], "variants": []})
        entry["count"] += 1
        entry["last"] = snapshot.time
        if window and window not in entry["windows"]:
            entry["windows"].append(window)
        if not entry["snapshots"]:
            entry["snapshots"].append(self._file(signature, snapshot))
        self._save()
        return signature

    def add_variant(self, signature: str, key: str, snapshot, limit: int) -> bool:
        """Keeps `snapshot` as the screen's variant `key` (another cursor row, another page) unless known or full."""
        entry = self.index["signatures"][signature]
        if any(v["key"] == key for v in entry["variants"]) or len(entry["variants"]) >= limit:
            return False
        entry["variants"].append({"key": key, "time": snapshot.time, "file": self._file(signature, snapshot)})
        self._save()
        return True

    def add_transition(self, before: str, after: str, when: float) -> None:
        for transition in self.transitions:
            if transition["from"] == before and transition["to"] == after:
                transition["count"] += 1
                transition["last"] = when
                break
        else:
            self.transitions.append({"from": before, "to": after, "count": 1, "first": when, "last": when})
        self._save()

    def set_blinking(self, groups) -> None:
        if sorted(groups) != self.index["blinking"]:
            self.index["blinking"] = sorted(groups)
            self._save()


def recorded_signatures(root: Path) -> list[set[str]]:
    """The group sets of every screen recorded in every session under `root` (work/ui)."""
    out = []
    for index in sorted((Path(root) / "recordings").glob("*/index.json")):
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        out += [set(entry["groups"]) for entry in data.get("signatures", {}).values()]
    return out
