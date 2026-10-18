"""Record validation rules (Task 2).

Checking is split in two steps (decision D13):
  1. loader.build_offer converts text to types and reports FORMAT errors
     (bad id, bad date/time, not a number, not yes/no).
  2. validate_offer in this module checks the BUSINESS RULES on a typed Offer
     (ranges, known company/destination, arrival after departure).

Every failure raises ValidationError with a `category`. Records that fail are
rejected, never corrected (decision D7).

Regular expressions are only used for fixed-format identifiers and timestamps
(offer id, booking reference, date, time). Numbers are checked by parsing them
and then comparing values, which a regex cannot do (decision D13).
"""
import re

from .exceptions import ValidationError
from .models import Offer, TravelRequest

# ---- fixed-format patterns -------------------------------------------------
# \A ... \Z (not ^ ... $) because $ also matches just before a trailing newline,
# which let 'OF-0001\n' through in an early test (found by test_offer_id_pattern).
BOOKING_REF_PATTERN = re.compile(r"\ABB-\d{8}-[A-Z0-9]{6}\Z")   # e.g. BB-20260712-A1B2C3
OFFER_ID_PATTERN = re.compile(r"\AOF-\d{4}\Z")                  # e.g. OF-0042
DATE_PATTERN = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")             # ISO date
TIME_PATTERN = re.compile(r"\A([01]\d|2[0-3]):[0-5]\d\Z")       # 24-hour HH:MM
# Names: letters (any language), optional full stop, separated by space, hyphen or apostrophe.
# No digits on purpose: the program must never store a card number typed in by mistake (D19).
TRAVELLER_NAME_PATTERN = re.compile(r"\A[^\W\d_]+\.?(?:[ '\-][^\W\d_]+\.?)*\Z")
MAX_NAME_LENGTH = 60

# ---- limits ---------------------------------------------------------------
RATING_MIN, RATING_MAX = 0.0, 5.0          # inclusive rating scale
MAX_DURATION_MINUTES = 24 * 60             # no bus journey in Spain takes longer

# Fields that must be present and non-empty in every row. (emissions_kg is optional.)
REQUIRED_FIELDS = (
    "offer_id", "company", "destination", "travel_date", "departure_time",
    "arrival_date", "arrival_time", "fare_type", "price", "transfers",
    "luggage_kg", "changeable", "refundable", "seats_available", "rating",
)


def is_valid_booking_ref(ref: str) -> bool:
    return bool(BOOKING_REF_PATTERN.match(ref))


def check_row_structure(row: dict) -> None:
    """Raise ValidationError if the row has the wrong number of columns
    (malformed_row) or an empty required field (missing_field)."""
    # csv.DictReader puts missing columns as None, and extra columns under the key None
    if None in row or any(value is None for value in row.values()):
        raise ValidationError("malformed_row", "row has missing or extra columns")
    for name in REQUIRED_FIELDS:
        value = row.get(name)
        if value is None or not value.strip():
            raise ValidationError("missing_field", f"required field '{name}' is empty")


def validate_offer(offer: Offer, known_destinations, known_companies) -> None:
    """Check business rules on an already typed Offer. Raises ValidationError."""
    if offer.price <= 0:
        raise ValidationError("negative_price",
                              f"price must be above 0, got {offer.price}")
    if offer.transfers < 0:
        raise ValidationError("negative_transfers",
                              f"transfers must not be negative, got {offer.transfers}")
    if offer.fare.luggage_kg < 0:
        raise ValidationError("invalid_number",
                              f"luggage_kg must not be negative, got {offer.fare.luggage_kg}")
    if not RATING_MIN <= offer.rating <= RATING_MAX:
        raise ValidationError("rating_out_of_range",
                              f"rating must be {RATING_MIN:g}-{RATING_MAX:g}, got {offer.rating}")
    if offer.seats_available <= 0:
        raise ValidationError("no_seats",
                              f"seats_available must be at least 1, got {offer.seats_available}")
    if offer.destination not in known_destinations:
        raise ValidationError("unknown_destination", f"unknown destination '{offer.destination}'")
    if offer.company not in known_companies:
        raise ValidationError("unknown_company", f"unknown company '{offer.company}'")
    if offer.arrival_datetime <= offer.departure_datetime:
        raise ValidationError("arrival_before_departure",
                              f"arrival {offer.arrival_datetime:%Y-%m-%d %H:%M} is not after "
                              f"departure {offer.departure_datetime:%Y-%m-%d %H:%M}")
    if offer.duration_minutes > MAX_DURATION_MINUTES:
        raise ValidationError("impossible_duration",
                              f"journey takes {offer.duration_minutes} min, "
                              f"more than the maximum {MAX_DURATION_MINUTES}")


def validate_request(request: TravelRequest, known_destinations=None) -> None:
    """Check the traveller's request before filtering (garbage in, clear error out).
    If `known_destinations` is given, the destination must be one of them."""
    if request.date_from > request.date_to:
        raise ValidationError("invalid_window",
                              f"travel window starts {request.date_from} after it ends {request.date_to}")
    if request.max_budget <= 0:
        raise ValidationError("invalid_budget", f"budget must be above 0, got {request.max_budget}")
    if request.max_transfers is not None and request.max_transfers < 0:
        raise ValidationError("invalid_transfers",
                              f"maximum transfers must be 0 or more, got {request.max_transfers}")
    if request.max_duration_minutes is not None and request.max_duration_minutes <= 0:
        raise ValidationError("invalid_duration_limit",
                              f"maximum duration must be above 0, got {request.max_duration_minutes}")
    if request.min_luggage_kg < 0:
        raise ValidationError("invalid_luggage", f"luggage must be 0 or more, got {request.min_luggage_kg}")
    if known_destinations is not None and request.destination not in known_destinations:
        raise ValidationError("unknown_destination", f"unknown destination '{request.destination}'")


def clean_traveller_name(name) -> str:
    """Return the name with tidy spaces, or raise ValidationError("invalid_name")."""
    if not isinstance(name, str):
        raise ValidationError("invalid_name", "name must be text")
    # phone keyboards type the curly apostrophe (O’Neil); store the plain one so the same name always matches
    cleaned = " ".join(name.replace("\u2019", "'").replace("\u2018", "'").split())
    if not cleaned:
        raise ValidationError("invalid_name", "name must not be empty")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValidationError("invalid_name", f"name must be at most {MAX_NAME_LENGTH} characters")
    if not TRAVELLER_NAME_PATTERN.match(cleaned):
        raise ValidationError("invalid_name",
                              "name may only contain letters, spaces, hyphens, apostrophes and "
                              "full stops (no digits: no payment data is collected)")
    return cleaned
