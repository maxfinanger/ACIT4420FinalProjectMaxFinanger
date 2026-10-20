"""Simulated booking (Section 6).

Decisions D9, D19, D20 (docs/decisions.md, docs/booking.md):
  - data/offers.csv is never modified. Seats sold are stored in data/bookings.json, which is
    the single source of truth: seats left = capacity (from the file) - bookings in the store.
  - The store is re-read before every booking, so a stale in-memory offer cannot oversell.
  - The store is written atomically (temp file, then rename), and never overwritten when it
    cannot be read.
  - Payment is simulated. The only personal data is a name, and names cannot contain digits.
"""
import json
import logging
import math
import os
import random
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .exceptions import (BookingError, DataFileError, DuplicateBookingError, SoldOutError,
                         ValidationError)
from .paths import place_output
from .loader import parse_date, parse_time
from .models import Booking, FareConditions, Offer, RankedOffer
from .validation import OFFER_ID_PATTERN, clean_traveller_name, is_valid_booking_ref

log = logging.getLogger("busbidder")

STORE_VERSION = 1
PAYMENT_STATUS = "SIMULATED-PAID"
# No 0/O/1/I so a reference can be read out loud without mistakes. Matches the pattern in validation.py.
REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
REFERENCE_SUFFIX_LENGTH = 6
MAX_REFERENCE_ATTEMPTS = 100


# ---------------------------------------------------------------------------
# Choosing an offer from a ranking
# ---------------------------------------------------------------------------
def select_from_ranking(ranked: list[RankedOffer], target: str) -> RankedOffer:
    """`target` is a rank number ("3") or an offer id ("OF-1025") from the ranking shown."""
    if not ranked:
        raise ValidationError("invalid_selection", "there are no offers to choose from")
    text = str(target).strip()
    if text.isdigit():
        rank = int(text)
        if not 1 <= rank <= len(ranked):
            raise ValidationError("invalid_selection",
                                  f"rank {rank} is not in the ranking (1-{len(ranked)})")
        return ranked[rank - 1]
    if OFFER_ID_PATTERN.match(text.upper()):
        for r in ranked:
            if r.offer.offer_id == text.upper():
                return r
        raise ValidationError("invalid_selection", f"{text.upper()} is not among the "
                              f"{len(ranked)} acceptable offers for this request")
    raise ValidationError("invalid_selection",
                          f"'{text}' is not a rank number (e.g. 1) or an offer id (e.g. OF-1025)")


# ---------------------------------------------------------------------------
# Saving and reading bookings
# ---------------------------------------------------------------------------
def booking_to_dict(b: Booking) -> dict:
    return {
        "reference": b.reference, "offer_id": b.offer_id, "company": b.company,
        "destination": b.destination, "travel_date": b.travel_date.isoformat(),
        "departure_time": f"{b.departure_time:%H:%M}",
        "arrival_date": b.arrival_date.isoformat(), "arrival_time": f"{b.arrival_time:%H:%M}",
        "price_paid": b.price_paid, "traveller_name": b.traveller_name,
        "fare": {"fare_type": b.fare.fare_type, "changeable": b.fare.changeable,
                 "refundable": b.fare.refundable, "luggage_kg": b.fare.luggage_kg},
        "payment_status": b.payment_status, "booked_at": b.booked_at,
    }


def _text(d: dict, key: str) -> str:
    value = d.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' is missing or not text")
    return value


def booking_from_dict(d) -> Booking:
    """Strict conversion. Raises ValueError (message says what is wrong)."""
    if not isinstance(d, dict):
        raise ValueError("not an object")
    try:
        fare = d.get("fare")
        if not isinstance(fare, dict):
            raise ValueError("'fare' is missing")
        for key in ("changeable", "refundable"):
            if not isinstance(fare.get(key), bool):
                raise ValueError(f"fare.{key} must be true or false")
        luggage = fare.get("luggage_kg")
        if isinstance(luggage, bool) or not isinstance(luggage, int) or luggage < 0:
            raise ValueError("fare.luggage_kg must be a whole number, 0 or more")
        price = d.get("price_paid")
        if isinstance(price, bool) or not isinstance(price, (int, float)) \
                or not math.isfinite(price) or price <= 0:
            raise ValueError("'price_paid' must be a number above 0")
        reference = _text(d, "reference")
        if not is_valid_booking_ref(reference):
            raise ValueError(f"invalid reference '{reference}'")
        offer_id = _text(d, "offer_id")
        if not OFFER_ID_PATTERN.match(offer_id):
            raise ValueError(f"invalid offer id '{offer_id}'")
        return Booking(
            reference=reference, offer_id=offer_id, company=_text(d, "company"),
            destination=_text(d, "destination"),
            travel_date=parse_date(_text(d, "travel_date"), "travel_date"),
            departure_time=parse_time(_text(d, "departure_time"), "departure_time"),
            arrival_date=parse_date(_text(d, "arrival_date"), "arrival_date"),
            arrival_time=parse_time(_text(d, "arrival_time"), "arrival_time"),
            price_paid=float(price), traveller_name=clean_traveller_name(d.get("traveller_name")),
            fare=FareConditions(fare["changeable"], fare["refundable"], luggage,
                                _text(fare, "fare_type")),
            payment_status=_text(d, "payment_status"),
            booked_at=d.get("booked_at") if isinstance(d.get("booked_at"), str) else "")
    except ValidationError as err:
        raise ValueError(err.message) from None


class BookingService:
    """Owns the bookings file. `rng` and `clock` can be replaced in tests (and by BUSBIDDER_SEED)
    so that references and timestamps are reproducible."""

    def __init__(self, store_path: str = "data/bookings.json",
                 rng: random.Random | None = None,
                 clock: Callable[[], datetime] | None = None):
        self.store_path = place_output(store_path)
        self._rng = rng if rng is not None else random.SystemRandom()
        self._clock = clock if clock is not None else (lambda: datetime.now().replace(microsecond=0))

    # ---- reading ----------------------------------------------------------
    def _fail(self, message: str):
        log.error(message)
        raise DataFileError(message)

    def load(self) -> list[Booking]:
        """All saved bookings. A missing file means no bookings. A file that cannot be read or
        is inconsistent raises DataFileError and is never overwritten."""
        if not self.store_path.exists():
            return []
        try:
            data = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
            self._fail(f"Could not read {self.store_path}: {err}")
        if not isinstance(data, dict) or data.get("version") != STORE_VERSION \
                or not isinstance(data.get("bookings"), list):
            self._fail(f"{self.store_path} is not a version {STORE_VERSION} bookings file")
        bookings, references = [], set()
        for n, raw in enumerate(data["bookings"], start=1):
            try:
                booking = booking_from_dict(raw)
            except ValueError as err:
                self._fail(f"{self.store_path}: booking #{n}: {err}")
            if booking.reference in references:
                self._fail(f"{self.store_path}: booking #{n}: reference {booking.reference} is used twice")
            references.add(booking.reference)
            bookings.append(booking)
        return bookings

    def sold(self, offer_id: str) -> int:
        return sum(b.offer_id == offer_id for b in self.load())

    def seats_left(self, offer: Offer) -> int:
        """Capacity in the offers file minus seats sold in the bookings file."""
        return max(0, offer.capacity - self.sold(offer.offer_id))

    def apply_to_offers(self, offers: list[Offer]) -> None:
        """Bring the in-memory offers in line with the saved bookings (call once at start-up)."""
        by_id = {o.offer_id: o for o in offers}
        sold: dict[str, int] = {}
        for b in self.load():
            sold[b.offer_id] = sold.get(b.offer_id, 0) + 1
        for offer_id, count in sold.items():
            offer = by_id.get(offer_id)
            if offer is None:
                log.warning("Saved bookings refer to %s, which is not in the offers file (%d booking(s) ignored)",
                            offer_id, count)
                continue
            if count > offer.capacity:
                log.warning("%s has %d bookings but only %d seats: seats left set to 0",
                            offer_id, count, offer.capacity)
            offer.seats_available = max(0, offer.capacity - count)
        log.info("Applied %d saved booking(s) to the offers", sum(sold.values()))

    # ---- writing ----------------------------------------------------------
    def _write(self, bookings: list[Booking]) -> None:
        payload = {"version": STORE_VERSION, "bookings": [booking_to_dict(b) for b in bookings]}
        directory = self.store_path.parent
        tmp_name = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, suffix=".tmp",
                                             delete=False) as tmp:
                tmp_name = tmp.name
                json.dump(payload, tmp, indent=2, ensure_ascii=False)
                tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            os.replace(tmp_name, self.store_path)
        except OSError as err:
            if tmp_name and os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise BookingError(f"could not save the booking: {err}") from err

    def _new_reference(self, offer: Offer, used: set[str]) -> str:
        """BB-<travel date>-<6 characters>, different from every saved reference."""
        for _ in range(MAX_REFERENCE_ATTEMPTS):
            suffix = "".join(self._rng.choice(REFERENCE_ALPHABET) for _ in range(REFERENCE_SUFFIX_LENGTH))
            reference = f"BB-{offer.travel_date:%Y%m%d}-{suffix}"
            if reference not in used:
                return reference
        raise BookingError("could not create a unique booking reference")

    def book(self, offer: Offer, traveller_name: str) -> Booking:
        """Book one seat. Order: check the name, re-read the store, check seats and duplicates,
        save, and only then reduce the seat count in memory."""
        name = clean_traveller_name(traveller_name)          # ValidationError if not acceptable
        saved = self.load()                                   # the file is the truth, not the offer object
        sold = sum(b.offer_id == offer.offer_id for b in saved)
        if offer.capacity - sold < 1:
            offer.seats_available = 0
            raise SoldOutError(f"{offer.offer_id} is sold out")
        if any(b.offer_id == offer.offer_id and b.traveller_name.casefold() == name.casefold()
               for b in saved):
            raise DuplicateBookingError(f"{name} already has a booking on {offer.offer_id}")

        booking = Booking(
            reference=self._new_reference(offer, {b.reference for b in saved}),
            offer_id=offer.offer_id, company=offer.company, destination=offer.destination,
            travel_date=offer.travel_date, departure_time=offer.departure_time,
            arrival_date=offer.arrival_date, arrival_time=offer.arrival_time,
            price_paid=offer.price, traveller_name=name, fare=offer.fare,
            payment_status=PAYMENT_STATUS, booked_at=self._clock().isoformat(timespec="seconds"))
        self._write(saved + [booking])
        offer.seats_available = offer.capacity - (sold + 1)
        log.info("Booking %s: %s on %s (%s), EUR %.2f, %d seat(s) left",
                 booking.reference, name, offer.offer_id, offer.company, offer.price,
                 offer.seats_available)
        return booking


# ---------------------------------------------------------------------------
# Text for the user
# ---------------------------------------------------------------------------
def format_confirmation(booking: Booking, seats_left: int, rank: int | None = None,
                        score: float | None = None) -> str:
    f = booking.fare
    h, m = divmod(booking.duration_minutes, 60)
    lines = [
        "BOOKING CONFIRMED",
        f"  Reference : {booking.reference}",
        f"  Traveller : {booking.traveller_name}",
        f"  Journey   : Madrid to {booking.destination} with {booking.company}",
        f"  Departs   : {booking.travel_date:%a %d %b %Y} {booking.departure_time:%H:%M}",
        f"  Arrives   : {booking.arrival_date:%a %d %b %Y} {booking.arrival_time:%H:%M} ({h}h{m:02d})",
        f"  Fare      : {f.fare_type} (changeable: {'yes' if f.changeable else 'no'}, "
        f"refundable: {'yes' if f.refundable else 'no'}, luggage: {f.luggage_kg} kg)",
        f"  Price     : EUR {booking.price_paid:.2f}",
        f"  Payment   : {booking.payment_status} (simulated, no real payment was taken)",
        f"  Offer     : {booking.offer_id}" + (f" (rank {rank}, score {score:.1f})" if rank else ""),
        f"  Seats left on this offer: {seats_left}",
    ]
    return "\n".join(lines)


def format_booking_list(bookings: list[Booking]) -> str:
    if not bookings:
        return "No bookings saved yet."
    lines = [f"{'Reference':<20} {'Traveller':<22} {'Offer':<8} {'Company':<15} {'Departs':<17} {'EUR':>6}"]
    for b in bookings:
        lines.append(f"{b.reference:<20} {b.traveller_name[:22]:<22} {b.offer_id:<8} {b.company:<15} "
                     f"{b.travel_date:%d %b} {b.departure_time:%H:%M}     {b.price_paid:>6.2f}")
    return "\n".join(lines)
