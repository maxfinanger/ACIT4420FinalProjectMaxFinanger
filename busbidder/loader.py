"""Load data from files (Task 2). Convert types and validate records."""
import csv
import json
import logging
from pathlib import Path

from .exceptions import DataFileError
from .models import Company, Destination, Offer

log = logging.getLogger("busbidder")


def _read_csv(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        log.error("Missing file: %s", path)
        raise DataFileError(f"File not found: {path}")
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_companies(path: str = "data/companies.csv") -> list[Company]:
    rows = _read_csv(path)
    log.info("Loaded %d companies", len(rows))
    return [Company(r["name"], r["profile"]) for r in rows]


def load_destinations(path: str = "data/destinations.csv") -> list[Destination]:
    rows = _read_csv(path)
    log.info("Loaded %d destinations", len(rows))
    return [Destination(r["name"]) for r in rows]


def load_profiles(path: str = "config/profiles.json") -> dict:
    p = Path(path)
    if not p.exists():
        raise DataFileError(f"File not found: {path}")
    with p.open(encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def load_offers(path: str = "data/offers.csv") -> list[Offer]:
    """TODO (Task 2): parse each row into an Offer, validate it, and
    reject / correct / set aside invalid rows. Log every decision."""
    raise NotImplementedError("Task 2: implement offer loading and validation")
