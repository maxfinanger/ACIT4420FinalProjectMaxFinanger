"""Phase 8: the interactive menu. Parsers are tested alone; sessions with scripted answers."""
import builtins
import json
import random
import re
from datetime import date, time

import pytest

from busbidder import interactive
from busbidder.booking import BookingService
from busbidder.cli import run
from busbidder.exceptions import ValidationError
from busbidder.interactive import (CUSTOM, InteractiveSession, normalise, parse_clock,
                                   parse_date_input, parse_destination, parse_hours,
                                   parse_luggage, parse_money, parse_profile_choice,
                                   parse_transfers, parse_weights_input, parse_yes_no,
                                   run_interactive)
from busbidder.loader import (load_companies, load_destinations, load_offers, load_profiles,
                              load_scoring_config)
from busbidder.marketplace import Marketplace
from busbidder.scoring_config import set_config

NAMES = [d.name for d in load_destinations()]
PROFILES = ["budget_traveller", "business_traveller", "flexible_tourist", "environment_focused"]


def bad(parser, *args):
    with pytest.raises(ValidationError) as info:
        parser(*args)
    assert info.value.category == "invalid_input"
    return info.value.message


# ------------------------------------------------------------ parsers
def test_normalise_ignores_case_accents_and_extra_spaces():
    assert normalise("  Málaga  ") == "malaga"
    assert normalise("SAN   Sebastián") == "san sebastian"


@pytest.mark.parametrize("text, expected", [
    ("4", "Malaga"), ("15", "Cadiz"), ("Malaga", "Malaga"), ("malaga", "Malaga"),
    ("  MALAGA ", "Malaga"), ("Málaga", "Malaga"), ("Córdoba", "Cordoba"),
    ("san sebastián", "San Sebastian"),
    ("sant", "Santiago de Compostela"), ("tol", "Toledo"), ("bar", "Barcelona"), ("sala", "Salamanca"),
])
def test_destination_accepts_numbers_names_accents_and_unique_prefixes(text, expected):
    assert parse_destination(text, NAMES) == expected


def test_destination_errors_are_helpful():
    assert "between 1 and 15" in bad(parse_destination, "0", NAMES)
    assert "between 1 and 15" in bad(parse_destination, "16", NAMES)
    assert "Did you mean: Malaga?" in bad(parse_destination, "Malga", NAMES)
    assert "Did you mean: San Sebastian, Santiago de Compostela?" in bad(parse_destination, "san", NAMES)
    assert "number from the list" in bad(parse_destination, "zzz", NAMES)
    assert "Please enter a destination" in bad(parse_destination, "  ", NAMES)
    bad(parse_destination, "sa", NAMES)                       # too short to guess from


@pytest.mark.parametrize("text, expected", [
    ("2026-07-12", date(2026, 7, 12)), ("12/07/2026", date(2026, 7, 12)),
    ("12.7.2026", date(2026, 7, 12)), ("1/2/2026", date(2026, 2, 1)),
])
def test_dates_in_iso_or_day_month_year(text, expected):
    assert parse_date_input(text) == expected


@pytest.mark.parametrize("text", ["2026-02-30", "tomorrow", "2026-7-12", "", "31/02/2026", "12-07-2026"])
def test_bad_dates_explain_the_format(text):
    assert "Dates look like 2026-07-12" in bad(parse_date_input, text)


def test_latest_date_cannot_be_before_the_earliest():
    earliest = date(2026, 7, 12)
    assert parse_date_input("2026-07-12", earliest) == earliest
    assert "cannot be before the earliest (2026-07-12)" in bad(parse_date_input, "2026-07-11", earliest)


@pytest.mark.parametrize("text, expected", [
    ("50", 50.0), ("50.5", 50.5), ("50,5", 50.5), ("49,90", 49.9), ("€50", 50.0), ("€ 50", 50.0),
    ("EUR 50", 50.0), ("eur50", 50.0), ("50 EUR", 50.0), ("50€", 50.0), (" 50 ", 50.0),
])
def test_money_accepts_common_ways_to_write_euros(text, expected):
    assert parse_money(text) == expected


@pytest.mark.parametrize("text", ["0", "0,00", "-5", "abc", "", "50,555", "1,000", "5 0", "EUR"])
def test_bad_money_is_explained(text):
    assert "maximum price in euros" in bad(parse_money, text)


@pytest.mark.parametrize("text, expected", [
    ("", None), ("any", None), ("No limit", None), ("direct", 0), ("Direct", 0),
    ("0", 0), ("1", 1), ("9", 9),
])
def test_transfers(text, expected):
    assert parse_transfers(text) == expected


@pytest.mark.parametrize("text", ["10", "-1", "abc", "1.5"])
def test_bad_transfers_are_explained(text):
    assert "0 to 9" in bad(parse_transfers, text)


@pytest.mark.parametrize("text, minutes", [
    ("", None), ("6", 360), ("6.5", 390), ("6,5", 390), ("6h30", 390), ("6h", 360),
    ("6 h 30 min", 390), ("6h30m", 390), ("0.5", 30), ("0h30", 30), ("48", 2880),
])
def test_journey_time_in_hours(text, minutes):
    assert parse_hours(text) == minutes


@pytest.mark.parametrize("text", ["0", "49", "48.5", "abc", "6h75", "-1", "0h0"])
def test_bad_journey_time_is_explained(text):
    assert "Enter the longest journey in hours" in bad(parse_hours, text)


@pytest.mark.parametrize("text, expected", [("", 0), ("20", 20), ("20kg", 20), ("20 KG", 20), ("0", 0)])
def test_luggage(text, expected):
    assert parse_luggage(text) == expected


@pytest.mark.parametrize("text", ["-1", "abc", "1000", "2.5"])
def test_bad_luggage_is_explained(text):
    assert "luggage allowance" in bad(parse_luggage, text)


@pytest.mark.parametrize("text, default, expected", [
    ("y", False, True), ("YES", False, True), ("j", False, True), ("ja", False, True),
    ("n", True, False), ("No", True, False), ("nei", True, False), ("", True, True), ("", False, False),
])
def test_yes_no(text, default, expected):
    assert parse_yes_no(text, default) is expected


def test_yes_no_rejects_other_answers():
    assert "y (yes) or n (no)" in bad(parse_yes_no, "maybe", False)


@pytest.mark.parametrize("text, expected", [
    ("", time(9, 0)), ("9", time(9, 0)), ("09:00", time(9, 0)), ("9:30", time(9, 30)),
    ("9.30", time(9, 30)), ("21:05", time(21, 5)), ("0", time(0, 0)), ("23:59", time(23, 59)),
])
def test_clock_times(text, expected):
    assert parse_clock(text, time(9, 0)) == expected


@pytest.mark.parametrize("text", ["24:00", "9:75", "abc", "9:5", "25"])
def test_bad_clock_times_are_explained(text):
    assert "Times look like 09:00" in bad(parse_clock, text, time(9, 0))


@pytest.mark.parametrize("text, expected", [
    ("", "budget_traveller"), ("1", "budget_traveller"), ("4", "environment_focused"),
    ("business_traveller", "business_traveller"), ("BUSINESS_TRAVELLER", "business_traveller"),
    ("c", CUSTOM), ("custom", CUSTOM), ("Own", CUSTOM),
])
def test_profile_choice(text, expected):
    assert parse_profile_choice(text, PROFILES, "budget_traveller") == expected


@pytest.mark.parametrize("text, message", [
    ("0", "between 1 and 4"), ("5", "between 1 and 4"), ("nobody", "Unknown profile 'nobody'")])
def test_bad_profile_choice(text, message):
    assert message in bad(parse_profile_choice, text, PROFILES, "budget_traveller")


def test_weights_input():
    assert parse_weights_input("price=60,duration=40") == pytest.approx({"price": 0.6, "duration": 0.4})
    message = bad(parse_weights_input, "price=50")
    assert "Weights must sum to 1.0" in message and "Example: price=40" in message
    assert "Unknown criteria" in bad(parse_weights_input, "price=50,comfort=50")


# ------------------------------------------------------------ scripted sessions
INTERRUPT = object()


def scripted(lines, hooks=None):
    """An input() that answers from a list and echoes prompt+answer, so the transcript reads like a session."""
    it, hooks, calls = iter(lines), hooks or {}, {"n": 0}

    def fake(prompt=""):
        i = calls["n"]
        calls["n"] += 1
        if i in hooks:
            hooks[i]()
        try:
            line = next(it)
        except StopIteration:
            raise EOFError from None
        if line is INTERRUPT:
            raise KeyboardInterrupt
        print(f"{prompt}{line}")
        return line
    return fake


@pytest.fixture
def market(tmp_path):
    set_config(load_scoring_config())
    comps, dests = load_companies(), load_destinations()
    offers = load_offers("data/offers.csv", [d.name for d in dests], [c.name for c in comps]).offers
    svc = BookingService(tmp_path / "b.json", rng=random.Random(5))
    svc.apply_to_offers(offers)
    return Marketplace(comps, dests, offers, load_profiles(), svc)


def session(market, lines, hooks=None, top=10):
    return run_interactive(market, scripted(lines, hooks), top)


# menu "1", destination, from, to, budget, transfers, changeable, preferred, profile, extra limits
SEARCH = ["1", "Malaga", "2026-07-12", "2026-07-14", "50", "1", "y", "09:00", "", "n"]


def out_of(capsys):
    return capsys.readouterr().out


def test_happy_path_filters_ranks_and_explains(market, capsys):
    assert session(market, SEARCH + ["0"]) == 0
    out = out_of(capsys)
    assert "HARD constraints" in out and "SOFT preferences" in out
    assert "RANKING (47 offers" in out and "RECOMMENDATION" in out and "Goodbye." in out
    assert "price at most EUR 50.00" in out and "ticket must be changeable" in out
    assert re.search(r"\n\s+1  OF-1025", out)


def test_every_bad_answer_gets_a_message_and_is_asked_again(market, capsys):
    lines = ["1",
             "Malga", "Málaga",                    # typo, then accents are fine
             "tomorrow", "12/07/2026",             # not a date, then day/month/year
             "2026-07-11", "14.7.2026",            # before the earliest date, then fine
             "abc", "0", "50",                     # not a number, zero, fine
             "ten", "1",                           # transfers
             "maybe", "y",                         # changeable
             "25:00", "9",                         # time
             "9", "",                              # profile number out of range, then default
             "n", "0"]
    assert session(market, lines) == 0
    out = out_of(capsys)
    for message in ("Did you mean: Malaga?", "Dates look like 2026-07-12",
                    "cannot be before the earliest (2026-07-12)", "maximum price in euros",
                    "0 to 9", "y (yes) or n (no)", "Times look like 09:00", "between 1 and 4"):
        assert message in out, message
    assert "RANKING (47 offers" in out


def test_q_cancels_a_question_and_returns_to_the_menu(market, capsys):
    assert session(market, ["1", "Malaga", "q", "2", "0"]) == 0
    out = out_of(capsys)
    assert "Cancelled. Back to the menu." in out and "Do a search first (option 1)." in out


def test_too_many_bad_answers_cancel_the_question(market, capsys):
    assert session(market, ["1"] + ["zzz"] * 8 + ["0"]) == 0
    out = out_of(capsys)
    assert "Too many answers I could not understand, so I cancelled the question." in out
    assert out.count("is not a destination") == 8 and "Goodbye." in out


def test_options_that_need_a_search_say_so(market, capsys):
    assert session(market, ["2", "3", "4", "5", "0"]) == 0
    assert out_of(capsys).count("Do a search first (option 1).") == 4


def test_bad_menu_choices_are_explained(market, capsys):
    assert session(market, ["9", "abc", "", "-1", "0"]) == 0
    assert out_of(capsys).count("Please type a number from 0 to 7") == 4


def test_q_at_the_menu_quits(market, capsys):
    assert session(market, ["q"]) == 0
    assert "Goodbye." in out_of(capsys)


def test_end_of_input_and_ctrl_c_end_the_session_politely(market, capsys):
    assert session(market, ["1", "Malaga"]) == 0
    assert "Input ended. Goodbye." in out_of(capsys)
    assert session(market, ["1", INTERRUPT]) == 0
    assert "Input ended. Goodbye." in out_of(capsys)


def test_too_many_bad_menu_answers_end_the_session(market, capsys):
    assert session(market, ["x"] * 8) == 0
    assert "Too many answers I could not understand." in out_of(capsys)


def test_window_outside_the_data_is_pointed_out(market, capsys):
    lines = ["1", "Malaga", "2026-08-01", "", "50", "", "", "", "", "n", "0"]
    assert session(market, lines) == 0
    out = out_of(capsys)
    assert "(offers exist for 2026-07-11 to 2026-07-15)" in out
    assert "no offers for those dates" in out and "No offer meets every hard constraint." in out


def test_search_without_results_gives_a_hint_and_nothing_to_book(market, capsys):
    lines = ["1", "Toledo", "2026-07-12", "2026-07-14", "3", "", "", "", "", "n", "5", "2", "0"]
    assert session(market, lines) == 0
    out = out_of(capsys)
    assert "No offer meets every hard constraint." in out and "Hint:" in out
    assert "Nothing to choose from." in out
    assert "no offers to choose from in the last search" in out and "The last search found no offers." in out


def test_extra_limits_become_hard_constraints(market, capsys):
    lines = SEARCH[:-1] + ["y", "7", "20", "0"]
    assert session(market, lines) == 0
    out = out_of(capsys)
    assert "journey at most 7 h" in out and "luggage allowance at least 20 kg" in out


def test_profile_by_number_and_the_environment_columns(market, capsys):
    lines = SEARCH[:8] + ["4", "n", "0"]
    assert session(market, lines) == 0
    out = out_of(capsys)
    assert "profile environment_focused" in out and "emissi" in out


def test_help_explains_hard_and_soft(market, capsys):
    assert session(market, ["7", "0"]) == 0
    out = out_of(capsys)
    assert "HARD requirements remove offers completely" in out and "SOFT preferences only change the score" in out


# ---- results: show all, re-rank, compare
def test_show_all_prints_every_offer_while_the_search_shows_only_the_top(market, capsys):
    assert session(market, SEARCH + ["0"], top=3) == 0
    assert "44 more offers not shown" in out_of(capsys)
    assert session(market, SEARCH + ["2", "0"], top=3) == 0
    out = out_of(capsys)
    assert re.search(r"\n 47  OF-\d{4}", out)


def test_rerank_with_another_profile_changes_the_winner(market, capsys):
    assert session(market, SEARCH + ["3", "2", "0"]) == 0
    out = out_of(capsys)
    assert re.search(r"\n\s+1  OF-1025", out) and re.search(r"\n\s+1  OF-1032", out)
    assert "profile business_traveller" in out


def test_rerank_with_own_weights_asks_again_after_a_bad_answer(market, capsys):
    assert session(market, SEARCH + ["3", "c", "price=50", "price=60,duration=40", "0"]) == 0
    out = out_of(capsys)
    assert "Weights must sum to 1.0" in out and "Example: price=40" in out
    assert "custom weights" in out and "your own weights" in out


def test_compare_profiles_on_the_last_search(market, capsys):
    assert session(market, SEARCH + ["4", "0"]) == 0
    out = out_of(capsys)
    assert "PROFILE COMPARISON: the same 47 offers" in out and "4 different winners" in out


def test_a_failing_search_is_reported_and_keeps_the_menu_alive(market, capsys, monkeypatch):
    def broken(*args, **kwargs):
        raise ValidationError("invalid_window", "something is wrong")
    monkeypatch.setattr(interactive, "print_search", broken)
    assert session(market, SEARCH + ["2", "0"]) == 0
    out = out_of(capsys)
    assert "Invalid request: something is wrong" in out and "Do a search first" in out


# ---- booking
def test_booking_from_the_menu_saves_it_and_lists_it(market, capsys):
    assert session(market, SEARCH + ["5", "1", "Ana Pérez", "y", "6", "0"]) == 0
    out = out_of(capsys)
    assert "BOOKING CONFIRMED" in out and "Traveller : Ana Pérez" in out
    assert "Selected: rank 1, OF-1025, SolRuta" in out
    assert re.search(r"BB-20260714-[A-Z2-9]{6}\s+Ana Pérez\s+OF-1025", out)
    assert len(market.bookings.load()) == 1


def test_declining_the_confirmation_saves_nothing(market, capsys):
    assert session(market, SEARCH + ["5", "1", "Ana", "n", "0"]) == 0
    assert "Booking cancelled, nothing was saved." in out_of(capsys)
    assert not market.bookings.store_path.exists()


def test_default_answer_to_the_confirmation_is_no(market, capsys):
    assert session(market, SEARCH + ["5", "1", "Ana", "", "0"]) == 0
    assert not market.bookings.store_path.exists()


def test_bad_selection_and_bad_name_are_asked_again(market, capsys):
    assert session(market, SEARCH + ["5", "99", "OF-0001", "of-1025", "Ana 2", "4111 1111", "Ana", "y", "0"]) == 0
    out = out_of(capsys)
    assert "rank 99 is not in the ranking (1-47)" in out
    assert "OF-0001 is not among the 47 acceptable offers" in out
    assert out.count("name may only contain letters") == 2
    assert "BOOKING CONFIRMED" in out and "Selected: rank 1, OF-1025" in out


def test_booking_the_same_offer_twice_with_one_name_is_refused(market, capsys):
    assert session(market, SEARCH + ["5", "1", "Ana", "y", "5", "1", "ana", "y", "0"]) == 0
    out = out_of(capsys)
    assert out.count("BOOKING CONFIRMED") == 1
    assert "ana already has a booking on OF-1025. Use another name" in out
    assert len(market.bookings.load()) == 1


def test_an_offer_that_sells_out_during_the_session_is_refused_cleanly(market, capsys):
    offer = next(o for o in market.offers if o.offer_id == "OF-1025")
    for i in range(offer.capacity - 1):
        market.bookings.book(offer, "Guest" + "ab"[i % 2] + "x" * (i // 2))
    lines = SEARCH + ["5", "OF-1025", "Zed", "y", "5", "OF-1025", "Yan", "y", "0"]
    assert session(market, lines) == 0
    out = out_of(capsys)
    assert out.count("BOOKING CONFIRMED") == 1 and "Seats left on this offer: 0" in out
    assert "Sorry, OF-1025 is sold out. Do a new search" in out
    assert offer.seats_available == 0


def test_a_corrupt_bookings_file_is_reported_and_left_alone(market, capsys):
    path = market.bookings.store_path
    hooks = {13: lambda: path.write_text("{oops", encoding="utf-8")}      # just before the confirmation
    assert session(market, SEARCH + ["5", "1", "Ana", "y", "0"], hooks) == 0
    out = out_of(capsys)
    assert "The booking was not made: Could not read" in out and "BOOKING CONFIRMED" not in out
    assert path.read_text(encoding="utf-8") == "{oops"


def test_listing_bookings(market, capsys):
    assert session(market, ["6", "0"]) == 0
    assert "No bookings saved yet." in out_of(capsys)
    market.bookings.store_path.write_text("{oops", encoding="utf-8")
    assert session(market, ["6", "0"]) == 0
    assert "! Could not read" in out_of(capsys)


def test_without_a_booking_service_booking_is_unavailable(market, capsys):
    plain = Marketplace(market.companies, market.destinations, market.offers, market.profiles)
    assert session(plain, SEARCH + ["5", "6", "0"]) == 0
    assert out_of(capsys).count("Booking is not available in this session.") == 2


def test_the_session_object_keeps_the_last_search(market, capsys):
    s = InteractiveSession(market, scripted(SEARCH + ["0"]))
    assert s.run() == 0
    assert len(s.ranked) == 47 and s.request.destination == "Malaga" and s.weights["price"] == 0.55


# ------------------------------------------------------------ through the command line
def test_cli_interactive_flag_starts_the_menu(capsys, monkeypatch):
    monkeypatch.setattr(builtins, "input", scripted(["0"]))
    assert run(["--interactive"]) == 0
    out = out_of(capsys)
    assert "interactive mode" in out and "Offers       : 1497 loaded" in out and "Goodbye." in out


def test_cli_interactive_passes_top_and_uses_the_bookings_option(capsys, monkeypatch, tmp_path):
    store = tmp_path / "cli.json"
    monkeypatch.setattr(builtins, "input", scripted(SEARCH + ["5", "1", "Ana", "y", "0"]))
    assert run(["-i", "--top", "3", "--bookings", str(store)]) == 0
    out = out_of(capsys)
    assert "44 more offers not shown" in out and "BOOKING CONFIRMED" in out
    assert len(json.loads(store.read_text(encoding="utf-8"))["bookings"]) == 1


@pytest.mark.parametrize("extra", [
    ["--destination", "Malaga", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "50"],
    ["--show-bookings"], ["--compare-profiles"], ["--book", "1"],
])
def test_cli_interactive_cannot_be_mixed_with_request_options(extra):
    with pytest.raises(SystemExit) as info:
        run(["--interactive"] + extra)
    assert info.value.code == 2


def test_cli_interactive_with_a_missing_data_file_exits_with_code_1(capsys):
    assert run(["--interactive", "--offers", "data/nope.csv"]) == 1
    assert "Error: File not found" in out_of(capsys)


def test_the_tip_without_options_mentions_the_interactive_menu(capsys):
    assert run([]) == 0
    assert "--interactive" in out_of(capsys)
