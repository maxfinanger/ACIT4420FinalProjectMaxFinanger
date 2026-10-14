# Validation rules (Phase 3)

How the loader decides whether an offer record is acceptable. Code:
`busbidder/loader.py` (conversion, file errors, duplicates) and
`busbidder/validation.py` (rules). Decisions: D7 and D13 in `decisions.md`.

## Policy

A bad record is **rejected, not corrected**. It is logged as a warning with row
number, offer id, category and reason, and kept in `LoadResult.rejected` so it can be
reviewed. Loading continues with the other rows. `python main.py --offers
data/offers_invalid.csv` shows this on the test file.

Only harmless clean-up is done: whitespace around values is removed, `yes/no`
(also `true/false/1/0`) is case-insensitive, a UTF-8 BOM is ignored. Names are
case-sensitive (`malaga` is not `Malaga`).

Row numbers count data rows after the header (the first offer is row 1).

## Record-level rules (16 error categories)

| Category | Rule | Checked in | Example row in `offers_invalid.csv` |
|---|---|---|---|
| `malformed_row` | wrong number of columns | `check_row_structure` | 17 |
| `missing_field` | a required field is empty | `check_row_structure` | 10 |
| `bad_offer_id` | must match `OF-` + 4 digits (regex) | `build_offer` | 12 |
| `invalid_date` | `YYYY-MM-DD` (regex) and a real calendar date | `build_offer` | 5 |
| `invalid_time` | `HH:MM`, 00:00 to 23:59 (regex) | `build_offer` | 13 |
| `invalid_number` | price, rating, emissions not a finite number; transfers, luggage, seats not a whole number; luggage below 0 | `build_offer`, `validate_offer` | 11 |
| `invalid_boolean` | changeable/refundable not yes/no | `build_offer` | 15 |
| `negative_price` | price must be above 0 | `validate_offer` | 2 |
| `negative_transfers` | transfers must be 0 or more | `validate_offer` | 14 |
| `rating_out_of_range` | rating 0 to 5, both ends allowed | `validate_offer` | 7, 8 |
| `no_seats` | at least 1 seat available | `validate_offer` | 9 |
| `unknown_destination` | not in `destinations.csv` | `validate_offer` | 3 |
| `unknown_company` | not in `companies.csv` | `validate_offer` | 4 |
| `arrival_before_departure` | arrival date+time must be after departure date+time | `validate_offer` | 6 |
| `impossible_duration` | journey longer than 24 hours | `validate_offer` | 18 |
| `duplicate_id` | offer id already loaded (first valid row wins) | `load_offers` | 16 |

Not rejected on purpose (must stay valid): overnight journeys (row 19), and the lowest
allowed values rating 0.0 and 1 seat (row 20). `emissions_kg` is optional.

Check order within a row: structure, id, dates, times, numbers, yes/no, then the
business rules, then duplicates. A row is reported with the first problem found.

## File-level errors (`DataFileError`, program stops)

File not found, empty file (no header), missing required column, file that cannot be
read or decoded, invalid JSON in the profiles file, empty company or destination name.
All are logged as errors, and `main.py` prints `Error: ...` and exits with code 1.

## Evidence

- `tests/test_validation.py`: business rules and boundaries (price 0.01 accepted, 0 rejected;
  duration exactly 24 h accepted, 24 h 1 min rejected; rating 0 and 5 accepted), row structure,
  regex patterns.
- `tests/test_loader.py`: type conversion, every file-level error, duplicate handling,
  logging, loading the real file (1497 accepted, 0 rejected), and the invalid file against
  `offers_invalid_expected.json` row by row.
- The test suite found one real bug: `$` in the first regexes accepted `"OF-0001\n"`
  (see D13). Good example for the report.

## Limitations

- Plausibility is not checked: a 1 EUR ticket to Cadiz or a very high price passes.
- `fare_type` is accepted as any non-empty text.
- A row with two problems is only reported with the first one.
- Valid-looking but wrong data (a correct but wrong price) cannot be detected.
- Blank lines in the CSV are skipped by the reader, so they do not count as rows.
