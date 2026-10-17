"""Interactive menu (Phase 8): the same features as the command-line options, step by step.

    python main.py --interactive

Design (decision D21, docs/interface.md):
  - Answers are checked by small pure parse_* functions. A bad answer gives a helpful message and
    the question is asked again; `q` cancels back to the menu, and too many bad answers cancel too.
  - Friendly input: accents and capital letters do not matter (Málaga = malaga), a unique start of
    a name is enough (san seb), dates may be 2026-07-12 or 12/07/2026, money may be 49,90 or EUR 50,
    times may be 9, 9:30 or 9.30, journey time may be 6, 6.5 or 6h30.
  - Booking asks for an explicit yes before anything is saved.
  - Everything shown comes from display.py, so it is identical to the command-line output.
  - `input_fn` can be replaced, so the whole session is tested with scripted answers.
"""
import difflib
import re
import unicodedata
from dataclasses import replace
from datetime import date, time
from typing import Callable

from .booking import format_booking_list, format_confirmation, select_from_ranking
from .display import print_compare, print_ranking, print_search
from .exceptions import (BookingError, BusBidderError, DataFileError, DuplicateBookingError,
                         SoldOutError, ValidationError)
from .loader import parse_date
from .marketplace import Marketplace
from .models import RankedOffer, TravelRequest
from .ranking import parse_weights
from .validation import clean_traveller_name

DEFAULT_TOP = 10
MAX_ATTEMPTS = 8                      # bad answers in a row before a question is cancelled
CANCEL_WORDS = {"q", "quit", "cancel"}
MENU = [
    (1, "New search"),
    (2, "Show all ranked offers of the last search"),
    (3, "Rank the last search again with another profile or your own weights"),
    (4, "Compare the traveller profiles on the last search"),
    (5, "Book an offer from the last search"),
    (6, "Show saved bookings"),
    (7, "Help"),
    (0, "Quit"),
]
CUSTOM = "(custom)"


class Cancelled(Exception):
    """The user typed q, or gave too many bad answers: go back to the menu."""


def _err(message: str) -> ValidationError:
    return ValidationError("invalid_input", message)


# ---------------------------------------------------------------------------
# Parsing answers (pure functions, each raises ValidationError with a helpful message)
# ---------------------------------------------------------------------------
def normalise(text: str) -> str:
    """Lower case, no accents, single spaces: 'Málaga ' and 'malaga' are the same."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def parse_destination(text: str, names: list[str]) -> str:
    t = text.strip()
    if not t:
        raise _err("Please enter a destination: a number from the list, or a name.")
    if t.isdigit():
        n = int(t)
        if 1 <= n <= len(names):
            return names[n - 1]
        raise _err(f"Choose a number between 1 and {len(names)}.")
    by_key = {normalise(n): n for n in names}
    key = normalise(t)
    if key in by_key:
        return by_key[key]
    starts = [n for k, n in by_key.items() if len(key) >= 3 and k.startswith(key)]
    if len(starts) == 1:
        return starts[0]
    close = starts or [by_key[k] for k in difflib.get_close_matches(key, list(by_key), n=3, cutoff=0.6)]
    if close:
        raise _err(f"'{t}' is not a destination. Did you mean: {', '.join(close)}?")
    raise _err(f"'{t}' is not a destination. Type a number from the list or one of the names shown.")


def parse_date_input(text: str, not_before: date | None = None) -> date:
    t = text.strip()
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", t)         # 12/07/2026 or 12.7.2026
    if m:
        t = f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    try:
        value = parse_date(t, "date")
    except ValidationError:
        raise _err("Dates look like 2026-07-12 (year-month-day) or 12/07/2026 (day/month/year), "
                   "and must be real dates.") from None
    if not_before is not None and value < not_before:
        raise _err(f"The latest date cannot be before the earliest ({not_before}).")
    return value


_MONEY = re.compile(r"\A(?:€|eur\s*)?\s*(\d+(?:[.,]\d{1,2})?)\s*(?:€|eur)?\Z", re.IGNORECASE)


def parse_money(text: str) -> float:
    m = _MONEY.match(text.strip())
    value = float(m[1].replace(",", ".")) if m else 0.0
    if not m or value <= 0:
        raise _err("Enter the maximum price in euros as a number above 0, e.g. 50 or 49,90.")
    return value


def parse_transfers(text: str) -> int | None:
    t = normalise(text)
    if t in ("", "any", "none", "no limit", "unlimited"):
        return None
    if t == "direct":
        return 0
    if t.isdigit() and int(t) <= 9:
        return int(t)
    raise _err("Enter a whole number from 0 to 9 (0 = direct only), or leave it empty for no limit.")


def parse_hours(text: str) -> int | None:
    """Maximum journey time in MINUTES (or None for no limit)."""
    t = normalise(text)
    if not t:
        return None
    m = re.fullmatch(r"(\d{1,2})\s*h\s*(?:(\d{1,2})\s*(?:m|min)?)?", t)
    if m:
        minutes = int(m[1]) * 60 + int(m[2] or 0)
        if int(m[2] or 0) >= 60:
            minutes = 0
    elif re.fullmatch(r"\d+(?:[.,]\d+)?", t):
        minutes = round(float(t.replace(",", ".")) * 60)
    else:
        minutes = 0
    if not 0 < minutes <= 48 * 60:
        raise _err("Enter the longest journey in hours, e.g. 6, 6.5 or 6h30 (at most 48), "
                   "or leave it empty for no limit.")
    return minutes


def parse_luggage(text: str) -> int:
    t = normalise(text)
    if not t:
        return 0
    m = re.fullmatch(r"(\d{1,3})\s*(?:kg)?", t)
    if not m:
        raise _err("Enter the luggage allowance you need in kg, e.g. 20, or leave it empty for no requirement.")
    return int(m[1])


def parse_yes_no(text: str, default: bool) -> bool:
    t = normalise(text)
    if not t:
        return default
    if t in ("y", "yes", "j", "ja"):
        return True
    if t in ("n", "no", "nei"):
        return False
    raise _err("Please answer y (yes) or n (no).")


def parse_clock(text: str, default: time) -> time:
    t = text.strip()
    if not t:
        return default
    m = re.fullmatch(r"(\d{1,2})(?:[:.](\d{2}))?", t)
    if m and int(m[1]) <= 23 and int(m[2] or 0) <= 59:
        return time(int(m[1]), int(m[2] or 0))
    raise _err("Times look like 09:00, 9:30 or 9.30 (24-hour clock).")


def parse_profile_choice(text: str, names: list[str], default: str) -> str:
    t = normalise(text)
    if not t:
        return default
    if t in ("c", "custom", "own"):
        return CUSTOM
    if t.isdigit():
        if 1 <= int(t) <= len(names):
            return names[int(t) - 1]
        raise _err(f"Choose a number between 1 and {len(names)}, or c for your own weights.")
    for name in names:
        if normalise(name) == t:
            return name
    raise _err(f"Unknown profile '{text.strip()}'. Choose a number from the list, a name, or c for your own weights.")


def parse_weights_input(text: str) -> dict:
    try:
        return parse_weights(text)
    except BusBidderError as err:
        raise _err(f"{err}. Example: price=40,duration=25,departure=15,flexibility=20 "
                   "(the numbers add up to 100).") from None


# ---------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------
HELP = """HELP
  The program finds bus offers from Madrid and ranks them for you in two steps:
    1. HARD requirements remove offers completely: destination, dates, budget, free seats,
       and (only if you set them) transfers, journey time, luggage, a changeable ticket.
    2. SOFT preferences only change the score: preferred departure time, journey duration,
       price within your budget, flexibility. How much each counts is set by the profile
       (budget traveller, business traveller, ...) or by your own weights.
  The best offer is only best under YOUR requirements and the chosen weights.
  Tips: press Enter to accept the value in [brackets]; type q to cancel a question;
  accents and capital letters do not matter (Malaga = málaga).
  Booking is simulated: no payment is taken, and names cannot contain digits."""


class InteractiveSession:
    def __init__(self, marketplace: Marketplace, input_fn: Callable[[str], str] | None = None,
                 top: int = DEFAULT_TOP):
        self.market = marketplace
        # `input` is looked up when a question is asked, not when this class is defined, so it can
        # be replaced later (by tests, or by a program that wraps this one)
        self._input = input_fn if input_fn is not None else (lambda prompt="": input(prompt))
        self.top = top
        self.request: TravelRequest | None = None
        self.weights: dict | None = None
        self.ranked: list[RankedOffer] = []

    # ---- asking ------------------------------------------------------------
    def ask(self, label: str, parser: Callable, hint: str = ""):
        """Ask until `parser` accepts the answer. q cancels, EOFError/KeyboardInterrupt end the session."""
        for _ in range(MAX_ATTEMPTS):
            text = self._input(f"{label}{' ' + hint if hint else ''}: ")
            if text.strip().lower() in CANCEL_WORDS:
                raise Cancelled("Cancelled.")
            try:
                return parser(text)
            except ValidationError as err:
                print(f"  ! {err.message}  (q = cancel)")
        raise Cancelled("Too many answers I could not understand, so I cancelled the question.")

    def _choose_action(self) -> int:
        for _ in range(MAX_ATTEMPTS):
            text = self._input("Choose an option (0-7): ").strip().lower()
            if text in ("0", "q", "quit", "exit"):
                return 0
            if text.isdigit() and 1 <= int(text) <= 7:
                return int(text)
            print("  ! Please type a number from 0 to 7 (0 quits).")
        print("Too many answers I could not understand.")
        return 0

    @staticmethod
    def _print_menu() -> None:
        print("\nMENU")
        for number, text in MENU:
            print(f"  {number}) {text}")

    def _need_search(self) -> bool:
        if self.request is None:
            print("  ! Do a search first (option 1).")
            return False
        return True

    # ---- main loop ----------------------------------------------------------
    def run(self) -> int:
        print("\n=== BusBidder Spain: interactive mode ===")
        print("Find and book a bus from Madrid. Type q to cancel a question, and 0 at the menu to quit.")
        actions = {1: self._new_search, 2: self._show_all, 3: self._rerank, 4: self._compare,
                   5: self._book, 6: self._bookings, 7: lambda: print("\n" + HELP)}
        try:
            while True:
                self._print_menu()
                choice = self._choose_action()
                if choice == 0:
                    print("Goodbye.")
                    return 0
                try:
                    actions[choice]()
                except Cancelled as cancel:
                    print(f"  {cancel} Back to the menu.")
        except (EOFError, KeyboardInterrupt):
            print("\nInput ended. Goodbye.")
            return 0

    # ---- the questions shared by search and re-ranking ---------------------
    def _ask_profile(self) -> tuple[str, dict]:
        profiles = self.market.profiles
        names = list(profiles)
        print("\nTraveller profiles (they set how much each criterion counts):")
        for i, name in enumerate(names, start=1):
            w = ", ".join(f"{k} {v * 100:.0f}%" for k, v in profiles[name].items() if v > 0)
            print(f"  {i}) {name:<20} {w}")
        print("  c) your own weights")
        default = names[0]
        choice = self.ask("Profile", lambda t: parse_profile_choice(t, names, default),
                          f"(number or name, c = own, Enter = {default})")
        if choice == CUSTOM:
            weights = self.ask("Weights", parse_weights_input,
                               "(e.g. price=40,duration=25,departure=15,flexibility=20)")
            return CUSTOM, weights
        return choice, profiles[choice]

    # ---- 1: new search -----------------------------------------------------
    def _new_search(self) -> None:
        names = [d.name for d in self.market.destinations]
        print("\nDestinations (every trip starts in Madrid):")
        for i in range(0, len(names), 3):
            print("  " + "".join(f"{j + 1:>2}) {names[j]:<24}" for j in range(i, min(i + 3, len(names)))))
        destination = self.ask("Destination", lambda t: parse_destination(t, names), "(number or name)")

        days = sorted({o.travel_date for o in self.market.offers})
        if days:
            print(f"  (offers exist for {days[0]} to {days[-1]})")
        date_from = self.ask("Earliest departure date", parse_date_input, "(e.g. 2026-07-12)")
        date_to = self.ask("Latest departure date", lambda t: date_from if not t.strip()
                           else parse_date_input(t, date_from), "(Enter = same day)")
        if days and (date_to < days[0] or date_from > days[-1]):
            print(f"  Note: there are no offers for those dates, so nothing will match.")
        budget = self.ask("Maximum price in EUR", parse_money, "(e.g. 50)")
        transfers = self.ask("Maximum transfers", parse_transfers, "(0 = direct only, Enter = no limit)")
        changeable = self.ask("Must the ticket be changeable?", lambda t: parse_yes_no(t, False), "[y/N]")
        preferred = self.ask("Preferred departure time", lambda t: parse_clock(t, time(9, 0)), "(Enter = 09:00)")
        label, weights = self._ask_profile()
        max_minutes, luggage = None, 0
        if self.ask("Set a journey-time or luggage limit too?", lambda t: parse_yes_no(t, False), "[y/N]"):
            max_minutes = self.ask("Longest journey in hours", parse_hours, "(e.g. 7 or 6h30, Enter = no limit)")
            luggage = self.ask("Luggage allowance needed in kg", parse_luggage, "(Enter = no requirement)")

        request = TravelRequest(destination=destination, date_from=date_from, date_to=date_to,
                                max_budget=budget, max_transfers=transfers, require_changeable=changeable,
                                min_luggage_kg=luggage, max_duration_minutes=max_minutes,
                                preferred_departure=preferred, profile=label)
        self._search(request, weights)

    def _search(self, request: TravelRequest, weights: dict) -> None:
        try:
            ranked = print_search(request, weights, self.market, self.top)
        except BusBidderError as err:
            print(f"  ! Invalid request: {getattr(err, 'message', err)}")
            return
        self.request, self.weights, self.ranked = request, weights, ranked
        if ranked:
            print("\n  Next: 5 books an offer, 3 ranks again with other weights, 4 compares profiles, "
                  "2 shows every offer.")
        else:
            print("\n  Nothing to choose from. Try a higher budget or wider dates (see the hint above).")

    # ---- 2, 3, 4 ----------------------------------------------------------------
    def _show_all(self) -> None:
        if not self._need_search():
            return
        if not self.ranked:
            print("  ! The last search found no offers.")
            return
        print_ranking(self.ranked, self.weights, len(self.ranked))

    def _rerank(self) -> None:
        if not self._need_search():
            return
        label, weights = self._ask_profile()
        self._search(replace(self.request, profile=label), weights)

    def _compare(self) -> None:
        if not self._need_search():
            return
        try:
            print_compare(self.request, self.market)
        except BusBidderError as err:
            print(f"  ! {getattr(err, 'message', err)}")

    # ---- 5: booking ---------------------------------------------------------
    def _book(self) -> None:
        if self.market.bookings is None:
            print("  ! Booking is not available in this session.")
            return
        if not self._need_search():
            return
        if not self.ranked:
            print("  ! There are no offers to choose from in the last search.")
            return
        chosen = self.ask("Which offer? Rank number or offer id", lambda t: select_from_ranking(self.ranked, t),
                          "(e.g. 1 or OF-1025)")
        o = chosen.offer
        print(f"  Selected: rank {chosen.rank}, {o.offer_id}, {o.company}, {o.travel_date:%a %d %b} "
              f"{o.departure_time:%H:%M} to {o.arrival_time:%H:%M}, EUR {o.price:.2f}, {o.fare.fare_type} fare "
              f"(changeable: {'yes' if o.fare.changeable else 'no'}, refundable: {'yes' if o.fare.refundable else 'no'}), "
              f"{o.seats_available} seats left")
        name = self.ask("Traveller name", clean_traveller_name, "(letters only)")
        if not self.ask(f"Book {o.offer_id} for {name}? Payment is simulated.", lambda t: parse_yes_no(t, False), "[y/N]"):
            print("  Booking cancelled, nothing was saved.")
            return
        try:
            booking = self.market.book(o, name)
        except SoldOutError:
            print(f"  ! Sorry, {o.offer_id} is sold out. Do a new search (option 1) to refresh the list.")
            return
        except DuplicateBookingError:
            print(f"  ! {name} already has a booking on {o.offer_id}. Use another name for another traveller.")
            return
        except (BookingError, ValidationError, DataFileError) as err:
            print(f"  ! The booking was not made: {getattr(err, 'message', err)}")
            return
        print("\n" + format_confirmation(booking, o.seats_available, chosen.rank, chosen.total_score))

    # ---- 6: bookings ----------------------------------------------------------
    def _bookings(self) -> None:
        if self.market.bookings is None:
            print("  ! Booking is not available in this session.")
            return
        try:
            print("\n" + format_booking_list(self.market.bookings.load()))
        except DataFileError as err:
            print(f"  ! {err}")


def run_interactive(marketplace: Marketplace, input_fn: Callable[[str], str] | None = None,
                    top: int = DEFAULT_TOP) -> int:
    return InteractiveSession(marketplace, input_fn, top).run()
