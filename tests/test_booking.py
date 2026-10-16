"""Phase 7: simulated booking, seat accounting, the bookings file, selection, CLI."""
import hashlib
import json
import os
import random
import re
import string
from datetime import date, datetime

import pytest

from busbidder import booking as booking_module
from busbidder.booking import (BookingService, booking_from_dict, booking_to_dict,
                               format_booking_list, format_confirmation, select_from_ranking)
from busbidder.cli import run
from busbidder.exceptions import (BookingError, DataFileError, DuplicateBookingError,
                                  SoldOutError, ValidationError)
from busbidder.filtering import filter_offers
from busbidder.loader import (load_companies, load_destinations, load_offers, load_profiles,
                              load_scoring_config)
from busbidder.marketplace import Marketplace
from busbidder.models import FareConditions, Offer, RankedOffer, TravelRequest
from busbidder.ranking import rank_offers
from busbidder.scoring_config import set_config
from busbidder.validation import clean_traveller_name, is_valid_booking_ref
from tests.test_ranking import SPEC, make

NOW = datetime(2026, 7, 1, 12, 0, 0)


@pytest.fixture
def service(tmp_path):
    return BookingService(tmp_path / "bookings.json", rng=random.Random(1), clock=lambda: NOW)


def names(n):
    return [a + b for a in string.ascii_uppercase for b in string.ascii_lowercase][:n]


# ------------------------------------------------------------ traveller name
@pytest.mark.parametrize("raw, clean", [
    ("Ana Pérez", "Ana Pérez"), ("  Mary-Jane   O'Neil ", "Mary-Jane O'Neil"),
    ("José María", "José María"), ("李 雷", "李 雷"), ("St. John", "St. John"),
    ("a" * 60, "a" * 60),
])
def test_valid_names_are_accepted_and_tidied(raw, clean):
    assert clean_traveller_name(raw) == clean


@pytest.mark.parametrize("raw", [
    "", "   ", "Ana 2", "4111 1111 1111 1111", "Ana@x", "-Ana", "Ana-", "Ana--Pérez",
    "Ana_Pérez", "a" * 61, None, 123, "Ana\n\t2",
])
def test_invalid_names_are_rejected(raw):
    with pytest.raises(ValidationError) as info:
        clean_traveller_name(raw)
    assert info.value.category == "invalid_name"


def test_card_number_in_the_name_is_refused_and_nothing_is_saved(service):
    with pytest.raises(ValidationError, match="no payment data"):
        service.book(make(), "4111 1111 1111 1111")
    assert not service.store_path.exists()


# ------------------------------------------------------------ one booking
def test_capacity_defaults_to_the_seats_in_the_file():
    o = make(seats=7)
    assert o.capacity == 7 and o.seats_available == 7


def test_booking_keeps_the_journey_fare_and_simulated_payment(service):
    offer = make("OF-0042", price=31.5, seats=5, changeable=True)
    b = service.book(offer, "Ana Pérez")
    assert (b.offer_id, b.company, b.destination) == ("OF-0042", "SolRuta", "Malaga")
    assert b.travel_date == date(2026, 7, 12) and b.price_paid == 31.5
    assert b.fare == offer.fare and b.fare.changeable is True
    assert b.payment_status == "SIMULATED-PAID" and b.booked_at == "2026-07-01T12:00:00"
    assert b.traveller_name == "Ana Pérez" and b.duration_minutes == offer.duration_minutes


def test_reference_has_the_required_format(service):
    b = service.book(make(), "Ana")
    assert is_valid_booking_ref(b.reference) and b.reference.startswith("BB-20260712-")


def test_seats_are_reduced_and_capacity_is_not(service):
    offer = make(seats=5)
    service.book(offer, "Ana")
    assert (offer.seats_available, offer.capacity) == (4, 5)
    assert service.seats_left(offer) == 4


def test_booking_is_saved_and_read_back_unchanged(service):
    b = service.book(make(), "Ana Pérez")
    assert service.load() == [b]
    assert booking_from_dict(booking_to_dict(b)) == b


def test_saved_file_has_a_version_and_no_payment_data(service):
    service.book(make(), "Ana")
    data = json.loads(service.store_path.read_text(encoding="utf-8"))
    assert data["version"] == 1 and len(data["bookings"]) == 1
    assert set(data["bookings"][0]) == {
        "reference", "offer_id", "company", "destination", "travel_date", "departure_time",
        "arrival_date", "arrival_time", "price_paid", "traveller_name", "fare",
        "payment_status", "booked_at"}
    assert set(data["bookings"][0]["fare"]) == {"fare_type", "changeable", "refundable", "luggage_kg"}


def test_store_in_a_new_folder_is_created(tmp_path):
    svc = BookingService(tmp_path / "a" / "b" / "bookings.json")
    svc.book(make(), "Ana")
    assert (tmp_path / "a" / "b" / "bookings.json").exists()


# ------------------------------------------------------------ seats: last seat, sold out
def test_last_seat_can_be_booked_once(service):
    offer = make(seats=1)
    service.book(offer, "Ana")
    assert offer.seats_available == 0
    with pytest.raises(SoldOutError, match="sold out"):
        service.book(offer, "Eva")
    assert len(service.load()) == 1


def test_every_seat_can_be_booked_and_no_more(service):
    offer = make(seats=3)
    for name in names(3):
        service.book(offer, name)
    assert offer.seats_available == 0 and service.seats_left(offer) == 0
    with pytest.raises(SoldOutError):
        service.book(offer, "Zed")
    assert len(service.load()) == 3


def test_a_stale_offer_cannot_oversell_because_the_file_is_the_truth(tmp_path):
    first = BookingService(tmp_path / "b.json", rng=random.Random(1))
    second = BookingService(tmp_path / "b.json", rng=random.Random(2))   # another program run
    a, b = make(seats=1), make(seats=1)                                    # same offer, two objects
    first.book(a, "Ana")
    assert b.seats_available == 1                                          # stale
    with pytest.raises(SoldOutError):
        second.book(b, "Eva")
    assert b.seats_available == 0                                          # corrected
    assert len(first.load()) == 1


def test_different_offers_have_separate_seat_counts(service):
    a, b = make("OF-0001", seats=1), make("OF-0002", seats=1)
    service.book(a, "Ana")
    service.book(b, "Ana")
    assert (a.seats_available, b.seats_available) == (0, 0)


# ------------------------------------------------------------ double booking
def test_same_traveller_cannot_book_the_same_offer_twice(service):
    offer = make(seats=5)
    service.book(offer, "Ana Pérez")
    for again in ("Ana Pérez", "ana pérez", "  ANA   PÉREZ "):
        with pytest.raises(DuplicateBookingError, match="already has a booking"):
            service.book(offer, again)
    assert offer.seats_available == 4 and len(service.load()) == 1


def test_same_traveller_can_book_different_offers_and_different_names_the_same_offer(service):
    a, b = make("OF-0001", seats=5), make("OF-0002", seats=5)
    service.book(a, "Ana")
    service.book(b, "Ana")
    service.book(a, "Eva")
    assert len(service.load()) == 3


# ------------------------------------------------------------ consistency across restarts
def test_seat_counts_survive_a_restart(tmp_path):
    path = tmp_path / "b.json"
    first = BookingService(path, rng=random.Random(1))
    offer = make(seats=5)
    for name in names(3):
        first.book(offer, name)
    fresh_offer = make(seats=5)                       # a new run reads the unchanged offers file
    second = BookingService(path)
    second.apply_to_offers([fresh_offer])
    assert (fresh_offer.seats_available, fresh_offer.capacity) == (2, 5)


def test_apply_with_no_file_changes_nothing(service):
    offer = make(seats=5)
    service.apply_to_offers([offer])
    assert offer.seats_available == 5


def test_booking_for_an_unknown_offer_is_ignored_with_a_warning(service, caplog):
    service.book(make("OF-0099", seats=5), "Ana")
    offer = make("OF-0001", seats=5)
    with caplog.at_level("WARNING", logger="busbidder"):
        service.apply_to_offers([offer])
    assert offer.seats_available == 5 and "OF-0099" in caplog.text


def test_more_bookings_than_seats_clamps_to_zero_with_a_warning(tmp_path, caplog):
    svc = BookingService(tmp_path / "b.json", rng=random.Random(1))
    big = make(seats=3)
    for name in names(3):
        svc.book(big, name)
    smaller = make(seats=2)                           # the offers file changed afterwards
    with caplog.at_level("WARNING", logger="busbidder"):
        svc.apply_to_offers([smaller])
    assert smaller.seats_available == 0 and "3 bookings but only 2 seats" in caplog.text


def test_offers_file_is_never_modified_by_booking(service):
    digest = lambda: hashlib.sha256(open("data/offers.csv", "rb").read()).hexdigest()
    before = digest()
    service.book(make(), "Ana")
    assert digest() == before


# ------------------------------------------------------------ corrupt or odd store files
def _valid_store(tmp_path):
    svc = BookingService(tmp_path / "good.json", rng=random.Random(1), clock=lambda: NOW)
    svc.book(make(seats=5), "Ana")
    svc.book(make(seats=5), "Eva")
    return json.loads(svc.store_path.read_text(encoding="utf-8"))


def _mutated(field_path, value):
    def change(data):
        node = data["bookings"][0]
        *parents, last = field_path
        for p in parents:
            node = node[p]
        if value is KeyError:
            del node[last]
        else:
            node[last] = value
        return data
    return change


CORRUPT = [
    ("not json", lambda d: "{oops"),
    ("empty file", lambda d: ""),
    ("a list", lambda d: "[]"),
    ("wrong version", lambda d: {**d, "version": 2}),
    ("bookings not a list", lambda d: {**d, "bookings": {}}),
    ("bad reference", _mutated(["reference"], "BAD")),
    ("lowercase reference", _mutated(["reference"], "BB-20260712-abcdef")),
    ("duplicate reference", lambda d: {**d, "bookings": [d["bookings"][0], d["bookings"][0]]}),
    ("bad date", _mutated(["travel_date"], "2026-02-30")),
    ("bad time", _mutated(["departure_time"], "25:00")),
    ("negative price", _mutated(["price_paid"], -1)),
    ("text price", _mutated(["price_paid"], "cheap")),
    ("bool price", _mutated(["price_paid"], True)),
    ("missing fare", _mutated(["fare"], KeyError)),
    ("changeable as text", _mutated(["fare", "changeable"], "yes")),
    ("negative luggage", _mutated(["fare", "luggage_kg"], -5)),
    ("name with digits", _mutated(["traveller_name"], "Ana 2")),
    ("bad offer id", _mutated(["offer_id"], "XX-1")),
    ("missing company", _mutated(["company"], KeyError)),
    ("entry not an object", lambda d: {**d, "bookings": ["x"]}),
]


@pytest.mark.parametrize("label, change", CORRUPT, ids=[c[0] for c in CORRUPT])
def test_a_bad_bookings_file_is_reported_and_never_overwritten(tmp_path, label, change):
    data = change(_valid_store(tmp_path))
    path = tmp_path / "bad.json"
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    before = path.read_bytes()
    svc = BookingService(path)
    with pytest.raises(DataFileError):
        svc.load()
    with pytest.raises(DataFileError):
        svc.book(make(), "Zed")
    with pytest.raises(DataFileError):
        svc.apply_to_offers([make()])
    assert path.read_bytes() == before


def test_undecodable_bookings_file_is_a_data_file_error(tmp_path):
    path = tmp_path / "b.json"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(DataFileError):
        BookingService(path).load()


def test_error_message_names_the_file_and_the_booking_number(tmp_path):
    data = _mutated(["price_paid"], -1)(_valid_store(tmp_path))
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(DataFileError, match=r"bad\.json: booking #1: 'price_paid'"):
        BookingService(path).load()


# ------------------------------------------------------------ saving fails
def test_failed_save_leaves_no_booking_no_temp_file_and_the_seat_count_alone(tmp_path, monkeypatch):
    svc = BookingService(tmp_path / "b.json", rng=random.Random(1))
    offer = make(seats=5)
    monkeypatch.setattr(booking_module.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(BookingError, match="could not save the booking: disk full"):
        svc.book(offer, "Ana")
    assert offer.seats_available == 5
    assert not (tmp_path / "b.json").exists() and list(tmp_path.glob("*.tmp")) == []
    monkeypatch.undo()
    svc.book(offer, "Ana")                                   # works again afterwards
    assert offer.seats_available == 4 and len(svc.load()) == 1


def test_failed_save_keeps_the_old_file_intact(tmp_path, monkeypatch):
    svc = BookingService(tmp_path / "b.json", rng=random.Random(1))
    svc.book(make(seats=5), "Ana")
    before = svc.store_path.read_bytes()
    monkeypatch.setattr(booking_module.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("nope")))
    with pytest.raises(BookingError):
        svc.book(make(seats=5), "Eva")
    assert svc.store_path.read_bytes() == before


# ------------------------------------------------------------ references
def test_references_are_unique_and_valid(tmp_path):
    svc = BookingService(tmp_path / "b.json", rng=random.Random(3))
    offer = make(seats=500)
    refs = [svc.book(offer, n).reference for n in names(120)]
    assert len(set(refs)) == 120 and all(is_valid_booking_ref(r) for r in refs)


def test_references_avoid_confusing_characters(tmp_path):
    svc = BookingService(tmp_path / "b.json", rng=random.Random(4))
    offer = make(seats=500)
    for n in names(60):
        suffix = svc.book(offer, n).reference.rsplit("-", 1)[1]
        assert not set(suffix) & set("01OI")


class SequenceRng:
    def __init__(self, text):
        self.chars = iter(text)

    def choice(self, alphabet):
        return next(self.chars)


def test_a_reference_collision_is_retried(tmp_path):
    svc = BookingService(tmp_path / "b.json", rng=SequenceRng("AAAAAA" + "AAAAAA" + "BBBBBB"))
    offer = make(seats=5)
    first, second = svc.book(offer, "Ana"), svc.book(offer, "Eva")
    assert first.reference.endswith("AAAAAA") and second.reference.endswith("BBBBBB")


def test_giving_up_after_too_many_collisions(tmp_path):
    class Always:
        def choice(self, alphabet):
            return "A"
    svc = BookingService(tmp_path / "b.json", rng=Always())
    offer = make(seats=5)
    svc.book(offer, "Ana")
    with pytest.raises(BookingError, match="unique booking reference"):
        svc.book(offer, "Eva")
    assert len(svc.load()) == 1 and offer.seats_available == 4


def test_same_seed_gives_the_same_references(tmp_path):
    a = BookingService(tmp_path / "a.json", rng=random.Random(9)).book(make(), "Ana")
    b = BookingService(tmp_path / "b.json", rng=random.Random(9)).book(make(), "Ana")
    assert a.reference == b.reference


# ------------------------------------------------------------ choosing from the ranking
@pytest.fixture
def ranked():
    offers = [make(f"OF-000{i}", price=30 + i) for i in range(1, 6)]
    req = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50.0)
    return rank_offers(offers, req, {"price": 1.0})


def test_select_by_rank_number_and_offer_id(ranked):
    assert select_from_ranking(ranked, "1").rank == 1
    assert select_from_ranking(ranked, " 5 ").rank == 5
    assert select_from_ranking(ranked, "OF-0003").offer.offer_id == "OF-0003"
    assert select_from_ranking(ranked, "of-0003").offer.offer_id == "OF-0003"


@pytest.mark.parametrize("target, text", [
    ("0", "rank 0 is not in the ranking (1-5)"), ("6", "rank 6 is not in the ranking (1-5)"),
    ("OF-9999", "OF-9999 is not among the 5 acceptable offers"),
    ("-1", "not a rank number"), ("cheapest", "not a rank number"), ("", "not a rank number"),
])
def test_bad_selection_is_explained(ranked, target, text):
    with pytest.raises(ValidationError, match=re.escape(text)) as info:
        select_from_ranking(ranked, target)
    assert info.value.category == "invalid_selection"


def test_selecting_from_an_empty_ranking():
    with pytest.raises(ValidationError, match="no offers to choose from"):
        select_from_ranking([], "1")


# ------------------------------------------------------------ text
def test_confirmation_shows_everything_the_spec_asks_for(service):
    b = service.book(make("OF-0042", price=31.5, changeable=True, seats=5), "Ana Pérez")
    text = format_confirmation(b, 4, rank=1, score=76.84)
    for part in (b.reference, "Ana Pérez", "Madrid to Malaga with SolRuta", "Sun 12 Jul 2026 09:00",
                 "changeable: yes", "refundable: no", "luggage: 20 kg", "EUR 31.50",
                 "SIMULATED-PAID", "no real payment was taken", "OF-0042 (rank 1, score 76.8)",
                 "Seats left on this offer: 4"):
        assert part in text
    assert "rank" not in format_confirmation(b, 4)


def test_booking_list(service):
    assert format_booking_list([]) == "No bookings saved yet."
    service.book(make(seats=5), "Ana")
    out = format_booking_list(service.load())
    assert "Ana" in out and "OF-0001" in out and "SolRuta" in out and "BB-20260712-" in out


# ------------------------------------------------------------ marketplace + real data
@pytest.fixture(scope="module")
def data():
    set_config(load_scoring_config())
    comps, dests = load_companies(), load_destinations()
    return comps, dests, [d.name for d in dests], [c.name for c in comps]


def fresh_market(data, store):
    comps, dests, dn, cn = data
    offers = load_offers("data/offers.csv", dn, cn).offers
    svc = BookingService(store, rng=random.Random(5))
    svc.apply_to_offers(offers)
    return Marketplace(comps, dests, offers, load_profiles(), svc), svc


def test_marketplace_without_booking_service_refuses(data):
    comps, dests, *_ = data
    with pytest.raises(BookingError, match="no booking service"):
        Marketplace(comps, dests, [], {}).book(make(), "Ana")


def test_booking_from_a_real_ranking_reduces_seats_and_persists(data, tmp_path):
    set_config(load_scoring_config())
    market, svc = fresh_market(data, tmp_path / "b.json")
    req = TravelRequest(**SPEC, profile="budget_traveller")
    _, ranked = market.search(req)
    top = ranked[0].offer
    seats_before = top.seats_available
    booking = market.book(top, "Ana Pérez")
    assert top.seats_available == seats_before - 1
    assert booking.offer_id == top.offer_id and booking.fare == top.fare
    restarted, _ = fresh_market(data, tmp_path / "b.json")            # new run, same files
    again = next(o for o in restarted.offers if o.offer_id == top.offer_id)
    assert again.seats_available == seats_before - 1


def test_a_sold_out_offer_disappears_from_the_next_search(data, tmp_path):
    set_config(load_scoring_config())
    market, svc = fresh_market(data, tmp_path / "b.json")
    req = TravelRequest(**SPEC, profile="budget_traveller")
    result, ranked = market.search(req)
    target = min((r.offer for r in ranked), key=lambda o: o.seats_available)
    for name in names(target.capacity):
        market.book(target, name)
    assert target.seats_available == 0
    restarted, _ = fresh_market(data, tmp_path / "b.json")
    result2, ranked2 = restarted.search(req)
    assert target.offer_id not in {r.offer.offer_id for r in ranked2}
    assert len(ranked2) == len(ranked) - 1
    assert result2.removed_by_reason["no seats left"] == 1


# ------------------------------------------------------------ CLI
REQ = ["--destination", "Malaga", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "50",
       "--max-transfers", "1", "--changeable"]


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "cli_bookings.json")


def test_cli_books_the_top_offer_and_saves_it(capsys, store, monkeypatch):
    monkeypatch.setenv("BUSBIDDER_SEED", "7")
    assert run(REQ + ["--book", "1", "--name", "Ana Pérez", "--bookings", store]) == 0
    out = capsys.readouterr().out
    assert "BOOKING CONFIRMED" in out
    assert re.search(r"Reference : BB-20260714-[A-Z2-9]{6}", out)
    assert "Traveller : Ana Pérez" in out and "SIMULATED-PAID" in out
    assert "OF-1025 (rank 1, score 76.8)" in out
    saved = json.loads(open(store, encoding="utf-8").read())["bookings"]
    assert len(saved) == 1 and saved[0]["offer_id"] == "OF-1025" and saved[0]["fare"]["luggage_kg"] == 20


def test_cli_seed_makes_the_reference_reproducible(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("BUSBIDDER_SEED", "7")
    refs = []
    for n in range(2):
        run(REQ + ["--book", "1", "--name", "Ana", "--bookings", str(tmp_path / f"s{n}.json")])
        refs.append(re.search(r"Reference : (\S+)", capsys.readouterr().out).group(1))
    assert refs[0] == refs[1]


def test_cli_second_booking_sees_one_seat_less(capsys, store):
    run(REQ + ["--book", "OF-1025", "--name", "Ana", "--bookings", store])
    first = int(re.search(r"Seats left on this offer: (\d+)", capsys.readouterr().out).group(1))
    run(REQ + ["--book", "OF-1025", "--name", "Eva", "--bookings", store])
    second = int(re.search(r"Seats left on this offer: (\d+)", capsys.readouterr().out).group(1))
    assert second == first - 1


def test_cli_can_book_a_rank_that_is_not_shown_in_the_table(capsys, store):
    assert run(REQ + ["--top", "3", "--book", "10", "--name", "Ana", "--bookings", store]) == 0
    assert "(rank 10," in capsys.readouterr().out


def test_cli_duplicate_booking_is_refused_with_code_3(capsys, store):
    run(REQ + ["--book", "1", "--name", "Ana", "--bookings", store])
    capsys.readouterr()
    assert run(REQ + ["--book", "1", "--name", "ANA", "--bookings", store]) == 3
    assert "Booking refused: ANA already has a booking on OF-1025" in capsys.readouterr().out
    assert len(json.loads(open(store, encoding="utf-8").read())["bookings"]) == 1


def test_cli_sold_out_offer_is_no_longer_offered(capsys, tmp_path, data):
    store = str(tmp_path / "b.json")
    market, svc = fresh_market(data, store)
    top = next(o for o in market.offers if o.offer_id == "OF-1025")
    for name in names(top.capacity):
        svc.book(top, name)
    assert run(REQ + ["--book", "OF-1025", "--name", "Zed", "--bookings", store]) == 2
    out = capsys.readouterr().out
    assert "RANKING (46 offers" in out and "no seats left" in out
    assert "OF-1025 is not among the 46 acceptable offers" in out


@pytest.mark.parametrize("target, text", [
    ("99", "rank 99 is not in the ranking (1-47)"),
    ("OF-0001", "OF-0001 is not among the 47 acceptable offers"),
    ("cheapest", "not a rank number"),
])
def test_cli_invalid_selection_gives_code_2_and_saves_nothing(capsys, store, target, text):
    assert run(REQ + ["--book", target, "--name", "Ana", "--bookings", store]) == 2
    assert text in capsys.readouterr().out and not os.path.exists(store)


def test_cli_invalid_name_gives_code_2_and_saves_nothing(capsys, store):
    assert run(REQ + ["--book", "1", "--name", "Ana 2", "--bookings", store]) == 2
    out = capsys.readouterr().out
    assert "Booking not made: name may only contain letters" in out and not os.path.exists(store)


def test_cli_booking_with_no_result_has_nothing_to_choose(capsys, store):
    args = ["--destination", "Toledo", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "3"]
    assert run(args + ["--book", "1", "--name", "Ana", "--bookings", store]) == 2
    assert "no offers to choose from" in capsys.readouterr().out


@pytest.mark.parametrize("args", [
    ["--book", "1", "--name", "Ana"],                                        # no request
    REQ + ["--book", "1"],                                                   # no name
    REQ + ["--book", "1", "--name", "Ana", "--compare-profiles"],            # incompatible
])
def test_cli_bad_booking_arguments_are_usage_errors(args):
    with pytest.raises(SystemExit) as info:
        run(args)
    assert info.value.code == 2


def test_cli_bad_seed_is_a_usage_error(monkeypatch):
    monkeypatch.setenv("BUSBIDDER_SEED", "abc")
    with pytest.raises(SystemExit):
        run([])


def test_cli_show_bookings(capsys, store):
    assert run(["--show-bookings", "--bookings", store]) == 0
    out = capsys.readouterr().out
    assert "Bookings     : 0 saved" in out and "No bookings saved yet." in out
    run(REQ + ["--book", "1", "--name", "Ana Pérez", "--bookings", store])
    capsys.readouterr()
    assert run(["--show-bookings", "--bookings", store]) == 0
    out = capsys.readouterr().out
    assert "Bookings     : 1 saved" in out and "Ana Pérez" in out and "OF-1025" in out


def test_cli_corrupt_bookings_file_is_a_clear_error_and_is_left_alone(capsys, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    assert run(REQ + ["--book", "1", "--name", "Ana", "--bookings", str(path)]) == 1
    assert "Error: Could not read" in capsys.readouterr().out
    assert path.read_text(encoding="utf-8") == "{oops"


def test_cli_without_booking_flags_never_writes_the_bookings_file(capsys, store):
    assert run(REQ + ["--bookings", store]) == 0
    assert not os.path.exists(store)
