"""Custom exceptions (Task 2). One base class so callers can catch everything."""


class BusBidderError(Exception):
    """Base class for all application errors."""


class DataFileError(BusBidderError):
    """A data/config file is missing or unreadable."""


class ValidationError(BusBidderError):
    """A record has a missing, inconsistent or impossible value."""


class WeightError(BusBidderError):
    """Ranking weights are invalid (e.g. do not sum to 1.0)."""


class BookingError(BusBidderError):
    """A booking could not be completed (e.g. no seats left)."""


class UnknownCriterionError(WeightError):
    """Weights refer to a scoring criterion that is not registered."""
