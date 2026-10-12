"""Domain model (Task 1).

Design notes (see docs/decisions.md):
- Plain dataclasses for things that mostly hold data.
- Composition: an Offer HAS-A FareConditions. A Booking stores a copy of the
  fare conditions that applied when it was made.
"""
from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True)
class Company:
    name: str
    profile: str


@dataclass(frozen=True)
class Destination:
    name: str


@dataclass(frozen=True)
class FareConditions:
    """Ticket rules. Frozen so a booking's conditions cannot change later."""
    changeable: bool
    refundable: bool
    luggage_kg: int


@dataclass
class Offer:
    offer_id: str
    company: str
    destination: str
    travel_date: date
    departure_time: time
    arrival_time: time
    price: float
    transfers: int
    fare: FareConditions
    seats_available: int
    rating: float

    @property
    def duration_minutes(self) -> int:
        # TODO (Phase 3): handle overnight journeys (arrival on the next day).
        dep = self.departure_time.hour * 60 + self.departure_time.minute
        arr = self.arrival_time.hour * 60 + self.arrival_time.minute
        return arr - dep


@dataclass
class TravelRequest:
    """What the traveller asks for. Hard constraints vs soft preferences."""
    # --- hard constraints (offers violating these are removed) ---
    destination: str
    date_from: date
    date_to: date
    max_budget: float
    max_transfers: int = 99
    require_changeable: bool = False
    # --- soft preferences (used in ranking only) ---
    preferred_departure: time = time(9, 0)
    profile: str = "budget_traveller"


@dataclass
class RankedOffer:
    """One offer after ranking: kept together with the numbers behind its position."""
    offer: Offer
    criterion_scores: dict[str, float]   # name -> 0-100
    total_score: float
    rank: int = 0


@dataclass
class Booking:
    reference: str
    offer_id: str
    company: str
    destination: str
    travel_date: date
    price_paid: float
    traveller_name: str
    fare: FareConditions
    payment_status: str = "SIMULATED-PAID"
