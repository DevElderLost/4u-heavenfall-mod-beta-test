"""The requests the recorder files: the folders the recorder files
in work/ui/peticiones/<id>/ (recorder/marks.py: `request.json`, the windows' snapshots, the Ctrl+P picture). A request
is answered by a file beside it, `respuesta.json` (time, the one-line answer, the commit); nothing is ever deleted or
rewritten, so what was filed stays as it was."""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.interface.game_gui.recorder.store import write_json

REQUESTS_DIR = "peticiones"
REQUEST_FILE = "request.json"
ANSWER_FILE = "respuesta.json"


@dataclass
class Request:
    id: str
    folder: Path
    time: float
    note: str
    picture: Path | None
    windows: dict[str, dict] = field(default_factory=dict)  # window -> its record (snapshot, signature, groups...)
    answer: dict | None = None


def read_requests(root: Path) -> list[Request]:
    """Every request under `root` (work/ui), newest first; a folder whose request.json cannot be read is left out."""
    out = []
    for path in (Path(root) / REQUESTS_DIR).glob(f"*/{REQUEST_FILE}"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        folder = path.parent
        answer = None
        if (folder / ANSWER_FILE).is_file():
            try:
                answer = json.loads((folder / ANSWER_FILE).read_text(encoding="utf-8"))
            except ValueError:
                answer = {}
        picture = folder / data["picture"] if data.get("picture") else None
        out.append(Request(data.get("id", folder.name), folder, float(data.get("time", 0.0)), data.get("note", ""),
                           picture, data.get("windows", {}), answer))
    return sorted(out, key=lambda r: (r.time, r.id), reverse=True)


def pending(root: Path) -> list[Request]:
    """The requests not answered yet, newest first."""
    return [request for request in read_requests(root) if request.answer is None]


def answer(root: Path, request_id: str, text: str, commit: str = "", when: float | None = None) -> Path:
    """Marks the request `request_id` answered (ValueError: no such request, or answered already); returns the
    marker's path."""
    folder = Path(root) / REQUESTS_DIR / request_id
    if not (folder / REQUEST_FILE).is_file():
        raise ValueError(f"no request {request_id} in {folder.parent}")
    if (folder / ANSWER_FILE).exists():
        raise ValueError(f"request {request_id} is answered already ({folder / ANSWER_FILE})")
    path = folder / ANSWER_FILE
    write_json(path, {"time": time.time() if when is None else when, "answer": text, "commit": commit})
    return path
