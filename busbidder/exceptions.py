"""Custom exceptions (Task 2). One base class so callers can catch everything."""


class BusBidderError(Exception):
    """Base class for all application errors."""


class DataFileError(BusBidderError):
    """A data/config file is missing or unreadable."""


class ValidationError(BusBidderError):
    """A record has a missing, inconsistent or impossible value.

    `category` is a short machine-readable name (e.g. "negative_price"), the
    same names that are used in data/offers_invalid_expected.json.
    """

    def __init__(self, category: str, message: str):
        super().__init__(f"{category}: {message}")
        self.category = category
        self.message = message


class WeightError(BusBidderError):
    """Ranking weights are invalid (e.g. do not sum to 1.0)."""


class BookingError(BusBidderError):
    """A booking could not be completed (e.g. no seats left)."""


class UnknownCriterionError(WeightError):
    """Weights refer to a scoring criterion that is not registered."""


class ScoringError(BusBidderError):
    """A criterion returned a value that is not a score between 0 and 100."""
