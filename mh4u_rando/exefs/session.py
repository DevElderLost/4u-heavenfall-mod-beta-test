"""What the patchers of one run write that depends on where the game's code and data sit.

The patchers write into a canonical image: the player's executable laid out as the EUR update's. To map the
result back onto the player's own executable, every word that holds a position must be translated, not copied:
a branch (its offset depends on where it and its target sit) and a pointer to the game's code or data. Our
prelinked blocks carry their relocations in code_space.json; anything else a patcher builds is noted here while a
`recording()` is active. Outside one (tools, most tests) the notes are dropped.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class Session:
    """Canonical addresses: `branches` maps a B/BL/BLX written by a patcher to its target; `pointers` are words a
    patcher wrote that hold a canonical address of the game's code or data; `placed` are the blocks written, by name
    and address (their own relocations are in the layout)."""
    branches: dict[int, int] = field(default_factory=dict)
    pointers: set[int] = field(default_factory=set)
    placed: dict[str, int] = field(default_factory=dict)


_current: ContextVar[Session | None] = ContextVar("exefs_session", default=None)


def current() -> Session | None:
    return _current.get()


@contextmanager
def recording(into: Session | None = None) -> Iterator[Session]:
    """Note what the patchers write until the block ends, in `into` (several blocks of one run add to one session)
    or a new session; nested recordings each get their own session."""
    session = Session() if into is None else into
    token = _current.set(session)
    try:
        yield session
    finally:
        _current.reset(token)


def note_branch(at: int, target: int) -> None:
    session = _current.get()
    if session is not None:
        session.branches[at] = target


def note_pointer(at: int) -> None:
    session = _current.get()
    if session is not None:
        session.pointers.add(at)


def note_place(name: str, at: int) -> None:
    session = _current.get()
    if session is not None:
        session.placed[name] = at
