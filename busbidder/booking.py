"""Simulated booking (Section 6 in spec).

BookingService is a class because it owns state: where bookings are stored and
which seats have already been sold. Decision D9: data/offers.csv is never
modified; remaining seats = seats in the file minus seats booked in bookings.json.
"""
from .models import Booking, Offer


class BookingService:
    def __init__(self, store_path: str = "data/bookings.json"):
        self.store_path = store_path

    def seats_left(self, offer: Offer) -> int:
        """TODO (Phase 7): offer.seats_available minus bookings for this offer."""
        raise NotImplementedError("Phase 7")

    def book(self, offer: Offer, traveller_name: str) -> Booking:
        """TODO (Phase 7): check seats, make reference, save, return Booking."""
        raise NotImplementedError("Phase 7")

    def _new_reference(self, offer: Offer) -> str:
        """TODO (Phase 7): must match BOOKING_REF_PATTERN in validation.py."""
        raise NotImplementedError("Phase 7")
