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

## D6. Hard constraints versus soft preferences (preliminary, finalise in Phase 4)
- **Status:** Decided (preliminary, confirmed in Phase 4)
- **Hard (offer is removed):** destination, travel window, budget, seats > 0,
  maximum transfers, and ticket flexibility *only if the traveller marks it as required*.
- **Soft (affects score only):** departure time, journey duration, flexibility
  when not required, plus any extra criteria (rating, emissions).
- **Note:** Price is both. Budget is a hard limit, and within the budget a lower
  price still scores higher. I need to explain this clearly in the report.
- **Reason:** A hard constraint is something where the traveller would not
  accept the offer at any score (cannot travel on the wrong day). A soft one is
  something that can be traded off against other criteria.

## D7. Invalid records are rejected and logged, not corrected (preliminary, finalise in Phase 3)
- **Status:** Decided (preliminary, confirmed in Phase 3)
- **Decision:** A record that fails validation is skipped, written to the log
  with its id and reason, and counted. The program continues with the valid rows.
  If a whole file is missing, or the header is wrong, the program stops with a `DataFileError`.
- **Alternatives:** Correct obvious mistakes (e.g. swap arrival/departure); stop on the first error.
- **Reason:** Guessing a correction can silently produce a wrong offer, and a
  traveller could then book something that does not exist. Stopping on one bad
  row would make the program fragile.

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

---

## Still to decide (not in the list above)

- Exact normalisation method for each criterion (Phase 5): min-max, fixed
  reference ranges, or a mix? How do outliers affect it?
- Tie-breaking rule (Phase 5).
- Booking reference format (Phase 7). Currently `BB-YYYYMMDD-XXXXXX`.
- Which extra criteria to add (Phase 5).
