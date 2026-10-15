# The explanation of the recommendation (Phase 6)

Code: `busbidder/explain.py`. Shown by `python main.py --destination ...` under **RECOMMENDATION**, and
for every profile in `docs/profile_comparison.md`. Decision: D17.

The spec asks for a short explanation of the top offer, generated from the data, that names advantages and
acknowledges a disadvantage, and that does **not** describe the result as objectively best.

## What the text contains

| Part | Rule |
|---|---|
| Headline | offer id, company, departure and arrival, price, total score, and which profile or weights it was ranked for |
| Advantages | weighted criteria where the offer scores **75 or more**, biggest weighted contribution first, at most 3. Plus "a direct route" when the offer has no transfers and other acceptable offers do |
| Drawbacks | criteria where it scores **40 or less**, biggest weighted loss first, at most 2. Plus transfers when the offer has some and others are direct |
| Always a drawback | If nothing is that weak, the **weakest** criterion is named. Only if it scores 100 on every weighted criterion does it say "none found" |
| Comparison | The runner-up, and in weighted points where the top offer is ahead and where it is behind |
| Tie note | Only when the top two have the same score to two decimals: says which tie-break decided (price, duration, departure, id) |
| Caveat | The offer is the highest-ranked **only under** the hard requirements, the weights of the profile (with percentages) and the scoring assumptions (D15). Other weights can give another result |

Only criteria with a weight above 0 are mentioned. Every sentence is built from the offer's own values compared
with the other acceptable offers ("EUR 8.00 above the cheapest (EUR 31.50)", "2h15 longer than the fastest (6h20)",
"departs 07:00, 120 min from the preferred 09:00"). Nothing is written per offer by hand.

## Example (generated)

```
OF-1025 (SolRuta), departs 14 Jul 07:00, arrives 14 Jul 15:35, EUR 31.50: ranked first with 76.8 out of 100 for the 'budget_traveller' profile.
Advantages:
  + price: EUR 31.50, the joint lowest of the 47 acceptable offers
  + a direct route, while 11 of the 47 acceptable offers have transfers
Drawbacks:
  - duration: 8h35, 2h15 longer than the fastest (6h20) (score 21 out of 100)
Compared with the runner-up OF-0723 (73.1): ahead on price (+6.3 points); behind on duration (-2.6 points).
This is the highest-ranked offer only under your hard requirements, the weights of the 'budget_traveller' profile (price 55%, duration 15%, departure 10%, flexibility 20%) and the scoring assumptions (price and duration are scored relative to the 47 acceptable offers). Other weights can give another result, so it is a recommendation under those assumptions, not a proof that nothing is better.
```

## Edge cases

- **No offer left** after filtering: "nothing to recommend" (the filter report says what to relax).
- **One offer left:** says it is the only offer, so there is nothing to compare it with, and makes no advantage claims.
- **Tie:** the tie-break reason is stated.
- **A criterion added later** (the registry, D5) without its own sentence gets a generic one
  ("score 80 out of 100 on 'x'"), so the explanation never fails.
- **Missing emissions figure:** "no emissions figure reported (scored as the worst case)".

## Why these rules (D17)

The explanation has to be useful to a traveller and honest about the model. Advantages and drawbacks come from the
criterion scores, so they always agree with the ranking. Showing a drawback every time, even a mild one, stops the text
from reading as a sales pitch. The runner-up comparison in weighted points shows what decided the order. The caveat
repeats that the result depends on the weights and the scoring assumptions.

## Limitations

- The thresholds (75 and 40) and the limits (3 and 2) are my choices. A criterion that scores 74 is not called an advantage
  even though it is nearly one.
- The comparison is only with the other offers that passed the filter. It says nothing about offers that were removed, even
  if one of them was much better on a criterion (the filter report is where that is shown).
- Scores for price and duration are relative (D15), so "the lowest of the 47 acceptable offers" is only true within this list.
- The sentences are templates in English. They are correct but not very varied.
- The explanation describes the model's result. It does not say whether the traveller *should* choose the offer.

## Evidence

`tests/test_explain.py`: hand-checked text for the worked example, both thresholds on each side of the boundary,
the always-a-drawback rule on all four profiles with real data, the no-drawback case, the weakest-point case, single
offer, empty list, tie note, direct-route and transfer facts, the missing emissions figure, the generic fallback
for a new criterion, every sentence template, and that the words "objectively" and "the best offer" never appear.
