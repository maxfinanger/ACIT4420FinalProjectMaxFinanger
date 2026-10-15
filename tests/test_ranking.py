"""Phase 5: scoring criteria, weights, ranking, ties, influence, CLI output."""
import math
import random
from datetime import date, time, timedelta, datetime

import pytest

from busbidder import criteria
from busbidder.cli import run
from busbidder.criteria import (departure_score, duration_score, emissions_score,
                                flexibility_score, minutes_between, price_score,
                                rating_score, relative_lower_is_better, transfers_score)
from busbidder.exceptions import ScoringError, UnknownCriterionError, WeightError
from busbidder.filtering import filter_offers, soft_preference_lines
from busbidder.loader import (load_companies, load_destinations, load_offers, load_profiles,
                              load_scoring_config)
from busbidder.marketplace import Marketplace
from busbidder.exceptions import ValidationError
from busbidder.models import FareConditions, Offer, TravelRequest
from busbidder.ranking import influence_share, parse_weights, rank_offers, validate_weights
from busbidder.scoring_config import ScoringConfig, set_config

W = {"price": 0.40, "duration": 0.25, "departure": 0.15, "flexibility": 0.20}


def make(offer_id="OF-0001", price=30.0, minutes=360, dep=time(9, 0), changeable=False,
         refundable=False, transfers=0, rating=4.0, emissions=None, day=date(2026, 7, 12), seats=10):
    departure = datetime.combine(day, dep)
    arrival = departure + timedelta(minutes=minutes)
    return Offer(offer_id, "SolRuta", "Malaga", day, dep, arrival.date(), arrival.time(), price,
                 transfers, FareConditions(changeable, refundable, 20, "Standard"), seats,
                 rating, emissions)


@pytest.fixture
def request_():
    return TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50.0,
                         preferred_departure=time(9, 0))


@pytest.fixture
def abc():
    """The hand-calculated example from docs/scoring.md."""
    return [make("OF-000A", 30, 360, time(9, 0), False, False),
            make("OF-000B", 35, 390, time(10, 30), True, False),
            make("OF-000C", 40, 420, time(12, 0), True, True)]


# ---------------------------------------------------------------- hand-calculated
def test_hand_calculated_criterion_scores(abc, request_):
    ranked = {r.offer.offer_id: r for r in rank_offers(abc, request_, W)}
    expected = {"OF-000A": (100, 100, 100, 0), "OF-000B": (50, 50, 75, 60),
                "OF-000C": (0, 0, 50, 100)}
    for oid, values in expected.items():
        got = ranked[oid].criterion_scores
        assert [got[k] for k in W] == pytest.approx(values)


def test_hand_calculated_totals_and_order(abc, request_):
    ranked = rank_offers(abc, request_, W)
    assert [r.offer.offer_id for r in ranked] == ["OF-000A", "OF-000B", "OF-000C"]
    assert [r.total_score for r in ranked] == pytest.approx([80.0, 55.75, 27.5])
    assert [r.rank for r in ranked] == [1, 2, 3]


def test_same_offers_different_weights_give_a_different_winner(abc, request_):
    flex_heavy = {"price": 0.1, "duration": 0.1, "departure": 0.1, "flexibility": 0.7}
    ranked = rank_offers(abc, request_, flex_heavy)
    assert [r.offer.offer_id for r in ranked] == ["OF-000C", "OF-000B", "OF-000A"]
    assert [r.total_score for r in ranked] == pytest.approx([75.0, 59.5, 30.0])


def test_contributions_add_up_to_total_and_totals_stay_in_0_100(abc, request_):
    for r in rank_offers(abc, request_, W):
        assert sum(r.contributions.values()) == pytest.approx(r.total_score)
        assert 0 <= r.total_score <= 100
        assert r.contributions["price"] == pytest.approx(W["price"] * r.criterion_scores["price"])


# ---------------------------------------------------------------- relative scales
def test_identical_offers_do_not_divide_by_zero(request_):
    offers = [make(f"OF-000{i}") for i in range(1, 4)]
    for r in rank_offers(offers, request_, W):
        assert r.criterion_scores["price"] == 100 and r.criterion_scores["duration"] == 100


def test_single_offer_scores_100_on_relative_criteria(request_):
    (r,) = rank_offers([make()], request_, W)
    assert r.criterion_scores["price"] == 100 and r.criterion_scores["duration"] == 100
    assert r.rank == 1 and not r.tie_broken


def test_empty_list_gives_empty_ranking(request_):
    assert rank_offers([], request_, W) == []


def test_min_span_stops_tiny_differences_from_being_blown_up(request_):
    cheap, dear = make("OF-0001", price=30.0), make("OF-0002", price=31.0)
    assert price_score(cheap, [cheap, dear], request_) == 100
    assert price_score(dear, [cheap, dear], request_) == pytest.approx(80.0)   # 1 EUR of a 5 EUR span


def test_outlier_cannot_stretch_the_scale(request_):
    offers = [make(f"OF-000{i}", minutes=m) for i, m in enumerate([360, 420, 480, 1440], start=1)]
    got = [duration_score(o, offers, request_) for o in offers]
    assert got == pytest.approx([100, 88.8889, 77.7778, 0], abs=1e-3)
    # without the cap the same offers would have scored 100, 94.4, 88.9, 0


@pytest.mark.parametrize("value, expected", [(10, 100), (15, 50), (20, 0), (30, 0)])
def test_relative_helper_clamps_between_0_and_100(value, expected):
    assert relative_lower_is_better(value, [10, 15, 20], min_span=1, cap_factor=99) == expected


# ---------------------------------------------------------------- absolute scales
@pytest.mark.parametrize("pref, dep, expected", [
    (time(9, 0), time(9, 0), 100.0),
    (time(9, 0), time(10, 30), 75.0),
    (time(9, 0), time(15, 0), 0.0),            # exactly the tolerance away
    (time(9, 0), time(14, 59), 0.2778),        # one minute inside the tolerance
    (time(9, 0), time(21, 0), 0.0),            # 12 h apart
    (time(0, 30), time(23, 55), 90.2778),      # 35 min apart, across midnight
    (time(23, 0), time(3, 0), 33.3333),        # 4 h apart, across midnight
])
def test_departure_score(request_, pref, dep, expected):
    request_.preferred_departure = pref
    assert departure_score(make(dep=dep), [], request_) == pytest.approx(expected, abs=1e-3)


def test_minutes_between_is_symmetric_and_circular():
    assert minutes_between(time(0, 30), time(23, 55)) == minutes_between(time(23, 55), time(0, 30)) == 35
    assert minutes_between(time(9, 0), time(21, 0)) == 720


def test_flexibility_levels(request_):
    levels = {(False, False): 0, (True, False): 60, (False, True): 40, (True, True): 100}
    for (ch, rf), expected in levels.items():
        assert flexibility_score(make(changeable=ch, refundable=rf), [], request_) == expected


@pytest.mark.parametrize("transfers, expected", [(0, 100), (1, 66.6667), (2, 33.3333), (3, 0), (5, 0)])
def test_transfers_score(request_, transfers, expected):
    assert transfers_score(make(transfers=transfers), [], request_) == pytest.approx(expected, abs=1e-3)


@pytest.mark.parametrize("rating, expected", [(5.0, 100), (4.0, 80), (0.0, 0)])
def test_rating_score(request_, rating, expected):
    assert rating_score(make(rating=rating), [], request_) == pytest.approx(expected)


# ---------------------------------------------------------------- missing values
def test_missing_emissions_get_the_missing_value_score(request_):
    # reported values 10, 11, 14 -> span 4 kg: 11 is 1/4 of the way down = 75, 14 is the worst = 0
    offers = [make("OF-0001", emissions=10.0), make("OF-0002", emissions=None),
              make("OF-0003", emissions=11.0), make("OF-0004", emissions=14.0)]
    got = [emissions_score(o, offers, request_) for o in offers]
    assert got == pytest.approx([100, 0, 75, 0])


def test_missing_value_score_is_configurable(request_):
    set_config(ScoringConfig(missing_value_score=50.0))
    offers = [make("OF-0001", emissions=10.0), make("OF-0002", emissions=None)]
    assert emissions_score(offers[1], offers, request_) == 50.0


def test_nobody_reports_emissions_does_not_crash(request_):
    offers = [make("OF-0001"), make("OF-0002")]
    ranked = rank_offers(offers, request_, {"emissions": 0.5, "price": 0.5})
    assert all(r.criterion_scores["emissions"] == 0 for r in ranked)


# ---------------------------------------------------------------- ties
TIE_W = {"departure": 0.5, "flexibility": 0.5}      # price and duration do not count here


def test_tie_is_broken_by_price_then_duration_then_departure_then_id(request_):
    a = make("OF-0004", price=30, minutes=400)
    b = make("OF-0003", price=30, minutes=380)       # same price, shorter
    c = make("OF-0002", price=25, minutes=500)       # cheapest -> first
    d = make("OF-0001", price=30, minutes=380)       # same as b, lower id
    ranked = rank_offers([a, b, c, d], request_, TIE_W)
    assert [r.offer.offer_id for r in ranked] == ["OF-0002", "OF-0001", "OF-0003", "OF-0004"]
    assert [r.rank for r in ranked] == [1, 2, 3, 4]
    assert all(r.tie_broken for r in ranked)


def test_tie_broken_flag_is_false_without_a_tie(abc, request_):
    assert not any(r.tie_broken for r in rank_offers(abc, request_, W))


def test_tie_break_by_departure_time_when_everything_else_is_equal(request_):
    early = make("OF-0009", dep=time(9, 0), day=date(2026, 7, 12))
    late = make("OF-0001", dep=time(9, 0), day=date(2026, 7, 13))
    ranked = rank_offers([late, early], request_, TIE_W)
    assert [r.offer.offer_id for r in ranked] == ["OF-0009", "OF-0001"]


# ---------------------------------------------------------------- reproducibility
def test_ranking_is_reproducible_and_independent_of_input_order(abc, request_):
    first = [r.offer.offer_id for r in rank_offers(abc, request_, W)]
    shuffled = abc[:]
    random.Random(3).shuffle(shuffled)
    assert [r.offer.offer_id for r in rank_offers(shuffled, request_, W)] == first
    assert [r.offer.offer_id for r in rank_offers(abc, request_, W)] == first


def test_input_list_is_not_modified(abc, request_):
    before = list(abc)
    rank_offers(abc, request_, W)
    assert abc == before


# ---------------------------------------------------------------- known limitation
def test_rank_reversal_is_possible_known_limitation(request_):
    """Relative scales depend on which offers are in the list: removing the LAST offer can
    swap two others. Documented in docs/scoring.md (D15) and discussed in the report."""
    def o(i, price, minutes, hour, ch, rf):
        return make(f"OF-000{i}", price, minutes, time(hour, 0), ch, rf)
    offers = [o(1, 20, 540, 9, True, True), o(2, 35, 330, 7, True, False),
              o(3, 25, 330, 7, False, True), o(4, 25, 330, 9, True, False)]
    with_all = [r.offer.offer_id for r in rank_offers(offers, request_, W)]
    without_2 = [r.offer.offer_id for r in rank_offers([offers[0], offers[2], offers[3]], request_, W)]
    assert with_all == ["OF-0004", "OF-0001", "OF-0003", "OF-0002"]
    assert without_2 == ["OF-0001", "OF-0004", "OF-0003"]      # 1 and 4 swapped


def test_absolute_criteria_do_not_depend_on_other_offers(request_):
    only = make(changeable=True, dep=time(10, 0))
    others = [make("OF-0002", price=10), make("OF-0003", price=45, minutes=900)]
    for fn in (departure_score, flexibility_score, transfers_score, rating_score):
        assert fn(only, [only], request_) == fn(only, [only] + others, request_)


# ---------------------------------------------------------------- weights
@pytest.mark.parametrize("weights, error", [
    ({}, WeightError),
    ({"price": 0.5, "duration": 0.2}, WeightError),                 # sums to 0.7
    ({"price": 1.5, "duration": -0.5}, WeightError),                # negative
    ({"price": float("nan"), "duration": 1.0}, WeightError),
    ({"price": True, "duration": 0.0}, WeightError),
    ({"price": "0.5", "duration": 0.5}, WeightError),
    ({"price": 0.5, "comfort": 0.5}, UnknownCriterionError),
])
def test_invalid_weights_are_rejected_by_validate_and_rank(request_, weights, error):
    with pytest.raises(error):
        validate_weights(weights)
    with pytest.raises(error):
        rank_offers([make()], request_, weights)


def test_floating_point_sums_are_tolerated():
    validate_weights({"price": 0.1, "duration": 0.2, "departure": 0.7})      # 0.1+0.2+0.7 != 1.0 exactly


def test_zero_weight_is_allowed(abc, request_):
    ranked = rank_offers(abc, request_, {"price": 1.0, "duration": 0.0})
    assert ranked[0].criterion_scores["duration"] == 100 and ranked[0].contributions["duration"] == 0


@pytest.mark.parametrize("text, expected", [
    ("price=40,duration=25,departure=15,flexibility=20", W),
    ("price=0.4, duration=0.25, departure=0.15, flexibility=0.2", W),
    (" price = 60 , duration = 40 ", {"price": 0.6, "duration": 0.4}),
])
def test_parse_weights_accepts_percent_and_fractions(text, expected):
    assert parse_weights(text) == pytest.approx(expected)


@pytest.mark.parametrize("text, error", [
    ("price=50,duration=20", WeightError),          # 70
    ("price", WeightError), ("=50", WeightError), ("price=abc,duration=1", WeightError),
    ("price=50,price=50", WeightError), ("", WeightError),
    ("price=50,comfort=50", UnknownCriterionError),
    ("price=-50,duration=150", WeightError),
])
def test_parse_weights_errors(text, error):
    with pytest.raises(error):
        parse_weights(text)


# ---------------------------------------------------------------- extensibility
def test_new_criterion_works_without_changing_the_ranker(monkeypatch, request_):
    monkeypatch.setattr(criteria, "_REGISTRY", dict(criteria._REGISTRY))

    @criteria.register_criterion("luggage", "More luggage is better")
    def luggage_score(offer, offers, request):
        return min(100.0, offer.fare.luggage_kg * 4)

    light = make("OF-0001")
    heavy = make("OF-0002")
    heavy.fare = FareConditions(False, False, 25, "Flex")
    ranked = rank_offers([light, heavy], request_, {"luggage": 1.0})
    assert [r.offer.offer_id for r in ranked] == ["OF-0002", "OF-0001"]
    assert ranked[0].criterion_scores["luggage"] == 100


def test_criterion_returning_a_bad_score_raises_scoring_error(monkeypatch, request_):
    monkeypatch.setattr(criteria, "_REGISTRY", dict(criteria._REGISTRY))
    criteria.register_criterion("broken")(lambda offer, offers, request: 150.0)
    with pytest.raises(ScoringError, match="broken"):
        rank_offers([make()], request_, {"broken": 1.0})
    monkeypatch.setitem(criteria._REGISTRY, "broken",
                        criteria.Criterion("broken", "", lambda o, os, r: float("nan")))
    with pytest.raises(ScoringError):
        rank_offers([make()], request_, {"broken": 1.0})


# ---------------------------------------------------------------- influence
def test_influence_shares_add_up_to_one(abc, request_):
    ranked = rank_offers(abc, request_, W)
    shares = influence_share(ranked, W)
    assert sum(shares.values()) == pytest.approx(1.0)
    assert all(v >= 0 for v in shares.values())


def test_high_weight_without_spread_has_no_influence(request_):
    offers = [make("OF-0001", price=30, minutes=360), make("OF-0002", price=30, minutes=420)]
    ranked = rank_offers(offers, request_, {"price": 0.9, "duration": 0.1})
    shares = influence_share(ranked, {"price": 0.9, "duration": 0.1})
    assert shares["price"] == 0 and shares["duration"] == pytest.approx(1.0)


def test_influence_for_one_offer_or_no_spread_is_zero(request_):
    one = rank_offers([make()], request_, W)
    assert influence_share(one, W) == {k: 0.0 for k in W}
    same = rank_offers([make("OF-0001"), make("OF-0002")], request_, W)
    assert influence_share(same, W) == {k: 0.0 for k in W}


# ---------------------------------------------------------------- soft lines
def test_soft_lines_without_weights_list_every_registered_criterion(request_):
    lines = soft_preference_lines(request_)
    assert len(lines) == len(criteria.registered_names()) + 2


# ---------------------------------------------------------------- real data
@pytest.fixture(scope="module")
def real():
    set_config(load_scoring_config())
    comps, dests = load_companies(), load_destinations()
    offers = load_offers("data/offers.csv", [d.name for d in dests], [c.name for c in comps]).offers
    return offers, comps, dests, load_profiles()


SPEC = dict(destination="Malaga", date_from=date(2026, 7, 12), date_to=date(2026, 7, 14),
            max_budget=50.0, max_transfers=1, require_changeable=True)


@pytest.mark.parametrize("profile, preferred, expected_top, company", [
    ("budget_traveller", time(9, 0), "OF-1025", "SolRuta"),
    ("business_traveller", time(8, 0), "OF-1032", "Camino Express"),
    ("flexible_tourist", time(10, 0), "OF-0730", "CostaLink"),
    ("environment_focused", time(9, 0), "OF-1030", "VerdeBus"),
])
def test_spec_example_winners_per_profile_are_stable(real, profile, preferred, expected_top, company):
    offers, _, _, profiles = real
    set_config(load_scoring_config())
    req = TravelRequest(**SPEC, preferred_departure=preferred, profile=profile)
    ranked = rank_offers(filter_offers(offers, req).kept, req, profiles[profile])
    assert len(ranked) == 47
    assert (ranked[0].offer.offer_id, ranked[0].offer.company) == (expected_top, company)


def test_profiles_give_different_recommendations_on_the_same_offers(real):
    offers, _, _, profiles = real
    set_config(load_scoring_config())
    tops = set()
    for name, pref in [("budget_traveller", time(9, 0)), ("business_traveller", time(8, 0)),
                       ("flexible_tourist", time(10, 0)), ("environment_focused", time(9, 0))]:
        req = TravelRequest(**SPEC, preferred_departure=pref, profile=name)
        tops.add(rank_offers(filter_offers(offers, req).kept, req, profiles[name])[0].offer.offer_id)
    assert len(tops) == 4


def test_real_ranking_is_complete_ordered_and_reproducible(real):
    offers, _, _, profiles = real
    set_config(load_scoring_config())
    req = TravelRequest(**SPEC, profile="budget_traveller")
    kept = filter_offers(offers, req).kept
    a = rank_offers(kept, req, profiles["budget_traveller"])
    b = rank_offers(list(reversed(kept)), req, profiles["budget_traveller"])
    assert [r.offer.offer_id for r in a] == [r.offer.offer_id for r in b]
    assert [r.rank for r in a] == list(range(1, 48))
    totals = [round(r.total_score, 2) for r in a]
    assert totals == sorted(totals, reverse=True)
    assert all(0 <= r.total_score <= 100 and math.isfinite(r.total_score) for r in a)


def test_environment_profile_prefers_low_emission_company(real):
    offers, _, _, profiles = real
    set_config(load_scoring_config())
    req = TravelRequest(**SPEC, profile="environment_focused")
    ranked = rank_offers(filter_offers(offers, req).kept, req, profiles["environment_focused"])
    assert sum(r.offer.company == "VerdeBus" for r in ranked[:5]) >= 3


def test_marketplace_search_filters_then_ranks_and_checks_profile(real):
    offers, comps, dests, profiles = real
    set_config(load_scoring_config())
    m = Marketplace(comps, dests, offers, profiles)
    result, ranked = m.search(TravelRequest(**SPEC, profile="budget_traveller"))
    assert len(ranked) == len(result.kept) == 47
    with pytest.raises(ValidationError) as info:
        m.search(TravelRequest(**SPEC, profile="nobody"))
    assert info.value.category == "unknown_profile"


# ---------------------------------------------------------------- CLI
BASE = ["--destination", "Malaga", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "50",
        "--max-transfers", "1", "--changeable"]


def test_cli_shows_ranking_with_criterion_scores_and_influence(capsys):
    assert run(BASE) == 0
    out = capsys.readouterr().out
    assert "RANKING (47 offers" in out
    assert "OF-1025" in out and "76.8" in out
    assert "Weight vs. real influence" in out and "influence" in out


def test_cli_top_limits_the_table(capsys):
    assert run(BASE + ["--top", "3"]) == 0
    out = capsys.readouterr().out
    assert "44 more offers not shown" in out


def test_cli_custom_weights_in_percent(capsys):
    assert run(BASE + ["--weights", "price=10,duration=10,departure=10,flexibility=70"]) == 0
    out = capsys.readouterr().out
    assert "custom weights" in out and "weight  70%" in out


def test_cli_environment_profile_shows_emissions_column(capsys):
    assert run(BASE + ["--profile", "environment_focused"]) == 0
    assert "emissi" in capsys.readouterr().out


@pytest.mark.parametrize("weights", ["price=50,duration=20", "price=50,comfort=50", "price"])
def test_cli_bad_weights_give_clear_message_and_code_2(capsys, weights):
    assert run(BASE + ["--weights", weights]) == 2
    assert "Invalid request:" in capsys.readouterr().out


def test_cli_missing_scoring_file_is_a_data_file_error(capsys, monkeypatch):
    import busbidder.cli as cli
    monkeypatch.setattr(cli, "load_scoring_config", lambda: load_scoring_config("config/nope.json"))
    assert run(BASE) == 1
    assert "Error: File not found" in capsys.readouterr().out
