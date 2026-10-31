"""Semi-fake progress bar animation (no tkinter, so it can be tested headless).

The real work is fast and uneven, so the bar does not show raw progress:

* each pipeline stage has a checkpoint (CHECKPOINTS); while a stage runs, the
  bar creeps towards the next checkpoint ever more slowly (it never reaches it);
* when the stage really ends, the bar jumps to that checkpoint;
* every stage stays on screen at least MIN_STAGE_SECONDS, so a fast run still
  shows the whole sequence; real quest progress is a floor inside "quests";
* at the end the bar rushes to 100 % and only then reports "finished".
"""

from collections import deque

CHECKPOINTS = {"start": 0.0, "rom": 0.04, "quests": 0.14, "write": 0.74, "equipment": 0.82, "install": 0.9,
               "done": 1.0}  # "install": copying into the emulator or the SD card (the Qt installer)
ORDER = tuple(CHECKPOINTS)
MIN_STAGE_SECONDS = 0.45   # minimum time a stage is shown
CREEP = 0.045              # share of the remaining distance covered per tick while waiting (deceleration)
FINAL_RUSH = 0.28          # same, once done
HEADROOM = 0.015           # the bar stops this short of the next checkpoint while waiting
QUESTS_SPAN = ("quests", "write")  # real quest progress fills this span


class ProgressAnimator:
    def __init__(self, now: float):
        self.value = 0.0
        self.stage = "start"
        self.stage_started = now
        self.pending: deque[str] = deque()
        self.quest_fraction = 0.0

    def push_stage(self, name: str) -> None:
        self.pending.append(name)

    def set_quest_fraction(self, fraction: float) -> None:
        self.quest_fraction = max(self.quest_fraction, min(1.0, fraction))

    def _ceiling(self) -> float:
        later = [CHECKPOINTS[s] for s in ORDER[ORDER.index(self.stage) + 1:]]
        return later[0] if later else 1.0

    def tick(self, now: float) -> float:
        if self.pending and now - self.stage_started >= MIN_STAGE_SECONDS:
            self.stage = self.pending.popleft()
            self.stage_started = now
            self.value = max(self.value, CHECKPOINTS[self.stage])  # jump to the checkpoint
        if self.stage == "done":
            self.value += (1.0 - self.value) * FINAL_RUSH
            if 1.0 - self.value < 0.002:
                self.value = 1.0
            return self.value
        target = self._ceiling() - HEADROOM
        self.value = max(self.value, self.value + (target - self.value) * CREEP)
        if self.stage == QUESTS_SPAN[0]:
            low, high = CHECKPOINTS[QUESTS_SPAN[0]], CHECKPOINTS[QUESTS_SPAN[1]] - HEADROOM
            self.value = max(self.value, low + (high - low) * self.quest_fraction)
        return self.value

    @property
    def finished(self) -> bool:
        return self.stage == "done" and self.value >= 1.0
