# 🚌 BusBidder Spain

A modular Python application that **filters** and **ranks** competing bus offers
according to an individual traveller's requirements and preferences.
Final project for **ACIT4420 – Problem-solving with scripting (OsloMet, 2026)**.

> **Central question:** How can a Python application filter and rank competing bus
> offers according to the requirements and preferences of an individual traveller?

---

## 1. Quick start

| Item | Value |
|---|---|
| Python version | 3.10+ (tested on 3.12) |
| Libraries | Standard library only (+ `pytest` for tests) |
| Entry point | `main.py` |

```bash
# virtual environment
python -m venv .venv
source .venv/bin/activate   

pip install -r requirements.txt

# run the application
python main.py

# run the tests
python -m pytest -v
```

Right now `main.py` only loads the sample data and prints a summary.
That is intentional: **Phase 0 = a working skeleton.**

---

## 2. Project structure

```
busbidder/
├── main.py                  # entry point
├── README.md
├── requirements.txt
├── config/
│   └── profiles.json        # traveller profiles -> ranking weights
├── data/
│   ├── companies.csv        # 5 companies
│   ├── destinations.csv     # 15 destinations
│   ├── offers.csv           # sample offers (Only 3 rows atm)
│   └── bookings.json        # created at runtime (git-ignored)
├── busbidder/               # the application package
│   ├── models.py            # dataclasses: Company, Offer, TravelRequest, Booking
│   ├── exceptions.py        # custom exception hierarchy
│   ├── log_setup.py         # logging to logs/busbidder.log
│   ├── loader.py            # file input + type conversion        (Task 2)
│   ├── validation.py        # record validation + regex           (Task 2)
│   ├── filtering.py         # hard-constraint filtering           (Task 3)
│   ├── ranking.py           # weighted scoring                    (Section 5)
│   ├── explain.py           # "why is this ranked first?"         (Section 6)
│   ├── booking.py           # simulated bookings                  (Section 6)
│   └── cli.py               # command-line interface
├── tests/
│   └── test_basics.py
├── logs/
└── docs/                    # diagrams, screenshots, notes for the report
```

### Intended flow of information

```
 files (CSV/JSON)
      │
      ▼
  loader.py ──► validation.py ──► valid Offers  (invalid → logged, rejected/set aside)
                                      │
 TravelRequest (from cli.py) ────────►│
                                      ▼
                               filtering.py   (HARD constraints)
                                      │
                                      ▼
                               ranking.py     (SOFT preferences + weights)
                                      │
                                      ▼
                               explain.py ──► cli.py shows ranking + explanation
                                      │
                                      ▼
                               booking.py ──► bookings.json + confirmation
```

Turn this into a proper diagram for the report (draw.io, Mermaid or PowerPoint).

---

## 3. Roadmap – step by step plan

This is the plan, to show incremental progress in the git history, and to make sure that the program fits the specifications

### [x] Phase 0 – Skeleton (done)
- [x] Folder structure and modules created
- [x] Sample data for companies, destinations and offers
- [x] Custom exceptions, logging set-up, dataclass models
- [x] `main.py` runs, 6 starter tests pass

### [ ] Phase 1 – Understand and design (Task 1)
*Goal: decide what the program is before coding more.*
- [ ] Write down the requirements in your own words (`docs/requirements.md`)
- [ ] Decide which concepts need **classes** and which are just functions
- [ ] Decide where you will use **inheritance / composition** (and why)
- [ ] Choose your **metaprogramming technique** (required) – options:
      decorator for logging/timing, a **registry** of scoring criteria,
      a descriptor for validated fields, dynamic discovery of company modules
- [ ] Draw the first architecture diagram → `docs/architecture.png`
- [ ] Start a `docs/decisions.md` log: *decision – alternatives – reason*
      (this becomes raw material for the report)

### [ ] Phase 2 – Dataset (Task 2)
*Goal: a realistic dataset of at least 5 companies × 15 destinations.*
- [ ] Decide how each company differs (routes, prices, times, fare rules)
- [ ] Generate/write `offers.csv` with ≥ 75 company–destination combinations
      (several departure times / fare types per combination is better)
- [ ] Make it reproducible: if you generate data with a script, use a fixed random seed
- [ ] Deliberately create a **separate `offers_invalid.csv`** with bad rows
      (negative price, unknown destination, arrival before departure,
      rating outside 0–5, zero seats, bad date, missing field) – for testing

### [ ] Phase 3 – Load and validate (Task 2)
- [ ] Implement `load_offers()` in `loader.py` (type conversion: str → date, time, float, bool)
- [ ] Implement `validate_offer()` in `validation.py`
- [ ] Raise custom exceptions (`ValidationError`, `DataFileError`)
- [ ] Use **regex** where genuinely useful (booking reference – already started – and offer IDs like `OF-\d{4}`)
- [ ] Decide and document: are invalid records **rejected, corrected, or set aside**?
- [ ] Log every rejected record with the reason
- [ ] Handle overnight journeys in `Offer.duration_minutes` (NocheVia!)
- [ ] Tests: normal, invalid, missing file, missing field, boundary values

### [ ] Phase 4 – Hard constraints (Task 3)
- [ ] Decide which conditions are **hard** (must hold) vs **soft** (preference)
- [ ] Implement `filter_offers()` – destination, travel window, budget, seats,
      max transfers, mandatory flexibility
- [ ] Make the hard/soft split **visible to the user** (e.g. show "removed: 4 over budget")
- [ ] Handle "zero offers survive" gracefully
- [ ] Tests incl. boundaries (price exactly at budget, date exactly on window edge)

### [ ] Phase 5 – Weighted ranking (Section 5)
- [ ] Implement normalisation to 0–100 for each criterion
  - price & duration: **lower is better** (invert)
  - departure convenience: based on distance from preferred time
  - flexibility: categorical (e.g. none = 0, changeable = 60, changeable + refundable = 100)
- [ ] Decide handling of: **ties**, **missing values**, **extreme values / outliers**,
      and the case where all offers have the *same* value (division by zero!)
- [ ] Validate weights sum to 1.0 (stub exists) and are not negative
- [ ] Optionally add criteria (transfers, rating, emissions)
- [ ] Return per-criterion scores *and* total score for each offer
- [ ] Tests: hand-calculated expected scores on a tiny dataset

### [ ] Phase 6 – Explanation and traveller profiles (Section 6)
- [ ] Implement `explain_top_offer()` – generated from the data
      (e.g. "direct route, departs 40 min from preferred time, flexible fare; drawback: €7 above cheapest")
- [ ] Never say "objectively best" – say best *under these constraints and weights*
- [ ] Run **≥ 3 profiles** on the same request (budget / business / flexible tourist) and
      save the outputs to `docs/profile_comparison.md`

### [ ] Phase 7 – Booking (Section 6)
- [ ] Select an offer from the ranking
- [ ] Check seats still available
- [ ] Generate unique booking reference (matches your regex)
- [ ] Reduce capacity **consistently** (in memory and in saved data)
- [ ] Save booking incl. fare conditions → `data/bookings.json`
- [ ] Clear confirmation message; simulated payment status only (no real card data!)
- [ ] Tests: last seat, sold out, double booking

### [ ] Phase 8 – Interface polish
- [ ] Interactive CLI menu: enter request → see filtered/ranked offers → book
- [ ] Input validation with helpful error messages
- [ ] (Optional) extensions: cancellation/refund, vouchers, return trips, GUI/web

### [ ] Phase 9 – Evaluation (20% of grade – don't leave this for last!)
- [ ] Run experiments: change weights, see how rankings change
- [ ] Test sensitivity: does one criterion dominate? (e.g. wide price range)
- [ ] Look for **unfair or unreasonable outcomes** (e.g. overnight buses penalised by "convenience")
- [ ] Record limitations and what you would improve
- [ ] Save screenshots / tables / log excerpts to `docs/`

### [ ] Phase 10 – Report and submission
- [ ] Write the report (PDF) – see checklist below
- [ ] Final README check: Python version, libraries, exact run/test commands
- [ ] Make sure a fresh clone runs: `pip install -r requirements.txt` → `python main.py` → `pytest`
- [ ] Include example outputs needed to reproduce report findings
- [ ] Submit PDF + code (zip or GitHub link)

---

## 4. Report checklist

The **report is the main assessed deliverable**. Keep source code out of it.

| Required content | Where it comes from |
|---|---|
| Flowchart / architecture diagram | Phase 1 |
| Dataset description and validation | Phases 2–3 |
| ≥ 3 traveller-profile comparisons | Phase 6 |
| Limitations and possible unfair outcomes | Phase 9 |
| Generative-AI declaration (what for, how checked, what you changed) | **keep notes as you go** |

### Grading weights

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

## 5. Technical requirements – tracker

- [ ] Modular application (multiple cohesive modules)
- [ ] File I/O (source data, bookings, config, logs)
- [ ] Custom error handling (invalid input, missing files, inconsistent data)
- [ ] Regex used where genuinely suitable
- [ ] One metaprogramming technique (decorator / registry / descriptor / dynamic discovery)
- [ ] Intuitive interface (CLI is fine)
- [ ] Reproducible ranking (same input → same output)
- [ ] Tests: normal, invalid, missing-data, boundary

---

## 6. Working habits that save marks

1. **Commit after every phase** with a meaningful message.
2. **Keep `docs/decisions.md` updated** – it feeds the design and reflection sections.
3. **Log your AI use** as you go (prompt → what you used → how you verified it).
4. Write the tests for a phase *before or while* coding it, not at the end.
5. Prefer a small, explainable scoring model over a clever one.

---

## 7. Python version and dependencies

- Python 3.10 or newer
- No third-party runtime dependencies
- `pytest` for testing (`requirements.txt`)
