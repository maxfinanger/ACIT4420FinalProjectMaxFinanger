"""Phase 4: hard constraints, filter_offers, request validation, CLI output."""
import random
from datetime import date, time

import pytest

from busbidder.cli import run
from busbidder.exceptions import ValidationError
from busbidder.filtering import (BudgetConstraint, Constraint, DestinationConstraint,
                                 FlexibilityConstraint, LuggageConstraint, MaxDurationConstraint,
                                 MaxTransfersConstraint, SeatsConstraint, TravelWindowConstraint,
                                 default_constraints, filter_offers, hard_constraint_lines,
                                 soft_preference_lines)
from busbidder.loader import load_companies, load_destinations, load_offers
from busbidder.marketplace import Marketplace
from busbidder.models import FareConditions, TravelRequest
from busbidder.validation import validate_request


@pytest.fixture
def request_():
    return TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50.0)


@pytest.fixture
def req(request_):
    return request_


# ------------------------------------------------------------ single constraints
def test_destination_exact_match_only(offer_factory, req):
    c = DestinationConstraint()
    assert c.is_satisfied(offer_factory(destination="Malaga"), req)
    assert not c.is_satisfied(offer_factory(destination="Granada"), req)
    assert not c.is_satisfied(offer_factory(destination="malaga"), req)


@pytest.mark.parametrize("day, ok", [
    (date(2026, 7, 11), False), (date(2026, 7, 12), True), (date(2026, 7, 13), True),
    (date(2026, 7, 14), True), (date(2026, 7, 15), False),
])
def test_travel_window_includes_both_end_days(offer_factory, req, day, ok):
    assert TravelWindowConstraint().is_satisfied(offer_factory(travel_date=day), req) is ok


def test_travel_window_single_day(offer_factory):
    r = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 12), 50)
    assert TravelWindowConstraint().is_satisfied(offer_factory(travel_date=date(2026, 7, 12)), r)
    assert not TravelWindowConstraint().is_satisfied(offer_factory(travel_date=date(2026, 7, 13)), r)


def test_window_uses_departure_date_not_arrival_date(offer_factory, req):
    overnight = offer_factory(travel_date=date(2026, 7, 14), departure_time=time(23, 55),
                              arrival_date=date(2026, 7, 15), arrival_time=time(7, 0))
    assert TravelWindowConstraint().is_satisfied(overnight, req)


@pytest.mark.parametrize("seats, ok", [(0, False), (1, True), (40, True)])
def test_seats(offer_factory, req, seats, ok):
    assert SeatsConstraint().is_satisfied(offer_factory(seats_available=seats), req) is ok


@pytest.mark.parametrize("price, ok", [(49.99, True), (50.00, True), (50.01, False)])
def test_budget_boundary(offer_factory, req, price, ok):
    assert BudgetConstraint().is_satisfied(offer_factory(price=price), req) is ok


def test_transfers_inactive_without_limit_and_boundary_with_limit(offer_factory, req):
    c = MaxTransfersConstraint()
    assert not c.is_active(req)
    r = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50, max_transfers=1)
    assert c.is_active(r)
    assert c.is_satisfied(offer_factory(transfers=0), r)
    assert c.is_satisfied(offer_factory(transfers=1), r)
    assert not c.is_satisfied(offer_factory(transfers=2), r)


def test_direct_only_request(offer_factory):
    r = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50, max_transfers=0)
    assert MaxTransfersConstraint().is_active(r)       # 0 is a real limit, not "no limit"
    assert not MaxTransfersConstraint().is_satisfied(offer_factory(transfers=1), r)


def test_max_duration_boundary_and_overnight(offer_factory):
    r = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50, max_duration_minutes=390)
    c = MaxDurationConstraint()
    assert c.is_active(r)
    assert c.is_satisfied(offer_factory(), r)                                   # exactly 390 min
    assert not c.is_satisfied(offer_factory(arrival_time=time(14, 31)), r)      # 391 min
    night = offer_factory(departure_time=time(23, 0), arrival_date=date(2026, 7, 13),
                          arrival_time=time(5, 0))
    assert c.is_satisfied(night, r)                                             # 360 min across midnight


def test_luggage_boundary(offer_factory):
    r = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50, min_luggage_kg=20)
    c = LuggageConstraint()
    assert c.is_active(r)
    assert c.is_satisfied(offer_factory(fare=FareConditions(False, False, 20, "Standard")), r)
    assert not c.is_satisfied(offer_factory(fare=FareConditions(False, False, 19, "Basic")), r)


def test_flexibility_only_active_when_required(offer_factory, req):
    c = FlexibilityConstraint()
    assert not c.is_active(req)
    r = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50, require_changeable=True)
    assert c.is_active(r)
    assert c.is_satisfied(offer_factory(fare=FareConditions(True, False, 10, "Standard")), r)
    assert not c.is_satisfied(offer_factory(), r)


def test_every_constraint_has_reason_and_requirement_text():
    full = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50, max_transfers=1,
                         require_changeable=True, min_luggage_kg=20, max_duration_minutes=390)
    constraints = default_constraints()
    assert len(constraints) == 8 and all(c.is_active(full) for c in constraints)
    for c in constraints:
        assert c.reason(full) and c.requirement(full)
    assert MaxDurationConstraint().reason(full) == "journey longer than 6 h 30 min"


# ------------------------------------------------------------ filter_offers
def mixed_offers(offer_factory):
    """One offer failing exactly one rule each, plus two good ones."""
    return [
        offer_factory(offer_id="OF-0001"),                                # passes
        offer_factory(offer_id="OF-0002", price=60.0),                    # budget
        offer_factory(offer_id="OF-0003", destination="Granada"),         # destination
        offer_factory(offer_id="OF-0004", travel_date=date(2026, 7, 20),
                      arrival_date=date(2026, 7, 20)),                    # window
        offer_factory(offer_id="OF-0005", seats_available=0),             # seats
        offer_factory(offer_id="OF-0006", price=50.0),                    # passes (boundary)
    ]


def test_filter_keeps_good_offers_and_counts_reasons(offer_factory, req):
    result = filter_offers(mixed_offers(offer_factory), req)
    assert [o.offer_id for o in result.kept] == ["OF-0001", "OF-0006"]
    assert result.considered == 6
    assert result.removed_count == 4
    assert result.removed_by_reason["wrong destination (wanted Malaga)"] == 1
    assert result.removed_by_reason["over budget (max EUR 50.00)"] == 1
    assert len(result.kept) + result.removed_count == result.considered


def test_only_active_constraints_are_reported(offer_factory, req):
    result = filter_offers(mixed_offers(offer_factory), req)
    assert not any("transfers" in r or "changeable" in r or "luggage" in r
                   for r in result.removed_by_reason)


def test_zero_counts_are_listed_for_active_constraints(offer_factory, req):
    result = filter_offers([offer_factory()], req)
    assert result.removed_by_reason["no seats left"] == 0
    assert result.kept and result.removed_count == 0


def test_offer_failing_several_rules_is_counted_once_under_the_first(offer_factory, req):
    bad = offer_factory(destination="Granada", price=99.0, seats_available=0)
    result = filter_offers([bad], req)
    assert result.removed_count == 1
    assert result.removed_by_reason["wrong destination (wanted Malaga)"] == 1
    assert result.removed_by_reason["over budget (max EUR 50.00)"] == 0


def test_reason_order_follows_constraint_order(offer_factory, req):
    reasons = list(filter_offers([offer_factory()], req).removed_by_reason)
    assert reasons[0].startswith("wrong destination")
    assert reasons[1].startswith("departs outside")


def test_empty_input_list(req):
    result = filter_offers([], req)
    assert result.kept == [] and result.considered == 0
    assert result.report_lines() == ["No offers to filter."]


def test_no_survivors_gives_a_hint_from_near_misses(offer_factory, req):
    offers = [offer_factory(offer_id=f"OF-00{i}", price=60.0 + i) for i in range(10, 13)]
    offers.append(offer_factory(offer_id="OF-0099", destination="Granada"))
    result = filter_offers(offers, req)
    assert result.kept == []
    assert result.near_misses == {"over budget (max EUR 50.00)": 3,
                                  "wrong destination (wanted Malaga)": 1}
    text = "\n".join(result.report_lines())
    assert "No offer meets every hard constraint." in text
    assert "relaxing only 'over budget (max EUR 50.00)' would give 3 offer(s)" in text


def test_no_survivors_and_nothing_is_a_near_miss(offer_factory, req):
    both = offer_factory(price=99.0, destination="Granada")
    text = "\n".join(filter_offers([both], req).report_lines())
    assert "no single requirement is to blame" in text


def test_input_is_not_modified_and_order_is_kept(offer_factory, req):
    offers = mixed_offers(offer_factory)
    snapshot = list(offers)
    filter_offers(offers, req)
    assert offers == snapshot


def test_result_is_the_same_set_for_any_input_order(offer_factory, req):
    offers = mixed_offers(offer_factory)
    shuffled = offers[:]
    random.Random(1).shuffle(shuffled)
    a = {o.offer_id for o in filter_offers(offers, req).kept}
    b = {o.offer_id for o in filter_offers(shuffled, req).kept}
    assert a == b


def test_custom_constraint_list_is_respected(offer_factory, req):
    result = filter_offers(mixed_offers(offer_factory), req, [BudgetConstraint()])
    assert len(result.kept) == 5 and list(result.removed_by_reason) == ["over budget (max EUR 50.00)"]


def test_all_requirements_combined(offer_factory):
    r = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50, max_transfers=0,
                      require_changeable=True, min_luggage_kg=20, max_duration_minutes=400)
    good = offer_factory(transfers=0, fare=FareConditions(True, False, 20, "Standard"))
    bad_lug = offer_factory(transfers=0, fare=FareConditions(True, False, 10, "Standard"))
    result = filter_offers([good, bad_lug], r)
    assert result.kept == [good]
    assert result.removed_by_reason["luggage allowance below 20 kg"] == 1


# ------------------------------------------------------------ request validation
@pytest.mark.parametrize("changes, category", [
    ({"date_from": date(2026, 7, 15)}, "invalid_window"),
    ({"max_budget": 0}, "invalid_budget"),
    ({"max_budget": -5}, "invalid_budget"),
    ({"max_transfers": -1}, "invalid_transfers"),
    ({"max_duration_minutes": 0}, "invalid_duration_limit"),
    ({"min_luggage_kg": -1}, "invalid_luggage"),
])
def test_invalid_requests_are_rejected(req, changes, category):
    for key, value in changes.items():
        setattr(req, key, value)
    with pytest.raises(ValidationError) as info:
        validate_request(req)
    assert info.value.category == category
    with pytest.raises(ValidationError):
        filter_offers([], req)                       # filter_offers checks the request too


def test_unknown_destination_is_rejected_only_when_known_list_given(req):
    req.destination = "Atlantis"
    validate_request(req)                            # no list: fine
    with pytest.raises(ValidationError) as info:
        validate_request(req, {"Malaga"})
    assert info.value.category == "unknown_destination"


# ------------------------------------------------------------ hard / soft display
def test_hard_lines_only_list_active_constraints(req):
    lines = hard_constraint_lines(req)
    assert len(lines) == 4                           # destination, window, seats, budget
    assert any("price at most EUR 50.00" in l for l in lines)
    req.max_transfers, req.require_changeable = 1, True
    assert len(hard_constraint_lines(req)) == 6


def test_soft_lines_come_from_the_criteria_registry(req):
    lines = soft_preference_lines(req, {"price": 0.55, "duration": 0.15,
                                        "departure": 0.10, "flexibility": 0.20})
    assert any(l.startswith("price:") and "weight 0.55" in l for l in lines)
    assert any("preferred departure time: 09:00" in l for l in lines)
    assert len(lines) == 6


# ------------------------------------------------------------ real data (independent check)
@pytest.fixture(scope="module")
def real():
    comps = [c.name for c in load_companies()]
    dests = [d.name for d in load_destinations()]
    return load_offers("data/offers.csv", dests, comps).offers, load_companies(), load_destinations()


def test_spec_example_on_real_data_matches_independent_count(real):
    offers, _, _ = real
    r = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50.0,
                      max_transfers=1, require_changeable=True)
    result = filter_offers(offers, r)
    expected = [o for o in offers
                if o.destination == "Malaga" and date(2026, 7, 12) <= o.travel_date <= date(2026, 7, 14)
                and o.price <= 50 and o.transfers <= 1 and o.fare.changeable and o.seats_available >= 1]
    assert {o.offer_id for o in result.kept} == {o.offer_id for o in expected}
    assert len(result.kept) == 47
    assert {o.company for o in result.kept} == {"SolRuta", "Camino Express", "CostaLink",
                                                 "VerdeBus", "NocheVia"}
    assert len(result.kept) + result.removed_count == len(offers)


def test_every_kept_offer_satisfies_every_active_constraint(real):
    offers, _, _ = real
    r = TravelRequest("Barcelona", date(2026, 7, 11), date(2026, 7, 15), 45.0, max_transfers=0,
                      min_luggage_kg=20, max_duration_minutes=9 * 60)
    for o in filter_offers(offers, r).kept:
        assert o.destination == "Barcelona" and o.price <= 45 and o.transfers == 0
        assert o.fare.luggage_kg >= 20 and o.duration_minutes <= 540


def test_impossible_request_on_real_data_gives_no_offers_and_a_hint(real):
    offers, _, _ = real
    r = TravelRequest("Toledo", date(2026, 7, 12), date(2026, 7, 14), 3.0)      # cheapest is ~6.5
    result = filter_offers(offers, r)
    assert result.kept == []
    assert "Hint:" in "\n".join(result.report_lines())


def test_marketplace_filter_checks_destination_and_filters(real):
    offers, companies, destinations = real
    m = Marketplace(companies, destinations, offers, {})
    ok = m.filter(TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50.0))
    assert ok.kept
    with pytest.raises(ValidationError):
        m.filter(TravelRequest("Atlantis", date(2026, 7, 12), date(2026, 7, 14), 50.0))


# ------------------------------------------------------------ CLI
BASE = ["--destination", "Malaga", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "50"]


def test_cli_shows_hard_soft_split_and_counts(capsys):
    assert run(BASE + ["--max-transfers", "1", "--changeable"]) == 0
    out = capsys.readouterr().out
    assert "HARD constraints" in out and "SOFT preferences" in out
    assert "Remaining: 47 offers" in out
    assert "removed  1373   wrong destination (wanted Malaga)" in out
    assert "ticket must be changeable" in out


def test_cli_without_request_only_loads_data(capsys):
    assert run([]) == 0
    out = capsys.readouterr().out
    assert "1497 loaded, 0 rejected" in out and "HARD constraints" not in out


def test_cli_invalid_request_gives_clear_message_and_code_2(capsys):
    assert run(["--destination", "Atlantis", "--from", "2026-07-12", "--to", "2026-07-14",
                "--budget", "50"]) == 2
    assert "Invalid request: unknown destination" in capsys.readouterr().out
    assert run(["--destination", "Malaga", "--from", "2026-07-15", "--to", "2026-07-14",
                "--budget", "50"]) == 2
    assert run(BASE + ["--profile", "nobody"]) == 2


def test_cli_missing_arguments_exit_with_usage_error(capsys):
    with pytest.raises(SystemExit) as info:
        run(["--destination", "Malaga"])
    assert info.value.code == 2
    with pytest.raises(SystemExit):
        run(["--destination", "Malaga", "--from", "12/07/2026", "--to", "2026-07-14", "--budget", "50"])


def test_cli_no_result_shows_hint(capsys):
    assert run(["--destination", "Toledo", "--from", "2026-07-12", "--to", "2026-07-14",
                "--budget", "3"]) == 0
    out = capsys.readouterr().out
    assert "No offer meets every hard constraint." in out and "Hint:" in out


def test_cli_missing_data_file_gives_error_code_1(capsys):
    assert run(["--offers", "data/nope.csv"]) == 1
    assert "Error: File not found" in capsys.readouterr().out
