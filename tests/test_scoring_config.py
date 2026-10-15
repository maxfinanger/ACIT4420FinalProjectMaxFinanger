import json

import pytest

from busbidder.criteria import price_score
from busbidder.exceptions import DataFileError
from busbidder.loader import load_scoring_config
from busbidder.scoring_config import ScoringConfig, get_config, reset_config, set_config
from tests.test_ranking import make


def test_defaults_in_code_equal_the_json_file():
    assert load_scoring_config().to_dict() == ScoringConfig().to_dict()


def test_partial_config_keeps_defaults_for_the_rest():
    cfg = ScoringConfig.from_dict({"price": {"min_span_eur": 10}})
    assert cfg.price_min_span_eur == 10 and cfg.departure_tolerance_minutes == 360


def test_comment_keys_are_ignored():
    assert ScoringConfig.from_dict({"_comment": "hello"}) == ScoringConfig()


@pytest.mark.parametrize("data", [
    {"typo": 1},
    {"price": {"min_span_eur": 0}},
    {"price": {"min_span_eur": -1}},
    {"price": {"min_span_eur": "5"}},
    {"price": {"min_span_eur": True}},
    {"relative_scale": {"outlier_cap_factor": 0.5}},
    {"flexibility": {"changeable": 120}},
    {"flexibility": {"none": -1}},
    {"missing_value_score": 101},
    {"missing_value_score": "x"},
    {"departure": {"tolerance_minutes": 0}},
])
def test_invalid_settings_are_rejected(data):
    with pytest.raises(ValueError):
        ScoringConfig.from_dict(data)


def test_zero_flexibility_score_is_allowed():
    assert ScoringConfig.from_dict({"flexibility": {"none": 0}}).flex_none == 0


def test_missing_invalid_or_non_object_file_is_a_data_file_error(tmp_path):
    with pytest.raises(DataFileError):
        load_scoring_config(str(tmp_path / "nope.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    with pytest.raises(DataFileError):
        load_scoring_config(str(bad))
    lst = tmp_path / "list.json"
    lst.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(DataFileError):
        load_scoring_config(str(lst))
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"price": {"min_span_eur": -3}}), encoding="utf-8")
    with pytest.raises(DataFileError, match="out of range"):
        load_scoring_config(str(wrong))


def test_changing_the_config_changes_the_scores_and_reset_restores_it():
    request = None
    a, b = make("OF-0001", price=30.0), make("OF-0002", price=31.0)
    assert price_score(b, [a, b], request) == pytest.approx(80.0)
    set_config(ScoringConfig(price_min_span_eur=2.0))
    assert price_score(b, [a, b], request) == pytest.approx(50.0)
    reset_config()
    assert get_config().price_min_span_eur == 5.0
