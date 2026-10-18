"""Building blocks for the Phase 9 experiments (scripts/evaluate.py writes docs/evaluation.md).

Everything here is deterministic: the random experiments take a `random.Random` made from a fixed
seed. The functions are small and pure so that they can be tested on hand-made data.
"""
import math
import random

from .models import Offer, RankedOffer, TravelRequest
from .ranking import assemble_ranking, compute_scores


class ScoredSet:
    """Candidates and their criterion scores, computed once. Criterion scores do not depend on the
    weights, so an experiment can then try thousands of weight vectors cheaply with `rank()`."""

    def __init__(self, offers: list[Offer], request: TravelRequest, names: list[str]):
        self.offers = list(offers)
        self.request = request
        self.names = list(names)
        self.scores = compute_scores(self.offers, request, self.names)

    def rank(self, weights: dict) -> list[RankedOffer]:
        missing = [n for n in weights if n not in self.names]
        if missing:
            raise KeyError(f"criteria not scored in this set: {missing}")
        return assemble_ranking(self.offers, self.scores, weights)


def order_of(ranked: list[RankedOffer]) -> list[str]:
    return [r.offer.offer_id for r in ranked]


# ---- weights --------------------------------------------------------------------
def rescale_weights(weights: dict, criterion: str, value: float) -> dict:
    """Give `criterion` the weight `value` and scale all the other weights in proportion so that the
    total stays 1.0 (so the other criteria keep their relative importance)."""
    if criterion not in weights:
        raise KeyError(criterion)
    if not 0.0 <= value <= 1.0:
        raise ValueError("weight must be between 0 and 1")
    others = {n: w for n, w in weights.items() if n != criterion}
    other_total = sum(others.values())
    result = {criterion: value}
    for n, w in others.items():
        if other_total > 0:
            result[n] = w * (1.0 - value) / other_total
        else:
            result[n] = (1.0 - value) / len(others) if others else 0.0
    return {n: round(w, 12) for n, w in result.items()}


def winner_interval(sset: ScoredSet, weights: dict, criterion: str,
                    step: float = 0.005) -> tuple[float, float]:
    """The range of weights for `criterion` (others rescaled) over which the baseline winner stays
    the winner, searching outward from the baseline in steps of `step` and stopping at the first change."""
    baseline = order_of(sset.rank(weights))[0]
    base = weights[criterion]
    n_steps = round(1.0 / step)

    def same(value: float) -> bool:
        return order_of(sset.rank(rescale_weights(weights, criterion, min(1.0, max(0.0, value)))))[0] == baseline

    k0 = round(base / step)
    lo = hi = k0
    while lo > 0 and same((lo - 1) * step):
        lo -= 1
    while hi < n_steps and same((hi + 1) * step):
        hi += 1
    return round(min(lo * step, base), 6), round(max(hi * step, base), 6)


def random_simplex(rng: random.Random, names: list[str]) -> dict:
    """Weights drawn uniformly from all possible weight vectors that add up to 1."""
    draws = [-math.log(1.0 - rng.random()) for _ in names]
    total = sum(draws)
    return {n: d / total for n, d in zip(names, draws)}


def perturb_weights(rng: random.Random, weights: dict, spread: float) -> dict:
    """Multiply each weight by a random factor in [1-spread, 1+spread] and renormalise. A weight of
    0 stays 0."""
    raw = {n: w * rng.uniform(1.0 - spread, 1.0 + spread) for n, w in weights.items()}
    total = sum(raw.values())
    return {n: v / total for n, v in raw.items()}


# ---- comparing orderings ----------------------------------------------------------
def spearman(order_a: list[str], order_b: list[str]) -> float:
    """Spearman rank correlation (1 = same order, -1 = reversed) of two orderings of the same ids."""
    if sorted(order_a) != sorted(order_b):
        raise ValueError("the two orderings must contain the same items")
    n = len(order_a)
    if n < 2:
        return 1.0
    pos_b = {item: i for i, item in enumerate(order_b)}
    d2 = sum((i - pos_b[item]) ** 2 for i, item in enumerate(order_a))
    return 1.0 - 6.0 * d2 / (n * (n * n - 1))


def inversions(order_a: list[str], order_b: list[str]) -> int:
    """Number of pairs of items that are in a different order in the two lists."""
    if sorted(order_a) != sorted(order_b):
        raise ValueError("the two orderings must contain the same items")
    pos_b = {item: i for i, item in enumerate(order_b)}
    seq = [pos_b[item] for item in order_a]
    return sum(1 for i in range(len(seq)) for j in range(i + 1, len(seq)) if seq[i] > seq[j])


def rank_in(order: list[str], offer_id: str) -> int:
    return order.index(offer_id) + 1


def average_ranks(values: list[float]) -> list[float]:
    """Ranks 1..n where equal values share the average of the ranks they occupy."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def rank_correlation(xs: list[float], ys: list[float]) -> float:
    """Spearman correlation that handles ties (Pearson correlation of the average ranks).
    Returns 0.0 if one of the lists is constant (no order to follow)."""
    if len(xs) != len(ys):
        raise ValueError("the two lists must have the same length")
    if len(xs) < 2:
        return 0.0
    rx, ry = average_ranks(xs), average_ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return 0.0
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sxx * syy) ** 0.5
