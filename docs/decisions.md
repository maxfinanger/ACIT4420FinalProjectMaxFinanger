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
- **Implemented (Phase 7):** `Offer.capacity` is the number in the file, `Offer.seats_available` is what is left
  (`capacity - bookings`). At start-up `BookingService.apply_to_offers` sets it, so `SeatsConstraint` stays simple
  (`seats_available >= 1`) and now removes sold-out offers. `book()` re-reads the file instead of trusting the in-memory number.

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

## D15. Normalisation: relative scales with a minimum spread, absolute scales where there is a reference
- **Status:** Decided
- **Decision:** All criteria give 0-100, higher is better. Price, duration and emissions are
  RELATIVE: the best offer in the list gets 100 and the score falls linearly to 0 over the spread of
  the values, but over at least a "meaningful difference" (EUR 5, 60 min, 2 kg). Departure,
  flexibility, transfers and rating are ABSOLUTE: they have a natural reference (the preferred time, the fare
  category, a direct bus, 5 stars). The parameters are in `config/scoring.json`.
- **Alternatives:**
  - Plain min-max for everything: simple, but a EUR 1 difference between two offers becomes 100 points, and
    all-equal lists divide by zero.
  - Fixed reference scales for everything (e.g. price score = 100 * (1 - price / budget)): no rank reversal and
    comparable between searches, but the scores bunch together when the budget is generous, so price would
    quietly lose influence.
  - z-scores or rank-based scores: harder to explain to a traveller.
- **Reason:** Price and duration have no natural "good" level, so comparing with the other offers is the only
  meaningful scale, and using the full range makes the weights mean what they say. The minimum spread keeps tiny
  differences small. Where a reference exists (the traveller's own preferred time), using it is more honest than
  comparing offers with each other.
- **Known cost:** rank reversal (an offer that is not at the top can change the order of the ones above it),
  shown by a test and discussed in `docs/scoring.md`.

## D16. Ties, missing values and extreme values
- **Status:** Decided
- **Decision:**
  - Ties are defined at the precision shown (2 decimals) and broken by lower price, shorter journey, earlier
    departure, offer id. Ranks run 1..n without gaps, and the offers that needed a tie-break are marked.
  - A missing criterion value (only emissions can be missing) gets `missing_value_score` = 0.
  - A value worse than 2x the median counts as the worst value, so an outlier cannot stretch a relative scale.
  - A criterion that returns anything but a finite number from 0 to 100 raises `ScoringError`.
- **Alternatives:** Shared ranks for ties; a neutral score (50) or dropping the criterion for offers with missing
  data; winsorising at percentiles.
- **Reason:** A strict order is easier to explain and to book from, and the tie-break is the traveller-friendly
  one (cheaper, faster, earlier). Scoring "unknown" as worst avoids rewarding missing data, which would let a company
  gain by not reporting emissions. A median-based cap works for any list size, where percentiles are unstable with a
  handful of offers.

## D17. The explanation is generated from the scores, with a fixed structure
- **Status:** Decided
- **Decision:** `explain_top_offer` builds the text from the ranked offers: advantages (criterion score 75 or
  more), drawbacks (40 or less, and always at least one line), a comparison with the runner-up in weighted points,
  a tie note when needed, and a caveat that the offer is best only under the hard requirements, the weights and
  the scoring assumptions. Details in `docs/explanation.md`.
- **Alternatives:** A fixed template per company or fare; a free-text description written by hand per offer;
  only listing the scores; asking an AI model to write the explanation.
- **Reason:** The spec wants the text generated from the data and honest about the model. Building it from the
  same criterion scores as the ranking means the two can never disagree, and it works for any criterion added through
  the registry. An AI-written explanation would be less reproducible and could claim things the data does not show.
  Always naming a drawback and ending with the caveat follows the spec's warning not to call a result objectively best.
- **Trade-off:** fixed thresholds and template sentences are simple and testable, but not very varied.

## D18. Profiles are compared on one request, filtering once, and the comparison file is generated
- **Status:** Decided
- **Decision:** `Marketplace.compare_profiles` filters once and ranks the same offers with each profile's weights.
  The request, including the preferred departure time, is identical for every profile. `scripts/compare_profiles.py`
  writes `docs/profile_comparison.md` (no hand editing, no timestamps), and a test checks that the committed file
  matches the script. A second small experiment gives each traveller their own preferred departure time.
- **Alternatives:** A different request per traveller (more realistic, but then differences cannot be blamed on the
  weights); copying numbers into the report by hand.
- **Reason:** Holding everything but the weights fixed is what shows that "the same offers can produce different
  recommendations for different travellers". A generated file means the report numbers can be reproduced, and the test
  catches stale documentation (it did, once, during this phase).
- **Observation:** with an identical request there are four different winners from four companies. If each traveller
  also gets their own preferred time, one winner changes (the flexible tourist moves from OF-0725 to OF-0730), so the
  soft departure preference matters too.

## D19. Bookings: one file as the truth, atomic writes, simple rules
- **Status:** Decided
- **Decision:** `data/bookings.json` is the only record of seats sold, and it is re-read before every booking. It is
  written atomically (temp file, then rename) and never overwritten if it cannot be read. A booking stores its own copy of the
  journey and fare conditions. The reference is `BB-<travel date>-<6 characters>` without the confusing characters 0, O, 1, I,
  and is checked for uniqueness. One booking is one seat. The same name cannot book the same offer twice (ignoring case).
  The name may contain letters, spaces, hyphens, apostrophes and full stops, but **no digits**. The seat count in memory is
  reduced only after the file is saved.
- **Alternatives:** Rewriting `offers.csv` with the new seat counts; keeping seat counts only in memory; a database (SQLite);
  allowing any text as a name; letting one name book the same offer several times (a group).
- **Reason:** One source of truth cannot disagree with itself, and it keeps `offers.csv` fixed so the results in the report stay
  reproducible (D9). Re-reading and atomic writes protect against stale data and crashes without needing a database (D1). A copy of the
  fare conditions means the booking cannot change if the offers are regenerated, which the spec asks for. Refusing digits in names
  means a card number typed by mistake is never stored, so the "no payment information" rule holds even for user mistakes. A repeated
  booking by the same name is almost always a mistake, and a group can use different names.
- **Trade-off:** no protection against two programs writing at exactly the same time (see `docs/booking.md`).

## D20. Choosing an offer: rank number or offer id, from the command line
- **Status:** Decided
- **Decision:** `--book` takes a rank number (`1`) or an offer id (`OF-1025`) from the ranking that was just computed, plus
  `--name`. Only offers in that ranking can be booked, and any rank can be booked, not just the ones shown. `BUSBIDDER_SEED` makes references
  repeatable for demos. The interactive menu is built in Phase 8 on top of the same functions.
- **Alternatives:** Only an interactive prompt; booking any offer id from the file; only offer ids.
- **Reason:** Options make the booking reproducible and testable, and a supervisor can run it without typing. Allowing only offers from the
  ranking means a booking can never break a hard constraint. A rank number is quick to type, an id is stable when the ranking changes.

## D21. The interactive menu uses the same functions, forgiving input, and an explicit confirmation
- **Status:** Decided
- **Decision:** `python main.py --interactive` starts a numbered menu (search, show all, rank again, compare profiles, book,
  bookings, help, quit). It calls the same functions as the command-line options and prints with the same `display.py`. Every
  answer goes through a small pure parser. Wrong answers get a message that names what was expected (and a "did you mean" for destinations),
  and the question is asked again. Input is forgiving: case and accents are ignored, a unique start of a name is enough, dates can be
  ISO or day/month/year, decimals can use a comma, times can be `9` or `9.30`. `q` cancels a question, 8 bad answers in a row cancel it,
  Enter takes the default, and a booking is only saved after an explicit `y` (the default is no). The input function can be replaced so
  that complete sessions are tested with scripted answers. Plain `python main.py` still prints the summary only; the menu needs `--interactive`.
- **Alternatives:** A graphical or web interface (more work, and the report is assessed on design and evaluation rather than on the
  interface); starting the menu whenever the program is run without options (breaks scripts and the non-interactive tests); a menu library
  such as `curses` (breaks on some terminals, harder to test); stricter parsing (shorter code, but more frustrating to use).
- **Reason:** The spec asks for an "intuitive" interface and offers a GUI/web interface as an optional extension. A guided text menu is
  intuitive for the core task, runs everywhere with the standard library (D1), and, because the answers are parsed by pure functions and the
  input can be injected, it is fully testable. Sharing `display.py` means the two ways of using the program cannot drift apart. The explicit
  confirmation follows from booking being the one action that changes saved data.
- **Not built (future work):** cancellation and refunds, vouchers, return and multi-city journeys, waiting lists, seat selection, group bookings,
  a graphical or web interface. The core requirements are complete without them, and the time is better spent on evaluation (Phase 9).

## D22. The evaluation is a generated report of experiments on the real code
- **Status:** Decided
- **Decision:** `scripts/evaluate.py` runs the experiments on the real filter, scoring and ranking, with fixed random seeds and no timestamps, and writes
  `docs/evaluation.md`. A test checks that the committed file equals the script's output. The experiments are: are the rankings reasonable (winner position
  and rank correlation per raw value); weight sensitivity (one weight at a time, the range in which the winner stays, random changes to all weights, completely
  random weights); whether one criterion dominates (weight versus influence, across different requests); sensitivity to the numbers in `config/scoring.json`;
  possible unfair outcomes (night buses, the budget cliff, how strict requirements narrow the field of companies, which companies win across the market,
  rank reversal, and the incentive to leave out data); and reproducibility fingerprints. The key findings at the top are computed from the numbers.
  `docs/limitations.md` is the hand-written reflection and quotes its numbers.
- **Alternatives:** Running experiments in a notebook and pasting numbers into the report; only a few hand-picked examples; statistical tests on
  many random requests.
- **Reason:** The evaluation is 20% of the grade and the report must be reproducible. A script means every number can be regenerated, a test stops the file from
  going stale (it already caught one stale document), and computing the findings from the numbers stops me from writing what I expect instead of what I measure.
  This mattered twice: a hypothesis about price spread turned out to be wrong, and a hand-copied observation in an earlier document was false.
- **Trade-off:** the experiments use one main request (the spec example) plus scenarios, and the random experiments use one seed. They show how the model
  behaves, not how real travellers behave. The reasoning is in `docs/limitations.md`.

---

## Still to decide

- Which parts of `docs/evaluation.md` and `docs/limitations.md` go into the report and in which order (Phase 10).
