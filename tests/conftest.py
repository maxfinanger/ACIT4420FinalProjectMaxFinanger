from datetime import date, time

import pytest

from busbidder.models import FareConditions, Offer


@pytest.fixture
def known_destinations():
    return {"Malaga", "Barcelona"}


@pytest.fixture
def known_companies():
    return {"SolRuta", "NocheVia"}


@pytest.fixture
def offer_factory():
    """Build a valid Offer; override any field with keyword arguments."""
    def make(**changes):
        base = dict(
            offer_id="OF-0001", company="SolRuta", destination="Malaga",
            travel_date=date(2026, 7, 12), departure_time=time(8, 0),
            arrival_date=date(2026, 7, 12), arrival_time=time(14, 30),
            price=32.5, transfers=1, fare=FareConditions(False, False, 10, "Basic"),
            seats_available=12, rating=3.9, emissions_kg=18.2)
        base.update(changes)
        return Offer(**base)
    return make


@pytest.fixture
def good_row():
    """A valid CSV row (all text, as csv.DictReader would give it)."""
    return {
        "offer_id": "OF-0001", "company": "SolRuta", "destination": "Malaga",
        "travel_date": "2026-07-12", "departure_time": "08:00",
        "arrival_date": "2026-07-12", "arrival_time": "14:30", "fare_type": "Basic",
        "price": "32.50", "transfers": "1", "luggage_kg": "10", "changeable": "no",
        "refundable": "no", "seats_available": "12", "rating": "3.9", "emissions_kg": "18.2",
    }


@pytest.fixture(autouse=True)
def _reset_scoring_config():
    """The scoring parameters are module-level state, so every test starts from the defaults."""
    from busbidder.scoring_config import reset_config
    reset_config()
    yield
    reset_config()
