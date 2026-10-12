"""Hard-constraint filtering (Task 3).

Design (decision D4): every hard constraint is a small class that inherits from
Constraint. Each one can say whether an offer passes AND why it was removed,
which is what makes the hard/soft split visible to the user.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .models import Offer, TravelRequest


class Constraint(ABC):
    """A HARD requirement: an offer that fails it is removed before ranking."""

    @abstractmethod
    def is_satisfied(self, offer: Offer, request: TravelRequest) -> bool:
        ...

    @abstractmethod
    def reason(self, request: TravelRequest) -> str:
        """Short text shown to the user, e.g. 'over budget (max EUR 50)'."""


class BudgetConstraint(Constraint):
    """Worked example. Boundary: a price exactly equal to the budget is accepted."""

    def is_satisfied(self, offer, request):
        return offer.price <= request.max_budget

    def reason(self, request):
        return f"over budget (max EUR {request.max_budget:.2f})"


class DestinationConstraint(Constraint):
    def is_satisfied(self, offer, request):
        raise NotImplementedError("Phase 4")

    def reason(self, request):
        return f"not going to {request.destination}"


class TravelWindowConstraint(Constraint):
    def is_satisfied(self, offer, request):
        raise NotImplementedError("Phase 4")

    def reason(self, request):
        return f"outside travel window {request.date_from} to {request.date_to}"


class SeatsConstraint(Constraint):
    def is_satisfied(self, offer, request):
        raise NotImplementedError("Phase 4")

    def reason(self, request):
        return "no seats available"


class MaxTransfersConstraint(Constraint):
    def is_satisfied(self, offer, request):
        raise NotImplementedError("Phase 4")

    def reason(self, request):
        return f"more than {request.max_transfers} transfers"


class FlexibilityConstraint(Constraint):
    """Only active when the traveller marked a changeable ticket as required."""

    def is_satisfied(self, offer, request):
        raise NotImplementedError("Phase 4")

    def reason(self, request):
        return "ticket is not changeable"


@dataclass
class FilterResult:
    kept: list[Offer]
    removed_by_reason: dict[str, int] = field(default_factory=dict)  # reason -> count


def default_constraints() -> list[Constraint]:
    return [
        DestinationConstraint(),
        TravelWindowConstraint(),
        BudgetConstraint(),
        SeatsConstraint(),
        MaxTransfersConstraint(),
        FlexibilityConstraint(),
    ]


def filter_offers(offers: list[Offer], request: TravelRequest,
                  constraints: list[Constraint] | None = None) -> FilterResult:
    """Keep only offers that pass every constraint; count why the rest were removed.
    TODO (Phase 4)."""
    raise NotImplementedError("Phase 4")
