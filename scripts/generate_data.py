"""Generate the fictional BusBidder dataset (Phase 2).

    python scripts/generate_data.py

Writes (all reproducible, fixed seed):
    data/offers.csv                  valid offers for 5 companies x 15 destinations
    data/offers_invalid.csv          deliberately broken rows for testing validation
    data/offers_invalid_expected.json  what each invalid row is supposed to trigger

How the companies differ is defined in COMPANIES below (decision D10). All
numbers are invented, they are NOT real prices or timetables.
"""
import csv
import io
import json
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

SEED = 42
START_DATE = date(2026, 7, 11)       # Saturday
DAYS = 5                              # 11-15 July (the spec example uses 12-14 July)
OPERATING_PROBABILITY = 0.90          # a scheduled departure is skipped on ~10% of days

HEADER = ["offer_id", "company", "destination", "travel_date", "departure_time",
          "arrival_date", "arrival_time", "fare_type", "price", "transfers",
          "luggage_kg", "changeable", "refundable", "seats_available", "rating",
          "emissions_kg"]

# Road distance from Madrid in km (approximate)
DISTANCE_KM = {
    "Barcelona": 620, "Valencia": 355, "Seville": 530, "Malaga": 530, "Granada": 430,
    "Cordoba": 400, "Bilbao": 400, "San Sebastian": 470, "Zaragoza": 320,
    "Alicante": 420, "Murcia": 400, "Salamanca": 210, "Toledo": 70,
    "Santiago de Compostela": 600, "Cadiz": 650,
}
DESTINATIONS = list(DISTANCE_KM)
COASTAL = {"Barcelona", "Valencia", "Malaga", "Alicante", "Cadiz", "San Sebastian",
           "Bilbao", "Santiago de Compostela"}
MAJOR = {"Barcelona", "Valencia", "Seville", "Malaga", "Bilbao", "Zaragoza"}

BASE_FEE_EUR = 5.0
EUR_PER_KM = 0.055
STOP_TIME_MIN = 15                    # fixed boarding / rest time
TRANSFER_TIME_MIN = 35                # extra time per transfer
WEEKEND_UPLIFT = 1.08                 # Fri-Sun demand
CO2_KG_PER_KM = 0.030                 # per passenger


@dataclass(frozen=True)
class Fare:
    name: str
    price_mult: float
    changeable: bool
    refundable: bool
    luggage_kg: int


@dataclass(frozen=True)
class CompanyProfile:
    price_mult: float
    speed_kmh: float
    departure_pool: tuple             # possible departure times for this company
    departures_per_day: Callable      # destination -> how many scheduled departures
    transfers: Callable               # (destination, rng) -> number of transfers
    fares: tuple
    rating_mean: float
    emissions_mult: float


def _solruta_transfers(dest, rng):
    d = DISTANCE_KM[dest]
    if d > 400:
        return rng.choices([0, 1, 2], weights=[35, 50, 15])[0]
    return rng.choices([0, 1], weights=[75, 25])[0]


def _camino_transfers(dest, rng):
    return 0 if dest in MAJOR else 1


def _costalink_transfers(dest, rng):
    return 0 if dest in COASTAL else rng.choices([1, 2], weights=[70, 30])[0]


def _verde_transfers(dest, rng):
    return rng.choices([0, 1], weights=[70, 30])[0] if DISTANCE_KM[dest] > 500 else 0


def _noche_transfers(dest, rng):
    return rng.choices([0, 1], weights=[75, 25])[0]


COMPANIES = {
    # Low-cost daytime: cheapest, slowest, most transfers, strict Basic fares
    "SolRuta": CompanyProfile(
        0.80, 65, ("07:00", "09:30", "12:00", "15:30"), lambda d: 2, _solruta_transfers,
        (Fare("Basic", 1.00, False, False, 10), Fare("Standard", 1.18, True, False, 20)),
        3.8, 1.15),
    # Fast direct connections between major cities: expensive, quick, flexible
    "Camino Express": CompanyProfile(
        1.20, 85, ("06:30", "08:30", "11:00", "14:00", "17:00"),
        lambda d: 3 if d in MAJOR else 1, _camino_transfers,
        (Fare("Standard", 1.00, True, False, 20), Fare("Flex", 1.30, True, True, 25)),
        4.4, 1.00),
    # Coastal coverage: many departures to the coast, fewer and slower inland
    "CostaLink": CompanyProfile(
        0.95, 72, ("07:45", "10:15", "13:30", "16:45"),
        lambda d: 3 if d in COASTAL else 1, _costalink_transfers,
        (Fare("Basic", 0.95, False, False, 15), Fare("Standard", 1.12, True, False, 20),
         Fare("Flex", 1.35, True, True, 25)),
        4.1, 1.00),
    # Environment-focused: modern vehicles, lowest emissions, slightly pricier
    "VerdeBus": CompanyProfile(
        1.10, 75, ("08:00", "12:30", "16:00"), lambda d: 2, _verde_transfers,
        (Fare("Standard", 1.00, True, False, 20), Fare("Flex", 1.25, True, True, 25)),
        4.3, 0.70),
    # Overnight / late evening: departures 21:00-00:45, arrives next morning
    "NocheVia": CompanyProfile(
        0.90, 78, ("21:00", "22:30", "23:55", "00:45"), lambda d: 2, _noche_transfers,
        (Fare("Basic", 0.90, False, False, 10), Fare("Standard", 1.15, True, False, 20)),
        3.6, 1.05),
}


def _yn(flag: bool) -> str:
    return "yes" if flag else "no"


def generate_offers(seed: int = SEED) -> list:
    """Return the valid offers as a list of dicts (same order every time)."""
    rng = random.Random(seed)
    rows = []
    for company, prof in COMPANIES.items():
        for dest in DESTINATIONS:
            dist = DISTANCE_KM[dest]
            times = sorted(rng.sample(prof.departure_pool, prof.departures_per_day(dest)))
            rating = min(5.0, max(1.0, round(rng.gauss(prof.rating_mean, 0.25), 1)))
            for day in range(DAYS):
                travel_date = START_DATE + timedelta(days=day)
                weekend = travel_date.weekday() >= 4
                for t in times:
                    if rng.random() > OPERATING_PROBABILITY:
                        continue
                    transfers = prof.transfers(dest, rng)
                    minutes = (dist / prof.speed_kmh * 60 * rng.uniform(0.95, 1.05)
                               + STOP_TIME_MIN + TRANSFER_TIME_MIN * transfers)
                    minutes = int(round(minutes / 5) * 5)
                    dep = datetime.combine(travel_date, datetime.strptime(t, "%H:%M").time())
                    arr = dep + timedelta(minutes=minutes)
                    emissions = round(dist * CO2_KG_PER_KM * prof.emissions_mult
                                      * rng.uniform(0.95, 1.05), 1)
                    for fare in prof.fares:
                        price = ((BASE_FEE_EUR + EUR_PER_KM * dist) * prof.price_mult
                                 * fare.price_mult * (1 - 0.03 * transfers)
                                 * (WEEKEND_UPLIFT if weekend else 1.0)
                                 * rng.uniform(0.95, 1.05))
                        seats = rng.randint(1, 4) if rng.random() < 0.12 else rng.randint(5, 50)
                        rows.append({
                            "company": company, "destination": dest,
                            "travel_date": travel_date.isoformat(), "departure_time": t,
                            "arrival_date": arr.date().isoformat(),
                            "arrival_time": arr.strftime("%H:%M"),
                            "fare_type": fare.name,
                            "price": f"{round(price * 2) / 2:.2f}",
                            "transfers": transfers, "luggage_kg": fare.luggage_kg,
                            "changeable": _yn(fare.changeable),
                            "refundable": _yn(fare.refundable),
                            "seats_available": seats, "rating": f"{rating:.1f}",
                            "emissions_kg": f"{emissions:.1f}",
                        })
    rows.sort(key=lambda r: (r["travel_date"], r["destination"], r["departure_time"],
                             r["company"], r["fare_type"]))
    for i, r in enumerate(rows, start=1):
        r["offer_id"] = f"OF-{i:04d}"
    return rows


def offers_to_csv_text(rows: list) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=HEADER, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Deliberately invalid rows (for the validation tests in Phase 3)
# ---------------------------------------------------------------------------
_GOOD = {
    "offer_id": "OF-9001", "company": "SolRuta", "destination": "Malaga",
    "travel_date": "2026-07-12", "departure_time": "08:00", "arrival_date": "2026-07-12",
    "arrival_time": "14:30", "fare_type": "Basic", "price": "32.50", "transfers": "1",
    "luggage_kg": "10", "changeable": "no", "refundable": "no", "seats_available": "12",
    "rating": "3.9", "emissions_kg": "18.2",
}


def _variant(offer_id, expected, **changes):
    row = dict(_GOOD, offer_id=offer_id)
    row.update(changes)
    return row, expected


def invalid_cases() -> list:
    """(row, expected_category). A row may also be a raw string for malformed lines."""
    return [
        _variant("OF-9001", "valid"),
        _variant("OF-9002", "negative_price", price="-5.00"),
        _variant("OF-9003", "unknown_destination", destination="Atlantis"),
        _variant("OF-9004", "unknown_company", company="GhostBus"),
        _variant("OF-9005", "invalid_date", travel_date="2026-02-30", arrival_date="2026-02-30"),
        _variant("OF-9006", "arrival_before_departure", arrival_time="06:00"),
        _variant("OF-9007", "rating_out_of_range", rating="6.2"),
        _variant("OF-9008", "rating_out_of_range", rating="-0.5"),
        _variant("OF-9009", "no_seats", seats_available="0"),
        _variant("OF-9010", "missing_field", price=""),
        _variant("OF-9011", "invalid_number", price="cheap"),
        _variant("BUS-12", "bad_offer_id"),
        _variant("OF-9013", "invalid_time", departure_time="25:61"),
        _variant("OF-9014", "negative_transfers", transfers="-1"),
        _variant("OF-9015", "invalid_boolean", changeable="maybe"),
        _variant("OF-9001", "duplicate_id"),
        ("OF-9017,SolRuta,Malaga", "malformed_row"),
        _variant("OF-9018", "impossible_duration", arrival_date="2026-07-20"),
        # valid boundary cases that must NOT be rejected:
        _variant("OF-9019", "valid", company="NocheVia", departure_time="23:55",
                 arrival_date="2026-07-13", arrival_time="07:10"),       # overnight
        _variant("OF-9020", "valid", rating="0.0", seats_available="1"),  # lowest values
    ]


def invalid_csv_text_and_expectations():
    buf = io.StringIO()
    expected = []
    w = csv.DictWriter(buf, fieldnames=HEADER, lineterminator="\n")
    w.writeheader()
    for n, (row, category) in enumerate(invalid_cases(), start=1):
        if isinstance(row, str):
            buf.write(row + "\n")
            offer_id = row.split(",")[0]
        else:
            w.writerow(row)
            offer_id = row["offer_id"]
        expected.append({"row": n, "offer_id": offer_id, "expected": category})
    return buf.getvalue(), expected


def main() -> None:
    data = Path(__file__).resolve().parent.parent / "data"
    rows = generate_offers()
    (data / "offers.csv").write_text(offers_to_csv_text(rows), encoding="utf-8", newline="")
    text, expected = invalid_csv_text_and_expectations()
    (data / "offers_invalid.csv").write_text(text, encoding="utf-8", newline="")
    (data / "offers_invalid_expected.json").write_text(
        json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    combos = {(r["company"], r["destination"]) for r in rows}
    print(f"offers.csv: {len(rows)} offers, {len(combos)} company-destination combinations")
    print(f"offers_invalid.csv: {len(expected)} rows")


if __name__ == "__main__":
    main()
