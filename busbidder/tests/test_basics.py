import pytest

from busbidder.exceptions import DataFileError, WeightError
from busbidder.loader import load_companies, load_destinations, load_profiles
from busbidder.ranking import validate_weights
from busbidder.validation import is_valid_booking_ref


def test_loads_five_companies():
    assert len(load_companies()) == 5


def test_loads_fifteen_destinations():
    assert len(load_destinations()) == 15


def test_missing_file_raises_custom_error():
    with pytest.raises(DataFileError):
        load_companies("data/does_not_exist.csv")


def test_profile_weights_sum_to_one():
    for weights in load_profiles().values():
        validate_weights(weights)


def test_bad_weights_rejected():
    with pytest.raises(WeightError):
        validate_weights({"price": 0.5, "duration": 0.2, "departure": 0.1, "flexibility": 0.1})


def test_booking_reference_pattern():
    assert is_valid_booking_ref("BB-20260712-A1B2C3")
    assert not is_valid_booking_ref("BOOKING123")
