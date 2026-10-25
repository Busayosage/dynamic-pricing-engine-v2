# Step 5B-2: assumption set and chronological replay simulator (results)

- **Status:** implemented and run. **The assumption file is `DRAFT`**, awaiting your review.
  - Not implemented: inventory recommendation, waste-risk and pricing engines; SQLite; Airtable; GitHub.
  - Unchanged: the forecast contract, models and historical results. The legacy scripts were not run.
- **Date:** 2026-10-22
- **Design:** [STEP_5B2_BUSINESS_ASSUMPTIONS_DESIGN.md](STEP_5B2_BUSINESS_ASSUMPTIONS_DESIGN.md) v2 (approved)
- **Runs** (protected):

  | Run | Content |
  |---|---|
  | `outputs/runs/20261022-225527_replay_worked_example/` | 2 series, SC1–SC3, with sales traces |
  | `outputs/runs/20261022-225809_replay_simulation/` | 720 series, SC1–SC3, sensitivity |

> **Everything in these runs is SYNTHETIC and illustrative.** Stock, deliveries, expiry, unmet units and scenario stresses are simulated under an unapproved (`DRAFT`) assumption set on apparently synthetic data.
> - Recorded sales are **not** verified unconstrained demand.
> - Simulated unmet units are **never observed lost sales**.
> - Coverage positions are **heuristics, not stockout probabilities**.
> - Daily values are `SIMULATED_DAILY_NOT_A_PREDICTION`.

---

## 1. Assumption file

| Item | Value |
|---|---|
| File | `config/assumptions/assumption_set_v1.json` |
| Id / version | `AS-2026-10-22-v1`, version 1 |
| Status | **`DRAFT`** (design approved; file content awaiting your review) |
| Content SHA-256 | `744404c8cc518344af2822b3bddd1ab35a466c63b58bd048a222301c71d809e5` |
| Parameters | 25 records, each with unit, granularity, scope, provenance, evidence, `supported_by_observed_business_data`, rationale, allowed range and sensitivity range |
| Observed | Only `lead_time_days` (supplier data). All ASSUMED and SYNTHETIC values are marked unsupported by business data. |
| Statements | Illustrative values; non-causal discount uplift ("must not be used to promise … sales, revenue or margin"); sales ≠ verified demand; planning weights are not calibrated probabilities |
| Immutability | `content_sha256` covers everything except the approval block. Approving (status, approver, date) leaves it unchanged; editing any value changes it. An `APPROVED` file whose hash differs is rejected, so changes need a new version. |

**Feasibility report** (largest discount step allowed by the margin floor):

| Category | Largest step | Note |
|---|---|---|
| Bakery | 25% | — |
| Beverages | 25% | — |
| Dairy | **20%** | 21.7% by margin |
| Meat | **20%** | 23.9% by margin |

---

## 2. Modules created

| Module | Purpose |
|---|---|
| `src/dpe/decision/assumptions.py` | Load, content hash, validation rules V1–V8, scenario resolution, planning-weight rule, case rounding, watermark |
| `src/dpe/decision/replay.py` | Day-level simulator (lots, deliveries, oldest-first selling, expiry, carry-over), chronology guard, conservation checks |
| `src/dpe/decision/review_queue.py` | One case per decision point; case precedence; holiday flag-only rule |
| `src/dpe/decision/replay_run.py` | Scenarios, KPIs, sensitivity, directional checks, run writer |
| `scripts/run_replay_simulation.py` | `worked-example` / `full` modes. Refuses to write if any conservation or directional check fails. |

---

## 3. How the simulator works (as implemented)

**Order of events:** for each origin *T* in ascending order:
1. **Decide** for all 720 series using only the contract row for origin *T* and the current simulated state.
2. **Then simulate days 1–7 of week *T* + 1.**
   - Demand is read through a guard that refuses any read before the decision. In the full run, all 14,400 reads per scenario came after their decision.

**Decision rule:**
- Weekly planning target = p50 + *w* × (p90 − p50).
- *w* = clip((service target − 50)/40, 0, 1): Bakery 0.875, Meat 0.95, Dairy and Beverages **capped at 1.0** (flag `TARGET_ABOVE_P90_CAPPED`).
- Extrapolation above p90 is disabled.

**Order timing:**
- Orders are placed at the start of Monday of week *T* + 1.
- Arrival is on **day 1 + lead time**, never earlier. Stock is usable only from that day.
- Each order covers 7 days from arrival. Consecutive windows tile without overlap or gap.

**Delivery arrangements** (explicit; `delivery_arrangements.csv`):

| Arrangement | Rule | Series |
|---|---|---|
| `LONG_LIFE_WEEKLY` (remaining life ≥ 7 days) | 1 delivery per order | 360 (Dairy and Beverages) |
| `SHORT_LIFE_RECURRING_DROPS` (remaining life < 7 days) | ⌈7/R⌉ drops, one every R days. This is an assumed standing supplier arrangement, not something a Monday order creates by itself. | 360 (Bakery and Meat) |
| `UNSUPPORTED` (lead time ≥ 7 days) | No order; mandatory review | 0 (none in the base data; tested) |

Drops per order for the short-life series:

| Category | 7 drops (daily, R = 1) | 4 drops | 3 drops | 2 drops |
|---|---|---|---|---|
| Bakery | 60 | 15 | 75 | 30 |
| Meat | — | 45 | 30 | 105 |

**Deliveries:**
- Every delivery has a unique id (`<scenario>-<store>-<product>-O<origin>-D<n>`) and belongs to exactly one order.
- Each records its pre-rounding need, ordered units, delivered units, arrival day and expiry day.
- SC1: 32,542 deliveries (32,092 order drops + 450 initial-schedule drops), all unique.

**Daily stock:**
- Receive that day's deliveries.
- Sell the oldest expiry first. **No sale before arrival or after expiry** is enforced in code and tested.
- Expire at the end of the last sellable day.
- Carry the rest over across days and weeks.

**Units:** integers throughout.
- Conservation on every series-day: opening + received = sold + expired + closing.
- Unmet = illustrative demand − sold.

**Initial state** (synthetic, from data ≤ origin 32):
- Long-life items open with `opening_cover_weeks` × the 4-week average.
- Short-life items open empty, with an initial drop schedule up to the first arrival.

**Simulation window:**
- Decisions at origins **32–51** (the first origin with bounds for every series), simulating weeks 33–52.
- Origins 25–31 have no bounds, so they enter only the review queue as `MANDATORY_REVIEW`. No order is invented for them.

---

## 4. Outputs and integrity

| Check | SC1 | SC2 | SC3 |
|---|---|---|---|
| Store-product-weeks simulated | 14,400 | 14,400 | 14,400 |
| Simulated store-product-days | 100,800 | 100,800 | 100,800 |
| Daily balance holds | ✅ | ✅ | ✅ |
| Weekly balance holds | ✅ | ✅ | ✅ |
| Closing = next opening | ✅ | ✅ | ✅ |
| No negative values | ✅ | ✅ | ✅ |
| Unmet = demand − sold | ✅ | ✅ | ✅ |
| Demand reads after the decision | 14,400 / 14,400 | 14,400 / 14,400 | 14,400 / 14,400 |
| Duplicate deliveries / duplicate cases | 0 / 0 | 0 / 0 | 0 / 0 |

**Run time:** 19.2 s for all three full scenarios (S17 budget: under 10 minutes).

**Files per scenario:**
- `decisions.csv`, `deliveries.csv`
- `daily.csv` (labelled `SIMULATED_DAILY_NOT_A_PREDICTION`)
- `weekly.csv`, `review_cases.csv`, `scenario_summary.json`

**Run-level files:** `scenario_comparison.csv`, `delivery_arrangements.csv`, `sensitivity_SC1.csv`, and `manifest.json` (assumption hash, statements, directional checks, code hashes).

---

## 5. Scenario comparison (all SYNTHETIC; units summed over weeks 33–52)

| KPI | SC1 Normal | SC2 Demand/supply pressure | SC3 Excess/expiry pressure |
|---|---|---|---|
| Ordered units | 25,466,832 | 30,073,668 | 23,179,602 |
| Received units | 25,447,746 | 22,474,035 (75% fill) | 25,095,070 (+20% short-life) |
| Illustrative demand | 23,480,390 | 27,002,249 (×1.15) | 19,958,373 (×0.85) |
| Sold | 22,645,520 | 21,855,095 | 19,818,920 |
| **Illustrative unmet** | **834,870** | **5,147,154** | 139,453 |
| **Expired** | 2,763,370 | 415,087 | **5,713,748** |
| Expired share of received | 10.9% | 1.8% | 22.8% |
| Illustrative sell-through | 96.4% | 80.9% | 99.3% |
| Series-weeks with any illustrative unmet | 3,064 | 9,920 | 647 |
| Decisions with HIGH waste band on existing stock | 2,881 | 316 | 5,216 |

**Directions are as designed:**
- SC2 raises illustrative unmet units (×6.2) and lowers expiry.
- SC3 raises expiry (×2.1).

**SC1 by category:**

| Category | Illustrative demand | Sold | Unmet | Expired |
|---|---|---|---|---|
| Bakery | 5,645,145 | 5,253,936 | 391,209 | 1,368,806 |
| Beverages | 6,046,180 | 5,960,506 | 85,674 | 0 |
| Dairy | 9,161,360 | 8,968,408 | 192,952 | 759,436 |
| Meat | 2,627,705 | 2,462,670 | 165,035 | 635,128 |

These are consequences of the assumptions, not predictions of real stockouts or waste.

---

## 6. Review cases (19,440 decision points per scenario; one case per point)

| Case type | SC1 | SC2 | SC3 |
|---|---|---|---|
| `MANDATORY_REVIEW` (bounds unavailable) | 5,040 | 5,040 | 5,040 |
| `MANDATORY_ESCALATION` (Christmas) | 2,880 | 2,880 | 2,880 |
| `RISK_ESCALATION` (material trigger) | 4,684 | 11,064 | 5,660 |
| **Total cases** | **12,604** | **18,984** | **13,580** |
| Holiday-flagged points with no case | 1,580 | 0 | 1,334 |
| Duplicate cases | 0 | 0 | 0 |

- **SC1 risk-trigger reasons** (a case can carry several):

  | Reason | Cases |
  |---|---|
  | `LIFE_LEAD_TIME_TIGHT` | 2,880 |
  | `WASTE_HIGH_EXISTING_STOCK` | 2,379 |
  | `TREND_DIVERGENCE` | 565 |

- **SC2:** every decision point carries `FILL_RATE_SHORTFALL_LAST_WEEK`, so no holiday-only points remain.
- **Christmas plans are simulated as proposed.** The 2,880 Christmas decision points have a computed plan, which the simulation executes. Their mandatory escalation is a review requirement, not a block on the simulated orders.

---

## 7. Sensitivity (SC1, one at a time) and directional checks

| Setting | Ordered | Illustrative unmet | Expired | Expired share | Cases | Decisions with a changed order |
|---|---|---|---|---|---|---|
| **Base** | 25.47 M | 834,870 | 2,763,370 | 10.9% | 12,604 | — |
| Service target 50 (all) | 20.42 M | 3,356,389 | 653,334 | 3.2% | 11,429 | 96.8% |
| Service target 70 (all) | 23.32 M | 1,629,478 | 1,613,145 | 6.9% | 12,006 | 90.4% |
| Service target 90 (all) | 25.77 M | 766,365 | 2,981,779 | 11.6% | 12,694 | 46.6% |
| Case size ×0.5 | 25.41 M | 848,547 | 2,724,896 | 10.7% | 12,594 | 58.8% |
| Case size ×2 | 25.58 M | 808,637 | 2,841,507 | 11.1% | 12,638 | 59.0% |
| MOQ 4 cases | 25.47 M | 834,798 | 2,763,370 | 10.9% | 12,604 | 0.04% |
| Fill rate 60% | 30.42 M | 5,059,204 | 223,163 | 1.2% | 18,920 | 45.5% |
| Demand ×0.85 | 23.89 M | 276,201 | 4,040,947 | 16.9% | 12,932 | 48.1% |
| Demand ×1.15 | 26.84 M | 1,932,611 | 1,819,119 | 6.8% | 12,282 | 45.5% |
| Transit age 0 days | 24.76 M | 960,559 | 2,177,020 | 8.8% | 11,186 | 51.8% |
| Transit age 2 days | 25.63 M | 873,113 | 2,957,630 | 11.6% | 13,386 | 42.9% |
| Opening cover ×3 | 24.25 M | 814,152 | 2,791,541 | 11.5% | 12,649 | 13.2% |
| Weekend-heavy daily profile | 25.55 M | 807,755 | 2,837,758 | 11.1% | 12,402 | 16.2% |
| `LIFE_LEAD_TIME_TIGHT` not a trigger | 25.47 M | 834,870 | 2,763,370 | 10.9% | **10,757** | 0% |

- **The service target is the dominant assumption:** it trades illustrative unmet units against expiry.
- **MOQ hardly matters** at these volumes.

**Directional checks** (all pass; the run refuses to write otherwise):
- higher planning weight → orders not lower
- larger case size → order not lower **for the same need**
- lower fill rate → unmet not lower
- lower demand → expired not lower
- higher minimum margin → maximum discount not higher

---

## 8. Tests

**Two new test files:**
- `tests/test_assumptions.py`: AF1–AF6, 17 tests.
- `tests/test_replay_simulator.py`: S1–S17 and the requested checks, 34 tests.

| Requested check | Test(s) |
|---|---|
| No future-data leakage + **mutation test** (all future sales and forecasts altered after cut-offs 17, 22, 26; earlier decisions and days unchanged) | `test_altering_future_sales_does_not_change_earlier_decisions`, `test_truncated_history_gives_identical_earlier_decisions`, `test_demand_is_read_only_after_the_decision` |
| Deterministic replay | `test_replay_is_deterministic` |
| Daily and weekly conservation; opening and closing stock | `test_daily_and_weekly_conservation` (SC1–SC3), `test_opening_and_closing_stock` |
| Supplier lead-time timing | `test_orders_arrive_only_on_day_one_plus_lead_time` (SC1, SC2 with +1 day) |
| Shelf-life expiry; no sale before delivery or after expiry | `test_shelf_life_and_short_life_drop_schedule`, `test_short_life_lots_carry_over_the_week_boundary`, `test_no_sale_before_delivery_or_after_expiry`, `test_expired_units_leave_stock_at_end_of_last_sellable_day` |
| No duplicated deliveries; explicit drop counts | `test_each_delivery_is_unique_and_received_exactly_once`, `test_monday_order_drop_count_is_explicit` |
| Scenario separation | `test_scenarios_are_separate_and_reproducible`, `test_scenario_directions` |
| Provenance labels | `test_provenance_labels_and_watermarks` |
| Missing uncertainty review; unsupported arrangements | `test_missing_uncertainty_requires_review_and_no_automatic_order`, `test_unsupported_delivery_arrangement_requires_review` |
| Christmas escalation; no duplicate cases; holiday flag-only | `test_real_christmas_escalation_and_case_counts`, `test_one_case_per_decision_point_and_holiday_only_creates_no_case` |
| No unsupported probability or daily claims | `test_no_probability_or_daily_prediction_claims` |
| Sensitivity, safety limits, rounding, worked example, output safety, protected runs | the remaining tests |

**Mutation check** (outside the repository): decisions were made to peek at the target week's actual sales. The future-sales mutation test **failed at all three cut-offs**, so the leak was caught.

**Full suite:** **320 passed, 0 failed** (269 earlier + 51 new). All 247 recorded checksums match, and all 330 files that existed before this checkpoint are unchanged.

---

## 9. Unsupported assumptions and operational contradictions found

1. **`LIFE_LEAD_TIME_TIGHT` already applies in normal trading.**
   - Design v2 §5 expected it "can occur in SC2". With remaining life = shelf life − 1 day, lead time ≥ remaining life holds for **12 products (180 series)** in SC1: 7 Bakery and 5 Meat.
   - As an approved material trigger, it creates **2,880 risk cases** in SC1, of which **1,847 have no other reason**.
   - It is implemented as approved, behind the switch `life_lead_time_tight_is_material_trigger`. Turning it off reduces SC1 cases from 12,604 to 10,757 and changes no order. **Decision needed.**
2. **The coverage-position trigger never fires.**
   - Positions are measured on *planned* supply (usable stock + the new order), and the order tops supply up to the planning target, which is always ≥ p50.
   - So `P10_TO_P50` and `BELOW_P10` never occur, even in SC2. The SC2 shortages come from fill-rate shortfalls the decision cannot foresee.
   - A meaningful shortage trigger would measure the position **before** the new order, or on **expected delivered** supply. That is a design change; **decision needed.**
3. **Case-size direction needs a feedback caveat.**
   - Across the whole system, larger cases can lower the *first* order: the synthetic initial schedule is also rounded up, so more stock is carried in. This affected 19 of 720 series, by 3–6 units.
   - The directional check now tests the rounding step for the same pre-rounding need, as design §9 intends. The whole-system effect appears in the sensitivity table.
4. **Recurring short-life drops are an assumed supplier arrangement.** For R = 1 that means daily deliveries including weekends. No supplier data confirms such arrangements.
5. **Christmas plans are executed in simulation** while being mandatory escalations. The simulated outcome therefore assumes the escalated plan would be approved as proposed.
6. **Origins 25–31 are not simulated** (no bounds). The first simulated week (33) depends on a synthetic opening state.
7. **Assumptions that dominate the results:**
   - all margins, costs, case sizes, MOQ, service targets, opening stock and stress settings are illustrative
   - recorded sales are treated as demand
   - the daily split is uniform

---

## 10. Superseded run

`outputs/runs/20261022-225236_replay_worked_example/` was the first worked-example run. Its numbers are identical, but it was written before deliveries recorded their pre-rounding need. It is kept and not used.
