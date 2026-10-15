# The scoring model (Phase 5)

Code: `busbidder/criteria.py` (the criteria), `busbidder/ranking.py` (weights, ranking, ties,
influence), `busbidder/scoring_config.py` and `config/scoring.json` (parameters).
Decisions: D5, D15, D16.

## The formula

```
total(j) = w_price * P(j) + w_duration * D(j) + w_departure * T(j) + w_flexibility * F(j)   (+ optional criteria)
```

Every criterion score is on a **0-100 scale where higher is always better**, and the weights add
up to 1.0, so the total is also 0-100. "Lower is better" criteria (price, duration) are
inverted inside their own function.

## Criteria

| Criterion | Raw value | Scale type | Score |
|---|---|---|---|
| `price` | EUR | relative | 100 for the cheapest; loses 100 points over the price spread (at least EUR 5) |
| `duration` | minutes | relative | 100 for the shortest; loses 100 points over the spread (at least 60 min) |
| `departure` | minutes from the preferred time, around midnight too | absolute | `100 * (1 - diff / 360)`, so 100 at the preferred time and 0 at 6 h away |
| `flexibility` | changeable / refundable | absolute | none 0, changeable 60, refundable 40, both 100 |
| `transfers` (optional) | number | absolute | `100 * (1 - n / 3)`, direct = 100 |
| `rating` (optional) | 0-5 | absolute | `rating / 5 * 100` |
| `emissions` (optional) | kg CO2 | relative | like price, over the offers that report a figure (at least 2 kg spread) |

Optional criteria only count when a profile or `--weights` gives them a weight. The profile
`environment_focused` uses `emissions` and `transfers`.

**Relative** means the offer is judged against the others in the list (price has no natural
"good" level). **Absolute** means the scale has its own reference point (the preferred time, the fare
category, a direct bus, 5 stars), so the score does not change with the other offers.

## Worked example (also a test: `test_hand_calculated_*`)

Three offers, preferred departure 09:00, weights 40 / 25 / 15 / 20:

| Offer | Price | Duration | Departs | Fare | P | D | T | F | Total |
|---|---|---|---|---|---|---|---|---|---|
| A | EUR 30 | 6 h 00 | 09:00 | none | 100 | 100 | 100 | 0 | 0.4*100 + 0.25*100 + 0.15*100 + 0.2*0 = **80.0** |
| B | EUR 35 | 6 h 30 | 10:30 | changeable | 50 | 50 | 75 | 60 | 20 + 12.5 + 11.25 + 12 = **55.75** |
| C | EUR 40 | 7 h 00 | 12:00 | both | 0 | 0 | 50 | 100 | 0 + 0 + 7.5 + 20 = **27.5** |

Price: best 30, worst 40, spread 10: B = 100 - 100 * 5/10 = 50. Duration: spread 60 min: B = 50.
Departure: B is 90 min away: 100 * (1 - 90/360) = 75. With flexibility weighted 70% (and 10% each on the
others) the same offers give C 75.0, B 59.5, A 30.0: the order turns upside down.

## The five design questions from the spec

1. **Normalisation.** Everything is mapped to 0-100. Price, duration and emissions use a relative
   scale (best = 100, each "meaningful difference" costs 100 points). The others use fixed reference
   points (D15).
2. **Lower or higher is better.** The criterion function does the inversion, so the ranker only
   ever sees "higher is better". Adding a criterion never requires changing the ranker.
3. **Weights.** `validate_weights` requires at least one weight, only known criteria, finite numbers,
   none negative, and a sum of 1.0 (tolerance 1e-9, so `0.1 + 0.2 + 0.7` is fine). `--weights` also
   accepts percentages that add up to 100. Anything else gives a clear `WeightError`.
4. **Ties, missing values, extreme values (D16).**
   - Ties: totals are compared to 2 decimals (what the user sees). Ties are broken by lower price, shorter
     journey, earlier departure, then offer id. The result is the same for any input order, and the table
     marks the offers that needed a tie-break.
   - Missing values: only `emissions_kg` can be missing. An offer without a figure scores
     `missing_value_score` (0): no information is not good news. If nobody reports a figure, everybody gets the same.
   - Extreme values: a value worse than 2x the median counts as the worst value, so one 24-hour bus
     cannot stretch the duration scale. All offers equal, or only one offer, gives everyone 100 on the relative criteria (no division by zero).
5. **One criterion dominating.** (a) Every score uses the same 0-100 range. (b) The minimum spread stops tiny
   differences (EUR 1 on a EUR 30 ticket) from being blown up to 100 points. (c) The outlier cap. (d) The
   program shows **weight versus real influence** (weight times the standard deviation of the scores): a criterion
   with a big weight but similar scores for all offers has little say, and the other way round.

## Profiles on the spec example

Malaga, 12-14 July, max EUR 50, at most 1 transfer, changeable required. 47 offers remain after filtering.
Preferred departure times are chosen per profile (a business traveller wants an early bus).

| Profile | Preferred | Winner | Departs | EUR | Duration | Fare | Total | Runner-up | Real influence |
|---|---|---|---|---|---|---|---|---|---|
| budget_traveller | 09:00 | OF-1025 SolRuta | 14 Jul 07:00 | 31.50 | 8h35 | Standard | 76.8 | OF-0723 (73.1) | price 60%, duration 13%, departure 13%, flexibility 14% |
| business_traveller | 08:00 | OF-1032 Camino Express | 14 Jul 08:30 | 40.00 | 6h35 | Standard | 80.7 | OF-0728 (77.8) | price 15%, duration 32%, departure 43%, flexibility 10% |
| flexible_tourist | 10:00 | OF-0730 CostaLink | 13 Jul 10:15 | 41.50 | 7h50 | Flex | 77.4 | OF-0725 (75.8) | price 31%, duration 15%, departure 13%, flexibility 41% |
| environment_focused | 09:00 | OF-1030 VerdeBus | 14 Jul 08:00 | 39.50 | 7h15 | Standard | 82.8 | OF-0426 (78.7) | price 23%, duration 9%, departure 7%, flexibility 7%, emissions 49%, transfers 6% |

The same 47 offers give four different winners from four different companies. Note the business
profile: departure time has weight 30% but 43% real influence, because departure times differ a lot
while prices differ little. Saved outputs: `docs/examples/ranking_<profile>.txt`.

Reproduce one: `python main.py --destination Malaga --from 2026-07-12 --to 2026-07-14 --budget 50 --max-transfers 1 --changeable --preferred-departure 08:00 --profile business_traveller`

## Known limitations (for the evaluation)

- **Rank reversal.** Relative scales depend on which offers are in the list. Example (a test,
  `test_rank_reversal_is_possible_known_limitation`): with four offers the order is 4, 1, 3, 2.
  Remove the last one (2) and offers 1 and 4 swap. A fixed reference scale would avoid this, but then the
  scores would not use the full 0-100 range and weights would mean less (alternative in D15).
- A score only has meaning inside one search. 80 points in one search is not comparable with 80 in another.
- **Night buses.** `departure` is absolute and measures distance from the preferred time. A 22:30 NocheVia bus is
  far from a preferred 09:00 and scores 0, even though it is a good overnight option. The traveller can move the
  preferred time, but the default favours day buses.
- The numbers in `config/scoring.json` (spreads 5 EUR / 60 min, tolerance 6 h, flexibility levels 0/60/40/100,
  cap 2x median) are the designer's choices. The report should show how sensitive the ranking is to them (Phase 9).
- Ratings are one number per company and route, and emissions are estimates, so the optional criteria rest on thin data.
- The weights in the profiles are invented, not measured from real travellers.
- Cost: a criterion looks at the whole list for every offer (O(n^2)). Fine for the filtered list (tens to hundreds),
  slow if all 1497 offers were ranked.

## Evidence

`tests/test_ranking.py` and `tests/test_scoring_config.py` (hand-calculated scores and totals, a different winner with
other weights, all-equal and single-offer cases, minimum spread, outlier cap, departure across midnight and at the
tolerance boundary, all flexibility levels, missing emissions, three levels of tie-break, order independence,
invalid and percentage weights, a new criterion added without touching the ranker, bad scores,
influence, the winners per profile on the real data, and the CLI).
