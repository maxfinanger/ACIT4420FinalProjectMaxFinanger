"""Load data from files (Task 2): read, convert types, validate, report.

Policy for invalid offer records (decision D7): a bad record is REJECTED, not
corrected. It is logged with its row number, id and reason, and collected in
LoadResult.rejected so the program (and the user) can see what was left out.
Loading continues with the remaining rows. Problems with a whole file (missing,
empty, wrong header, unreadable) raise DataFileError instead.
"""
import csv
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Iterable

from .exceptions import DataFileError, ValidationError
from .models import Company, Destination, FareConditions, Offer
from .validation import (DATE_PATTERN, OFFER_ID_PATTERN, REQUIRED_FIELDS, TIME_PATTERN,
                         check_row_structure, validate_offer)

log = logging.getLogger("busbidder")

_TRUE = {"yes", "true", "1"}
_FALSE = {"no", "false", "0"}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class RejectedRecord:
    row: int            # data row number (1 = first row after the header)
    offer_id: str
    category: str
    message: str


@dataclass
class LoadResult:
    offers: list[Offer] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)
    total_rows: int = 0

    def rejected_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.rejected:
            counts[record.category] = counts.get(record.category, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# File-level reading (errors here raise DataFileError)
# ---------------------------------------------------------------------------
def _fail(message: str) -> None:
    log.error(message)
    raise DataFileError(message)


def _read_csv(path: str, required_columns: Iterable[str]) -> list[dict]:
    p = Path(path)
    if not p.exists():
        _fail(f"File not found: {path}")
    try:
        with p.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                _fail(f"File is empty (no header row): {path}")
            missing = [c for c in required_columns if c not in reader.fieldnames]
            if missing:
                _fail(f"File {path} is missing required columns: {', '.join(missing)}")
            return list(reader)
    except (OSError, UnicodeDecodeError, csv.Error) as err:
        _fail(f"Could not read {path}: {err}")


def load_companies(path: str = "data/companies.csv") -> list[Company]:
    rows = _read_csv(path, ("name", "profile"))
    companies = []
    for n, r in enumerate(rows, start=1):
        if not (r["name"] or "").strip():
            _fail(f"{path}: row {n} has an empty company name")
        companies.append(Company(r["name"].strip(), (r["profile"] or "").strip()))
    log.info("Loaded %d companies from %s", len(companies), path)
    return companies


def load_destinations(path: str = "data/destinations.csv") -> list[Destination]:
    rows = _read_csv(path, ("name",))
    destinations = []
    for n, r in enumerate(rows, start=1):
        if not (r["name"] or "").strip():
            _fail(f"{path}: row {n} has an empty destination name")
        destinations.append(Destination(r["name"].strip()))
    log.info("Loaded %d destinations from %s", len(destinations), path)
    return destinations


def load_profiles(path: str = "config/profiles.json") -> dict:
    p = Path(path)
    if not p.exists():
        _fail(f"File not found: {path}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        _fail(f"Could not read {path}: {err}")
    if not isinstance(data, dict):
        _fail(f"{path} must contain a JSON object of profiles")
    return {k: v for k, v in data.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Row-level conversion (errors here raise ValidationError)
# ---------------------------------------------------------------------------
def _parse_date(text: str, name: str) -> date:
    if not DATE_PATTERN.match(text):
        raise ValidationError("invalid_date", f"{name} must be YYYY-MM-DD, got {text!r}")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValidationError("invalid_date", f"{name} is not a real date: {text!r}") from None


def _parse_time(text: str, name: str) -> time:
    if not TIME_PATTERN.match(text):
        raise ValidationError("invalid_time", f"{name} must be HH:MM (00:00-23:59), got {text!r}")
    return time(int(text[:2]), int(text[3:]))


def _parse_int(text: str, name: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValidationError("invalid_number", f"{name} must be a whole number, got {text!r}") from None


def _parse_float(text: str, name: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise ValidationError("invalid_number", f"{name} must be a number, got {text!r}") from None
    if not math.isfinite(value):
        raise ValidationError("invalid_number", f"{name} must be a finite number, got {text!r}")
    return value


def _parse_bool(text: str, name: str) -> bool:
    lowered = text.lower()
    if lowered in _TRUE:
        return True
    if lowered in _FALSE:
        return False
    raise ValidationError("invalid_boolean", f"{name} must be yes or no, got {text!r}")


def build_offer(row: dict, known_destinations, known_companies) -> Offer:
    """Convert one CSV row into a validated Offer, or raise ValidationError."""
    check_row_structure(row)
    f = {name: (row[name] or "").strip() for name in REQUIRED_FIELDS}

    if not OFFER_ID_PATTERN.match(f["offer_id"]):
        raise ValidationError("bad_offer_id", f"offer_id must look like OF-0001, got {f['offer_id']!r}")

    travel_date = _parse_date(f["travel_date"], "travel_date")
    arrival_date = _parse_date(f["arrival_date"], "arrival_date")
    departure_time = _parse_time(f["departure_time"], "departure_time")
    arrival_time = _parse_time(f["arrival_time"], "arrival_time")
    price = _parse_float(f["price"], "price")
    transfers = _parse_int(f["transfers"], "transfers")
    luggage_kg = _parse_int(f["luggage_kg"], "luggage_kg")
    seats = _parse_int(f["seats_available"], "seats_available")
    rating = _parse_float(f["rating"], "rating")
    changeable = _parse_bool(f["changeable"], "changeable")
    refundable = _parse_bool(f["refundable"], "refundable")

    emissions_text = (row.get("emissions_kg") or "").strip()    # optional column
    emissions = _parse_float(emissions_text, "emissions_kg") if emissions_text else None

    offer = Offer(
        offer_id=f["offer_id"], company=f["company"], destination=f["destination"],
        travel_date=travel_date, departure_time=departure_time,
        arrival_date=arrival_date, arrival_time=arrival_time,
        price=price, transfers=transfers,
        fare=FareConditions(changeable, refundable, luggage_kg, f["fare_type"]),
        seats_available=seats, rating=rating, emissions_kg=emissions,
    )
    validate_offer(offer, known_destinations, known_companies)
    return offer


def _id_for_log(row: dict) -> str:
    value = row.get("offer_id")
    return value.strip() if isinstance(value, str) and value.strip() else "?"


def load_offers(path: str = "data/offers.csv",
                known_destinations: Iterable[str] = (),
                known_companies: Iterable[str] = ()) -> LoadResult:
    """Read offers, reject invalid rows (and log them), return what is left.

    A repeated offer_id is rejected as duplicate_id: the first valid row wins.
    """
    destinations, companies = set(known_destinations), set(known_companies)
    rows = _read_csv(path, REQUIRED_FIELDS)
    result = LoadResult(total_rows=len(rows))
    seen_ids: set[str] = set()

    for n, row in enumerate(rows, start=1):
        try:
            offer = build_offer(row, destinations, companies)
            if offer.offer_id in seen_ids:
                raise ValidationError("duplicate_id", f"offer_id {offer.offer_id} already loaded")
        except ValidationError as err:
            record = RejectedRecord(n, _id_for_log(row), err.category, err.message)
            result.rejected.append(record)
            log.warning("Rejected row %d (%s) in %s: %s - %s",
                        n, record.offer_id, path, err.category, err.message)
            continue
        seen_ids.add(offer.offer_id)
        result.offers.append(offer)

    if not rows:
        log.warning("No data rows in %s", path)
    log.info("Loaded offers from %s: %d accepted, %d rejected (of %d rows)",
             path, len(result.offers), len(result.rejected), result.total_rows)
    return result
