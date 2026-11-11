"""What a look of the forge-style screens costs in zenny.

A look's zenny follows what forging the real gear cost in its own game (its **original** price: an armor look the sum of
its pieces', a weapon look its weapon's, a Felyne row its pieces'), mapped into the range of its kind and rank (curated
`recipes.zenny`): within a **pool** (one kind, one listed rank, one game) the cheapest original gets the range's
minimum, the dearest its maximum, the others in between by their place among the pool's prices (a percentile: the
i-th of n different prices sits at i / (n - 1) of the range, so a few dear or cheap pieces never crowd the rest at one
end), rounded to the curated step. A pool is per game because MH4U and XX price their gear on different scales; by
place, both games' looks of one rank spread alike. A look with no original price (none known, or 0), and a pool whose
originals are all equal, cost the range's curated `fallback` point (0.5: the middle).
"""

from collections import defaultdict
from collections.abc import Hashable, Mapping
from dataclasses import dataclass

ZENNY_KINDS = ("armor", "weapons", "felyne")    # the kinds of recipes.zenny, each with a range per rank
RANKS = 3


@dataclass(frozen=True)
class ZennyScale:
    """The curated `recipes.zenny`: kind -> ((low min, max), (high min, max), (G min, max)), the step the prices are
    rounded to, and the point of the range a look with no original price costs (0 the minimum, 1 the maximum)."""
    ranges: Mapping[str, tuple[tuple[int, int], ...]]
    step: int
    fallback: float

    def rounded(self, kind: str, rank: int, value: float) -> int:
        """`value` to the nearest step (a half up), kept inside the rank's range."""
        low, high = self.ranges[kind][rank - 1]
        stepped = int((value + self.step / 2) // self.step) * self.step
        return max(low, min(high, stepped))

    def point(self, kind: str, rank: int, fraction: float) -> int:
        low, high = self.ranges[kind][rank - 1]
        return self.rounded(kind, rank, low + fraction * (high - low))


def scaled_zenny(scale: ZennyScale, looks: Mapping[Hashable, tuple[str, int, int, int | None]]) -> dict:
    """Key -> zenny, for `looks`: key -> (kind, listed rank 1-3, game, original price or None). The pools are by kind,
    rank and game, each look placed by the percentile of its original among the pool's different prices; a look with
    no original (None or 0) takes the fallback point and does not count in its pool."""
    pools: dict[tuple, set[int]] = defaultdict(set)
    for kind, rank, game, original in looks.values():
        if original:
            pools[kind, rank, game].add(original)
    places = {pool: {price: n for n, price in enumerate(sorted(prices))} for pool, prices in pools.items()}
    out = {}
    for key, (kind, rank, game, original) in looks.items():
        place = places.get((kind, rank, game), {})
        if not original or len(place) < 2:
            out[key] = scale.point(kind, rank, scale.fallback)
        else:
            out[key] = scale.point(kind, rank, place[original] / (len(place) - 1))
    return out
