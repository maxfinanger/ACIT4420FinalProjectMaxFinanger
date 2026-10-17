"""Command-line interface. Starts simple; grows with each phase.

Phase 3: load and validate the data.
Phase 4: describe a traveller request and show which offers survive the hard
constraints (use --destination ...).
Phase 5: rank the survivors with the weighted scoring model and show the score of
every criterion.
Phase 6: explain the top offer (advantages, drawbacks, comparison, caveat) and
compare traveller profiles (--compare-profiles).
Phase 7: book an offer from the ranking (--book 1 --name "Ana Perez"). The interactive
menu comes in Phase 8.

Exit codes: 0 ok, 1 a data file is missing or unreadable, 2 invalid request or selection,
3 the booking was refused (sold out, duplicate).
"""
import os
import random
import argparse
from datetime import date, time

from .booking import (BookingService, format_booking_list, format_confirmation,
                      select_from_ranking)
from .exceptions import BookingError, BusBidderError, DataFileError, ValidationError
from .display import print_compare, print_load_summary, print_search
from .interactive import run_interactive
from .loader import (load_companies, load_destinations, load_offers, load_profiles,
                     load_scoring_config, parse_date, parse_time)
from .log_setup import setup_logging
from .marketplace import Marketplace
from .models import TravelRequest
from .ranking import parse_weights
from .scoring_config import set_config

DEFAULT_BOOKINGS_FILE = "data/bookings.json"
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
    p.add_argument("-i", "--interactive", action="store_true",
                   help="guided menu: search, rank, compare profiles and book step by step")
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
    g.add_argument("--compare-profiles", action="store_true",
                   help="rank the same offers for every profile and compare the winners")
    b = p.add_argument_group("booking (simulated, no payment data is collected)")
    b.add_argument("--book", metavar="RANK|OFFER_ID",
                   help="book one seat from the ranking: a rank number (1) or an offer id (OF-1025)")
    b.add_argument("--name", help="traveller name for the booking (letters only, no digits)")
    b.add_argument("--bookings", default=DEFAULT_BOOKINGS_FILE, metavar="FILE",
                   help=f"bookings file (default: {DEFAULT_BOOKINGS_FILE})")
    b.add_argument("--show-bookings", action="store_true", help="list the saved bookings and exit")
    g.add_argument("--top", type=int, default=DEFAULT_TOP,
                   help=f"how many ranked offers to show (default {DEFAULT_TOP})")
    return p


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.destination and None in (args.date_from, args.date_to, args.budget):
        parser.error("--destination also needs --from, --to and --budget")
    if args.interactive and (args.destination or args.book or args.compare_profiles
                             or args.show_bookings):
        parser.error("--interactive asks for everything itself, so it cannot be combined with "
                     "--destination, --book, --compare-profiles or --show-bookings")
    if args.book and not args.destination:
        parser.error("--book needs a request (--destination, --from, --to, --budget) to choose from")
    if args.book and not args.name:
        parser.error("--book also needs --name")
    if args.book and args.compare_profiles:
        parser.error("--book cannot be combined with --compare-profiles")
    seed = os.environ.get("BUSBIDDER_SEED")
    if seed is not None and not seed.lstrip("-").isdigit():
        parser.error("BUSBIDDER_SEED must be a whole number")

    log = setup_logging()
    log.info("BusBidder started")

    try:
        companies = load_companies()
        destinations = load_destinations()
        profiles = load_profiles()
        set_config(load_scoring_config())
        result = load_offers(args.offers,
                             [d.name for d in destinations], [c.name for c in companies])
        # BUSBIDDER_SEED makes booking references reproducible (for demos and the report)
        service = BookingService(args.bookings,
                                 rng=random.Random(int(seed)) if seed is not None else None)
        service.apply_to_offers(result.offers)
        print_load_summary(companies, destinations, profiles, result, args.offers, service)
    except DataFileError as err:
        print(f"Error: {err}")
        return 1

    if args.show_bookings:
        print("\n" + format_booking_list(service.load()))
        return 0

    if args.interactive:
        return run_interactive(Marketplace(companies, destinations, result.offers, profiles, service),
                               top=max(1, args.top))

    if not args.destination:
        print("\nTip: run with --interactive for a guided menu, or add --destination Malaga "
              "--from 2026-07-12 --to 2026-07-14 --budget 50 to filter and rank offers.")
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
        marketplace = Marketplace(companies, destinations, result.offers, profiles, service)
        if args.compare_profiles:
            print_compare(request, marketplace)
            ranked = []
        else:
            ranked = print_search(request, weights, marketplace, max(1, args.top))
        chosen = select_from_ranking(ranked, args.book) if args.book else None
    except BookingError as err:
        print(f"\nBooking refused: {err}")
        return 3
    except BusBidderError as err:
        log.warning("Invalid request: %s", err)
        print(f"\nInvalid request: {getattr(err, 'message', err)}")
        return 2
    if chosen is not None:
        try:
            booking = marketplace.book(chosen.offer, args.name)
        except BookingError as err:
            log.warning("Booking refused: %s", err)
            print(f"\nBooking refused: {err}")
            return 3
        except (ValidationError, DataFileError) as err:
            print(f"\nBooking not made: {getattr(err, 'message', err)}")
            return 2 if isinstance(err, ValidationError) else 1
        print("\n" + format_confirmation(booking, chosen.offer.seats_available,
                                         chosen.rank, chosen.total_score))

    print("\n(Done. Next: Phase 9, evaluation. See README.)")
    return 0
