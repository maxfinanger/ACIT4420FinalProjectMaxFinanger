from datetime import date, time

import pytest

from busbidder import criteria
from busbidder.exceptions import UnknownCriterionError, WeightError
from busbidder.filtering import BudgetConstraint, Constraint
from busbidder.models import FareConditions, Offer, TravelRequest
from busbidder.ranking import validate_weights


def make_offer(price=40.0):
    return Offer("OF-0001", "SolRuta", "Malaga", date(2026, 7, 12), time(8, 0),
                 time(14, 0), price, 0, FareConditions(True, False, 20), 5, 4.0)


def make_request(budget=50.0):
    return TravelRequest("Malaga", date(2026, 7, 12), date(2026, 7, 14), budget)


def test_offer_has_fare_conditions_by_composition():
    offer = make_offer()
    assert offer.fare.changeable is True
    assert offer.duration_minutes == 360


def test_fare_conditions_are_immutable():
    with pytest.raises(Exception):
        make_offer().fare.changeable = False


def test_constraint_base_class_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Constraint()


def test_budget_boundary_price_equal_to_budget_is_accepted():
    assert BudgetConstraint().is_satisfied(make_offer(50.0), make_request(50.0))
    assert not BudgetConstraint().is_satisfied(make_offer(50.01), make_request(50.0))


def test_four_mandatory_criteria_are_registered():
    assert {"price", "duration", "departure", "flexibility"} <= set(criteria.registered_names())


def test_decorator_registers_new_criterion(monkeypatch):
    monkeypatch.setattr(criteria, "_REGISTRY", {})

    @criteria.register_criterion("rating", "Higher rating is better")
    def rating_score(offer, offers, request):
        return offer.rating / 5 * 100

    assert criteria.registered_names() == ["rating"]
    assert criteria.get_criterion("rating").func(make_offer(), [], make_request()) == 80.0


def test_duplicate_registration_is_rejected(monkeypatch):
    monkeypatch.setattr(criteria, "_REGISTRY", {})
    criteria.register_criterion("x")(lambda o, os, r: 0)
    with pytest.raises(ValueError):
        criteria.register_criterion("x")(lambda o, os, r: 0)


def test_unknown_criterion_in_weights_is_rejected():
    with pytest.raises(UnknownCriterionError):
        validate_weights({"price": 0.5, "comfort": 0.5})


def test_negative_weight_is_rejected():
    with pytest.raises(WeightError):
        validate_weights({"price": 1.5, "duration": -0.5})
