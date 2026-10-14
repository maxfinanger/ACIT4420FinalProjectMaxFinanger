"""Domain model (Task 1).

Design notes (see docs/decisions.md):
- Plain dataclasses for things that mostly hold data.
- Composition: an Offer HAS-A FareConditions. A Booking stores a copy of the
  fare conditions that applied when it was made.
"""
from dataclasses import dataclass
from datetime import date, datetime, time


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
    fare_type: str = "Standard"     # label from the data, e.g. Basic / Standard / Flex


@dataclass
class Offer:
    offer_id: str
    company: str
    destination: str
    travel_date: date
    departure_time: time
    arrival_date: date              # differs from travel_date for overnight journeys
    arrival_time: time
    price: float
    transfers: int
    fare: FareConditions
    seats_available: int
    rating: float
    emissions_kg: float | None = None   # optional environmental measure (kg CO2 per passenger)

    @property
    def departure_datetime(self) -> datetime:
        return datetime.combine(self.travel_date, self.departure_time)

    @property
    def arrival_datetime(self) -> datetime:
        return datetime.combine(self.arrival_date, self.arrival_time)

    @property
    def duration_minutes(self) -> int:
        """Journey time in minutes. Works for overnight journeys because the
        arrival has its own date (decision D11)."""
        return int((self.arrival_datetime - self.departure_datetime).total_seconds() // 60)


@dataclass
class TravelRequest:
    """What the traveller asks for. Hard constraints vs soft preferences."""
    # --- hard constraints (offers violating these are removed) ---
    destination: str
    date_from: date
    date_to: date
    max_budget: float
    max_transfers: int | None = None          # None = no limit
    require_changeable: bool = False
    min_luggage_kg: int = 0                   # 0 = no requirement
    max_duration_minutes: int | None = None   # None = no limit (duration is then soft only)
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
