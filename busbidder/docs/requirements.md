# Requirements (draft)

Written from the project specification (FinalProjectDescription.pdf). Section
numbers in brackets refer to that document. This is a working draft, I will
adjust it as the design becomes clearer.

## 1. What the system should do (in my own words)

BusBidder Spain is a fictional marketplace where five bus companies offer
journeys from Madrid to fifteen destinations. A traveller describes what they
need. The program removes offers that are unacceptable, ranks the rest, explains
the top choice, and lets the traveller make a simulated booking.

## 2. Functional requirements

| ID | Requirement | Spec ref | Planned in |
|---|---|---|---|
| FR1 | Read companies, destinations and offers from files | Task 2 | Phase 3 |
| FR2 | Convert fields to proper types and detect missing, inconsistent or impossible values (negative price, unknown destination, invalid date, arrival before departure, rating out of range, no seats) | Task 2 | Phase 3 |
| FR3 | Report important failures with custom exceptions and write events/errors to a log file | Task 2 | Phase 3 |
| FR4 | Use a regular expression where it genuinely fits (booking reference, offer id) | Task 2 | Phase 3 |
| FR5 | Separate mandatory constraints from preferences, and remove offers that break a mandatory constraint before ranking | Task 3 | Phase 4 |
| FR6 | Make the hard/soft split visible to the user | Task 3 | Phase 4 |
| FR7 | Rank remaining offers with a weighted model using at least four criteria (price, duration, departure convenience, flexibility) | Sec. 5 | Phase 5 |
| FR8 | Let the traveller express the relative importance of the criteria, and validate that the weights are valid (sum to 1.0) | Sec. 5 | Phase 5 |
| FR9 | Normalise criteria to a comparable scale; handle lower-is-better vs higher-is-better, ties, missing values and extreme values | Sec. 5 | Phase 5 |
| FR10 | Show ranked offers with values, criterion scores and total score | Sec. 6 | Phase 6 |
| FR11 | Generate a short explanation for the top offer from the data, including remaining disadvantages, without calling it "objectively best" | Sec. 6 | Phase 6 |
| FR12 | Support at least three traveller profiles and show that they give different recommendations | Sec. 6 | Phase 6 |
| FR13 | Book an offer: check seats, make a unique reference, save the booking, reduce capacity, store the fare conditions, confirm | Sec. 6 | Phase 7 |
| FR14 | Provide a command-line interface | Sec. 7 | Phase 8 |

## 3. Non-functional requirements

| ID | Requirement | Spec ref |
|---|---|---|
| NFR1 | Modular Python application with several cohesive modules | Sec. 7 |
| NFR2 | File input/output for data, bookings, configuration and logs | Sec. 7 |
| NFR3 | One class/metaprogramming technique (decorator, registry, descriptor or dynamic discovery) | Sec. 7 |
| NFR4 | Reproducible ranking: same data and settings give the same result | Sec. 7 |
| NFR5 | Automated tests for normal, invalid, missing-data and boundary cases | Sec. 7 |
| NFR6 | README with Python version, libraries, entry point, input locations and exact run/test commands | Sec. 11 |
| NFR7 | No real payment data is collected, payment is simulated | Sec. 6 |

## 4. Dataset requirement

At least 5 companies x 15 destinations = 75 company-destination combinations.
Offers should also differ in departure times and fare types.

## 5. Assumptions (so far)

- All journeys start in Madrid (the departure hub).
- Prices are in euro and all times are local Spanish time.
- One booking is for one traveller and one seat (group bookings would be an extension).
- All data is fictional, so there is no connection to real timetables or prices.

## 6. Out of scope for now (possible extensions)

Date changes and cancellation fees, vouchers, return/multi-city journeys,
waiting lists, seat selection, and a graphical or web interface. I will only
start these if the core is finished and tested.

## 7. Open questions

- Which of the spec's example constraints should be hard for each profile, and
  is "changeable ticket" always hard? (decide in Phase 4, see decisions.md D6)
- Should invalid offers be corrected anywhere, or always rejected? (Phase 3, D7)
- Which extra criteria are worth adding on top of the mandatory four? (Phase 5)
