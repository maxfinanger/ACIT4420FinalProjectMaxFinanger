"""Record validation rules (Task 2). TODO: implement."""
import re

# Booking reference format, e.g. BB-20260712-A1B2C3 (adjust to your design)
BOOKING_REF_PATTERN = re.compile(r"^BB-\d{8}-[A-Z0-9]{6}$")


def is_valid_booking_ref(ref: str) -> bool:
    return bool(BOOKING_REF_PATTERN.match(ref))


def validate_offer(offer, known_destinations, known_companies):
    """TODO: raise ValidationError for negative price, unknown destination,
    arrival before departure, rating outside 0-5, no seats, etc."""
    raise NotImplementedError
