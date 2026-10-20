"""Run the Phase 9 experiments and write docs/evaluation.md.

    python scripts/evaluate.py

Everything is computed from the real program (filtering, scoring, ranking) with fixed random seeds, and
the file has no timestamps, so the numbers in the report can be reproduced exactly. A test checks that
the committed file matches this script.
"""
import hashlib
import random
import statistics
import sys
from dataclasses import replace
from datetime import date, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so it runs as a plain script

from busbidder.criteria import minutes_between, registered_names
from busbidder.evaluation import (ScoredSet, inversions, order_of, perturb_weights, random_simplex,
                                  rank_correlation, rank_in, rescale_weights, spearman, winner_interval)
from busbidder.filtering import filter_offers
from busbidder.loader import (load_companies, load_destinations, load_offers, load_profiles,
                              load_scoring_config)
from busbidder.models import TravelRequest
from busbidder.ranking import influence_share, rank_offers
from busbidder.scoring_config import ScoringConfig, set_config

SEED = 42
MANDATORY = ["price", "duration", "departure", "flexibility"]
WITH_EXTRAS = MANDATORY + ["transfers", "emissions"]       # the two optional criteria used by environment_focused
NO_FIGURE = 1e9                                           # a missing emissions figure counts as the worst value
SPEC = dict(destination="Malaga", date_from=date(2026, 7, 12), date_to=date(2026, 7, 14),
            max_budget=50.0, max_transfers=1, require_changeable=True, preferred_departure=time(9, 0))
ROOT = Path(__file__).resolve().parent.parent


def md_table(headers: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out + [""]


def pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%"


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class World:
    """The data, loaded once, and helpers to filter and score a request."""

    def __init__(self):
        self.base_config = load_scoring_config()
        set_config(self.base_config)
        self.companies = [c.name for c in load_companies()]
        self.destinations = [d.name for d in load_destinations()]
        self.offers = load_offers(str(ROOT / "data/offers.csv"), self.destinations, self.companies).offers
        self.profiles = load_profiles(str(ROOT / "config/profiles.json"))
        self.names = registered_names()

    def request(self, destination: str, budget: float, **kw) -> TravelRequest:
        base = dict(date_from=date(2026, 7, 12), date_to=date(2026, 7, 14), preferred_departure=time(9, 0))
        base.update(kw)
        return TravelRequest(destination=destination, max_budget=budget, **base)

    def spec(self, **changes) -> TravelRequest:
        return TravelRequest(**{**SPEC, **changes})

    def kept(self, request: TravelRequest, offers=None) -> list:
        return filter_offers(self.offers if offers is None else offers, request).kept

    def scored(self, request: TravelRequest, offers=None) -> ScoredSet:
        return ScoredSet(self.kept(request, offers), request, self.names)

    def with_config(self, **changes) -> None:
        set_config(replace(self.base_config, **changes))

    def reset_config(self) -> None:
        set_config(self.base_config)


def raw_values(sset: ScoredSet, request: TravelRequest) -> dict[str, dict[str, float]]:
    """The raw value of every offer on each criterion, where LOWER IS ALWAYS BETTER."""
    flex = {o.offer_id: s["flexibility"] for o, s in zip(sset.offers, sset.scores)}
    return {
        "price": {o.offer_id: o.price for o in sset.offers},
        "duration": {o.offer_id: float(o.duration_minutes) for o in sset.offers},
        "departure": {o.offer_id: float(minutes_between(o.departure_time, request.preferred_departure))
                      for o in sset.offers},
        "flexibility": {o.offer_id: -flex[o.offer_id] for o in sset.offers},
        "transfers": {o.offer_id: float(o.transfers) for o in sset.offers},
        "emissions": {o.offer_id: NO_FIGURE if o.emissions_kg is None else o.emissions_kg for o in sset.offers},
    }


def best_position(sset: ScoredSet, request: TravelRequest, offer_id: str) -> dict[str, int]:
    """Rank of one offer on each raw criterion, 1 = best, ties share the best rank."""
    o = next(x for x in sset.offers if x.offer_id == offer_id)
    flex = {x.offer_id: s["flexibility"] for x, s in zip(sset.offers, sset.scores)}
    diff = lambda x: minutes_between(x.departure_time, request.preferred_departure)
    return {
        "price": 1 + sum(x.price < o.price for x in sset.offers),
        "duration": 1 + sum(x.duration_minutes < o.duration_minutes for x in sset.offers),
        "departure": 1 + sum(diff(x) < diff(o) for x in sset.offers),
        "flexibility": 1 + sum(flex[x.offer_id] > flex[offer_id] for x in sset.offers),
        "emissions": 1 + sum((x.emissions_kg or NO_FIGURE) < (o.emissions_kg or NO_FIGURE) for x in sset.offers),
    }


# ----------------------------------------------------------------------------------------------
# 1. Are the rankings reasonable?
# ----------------------------------------------------------------------------------------------
def section_reasonable(w: World, findings: list[str]) -> list[str]:
    req = w.spec()
    sset = w.scored(req)
    n = len(sset.offers)
    values = raw_values(sset, req)
    rows_pos, rows_rho = [], []
    for name, weights in w.profiles.items():
        ranked = sset.rank(weights)
        order = order_of(ranked)
        top = ranked[0].offer
        pos = best_position(sset, req, top.offer_id)
        rows_pos.append([name, f"{top.offer_id} ({top.company})"] + [f"{pos[c]}" for c in MANDATORY + ["emissions"]])
        position = {oid: i + 1 for i, oid in enumerate(order)}
        rows_rho.append([name] + [f"{rank_correlation([position[i] for i in order], [values[c][i] for i in order]):+.2f}"
                                  for c in WITH_EXTRAS])
    out = ["## 1. Are the rankings reasonable?", "",
           f"Test request: the example from the spec (Malaga, 12-14 July, max EUR 50, at most 1 transfer, changeable "
           f"ticket required, preferred departure 09:00). {n} offers remain after filtering.", "",
           "### 1a. Where does each winner stand on the raw values?", "",
           f"Rank of the winning offer among the {n} offers when they are ordered by one raw value only "
           "(1 = best, ties share a rank). A sensible winner is near the top on the criteria its profile cares about.", ""]
    out += md_table(["Profile", "Winner"] + [f"{c} rank" for c in MANDATORY + ["emissions"]], rows_pos)
    out += ["### 1b. How much does each profile's ranking follow a single raw value?", "",
            "Spearman rank correlation (equal values share a rank) between the profile's ranking position and one raw value where lower is better "
            "(+1 = the ranking follows that value, 0 = unrelated, negative = opposite).", ""]
    out += md_table(["Profile"] + WITH_EXTRAS, rows_rho)
    strongest = []
    for row in rows_rho:
        values = {c: float(v) for c, v in zip(WITH_EXTRAS, row[1:])}
        best = max(values, key=values.get)
        strongest.append(f"`{row[0]}` follows {best} most (rho {values[best]:+.2f})")
    findings.append("Each profile's ranking follows the raw value its weights favour: " + "; ".join(strongest) + ". "
                    "Rho is well below 1 because the ranking combines four criteria.")
    return out


# ----------------------------------------------------------------------------------------------
# 2. Weight sensitivity
# ----------------------------------------------------------------------------------------------
def section_weights(w: World, findings: list[str]) -> list[str]:
    req = w.spec()
    sset = w.scored(req)
    out = ["## 2. How sensitive is the winner to the weights?", ""]

    # 2a one-at-a-time sweep for the budget profile
    base = w.profiles["budget_traveller"]
    out += ["### 2a. One weight at a time (budget traveller)", "",
            "The weight of one criterion is set to the value in the first column, and the other three keep their "
            "relative sizes (so the total stays 100%). The cell shows the winning offer.", ""]
    rows, winners = [], set()
    for k in range(0, 101, 10):
        row = [f"{k}%"]
        for c in MANDATORY:
            win = order_of(sset.rank(rescale_weights(base, c, k / 100)))[0]
            winners.add(win)
            row.append(win)
        rows.append(row)
    out += md_table(["Weight on the criterion"] + [f"{c}" for c in MANDATORY], rows)
    out += [f"Across this sweep {len(winners)} different offers win.", ""]

    # 2b stability intervals
    out += ["### 2b. How far can a weight move before the winner changes?", "",
            "For each weight of each profile (the others rescaled in proportion), the range in which the baseline winner "
            "stays the winner, searched in steps of 0.5 percentage points. The margin is the distance from the "
            "current weight to the nearest change.", ""]
    rows, margins = [], []
    for name, weights in w.profiles.items():
        sset_p = ScoredSet(sset.offers, req, w.names)
        win = order_of(sset_p.rank(weights))[0]
        for c, base_w in weights.items():
            if base_w <= 0:
                continue
            lo, hi = winner_interval(sset_p, weights, c)
            margin = min(base_w - lo, hi - base_w) * 100
            margins.append((margin, name, c))
            rows.append([name, win, c, pct(base_w), f"{lo * 100:.1f}% to {hi * 100:.1f}%", f"{margin:.1f}"])
    out += md_table(["Profile", "Winner", "Criterion", "Weight now", "Winner stays for", "Margin (points)"], rows)
    margins.sort()
    least = margins[0]
    robust = sum(1 for m, _, _ in margins if m >= 10)
    findings.append(f"The winner is stable for most single-weight changes: {robust} of {len(margins)} weights can move by 10 points or more "
                    f"before the winner changes. The most fragile is `{least[2]}` for `{least[1]}` (margin {least[0]:.1f} points).")

    # 2c random perturbation
    out += ["### 2c. Random changes to all weights at once", "",
            f"Each weight is multiplied by a random factor within the given spread and the weights are renormalised "
            f"(1000 samples per row, seed {SEED}).", ""]
    rows = []
    rng = random.Random(SEED)
    stat = {}
    for name, weights in w.profiles.items():
        base_order = order_of(sset.rank(weights))
        for spread in (0.1, 0.3, 0.5):
            same = top3 = 0
            rho = []
            winners = set()
            for _ in range(1000):
                order = order_of(sset.rank(perturb_weights(rng, weights, spread)))
                same += order[0] == base_order[0]
                top3 += base_order[0] in order[:3]
                rho.append(spearman(base_order, order))
                winners.add(order[0])
            rows.append([name, f"+/-{spread * 100:.0f}%", pct(same / 1000), pct(top3 / 1000),
                         f"{statistics.mean(rho):.3f}", len(winners)])
            stat[(name, spread)] = same / 1000
    out += md_table(["Profile", "Spread", "Same winner", "Old winner still in top 3", "Mean rank correlation", "Different winners seen"], rows)
    low = min(v for (n, s), v in stat.items() if s == 0.3)
    findings.append(f"With every weight changed randomly by up to 30%, the winner stays the same in at least {pct(low)} of the samples for every profile.")

    # 2d fully random weights
    rng = random.Random(SEED)
    counts: dict[str, int] = {}
    for _ in range(2000):
        win = order_of(sset.rank(random_simplex(rng, MANDATORY)))[0]
        counts[win] = counts.get(win, 0) + 1
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    by_id = {o.offer_id: o for o in sset.offers}
    out += ["### 2d. Completely random weights", "",
            f"2000 weight vectors drawn uniformly from all possible ones over the four criteria (seed {SEED}). "
            "Which offers can win at all, and how often?", ""]
    rows = []
    for oid, c in ordered[:8]:
        o = by_id[oid]
        rows.append([oid, o.company, o.fare.fare_type, f"{o.price:.2f}", f"{o.duration_minutes // 60}h{o.duration_minutes % 60:02d}",
                     f"{o.departure_time:%H:%M}", pct(c / 2000, 1)])
    out += md_table(["Offer", "Company", "Fare", "EUR", "Duration", "Departs", "Share of wins"], rows)
    top3_share = sum(c for _, c in ordered[:3]) / 2000
    out += [f"{len(counts)} of the {len(sset.offers)} offers win under at least one weighting; the top three offers win "
            f"{pct(top3_share)} of the time.", ""]
    findings.append(f"Only {len(counts)} of {len(sset.offers)} offers can win under ANY weighting of the four criteria, and three offers win "
                    f"{pct(top3_share)} of random weightings: the weights choose between a few contenders, they do not make every offer a candidate.")
    return out


# ----------------------------------------------------------------------------------------------
# 3. Does one criterion dominate?
# ----------------------------------------------------------------------------------------------
def section_dominance(w: World, findings: list[str]) -> list[str]:
    out = ["## 3. Does one criterion dominate?", "",
           "Influence = weight x the spread (standard deviation) of that criterion's scores across the offers, as a share of the "
           "total (`docs/scoring.md`). If influence is far from the weight, the criterion has more or less say than its weight suggests.", ""]
    sset = w.scored(w.spec())
    rows, gaps = [], []
    for name, weights in w.profiles.items():
        shares = influence_share(sset.rank(weights), weights)
        for c, wt in weights.items():
            if wt <= 0:
                continue
            rows.append([name, c, pct(wt), pct(shares[c])])
            gaps.append((shares[c] - wt, name, c))
    out += ["### 3a. Weight versus influence on the spec request", ""]
    out += md_table(["Profile", "Criterion", "Weight", "Influence"], rows)
    gaps.sort()
    findings.append(f"Influence differs from weight: the largest excess is `{gaps[-1][2]}` for `{gaps[-1][1]}` ({gaps[-1][0] * 100:+.0f} points), "
                    f"the largest shortfall `{gaps[0][2]}` for `{gaps[0][1]}` ({gaps[0][0] * 100:+.0f} points). The weights are not the same as the "
                    "real importance.")

    scenarios = [
        ("Malaga, spec request", w.spec()),
        ("Malaga, no limits, max EUR 100", w.request("Malaga", 100.0)),
        ("Toledo (short trip), max EUR 20", w.request("Toledo", 20.0)),
        ("Cadiz (long trip), max EUR 80", w.request("Cadiz", 80.0)),
    ]
    out += ["### 3b. Does the candidate set change who dominates?", "",
            "Same two profiles, different requests. Because every criterion is scaled to the spread of the offers, the raw spread should matter "
            "less than how the values are distributed.", ""]
    rows, price_inf = [], []
    for label, request in scenarios:
        sc = w.scored(request)
        prices = [o.price for o in sc.offers]
        durations = [o.duration_minutes for o in sc.offers]
        for pname in ("budget_traveller", "business_traveller"):
            weights = {c: w.profiles[pname][c] for c in MANDATORY}
            shares = influence_share(sc.rank(weights), weights)
            rows.append([label, pname, len(sc.offers), f"{min(prices):.1f}-{max(prices):.1f}",
                         f"{min(durations) / 60:.1f}-{max(durations) / 60:.1f}"] + [pct(shares[c]) for c in MANDATORY])
            if pname == "budget_traveller":
                price_inf.append((shares["price"], label))
    out += md_table(["Request", "Profile", "Offers", "EUR range", "Hours range"] + [f"{c} influence" for c in MANDATORY], rows)
    by_label = {lab: val for val, lab in price_inf}
    narrow, wide = by_label["Toledo (short trip), max EUR 20"], by_label["Cadiz (long trip), max EUR 80"]
    out += [f"The price spread is EUR 8 in the Toledo request and EUR 38 in the Cadiz request, yet the budget profile's price influence is "
            f"{pct(narrow)} and {pct(wide)}: "
            + ("practically the same, so the scaling stops a wide price range from taking over." if abs(narrow - wide) < 0.03
               else "different, so the raw spread does change the influence."), ""]
    price_inf.sort()
    findings.append(f"For the budget profile (price weight 55%) the real influence of price ranges from {pct(price_inf[0][0])} "
                    f"({price_inf[0][1]}) to {pct(price_inf[-1][0])} ({price_inf[-1][1]}) depending on the request, so the same weight does "
                    "not mean the same thing in every search.")
    return out


# ----------------------------------------------------------------------------------------------
# 4. Scoring parameters
# ----------------------------------------------------------------------------------------------
PARAMS = [
    ("price_min_span_eur", "price: smallest meaningful spread (EUR)", [1.0, 2.5, 5.0, 10.0, 20.0]),
    ("duration_min_span_minutes", "duration: smallest meaningful spread (min)", [15.0, 30.0, 60.0, 120.0, 240.0]),
    ("departure_tolerance_minutes", "departure: distance that scores 0 (min)", [120.0, 240.0, 360.0, 480.0, 720.0]),
    ("outlier_cap_factor", "outlier cap (x median; 1000 = no cap)", [1.5, 2.0, 3.0, 1000.0]),
    ("flex_changeable", "flexibility: score of a changeable fare", [30.0, 45.0, 60.0, 75.0, 90.0]),
    ("transfers_max_reference", "transfers: number that scores 0", [2, 3, 5]),
]


def section_parameters(w: World, findings: list[str]) -> list[str]:
    req = w.spec()
    out = ["## 4. How sensitive is the result to the numbers in `config/scoring.json`?", "",
           "These numbers are my own choices (D15). Each row changes ONE of them and shows the winner for every profile "
           "(`*` = different from the default setting). A winner that never changes means the result does not depend on that choice.", ""]
    default = {}
    for name, weights in w.profiles.items():
        default[name] = order_of(w.scored(req).rank(weights))[0]
    rows, changed, total = [], 0, 0
    per_param = {}
    cases: list[str] = []
    try:
        for field, label, values in PARAMS:
            current = getattr(w.base_config, field)
            for value in values:
                w.with_config(**{field: type(current)(value)})
                sset = w.scored(req)
                cells = []
                for name, weights in w.profiles.items():
                    win = order_of(sset.rank(weights))[0]
                    differs = win != default[name]
                    if differs:
                        cases.append(f"{label.split(':')[0]} = {value:g} ({name})")
                    changed += differs
                    total += 1
                    per_param[field] = per_param.get(field, 0) + differs
                    cells.append(f"{win}{'*' if differs else ''}")
                tag = " (default)" if type(current)(value) == current else ""
                rows.append([label, f"{value:g}{tag}"] + cells)
    finally:
        w.reset_config()
    out += md_table(["Parameter", "Value"] + list(w.profiles), rows)
    out += [f"In {changed} of {total} cases ({pct(changed / total)}) the winner differs from the default"
            + (": " + "; ".join(cases) if cases else "") + ".", ""]
    findings.append(f"Changing one scoring parameter at a time (over ranges up to 4x either way) changes the winner in only {changed} of {total} cases "
                    f"({pct(changed / total)})" + (f": {'; '.join(cases)}" if cases else "") + ". The result does not hinge on any single one of my numbers, "
                    "but they remain design choices and the report should say so.")
    return out


# ----------------------------------------------------------------------------------------------
# 5. Unfair or unreasonable outcomes
# ----------------------------------------------------------------------------------------------
def section_night(w: World, findings: list[str]) -> list[str]:
    out = ["### 5a. Night buses and the departure criterion", "",
           "NocheVia leaves between 21:00 and 00:45. The `departure` score is 100 at the preferred time and 0 six hours away, so with "
           "the default preferred time 09:00 every night bus scores 0 on it. Does that hurt NocheVia? Request: Cadiz, 12-14 July, max EUR 80, "
           "no other limits.", ""]
    rows = []
    effects = {}
    for pname, weights in w.profiles.items():
        cells = []
        for hour in (9, 22):
            req = w.request("Cadiz", 80.0, preferred_departure=time(hour, 0))
            sset = w.scored(req)
            ranked = sset.rank(weights)
            night = [r.rank for r in ranked if r.offer.company == "NocheVia"]
            cells += [min(night), sum(r.offer.company == "NocheVia" for r in ranked[:10]), ranked[0].offer.company]
        rows.append([pname, weights.get("departure", 0) * 100 // 1 and f"{weights.get('departure', 0) * 100:.0f}%"] + cells)
        effects[pname] = (cells[0], cells[3])
    out += md_table(["Profile", "Departure weight", "Prefers 09:00: best NocheVia rank", "in top 10", "winner",
                     "Prefers 22:00: best NocheVia rank", "in top 10", "winner"], rows)
    avg = {}
    for hour in (9, 22):
        req = w.request("Cadiz", 80.0, preferred_departure=time(hour, 0))
        sset = w.scored(req)
        by_company: dict[str, list[float]] = {}
        for o, s in zip(sset.offers, sset.scores):
            by_company.setdefault(o.company, []).append(s["departure"])
        avg[hour] = {c: statistics.mean(v) for c, v in by_company.items()}
    out += ["Average `departure` score per company (0-100) on the same offers:", ""]
    out += md_table(["Company", "Prefers 09:00", "Prefers 22:00"],
                    [[c, f"{avg[9][c]:.0f}", f"{avg[22][c]:.0f}"] for c in sorted(avg[9])])
    hurt = [p for p, (a, b) in effects.items() if a > b]
    unhurt = [p for p, (a, b) in effects.items() if a <= b]
    findings.append(f"Night buses score {avg[9]['NocheVia']:.0f} on departure with the default 09:00 preference, against {avg[22]['NocheVia']:.0f} when the traveller "
                    f"prefers 22:00. The best NocheVia offer ranks lower at 09:00 than at 22:00 for {len(hurt)} of 4 profiles ({', '.join(hurt) if hurt else 'none'}); "
                    f"for {', '.join(unhurt) if unhurt else 'no profile'} the penalty does not matter because the price weight outweighs it. "
                    "The default preferred time, not the model's idea of night buses, creates the disadvantage.")
    return out


def section_budget(w: World, findings: list[str]) -> list[str]:
    out = ["### 5b. The budget: a hard limit that also moves the scores", "",
           "The budget removes offers completely (hard), but price and duration are scored RELATIVE to the offers that remain (D15). So changing "
           "the budget changes the scores of offers whose own values did not change. Sweep of the budget on the spec request, budget profile, "
           "in steps of EUR 0.50:", ""]
    weights = w.profiles["budget_traveller"]
    prev_top = None
    rows, totals, winners = [], [], []
    k = 30.0
    while k <= 50.0 + 1e-9:
        req = w.spec(max_budget=k)
        sset = w.scored(req)
        if sset.offers:
            ranked = sset.rank(weights)
            top3 = tuple(order_of(ranked)[:3])
            totals.append((ranked[0].total_score, k))
            winners.append(ranked[0].offer.offer_id)
            if top3 != prev_top:
                rows.append([f"{k:.2f}", len(sset.offers), ", ".join(top3), f"{ranked[0].total_score:.1f}"])
                prev_top = top3
        k += 0.5
    out += ["Rows are shown only where the top three change.", ""]
    out += md_table(["Budget (EUR)", "Offers left", "Top three", "Score of the winner"], rows)
    lo, hi = min(totals), max(totals)
    out += [f"The winner is {', '.join(sorted(set(winners)))} for every budget with at least one offer, but its score runs from {lo[0]:.1f} "
            f"(budget {lo[1]:.1f}) to {hi[0]:.1f} (budget {hi[1]:.1f}) although its own price, duration and fare never change.", ""]

    # the cliff: the runner-up appears or disappears with one cent
    req = w.spec(max_budget=50.0)
    ranked = w.scored(req).rank(weights)
    runner = ranked[1].offer
    cliff = []
    for budget in (round(runner.price - 0.01, 2), runner.price):
        r = w.spec(max_budget=budget)
        sc = w.scored(r)
        present = any(o.offer_id == runner.offer_id for o in sc.offers)
        position = rank_in(order_of(sc.rank(weights)), runner.offer_id) if present else "-"
        cliff.append([f"{budget:.2f}", len(sc.offers), "yes" if present else "no", position])
    out += [f"The cliff itself: {runner.offer_id} costs EUR {runner.price:.2f} and is number 2 at budget 50. One cent less budget removes it completely:", ""]
    out += md_table(["Budget (EUR)", "Offers left", f"{runner.offer_id} present", "Its rank"], cliff)
    findings.append(f"A hard budget is a cliff: {runner.offer_id} (EUR {runner.price:.2f}) is rank 2 at budget 50, still included at budget {runner.price:.2f} "
                    f"(rank {cliff[1][3]} there) and completely gone at {runner.price - 0.01:.2f}. The budget also shifts the winner's score between "
                    f"{lo[0]:.1f} and {hi[0]:.1f} through the relative price scale, although the winner itself does not change.")
    return out


STRICTNESS = [
    ("L0: budget 60", dict(budget=60.0)),
    ("L1: + direct only", dict(budget=60.0, max_transfers=0)),
    ("L2: + luggage 20 kg", dict(budget=60.0, max_transfers=0, min_luggage_kg=20)),
    ("L3: + journey at most 7 h", dict(budget=60.0, max_transfers=0, min_luggage_kg=20, max_duration_minutes=420)),
    ("L4: + changeable ticket", dict(budget=60.0, max_transfers=0, min_luggage_kg=20, max_duration_minutes=420,
                                      require_changeable=True)),
    ("L5: + budget 35", dict(budget=35.0, max_transfers=0, min_luggage_kg=20, max_duration_minutes=420,
                             require_changeable=True)),
]


def section_one_company(w: World, findings: list[str]) -> list[str]:
    out = ["### 5c. How strict requirements narrow the field of companies", "",
           "Hard requirements are added one by one (each level keeps the earlier ones). For all 15 destinations, 11-15 July, how many "
           "companies still have an offer? When only one company is left, the filter, not the scoring, decides the winner.", ""]
    rows, singles, last = [], [], None
    for label, kw in STRICTNESS:
        kw = dict(kw)
        budget = kw.pop("budget")
        counts, one, none = [], [], []
        for dest in w.destinations:
            req = w.request(dest, budget, date_from=date(2026, 7, 11), date_to=date(2026, 7, 15), **kw)
            companies = sorted({o.company for o in w.kept(req)})
            counts.append(len(companies))
            if len(companies) == 1:
                one.append(f"{dest} ({companies[0]})")
            if not companies:
                none.append(dest)
        rows.append([label, f"{statistics.mean(counts):.1f}", min(counts), len(one), len(none),
                     ", ".join(one) if one else "-"])
        singles.append((label, len(one), len(none), one))
        last = (label, len(one), len(none), one)
    out += md_table(["Requirements", "Companies left (average)", "Fewest", "Destinations with exactly 1 company",
                     "Destinations with no offer", "Which"], rows)
    first_none = next((l for l, o, n, _ in singles if n > 0), None)
    first_one = next((l for l, o, n, _ in singles if o > 0), None)
    findings.append("The field of companies narrows slowly: " + (f"a single company only remains from level '{first_one}'" if first_one else "no destination was ever reduced to one company")
                    + (f", and the first destinations with no offer at all appear at '{first_none}'" if first_none else "")
                    + f". At the strictest level {last[1]} of {len(w.destinations)} destinations have exactly one company ({', '.join(last[3]) if last[3] else 'none'}) "
                    f"and {last[2]} have none: in those cases the hard filter, not the scoring, decides.")
    return out


def section_market(w: World, findings: list[str]) -> list[str]:
    out = ["### 5d. Which companies win across the market?", "",
           "Request for every destination: 12-14 July, max EUR 60, preferred departure 09:00, no other limits. Winner of each profile "
           "(wins out of the destinations that have offers) and appearances in the top three:", ""]
    wins = {p: {c: 0 for c in w.companies} for p in w.profiles}
    top3 = {p: {c: 0 for c in w.companies} for p in w.profiles}
    used = 0
    for dest in w.destinations:
        req = w.request(dest, 60.0)
        sset = w.scored(req)
        if not sset.offers:
            continue
        used += 1
        for pname, weights in w.profiles.items():
            ranked = sset.rank(weights)
            wins[pname][ranked[0].offer.company] += 1
            for r in ranked[:3]:
                top3[pname][r.offer.company] += 1
    out += [f"Destinations with at least one offer: {used} of {len(w.destinations)}.", "", "Wins:", ""]
    out += md_table(["Company"] + list(w.profiles), [[c] + [wins[p][c] for p in w.profiles] for c in w.companies])
    out += ["Appearances in the top three:", ""]
    out += md_table(["Company"] + list(w.profiles), [[c] + [top3[p][c] for p in w.profiles] for c in w.companies])
    never = [c for c in w.companies if all(wins[p][c] == 0 for p in w.profiles)]
    dom = max(((wins[p][c], p, c) for p in w.profiles for c in w.companies))
    out += [f"Companies that never win under any profile: {', '.join(never) if never else 'none'}. "
            f"The strongest single result: {dom[2]} wins {dom[0]} of {used} destinations for `{dom[1]}`.", ""]
    leaders = []
    for p in w.profiles:
        company = max(w.companies, key=lambda c: (wins[p][c], c))
        leaders.append(f"`{p}` -> {company} ({wins[p][company]}/{used})")
    findings.append("Market structure (synthetic data, so this reflects how the companies were generated): the leading company per profile is "
                    + "; ".join(leaders) + ". "
                    + (f"{', '.join(never)} never win" + ("s" if len(never) == 1 else "") + " under any profile." if never else "Every company wins somewhere."))
    return out


def section_reversal(w: World, findings: list[str]) -> list[str]:
    out = ["### 5e. Rank reversal: does an offer that is not recommended change the order of the others?", "",
           "Spec request. For each profile every offer is removed in turn and the rest are ranked again (the scores are recomputed, "
           "because price and duration are relative). The new order is compared with the old order of the same offers.", ""]
    req = w.spec()
    offers = w.kept(req)
    rows = []
    summary = []
    for pname in ("budget_traveller", "business_traveller"):
        weights = {c: w.profiles[pname][c] for c in MANDATORY}
        base = order_of(rank_offers(offers, req, weights))
        winner_changes = order_changes = 0
        inv = []
        for o in offers:
            if o.offer_id == base[0]:
                continue                                  # removing the winner changes the winner by definition
            subset = [x for x in offers if x.offer_id != o.offer_id]
            new = order_of(rank_offers(subset, req, weights))
            expected = [i for i in base if i != o.offer_id]
            winner_changes += new[0] != expected[0]
            n_inv = inversions(expected, new)
            order_changes += n_inv > 0
            inv.append(n_inv)
        tested = len(offers) - 1
        rows.append([pname, tested, winner_changes, order_changes, f"{pct(order_changes / tested)}", max(inv), f"{statistics.mean(inv):.1f}"])
        summary.append((pname, winner_changes, order_changes, tested, max(inv)))
    out += md_table(["Profile", "Non-winners removed", "Winner changed", "Order of the rest changed", "Share", "Most pairs swapped", "Mean pairs swapped"], rows)
    worst = max(summary, key=lambda s: (s[2] / s[3], s[4]))
    findings.append(f"Rank reversal is real but rare here: removing one non-winning offer changed the order of the remaining offers in {worst[2]} of {worst[3]} cases "
                    f"for `{worst[0]}` (up to {worst[4]} pairs swapped), and changed the winner in {worst[1]}. The score of an offer only has meaning inside one list.")
    return out


def section_incentive(w: World, findings: list[str]) -> list[str]:
    out = ["### 5f. Does leaving out data pay? (emissions)", "",
           "A missing emissions figure scores 0 (D16). Suppose VerdeBus, the company with the lowest emissions, stopped reporting them. "
           "`environment_focused` profile, spec request:", ""]
    req = w.spec()
    weights = w.profiles["environment_focused"]
    offers = w.kept(req)
    omitted = [replace(o, emissions_kg=None) if o.company == "VerdeBus" else o for o in offers]
    rows = []
    results = {}
    for label, items in (("all companies report emissions", offers), ("VerdeBus reports none", omitted)):
        ranked = rank_offers(items, req, weights)
        results[label] = ranked
        rows.append([label, f"{ranked[0].offer.offer_id} ({ranked[0].offer.company})", f"{ranked[0].total_score:.1f}",
                     sum(r.offer.company == "VerdeBus" for r in ranked[:5]), min(r.rank for r in ranked if r.offer.company == "VerdeBus")])
    out += md_table(["Scenario", "Winner", "Score", "VerdeBus offers in top 5", "Best VerdeBus rank"], rows)
    a, b = rows[0], rows[1]
    findings.append(f"Penalising missing data works as intended: if VerdeBus stops reporting emissions, its offers in the environment profile's top 5 drop from "
                    f"{a[3]} to {b[3]} (best rank {a[4]} -> {b[4]}). The risk is the other way round: a company with poor data is punished even if the bus is clean.")
    return out


# ----------------------------------------------------------------------------------------------
# 6. Reproducibility
# ----------------------------------------------------------------------------------------------
def section_repro(w: World, findings: list[str]) -> list[str]:
    out = ["## 6. Reproducibility", "",
           "The same inputs must give the same ranking. Each profile is ranked three times, and once with the offers in reverse and in a shuffled "
           f"order (seed {SEED}). The fingerprint is the first 12 characters of the SHA-256 of the ranked offer ids, so a reader can check their own run.", ""]
    req = w.spec()
    offers = w.kept(req)
    shuffled = offers[:]
    random.Random(SEED).shuffle(shuffled)
    rows, all_same = [], True
    for pname, weights in w.profiles.items():
        runs = [order_of(rank_offers(offers, req, weights)) for _ in range(3)]
        runs.append(order_of(rank_offers(list(reversed(offers)), req, weights)))
        runs.append(order_of(rank_offers(shuffled, req, weights)))
        same = all(r == runs[0] for r in runs)
        all_same &= same
        rows.append([pname, "yes" if same else "NO", fingerprint(",".join(runs[0]))])
    out += md_table(["Profile", "Identical in 5 runs", "Fingerprint of the ranking"], rows)
    out += ["Fingerprints of the inputs (SHA-256, first 12 characters):", ""]
    out += md_table(["File", "Fingerprint"],
                    [[f, fingerprint((ROOT / f).read_text(encoding="utf-8"))] for f in
                     ("data/offers.csv", "config/scoring.json", "config/profiles.json")])
    findings.append("The ranking is identical in repeated runs and for any input order" if all_same else "WARNING: the ranking is not reproducible")
    return out


# ----------------------------------------------------------------------------------------------
def build_report() -> str:
    w = World()
    findings: list[str] = []
    try:
        s1 = section_reasonable(w, findings)
        s2 = section_weights(w, findings)
        s3 = section_dominance(w, findings)
        s4 = section_parameters(w, findings)
        s5 = ["## 5. Unfair or unreasonable outcomes", ""]
        for part in (section_night, section_budget, section_one_company, section_market,
                     section_reversal, section_incentive):
            s5 += part(w, findings)
        s6 = section_repro(w, findings)
    finally:
        w.reset_config()
    head = ["# Evaluation", "",
            "Generated by `python scripts/evaluate.py` from the real program. Do not edit by hand: a test checks that this file matches the "
            "script, so every number can be reproduced. Random experiments use a fixed seed. The data is synthetic (`docs/dataset.md`), so "
            "the results say how the MODEL behaves, not how real bus markets work.", "",
            "## Key findings", ""]
    head += [f"{i}. {f}" for i, f in enumerate(findings, start=1)] + [""]
    return "\n".join(head + s1 + s2 + s3 + s4 + s5 + s6)


def main() -> None:
    target = ROOT / "docs" / "evaluation.md"
    target.write_text(build_report(), encoding="utf-8", newline="\n")
    print(f"wrote {target}")


if __name__ == "__main__":
    main()
