"""Loader: type conversion, file errors, the invalid-rows file, logging."""
import json
import logging
from datetime import date, time
from pathlib import Path

import pytest

from busbidder.exceptions import DataFileError, ValidationError
from busbidder.loader import (build_offer, load_companies, load_destinations, load_offers,
                              load_profiles)
from busbidder.validation import REQUIRED_FIELDS

DATA = Path("data")
HEADER = ",".join(REQUIRED_FIELDS) + ",emissions_kg"


def write_csv(tmp_path, *lines, name="offers.csv"):
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


GOOD_LINE = "OF-0001,SolRuta,Malaga,2026-07-12,08:00,2026-07-12,14:30,Basic,32.50,1,10,no,no,12,3.9,18.2"


# ---------------------------------------------------------------- build_offer
def test_build_offer_converts_types(good_row, known_destinations, known_companies):
    offer = build_offer(good_row, known_destinations, known_companies)
    assert offer.travel_date == date(2026, 7, 12)
    assert offer.departure_time == time(8, 0)
    assert offer.price == 32.5 and isinstance(offer.price, float)
    assert offer.transfers == 1 and offer.seats_available == 12
    assert offer.fare.changeable is False and offer.fare.luggage_kg == 10
    assert offer.fare.fare_type == "Basic"
    assert offer.duration_minutes == 390


def test_build_offer_strips_whitespace_and_accepts_yes_case_insensitive(
        good_row, known_destinations, known_companies):
    good_row["company"] = "  SolRuta "
    good_row["changeable"] = "YES"
    offer = build_offer(good_row, known_destinations, known_companies)
    assert offer.company == "SolRuta" and offer.fare.changeable is True


def test_blank_emissions_is_none(good_row, known_destinations, known_companies):
    good_row["emissions_kg"] = ""
    assert build_offer(good_row, known_destinations, known_companies).emissions_kg is None


@pytest.mark.parametrize("field, value, expected", [
    ("offer_id", "BUS-12", "bad_offer_id"),
    ("offer_id", "OF-001", "bad_offer_id"),
    ("travel_date", "2026-02-30", "invalid_date"),
    ("travel_date", "12/07/2026", "invalid_date"),
    ("travel_date", "20260712", "invalid_date"),
    ("departure_time", "25:61", "invalid_time"),
    ("departure_time", "8:00", "invalid_time"),
    ("arrival_time", "24:00", "invalid_time"),
    ("price", "cheap", "invalid_number"),
    ("price", "nan", "invalid_number"),
    ("price", "inf", "invalid_number"),
    ("transfers", "1.5", "invalid_number"),
    ("seats_available", "many", "invalid_number"),
    ("emissions_kg", "x", "invalid_number"),
    ("changeable", "maybe", "invalid_boolean"),
    ("refundable", "", "missing_field"),
    ("price", "-5.00", "negative_price"),
    ("rating", "6.2", "rating_out_of_range"),
    ("seats_available", "0", "no_seats"),
    ("destination", "Atlantis", "unknown_destination"),
    ("company", "GhostBus", "unknown_company"),
])
def test_bad_values_give_the_right_category(good_row, known_destinations, known_companies,
                                            field, value, expected):
    good_row[field] = value
    with pytest.raises(ValidationError) as info:
        build_offer(good_row, known_destinations, known_companies)
    assert info.value.category == expected


# ---------------------------------------------------------------- file errors
def test_missing_file_is_data_file_error_and_logged(caplog):
    with caplog.at_level(logging.ERROR, logger="busbidder"):
        with pytest.raises(DataFileError):
            load_offers("data/nope.csv")
    assert "File not found" in caplog.text


def test_empty_file_is_data_file_error(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(DataFileError, match="empty"):
        load_offers(str(path))


def test_missing_column_in_header_is_data_file_error(tmp_path):
    path = write_csv(tmp_path, "offer_id,company", "OF-0001,SolRuta")
    with pytest.raises(DataFileError, match="missing required columns"):
        load_offers(path)


def test_undecodable_file_is_data_file_error(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(DataFileError):
        load_offers(str(path))


def test_directory_instead_of_file_is_data_file_error(tmp_path):
    with pytest.raises(DataFileError):
        load_offers(str(tmp_path))


def test_header_only_file_gives_empty_result_and_warning(tmp_path, caplog):
    path = write_csv(tmp_path, HEADER)
    with caplog.at_level(logging.WARNING, logger="busbidder"):
        result = load_offers(path, {"Malaga"}, {"SolRuta"})
    assert result.offers == [] and result.rejected == [] and result.total_rows == 0
    assert "No data rows" in caplog.text


def test_invalid_profiles_json_is_data_file_error(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(DataFileError):
        load_profiles(str(path))


def test_company_file_with_empty_name_is_data_file_error(tmp_path):
    path = write_csv(tmp_path, "name,profile", ",no name", name="companies.csv")
    with pytest.raises(DataFileError, match="empty company name"):
        load_companies(str(path))


def test_destination_file_wrong_header_is_data_file_error(tmp_path):
    path = write_csv(tmp_path, "city", "Madrid", name="destinations.csv")
    with pytest.raises(DataFileError):
        load_destinations(str(path))


# ------------------------------------------------------ whole-file behaviour
def test_utf8_bom_is_handled(tmp_path):
    path = tmp_path / "bom.csv"
    path.write_text(HEADER + "\n" + GOOD_LINE + "\n", encoding="utf-8-sig")
    assert len(load_offers(str(path), {"Malaga"}, {"SolRuta"}).offers) == 1


def test_row_with_extra_columns_is_rejected_as_malformed(tmp_path):
    path = write_csv(tmp_path, HEADER, GOOD_LINE + ",surplus")
    result = load_offers(path, {"Malaga"}, {"SolRuta"})
    assert result.offers == []
    assert result.rejected[0].category == "malformed_row"


def test_duplicate_id_first_valid_row_wins(tmp_path):
    second = GOOD_LINE.replace("32.50", "99.00")
    result = load_offers(write_csv(tmp_path, HEADER, GOOD_LINE, second), {"Malaga"}, {"SolRuta"})
    assert [o.price for o in result.offers] == [32.5]
    assert result.rejected[0].category == "duplicate_id" and result.rejected[0].row == 2


def test_duplicate_id_after_a_rejected_first_row_is_accepted(tmp_path):
    bad = GOOD_LINE.replace("32.50", "-1")
    result = load_offers(write_csv(tmp_path, HEADER, bad, GOOD_LINE), {"Malaga"}, {"SolRuta"})
    assert len(result.offers) == 1 and result.rejected[0].category == "negative_price"


def test_loading_continues_after_a_bad_row(tmp_path):
    bad = GOOD_LINE.replace("OF-0001", "OF-0002").replace("32.50", "cheap")
    good2 = GOOD_LINE.replace("OF-0001", "OF-0003")
    result = load_offers(write_csv(tmp_path, HEADER, GOOD_LINE, bad, good2),
                         {"Malaga"}, {"SolRuta"})
    assert [o.offer_id for o in result.offers] == ["OF-0001", "OF-0003"]
    assert result.total_rows == 3 and result.rejected_by_category() == {"invalid_number": 1}


def test_rejected_rows_are_logged_with_row_id_and_reason(tmp_path, caplog):
    bad = GOOD_LINE.replace("32.50", "-1")
    with caplog.at_level(logging.INFO, logger="busbidder"):
        load_offers(write_csv(tmp_path, HEADER, bad), {"Malaga"}, {"SolRuta"})
    assert "Rejected row 1 (OF-0001)" in caplog.text
    assert "negative_price" in caplog.text
    assert "0 accepted, 1 rejected" in caplog.text


# ---------------------------------------------------- the real data files
def _names(path):
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        return {r["name"] for r in csv.DictReader(f)}


def test_real_offers_file_loads_without_any_rejection():
    result = load_offers("data/offers.csv", _names("data/destinations.csv"), _names("data/companies.csv"))
    assert len(result.offers) == 1497
    assert result.rejected == []
    assert {o.company for o in result.offers} == _names("data/companies.csv")
    assert any(o.arrival_date > o.travel_date for o in result.offers)   # overnight offers kept


def test_invalid_file_is_detected_exactly_as_expected():
    expected = json.loads((DATA / "offers_invalid_expected.json").read_text(encoding="utf-8"))
    result = load_offers("data/offers_invalid.csv", _names("data/destinations.csv"),
                         _names("data/companies.csv"))
    rejected = {r.row: r.category for r in result.rejected}
    assert result.total_rows == len(expected)
    for entry in expected:
        if entry["expected"] == "valid":
            assert entry["row"] not in rejected, entry
        else:
            assert rejected.get(entry["row"]) == entry["expected"], entry
    accepted = [e for e in expected if e["expected"] == "valid"]
    assert len(result.offers) == len(accepted) == 3


def test_every_error_category_in_the_invalid_file_is_covered():
    expected = json.loads((DATA / "offers_invalid_expected.json").read_text(encoding="utf-8"))
    cats = {e["expected"] for e in expected} - {"valid"}
    assert len(cats) == 16
