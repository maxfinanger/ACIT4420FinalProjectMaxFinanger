"""Print a transcript of an interactive session with scripted answers (for the report).

    python scripts/demo_interactive.py > docs/examples/interactive_session.txt

The answers are echoed after each question, so the transcript reads like a real session. It uses a
temporary bookings file and a fixed seed, so the output is the same every time and nothing is saved
in data/bookings.json.
"""
import random
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so it runs as a plain script

from busbidder.booking import BookingService
from busbidder.interactive import run_interactive
from busbidder.loader import (load_companies, load_destinations, load_offers, load_profiles,
                              load_scoring_config)
from busbidder.marketplace import Marketplace
from busbidder.scoring_config import set_config

ANSWERS = [
    "1",                                    # new search
    "Malga", "Málaga",                      # a typo is explained, accents are fine
    "tomorrow", "12/07/2026",               # not a date, then day/month/year
    "2026-07-11", "14.7.2026",              # latest date before the earliest, then fine
    "abc", "49,90",                         # not a number, then a comma as decimal sign
    "1", "y", "9.30", "",                   # one transfer, changeable, 09:30, default profile
    "n",                                    # no extra limits
    "3", "business_traveller",              # rank the same offers for another profile
    "5", "2", "Ana Pérez", "n",             # choose rank 2, then decline the confirmation
    "5", "OF-1032", "Ana 2", "Ana Pérez", "y",   # a digit in the name is refused, then book
    "5", "OF-1032", "ana pérez", "y",       # the same name twice on one offer is refused
    "6",                                    # saved bookings
    "0",                                    # quit
]


def main() -> None:
    set_config(load_scoring_config())
    companies, destinations = load_companies(), load_destinations()
    offers = load_offers("data/offers.csv", [d.name for d in destinations],
                         [c.name for c in companies]).offers
    with tempfile.TemporaryDirectory() as folder:
        service = BookingService(Path(folder) / "bookings.json", rng=random.Random(7))
        service.apply_to_offers(offers)
        market = Marketplace(companies, destinations, offers, load_profiles(), service)
        answers = iter(ANSWERS)

        def scripted(prompt: str = "") -> str:
            try:
                answer = next(answers)
            except StopIteration:
                raise EOFError from None
            print(f"{prompt}{answer}")
            return answer

        run_interactive(market, scripted, top=5)


if __name__ == "__main__":
    main()
