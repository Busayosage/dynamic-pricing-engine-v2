# Phase 1 — Numerical discount recommendation engine (simulated research)

**Status:** built, DRAFT, research only. Every result is a **SIMULATED RESEARCH RECOMMENDATION — NOT VALIDATED FOR
LIVE USE**. Nothing is proposed, approved, published or executed; no price changes.

- Engine: `src/dpe/decision/discount_recommendation.py`. It is pure and deterministic, with no I/O.
- Parameters: `config/assumption_set_v6.json` (DRAFT), validated by `src/dpe/decision/assumptions_v6.py`. The file is
  built by `scripts/build_assumption_set_v6.py`, which refuses to overwrite.
- Dashboard: **Discount Decision Lab** (`app/dashboard/pages/6_Discount_decision_lab.py`). It replaces the Stage 8B
  pricing demonstration page; the Stage 8B engine is reused unchanged for the rule checks.
- Tests: `tests/test_discount_recommendation.py`, plus the Lab tests in `tests/test_dashboard.py`.

## 1. What the engine does

For every line that Markdown review marks **eligible** (store × product × decision week), it compares each permitted
markdown step (5, 10, 15, 20, 25%) with keeping the full price. It returns one of six results:

| Result | Meaning |
|---|---|
| `SIMULATED_RESEARCH_RECOMMENDATION` | One permitted step ranks first under the stated assumptions (not validated) |
| `NO_RECOMMENDATION_KEEP_FULL_PRICE` | No step beats the full price by a material amount |
| `NO_RECOMMENDATION_TOO_UNCERTAIN` | The step with the best expected result could lose too much if customers respond weakly |
| `NO_RECOMMENDATION_NO_PERMITTED_OPTION` | Every step is blocked: promotion, margin floor or maximum markdown |
| `NO_RECOMMENDATION_INSUFFICIENT_EVIDENCE` | Inputs are missing, or the price evidence conflicts |
| `NOT_ASSESSED_NOT_ELIGIBLE` | The line is not eligible for markdown review |

## 2. Inputs and their evidence status

| Input | Source | Status |
|---|---|---|
| Current price P0 | Forecast-contract `reference_price_asof` | ESTIMATED proxy, not a verified shelf price |
| Recorded shelf price that week | Recorded dataset | RECORDED, noisy, apparently synthetic; cross-check only |
| Unit cost C = P0 × (1 − margin) | v5 `gross_margin_pct` | ASSUMED |
| Margin floor, maximum markdown, steps | v5 | ASSUMED |
| Units at risk X | Waste-risk projection of existing stock | SIMULATED stock × FORECAST demand |
| Markdown window W (days) | Investigate-by day → oldest batch's last sellable day | SIMULATED dates |
| Weekly demand p10 / p50 / p90 | Protected 1-week forecast contract | FORECAST |
| Customer-response scenarios, weights, limits | v6 | ASSUMED research scenarios |

No verified cost, shelf price, batch stock or causal markdown response exists. Evidence quality is therefore always
reported as **LOW**.

## 3. Customer-response scenarios (v6, ASSUMED)

| Scenario | % more units per markdown point | Weight | Role |
|---|---|---|---|
| R0 No response | 0 | — | Stress test, reported for every option, never weighted |
| R1 Low | 1.0 | 25% | Close to revenue-neutral for small markdowns; loses money at every step |
| R2 Central | 1.6 | 50% | The **non-causal** historical association, used only as one stated scenario |
| R3 High | 3.0 | 25% | A strong near-expiry response |

The weights are research weights, not probabilities estimated from data. The +1.6% figure is never treated as a
causal elasticity.

## 4. Calculation

For markdown d and response r, with baseline quantile q:

```
S0      = q / 7 × W                          full-price units that would sell in the window anyway
extra   = min(S0 × r × (100·d) / 100, X)     additional units sold, only out of the at-risk stock
sold    = S0 + extra;   expired = X − extra
GP(d)   = sold × P0(1 − d) − C × (S0 + X) − expired × C × disposal%   (stock in scope is already bought)
change  = GP(d) − GP(0)
```

The disposal cost is 0% by default because there is no evidence for it; it is varied in the tests.

## 5. Decision method

The rules are applied in this order, and the first failure decides the result.

1. **Evidence gates.** Each of these on its own returns insufficient evidence:
   - a missing price or margin
   - missing forecast quantiles
   - missing units at risk
   - no batch dates
   - a recorded price that differs from the reference by more than ±25%
2. **Mandatory constraints.** These checks reuse the Stage 8B rules unchanged:
   - an overlapping promotion
   - a step that is not allowed
   - a step above the maximum markdown
   - a step below the margin floor
   - a step with no profit per unit

   A blocked step is never ranked.
3. **Materiality.** The expected change is the weighted average over R1–R3 at p50 demand. It must be at least
   £1 **and** at least 2% of the illustrative cost of the stock at risk.
4. **Downside guard.** Under R1 (low response) with **p90** demand, the most full-price sales are given away. The loss
   in that case may not exceed 25% of the stock at stake.
5. **Ranking.** Higher expected change ranks first; ties go to the smaller downside loss, then to the smaller markdown.
   The top option that passes steps 3–4 is the simulated research recommendation.
6. **Explanation.** Every result comes with a plain-English explanation:
   - why the option ranks above the runner-up
   - its downside and its no-response stress result
   - for a no-recommendation, the exact reason

## 6. Worked example (SC1, policy P2)

Cottage Cheese 300g, store 504, Dairy, order week 40.

| Input | Value |
|---|---|
| P0 | £2.64 |
| C (28% assumed margin) | £1.9008 |
| X | 2,373.6 units |
| W | 2 days |
| Weekly demand p50 | 3,954.7 units |
| Weekly demand p90 | 5,769.7 units |
| Stock at stake | £4,511.74 |

| Markdown | Margin | Rules | No response | Low | Central | High | Low response, p90 demand | Expected | Rank |
|---|---|---|---|---|---|---|---|---|---|
| 5% | 24.2% | passes | −£149.15 | −£7.46 | +£77.56 | +£275.93 | −£10.88 | +£105.90 | 4 |
| 10% | 20.0% | passes | −£298.30 | −£29.83 | +£131.25 | +£507.11 | −£43.52 | +£184.95 | 3 |
| 15% | 15.3% | passes | −£447.45 | −£67.12 | +£161.08 | +£693.54 | −£97.92 | +£237.15 | 2 |
| **20%** | 10.0% | passes | −£596.60 | −£119.32 | +£167.05 | +£835.24 | −£174.08 | **+£262.50** | **1** |
| 25% | 4.0% | **blocked** (below the 8% floor) | — | — | — | — | — | — | — |

**Result:** 20% ranks first. Its expected change is +£262.50, above the £90.23 needed to count as a real benefit. Its
downside is −£174.08, within the £1,127.93 limit.

**What this does not show:**
- In the central case only about 362 of the 2,374 at-risk units are sold. Most of the projected surplus would still
  expire.
- If customers did not respond at all, the markdown would lose £596.60.

## 7. Results across the protected scenarios (computed in memory, nothing saved)

| Scenario / policy | Assessed | Simulated recommendations | No recommendation — evidence |
|---|---|---|---|
| SC1 P2 | 91 | 41 (24 × 20%, 14 × 15%, 3 × 10%) | 50 |
| SC3 P2 | 497 | 225 | 272 |
| SC2 P0 | 0 | — | — |

Every "insufficient evidence" result on real data comes from the price-conflict gate. Recorded weekly prices differ
from the reference proxy by up to ±70%.

"Keep full price", "too uncertain" and "all blocked" results do not occur at the v6 settings on the protected data.
The tests cover each of them, and they appear when the stated assumptions change, for example:
- a low-response weighting gives "keep full price"
- a tighter downside limit gives "too uncertain"
- a promotion week gives "all blocked"

## 8. Limitations

- **Customer response is assumed, not measured.** The ranking is only as good as the stated scenarios.
- **The pricing and stock inputs are not verified.**
  - The price is a proxy and the cost is an assumed margin.
  - Stock, expiry and dates are simulated.
  - Demand is a forecast of recorded sales, not of unconstrained demand.
- **The window model is simplified.**
  - Demand is spread evenly over the days of the week.
  - The markdown runs only to the oldest batch's last day.
  - Stock in later batches is not modelled.
- **No cooldown, legal or commercial pricing rules, store operations or approvers are implemented.**

Live use would need everything listed under "Before a discount can be recommended" on the Markdown review page.
