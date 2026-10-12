"""Phase 2 tests: the generated dataset itself (no loader involved yet)."""
import csv
import json
import re
from datetime import datetime
from pathlib import Path

from scripts.generate_data import (HEADER, generate_offers, invalid_csv_text_and_expectations,
                                    offers_to_csv_text)

DATA = Path("data")


def read_rows(name="offers.csv"):
    with (DATA / name).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_generation_is_reproducible():
    assert generate_offers(42) == generate_offers(42)


def test_different_seed_gives_different_data():
    assert generate_offers(1) != generate_offers(2)


def test_committed_file_matches_generator_output():
    # If this fails: re-run  python scripts/generate_data.py  (or the script was changed)
    assert (DATA / "offers.csv").read_text(encoding="utf-8") == offers_to_csv_text(generate_offers())


def test_header_columns():
    with (DATA / "offers.csv").open(encoding="utf-8") as f:
        assert next(csv.reader(f)) == HEADER


def test_all_companies_and_destinations_present():
    rows = read_rows()
    companies = {r["name"] for r in csv.DictReader((DATA / "companies.csv").open(encoding="utf-8"))}
    destinations = {r["name"] for r in csv.DictReader((DATA / "destinations.csv").open(encoding="utf-8"))}
    assert {r["company"] for r in rows} == companies
    assert {r["destination"] for r in rows} == destinations


def test_at_least_75_company_destination_combinations():
    combos = {(r["company"], r["destination"]) for r in read_rows()}
    assert len(combos) >= 75


def test_offer_ids_are_unique_and_match_pattern():
    ids = [r["offer_id"] for r in read_rows()]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"OF-\d{4}", i) for i in ids)


def test_valid_rows_have_sensible_values():
    for r in read_rows():
        dep = datetime.fromisoformat(f'{r["travel_date"]}T{r["departure_time"]}')
        arr = datetime.fromisoformat(f'{r["arrival_date"]}T{r["arrival_time"]}')
        minutes = (arr - dep).total_seconds() / 60
        assert 0 < minutes <= 24 * 60, r["offer_id"]
        assert float(r["price"]) > 0
        assert int(r["seats_available"]) >= 1
        assert 0 <= float(r["rating"]) <= 5
        assert int(r["transfers"]) >= 0
        assert r["changeable"] in ("yes", "no") and r["refundable"] in ("yes", "no")


def test_dataset_contains_overnight_offers():
    rows = read_rows()
    assert any(r["arrival_date"] != r["travel_date"] for r in rows)


def test_companies_differ_in_a_measurable_way():
    rows = read_rows()
    avg = lambda c: sum(float(r["price"]) for r in rows if r["company"] == c) / \
        sum(1 for r in rows if r["company"] == c)
    assert avg("SolRuta") < avg("Camino Express")      # low-cost vs premium
    assert all(r["transfers"] == "0" for r in rows
               if r["company"] == "Camino Express" and r["destination"] in
               {"Barcelona", "Valencia", "Seville", "Malaga", "Bilbao", "Zaragoza"})


def test_invalid_file_matches_expectations_file():
    text, expected = invalid_csv_text_and_expectations()
    assert (DATA / "offers_invalid.csv").read_text(encoding="utf-8") == text
    saved = json.loads((DATA / "offers_invalid_expected.json").read_text(encoding="utf-8"))
    assert saved == expected
    assert len(text.strip().splitlines()) - 1 == len(expected)   # header excluded


def test_invalid_file_covers_the_error_categories_in_the_spec():
    categories = {e["expected"] for e in json.loads(
        (DATA / "offers_invalid_expected.json").read_text(encoding="utf-8"))}
    for needed in ("negative_price", "unknown_destination", "invalid_date",
                   "arrival_before_departure", "rating_out_of_range", "no_seats",
                   "missing_field", "malformed_row", "valid"):
        assert needed in categories
