"""Phase 6: the generated explanation."""
from datetime import date, time

import pytest

from busbidder import criteria
from busbidder.explain import (ADVANTAGE_MIN_SCORE, DISADVANTAGE_MAX_SCORE, describe_criterion,
                               explain_top_offer, format_minutes)
from busbidder.filtering import filter_offers
from busbidder.loader import (load_companies, load_destinations, load_offers, load_profiles,
                              load_scoring_config)
from busbidder.models import FareConditions, TravelRequest
from busbidder.ranking import rank_offers
from busbidder.scoring_config import set_config
from tests.test_ranking import SPEC, W, make


@pytest.fixture
def request_():
    return TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50.0,
                         preferred_departure=time(9, 0), profile="budget_traveller")


@pytest.fixture
def abc():
    return [make("OF-000A", 30, 360, time(9, 0), False, False),
            make("OF-000B", 35, 390, time(10, 30), True, False),
            make("OF-000C", 40, 420, time(12, 0), True, True)]


def explain(offers, request, weights):
    return explain_top_offer(rank_offers(offers, request, weights), request, weights)


# ------------------------------------------------------------ hand-checked content
def test_headline_names_offer_company_price_score_and_profile(abc, request_):
    e = explain(abc, request_, W)
    assert "OF-000A (SolRuta)" in e.headline and "EUR 30.00" in e.headline
    assert "ranked first with 80.0 out of 100" in e.headline
    assert "'budget_traveller' profile" in e.headline


def test_advantages_are_the_three_strongest_by_weighted_contribution(abc, request_):
    e = explain(abc, request_, W)
    assert [a.split(":")[0] for a in e.advantages] == ["price", "duration", "departure"]
    assert "the lowest of the 3 acceptable offers" in e.advantages[0]
    assert "the shortest journey on offer" in e.advantages[1]
    assert "exactly at the preferred time" in e.advantages[2]


def test_drawback_is_the_weak_criterion(abc, request_):
    e = explain(abc, request_, W)
    assert e.disadvantages == ["flexibility: a fixed fare (not changeable, not refundable) "
                               "(score 0 out of 100)"]


def test_comparison_with_runner_up_uses_weighted_points(abc, request_):
    e = explain(abc, request_, W)
    assert e.comparison.startswith("Compared with the runner-up OF-000B")
    assert "ahead on price (+20.0 points), duration (+12.5 points)" in e.comparison
    assert "behind on flexibility (-12.0 points)" in e.comparison


def test_text_has_all_parts_and_str_equals_text(abc, request_):
    e = explain(abc, request_, W)
    text = e.text()
    for part in ("Advantages:", "Drawbacks:", "Compared with the runner-up", "hard requirements"):
        assert part in text
    assert str(e) == text


# ------------------------------------------------------------ honesty rules
def test_never_claims_the_offer_is_objectively_best(abc, request_):
    text = explain(abc, request_, W).text().lower()
    assert "objectively" not in text and "the best offer" not in text
    assert "only under your hard requirements" in text
    assert "weights of the 'budget_traveller' profile (price 40%, duration 25%" in text
    assert "relative to the 3 acceptable offers" in text


def test_custom_weights_are_labelled_as_such(abc, request_):
    request_.profile = "(custom)"
    assert "your own weights" in explain(abc, request_, W).headline


def test_zero_weight_and_unweighted_criteria_are_not_mentioned(abc, request_):
    e = explain(abc, request_, {"price": 1.0, "duration": 0.0})
    text = e.text()
    assert "duration:" not in text and "rated" not in text and "flexibility" not in text.split("Compared")[0]


def test_always_at_least_one_drawback_line_on_real_data():
    set_config(load_scoring_config())
    comps, dests = load_companies(), load_destinations()
    offers = load_offers("data/offers.csv", [d.name for d in dests], [c.name for c in comps]).offers
    profiles = load_profiles()
    for name in profiles:
        req = TravelRequest(**SPEC, profile=name)
        ranked = rank_offers(filter_offers(offers, req).kept, req, profiles[name])
        e = explain_top_offer(ranked, req, profiles[name])
        assert e.advantages and e.disadvantages, name
        assert ranked[0].offer.offer_id in e.headline
        assert f"{ranked[0].total_score:.1f}" in e.headline


def test_no_drawback_when_the_top_offer_wins_every_criterion(request_):
    better = make("OF-0001", price=25, minutes=300)
    worse = make("OF-0002", price=35, minutes=400)
    e = explain([better, worse], request_, {"price": 0.5, "duration": 0.5})
    assert e.disadvantages == ["none found: it scores 100 on every weighted criterion compared "
                               "with the other acceptable offers"]


def test_weakest_point_is_named_when_nothing_is_below_the_drawback_threshold(request_):
    # duration is the top offer's weakest criterion (score 50), above the drawback threshold of 40
    a = make("OF-0001", price=30.0, minutes=390)
    b = make("OF-0002", price=32.0, minutes=360)
    e = explain([a, b], request_, {"price": 0.8, "duration": 0.2})
    assert e.disadvantages == ["weakest point is duration: 6h30, 0h30 longer than the fastest (6h00) "
                               "(score 50 out of 100)"]
    assert e.advantages[0].startswith("price:")


# ------------------------------------------------------------ thresholds (boundaries)
@pytest.fixture
def q_criterion(monkeypatch):
    """A criterion whose score is simply the offer's price, to control scores exactly."""
    monkeypatch.setattr(criteria, "_REGISTRY", dict(criteria._REGISTRY))
    criteria.register_criterion("q", "test criterion")(lambda offer, offers, request: offer.price)


def _two(top_q, other_q=10.0):
    return [make("OF-0001", price=top_q), make("OF-0002", price=other_q)]


@pytest.mark.parametrize("score, is_advantage", [
    (ADVANTAGE_MIN_SCORE, True), (ADVANTAGE_MIN_SCORE - 0.1, False)])
def test_advantage_threshold_boundary(q_criterion, request_, score, is_advantage):
    e = explain(_two(score), request_, {"q": 1.0})
    stands_out = any(a.startswith("q:") for a in e.advantages)
    assert stands_out is is_advantage
    if not is_advantage:
        assert "no single criterion stands out" in e.advantages[0]


@pytest.mark.parametrize("score, is_drawback", [
    (DISADVANTAGE_MAX_SCORE, True), (DISADVANTAGE_MAX_SCORE + 0.1, False)])
def test_drawback_threshold_boundary(q_criterion, request_, score, is_drawback):
    e = explain(_two(score, other_q=5.0), request_, {"q": 1.0})
    assert e.disadvantages[0].startswith("q:") is is_drawback
    assert (e.disadvantages[0].startswith("weakest point is q")) is (not is_drawback)


def test_criterion_without_its_own_sentence_gets_a_generic_one(q_criterion, request_):
    e = explain(_two(80.0), request_, {"q": 1.0})
    assert e.advantages == ["q: score 80 out of 100 on 'q'"]


# ------------------------------------------------------------ edge cases
def test_empty_ranking_says_there_is_nothing_to_recommend(request_):
    e = explain_top_offer([], request_, W)
    assert "nothing to recommend" in e.text()


def test_single_offer_is_not_compared_with_anything(request_):
    e = explain([make()], request_, W)
    assert "only offer that meets the hard requirements" in e.comparison
    assert e.advantages == [] and e.disadvantages == []
    assert "relative to the 1 acceptable offer)" in e.caveat


def test_tie_is_explained(request_):
    a = make("OF-0002", price=25, minutes=500)
    b = make("OF-0001", price=30, minutes=380)
    e = explain([b, a], request_, {"departure": 0.5, "flexibility": 0.5})
    assert e.tie_note == "It has the same score as OF-0001 to two decimals and is placed first because its price is lower."


def test_no_tie_note_without_a_tie(abc, request_):
    assert explain(abc, request_, W).tie_note is None


def test_direct_route_is_an_advantage_only_when_others_have_transfers(request_):
    direct, with_stop = make("OF-0001", price=30), make("OF-0002", price=40, transfers=1)
    w = {"price": 1.0}
    assert any("direct route, while 1 of the 2" in a for a in explain([direct, with_stop], request_, w).advantages)
    assert not any("direct" in a for a in explain([direct, make("OF-0003", price=40)], request_, w).advantages)


def test_transfers_are_a_drawback_when_others_are_direct(request_):
    cheap_with_stop = make("OF-0001", price=30, transfers=2)
    dear_direct = make("OF-0002", price=40)
    e = explain([cheap_with_stop, dear_direct], request_, {"price": 1.0})
    assert any("2 transfers, while 1 acceptable offers are direct" in d for d in e.disadvantages)


def test_transfers_are_not_added_twice_when_they_are_weighted(request_):
    direct, with_stop = make("OF-0001", price=30), make("OF-0002", price=40, transfers=1)
    e = explain([direct, with_stop], request_, {"price": 0.5, "transfers": 0.5})
    assert sum("direct route" in a for a in e.advantages) == 1


def test_missing_emissions_figure_is_called_out(request_):
    a = make("OF-0001", price=30, emissions=None)
    b = make("OF-0002", price=40, emissions=12.0)
    e = explain([a, b], request_, {"price": 0.5, "emissions": 0.5})
    assert any("no emissions figure reported" in d for d in e.disadvantages)


# ------------------------------------------------------------ the sentences
def test_describe_price_and_duration(request_):
    offers = [make("OF-0001", price=30, minutes=360), make("OF-0002", price=30, minutes=480),
              make("OF-0003", price=36.5, minutes=500)]
    assert "the joint lowest of the 3" in describe_criterion("price", offers[0], offers, request_, 100)
    assert "EUR 6.50 above the cheapest (EUR 30.00)" in describe_criterion("price", offers[2], offers, request_, 0)
    assert "2h20 longer than the fastest (6h00)" in describe_criterion("duration", offers[2], offers, request_, 0)


def test_describe_departure_flexibility_transfers_rating_emissions(request_):
    o = make(dep=time(7, 0), changeable=True, refundable=True, transfers=1, rating=4.3, emissions=10.0)
    other = make("OF-0002", emissions=8.0)
    assert "departs 07:00, 120 min from the preferred 09:00" in describe_criterion("departure", o, [o], request_, 0)
    assert describe_criterion("flexibility", o, [o], request_, 0) == "a changeable and refundable fare"
    assert describe_criterion("transfers", o, [o], request_, 0) == "1 transfer"
    assert describe_criterion("rating", o, [o], request_, 0) == "rated 4.3 out of 5"
    assert "10.0 kg CO2 (lowest reported: 8.0 kg)" in describe_criterion("emissions", o, [o, other], request_, 0)


@pytest.mark.parametrize("changeable, refundable, text", [
    (True, False, "a changeable fare, but not refundable"),
    (False, True, "a refundable fare, but not changeable"),
    (False, False, "a fixed fare (not changeable, not refundable)")])
def test_describe_flexibility_variants(request_, changeable, refundable, text):
    o = make(changeable=changeable, refundable=refundable)
    assert describe_criterion("flexibility", o, [o], request_, 0) == text


def test_format_minutes():
    assert format_minutes(395) == "6h35" and format_minutes(60) == "1h00" and format_minutes(5) == "0h05"
