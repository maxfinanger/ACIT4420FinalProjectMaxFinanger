"""Command-line interface. Starts very simple; grows with each phase."""
import argparse

from .exceptions import DataFileError
from .loader import load_companies, load_destinations, load_offers, load_profiles
from .log_setup import setup_logging

MAX_REJECTED_SHOWN = 25


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="main.py", description="BusBidder Spain")
    parser.add_argument("--offers", default="data/offers.csv",
                        help="offers CSV file (default: data/offers.csv)")
    args = parser.parse_args(argv)

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

    print("=== BusBidder Spain ===")
    print(f"Companies    : {len(companies)}")
    print(f"Destinations : {len(destinations)}")
    print(f"Profiles     : {', '.join(profiles)}")
    print(f"Offers       : {len(result.offers)} loaded, {len(result.rejected)} rejected "
          f"({args.offers})")

    if result.rejected:
        print("\nRejected records (details in logs/busbidder.log):")
        for rec in result.rejected[:MAX_REJECTED_SHOWN]:
            print(f"  row {rec.row:>3}  {rec.offer_id:<9} {rec.category}: {rec.message}")
        if len(result.rejected) > MAX_REJECTED_SHOWN:
            print(f"  ... and {len(result.rejected) - MAX_REJECTED_SHOWN} more")

    print("\n(Loading and validation done. Next: Phase 4, filtering. See README.)")
    return 0
