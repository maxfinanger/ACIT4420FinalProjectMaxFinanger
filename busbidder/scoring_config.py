"""Parameters of the scoring model, loaded from config/scoring.json (decision D15).

The defaults below are the same values as in the file. A test checks that they
agree, so the model can be reproduced from the file alone.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringConfig:
    # "meaningful difference": the spread over which a relative criterion goes from 100 to 0
    price_min_span_eur: float = 5.0
    duration_min_span_minutes: float = 60.0
    emissions_min_span_kg: float = 2.0
    # values worse than this multiple of the median count as the worst possible
    outlier_cap_factor: float = 2.0
    # a departure this far from the preferred time scores 0
    departure_tolerance_minutes: float = 360.0
    # this many transfers (or more) scores 0
    transfers_max_reference: int = 3
    # flexibility levels (fixed scores, 0-100)
    flex_none: float = 0.0
    flex_changeable: float = 60.0
    flex_refundable: float = 40.0
    flex_both: float = 100.0
    # score for an offer that has no value for a criterion (e.g. no emissions figure)
    missing_value_score: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "ScoringConfig":
        """Build from the nested JSON structure. Raises ValueError for bad input."""
        known = {"price", "duration", "emissions", "relative_scale", "departure",
                 "transfers", "flexibility", "missing_value_score"}
        unknown = [k for k in data if k not in known and not k.startswith("_")]
        if unknown:
            raise ValueError(f"unknown scoring settings: {', '.join(unknown)}")
        d = cls()

        def num(section, key, default, minimum=0.0, maximum=None, strict=True):
            value = (data.get(section) or {}).get(key, default) if isinstance(
                data.get(section, {}), dict) else default
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{section}.{key} must be a number, got {value!r}")
            if (value <= minimum if strict else value < minimum) or (
                    maximum is not None and value > maximum):
                raise ValueError(f"{section}.{key} is out of range: {value}")
            return float(value)

        missing = data.get("missing_value_score", d.missing_value_score)
        if isinstance(missing, bool) or not isinstance(missing, (int, float)) or not 0 <= missing <= 100:
            raise ValueError(f"missing_value_score must be 0-100, got {missing!r}")
        cap = num("relative_scale", "outlier_cap_factor", d.outlier_cap_factor)
        if cap < 1:
            raise ValueError("relative_scale.outlier_cap_factor must be at least 1")
        return cls(
            price_min_span_eur=num("price", "min_span_eur", d.price_min_span_eur),
            duration_min_span_minutes=num("duration", "min_span_minutes", d.duration_min_span_minutes),
            emissions_min_span_kg=num("emissions", "min_span_kg", d.emissions_min_span_kg),
            outlier_cap_factor=cap,
            departure_tolerance_minutes=num("departure", "tolerance_minutes", d.departure_tolerance_minutes),
            transfers_max_reference=int(num("transfers", "max_reference", d.transfers_max_reference)),
            flex_none=num("flexibility", "none", d.flex_none, 0, 100, strict=False),
            flex_changeable=num("flexibility", "changeable", d.flex_changeable, 0, 100, strict=False),
            flex_refundable=num("flexibility", "refundable", d.flex_refundable, 0, 100, strict=False),
            flex_both=num("flexibility", "changeable_and_refundable", d.flex_both, 0, 100, strict=False),
            missing_value_score=float(missing),
        )

    def to_dict(self) -> dict:
        return {
            "price": {"min_span_eur": self.price_min_span_eur},
            "duration": {"min_span_minutes": self.duration_min_span_minutes},
            "emissions": {"min_span_kg": self.emissions_min_span_kg},
            "relative_scale": {"outlier_cap_factor": self.outlier_cap_factor},
            "departure": {"tolerance_minutes": self.departure_tolerance_minutes},
            "transfers": {"max_reference": self.transfers_max_reference},
            "flexibility": {"none": self.flex_none, "changeable": self.flex_changeable,
                            "refundable": self.flex_refundable,
                            "changeable_and_refundable": self.flex_both},
            "missing_value_score": self.missing_value_score,
        }


_current = ScoringConfig()


def get_config() -> ScoringConfig:
    return _current


def set_config(config: ScoringConfig) -> None:
    global _current
    _current = config


def reset_config() -> None:
    set_config(ScoringConfig())
