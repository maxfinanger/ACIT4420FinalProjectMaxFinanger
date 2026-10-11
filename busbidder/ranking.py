"""Weighted multi-criteria ranking (Section 5). TODO: implement.

Score(j) = w_price*P(j) + w_duration*D(j) + w_time*T(j) + w_flex*F(j)
Each criterion must be normalised to a common 0-100 scale first.
"""
from .exceptions import WeightError
from .models import Offer, TravelRequest

CRITERIA = ("price", "duration", "departure", "flexibility")


def validate_weights(weights: dict) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise WeightError(f"Weights must sum to 1.0, got {total:.3f}")


def rank_offers(offers: list[Offer], request: TravelRequest, weights: dict):
    """TODO: normalise criteria, compute scores, sort, handle ties."""
    validate_weights(weights)
    raise NotImplementedError
