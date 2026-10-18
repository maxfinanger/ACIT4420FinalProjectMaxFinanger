# Hard and soft: how the filter works (Phase 4)

Code: `busbidder/filtering.py` (constraints and `filter_offers`), `busbidder/validation.py`
(`validate_request`), `busbidder/marketplace.py` (`Marketplace.filter`), `busbidder/cli.py`
(display). Decisions: D4, D6, D14.

## Hard and soft conditions

| Condition | Hard or soft | Justification (draft) | Class / criterion |
|---|---|---|---|
| Destination | Hard, always | A bus to another city is no alternative at any score | `DestinationConstraint` |
| Travel window | Hard, always | The traveller cannot travel on other days. Checked on the departure date, both end days included | `TravelWindowConstraint` |
| Seats available | Hard, always | A full bus cannot be booked | `SeatsConstraint` |
| Maximum budget | Hard, always | A spending limit, not a wish | `BudgetConstraint` |
| Maximum transfers | Hard only if set | Some travellers cannot manage transfers (luggage, mobility). If not set, transfers are not scored | `MaxTransfersConstraint` |
| Maximum duration | Hard only if set | A real deadline for some. If not set, shorter is better (soft) | `MaxDurationConstraint`, criterion `duration` |
| Minimum luggage | Hard only if set | A traveller with a bike or a suitcase cannot use a 10 kg fare | `LuggageConstraint` |
| Changeable ticket | Hard only if required | "Must be changeable" is a requirement. If not required, flexibility is rewarded (soft) | `FlexibilityConstraint`, criterion `flexibility` |
| Departure time | Soft, always | One hour from the preferred time is a trade-off, not a dealbreaker | criterion `departure` |
| Price within the budget | Soft | Cheaper is better, but only among offers that fit the budget | criterion `price` |
| Refundable, rating, emissions | Soft | Nice to have, can be traded | criteria (Phase 5) |

Optional constraints are *inactive* when the traveller does not set them. An inactive
constraint is neither applied nor shown in the removal report.

## How it is shown to the user

`python main.py --destination ... --from ... --to ... --budget ...` prints:

1. **HARD constraints** the traveller required (only the active ones).
2. **SOFT preferences** with the profile weights, taken from the criteria registry.
3. How many offers each rule removed, and how many remain.
4. The remaining offers, explicitly marked *not ranked yet*.

Saved outputs (reproducible). Since Phase 5 the same commands also show the ranking of the remaining offers (`docs/scoring.md`):

| File | Command |
|---|---|
| `docs/examples/filter_spec_example.txt` | `python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable --preferred-departure 09:00` |
| `docs/examples/filter_no_result.txt` | `python main.py --destination Toledo --from 2026-07-12 --to 2026-07-14 --budget 3` |
| `docs/examples/validation_invalid_file.txt` | `python main.py --offers data/offers_invalid.csv` |

## Empty results

When no offer survives, the program says so and names the single requirement whose
relaxing would give back the most offers ("near miss"). Example: a EUR 3 budget to Toledo
removes everything, and relaxing the budget alone would give 49 offers.
An invalid request (window start after end, budget 0 or below, negative limits, unknown
destination) is rejected with a clear message and exit code 2 before any filtering.

## Observations to use in the evaluation

- For the spec example (Malaga, 12-14 July, max EUR 50, at most 1 transfer, changeable
  required) 47 of 1497 offers remain, from all five companies. 1373 are removed only
  because of the destination.
- Strict requirements narrow the field of companies, but only slowly. **Correction:** an earlier version of this
  file said that Barcelona, 11-15 July, max EUR 45, direct, at least 20 kg and at most 9 h leaves "16 offers, all from
  NocheVia". That was wrong. The 16 offers come from four companies (Camino Express, CostaLink, NocheVia, VerdeBus). The mistake
  came from reading the first ten lines of a list sorted by departure time, where NocheVia's early-morning
  departures come first. The measured picture is in `docs/evaluation.md` section 5c: a single company
  only remains for the strictest combination tested, and then for few destinations.
- Hard constraints are binary. An offer EUR 0.01 over the budget is removed completely
  (a "cliff"), while an offer exactly at the budget is kept. This is the main
  weakness of the hard/soft split and a good limitation to discuss.

## Limitations

- The removal counts depend on the order of the constraints (D14). Near misses are
  order independent.
- The window only looks at the departure date. A traveller who needs to ARRIVE within the
  window is not served.
- Seats are per fare type (D12). After Phase 7, booked seats are subtracted before filtering (D9).
- Only one destination per request and no return journeys.

## Evidence

`tests/test_filtering.py` (51 tests): every constraint with boundary values (budget
49.99 / 50.00 / 50.01, window edge days, one-day window, duration 390 vs 391 min incl.
overnight, luggage 19 vs 20 kg, direct-only), inactive constraints, counting rules,
empty input, no survivors and near misses, input not modified and order independent,
invalid requests, the real data checked against an independent calculation, and the CLI.
