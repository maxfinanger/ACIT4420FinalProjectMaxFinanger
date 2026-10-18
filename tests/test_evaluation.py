"""Phase 9 building blocks: weight experiments, correlations, and the split of rank_offers."""
import random
from datetime import date, time

import pytest

from busbidder.evaluation import (ScoredSet, inversions, order_of, perturb_weights, random_simplex,
                                  rank_in, rescale_weights, spearman, winner_interval)
from busbidder.models import TravelRequest
from busbidder.ranking import assemble_ranking, compute_scores, rank_offers
from tests.test_ranking import W, make


@pytest.fixture
def request_():
    return TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), 50.0,
                         preferred_departure=time(9, 0))


@pytest.fixture
def abc():
    return [make("OF-000A", 30, 360, time(9, 0), False, False),
            make("OF-000B", 35, 390, time(10, 30), True, False),
            make("OF-000C", 40, 420, time(12, 0), True, True)]


# ------------------------------------------------------------ the split of rank_offers
def test_assemble_from_precomputed_scores_equals_rank_offers(abc, request_):
    direct = rank_offers(abc, request_, W)
    scores = compute_scores(abc, request_, list(W))
    via = assemble_ranking(abc, scores, W)
    assert [(r.offer.offer_id, r.rank, r.total_score, r.criterion_scores) for r in direct] == \
           [(r.offer.offer_id, r.rank, r.total_score, r.criterion_scores) for r in via]


def test_scores_do_not_depend_on_the_weights_so_one_set_serves_many_weightings(abc, request_):
    scores = compute_scores(abc, request_, list(W))
    for weights in (W, {"price": 1.0, "duration": 0.0, "departure": 0.0, "flexibility": 0.0},
                    {"price": 0.1, "duration": 0.1, "departure": 0.1, "flexibility": 0.7}):
        assert order_of(assemble_ranking(abc, scores, weights)) == order_of(rank_offers(abc, request_, weights))


def test_assemble_uses_only_the_weighted_criteria(abc, request_):
    scores = compute_scores(abc, request_, ["price", "duration", "departure", "flexibility", "rating"])
    ranked = assemble_ranking(abc, scores, {"price": 1.0})
    assert set(ranked[0].criterion_scores) == {"price"}


def test_scored_set_rejects_a_criterion_that_was_not_scored(abc, request_):
    with pytest.raises(KeyError):
        ScoredSet(abc, request_, ["price"]).rank({"price": 0.5, "duration": 0.5})


# ------------------------------------------------------------ rescale_weights
def test_rescale_keeps_the_total_and_the_proportions_of_the_others():
    out = rescale_weights(W, "price", 0.6)
    assert sum(out.values()) == pytest.approx(1.0) and out["price"] == 0.6
    assert out["duration"] / out["departure"] == pytest.approx(W["duration"] / W["departure"])
    assert out["flexibility"] / out["duration"] == pytest.approx(W["flexibility"] / W["duration"])


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_rescale_extremes(value):
    out = rescale_weights(W, "duration", value)
    assert sum(out.values()) == pytest.approx(1.0)
    assert out["duration"] == value
    if value == 1.0:
        assert all(w == 0 for n, w in out.items() if n != "duration")


def test_rescale_when_the_others_are_all_zero_shares_equally():
    out = rescale_weights({"price": 1.0, "duration": 0.0, "departure": 0.0}, "price", 0.4)
    assert out == {"price": 0.4, "duration": 0.3, "departure": 0.3}


def test_rescale_errors():
    with pytest.raises(KeyError):
        rescale_weights(W, "comfort", 0.5)
    for bad in (-0.1, 1.1):
        with pytest.raises(ValueError):
            rescale_weights(W, "price", bad)


# ------------------------------------------------------------ winner_interval
def test_winner_interval_matches_the_hand_calculation(abc, request_):
    # docs/scoring.md example: A beats B until the flexibility weight reaches 0.4303 (derived by hand)
    lo, hi = winner_interval(ScoredSet(abc, request_, list(W)), W, "flexibility")
    assert (lo, hi) == (0.0, 0.43)


def test_the_baseline_weight_is_always_inside_its_interval(abc, request_):
    sset = ScoredSet(abc, request_, list(W))
    for criterion in W:
        lo, hi = winner_interval(sset, W, criterion)
        assert lo <= W[criterion] <= hi


def test_just_outside_the_interval_the_winner_changes(abc, request_):
    sset = ScoredSet(abc, request_, list(W))
    baseline = order_of(sset.rank(W))[0]
    lo, hi = winner_interval(sset, W, "flexibility")
    assert order_of(sset.rank(rescale_weights(W, "flexibility", hi)))[0] == baseline
    assert order_of(sset.rank(rescale_weights(W, "flexibility", hi + 0.005)))[0] != baseline


def test_a_winner_that_never_changes_has_the_full_interval(request_):
    best = make("OF-0001", price=20, minutes=300, changeable=True, refundable=True)
    worse = make("OF-0002", price=40, minutes=400)
    sset = ScoredSet([best, worse], request_, list(W))
    assert winner_interval(sset, W, "price") == (0.0, 1.0)


# ------------------------------------------------------------ random weights
def test_random_simplex_is_valid_and_reproducible():
    names = list(W)
    a = random_simplex(random.Random(1), names)
    assert sum(a.values()) == pytest.approx(1.0) and all(v >= 0 for v in a.values())
    assert a == random_simplex(random.Random(1), names) and a != random_simplex(random.Random(2), names)


def test_random_simplex_covers_the_whole_range():
    rng = random.Random(0)
    samples = [random_simplex(rng, ["a", "b", "c", "d"]) for _ in range(2000)]
    for name in "abcd":
        values = [s[name] for s in samples]
        assert min(values) < 0.02 and max(values) > 0.7
        assert sum(values) / len(values) == pytest.approx(0.25, abs=0.02)


def test_perturbed_weights_stay_valid_close_and_zero_stays_zero():
    rng = random.Random(3)
    base = {"price": 0.5, "duration": 0.5, "flexibility": 0.0}
    for _ in range(200):
        out = perturb_weights(rng, base, 0.3)
        assert sum(out.values()) == pytest.approx(1.0) and out["flexibility"] == 0.0
        assert 0.5 * 0.7 / 1.3 - 1e-9 <= out["price"] <= 0.5 * 1.3 / 0.7 + 1e-9
    assert perturb_weights(random.Random(3), base, 0.0) == pytest.approx(base)


# ------------------------------------------------------------ comparing orderings
def test_spearman_values():
    a = list("abcde")
    assert spearman(a, a) == 1.0
    assert spearman(a, a[::-1]) == -1.0
    assert spearman(list("abcd"), list("abdc")) == pytest.approx(0.8)
    assert spearman(["x"], ["x"]) == 1.0
    with pytest.raises(ValueError):
        spearman(["a", "b"], ["a", "c"])


def test_inversions_count_pairs_in_a_different_order():
    assert inversions(list("abc"), list("abc")) == 0
    assert inversions(list("abc"), list("cba")) == 3
    assert inversions(list("abcd"), list("abdc")) == 1
    with pytest.raises(ValueError):
        inversions(["a"], ["b"])


def test_rank_in():
    assert rank_in(["x", "y", "z"], "z") == 3


# ------------------------------------------------------------ tie-aware correlation
from busbidder.evaluation import average_ranks, rank_correlation


def test_average_ranks_share_the_ranks_of_ties():
    assert average_ranks([10, 20, 30]) == [1.0, 2.0, 3.0]
    assert average_ranks([30, 10, 20]) == [3.0, 1.0, 2.0]
    assert average_ranks([5, 5, 9]) == [1.5, 1.5, 3.0]
    assert average_ranks([7, 7, 7, 7]) == [2.5, 2.5, 2.5, 2.5]
    assert average_ranks([]) == []


def test_rank_correlation_values():
    assert rank_correlation([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert rank_correlation([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert rank_correlation([1, 2, 3], [1, 3, 2]) == pytest.approx(0.5)
    assert rank_correlation([1, 2, 3, 4], [1, 2, 3, 4.5]) == pytest.approx(1.0)       # only the order counts


def test_rank_correlation_with_ties_and_constants():
    assert rank_correlation([1, 2, 3, 4], [0, 0, 1, 1]) == pytest.approx(0.8944, abs=1e-3)
    assert rank_correlation([1, 2, 3], [5, 5, 5]) == 0.0           # nothing to follow
    assert rank_correlation([1], [1]) == 0.0
    with pytest.raises(ValueError):
        rank_correlation([1, 2], [1])


def test_rank_correlation_matches_spearman_without_ties():
    a, b = list("abcdef"), list("badcfe")
    pos = {x: i for i, x in enumerate(b)}
    assert rank_correlation(list(range(6)), [pos[x] for x in a]) == pytest.approx(spearman(a, b))
