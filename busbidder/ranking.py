"""Weighted multi-criteria ranking (Section 5 in spec).

    total(j) = sum over criteria c of  weight_c * score_c(j)

Each criterion function (criteria.py) returns 0-100 with higher = better, and the
weights add up to 1.0, so the total is also on a 0-100 scale.
"""
import math
import statistics

from .criteria import get_criterion, registered_names
from .exceptions import ScoringError, UnknownCriterionError, WeightError
from .models import Offer, RankedOffer, TravelRequest

TIE_DECIMALS = 2          # totals are compared at the precision shown to the user


def validate_weights(weights: dict) -> None:
    if not weights:
        raise WeightError("At least one criterion needs a weight")
    unknown = [name for name in weights if name not in registered_names()]
    if unknown:
        raise UnknownCriterionError(f"Unknown criteria in weights: {unknown}")
    if any(not isinstance(w, (int, float)) or isinstance(w, bool) or not math.isfinite(w)
           for w in weights.values()):
        raise WeightError("Weights must be finite numbers")
    if any(w < 0 for w in weights.values()):
        raise WeightError("Weights must not be negative")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise WeightError(f"Weights must sum to 1.0, got {total:.3f}")


def parse_weights(text: str) -> dict:
    """Parse 'price=40,duration=25,departure=15,flexibility=20'. The numbers may add up to
    100 (percent) or to 1.0 (fractions). Raises WeightError / UnknownCriterionError."""
    weights: dict[str, float] = {}
    for part in text.split(","):
        name, sep, value = part.partition("=")
        name = name.strip()
        if not sep or not name:
            raise WeightError(f"Cannot read weight '{part.strip()}', use name=number")
        if name in weights:
            raise WeightError(f"Criterion '{name}' is given twice")
        try:
            weights[name] = float(value)
        except ValueError:
            raise WeightError(f"Weight for '{name}' is not a number: {value.strip()!r}") from None
    if weights and abs(sum(weights.values()) - 100.0) < 1e-6:
        weights = {k: v / 100.0 for k, v in weights.items()}
    validate_weights(weights)
    return weights


def compute_scores(candidates: list[Offer], request: TravelRequest,
                   names: list[str]) -> list[dict[str, float]]:
    """The 0-100 score of every candidate on every named criterion (same order as `candidates`).

    The scores do NOT depend on the weights, so an experiment that tries many weight vectors on the same
    offers can compute them once and call `assemble_ranking` many times.
    """
    all_scores = []
    for offer in candidates:
        scores = {}
        for name in names:
            score = get_criterion(name).func(offer, candidates, request)
            if not isinstance(score, (int, float)) or not math.isfinite(score) \
                    or not 0.0 <= score <= 100.0:
                raise ScoringError(f"Criterion '{name}' gave {score!r} for {offer.offer_id}, "
                                   "expected a number from 0 to 100")
            scores[name] = float(score)
        all_scores.append(scores)
    return all_scores


def assemble_ranking(candidates: list[Offer], all_scores: list[dict[str, float]],
                     weights: dict) -> list[RankedOffer]:
    """Combine precomputed criterion scores with weights, sort, break ties, and set ranks."""
    validate_weights(weights)
    ranked: list[RankedOffer] = []
    for offer, scores in zip(candidates, all_scores):
        scores = {name: scores[name] for name in weights}
        contributions = {name: weights[name] * scores[name] for name in weights}
        ranked.append(RankedOffer(offer, scores, sum(contributions.values()),
                                  contributions=contributions))

    ranked.sort(key=lambda r: (-round(r.total_score, TIE_DECIMALS), r.offer.price,
                               r.offer.duration_minutes, r.offer.departure_datetime,
                               r.offer.offer_id))
    for i, r in enumerate(ranked):
        r.rank = i + 1
    for i, r in enumerate(ranked):
        same_as_prev = i > 0 and round(ranked[i - 1].total_score, TIE_DECIMALS) == round(r.total_score, TIE_DECIMALS)
        same_as_next = i + 1 < len(ranked) and round(ranked[i + 1].total_score, TIE_DECIMALS) == round(r.total_score, TIE_DECIMALS)
        r.tie_broken = same_as_prev or same_as_next
    return ranked


def rank_offers(offers: list[Offer], request: TravelRequest,
                weights: dict) -> list[RankedOffer]:
    """Score every offer with each weighted criterion and sort best first.

    - The input list is not changed, and the result does not depend on its order.
    - Ties (equal total to 2 decimals) are broken by: lower price, shorter
      journey, earlier departure, then offer id. Ranks are 1, 2, 3 ... without gaps,
      and `tie_broken` marks the offers that needed a tie-break (decision D16).
    """
    validate_weights(weights)
    candidates = list(offers)
    if not candidates:
        return []
    return assemble_ranking(candidates, compute_scores(candidates, request, list(weights)), weights)


def influence_share(ranked: list[RankedOffer], weights: dict) -> dict[str, float]:
    """How much each criterion actually separates the offers (0-1, adds up to 1).

    influence = weight x standard deviation of that criterion's scores. A criterion
    with a high weight but almost equal scores for all offers has little influence,
    and the other way round. This is the check for "does one criterion dominate?".
    """
    if len(ranked) < 2:
        return {name: 0.0 for name in weights}
    raw = {name: weights[name] * statistics.pstdev(r.criterion_scores[name] for r in ranked)
           for name in weights}
    total = sum(raw.values())
    return {name: (value / total if total > 0 else 0.0) for name, value in raw.items()}
