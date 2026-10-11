"""Domain model (Task 1). Plain dataclasses for now; extend as the design grows."""
from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True)
class Company:
    name: str
    profile: str


@dataclass(frozen=True)
class Destination:
    name: str


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
    luggage_kg: int
    changeable: bool
    refundable: bool
    seats_available: int
    rating: float

    @property
    def duration_minutes(self) -> int:
        # TODO: handle overnight journeys (arrival on the next day).
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
class Booking:
    reference: str
    offer: Offer
    traveller_name: str
    payment_status: str = "SIMULATED-PAID"
