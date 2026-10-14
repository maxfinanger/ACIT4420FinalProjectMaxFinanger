"""Command-line interface. Starts simple; grows with each phase.

Phase 3: load and validate the data.
Phase 4: describe a traveller request and show which offers survive the hard
constraints (use --destination ...). Ranking comes in Phase 5, the interactive
menu in Phase 8.
"""
import argparse
from datetime import date, time

from .exceptions import DataFileError, ValidationError
from .filtering import hard_constraint_lines, soft_preference_lines
from .loader import (load_companies, load_destinations, load_offers, load_profiles,
                     parse_date, parse_time)
from .log_setup import setup_logging
from .marketplace import Marketplace
from .models import TravelRequest

MAX_REJECTED_SHOWN = 25
MAX_REMAINING_SHOWN = 10


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


def _print_filter(request: TravelRequest, weights: dict, marketplace: Marketplace) -> None:
    print(f"\nRequest: Madrid to {request.destination}, "
          f"{request.date_from} to {request.date_to}, profile {request.profile}")
    print("\nHARD constraints (an offer that breaks one is removed before ranking):")
    for line in hard_constraint_lines(request):
        print(f"  - {line}")
    print("\nSOFT preferences (only affect the score, never remove an offer):")
    for line in soft_preference_lines(request, weights):
        print(f"  - {line}")
    print("  (price is both: the budget is hard, and within it a lower price scores higher)\n")

    result = marketplace.filter(request)
    for line in result.report_lines():
        print(line)
    if result.kept:
        shown = sorted(result.kept, key=lambda o: (o.travel_date, o.departure_time, o.price))
        print(f"\nRemaining offers, NOT ranked yet (first {min(len(shown), MAX_REMAINING_SHOWN)} "
              "by departure):")
        for o in shown[:MAX_REMAINING_SHOWN]:
            print(f"  {o.offer_id}  {o.company:<15} {o.travel_date} "
                  f"{o.departure_time:%H:%M}->{o.arrival_time:%H:%M}  EUR {o.price:>6.2f}  "
                  f"{o.transfers} transfer(s)  {o.fare.fare_type:<8} "
                  f"{'changeable' if o.fare.changeable else 'fixed'}")


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
        result = load_offers(args.offers,
                             [d.name for d in destinations], [c.name for c in companies])
    except DataFileError as err:
        print(f"Error: {err}")
        return 1

    _print_load_summary(companies, destinations, profiles, result, args.offers)

    if not args.destination:
        print("\nTip: add --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 "
              "to try the hard-constraint filter.")
        return 0

    if args.profile not in profiles:
        print(f"\nInvalid request: unknown profile '{args.profile}' "
              f"(choose from: {', '.join(profiles)})")
        return 2
    request = TravelRequest(
        destination=args.destination, date_from=args.date_from, date_to=args.date_to,
        max_budget=args.budget, max_transfers=args.max_transfers,
        require_changeable=args.changeable, min_luggage_kg=args.min_luggage,
        max_duration_minutes=None if args.max_hours is None else round(args.max_hours * 60),
        preferred_departure=args.preferred_departure, profile=args.profile)
    marketplace = Marketplace(companies, destinations, result.offers, profiles)
    try:
        _print_filter(request, profiles[args.profile], marketplace)
    except ValidationError as err:
        log.warning("Invalid request: %s", err)
        print(f"\nInvalid request: {err.message}")
        return 2
    print("\n(Filtering done. Next: Phase 5, weighted ranking. See README.)")
    return 0
