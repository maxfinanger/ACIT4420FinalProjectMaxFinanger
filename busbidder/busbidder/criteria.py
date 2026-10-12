"""Scoring criteria, collected in a registry by a decorator (Phase 1 decision D5).

Adding a new criterion = write one function and decorate it. The ranker and the
weight validation find it by name, so neither has to be edited.

Every criterion function has the same signature and returns a score on a
0-100 scale where HIGHER IS ALWAYS BETTER (so "lower is better" criteria such
as price must invert their raw value inside the function).
"""
from dataclasses import dataclass
from typing import Callable

from .exceptions import UnknownCriterionError
from .models import Offer, TravelRequest

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


# ---- The four mandatory criteria (bodies are Phase 5) ----------------------

@register_criterion("price", "Lower price is better")
def price_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    raise NotImplementedError("Phase 5")


@register_criterion("duration", "Shorter journey is better")
def duration_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    raise NotImplementedError("Phase 5")


@register_criterion("departure", "Departure close to the preferred time is better")
def departure_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    raise NotImplementedError("Phase 5")


@register_criterion("flexibility", "Changeable / refundable fares are rewarded")
def flexibility_score(offer: Offer, offers: list[Offer], request: TravelRequest) -> float:
    raise NotImplementedError("Phase 5")
