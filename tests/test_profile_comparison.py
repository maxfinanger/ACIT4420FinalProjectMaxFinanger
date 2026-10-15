"""Phase 6: comparing traveller profiles on the same request and offers."""
from datetime import date, time

import pytest

from busbidder.cli import run
from busbidder.comparison import winner_rank_matrix
from busbidder.exceptions import ValidationError
from busbidder.loader import (load_companies, load_destinations, load_offers, load_profiles,
                              load_scoring_config)
from busbidder.marketplace import Marketplace
from busbidder.models import TravelRequest
from busbidder.ranking import rank_offers
from busbidder.scoring_config import set_config
from scripts.compare_profiles import SPEC_REQUEST, build_report
from tests.test_ranking import SPEC, W, make


@pytest.fixture(scope="module")
def market():
    set_config(load_scoring_config())
    comps, dests = load_companies(), load_destinations()
    offers = load_offers("data/offers.csv", [d.name for d in dests], [c.name for c in comps]).offers
    return Marketplace(comps, dests, offers, load_profiles())


@pytest.fixture
def request_(market):
    set_config(load_scoring_config())
    return TravelRequest(**SPEC_REQUEST, profile="(compare)")


# ------------------------------------------------------------ Marketplace.compare_profiles
def test_same_filtered_offers_are_ranked_for_every_profile(market, request_):
    filtered, rankings = market.compare_profiles(request_)
    assert list(rankings) == list(market.profiles) and len(rankings) == 4
    ids = {o.offer_id for o in filtered.kept}
    assert len(ids) == 47
    for ranked in rankings.values():
        assert {r.offer.offer_id for r in ranked} == ids


def test_at_least_three_different_winners_on_the_spec_request(market, request_):
    _, rankings = market.compare_profiles(request_)
    winners = {ranked[0].offer.offer_id for ranked in rankings.values()}
    companies = {ranked[0].offer.company for ranked in rankings.values()}
    assert len(winners) >= 3 and len(companies) >= 3
    assert {n: r[0].offer.offer_id for n, r in rankings.items()} == {
        "budget_traveller": "OF-1025", "business_traveller": "OF-1032",
        "flexible_tourist": "OF-0725", "environment_focused": "OF-1030"}


def test_subset_of_profiles_and_unknown_profile(market, request_):
    _, rankings = market.compare_profiles(request_, ["business_traveller", "budget_traveller"])
    assert list(rankings) == ["business_traveller", "budget_traveller"]
    with pytest.raises(ValidationError) as info:
        market.compare_profiles(request_, ["budget_traveller", "nobody"])
    assert info.value.category == "unknown_profile"


def test_comparison_does_not_depend_on_the_profile_named_in_the_request(market):
    a = TravelRequest(**SPEC_REQUEST, profile="budget_traveller")
    b = TravelRequest(**SPEC_REQUEST, profile="(compare)")
    ra = {n: [r.offer.offer_id for r in v] for n, v in market.compare_profiles(a)[1].items()}
    rb = {n: [r.offer.offer_id for r in v] for n, v in market.compare_profiles(b)[1].items()}
    assert ra == rb


def test_no_survivors_gives_empty_rankings(market):
    req = TravelRequest("Toledo", date(2026, 7, 12), date(2026, 7, 14), 3.0)
    filtered, rankings = market.compare_profiles(req)
    assert filtered.kept == [] and all(v == [] for v in rankings.values())


# ------------------------------------------------------------ winner_rank_matrix
def test_rank_matrix_diagonal_is_one_and_ranks_are_consistent(market, request_):
    _, rankings = market.compare_profiles(request_)
    matrix = winner_rank_matrix(rankings)
    assert len(matrix) == 4
    for winner, ranks in matrix:
        own = [n for n, r in rankings.items() if r[0].offer.offer_id == winner.offer.offer_id]
        assert all(ranks[n] == 1 for n in own)
        assert all(1 <= ranks[n] <= 47 for n in ranks)


def test_rank_matrix_has_one_row_per_distinct_winner():
    req = TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50.0, preferred_departure=time(9, 0))
    offers = [make("OF-000A", 30, 360, time(9, 0), False, False),
              make("OF-000B", 35, 390, time(10, 30), True, False),
              make("OF-000C", 40, 420, time(12, 0), True, True)]
    cheap = {"price": 0.4, "duration": 0.25, "departure": 0.15, "flexibility": 0.2}
    cheap_too = {"price": 0.5, "duration": 0.2, "departure": 0.2, "flexibility": 0.1}
    flex = {"price": 0.1, "duration": 0.1, "departure": 0.1, "flexibility": 0.7}
    rankings = {n: rank_offers(offers, req, w) for n, w in
                {"a": cheap, "b": cheap_too, "c": flex}.items()}
    matrix = winner_rank_matrix(rankings)
    assert [w.offer.offer_id for w, _ in matrix] == ["OF-000A", "OF-000C"]
    assert matrix[0][1] == {"a": 1, "b": 1, "c": 3}
    assert matrix[1][1] == {"a": 3, "b": 3, "c": 1}


def test_rank_matrix_of_empty_rankings_is_empty():
    assert winner_rank_matrix({"a": [], "b": []}) == [] and winner_rank_matrix({}) == []


# ------------------------------------------------------------ generated document
def test_committed_profile_comparison_matches_the_script():
    # If this fails: run  python scripts/compare_profiles.py  and commit the new file.
    text = open("docs/profile_comparison.md", encoding="utf-8").read()
    assert text == build_report()


def test_report_is_reproducible_and_complete():
    a, b = build_report(), build_report()
    assert a == b
    for name in ("budget_traveller", "business_traveller", "flexible_tourist", "environment_focused"):
        assert f"### {name}" in a
    for part in ("## The request", "## The profiles", "### How each winner ranks",
                 "Explanation generated for the top offer", "## Variation", "## How to read this"):
        assert part in a
    assert "objectively" not in a.lower()
    assert "4 different offers win, from 4 different companies" in a


# ------------------------------------------------------------ CLI
BASE = ["--destination", "Malaga", "--from", "2026-07-12", "--to", "2026-07-14", "--budget", "50",
        "--max-transfers", "1", "--changeable"]


def test_cli_recommendation_has_advantages_drawbacks_and_caveat(capsys):
    assert run(BASE) == 0
    out = capsys.readouterr().out
    assert "RECOMMENDATION" in out and "Advantages:" in out and "Drawbacks:" in out
    assert "only under your hard requirements" in out
    assert "objectively" not in out.lower()


def test_cli_compare_profiles(capsys):
    assert run(BASE + ["--compare-profiles"]) == 0
    out = capsys.readouterr().out
    assert "PROFILE COMPARISON: the same 47 offers" in out
    assert "Rank of each winner under every profile" in out
    assert "4 different winners from 4 company/companies" in out
    for name in ("budget_traveller", "business_traveller", "flexible_tourist", "environment_focused"):
        assert name in out
    assert "RECOMMENDATION" not in out


def test_cli_compare_with_one_offer_says_all_profiles_agree(capsys):
    args = ["--destination", "Zaragoza", "--from", "2026-07-12", "--to", "2026-07-12", "--budget", "25",
            "--max-transfers", "0", "--changeable"]
    assert run(args + ["--compare-profiles"]) == 0
    assert "All profiles recommend the same offer" in capsys.readouterr().out
    assert run(args) == 0
    out = capsys.readouterr().out
    assert "only offer that meets the hard requirements" in out and "1 acceptable offer)" in out


def test_cli_compare_with_no_result_shows_filter_report_only(capsys):
    assert run(["--destination", "Toledo", "--from", "2026-07-12", "--to", "2026-07-14",
                "--budget", "3", "--compare-profiles"]) == 0
    out = capsys.readouterr().out
    assert "No offer meets every hard constraint." in out and "PROFILE COMPARISON" not in out


def test_cli_custom_weights_explanation_names_own_weights(capsys):
    assert run(BASE + ["--weights", "price=60,duration=40"]) == 0
    assert "your own weights" in capsys.readouterr().out
