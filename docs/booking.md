# Booking

Code: `busbidder/booking.py` (`BookingService`, `select_from_ranking`, the texts),
`busbidder/validation.py` (`clean_traveller_name`), `busbidder/marketplace.py` (`Marketplace.book`),
`busbidder/cli.py` (the options). Decisions: D9, D19, D20.

No real payment data is ever collected. Payment is the fixed status `SIMULATED-PAID`.

## What the spec asks for, and where it is done

| Spec | How |
|---|---|
| Select an offer after viewing the ranking | `--book RANK` or `--book OFFER_ID`, chosen from the ranking that was just shown. Only an offer that passed the hard constraints can be chosen |
| Confirm that seats remain available | `book()` re-reads the bookings file and checks `capacity - seats sold >= 1` |
| Unique booking reference, saved | `BB-<travel date>-<6 characters>`, checked against every saved reference, saved to `data/bookings.json` |
| Reduce available capacity consistently | The bookings file is the only record of seats sold. `seats_available == capacity - bookings`, in memory and after a restart |
| Store the fare conditions with the booking | The booking has its own copy of fare type, changeable, refundable and luggage |
| Clear confirmation | `BOOKING CONFIRMED` block (see below) |
| Simulated payment | `payment_status = SIMULATED-PAID`, the only personal data is a name |

## The flow

```
ranking shown ── --book 1 / OF-1025 ──► select_from_ranking (must be in the ranking)
      │
      ▼
BookingService.book(offer, name)
  1. check the name                      (letters only, no digits)            -> ValidationError
  2. re-read data/bookings.json          (the file is the truth)              -> DataFileError if unreadable
  3. seats left? capacity - sold >= 1                                          -> SoldOutError
  4. same traveller already on this offer?                                     -> DuplicateBookingError
  5. make a unique reference (retry on collision)                              -> BookingError after 100 tries
  6. write the whole file atomically     (temp file, then rename)             -> BookingError, nothing changed
  7. only now reduce seats_available in memory
  8. log the booking and return it
```

The order matters: the seat count in memory is only reduced **after** the booking is safely on disk, so a failed
save never leaves the program thinking a seat is gone. A test mutates this order and fails (checked).

## Seats: one source of truth (D9, D19)

- `data/offers.csv` is never modified (a test checks its checksum before and after).
- `Offer.capacity` is the seat count from that file, `Offer.seats_available` is what is left.
  At start-up `apply_to_offers` sets `seats_available = capacity - bookings in the file`.
- `book()` does **not** trust the in-memory number. If two program runs use the same file, the second one still
  sees the first one's booking (test: `test_a_stale_offer_cannot_oversell_because_the_file_is_the_truth`).
- Once the last seat is booked, `SeatsConstraint` removes the offer, and the filter report shows
  `removed 1  no seats left` (test: `test_a_sold_out_offer_disappears_from_the_next_search`). Before this phase that constraint
  never removed anything.
- Fare types do not share seats (D12), so each offer row has its own capacity.

## Rules

- **One booking = one seat.** Group booking is an extension that is not built.
- **Double booking:** the same name (ignoring case and extra spaces) cannot book the same offer twice. Different
  names can, and the same name can book different offers.
- **Name:** letters (any language), spaces, hyphens, apostrophes and full stops, at most 60 characters. **No digits**, on
  purpose: a card number typed in by mistake is refused and never stored (D19). This is one of the few places where a
  regular expression is genuinely suitable (it is a format rule).
- **Reference:** `BB-YYYYMMDD-XXXXXX`, the date is the **travel date**. The six characters come from 32 letters and
  digits without `0 O 1 I`, so a reference can be read out loud. That gives about a billion combinations per date. References
  are labels, not secrets.
- **Reproducible demos:** the environment variable `BUSBIDDER_SEED` makes the references repeatable. It is only for
  demos and the report: without it the references come from the operating system's random source.

## The bookings file

`data/bookings.json` is created on the first booking and ignored by git. A saved booking:

```json
{
  "reference": "BB-20260714-WK3DEG",
  "offer_id": "OF-1025",
  "company": "SolRuta",
  "destination": "Malaga",
  "travel_date": "2026-07-14",
  "departure_time": "07:00",
  "arrival_date": "2026-07-14",
  "arrival_time": "15:35",
  "price_paid": 31.5,
  "traveller_name": "Ana Pérez",
  "fare": {
    "fare_type": "Standard",
    "changeable": true,
    "refundable": false,
    "luggage_kg": 20
  },
  "payment_status": "SIMULATED-PAID",
  "booked_at": "2026-10-16T05:40:52"
}
```

The file is written as a whole to a temporary file in the same folder and then renamed, so a crash cannot leave half a file.
When it is read, every booking is checked (reference format, no duplicate references, real dates and times,
price above 0, boolean fare fields, valid name). A file that cannot be read or is inconsistent stops the program with
`Error: ... booking #n: ...` and is **never overwritten**, so a bad edit cannot silently destroy the records (20 corrupt variants
are tested, each also checked byte for byte).

## Command line

```bash
# book the top offer for the example request (the booking is saved in data/bookings.json)
python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable --book 1 --name "Ana Perez"

# book by offer id, and use another bookings file (handy for trying things without touching your real one)
python main.py ... --book OF-1025 --name "Eva Larsen" --bookings /tmp/try.json

python main.py --show-bookings
```

Exit codes: `0` ok, `1` a data file is missing or unreadable, `2` invalid request, selection or name, `3` booking refused
(duplicate, sold out). A saved transcript is in `docs/examples/booking_demo.txt`.

## Limitations

- **No locking between programs.** The file is re-read before each booking and replaced atomically, which protects
  against stale in-memory data and crashes. Two programs booking at exactly the same moment could still both read the old file,
  and the last write wins. A real system would use a database or a lock. For one user at a time (this project) it is fine.
- Bookings cannot be cancelled, changed or refunded, and there are no vouchers. Those are the optional extensions in the spec.
- Only a name is stored. There is no account, so "the same traveller" means "the same name".
- Seat counts per fare type are independent (D12), which a real bus would not do.
- The booking date/time (`booked_at`) is the local clock of the computer.
- Selection is done with command-line options. The interactive menu does the same step by step (`docs/interface.md`).

## Evidence

`tests/test_booking.py` (98 tests): name rules; the saved fields, round trip and no payment data in the file; last
seat, sold out and every seat booked once; a stale offer cannot oversell; double booking; seat counts after a restart;
offers file unchanged; unknown offer and oversold store (warnings); 20 corrupt files; failed saves leave nothing behind and the old file intact;
unique references (120 bookings), collision retry and giving up; choosing from the ranking; the texts; the marketplace on real data
(a sold-out offer disappears from the next search); and the CLI (all exit codes, reproducible reference, seats going down).
Mutation check: breaking the file-as-truth rule, the duplicate check, the case-insensitive check, the save order and the
corrupt-file protection each made a test fail.
