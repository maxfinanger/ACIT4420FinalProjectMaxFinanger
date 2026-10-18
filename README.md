# BusBidder Spain

Final project for ACIT4420 Problem-solving with scripting (OsloMet, 2026).

BusBidder Spain is a Python application that takes a traveller's request, throws
out the bus offers that break their hard requirements, and then ranks what is
left with a weighted scoring model. The aim is that the traveller can see *why*
an offer ranks first, and not just that it does.

The question I'm trying to answer in this project:

> How can a Python application filter and rank competing bus offers according to
> the requirements and preferences of an individual traveller?

---

## 1. Setup and how to run

| Item | Value |
|---|---|
| Python version | 3.10 or newer (I develop on 3.12) |
| Libraries | Standard library only, plus `pytest` for the tests |
| Entry point | `main.py` |
| Input data | `data/` (CSV files) and `config/` (JSON) |

```bash
# create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate      

# install dependencies
pip install -r requirements.txt

# run the application from the project root
python main.py

# run the tests
python -m pytest -v

# (optional) regenerate the dataset, it is reproducible (fixed seed)
python scripts/generate_data.py

# see the validation reject the deliberately broken test file
python main.py --offers data/offers_invalid.csv

# guided menu: search, rank, compare profiles and book step by step
python main.py --interactive

# filter and rank with the example request from the spec
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable

# same request for another traveller profile, or with your own weights
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable --profile business_traveller --preferred-departure 08:00
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --weights price=40,duration=25,departure=15,flexibility=20

# compare all traveller profiles on the same request
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable --compare-profiles

# book the top offer of the ranking (simulated, saved in data/bookings.json), or book by offer id
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable --book 1 --name "Ana Perez"
python main.py --show-bookings

# regenerate docs/profile_comparison.md and docs/evaluation.md (reproducible, fixed seeds)
python scripts/compare_profiles.py
python scripts/evaluate.py
```

`python main.py --help` lists all request options (`--max-hours`, `--min-luggage`, `--profile`, `--weights`, `--top`, ...).
Profiles: `budget_traveller`, `business_traveller`, `flexible_tourist`, `environment_focused`.

All commands need to be run from the project root, because the data and config
paths are relative. The generated data files are already in the repository, so the
generator only has to be run if I change it.

`python main.py --interactive` starts a guided menu (see `docs/interface.md`). Without options, `main.py` loads the companies, destinations, profiles and offers,
validates the offers and prints a short summary (plus the rejected rows, if any).
If a request is given (`--destination ...`) it also applies the hard constraints, shows
what was removed and why, and ranks the rest with the weighted model (score of every
criterion, total, and how much each criterion really influences the order), and explains
the top offer (advantages, drawbacks, comparison with the runner-up, caveat).
`--compare-profiles` ranks the same offers for every profile. `--book RANK|OFFER_ID --name NAME` books one
seat (simulated payment, the name cannot contain digits). Use `--bookings FILE` to keep trial bookings out of
`data/bookings.json`, and `BUSBIDDER_SEED=7` to make booking references repeatable in demos.
Exit codes: 0 ok, 1 data file problem, 2 invalid request/selection/name, 3 booking refused.

Logs are written to `logs/busbidder.log` when the program runs. Every rejected
offer record is logged there with its row number, id and reason.

---

## 2. Project structure

```
busbidder/
├── main.py                  # entry point
├── README.md
├── requirements.txt
├── config/
│   ├── profiles.json        # 4 traveller profiles and their ranking weights
│   └── scoring.json         # parameters of the scoring model
├── data/
│   ├── companies.csv        # the 5 companies
│   ├── destinations.csv     # the 15 destinations
│   ├── offers.csv           # 1497 generated offers (scripts/generate_data.py)
│   ├── offers_invalid.csv   # broken rows for testing validation
│   ├── offers_invalid_expected.json   # what each broken row should be detected as
│   └── bookings.json        # created at runtime (git-ignored)
├── scripts/
│   ├── generate_data.py     # makes the dataset (fixed seed, reproducible)
│   ├── compare_profiles.py  # makes docs/profile_comparison.md (reproducible)
│   ├── evaluate.py          # runs the Phase 9 experiments and writes docs/evaluation.md
│   └── demo_interactive.py  # transcript of a scripted interactive session (reproducible)
├── busbidder/               # the application package
│   ├── models.py            # dataclasses: Company, Offer, TravelRequest, Booking
│   ├── exceptions.py        # custom exception hierarchy
│   ├── log_setup.py         # logging to logs/busbidder.log
│   ├── criteria.py          # scoring criteria, registered with a decorator
│   ├── scoring_config.py    # parameters of the scoring model (config/scoring.json)
│   ├── marketplace.py       # Marketplace: runs filter -> rank
│   ├── loader.py            # file input, type conversion, LoadResult (Task 2)
│   ├── validation.py        # business rules and regex patterns    (Task 2)
│   ├── filtering.py         # hard-constraint filtering            (Task 3)
│   ├── ranking.py           # weights, weighted ranking, ties, influence (Section 5 in spec)
│   ├── evaluation.py        # building blocks for the experiments (weights, correlations, ...)
│   ├── explain.py           # generated explanation of the top offer (Section 6 in spec)
│   ├── comparison.py        # compare profiles: which winner ranks where
│   ├── booking.py           # BookingService: seats, references, bookings file (Section 6 in spec)
│   ├── display.py           # everything that is printed (shared by the CLI and the menu)
│   ├── interactive.py       # interactive menu and the parsers for its questions
│   └── cli.py               # command-line options
├── tests/
│   ├── conftest.py          # shared fixtures (valid offer and row)
│   ├── test_basics.py
│   ├── test_design.py       # composition, constraints, criteria registry
│   ├── test_dataset.py      # the generated dataset and the invalid test file
│   ├── test_filtering.py    # hard constraints, filter report, request validation, CLI
│   ├── test_ranking.py      # criteria, weights, ranking, ties, influence, CLI
│   ├── test_explain.py      # the generated explanation
│   ├── test_booking.py      # booking, seat accounting, corrupt files, selection, CLI
│   ├── test_interactive.py  # the menu: every parser, scripted sessions, mistakes
│   ├── test_evaluation.py   # the experiment building blocks, checked against hand calculations
│   ├── test_evaluation_report.py   # docs/evaluation.md equals what the script generates
│   ├── test_profile_comparison.py   # profile comparison, generated document, CLI
│   ├── test_scoring_config.py   # scoring parameters and their file
│   ├── test_validation.py   # validation rules, boundaries, regex patterns
│   └── test_loader.py       # conversion, file errors, rejected rows, logging
├── logs/
├── docs/
│   ├── requirements.md      # requirements, drafted from the spec
│   ├── decisions.md         # design decisions: decision, alternatives, reason
│   ├── dataset.md           # how the dataset is built and how the companies differ
│   ├── validation.md        # validation rules, error categories, policy
│   ├── filtering.md         # hard vs soft table, how the filter reports, limitations
│   ├── scoring.md           # the scoring model, worked example, design questions, limitations
│   ├── explanation.md       # how the explanation is generated, example, limitations
│   ├── booking.md           # booking flow, rules, file format, limitations
│   ├── interface.md         # the interactive menu: input rules, behaviour, limitations
│   ├── evaluation.md        # the experiments and their results (generated)
│   ├── limitations.md       # limitations, possible unfair outcomes, improvements, what I learned
│   ├── profile_comparison.md    # the 4 profiles on the same request (generated)
│   ├── examples/            # saved program outputs used as evidence in the report
│   ├── architecture.png     # components and flow of information
│   ├── class_diagram.png    # main classes and their relations
│   └── diagrams/            # Graphviz sources for the two diagrams
└── report/
    └── BusBidder_Report.docx   # report skeleton (written in Word)
```

---

## 3. How the program is meant to work

```
 files (CSV/JSON)
      │
      ▼
  loader.py ──► validation.py ──► valid Offers  (invalid ones are logged and rejected/set aside)
                                      │
 TravelRequest (from cli.py) ────────►│
                                      ▼
                               filtering.py   (HARD constraints)
                                      │
                                      ▼
                               ranking.py     (SOFT preferences + weights)
                                      │
                                      ▼
                               explain.py ──► cli.py shows the ranking and an explanation
                                      │
                                      ▼
                               booking.py ──► bookings.json + confirmation
```

The proper version of this diagram is `docs/architecture.png` (source in
`docs/diagrams/`), and the main classes are in `docs/class_diagram.png`.

The main idea is the split between hard constraints and soft preferences.
Hard constraints (for example destination, budget and travel window) remove an
offer completely before ranking. Soft preferences (for example preferred
departure time) only affect the score. Which condition goes where is a design
decision, which is justified in `docs/filtering.md` (D6).

Design choices from Phase 1 (reasons and alternatives are in `docs/decisions.md`):

- **Composition:** an `Offer` has a `FareConditions` object, and a `Booking` keeps a copy of it.
- **Inheritance:** every hard constraint is a subclass of an abstract `Constraint`, so
  each one can both test an offer and explain why it was removed.
- **Metaprogramming:** scoring criteria are registered with a `@register_criterion`
  decorator, so the weights in `profiles.json` can refer to criteria by name.
- **Scoring (Phase 5):** every criterion gives 0-100 (higher is better). Price and duration are
  scored relative to the other offers (with a minimum spread), the others against a fixed reference
  (D15, `docs/scoring.md`).
- **Explanation (Phase 6):** built from the criterion scores (advantages, always a drawback, comparison
  with the runner-up, and a caveat that the result holds only under the chosen constraints, weights
  and scoring assumptions), see `docs/explanation.md` (D17).
- **Booking (Phase 7):** `data/bookings.json` is the only record of seats sold (the offers file is never changed),
  it is re-read before every booking and written atomically, and a booking keeps its own copy of the fare
  conditions. See `docs/booking.md` (D19, D20).
- **Interface (Phase 8):** the menu uses the same functions and the same printing as the command-line options.
  Answers go through small tested parsers with helpful messages, and nothing is saved without a `y`
  (`docs/interface.md`, D21).
- **Evaluation (Phase 9):** the experiments are a script that runs on the real code with fixed seeds and writes
  `docs/evaluation.md`; the findings are computed from the numbers, and a test keeps the file up to date (D22).
- **`Marketplace`** holds the data and runs the filter-then-rank pipeline, so the
  CLI only has to talk to one class.

---

## 4. Testing

Tests are in `tests/` and run with `python -m pytest -v`.

Right now there are 595 tests. They cover:

- **Design:** fare conditions, the abstract constraint, the budget boundary, the
  criteria registry, overnight durations, weight validation.
- **Dataset:** reproducible generation, 75+ company-destination combinations, unique ids,
  sensible values, and that the invalid file matches its expectations.
- **Validation:** every error category, boundary values (price 0.01 accepted and 0
  rejected, duration exactly 24 h accepted, rating 0 and 5 accepted), regex patterns.
- **Loading:** type conversion, missing/empty/unreadable files, wrong header, duplicate ids,
  logging, and the real file (1497 accepted, 0 rejected). The invalid file is checked
  row by row against `data/offers_invalid_expected.json`.
- **Filtering:** every hard constraint with boundary values (budget 49.99 / 50.00 / 50.01,
  edge days of the window, 390 vs 391 minutes incl. overnight, 19 vs 20 kg luggage), inactive
  constraints, the removal counts, empty and impossible requests, invalid requests, the spec
  example on the real data checked against an independent calculation (47 offers), and the CLI.
- **Ranking:** hand-calculated scores and totals, a different winner with other weights, all-equal
  and single-offer cases (no division by zero), minimum spread, outlier cap, departure across midnight,
  missing emissions, tie-breaking, order independence, invalid and percentage weights, a criterion
  added without touching the ranker, the winner per profile on the real data, and a documented
  rank-reversal example (known limitation).
- **Explanation:** hand-checked text, both thresholds on each side of the boundary, a drawback on every
  profile, no-drawback / single-offer / empty cases, ties, the generic fallback for a new criterion, and that
  the text never says "objectively".
- **Profile comparison:** same filtered offers for every profile, at least three different winners, the rank
  matrix, the CLI, and that the committed `docs/profile_comparison.md` is identical to what the script generates.
- **Booking:** the name rules, saved fields and no payment data, last seat / sold out / double booking, a stale
  offer cannot oversell, seat counts after a restart, 20 kinds of corrupt bookings file (never overwritten), failed saves,
  unique references and collisions, choosing from the ranking, a sold-out offer disappearing from the next search,
  and the CLI exit codes. I also broke the booking code on purpose in five ways to check that the tests notice.
- **Interactive menu:** every parser with valid, invalid and boundary input, and complete sessions with scripted
  answers (mistakes, `q`, end of input, no results, re-ranking, comparing, booking, declining, duplicates, a corrupt
  bookings file). Five deliberate breakages were all caught.
- **Evaluation:** the experiment building blocks against hand calculations (the weight range in which a winner stays, rank
  correlation with ties, random weights), and that the committed `docs/evaluation.md` equals what the script generates, with
  a few numbers re-checked through the filter on its own.

As each phase is finished I will add tests for normal input, invalid input,
missing data and boundary cases, as the spec requires. Hand-calculated expected
scores will be used for the ranking tests so I can check the maths independently
of my own code.

---

## 5. Roadmap

This is my plan. I'm using it to work in small steps, to show progress in the
git history, and to check along the way that the program fits the specification.
I commit after every phase.

### [x] Phase 0: Skeleton
- [x] Folder structure and modules created
- [x] Sample data for companies, destinations and offers
- [x] Custom exceptions, logging setup, dataclass models
- [x] `main.py` runs, 6 starter tests pass

### [x] Phase 1: Understand and design
- [x] Write the requirements in its own file (`docs/requirements.md`)
- [x] Decide which concepts need classes and which can just be functions
- [x] Decide where to use inheritance or composition, and why
- [x] Choose the metaprogramming technique (required). Chosen: a registry of scoring
      criteria filled by a decorator. Also considered: a logging/timing decorator, a
      descriptor for validated fields, dynamic discovery of company modules
- [x] Draw the first architecture diagram, saved as `docs/architecture.png`
- [x] Start `docs/decisions.md` with decision, alternatives and reason
- [x] Class skeletons for the design (`criteria.py`, `marketplace.py`, constraint classes), with tests
- [x] Start the report skeleton (`report/BusBidder_Report.docx`)

### [x] Phase 2: Dataset 
- [x] Decide how each company differs (routes, prices, times, fare rules)
- [x] Write or generate `offers.csv` with at least 75 company-destination
      combinations, ideally with several departure times or fare types each
- [x] Keep it reproducible: if I generate the data with a script, use a fixed random seed
- [x] Make a separate `offers_invalid.csv` with bad rows for testing (negative
      price, unknown destination, arrival before departure, rating outside 0-5,
      zero seats, bad date, missing field)

### [x] Phase 3: Load and validate 
- [x] Implement `load_offers()` in `loader.py` (str to date, time, float, bool)
- [x] Implement `validate_offer()` in `validation.py`
- [x] Raise the custom exceptions (`ValidationError` with a category, `DataFileError`)
- [x] Use regex where it fits (offer id, booking reference, date and time formats, see D13)
- [x] Decide and document whether invalid records are rejected, corrected or set aside
      (rejected and logged, see D7 and `docs/validation.md`)
- [x] Log every rejected record with the reason
- [x] Handle overnight journeys in `Offer.duration_minutes` (done in Phase 2: offers have an `arrival_date`, see D11)
- [x] Tests: normal, invalid, missing file, missing field, boundary values
      (expected results for every row of `offers_invalid.csv` are in `offers_invalid_expected.json`)

### [x] Phase 4: Hard constraints
- [x] Decide which conditions are hard (must hold) and which are soft (preference)
      (table in `docs/filtering.md`, decision D6)
- [x] Implement `filter_offers()` for destination, travel window, budget, seats,
      max transfers and mandatory flexibility (plus luggage and maximum duration when set)
- [x] Make the hard/soft split visible to the user (e.g. "removed: 4 over budget")
- [x] Handle the case where no offers survive (message and a hint about what to relax)
- [x] Tests including boundaries (price exactly at budget, date exactly on the window edge)

### [x] Phase 5: Weighted ranking 
- [x] Normalise each criterion to a 0-100 scale (D15, `docs/scoring.md`)
  - price and duration: lower is better, so invert
  - departure convenience: based on distance from the preferred time
  - flexibility: categorical (e.g. none = 0, changeable = 60, changeable + refundable = 100)
- [x] Decide how to handle ties, missing values, extreme values, and the case
      where all offers have the same value (division by zero) (D16)
- [x] Validate that weights sum to 1.0 and are not negative (also unknown criteria; percentages accepted)
- [x] Maybe add extra criteria (transfers, rating, emissions), used by a fourth profile `environment_focused`
- [x] Return the score per criterion and the total score for every offer
- [x] Tests with hand-calculated expected scores on a tiny dataset

### [x] Phase 6: Explanation and traveller profiles 
- [x] Implement `explain_top_offer()`, generated from the data
      (e.g. "direct route, departs 40 min from preferred time, flexible fare;
      drawback: EUR 7 above the cheapest")
- [x] Never call the result "objectively best". It is best under the chosen
      constraints and weights (the caveat is always printed, and a test checks the wording)
- [x] Run at least 3 profiles on the same request (budget, business, flexible
      tourist) and save the output to `docs/profile_comparison.md` (4 profiles, generated by a script)

### [x] Phase 7: Booking 
- [x] Let the user select an offer from the ranking (`--book RANK|OFFER_ID`)
- [x] Check that seats are still available (the file is re-read before every booking)
- [x] Generate a unique booking reference that matches the regex
- [x] Reduce capacity consistently (in memory and in the saved data)
- [x] Save the booking with its fare conditions to `data/bookings.json`
- [x] Clear confirmation message, simulated payment status only (no real card data)
- [x] Tests: last seat, sold out, double booking

### [x] Phase 8: Interface polish
- [x] Interactive CLI menu: enter request, see filtered and ranked offers, book (`--interactive`)
- [x] Input validation with helpful error messages (the question is asked again, with an example)
- [ ] Optional extensions if there is time: cancellation/refund, vouchers, return trips, GUI/web
      (not built, listed as future work in `docs/interface.md` and D21)

### [x] Phase 9: Evaluation
- [x] Run experiments where I change the weights and see how the ranking changes (`docs/evaluation.md` section 2)
- [x] Check sensitivity: does one criterion dominate (e.g. when the price range is wide)? (sections 3 and 4)
- [x] Look for unfair or unreasonable outcomes (e.g. overnight buses being
      penalized by the departure convenience criterion) (section 5)
- [x] Write down limitations and what I would improve (`docs/limitations.md`)
- [x] Save screenshots, tables and log excerpts to `docs/` (`docs/examples/` has text transcripts, `docs/evaluation.md` the tables)

### [ ] Phase 10: Report and submission
- [ ] Write the report (PDF), see the checklist in section 6
- [ ] Final README check: Python version, libraries, exact run and test commands
- [ ] Check that a fresh clone works: `pip install -r requirements.txt`, then `python main.py`, then `pytest`
- [ ] Include the example outputs needed to reproduce the report findings
- [ ] Submit the PDF and the code (zip or GitHub link)

---

## 6. Report plan

The report is the main assessed part, so I'm collecting material for it as I go
instead of writing everything at the end. The structure is already in
`report/BusBidder_Report.docx`, with Word comments saying what each section needs. Source code stays out of the report
as far as possible.

| Required content | Where it comes from |
|---|---|
| Flowchart / architecture diagram | Phase 1 |
| Dataset description and validation | Phases 2-3 (`docs/dataset.md`, `docs/validation.md`) |
| At least 3 traveller-profile comparisons | Phase 6 (`docs/profile_comparison.md`) |
| Limitations and possible unfair outcomes | Phase 9 (`docs/limitations.md`, `docs/evaluation.md`) |
| Generative-AI declaration (what for, how it was checked, what I changed) | notes kept during the project, see section 8 |

Grading weights from the spec, which I use to decide where to spend time:

| Component | Weight |
|---|---|
| Problem interpretation and requirements | 10% |
| Software design and architecture justifications | 15% |
| Implementation explanation | 15% |
| Testing and experimental evidence | 15% |
| **Evaluation, limitations, critical reflection** | **20%** |
| Implementation traceability and reproducibility | 10% |
| Report organisation and technical communication | 15% |

---

## 7. Technical requirements tracker

Checked against the spec, section 7.

- [ ] Modular application (several cohesive modules)
- [ ] File I/O (source data, bookings, config, logs)
- [ ] Custom error handling (invalid input, missing files, inconsistent data)
- [ ] Regex used where it genuinely fits
- [ ] One metaprogramming technique (decorator / registry / descriptor / dynamic discovery)
- [ ] Intuitive interface (CLI is fine)
- [ ] Reproducible ranking (same input gives the same output)
- [ ] Tests for normal, invalid, missing-data and boundary cases

---

## 8. Use of generative AI

I use Claude (Anthropic) as an assistant during the project. This is how i have used the model, and a explanation of what is my work specifically and where the tool is used along side my own efforts.

**What I use it for**

- Planning and structure: breaking the specification into phases, the structure of this README, and the outline of the report with guidance comments.
- Code: first drafts of the project skeleton, the class design, the data generation
  script and the tests.
- Illustrations: the architecture diagram and the class diagram (Graphviz sources are in `docs/diagrams/`).
- General questions and discussing design alternatives, for example which metaprogramming technique to use.

**How I check it**

I run the program and the tests, read through the generated code and documents, check the diagrams against the code, and compare everything with the specification. The data generator is checked with tests, and the generated dataset is checked against the summary statistics in `docs/dataset.md`.

**What is mine**

I have read and agreed with the design decisions in `docs/decisions.md`, and I edit
the README and the other documents myself. I write the report text myself. I stay
responsible for all design decisions and for everything in the submission.

---

## 9. Dependencies

- Python 3.10 or newer
- No third-party runtime dependencies
- `pytest` for testing (listed in `requirements.txt`)
