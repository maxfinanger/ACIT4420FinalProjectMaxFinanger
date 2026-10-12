"""Weighted multi-criteria ranking (Section 5 in spec).

Score(j) = sum over criteria of  weight_c * score_c(j)
Each criterion function (criteria.py) already returns 0-100, higher = better.
"""
from .criteria import registered_names
from .exceptions import UnknownCriterionError, WeightError
from .models import Offer, RankedOffer, TravelRequest


def validate_weights(weights: dict) -> None:
    unknown = [name for name in weights if name not in registered_names()]
    if unknown:
        raise UnknownCriterionError(f"Unknown criteria in weights: {unknown}")
    if any(w < 0 for w in weights.values()):
        raise WeightError("Weights must not be negative")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise WeightError(f"Weights must sum to 1.0, got {total:.3f}")


def rank_offers(offers: list[Offer], request: TravelRequest,
                weights: dict) -> list[RankedOffer]:
    """TODO (Phase 5): score every offer with each weighted criterion, sort by
    total score, decide tie-breaking, set .rank."""
    validate_weights(weights)
    raise NotImplementedError("Phase 5")
