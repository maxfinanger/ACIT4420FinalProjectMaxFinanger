"""Business-rule validation on typed offers: normal, invalid and boundary cases."""
from datetime import date, time

import pytest

from busbidder.exceptions import ValidationError
from busbidder.models import FareConditions
from busbidder.validation import (MAX_DURATION_MINUTES, OFFER_ID_PATTERN, check_row_structure,
                                  is_valid_booking_ref, validate_offer)


def category_of(offer, dests, comps):
    with pytest.raises(ValidationError) as info:
        validate_offer(offer, dests, comps)
    return info.value.category


def test_valid_offer_passes(offer_factory, known_destinations, known_companies):
    validate_offer(offer_factory(), known_destinations, known_companies)


@pytest.mark.parametrize("changes, expected", [
    ({"price": -5.0}, "negative_price"),
    ({"price": 0.0}, "negative_price"),
    ({"transfers": -1}, "negative_transfers"),
    ({"rating": -0.1}, "rating_out_of_range"),
    ({"rating": 5.1}, "rating_out_of_range"),
    ({"seats_available": 0}, "no_seats"),
    ({"seats_available": -3}, "no_seats"),
    ({"destination": "Atlantis"}, "unknown_destination"),
    ({"destination": "malaga"}, "unknown_destination"),       # case-sensitive
    ({"company": "GhostBus"}, "unknown_company"),
    ({"arrival_time": time(6, 0)}, "arrival_before_departure"),
    ({"arrival_time": time(8, 0)}, "arrival_before_departure"),  # zero duration
    ({"arrival_date": date(2026, 7, 20)}, "impossible_duration"),
    ({"fare": FareConditions(False, False, -1, "Basic")}, "invalid_number"),
])
def test_invalid_offers_get_the_right_category(offer_factory, known_destinations,
                                                known_companies, changes, expected):
    assert category_of(offer_factory(**changes), known_destinations, known_companies) == expected


# ---- boundary values that must be ACCEPTED ----
@pytest.mark.parametrize("changes", [
    {"price": 0.01},
    {"transfers": 0},
    {"rating": 0.0},
    {"rating": 5.0},
    {"seats_available": 1},
    {"arrival_time": time(8, 1)},                              # shortest possible journey
    {"departure_time": time(23, 55), "arrival_date": date(2026, 7, 13),
     "arrival_time": time(7, 10)},                             # overnight
    {"emissions_kg": None},                                    # optional field
])
def test_boundary_values_are_accepted(offer_factory, known_destinations, known_companies, changes):
    validate_offer(offer_factory(**changes), known_destinations, known_companies)


def test_duration_exactly_24_hours_is_accepted_and_one_minute_more_is_not(
        offer_factory, known_destinations, known_companies):
    ok = offer_factory(departure_time=time(8, 0), arrival_date=date(2026, 7, 13), arrival_time=time(8, 0))
    assert ok.duration_minutes == MAX_DURATION_MINUTES
    validate_offer(ok, known_destinations, known_companies)
    too_long = offer_factory(departure_time=time(8, 0), arrival_date=date(2026, 7, 13), arrival_time=time(8, 1))
    assert category_of(too_long, known_destinations, known_companies) == "impossible_duration"


def test_validation_error_exposes_category_and_message():
    err = ValidationError("negative_price", "price must be above 0")
    assert err.category == "negative_price"
    assert str(err) == "negative_price: price must be above 0"


# ---- row structure ----
def test_good_row_structure_passes(good_row):
    check_row_structure(good_row)


def test_empty_required_field_is_missing_field(good_row):
    good_row["price"] = "  "
    with pytest.raises(ValidationError) as info:
        check_row_structure(good_row)
    assert info.value.category == "missing_field"


def test_none_value_is_malformed_row(good_row):
    good_row["rating"] = None          # DictReader: row was too short
    with pytest.raises(ValidationError) as info:
        check_row_structure(good_row)
    assert info.value.category == "malformed_row"


def test_extra_columns_is_malformed_row(good_row):
    good_row[None] = ["extra"]         # DictReader: row was too long
    with pytest.raises(ValidationError) as info:
        check_row_structure(good_row)
    assert info.value.category == "malformed_row"


# ---- regular expressions ----
@pytest.mark.parametrize("text, ok", [
    ("OF-0001", True), ("OF-9999", True), ("OF-001", False), ("OF-00001", False),
    ("of-0001", False), ("BUS-12", False), (" OF-0001", False), ("OF-0001\n", False),
])
def test_offer_id_pattern(text, ok):
    assert bool(OFFER_ID_PATTERN.match(text)) is ok


@pytest.mark.parametrize("text, ok", [
    ("BB-20260712-A1B2C3", True), ("BB-20260712-a1b2c3", False),
    ("BB-2026712-A1B2C3", False), ("BB-20260712-A1B2C", False), ("BOOKING123", False),
])
def test_booking_reference_pattern(text, ok):
    assert is_valid_booking_ref(text) is ok
