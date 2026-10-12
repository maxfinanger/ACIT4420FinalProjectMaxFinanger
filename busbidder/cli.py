"""Command-line interface. Starts very simple; grows with each phase."""
from .loader import load_companies, load_destinations, load_profiles
from .log_setup import setup_logging


def run() -> None:
    log = setup_logging()
    log.info("BusBidder started")

    companies = load_companies()
    destinations = load_destinations()
    profiles = load_profiles()

    print("=== BusBidder Spain ===")
    print(f"Companies    : {len(companies)}")
    print(f"Destinations : {len(destinations)}")
    print(f"Profiles     : {', '.join(profiles)}")
    print("\n(Skeleton and design in place. Next: Phase 3 (loading and validation), see README.)")
