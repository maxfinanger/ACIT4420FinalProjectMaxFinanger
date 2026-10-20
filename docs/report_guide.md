# Guide for writing the report

The report is written by me, in `report/BusBidder_Report.docx` (the skeleton with comments). This file lists, section by
section, what to say and where the material is, so nothing has to be searched for. Every number below comes from a file in
the repository that can be regenerated.

## Order of work

1. Run everything once so the numbers in the report are fresh: `python -m pytest -q`, `python scripts/make_examples.py`,
   `python scripts/evaluate.py`, `python scripts/compare_profiles.py`.
2. Write 4 (design) and 5 (implementation) first, they are the most concrete.
3. Then 6 (testing) and 7 (evaluation, 20% of the grade), then 1-3, and the summary last.
4. Take the screenshots (list below), fill the AI declaration, check the pre-submit list at the end.

## Section by section

| Section | What to say | Material |
|---|---|---|
| Problem and requirements | The research question; the hard/soft split; what is in and out of scope; the requirements table FR1-FR14 | `README.md` top, `docs/requirements.md` |
| Design | Modules and data flow; classes vs functions (D2); composition (D3) and inheritance for constraints (D4); the metaprogramming choice, a decorator registry (D5); why standard library only (D1); why CSV/JSON (D1, D9) | `docs/decisions.md` D1-D8, `docs/architecture.png`, `docs/class_diagram.png` |
| Data | Synthetic data, 5 companies, 15 destinations, 1497 offers, how companies differ, fixed seed (D10); overnight journeys (D11); fare types (D12) | `docs/dataset.md` |
| Validation | Reject, not correct (D7); 16 error categories; regex and why `\A..\Z` (D13); file-level errors; logging | `docs/validation.md`, `docs/examples/validation_invalid_file.txt` |
| Filtering | Which conditions are hard and why (D6, D14); the removal counts; the "no result" message | `docs/filtering.md`, `docs/examples/filter_spec_example.txt`, `filter_no_result.txt` |
| Scoring | Formula; the five design questions; relative vs absolute scales (D15); ties, missing and extreme values (D16); weight vs real influence; the hand-calculated example | `docs/scoring.md`, `docs/examples/ranking_*.txt` |
| Explanation and profiles | Generated text, never "objectively best" (D17); four profiles give four different winners (D18) | `docs/explanation.md`, `docs/profile_comparison.md` |
| Booking | One file as the truth, atomic write, re-read before booking, reference regex, no payment data (D19, D20) | `docs/booking.md`, `docs/examples/booking_demo.txt` |
| Interface | Menu, forgiving input, explicit confirmation (D21) | `docs/interface.md`, `docs/examples/interactive_session.txt` |
| Testing | 617 tests; what each file covers; boundary values; mutation checks; bugs the tests found (below) | `README.md` section 5, `tests/` |
| Evaluation | Experiments, findings, limits, unfair outcomes, improvements | `docs/evaluation.md`, `docs/limitations.md` (D22) |
| Reproducibility | Fixed seeds, generated documents checked by tests, exact commands | the command list at the end of this file |
| AI declaration | See the template below | `README.md` section 8 |

## Key numbers (from the generated files)

- 5 companies, 15 destinations, 1497 offers (1497 accepted, 0 rejected); the invalid test file has 20 rows, 16 error categories.
- Spec example (Malaga, 12-14 July, max EUR 50, at most 1 transfer, changeable): 47 offers remain.
- Four profiles, four different winners from four companies (`docs/scoring.md`, table "Profiles on the spec example").
- Winner stable: 15 of 18 weights can move 10 points or more; 98% or more of random +-30% weight changes keep the winner.
- Parameter sensitivity: the winner changed in only 2 of 108 cases.
- Only 12 of 47 offers can win under any weighting; three offers win 76% of random weightings.
- Rank reversal: removing one non-winning offer changed the order of the others in 2 of 46 cases; the winner never changed.
- Largest gap between weight and influence: +9 points (departure, business), -10 points (flexibility, tourist).

## Bugs and corrections the tests and experiments found (good for the reflection)

1. `$` in a regex accepted `"OF-0001\n"`; fixed with `\A..\Z` (D13).
2. `input` was bound when the function was defined, so scripted sessions could not replace it (D21).
3. A generated document went stale after a wording change; now a test compares it with the script (D17, D18).
4. A name rule refused the curly apostrophe typed on phones; names are normalised to a straight apostrophe.
5. My own sentence "strict requirements leave only NocheVia for Barcelona" was false; the experiment (5c) showed the real picture and
   `docs/filtering.md` carries a correction note. Do not repeat the false claim in the report.
6. I expected a wide price range to give price more influence; experiment 3b showed the opposite.
7. Final audit: development wording in the terminal output, a program that only worked from the project folder, and `nan` accepted as a
   budget by the command line. All three are now covered by `tests/test_delivery.py`.

## Screenshots to take

| # | What | Command |
|---|---|---|
| S1 | The load summary and the rejected rows | `python main.py --offers data/offers_invalid.csv` |
| S2 | Hard and soft requirements and the removal counts | the spec example (see commands) |
| S3 | The ranking with criterion scores and real influence | the spec example |
| S4 | The explanation of the top offer | the spec example |
| S5 | The four profiles compared | `--compare-profiles` |
| S6 | A booking and the refused duplicate | `docs/examples/booking_demo.txt` (use `--bookings` with a temporary file) |
| S7 | The interactive menu with a mistaken answer | `python main.py --interactive` |
| S8 | The test run | `python -m pytest -q` |

## AI declaration, template (fill in the brackets yourself)

- **Tool:** Claude (Anthropic), used through a chat and coding assistant.
- **What it was used for:** planning the phases, drafting the source modules, the tests, the data generator, the evaluation scripts, the
  diagrams and the first versions of the documentation; discussing design alternatives.
- **What I did myself:** [your own decisions, edits, what you changed or rejected, the report text, the checking you did].
- **How the output was checked:** I ran the 617 tests; I checked the worked scoring example by hand; the generated documents are compared
  with their scripts by tests; I broke the code on purpose to see that the tests fail (booking and menu); I found and corrected the mistakes listed above.
- **Responsibility:** I have read and understood the code and the report, and I am responsible for the submitted work.

## Commands to reproduce the results

```bash
python -m pytest -q
python main.py --offers data/offers_invalid.csv
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable --compare-profiles
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable --profile business_traveller --preferred-departure 08:00
python scripts/generate_data.py && python scripts/compare_profiles.py && python scripts/evaluate.py && python scripts/make_examples.py
```

## Before submitting

- [ ] Python version and libraries stated in the report
- [ ] Every figure and table is referred to in the text
- [ ] No claim without evidence in `docs/` or a test
- [ ] The false "only NocheVia" claim is not in the report
- [ ] AI declaration filled in
- [ ] Link to the repository (or the zip) on the front page
- [ ] `data/bookings.json` and `logs/*.log` are not in the zip
