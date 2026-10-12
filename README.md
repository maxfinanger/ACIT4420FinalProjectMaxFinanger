# BusBidder Spain

Final project for ACIT4420 Problem-solving with scripting (OsloMet, 2026).

BusBidder Spain is a Python application that takes a traveller's request, throws
out the bus offers that break their hard requirements, and then ranks what is
left with a weighted scoring model. The aim is that the traveller can see *why*
an offer ranks first, and not just that it does.

The question I'm trying to answer in this project:

> How can a Python application filter and rank competing bus offers according to
> the requirements and preferences of an individual traveller?

**Current status:** Phases 0 to 2 are finished (skeleton, design and dataset). Phase 3
(loading and validation) is next, see the roadmap in section 5. This README will be updated as I go.

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
```

All commands need to be run from the project root, because the data and config
paths are relative. The generated data files are already in the repository, so the
generator only has to be run if I change it.

At the moment `main.py` only loads the companies, destinations and profiles and
prints a short summary. That is on purpose, the first step was just to get a
working skeleton before adding logic.

Logs are written to `logs/busbidder.log` when the program runs.

---

## 2. Project structure

```
busbidder/
├── main.py                  # entry point
├── README.md
├── requirements.txt
├── config/
│   └── profiles.json        # traveller profiles and their ranking weights
├── data/
│   ├── companies.csv        # the 5 companies
│   ├── destinations.csv     # the 15 destinations
│   ├── offers.csv           # 1497 generated offers (scripts/generate_data.py)
│   ├── offers_invalid.csv   # broken rows for testing validation
│   ├── offers_invalid_expected.json   # what each broken row should be detected as
│   └── bookings.json        # created at runtime (git-ignored)
├── scripts/
│   └── generate_data.py     # makes the dataset (fixed seed, reproducible)
├── busbidder/               # the application package
│   ├── models.py            # dataclasses: Company, Offer, TravelRequest, Booking
│   ├── exceptions.py        # custom exception hierarchy
│   ├── log_setup.py         # logging to logs/busbidder.log
│   ├── criteria.py          # scoring criteria registry (decorator) (Phase 1 design)
│   ├── marketplace.py       # Marketplace: runs filter -> rank
│   ├── loader.py            # file input and type conversion       (Task 2)
│   ├── validation.py        # record validation and regex          (Task 2)
│   ├── filtering.py         # hard-constraint filtering            (Task 3)
│   ├── ranking.py           # weighted scoring                     (Section 5 in spec)
│   ├── explain.py           # "why is this ranked first?"          (Section 6 in spec)
│   ├── booking.py           # simulated bookings                   (Section 6 in spec)
│   └── cli.py               # command-line interface
├── tests/
│   ├── test_basics.py
│   ├── test_design.py       # composition, constraints, criteria registry
│   └── test_dataset.py      # the generated dataset and the invalid test file
├── logs/
├── docs/
│   ├── requirements.md      # requirements, drafted from the spec
│   ├── decisions.md         # design decisions: decision, alternatives, reason
│   ├── dataset.md           # how the dataset is built and how the companies differ
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
decision I still have to make and justify, see Phase 4.

Design choices from Phase 1 (reasons and alternatives are in `docs/decisions.md`):

- **Composition:** an `Offer` has a `FareConditions` object, and a `Booking` keeps a copy of it.
- **Inheritance:** every hard constraint is a subclass of an abstract `Constraint`, so
  each one can both test an offer and explain why it was removed.
- **Metaprogramming:** scoring criteria are registered with a `@register_criterion`
  decorator, so the weights in `profiles.json` can refer to criteria by name.
- **`Marketplace`** holds the data and runs the filter-then-rank pipeline, so the
  CLI only has to talk to one class.

---

## 4. Testing

Tests are in `tests/` and run with `python -m pytest -v`.

Right now there are 28 tests. They cover loading the companies and destinations,
the missing-file error, weight validation (sum, negative, unknown criterion), the
booking reference pattern, the Phase 1 design (fare conditions, the abstract
constraint, the budget boundary, the criteria registry, overnight durations) and the
dataset (reproducible generation, 75+ company-destination combinations, unique ids,
sensible values, and that the invalid file matches its expectations).

As each phase is finished I will add tests for normal input, invalid input,
missing data and boundary cases, as the spec requires. Hand-calculated expected
scores will be used for the ranking tests so I can check the maths independently
of my own code.

---

## 5. Roadmap

This is my plan. I'm using it to work in small steps, to show progress in the
git history, and to check along the way that the program fits the specification.
I commit after every phase.

### [x] Phase 0: Skeleton (done)
- [x] Folder structure and modules created
- [x] Sample data for companies, destinations and offers
- [x] Custom exceptions, logging setup, dataclass models
- [x] `main.py` runs, 6 starter tests pass

### [x] Phase 1: Understand and design (Task 1)
Goal: decide what the program is before writing more code.
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
Goal: a realistic dataset covering 5 companies and 15 destinations.
Details and the numbers are in `docs/dataset.md`.
- [x] Decide how each company differs (routes, prices, times, fare rules)
- [x] Write or generate `offers.csv` with at least 75 company-destination
      combinations, ideally with several departure times or fare types each
- [x] Keep it reproducible: if I generate the data with a script, use a fixed random seed
- [x] Make a separate `offers_invalid.csv` with bad rows for testing (negative
      price, unknown destination, arrival before departure, rating outside 0-5,
      zero seats, bad date, missing field)

### [ ] Phase 3: Load and validate 
- [ ] Implement `load_offers()` in `loader.py` (str to date, time, float, bool)
- [ ] Implement `validate_offer()` in `validation.py`
- [ ] Raise the custom exceptions (`ValidationError`, `DataFileError`)
- [ ] Use regex where it fits (booking reference, which is already started, and offer IDs like `OF-\d{4}`)
- [ ] Decide and document whether invalid records are rejected, corrected or set aside
- [ ] Log every rejected record with the reason
- [x] Handle overnight journeys in `Offer.duration_minutes` (done in Phase 2: offers have an `arrival_date`, see D11)
- [ ] Tests: normal, invalid, missing file, missing field, boundary values
      (expected results for every row of `offers_invalid.csv` are in `offers_invalid_expected.json`)

### [ ] Phase 4: Hard constraints
- [ ] Decide which conditions are hard (must hold) and which are soft (preference)
- [ ] Implement `filter_offers()` for destination, travel window, budget, seats,
      max transfers and mandatory flexibility
- [ ] Make the hard/soft split visible to the user (e.g. "removed: 4 over budget")
- [ ] Handle the case where no offers survive
- [ ] Tests including boundaries (price exactly at budget, date exactly on the window edge)

### [ ] Phase 5: Weighted ranking 
- [ ] Normalise each criterion to a 0-100 scale
  - price and duration: lower is better, so invert
  - departure convenience: based on distance from the preferred time
  - flexibility: categorical (e.g. none = 0, changeable = 60, changeable + refundable = 100)
- [ ] Decide how to handle ties, missing values, extreme values, and the case
      where all offers have the same value (division by zero)
- [ ] Validate that weights sum to 1.0 (stub exists) and are not negative
- [ ] Maybe add extra criteria (transfers, rating, emissions)
- [ ] Return the score per criterion and the total score for every offer
- [ ] Tests with hand-calculated expected scores on a tiny dataset

### [ ] Phase 6: Explanation and traveller profiles 
- [ ] Implement `explain_top_offer()`, generated from the data
      (e.g. "direct route, departs 40 min from preferred time, flexible fare;
      drawback: EUR 7 above the cheapest")
- [ ] Never call the result "objectively best". It is best under the chosen
      constraints and weights
- [ ] Run at least 3 profiles on the same request (budget, business, flexible
      tourist) and save the output to `docs/profile_comparison.md`

### [ ] Phase 7: Booking 
- [ ] Let the user select an offer from the ranking
- [ ] Check that seats are still available
- [ ] Generate a unique booking reference that matches the regex
- [ ] Reduce capacity consistently (in memory and in the saved data)
- [ ] Save the booking with its fare conditions to `data/bookings.json`
- [ ] Clear confirmation message, simulated payment status only (no real card data)
- [ ] Tests: last seat, sold out, double booking

### [ ] Phase 8: Interface polish
- [ ] Interactive CLI menu: enter request, see filtered and ranked offers, book
- [ ] Input validation with helpful error messages
- [ ] Optional extensions if there is time: cancellation/refund, vouchers, return trips, GUI/web

### [ ] Phase 9: Evaluation
- [ ] Run experiments where I change the weights and see how the ranking changes
- [ ] Check sensitivity: does one criterion dominate (e.g. when the price range is wide)?
- [ ] Look for unfair or unreasonable outcomes (e.g. overnight buses being
      penalized by the departure convenience criterion)
- [ ] Write down limitations and what I would improve
- [ ] Save screenshots, tables and log excerpts to `docs/`

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
| Dataset description and validation | Phases 2-3 (`docs/dataset.md`) |
| At least 3 traveller-profile comparisons | Phase 6 |
| Limitations and possible unfair outcomes | Phase 9 |
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

I use Claude (Anthropic) as an assistant during the project. This is the general
picture of how, and I will keep it up to date if the way I use it changes.

**What I use it for**

- Planning and structure: breaking the specification into phases, the structure of this
  README, and the outline of the report with guidance comments.
- Code: first drafts of the project skeleton, the class design, the data generation
  script and the tests.
- Illustrations: the architecture diagram and the class diagram (Graphviz sources are
  in `docs/diagrams/`).
- General questions and discussing design alternatives (for example which
  metaprogramming technique to use).

**How I check it**

I run the program and the tests, read through the generated code and documents, check
the diagrams against the code, and compare everything with the specification. The data
generator is checked with tests, and the generated dataset is checked against the
summary statistics in `docs/dataset.md`.

**What is mine**

I have read and agreed with the design decisions in `docs/decisions.md`, and I edit
the README and the other documents myself. I write the report text myself. I stay
responsible for all design decisions and for everything in the submission.

---

## 9. Dependencies

- Python 3.10 or newer
- No third-party runtime dependencies
- `pytest` for testing (listed in `requirements.txt`)
