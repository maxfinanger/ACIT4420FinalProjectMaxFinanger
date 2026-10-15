"""Command-line interface. Starts simple; grows with each phase.

Phase 3: load and validate the data.
Phase 4: describe a traveller request and show which offers survive the hard
constraints (use --destination ...).
Phase 5: rank the survivors with the weighted scoring model and show the score of
every criterion. Explanations and profile comparisons come in Phase 6, the
interactive menu in Phase 8.
"""
import argparse
from datetime import date, time

from .exceptions import BusBidderError, DataFileError, ValidationError
from .filtering import hard_constraint_lines, soft_preference_lines
from .loader import (load_companies, load_destinations, load_offers, load_profiles,
                     load_scoring_config, parse_date, parse_time)
from .log_setup import setup_logging
from .marketplace import Marketplace
from .models import RankedOffer, TravelRequest
from .ranking import influence_share, parse_weights
from .scoring_config import set_config

MAX_REJECTED_SHOWN = 25
DEFAULT_TOP = 10


def _date_arg(text: str) -> date:
    try:
        return parse_date(text, "date")
    except ValidationError as err:
        raise argparse.ArgumentTypeError(err.message) from None


def _time_arg(text: str) -> time:
    try:
        return parse_time(text, "time")
    except ValidationError as err:
        raise argparse.ArgumentTypeError(err.message) from None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="main.py", description="BusBidder Spain")
    p.add_argument("--offers", default="data/offers.csv",
                   help="offers CSV file (default: data/offers.csv)")
    g = p.add_argument_group(
        "traveller request (give --destination to run the hard-constraint filter)")
    g.add_argument("--destination", help="destination, e.g. Malaga")
    g.add_argument("--from", dest="date_from", type=_date_arg, metavar="YYYY-MM-DD",
                   help="earliest departure date")
    g.add_argument("--to", dest="date_to", type=_date_arg, metavar="YYYY-MM-DD",
                   help="latest departure date")
    g.add_argument("--budget", type=float, help="maximum price in EUR")
    g.add_argument("--max-transfers", type=int, help="maximum number of transfers")
    g.add_argument("--max-hours", type=float, help="maximum journey time in hours")
    g.add_argument("--min-luggage", type=int, default=0, help="minimum luggage allowance in kg")
    g.add_argument("--changeable", action="store_true", help="ticket must be changeable")
    g.add_argument("--preferred-departure", type=_time_arg, default=time(9, 0),
                   metavar="HH:MM", help="preferred departure time (soft, default 09:00)")
    g.add_argument("--profile", default="budget_traveller",
                   help="traveller profile (weights), default budget_traveller")
    g.add_argument("--weights", metavar="NAME=N,...",
                   help="own weights instead of a profile, e.g. price=40,duration=25,"
                        "departure=15,flexibility=20 (adding up to 100 or 1.0)")
    g.add_argument("--top", type=int, default=DEFAULT_TOP,
                   help=f"how many ranked offers to show (default {DEFAULT_TOP})")
    return p


def _print_load_summary(companies, destinations, profiles, result, path) -> None:
    print("=== BusBidder Spain ===")
    print(f"Companies    : {len(companies)}")
    print(f"Destinations : {len(destinations)}")
    print(f"Profiles     : {', '.join(profiles)}")
    print(f"Offers       : {len(result.offers)} loaded, {len(result.rejected)} rejected ({path})")
    if result.rejected:
        print("\nRejected records (details in logs/busbidder.log):")
        for rec in result.rejected[:MAX_REJECTED_SHOWN]:
            print(f"  row {rec.row:>3}  {rec.offer_id:<9} {rec.category}: {rec.message}")
        if len(result.rejected) > MAX_REJECTED_SHOWN:
            print(f"  ... and {len(result.rejected) - MAX_REJECTED_SHOWN} more")


def _duration_text(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}"


def _print_ranking(ranked: list[RankedOffer], weights: dict, top: int) -> None:
    names = list(weights)
    print(f"\nRANKING ({len(ranked)} offers, best first). Scores are 0-100, higher is better; "
          "price, duration and\nemissions are scored relative to these offers, see docs/scoring.md.")
    head = (f"{'#':>3}  {'Offer':<8} {'Company':<15} {'Departure':<12} {'EUR':>6} {'Dur':>6} "
            f"{'Tr':>2} {'Fare':<8}")
    head += " |" + "".join(f" {n[:6]:>6}" for n in names) + " | TOTAL"
    print(head)
    for r in ranked[:top]:
        o = r.offer
        row = (f"{r.rank:>3}  {o.offer_id:<8} {o.company:<15} "
               f"{o.travel_date:%d %b} {o.departure_time:%H:%M} {o.price:>6.2f} "
               f"{_duration_text(o.duration_minutes):>6} {o.transfers:>2} {o.fare.fare_type:<8}")
        row += " |" + "".join(f" {r.criterion_scores[n]:>6.1f}" for n in names)
        row += f" | {r.total_score:>5.1f}" + ("  (tie-break)" if r.tie_broken else "")
        print(row)
    if len(ranked) > top:
        print(f"... {len(ranked) - top} more offers not shown (use --top)")
    shares = influence_share(ranked, weights)
    print("\nWeight vs. real influence on the order (weight x spread of the scores):")
    for n in names:
        print(f"  {n:<12} weight {weights[n]*100:>3.0f}%   influence {shares[n]*100:>3.0f}%")


def _print_search(request: TravelRequest, weights: dict, marketplace: Marketplace,
                  top: int) -> None:
    label = "custom weights" if request.profile == "(custom)" else f"profile {request.profile}"
    print(f"\nRequest: Madrid to {request.destination}, "
          f"{request.date_from} to {request.date_to}, {label}")
    print("\nHARD constraints (an offer that breaks one is removed before ranking):")
    for line in hard_constraint_lines(request):
        print(f"  - {line}")
    print("\nSOFT preferences (only affect the score, never remove an offer):")
    for line in soft_preference_lines(request, weights):
        print(f"  - {line}")
    print("  (price is both: the budget is hard, and within it a lower price scores higher)\n")

    result, ranked = marketplace.search(request, weights)
    for line in result.report_lines():
        print(line)
    if ranked:
        _print_ranking(ranked, weights, top)


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.destination and None in (args.date_from, args.date_to, args.budget):
        parser.error("--destination also needs --from, --to and --budget")

    log = setup_logging()
    log.info("BusBidder started")

    try:
        companies = load_companies()
        destinations = load_destinations()
        profiles = load_profiles()
        set_config(load_scoring_config())
        result = load_offers(args.offers,
                             [d.name for d in destinations], [c.name for c in companies])
    except DataFileError as err:
        print(f"Error: {err}")
        return 1

    _print_load_summary(companies, destinations, profiles, result, args.offers)

    if not args.destination:
        print("\nTip: add --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 "
              "to filter and rank offers.")
        return 0

    try:
        if args.weights:
            weights, profile = parse_weights(args.weights), "(custom)"
        elif args.profile in profiles:
            weights, profile = profiles[args.profile], args.profile
        else:
            print(f"\nInvalid request: unknown profile '{args.profile}' "
                  f"(choose from: {', '.join(profiles)})")
            return 2
        request = TravelRequest(
            destination=args.destination, date_from=args.date_from, date_to=args.date_to,
            max_budget=args.budget, max_transfers=args.max_transfers,
            require_changeable=args.changeable, min_luggage_kg=args.min_luggage,
            max_duration_minutes=None if args.max_hours is None else round(args.max_hours * 60),
            preferred_departure=args.preferred_departure, profile=profile)
        marketplace = Marketplace(companies, destinations, result.offers, profiles)
        _print_search(request, weights, marketplace, max(1, args.top))
    except BusBidderError as err:
        log.warning("Invalid request: %s", err)
        print(f"\nInvalid request: {getattr(err, 'message', err)}")
        return 2
    print("\n(Filtering and ranking done. Next: Phase 6, explanation and profile comparison. See README.)")
    return 0
