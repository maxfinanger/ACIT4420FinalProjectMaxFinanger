# Design decisions log

Format: decision, alternatives I looked at, reason. Status is **Proposed** until
I have read it and agreed, then **Decided**. D1-D9 were reviewed after Phase 1. Final wording for the report comes
from here. Decisions marked "preliminary" will be confirmed in the phase named.

---

## D1. Standard library only, CSV and JSON files
- **Status:** Decided
- **Decision:** No third-party runtime libraries. Offers, companies and
  destinations are CSV files. Profiles/weights and bookings are JSON.
- **Alternatives:** pandas for data handling; SQLite for offers and bookings.
- **Reason:** The project is about scripting and design, and the dataset is small
  (a few hundred rows). CSV is easy to read and edit by hand, and a supervisor can
  run the program without installing anything. pandas would hide the validation
  logic I have to show. SQLite is better for concurrency, which is not needed here.

## D2. Classes where there is state or shared behaviour, functions elsewhere
- **Status:** Decided
- **Decision:**
  - Dataclasses for data: `Offer`, `FareConditions`, `TravelRequest`, `RankedOffer`, `Booking`, `Company`, `Destination`.
  - Classes for behaviour that has state or several variants: `Marketplace`, `BookingService`, the `Constraint` family.
  - Plain functions for stateless steps: loading, validation, normalisation, explanation.
- **Alternatives:** Everything as classes (loader class, validator class, ranker class); or everything as functions on dicts.
- **Reason:** A class should earn its place. A loader has no state worth keeping,
  so a function is simpler. A booking service must remember where bookings are
  stored, so a class fits. Dicts would lose type information and make the
  validation harder to explain.

## D3. Composition for fares and for the Marketplace
- **Status:** Decided
- **Decision:** An `Offer` has a `FareConditions` object (changeable, refundable,
  luggage) instead of three loose fields. A `Booking` stores a copy of the
  `FareConditions`. `Marketplace` holds the data and calls filtering and ranking.
- **Alternatives:** Flat fields on `Offer`; a `Fare` subclass of `Offer`.
- **Reason:** The spec requires that the booking stores the fare conditions. A
  small frozen object can be copied into the booking and cannot change later. An
  offer *is not* a kind of fare, so inheritance would be wrong here.

## D4. Inheritance for hard constraints
- **Status:** Decided
- **Decision:** Abstract base class `Constraint` with `is_satisfied()` and
  `reason()`. One subclass per hard constraint (`BudgetConstraint`,
  `DestinationConstraint`, `TravelWindowConstraint`, `SeatsConstraint`,
  `MaxTransfersConstraint`, `FlexibilityConstraint`). The custom exception
  hierarchy also inherits from one base `BusBidderError`.
- **Alternatives:** A list of small functions; one big function with `if` statements.
- **Reason:** Every constraint does the same two things (test an offer, explain
  why it was removed), so the shared interface is genuine. The `reason()` text
  is what makes the hard/soft split visible to the user ("removed: 4 over
  budget"). A new constraint can be added without touching `filter_offers`.
- **Where inheritance is NOT used:** the dataclasses, because there is no
  "is-a" relationship between them.

## D5. Metaprogramming: decorator-based registry of scoring criteria
- **Status:** Decided
- **Decision:** `@register_criterion("price")` adds a scoring function to a
  registry in `criteria.py`. The ranker looks criteria up by name, and weight
  validation checks that every name in the weights exists in the registry.
- **Alternatives considered:**
  - Logging/timing decorator: easy, but a weak fit for the problem.
  - Descriptors for validated fields: possible, but dataclasses plus a validation module already cover this.
  - Dynamic discovery of company modules: interesting, but the companies are only data here.
- **Reason:** Weights in `profiles.json` refer to criteria by name, so a registry
  is a natural link between configuration and code. Adding a criterion (rating,
  emissions) means writing and decorating one function. This also supports the
  required "traveller can express the relative importance" feature.
- **Check later:** is it still justified in the report, or is it over-engineering?
  I should be able to show one example of a criterion added without editing `ranking.py`.

## D6. Hard constraints versus soft preferences
- **Status:** Decided (confirmed in Phase 4)
- **Always hard (offer is removed):** destination, travel window (departure date, both
  end days included), seats available, and the budget.
- **Hard only if the traveller sets it:** maximum transfers, maximum journey time,
  minimum luggage allowance, and "ticket must be changeable". If it is not set, the
  condition is not a constraint at all, and (for duration and flexibility) it is a soft
  criterion instead.
- **Always soft (affects score only):** departure time versus the preferred time,
  journey duration (when there is no limit), flexibility (when not required), and the
  optional criteria rating and emissions.
- **Note:** Price is both. The budget is a hard limit, and within it a lower price
  still scores higher. The program says so on screen.
- **Reason:** A hard constraint is something where the traveller would not accept the
  offer at any score (they cannot travel on the wrong day or pay more than they have).
  A soft one is something that can be traded against other criteria. Letting the
  traveller decide for the optional limits means the same program serves both a person
  who needs a direct bus with luggage and a person who does not care. Full table with
  justifications: `docs/filtering.md`.

## D7. Invalid records are rejected and logged, not corrected
- **Status:** Decided (confirmed in Phase 3)
- **Decision:** A record that fails validation is skipped, written to the log
  with its id and reason, and counted. The program continues with the valid rows.
  If a whole file is missing, or the header is wrong, the program stops with a `DataFileError`.
- **Alternatives:** Correct obvious mistakes (e.g. swap arrival/departure); stop on the first error.
- **Reason:** Guessing a correction can silently produce a wrong offer, and a
  traveller could then book something that does not exist. Stopping on one bad
  row would make the program fragile.
- **Implemented (Phase 3):** `load_offers` returns a `LoadResult` with the accepted
  offers and a list of `RejectedRecord`s (row number, offer id, category, message).
  Each rejection is also written to `logs/busbidder.log` as a warning. "Set aside"
  therefore means: kept in the result and the log for review, never used in
  filtering or ranking. The only tolerated clean-ups are harmless ones: surrounding
  whitespace is stripped, yes/no is case-insensitive, and a UTF-8 BOM is ignored.
  A repeated offer id is rejected (first valid row wins). Problems with a whole file
  (missing, empty, wrong header, unreadable) raise `DataFileError` instead.

## D8. Command-line interface first
- **Status:** Decided
- **Decision:** A CLI is enough for the core project. A GUI/web interface is only an optional extension.
- **Reason:** The assessment focuses on design, evaluation and the report, so
  effort is better spent on testing and evaluation.

## D9. The offers file is never modified
- **Status:** Decided
- **Decision:** `data/offers.csv` stays unchanged. Seats left for an offer are
  computed as seats in the file minus seats already booked in `data/bookings.json`.
- **Alternatives:** Rewrite `offers.csv` after each booking; keep seat counts only in memory.
- **Reason:** The report findings must be reproducible from the same input
  data, so the source data should not change when someone books. It also makes
  "reduce capacity consistently" easy to test, because the bookings file is the
  single source of truth for seats sold.
- **Consequence for filtering:** `SeatsConstraint` only checks `seats_available >= 1`. In
  Phase 7 the Marketplace subtracts booked seats from the offers when it starts, so the
  constraint stays simple. Until then it never removes anything (validation already rejects
  rows without seats).

## D10. The dataset is generated by a seeded script and committed
- **Status:** Decided
- **Decision:** `scripts/generate_data.py` creates `data/offers.csv` (and the invalid
  test file) with a fixed random seed. The generated files are kept in the repository.
  The differences between the companies are defined in one place in the script.
- **Alternatives:** Writing 75+ rows by hand; generating the data every time the program starts.
- **Reason:** By hand, 1000+ rows with consistent prices and times is not realistic,
  and errors would be hard to find. A fixed seed makes the dataset reproducible for the
  report. Committing the files means the program runs without a generation step, and a test
  checks that the file and the script still agree. Company behaviour as parameters (price
  level, speed, departure times, transfers, fare types) makes the "how do the companies
  differ" decision explicit and easy to explain.

## D11. Overnight journeys are represented with an arrival date
- **Status:** Decided
- **Decision:** Each offer has `travel_date` (departure) and `arrival_date`.
  Duration = arrival datetime minus departure datetime. Validation "arrival before
  departure" compares full datetimes, and a maximum plausible duration of 24 hours catches
  impossible rows.
- **Alternatives:** Only times (arrival "before" departure means next day); a stored duration column;
  an `overnight` flag.
- **Reason:** With only times, an overnight NocheVia bus would look exactly like an invalid
  record. A stored duration could contradict the times. With two full dates the duration is
  always derived and there is nothing to keep consistent.

## D12. Fare types decide the fare conditions
- **Status:** Decided
- **Decision:** Every departure is sold in 1-3 fare types (Basic, Standard, Flex) with
  different price, changeable, refundable and luggage values. Each fare type is a separate
  offer row with its own seat count.
- **Alternatives:** One row per departure with a fare-conditions table on the side.
- **Reason:** The spec treats price and flexibility as trade-offs, and the same bus with a
  cheaper non-changeable fare and a more expensive flexible fare is exactly that trade-off. One
  row per fare keeps the filtering and ranking code simple (an offer is one thing to score).
  The simplification is that fare types do not share seats on the same bus.

## D13. Two-step validation, and where regular expressions are (not) used
- **Status:** Decided
- **Decision:** `loader.build_offer` converts text to types and reports format errors
  (bad id, date, time, number, yes/no). `validation.validate_offer` then checks the
  business rules on a typed `Offer` (ranges, known company and destination, arrival
  after departure, maximum duration). Both raise `ValidationError` with a `category`.
  Regular expressions are used for: offer id (`OF-0001`), booking reference
  (`BB-20260712-A1B2C3`), date (`YYYY-MM-DD`) and time (`HH:MM`). They are NOT used
  for numbers, names or yes/no values.
- **Alternatives:** One big validation function on raw text; a regex for every field;
  a validation library.
- **Reason:** Splitting format from meaning keeps each function short and lets the
  rules be tested directly on `Offer` objects (including boundaries such as exactly
  24 hours). A regex fits fixed-format identifiers and timestamps, but for numbers it
  is the wrong tool: `float()` already parses them, and "price above 0" or "rating
  between 0 and 5" are comparisons. The spec asks for regexes only "where genuinely
  suitable", so the list above is deliberately short.
- **Found by testing:** the first version used `^...$`, but `$` also matches before a
  trailing newline, so `"OF-0001\n"` was accepted. The patterns now use `\A...\Z`.

## D14. How filtering reports what it removed
- **Status:** Decided
- **Decision:** Each removed offer is counted once, under the FIRST active constraint it
  fails, in a fixed order (destination, window, seats, budget, transfers, duration,
  luggage, changeable). Active constraints with zero removals are still listed. In addition
  the filter records "near misses" (offers that fail only one constraint). If nothing
  survives, the message names the constraint whose relaxing would give back most offers.
  The traveller's request is validated first (window, budget, limits, known destination).
- **Alternatives:** Count every violation per constraint (the numbers overlap and do not
  add up); only return the surviving list; silently return nothing for impossible requests.
- **Reason:** "Removed: 1373 wrong destination, 49 outside window, 9 over budget ..." adds
  up to the number of removed offers, so the user can follow it. The order puts WHICH trip
  first, so budget counts mean "right trip, too expensive". Showing zeros proves a
  constraint was checked. The hint turns an empty result into something to act on.
- **Trade-off:** the counts depend on the order, so a constraint late in the list can look
  less important than it is. The near-miss numbers (order independent) give the other view.

---

## Still to decide (not in the list above)

- Exact normalisation method for each criterion (Phase 5): min-max, fixed
  reference ranges, or a mix? How do outliers affect it?
- Tie-breaking rule (Phase 5).
- Booking reference format (Phase 7). Currently `BB-YYYYMMDD-XXXXXX`.
- Which extra criteria to add (Phase 5).
