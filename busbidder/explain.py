"""Explainable recommendation (Section 6): a short text built from the data.

The explanation says WHY the top offer ranks first and what still counts against
it. Everything in it is computed from the ranked offers, nothing is hand-written
per offer (decision D17):

  - Advantages: weighted criteria where the offer scores 75 or more, strongest
    contribution first (at most 3).
  - Drawbacks: criteria where it scores 40 or less, biggest weighted loss first
    (at most 2). There is ALWAYS a drawback line: if nothing is that weak, its
    weakest criterion is named, and only if it scores 100 on everything does the
    text say that no shortfall was found.
  - Comparison with the runner-up, in weighted points per criterion.
  - A caveat: the offer is best only under the hard requirements, the weights and
    the scoring assumptions, never "objectively".
"""
from dataclasses import dataclass, field

from .criteria import minutes_between
from .models import Offer, RankedOffer, TravelRequest

ADVANTAGE_MIN_SCORE = 75.0
DISADVANTAGE_MAX_SCORE = 40.0
MAX_ADVANTAGES = 3
MAX_DISADVANTAGES = 2


def format_minutes(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


# ---- one sentence fragment per criterion (comparing with the other offers) ----
def _price_fact(offer: Offer, offers: list[Offer], request: TravelRequest) -> str:
    cheapest = min(o.price for o in offers)
    if offer.price <= cheapest:
        joint = sum(o.price == cheapest for o in offers) > 1
        return (f"EUR {offer.price:.2f}, the {'joint ' if joint else ''}lowest of the "
                f"{len(offers)} acceptable offers")
    return (f"EUR {offer.price:.2f}, EUR {offer.price - cheapest:.2f} above the cheapest "
            f"(EUR {cheapest:.2f})")


def _duration_fact(offer: Offer, offers: list[Offer], request: TravelRequest) -> str:
    fastest = min(o.duration_minutes for o in offers)
    if offer.duration_minutes <= fastest:
        return f"{format_minutes(offer.duration_minutes)}, the shortest journey on offer"
    return (f"{format_minutes(offer.duration_minutes)}, "
            f"{format_minutes(offer.duration_minutes - fastest)} longer than the fastest "
            f"({format_minutes(fastest)})")


def _departure_fact(offer: Offer, offers: list[Offer], request: TravelRequest) -> str:
    diff = minutes_between(offer.departure_time, request.preferred_departure)
    if diff == 0:
        return f"departs {offer.departure_time:%H:%M}, exactly at the preferred time"
    return (f"departs {offer.departure_time:%H:%M}, {diff} min from the preferred "
            f"{request.preferred_departure:%H:%M}")


def _flexibility_fact(offer: Offer, offers: list[Offer], request: TravelRequest) -> str:
    fare = offer.fare
    if fare.changeable and fare.refundable:
        return "a changeable and refundable fare"
    if fare.changeable:
        return "a changeable fare, but not refundable"
    if fare.refundable:
        return "a refundable fare, but not changeable"
    return "a fixed fare (not changeable, not refundable)"


def _transfers_fact(offer: Offer, offers: list[Offer], request: TravelRequest) -> str:
    if offer.transfers == 0:
        return "a direct route"
    return f"{offer.transfers} transfer{'s' if offer.transfers > 1 else ''}"


def _rating_fact(offer: Offer, offers: list[Offer], request: TravelRequest) -> str:
    return f"rated {offer.rating:.1f} out of 5"


def _emissions_fact(offer: Offer, offers: list[Offer], request: TravelRequest) -> str:
    if offer.emissions_kg is None:
        return "no emissions figure reported (scored as the worst case)"
    lowest = min(o.emissions_kg for o in offers if o.emissions_kg is not None)
    return f"{offer.emissions_kg:.1f} kg CO2 (lowest reported: {lowest:.1f} kg)"


FACTS = {"price": _price_fact, "duration": _duration_fact, "departure": _departure_fact,
         "flexibility": _flexibility_fact, "transfers": _transfers_fact,
         "rating": _rating_fact, "emissions": _emissions_fact}


def describe_criterion(name: str, offer: Offer, offers: list[Offer],
                       request: TravelRequest, score: float) -> str:
    """Words for one criterion. A criterion added later (registry, D5) without its own
    sentence still gets a generic one, so the explanation never breaks."""
    fact = FACTS.get(name)
    return fact(offer, offers, request) if fact else f"score {score:.0f} out of 100 on '{name}'"


# ---- the explanation ------------------------------------------------------------
@dataclass
class Explanation:
    headline: str
    advantages: list[str] = field(default_factory=list)
    disadvantages: list[str] = field(default_factory=list)
    comparison: str | None = None
    tie_note: str | None = None
    caveat: str = ""

    def text(self) -> str:
        lines = [self.headline]
        if self.advantages:
            lines.append("Advantages:")
            lines += [f"  + {a}" for a in self.advantages]
        if self.disadvantages:
            lines.append("Drawbacks:")
            lines += [f"  - {d}" for d in self.disadvantages]
        for extra in (self.comparison, self.tie_note):
            if extra:
                lines.append(extra)
        if self.caveat:
            lines.append(self.caveat)
        return "\n".join(lines)

    __str__ = text


def _tie_break_reason(a: Offer, b: Offer) -> str:
    if a.price != b.price:
        return "its price is lower"
    if a.duration_minutes != b.duration_minutes:
        return "its journey is shorter"
    if a.departure_datetime != b.departure_datetime:
        return "it departs earlier"
    return "its offer id comes first"


def _weights_text(weights: dict) -> str:
    return ", ".join(f"{n} {w * 100:.0f}%" for n, w in weights.items() if w > 0)


def explain_top_offer(ranked: list[RankedOffer], request: TravelRequest,
                      weights: dict) -> Explanation:
    """Explain why ranked[0] is recommended, and what still counts against it."""
    if not ranked:
        return Explanation("No offer meets the hard requirements, so there is nothing to recommend.")

    top = ranked[0]
    o = top.offer
    offers = [r.offer for r in ranked]
    active = [n for n, w in weights.items() if w > 0]
    label = ("your own weights" if request.profile == "(custom)"
             else f"the '{request.profile}' profile")

    headline = (f"{o.offer_id} ({o.company}), departs {o.travel_date:%d %b} {o.departure_time:%H:%M}, "
                f"arrives {o.arrival_date:%d %b} {o.arrival_time:%H:%M}, EUR {o.price:.2f}: "
                f"ranked first with {top.total_score:.1f} out of 100 for {label}.")
    caveat = (f"This is the highest-ranked offer only under your hard requirements, the weights of "
              f"{label} ({_weights_text(weights)}) and the scoring assumptions (price and duration "
              f"are scored relative to the {len(ranked)} acceptable offer{'s' if len(ranked) != 1 else ''}). Other weights can give another "
              f"result, so it is a recommendation under those assumptions, not a proof that nothing "
              f"is better.")

    if len(ranked) == 1:
        return Explanation(headline, comparison="It is the only offer that meets the hard "
                           "requirements, so there is nothing to compare it with.", caveat=caveat)

    # advantages: strong criteria, biggest weighted contribution first
    strong = sorted((n for n in active if top.criterion_scores[n] >= ADVANTAGE_MIN_SCORE),
                    key=lambda n: (-top.contributions[n], n))
    advantages = [f"{n}: {describe_criterion(n, o, offers, request, top.criterion_scores[n])}"
                  for n in strong[:MAX_ADVANTAGES]]
    if "transfers" not in weights and o.transfers == 0 and any(x.transfers > 0 for x in offers):
        advantages.append(f"a direct route, while {sum(x.transfers > 0 for x in offers)} of the "
                          f"{len(offers)} acceptable offers have transfers")
    if not advantages:
        advantages = [f"no single criterion stands out (none scores {ADVANTAGE_MIN_SCORE:.0f} or "
                      "more); it ranks first on balance"]

    # drawbacks: ALWAYS at least one line
    weak = sorted((n for n in active if top.criterion_scores[n] <= DISADVANTAGE_MAX_SCORE),
                  key=lambda n: (-(weights[n] * (100 - top.criterion_scores[n])), n))
    disadvantages = [f"{n}: {describe_criterion(n, o, offers, request, top.criterion_scores[n])} "
                     f"(score {top.criterion_scores[n]:.0f} out of 100)" for n in weak[:MAX_DISADVANTAGES]]
    if not disadvantages:
        weakest = min(active, key=lambda n: (top.criterion_scores[n], n))
        if top.criterion_scores[weakest] < 100:
            disadvantages = [f"weakest point is {weakest}: "
                             f"{describe_criterion(weakest, o, offers, request, top.criterion_scores[weakest])} "
                             f"(score {top.criterion_scores[weakest]:.0f} out of 100)"]
        else:
            disadvantages = ["none found: it scores 100 on every weighted criterion compared "
                             "with the other acceptable offers"]
    if "transfers" not in weights and o.transfers > 0 and any(x.transfers == 0 for x in offers):
        disadvantages.append(f"{o.transfers} transfer{'s' if o.transfers > 1 else ''}, while "
                             f"{sum(x.transfers == 0 for x in offers)} acceptable offers are direct")

    # comparison with the runner-up, in weighted points
    runner = ranked[1]
    diffs = {n: top.contributions[n] - runner.contributions[n] for n in active}
    ahead = sorted((n for n in diffs if diffs[n] > 0.05), key=lambda n: (-diffs[n], n))[:2]
    behind = sorted((n for n in diffs if diffs[n] < -0.05), key=lambda n: (diffs[n], n))[:2]
    parts = []
    if ahead:
        parts.append("ahead on " + ", ".join(f"{n} (+{diffs[n]:.1f} points)" for n in ahead))
    if behind:
        parts.append("behind on " + ", ".join(f"{n} ({diffs[n]:.1f} points)" for n in behind))
    comparison = (f"Compared with the runner-up {runner.offer.offer_id} "
                  f"({runner.total_score:.1f}): " + ("; ".join(parts) if parts
                                                      else "practically the same on every criterion") + ".")
    tie_note = None
    if top.tie_broken and round(top.total_score, 2) == round(runner.total_score, 2):
        tie_note = (f"It has the same score as {runner.offer.offer_id} to two decimals and is "
                    f"placed first because {_tie_break_reason(o, runner.offer)}.")

    return Explanation(headline, advantages, disadvantages, comparison, tie_note, caveat)
