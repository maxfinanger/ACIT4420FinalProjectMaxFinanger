"""Domain model (Task 1).

Design notes (see docs/decisions.md):
- Plain dataclasses for things that mostly hold data.
- Composition: an Offer HAS-A FareConditions. A Booking stores a copy of the
  fare conditions that applied when it was made.
"""
from dataclasses import dataclass, field
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
    # Seats in the data file. `seats_available` is what is left after bookings (D9, D19):
    # seats_available == capacity - seats sold. Defaults to the value in the file.
    capacity: int | None = None

    def __post_init__(self):
        if self.capacity is None:
            self.capacity = self.seats_available

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
    criterion_scores: dict[str, float]   # name -> 0-100, higher is always better
    total_score: float                   # sum of weight * score, so also 0-100
    rank: int = 0                        # 1 = best
    contributions: dict[str, float] = field(default_factory=dict)   # name -> weight * score
    tie_broken: bool = False             # same total (to 2 decimals) as a neighbour


@dataclass
class Booking:
    """A saved booking. It keeps its own copy of the journey and the fare conditions that
    applied when it was made, so later changes to the offers cannot change it."""
    reference: str
    offer_id: str
    company: str
    destination: str
    travel_date: date
    departure_time: time
    arrival_date: date
    arrival_time: time
    price_paid: float
    traveller_name: str
    fare: FareConditions
    payment_status: str = "SIMULATED-PAID"      # no real payment is ever taken
    booked_at: str = ""                         # ISO timestamp, set by the booking service

    @property
    def duration_minutes(self) -> int:
        start = datetime.combine(self.travel_date, self.departure_time)
        end = datetime.combine(self.arrival_date, self.arrival_time)
        return int((end - start).total_seconds() // 60)
