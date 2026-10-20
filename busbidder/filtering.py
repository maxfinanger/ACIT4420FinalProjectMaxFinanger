"""Hard-constraint filtering (Task 3).

Design (decisions D4, D6, D14): every hard constraint is a small class that
inherits from Constraint. Each one can say
  - whether an offer passes            (is_satisfied)
  - why an offer was removed           (reason)
  - what the traveller required        (requirement)
  - whether it applies to this request (is_active)
Optional limits (transfers, duration, luggage, changeable ticket) are only
ACTIVE when the traveller set them; otherwise they are not hard constraints.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .criteria import get_criterion, registered_names
from .models import Offer, TravelRequest
from .validation import validate_request


def _hours_minutes(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} min" if m else f"{h} h"


class Constraint(ABC):
    """A HARD requirement: an offer that fails it is removed before ranking."""

    def is_active(self, request: TravelRequest) -> bool:
        return True

    @abstractmethod
    def is_satisfied(self, offer: Offer, request: TravelRequest) -> bool:
        ...

    @abstractmethod
    def reason(self, request: TravelRequest) -> str:
        """Why an offer was removed, e.g. 'over budget (max EUR 50.00)'."""

    @abstractmethod
    def requirement(self, request: TravelRequest) -> str:
        """What the traveller required, e.g. 'price at most EUR 50.00'."""


class DestinationConstraint(Constraint):
    def is_satisfied(self, offer, request):
        return offer.destination == request.destination

    def reason(self, request):
        return f"wrong destination (wanted {request.destination})"

    def requirement(self, request):
        return f"destination: {request.destination}"


class TravelWindowConstraint(Constraint):
    """The DEPARTURE date must lie in the window; both end days are included."""

    def is_satisfied(self, offer, request):
        return request.date_from <= offer.travel_date <= request.date_to

    def reason(self, request):
        return f"departs outside {request.date_from} to {request.date_to}"

    def requirement(self, request):
        return f"departure between {request.date_from} and {request.date_to} (both days included)"


class SeatsConstraint(Constraint):
    def is_satisfied(self, offer, request):
        return offer.seats_available >= 1

    def reason(self, request):
        return "no seats left"

    def requirement(self, request):
        return "at least 1 seat available"


class BudgetConstraint(Constraint):
    """Boundary: a price exactly equal to the budget is accepted."""

    def is_satisfied(self, offer, request):
        return offer.price <= request.max_budget

    def reason(self, request):
        return f"over budget (max EUR {request.max_budget:.2f})"

    def requirement(self, request):
        return f"price at most EUR {request.max_budget:.2f}"


class MaxTransfersConstraint(Constraint):
    def is_active(self, request):
        return request.max_transfers is not None

    def is_satisfied(self, offer, request):
        return offer.transfers <= request.max_transfers

    def reason(self, request):
        return f"too many transfers (max {request.max_transfers})"

    def requirement(self, request):
        return f"at most {request.max_transfers} transfer(s)"


class MaxDurationConstraint(Constraint):
    def is_active(self, request):
        return request.max_duration_minutes is not None

    def is_satisfied(self, offer, request):
        return offer.duration_minutes <= request.max_duration_minutes

    def reason(self, request):
        return f"journey longer than {_hours_minutes(request.max_duration_minutes)}"

    def requirement(self, request):
        return f"journey at most {_hours_minutes(request.max_duration_minutes)}"


class LuggageConstraint(Constraint):
    def is_active(self, request):
        return request.min_luggage_kg > 0

    def is_satisfied(self, offer, request):
        return offer.fare.luggage_kg >= request.min_luggage_kg

    def reason(self, request):
        return f"luggage allowance below {request.min_luggage_kg} kg"

    def requirement(self, request):
        return f"luggage allowance at least {request.min_luggage_kg} kg"


class FlexibilityConstraint(Constraint):
    """Only active when the traveller marked a changeable ticket as required."""

    def is_active(self, request):
        return request.require_changeable

    def is_satisfied(self, offer, request):
        return offer.fare.changeable

    def reason(self, request):
        return "ticket is not changeable"

    def requirement(self, request):
        return "ticket must be changeable"


def default_constraints() -> list[Constraint]:
    """Order matters for the report: first WHICH trip, then availability, then the
    traveller's own limits (decision D14)."""
    return [
        DestinationConstraint(),
        TravelWindowConstraint(),
        SeatsConstraint(),
        BudgetConstraint(),
        MaxTransfersConstraint(),
        MaxDurationConstraint(),
        LuggageConstraint(),
        FlexibilityConstraint(),
    ]


@dataclass
class FilterResult:
    kept: list[Offer]
    considered: int = 0
    # reason -> offers removed. Each removed offer is counted ONCE, under the first
    # (active) constraint it fails, so the numbers add up. Zeros are included.
    removed_by_reason: dict[str, int] = field(default_factory=dict)
    # reason -> offers that fail ONLY that constraint (what relaxing it would give back)
    near_misses: dict[str, int] = field(default_factory=dict)

    @property
    def removed_count(self) -> int:
        return sum(self.removed_by_reason.values())

    def report_lines(self) -> list[str]:
        """Text shown to the user: what was removed and why."""
        if self.considered == 0:
            return ["No offers to filter."]
        lines = [f"Filtering {self.considered} offers "
                 "(each removed offer is counted once, under the first rule it breaks):"]
        for reason, count in self.removed_by_reason.items():
            lines.append(f"  removed {count:>5}   {reason}")
        lines.append(f"Remaining: {len(self.kept)} offers")
        if not self.kept:
            lines.append("No offer meets every hard constraint.")
            if self.near_misses:
                reason, count = max(self.near_misses.items(), key=lambda kv: kv[1])
                lines.append(f"Hint: relaxing only '{reason}' would give {count} offer(s).")
            else:
                lines.append("Hint: no single requirement is to blame, several must be relaxed together.")
        return lines


def filter_offers(offers: list[Offer], request: TravelRequest,
                  constraints: list[Constraint] | None = None) -> FilterResult:
    """Keep only offers that pass every ACTIVE constraint; count why the rest were removed.

    Raises ValidationError if the request itself is invalid. The input list is
    not modified, and the order of the kept offers is the input order.
    """
    validate_request(request)
    active = [c for c in (constraints if constraints is not None else default_constraints())
              if c.is_active(request)]
    reasons = [c.reason(request) for c in active]

    kept: list[Offer] = []
    removed = {reason: 0 for reason in reasons}
    near: dict[str, int] = {}
    for offer in offers:
        failed = [i for i, c in enumerate(active) if not c.is_satisfied(offer, request)]
        if not failed:
            kept.append(offer)
            continue
        removed[reasons[failed[0]]] += 1
        if len(failed) == 1:
            near[reasons[failed[0]]] = near.get(reasons[failed[0]], 0) + 1
    return FilterResult(kept=kept, considered=len(offers),
                        removed_by_reason=removed, near_misses=near)


# ---- making the hard / soft split visible to the user -----------------------
def hard_constraint_lines(request: TravelRequest,
                          constraints: list[Constraint] | None = None) -> list[str]:
    """What the traveller REQUIRES: breaking any of these removes the offer."""
    constraints = constraints if constraints is not None else default_constraints()
    return [c.requirement(request) for c in constraints if c.is_active(request)]


def soft_preference_lines(request: TravelRequest, weights: dict | None = None) -> list[str]:
    """What only affects the SCORE (ranking): never removes an offer."""
    lines = []
    names = [n for n in registered_names() if weights is None or n in weights]
    for name in names:
        text = f"{name}: {get_criterion(name).description}"
        if weights and name in weights:
            text += f" (weight {weights[name]:.2f})"
        lines.append(text)
    lines.append(f"preferred departure time: {request.preferred_departure:%H:%M}")
    lines.append(f"profile: {request.profile}")
    return lines
