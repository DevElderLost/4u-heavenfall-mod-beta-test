"""Screens from a stream of exact snapshots. A screen's signature is the
set of shown root groups, without those measured to blink (shown and hidden `blink_toggles` times within
`blink_window_s`; once measured they stay out for the session). A screen is kept once its signature holds `stable_s`;
while it holds, another variant (a key of the groups' places on screen, the panes shown and the texts: another cursor
row, another page) that holds `stable_s` too is kept, up to `max_variants`. Going from one kept screen to another is a
transition."""

import hashlib
import json
from collections import defaultdict, deque


def variant_key(snapshot, groups) -> str:
    """What tells two looks of one screen apart: per shown group of `groups` its screen and its place (whole pixels),
    the names of its panes shown and its texts. Pane animations (positions, colours) are left out: they never hold."""
    parts = []
    for group in snapshot.groups():
        if group.label not in groups:
            continue
        x, y = group.fields.get("position", (0.0, 0.0))
        shown = [pane.name for pane in group.walk() if pane.name and pane.fields.get("visible", True)]
        texts = [pane.text for pane in group.walk() if pane.text]
        parts.append([group.label, group.screen, round(x), round(y), shown, texts])
    parts.sort(key=lambda part: part[0])
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


class ScreenTracker:
    def __init__(self, settings, session, window: str | None = None):
        self.settings, self.session, self.window = settings, session, window
        self.toggles: dict[str, deque] = defaultdict(deque)
        self.blinking: set[str] = set(session.index.get("blinking", []))
        self.last_shown: set[str] | None = None
        self.candidate: frozenset | None = None
        self.since = 0.0
        self.kept = False                   # the candidate's stay was counted
        self.current: str | None = None     # the signature of the screen the game is on (kept)
        self.variant: tuple[str, float] | None = None
        self.events: deque = deque(maxlen=50)

    def _blink(self, shown: set[str], now: float) -> None:
        if self.last_shown is not None:
            for group in shown ^ self.last_shown:
                self.toggles[group].append(now)
        self.last_shown = shown
        for group, times in list(self.toggles.items()):
            while times and times[0] < now - self.settings.blink_window_s:
                times.popleft()
            if len(times) >= self.settings.blink_toggles and group not in self.blinking:
                self.blinking.add(group)
                self.events.append((now, "blink", group))
            if not times:
                del self.toggles[group]
        self.session.set_blinking(self.blinking)

    def observe(self, snapshot) -> None:
        now = snapshot.time
        shown = set(snapshot.shown())
        self._blink(shown, now)
        signature = frozenset(shown - self.blinking)
        if signature != self.candidate:
            self.candidate, self.since, self.kept, self.variant = signature, now, False, None
            return
        if not signature or now - self.since < self.settings.stable_s:
            return
        if not self.kept:
            found = self.session.add_screen(signature, snapshot, self.window, variant_key(snapshot, signature))
            entry = self.session.index["signatures"][found]
            if self.current and self.current != found:
                self.session.add_transition(self.current, found, now)
            self.events.append((now, "screen", found))
            self.current, self.kept = found, True
            self.variant = (entry["base_key"], now)
            return
        key = variant_key(snapshot, signature)
        if self.variant is None or self.variant[0] != key:
            self.variant = (key, now)
            return
        entry = self.session.index["signatures"][self.current]
        if now - self.variant[1] >= self.settings.stable_s and key != entry.get("base_key"):
            if self.session.add_variant(self.current, key, snapshot, self.settings.max_variants):
                self.events.append((now, "variant", self.current))
