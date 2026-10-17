# The interactive menu (Phase 8)

Code: `busbidder/interactive.py` (menu, questions, parsers), `busbidder/display.py` (everything that is printed,
shared with the command-line options), `busbidder/cli.py` (`--interactive`). Decision: D21.

```bash
python main.py --interactive        # or -i
```

Everything the menu does can also be done with command-line options (`docs/booking.md`, `docs/filtering.md`), and
both print the same text, because they use the same functions in `display.py`.

## The menu

| Option | What it does |
|---|---|
| 1 New search | Asks for destination, dates, budget, transfers, changeable ticket, preferred departure time and profile (and, if you want, journey time and luggage). Shows the hard requirements, the soft preferences, what was removed and why, the ranking, and the explanation |
| 2 Show all ranked offers | The ranking is shortened to the top 10; this prints every offer of the last search |
| 3 Rank again | The same offers with another profile or your own weights (the filtering is repeated, so it is always consistent) |
| 4 Compare profiles | The winner under every profile and where each winner ranks under the others |
| 5 Book an offer | Choose by rank number or offer id, enter a name, **confirm with y**, and the booking is saved |
| 6 Show saved bookings | The bookings file as a table |
| 7 Help | Hard versus soft, and the typing tips |
| 0 Quit | (`q`, `quit` and `exit` also work at the menu) |

Options 2-5 need a search first, and say so if there is none.

## Helpful input (D21)

Each answer is checked by a small function that is also tested alone. A wrong answer gets a message that
says what was expected, and the same question is asked again.

| Question | Accepted | Message when wrong |
|---|---|---|
| Destination | number from the list, name, any case, no accents (`Málaga`), a unique start (`sant`) | `'Malga' is not a destination. Did you mean: Malaga?` (also lists the candidates when a start is ambiguous) |
| Dates | `2026-07-12`, `12/07/2026`, `12.7.2026` (day first) | `Dates look like 2026-07-12 ... and must be real dates.` The latest date cannot be before the earliest |
| Budget | `50`, `49,90`, `€50`, `EUR 50`, `50 eur` | `Enter the maximum price in euros as a number above 0, e.g. 50 or 49,90.` |
| Transfers | `0`-`9`, `direct`, Enter or `any` = no limit | `Enter a whole number from 0 to 9 (0 = direct only), or leave it empty for no limit.` |
| Journey time | `6`, `6.5`, `6,5`, `6h30` (Enter = no limit) | `Enter the longest journey in hours, e.g. 6, 6.5 or 6h30 (at most 48) ...` |
| Luggage | `20`, `20kg` | `Enter the luggage allowance you need in kg ...` |
| Yes/no | `y`, `yes`, `j`, `ja`, `n`, `no`, `nei`; Enter = the default in `[ ]` | `Please answer y (yes) or n (no).` |
| Departure time | `9`, `9:30`, `9.30`, `09:00` (24 h) | `Times look like 09:00, 9:30 or 9.30 (24-hour clock).` |
| Profile | number, name, `c` for own weights | `Unknown profile ...` / `Choose a number between 1 and 4 ...` |
| Own weights | `price=40,duration=25,...` adding up to 100 (or 1.0) | the weight error and an example |
| Selection to book | rank number or offer id | `rank 99 is not in the ranking (1-47)`, `OF-0001 is not among the 47 acceptable offers` |
| Name | letters, spaces, hyphens, apostrophes, full stops | `name may only contain letters ... (no digits: no payment data is collected)` |

Other behaviour:

- **`q` cancels** the current question and goes back to the menu, and 8 unusable answers in a row cancel it too (so a
  stuck script cannot loop forever).
- **Enter** accepts the default shown in brackets.
- **Nothing is saved without a `y`.** The confirmation defaults to no.
- **End of input and Ctrl-C** end the session politely, never with a traceback.
- **Problems do not end the session:** a sold-out offer, a duplicate booking, a corrupt bookings file or a request the filter
  rejects each give a message and return to the menu. A corrupt bookings file is never overwritten.
- Dates outside the data (offers exist for 11-15 July 2026) are pointed out before the search.

## Example (generated)

Part of `docs/examples/interactive_session.txt`, which is produced by `python scripts/demo_interactive.py`
(scripted answers, a temporary bookings file and a fixed seed, so it is identical every time):

```
Destination (number or name): Malga
  ! 'Malga' is not a destination. Did you mean: Malaga?  (q = cancel)
Destination (number or name): Málaga
  (offers exist for 2026-07-11 to 2026-07-15)
Earliest departure date (e.g. 2026-07-12): tomorrow
  ! Dates look like 2026-07-12 (year-month-day) or 12/07/2026 (day/month/year), and must be real dates.  (q = cancel)
Earliest departure date (e.g. 2026-07-12): 12/07/2026
Latest departure date (Enter = same day): 2026-07-11
  ! The latest date cannot be before the earliest (2026-07-12).  (q = cancel)
Latest departure date (Enter = same day): 14.7.2026
Maximum price in EUR (e.g. 50): abc
  ! Enter the maximum price in euros as a number above 0, e.g. 50 or 49,90.  (q = cancel)
Maximum price in EUR (e.g. 50): 49,90
Maximum transfers (0 = direct only, Enter = no limit): 1
Must the ticket be changeable? [y/N]: y
Preferred departure time (Enter = 09:00): 9.30

```

## Limitations

- It is a text interface only. A graphical or web interface is one of the optional extensions and is not built.
- The text is English only. Accent-insensitive matching covers European names (Málaga, Córdoba) but not other scripts.
- `07/12/2026` is read day first (7 December), as is usual in Spain and Norway. The format is stated in the error message, but a user who
  expects month first would be confused. ISO dates avoid it.
- There is no way to go back one question, only to cancel (`q`) and start the search again.
- The menu does not remember earlier searches, only the last one.
- A piped (non-terminal) session does not echo the answers; use the transcript script to see them.
- Optional extensions that are **not** built: cancellation and refunds, vouchers, return and multi-city journeys, waiting lists, seat selection, group
  bookings, notifications. They are future work (and are listed in the limitations of `docs/booking.md`).

## Evidence

`tests/test_interactive.py` (156 tests): every parser with valid, invalid and boundary input (48 h, 24:00, 6h75, 1,000 ...);
scripted sessions for the happy path, every kind of bad answer, `q`, too many bad answers, end of input, Ctrl-C,
searches with no result, dates outside the data, extra limits, re-ranking with a profile and with own weights, comparing,
booking (saved, declined, default answer, bad selection, bad name, duplicate, an offer that sells out during the session, a corrupt
file), listing bookings, a marketplace without booking, and the command-line flag. Mutation check: removing the confirmation, `q`
cancelling, accent handling, the default answer and the comma decimals each made a test fail. Testing found one real defect:
`input` was bound when the function was defined, so it could not be replaced later; it is now looked up when used.
