"""Scoring criteria, collected in a registry by a decorator (decision D5).

Adding a new criterion = write one function and decorate it. The ranker and the
weight validation find it by name, so neither has to be edited.

Every criterion function has the same signature and returns a score on a
0-100 scale where HIGHER IS ALWAYS BETTER (so "lower is better" criteria such
as price invert their raw value inside the function).

Two kinds of scale are used (decision D15, details in docs/scoring.md):
  RELATIVE  (price, duration, emissions): no natural reference point, so an offer
            is judged against the others. The best offer scores 100 and every
            "meaningful difference" (min_span) worse costs 100 points, at most
            down to 0. Very bad outliers cannot stretch the scale.
  ABSOLUTE  (departure, flexibility, transfers, rating): the scale has a natural
            reference (preferred time, fare categories, direct, 5 stars), so the
            score does not depend on which other offers are in the list.
"""
import statistics
from dataclasses import dataclass
from datetime import time
from functools import lru_cache
from typing import Callable

from .exceptions import UnknownCriterionError
from .models import Offer, TravelRequest
from .scoring_config import get_config

ScoreFunc = Callable[[Offer, list[Offer], TravelRequest], float]


@dataclass(frozen=True)
class Criterion:
    name: str
    description: str
    func: ScoreFunc


_REGISTRY: dict[str, Criterion] = {}


def register_criterion(name: str, description: str = ""):
    """Decorator: register a scoring function under `name`."""
    def decorator(func: ScoreFunc) -> ScoreFunc:
        if name in _REGISTRY:
            raise ValueError(f"Criterion '{name}' is already registered")
        _REGISTRY[name] = Criterion(name, description, func)
        return func
    return decorator


def get_criterion(name: str) -> Criterion:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownCriterionError(f"Unknown criterion: '{name}'") from None


def registered_names() -> list[str]:
    return list(_REGISTRY)


# ---- shared helpers ---------------------------------------------------------
def _clamp(score: float) -> float:
    return max(0.0, min(100.0, score))


@lru_cache(maxsize=64)
def _best_and_worst(values: tuple, cap_factor: float) -> tuple[float, float]:
    """Reference points of a relative scale: the best value and the worst value that
    still counts (the real maximum, but never more than cap_factor x the median)."""
    best = min(values)
    worst = min(max(values), cap_factor * statistics.median(values))
    return best, max(best, worst)


def relative_lower_is_better(value: float, values: list[float], min_span: float,
                             cap_factor: float) -> float:
    """100 for the lowest value, falling linearly to 0 over the spread of the values
    (but over at least `min_span`, so tiny differences are not blown up)."""
    best, worst = _best_and_worst(tuple(values), cap_factor)
    span = max(worst - best, min_span)
    return _clamp(100.0 - 100.0 * (value - best) / span)


def minutes_between(t1: time, t2: time) -> int:
    """Shortest distance between two clock times, around midnight too (23:55 and 00:30 are 35 min)."""
    a, b = t1.hour * 60 + t1.minute, t2.hour * 60 + t2.minute
    d = abs(a - b)
    return min(d, 24 * 60 - d)


# ---- the four mandatory criteria -------------------------------------------
@register_criterion("price", "Lower price is better")
def price_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    cfg = get_config()
    return relative_lower_is_better(offer.price, [o.price for o in offers],
                                    cfg.price_min_span_eur, cfg.outlier_cap_factor)


@register_criterion("duration", "Shorter journey is better")
def duration_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    cfg = get_config()
    return relative_lower_is_better(offer.duration_minutes, [o.duration_minutes for o in offers],
                                    cfg.duration_min_span_minutes, cfg.outlier_cap_factor)


@register_criterion("departure", "Departure close to the preferred time is better")
def departure_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    """100 at the preferred time, 0 at `tolerance_minutes` away (absolute scale)."""
    diff = minutes_between(offer.departure_time, request.preferred_departure)
    return _clamp(100.0 * (1 - diff / get_config().departure_tolerance_minutes))


@register_criterion("flexibility", "Changeable / refundable fares are rewarded")
def flexibility_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    """Fixed score per fare category (absolute scale)."""
    cfg, fare = get_config(), offer.fare
    if fare.changeable and fare.refundable:
        return cfg.flex_both
    if fare.changeable:
        return cfg.flex_changeable
    if fare.refundable:
        return cfg.flex_refundable
    return cfg.flex_none


# ---- optional criteria (only used when a profile gives them a weight) ------
@register_criterion("transfers", "Fewer transfers are better")
def transfers_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    """Direct = 100, falling evenly to 0 at `max_reference` transfers (absolute)."""
    return _clamp(100.0 * (1 - offer.transfers / get_config().transfers_max_reference))


@register_criterion("rating", "Higher customer rating is better")
def rating_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    """Rating 0-5 mapped to 0-100 (absolute)."""
    return _clamp(offer.rating / 5.0 * 100.0)


@register_criterion("emissions", "Lower CO2 emissions are better")
def emissions_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    """Relative scale over the offers that report emissions. An offer without a figure
    gets `missing_value_score` (no information is not good news, decision D16)."""
    cfg = get_config()
    if offer.emissions_kg is None:
        return cfg.missing_value_score
    values = [o.emissions_kg for o in offers if o.emissions_kg is not None]
    return relative_lower_is_better(offer.emissions_kg, values,
                                    cfg.emissions_min_span_kg, cfg.outlier_cap_factor)
