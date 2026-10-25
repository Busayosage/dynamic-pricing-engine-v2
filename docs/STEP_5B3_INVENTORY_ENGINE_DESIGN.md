# Step 5B-3 inventory recommendation engine: design (for review)

**Date:** 23 Oct 2026
**Status:** DESIGN ONLY. Nothing in this document is implemented.

**Inputs it builds on:**
- Forecast contract v1.0: `outputs/runs/20261022-081926_forecast_contract`
- Replay simulator v1.1, accepted full replay: `outputs/runs/20261023-081809_replay_simulation_v1_1`
- Assumption set AS-2026-10-22-v1, which is **DRAFT**

All parameter values quoted here come from that draft file. They are illustrative ASSUMED or SYNTHETIC values, **not
validated business policy**. All worked-example numbers are SYNTHETIC replay values: recorded sales are used as
illustrative demand, and the opening stock is synthetic.

Out of scope here: pricing, the waste-risk engine, any database, Airtable and GitHub.

---

## 1. Plain-English summary

Once a week, for each store and product, the engine will propose how much to order. It will show its working and say
whether a person must look at it. It never places an order: every proposal waits for an explicit human approval
event.

What changes compared with the accepted replay sizing (v1.1):

1. **Stock is counted day by day, and only while it is still sellable.**
   - v1.1 subtracted all stock still usable on the day the delivery arrives, even stock that expires the next day.
   - The new engine walks through each day of the week the order must cover. A batch helps only on days between its
     arrival and its expiry.
   - This removes the cause of the 29 (SC1) and 111 (SC3) post-order shortfalls found at the correction checkpoint.
2. **It separates four situations:**
   - a routine order
   - a shortage that will happen before the next delivery can arrive, which no routine order can fix
   - a shortage that would remain even after the proposed order
   - a supplier arrangement that is unsupported or unproven

   Each has its own recommendation category and review rule.
3. **Expected supplier fill rate is a planning assumption, kept apart from what suppliers actually deliver.** By
   default the engine still plans for full delivery, as now. It reports how exposed the plan is if the supplier
   delivers less. Adjusting order sizes for expected short deliveries is a decision for you (D3).
4. **Uncertainty safeguards are unchanged:**
   - the p50-to-p90 planning heuristic, capped at p90
   - mandatory review where forecast bounds are missing
   - mandatory escalation at Christmas
   - no approval without an approval event

The engine's value will be judged only inside the replay simulator. It will be compared with a simple
historical-sales rule and with the current forecast-informed rule, on the same synthetic scenarios. The results will
be described as simulated differences, never as real-world waste reduction or measured lost sales.

---

## 2. Inputs and the information boundary

The engine decides on **decision day D0**: day 1 (Monday) of target week T + 1, after week T's sales are final.

### May be used at D0

| Input | Notes |
|---|---|
| Forecast contract row for origin T, decision-time fields only | p10/p50/p90, point forecast, `uncertainty_status`, risk flags, H4 point forecast (trend divergence check only) |
| Stock on hand at the start of D0, by batch | quantity, arrival day, expiry day |
| Deliveries already scheduled (ordered, not yet received) | **ordered quantity** and planned arrival day; never the quantity that will actually arrive |
| Receipts up to D0 − 1 | realised quantities of past deliveries; for an as-of fill-rate estimate (section 5) |
| Supplier lead time, shelf life, delivery arrangement | lead time is observed; transit age and arrangements are ASSUMED |
| Resolved assumption values for the scenario | case size, MOQ, service target, planning fill rate, daily profile, thresholds |

### Never used at D0

- sales or illustrative demand for week T + 1 or later
- realised quantities of deliveries not yet received
- replay-only contract fields
- contract rows for later origins
- recorded `Wastage_Units` (as in Step 4, never an input)

The replay's `DemandAccess` guard and the leakage tests (section 10) enforce this.

---

## 3. Time-phased calculation logic

### 3.1 Definitions

| Symbol | Meaning |
|---|---|
| `LT` | Effective lead time in days: observed + `lead_time_adjustment_days` |
| `R` | Remaining sellable life on arrival, in days: shelf life − `transit_age_days` |
| `a` | First arrival day of the new order = D0 + LT |
| Coverage window | Days `a … a+6`. Consecutive windows tile without overlap, as in v1.1. |
| Pre-arrival period | Days `D0 … a−1`, which the new order cannot reach |
| Drop | One delivery inside the window. `LONG_LIFE_WEEKLY` (R ≥ 7) has one drop on day `a`. `SHORT_LIFE_RECURRING_DROPS` (R < 7) has ⌈7/R⌉ drops every R days from `a`. Drop *i* arrives on `d_i`, covers its `c_i` days and expires at the end of `d_i + R − 1`. |
| Batch (lot) | Units with one arrival day and one expiry day. A lot is sellable on day *x* only if arrival ≤ *x* ≤ expiry. |
| `S_week` | Weekly planning target = p50 + w·(p90 − p50), with w = clip((target − 50)/40, 0, 1), capped at p90 |
| `r_x` | Planning use on day *x* = `S_week × profile[dow(x)]` (profile is uniform in the draft: ÷7). This is a **coverage convention**, not a daily demand forecast. |
| `m_x` | Expected depletion on day *x* before the window = p50 × profile[dow(x)] (decision D2) |
| `f_plan` | Planning fill rate: expected share of ordered units that arrive. Kept apart from the simulator's realised `delivery_fill_rate_pct`. |

### 3.2 Steps (per series, per decision)

1. **Gate.**
   - If bounds are unavailable, the arrangement is `UNSUPPORTED`, or R < 1: no quantity is proposed. The category is
     `NO_RECOMMENDATION_REVIEW_REQUIRED`, and the case is a mandatory review.
   - Stop here.
2. **Project the stock position to day `a`.** Starting from the lots on hand at D0, walk the days D0 … a−1:
   - Add each scheduled delivery on its planned day, at `ordered × f_plan`.
   - Deplete at `m_x`, oldest expiry first.
   - Remove a lot after its expiry day.
   - The units left unsold at expiry are the **expected existing-stock expiry**.
3. **Pre-delivery coverage**, unchanged from v1.1. Repeat the walk at the p90, p50 and p10 rates to get the position
   (`COVERS_P90_RATE` … `BELOW_P10_RATE`) and the heuristic gap in units at each rate.
4. **Size each drop in date order**, *i* = 1 … n. For each covered day *x* = d_i … d_i + c_i − 1:
   - Serve `r_x` from the projected lots sellable on *x*: existing stock, committed deliveries and earlier drops,
     oldest expiry first.
   - Any part not served is that day's shortfall.

   Then:
   - `net_need_i` = sum of those daily shortfalls. Stock that expires before day *x* never counts for day *x*.
   - `gross_need_i` = `net_need_i / f_plan`.
   - `order_i` = 0 if `gross_need_i` ≤ 0. Otherwise it is ⌈`gross_need_i` / case⌉ × case, and at least
     MOQ × case.
   - Add drop *i* (`order_i × f_plan` units, expiring at d_i + R − 1) to the projection before sizing drop *i* + 1.
5. **Post-order coverage.** Re-walk the window with all drops at their scheduled arrival days and get the position.
   Any shortfall left at the planning rate is the **residual shortfall** (section 4).
6. **Exposure figures.** Each figure is a heuristic, labelled as such, and none is a probability:
   - **Planned expiry exposure of the new order:** units expected unsold at their expiry if demand runs at p50.
   - **Rounding and MOQ overage:** `order_i − gross_need_i`.
   - **Fill-rate exposure:** the extra window shortfall if the supplier delivers only `f_low` (decision D3), all else
     equal.
7. **Category and review** (section 4). Status is `HYPOTHETICAL_UNAPPROVED` in replay and `PENDING_APPROVAL` live.

### 3.3 Rules that must always hold

1. No stock is counted on a day after its expiry day, and no delivery before its arrival day.
2. A scheduled delivery is planned at its ordered quantity × `f_plan`, never its realised quantity.
3. Every proposed drop is a whole number of cases. A drop is either 0 or at least MOQ × case. Units are integers.
4. Drops arrive only on `a + k·R` inside the window, never before day `a`.
5. The target never exceeds p90 (no extrapolation above a 90% service target).
6. The engine never writes an approval, execution or authorisation status.

### 3.4 What stays the same as v1.1

The following are unchanged:
- delivery arrangements and drop days
- planning weight and the p90 cap
- case and MOQ rounding
- pre- and post-order coverage positions
- review precedence
- Christmas escalation
- approval labels

When the stock on hand would all stay sellable through the window, the new sizing equals v1.1. Example B shows this.

---

## 4. Shortage response, recommendation categories and review

### 4.1 Categories (one primary category per decision point)

| Category | When | Proposed quantity | Review |
|---|---|---|---|
| `NO_RECOMMENDATION_REVIEW_REQUIRED` | Bounds unavailable; arrangement `UNSUPPORTED`; R < 1 | none | MANDATORY_REVIEW |
| `RESIDUAL_SHORTFALL_AFTER_ORDER` | The post-order walk still shows a shortfall at the planning rate. With time-phased sizing, this happens only for structural reasons: drop spacing or expiry makes some days unreachable, or a capacity limit applies (if approved, D8). | sized as far as possible | RISK_ESCALATION (reason names the cause) |
| `PRE_DELIVERY_SHORTAGE` | The pre-delivery position is `COVERS_P10_RATE_ONLY` or `BELOW_P10_RATE` | routine window order, sized normally | RISK_ESCALATION. The case shows the gap range at the p10/p50/p90 rates. |
| `NO_ORDER_STOCK_SUFFICIENT` | Every drop's net need ≤ 0 | 0 (MOQ is not forced) | none, unless another trigger applies |
| `ROUTINE_REPLENISHMENT` | None of the above | sized order | none, unless another trigger applies |

Precedence among the category rows:
`NO_RECOMMENDATION_REVIEW_REQUIRED` > `RESIDUAL_SHORTFALL_AFTER_ORDER` > `PRE_DELIVERY_SHORTAGE` > the rest.

The v1.1 review rules still apply on top of the category:
- A Christmas target week is **MANDATORY_ESCALATION**, whatever the category.
- The other material triggers still raise a RISK_ESCALATION:
  - high existing-stock expiry exposure
  - last week's fill-rate shortfall
  - trend divergence
- Warnings never create a case on their own:
  - `LIFE_LEAD_TIME_TIGHT`
  - `TARGET_ABOVE_P90_CAPPED`
  - `HOLIDAY_TARGET_WEEK`
  - `SHORT_LIFE_ARRANGEMENT_ASSUMED` (new; decision D6)

  When a case exists, they are listed in it as evidence.

### 4.2 Shortage before the next delivery: no remedies are assumed

A routine order cannot reach the store before day `a`. The case reports the following and stops there:
- the gap range, for example "about 405 to 1,752 units at the p10 to p90 rates; heuristic"
- the days affected
- the stock on hand

Remedies such as an expedited delivery, a store transfer or a substitute are listed only as **"options requiring
evidence"**. The engine never assumes they are available, never sizes them and never counts them in coverage.

Supporting a remedy later would need, for each option:
- documented availability (supplier, lead time, cost)
- a new assumption parameter in a new assumption-set version
- your approval

### 4.3 Uncertain or unsupported supplier arrangements

| Arrangement | Handling |
|---|---|
| `UNSUPPORTED` (lead time ≥ 7 days, or R < 1) | No quantity proposed. Mandatory review. |
| `SHORT_LIFE_RECURRING_DROPS` (all 360 Bakery and Meat series) | Drops on up to 7 days a week, weekends included, rest on an ASSUMED standing arrangement with no evidence. Each proposal carries the warning `SHORT_LIFE_ARRANGEMENT_ASSUMED`. Whether this alone requires review is decision D6. |
| `LIFE_LEAD_TIME_TIGHT` (lead time ≥ R) | Warning only, as accepted at the correction checkpoint. |
| Fill-rate history | Last week's shortfall stays a material trigger. An as-of fill estimate below `f_low` adds the warning `LOW_FILL_HISTORY` (D3). |

`Supply_Capacity` in `supplier_info.csv` is **not used**. Its unit and period are undefined. For 8 of the 10 suppliers,
it is below the median recorded weekly sales of their products. Supplier 5, for example, has a capacity of 11,306
against median weekly sales of 105,966. So it cannot be a weekly unit limit. Using it needs a definition (D8).

### 4.4 Approval safeguards

These are carried over and extended:
1. Every recommendation is `HYPOTHETICAL_UNAPPROVED` in replay and `PENDING_APPROVAL` live, with an empty
   `approval_event_id`.
2. An approval event is a separate record. It holds:
   - recommendation id
   - approver
   - timestamp
   - decision: `APPROVE`, `REJECT` or `MODIFY`, with the modified quantity
   - reason
3. Only an approval event can move the status, to `APPROVED`, `REJECTED` or `MODIFIED_APPROVED`. The engine never
   sets "executed". Execution happens outside this system.
4. Approval events do not exist in a replay. The run script refuses to write if one appears.
5. Christmas escalations cannot be approved by default, bulk or auto rules (D9).
6. The recommendation keeps everything it was based on:
   - the inputs it used (contract row id, lots, scheduled deliveries, assumption content hash)
   - its calculation steps
   - its warnings

   A reviewer can reproduce it exactly.

---

## 5. Supplier fill rate

### 5.1 Two separate quantities

| | Planning fill rate `f_plan` | Realised delivered quantity |
|---|---|---|
| What it is | An ASSUMED expectation used to size orders and project scheduled deliveries | What the supplier actually delivered |
| Where it comes from | A new assumption parameter `planning_fill_rate_pct`, set per scenario. Optionally, an as-of estimate from receipts before D0. | The simulator's `delivery_fill_rate_pct` and over-delivery parameters in replay; supplier receipts live |
| When it is known | At D0 | Only on the arrival day |

The engine reads realised quantities only for deliveries already received before D0. The test in section 10 (T2b)
proves that changing the realised fill rate does not change the first decision.

### 5.2 Options (decision D3)

- **F1 — plan for 100% (current behaviour).** Order sizes are unchanged. The case shows the fill-rate exposure at
  `f_low`.
- **F2 — plan for an assumed rate, `f_plan` < 100%.** Orders are grossed up by 1/f_plan.
- **F3 — plan for the as-of observed rate.** This is the receipts before D0, for example over the last 4 weeks, with
  a floor and a cap.

  In replay those receipts are themselves simulated from the scenario's parameter. F3 would only rediscover that
  parameter, so it is meaningful only with real receipt data. In replay it is reported as a diagnostic.

**Recommendation:** F1 as the default, with exposure reporting. F2 is evaluated as a sensitivity: the planning rate
equals the realised rate in SC2 (75%), and there is a mismatch case (plan 100%, realise 75%). F3 is reserved for real
receipt data.

### 5.3 Risks of assuming 100% fulfilment (evidence from the accepted replay)

These figures are from synthetic replay only, and are not real-world measurements.

1. **SC2 (75% realised fill):** 51.5% of pre-arrival windows with **no** pre-order shortage flag still had simulated
   unmet units. Plans counted committed deliveries in full, and they arrived short.
2. **SC1 sensitivity:** lowering the realised fill rate to 60% raised illustrative unmet units from 834,870 to
   5,059,204. It raised pre-order shortages from 957 to 8,594.
3. `FILL_RATE_SHORTFALL_LAST_WEEK` reacts only after a short delivery has already happened.
4. **Grossing up has a cost too.** If the supplier then delivers in full, the extra units add expiry exposure. This is
   worst for short-life items: Example D shows 168 extra units a week for one Bakery line. MOQ overage adds to it.

---

## 6. Uncertainty and safety

These are unchanged from the approved Step 5B-2 design and the correction checkpoint:
- **Planning weight:** w = clip((target − 50)/40, 0, 1), with the target p50 + w(p90 − p50). Above a 90% target, it
  is capped at p90 and flagged `TARGET_ABOVE_P90_CAPPED`. There is no extrapolation.
- **Draft service targets:** Bakery 85, Meat 88, Dairy 92, Beverages 95. So Dairy and Beverages always sit at the p90
  cap.
- **Missing bounds:** no quantity is proposed, and the case is a mandatory review. In the accepted replay this is
  5,040 decision points.
- **Christmas:** target weeks 51 and 52 are a mandatory escalation, with `escalation_required = true`.
- **Coverage positions** are heuristics against forecast quantiles. They are never stockout probabilities. The daily
  rates are coverage conventions, not daily forecasts. The banned-wording test is kept.

---

## 7. Business value: how the policies would be compared

### 7.1 Three ordering policies, run in the same replay simulator

| Policy | Weekly quantity | Netting of current stock |
|---|---|---|
| **P0 Historical-sales baseline** | As-of 4-week average of recorded weekly sales | All stock on hand, ignoring expiry (a typical simple rule) |
| **P1 Forecast-informed** (accepted v1.1 sizing) | Planning target S_week | All stock usable on the arrival day, the v1.1 rule |
| **P2 Shortage-aware, time-phased** (this design) | Planning target S_week | Day by day, expiry-aware (section 3), with shortage categories |

All three policies share the same:
- delivery arrangement and drop days
- case and MOQ rounding
- review gates (no quantity where bounds are missing, Christmas escalation)
- scenarios SC1–SC3
- assumption set
- demand path

Only the sizing rule differs. Each policy runs in its own replay, so its own decisions shape its stock.

### 7.2 Metrics, per scenario and per category

All are simulated and SYNTHETIC.

| Group | Metric |
|---|---|
| Availability (illustrative) | unmet units and their share of illustrative demand; series-weeks with any unmet units; unmet units falling in pre-arrival periods versus inside coverage windows |
| Waste (simulated) | expired units; expired share of received units; expired units traced to existing stock versus new orders |
| Stock | average closing stock in days of p50 cover; final-week closing stock |
| Ordering | ordered units; number of deliveries; rounding and MOQ overage units |
| Detection | pre-delivery shortage count; residual shortfall count; flagged windows that did or did not show simulated unmet units (evidence, not calibration) |
| Workload | review cases by type; warnings without a case |
| Cost proxy (optional, D10) | expired units × assumed purchase cost; holding cost. Labelled "ASSUMED margins, illustrative". |

For each pair of policies, P2 − P1 and P1 − P0, the report gives paired differences by series-week. A series ×
week-block bootstrap describes how much they vary within this simulation. It is not real-world evidence.

### 7.3 Wording rules for results

- **Allowed:** "in the synthetic replay, P2 had X fewer simulated expired units than P1 under SC1".
- **Not allowed:**
  - "reduces waste by X%"
  - "prevents lost sales"
  - "saves £"
  - any stockout probability

Recorded sales are censored by past availability, so simulated unmet units are **never** observed lost sales. Opening
stock is synthetic.

The banned-wording list is extended to the comparison outputs.

### 7.4 Pre-registered comparison thresholds (proposed, decision D11)

The thresholds must be fixed **before** the comparison is run. Proposed rule: P2 becomes the default replay sizing rule
only if, in SC1, all of the following hold:
- Residual shortfalls are 0, except for documented structural causes.
- Simulated expired units are no more than 1.05 × P1.
- Illustrative unmet units are no more than P1.
- The direction is consistent in SC2 and SC3.

Otherwise P1 stays, and the reasons are reported.

---

## 8. Worked examples

All examples come from the accepted v1.1 replay logic. The simulator state was captured at the decision. The proposed
rule was applied by a scratch prototype outside `src/`, which is not the engine. Days run Monday to Sunday. Units are
SYNTHETIC.

### Example A — stock that expires inside the window

**Inputs:** SC1, store 500, product 1034 (Dairy), origin week 33.

| Item | Value |
|---|---|
| Shelf life / remaining life R | 10 days / 9 days |
| Lead time | 2 days |
| Arrangement | weekly (one drop) |
| Forecast p10 / p50 / p90 | 2,530.9 / 4,023.9 / 5,835.9 |
| Service target / planning weight | 92% / w = 1 |
| Weekly planning target | capped at p90: 5,835.9, so 833.7 a day |

**Stock and timing:**
- On hand at the decision (Monday, week 34): one batch of **4,214 units, expiring at the end of Thursday**.
- The new order arrives **Wednesday**. The coverage window is Wednesday to the following Tuesday.

**What happens to the existing batch:**
- At the p50 rate (574.8 a day), 3,064.3 units are left on Wednesday.
- Only Wednesday and Thursday can use them: 2 × 833.7 = 1,667.4.
- The other **1,396.9 units are expected to expire on Thursday**, whatever is ordered.

| | v1.1 (accepted) | Proposed time-phased |
|---|---|---|
| Existing stock credited | 3,064.3 (all usable on arrival) | 1,667.4 (Wednesday and Thursday only) |
| Net need | 5,835.9 − 3,064.3 = 2,771.6 | 5 days × 833.7 = 4,168.5 (Friday to Tuesday) |
| Proposed order (12-unit cases) | **2,772** | **4,176** (348 cases) |
| Post-order position | `COVERS_P10_RATE_ONLY`: `POST_ORDER_SHORTFALL` | covers the planning (p90) rate: no residual shortfall |
| Existing-stock expiry flag | `WASTE_HIGH_EXISTING_STOCK` | same flag; expected expiry 1,396.9 |
| Category | — | `ROUTINE_REPLENISHMENT`, plus the existing-stock expiry trigger, so RISK_ESCALATION |

The net need is the same whether the existing batch is depleted at p50 or at the planning rate before Wednesday.
The batch expires on Thursday either way. Only the expected expiry changes: 1,396.9 at p50 or 879.2 at the planning
rate (decision D2). A larger order does not cause the existing batch's expiry. That expiry is reported for the later
waste-risk engine, not solved here.

### Example B — short-life daily drops, where the new rule equals v1.1

**Inputs:** SC1, store 505, product 1001 (White Sandwich Loaf, Bakery), origin week 44.

| Item | Value |
|---|---|
| Shelf life / remaining life R | 2 days / 1 day |
| Lead time | 3 days |
| Arrangement | recurring drops: one a day |
| Forecast p50 / p90 | 997.3 / 1,476.9 |
| Service target / planning weight | 85% / w = 0.875 |
| Weekly planning target | 1,416.9, so 202.4 a day |

**Stock and timing:**
- On hand at the decision: nothing.
- Already scheduled from last week's order: 204 units on each of Monday, Tuesday and Wednesday.
- Pre-delivery position: `COVERS_P50_RATE` (204 a day against 142.5 at p50 and 211.0 at p90).
- The new drops arrive Thursday to the following Wednesday.

**Sizing:**
- Each drop needs 202.4, which rounds to 17 cases of 12 = **204**.
- 7 drops make **1,428**: identical to v1.1, because there was no existing stock to over-credit.
- About 1.6 units a day are rounding overage.
- The MOQ of 2 cases (24 units) per drop does not bind here.
- Category: `ROUTINE_REPLENISHMENT`, with the warnings `LIFE_LEAD_TIME_TIGHT` and `SHORT_LIFE_ARRANGEMENT_ASSUMED`.

### Example C — shortage before the next delivery

**Inputs:** SC2, store 500, product 1024 (Dairy), origin week 32.

| Item | Value |
|---|---|
| Remaining life R | 15 days |
| Lead time | 3 days, after the SC2 +1 day adjustment |
| Forecast p10 / p50 / p90 | 2,432.2 / 3,837.7 / 5,576.8 |
| Weekly planning target | capped at p90: 5,576.8, so 796.7 a day |

**Stock and timing:**
- On hand: 638 units.
- The new order arrives **Thursday**.
- Monday to Wednesday are out of the order's reach.

**Pre-delivery gap.** These are heuristics, not forecasts.

| Rate | Gap, Monday to Wednesday |
|---|---|
| p10 (347.5 a day) | 404.4 units |
| p50 (548.2 a day) | 1,006.7 units |
| planning / p90 (796.7 a day) | 1,752.1 units |

**Recommendation:**
- Category `PRE_DELIVERY_SHORTAGE`, so RISK_ESCALATION.
- The routine window order of **5,580** (465 cases) covers Thursday onwards at the planning rate.
- The case lists "expedited delivery / transfer — options requiring evidence". It sizes neither.

### Example D — supplier fill rate

The same decisions, with different planning fill rates. "Delivered at realised fill" is what the simulator would
deliver.

| | f_plan 100% (F1, default) | f_plan 90% (F2) | f_plan 75% (F2) |
|---|---|---|---|
| Example C order | 5,580 | 6,204 | 7,440 |
| Example C delivered at SC2's realised 75% | 4,185 | 4,653 | 5,580 |
| Example B order (7 drops) | 1,428 (204 a day) | 1,596 (228 a day) | — |
| Example B extra units if the supplier delivers 100% | 0 | 24 a day, 168 a week; with R = 1, all expected to expire | — |

Planning for full delivery leaves Example C short by about 1,392 units in SC2, inside the window as well as before
it. Grossing up fixes that shortfall in SC2, but in SC1 (full delivery) it would add expiry exposure. Example B shows
that cost for a short-life line. This is the trade-off behind decision D3.

### Example E — no recommendation

The accepted replay has 5,040 decision points with unavailable bounds. They get no quantity, category
`NO_RECOMMENDATION_REVIEW_REQUIRED` and a mandatory review.

No series is `UNSUPPORTED` in the draft data: lead times are 1–3 days. The test `T1/U` forces one by adding 6 days of
lead time.

---

## 9. Output record (one row per store × product × origin)

| Group | Fields |
|---|---|
| Identity | recommendation id, store, product, category, origin week, target week, scenario, assumption-set id and content hash, engine version |
| Inputs used | contract row key; lots on hand (id, quantity, arrival, expiry); scheduled deliveries (id, ordered quantity, day); `f_plan` |
| Calculation | per-day table for D0 … a+6: sellable stock, planning use, shortfall, expiring units; per-drop table: day, days covered, net need, gross need, order, overage, expiry |
| Results | proposed units per drop and in total; pre-delivery position and gap at p10/p50/p90; post-order position; residual shortfall; expected expiry of existing stock and of the new order (heuristic); fill-rate exposure |
| Review | category, case type, reasons, warnings, `escalation_required` |
| Status | `HYPOTHETICAL_UNAPPROVED` / `PENDING_APPROVAL`, `approval_event_id` (empty), `position_note` |

---

## 10. Tests and acceptance criteria

### 10.1 Tests to implement

Unit tests use small hand-built cases. Integration tests use the synthetic fixtures, plus the protected real
contract where stated.

| # | Area | Test |
|---|---|---|
| T1a | Expiry-aware stock | A lot expiring on day *e* contributes nothing to days after *e*; Example A is reproduced exactly (4,176) |
| T1b | Expiry-aware stock | With no stock and no expiry inside the window, P2 = P1 for every drop; Example B is reproduced (1,428) |
| T1c | Expiry-aware stock | Proposed drops never cover days after their own expiry; short-life R = 1, 2, 4, 6 tested |
| T2a | No future information | Scrambling or permuting sales after cut-off K (3 cut-offs) leaves every recommendation for origins ≤ K identical, including the per-day tables |
| T2b | No future information | Changing the realised fill rate or over-delivery leaves the first decision identical |
| T2c | No future information | Mutation check: an injected leak (reading realised deliveries, or week T+1 demand) must make T2a or T2b fail |
| T2d | No future information | `DemandAccess` log: every demand read happens after the decisions for its origin |
| T3 | Pre-delivery shortage | Hand cases give the right position and gap at each rate; Example C gives a gap of 404.4 / 1,006.7 / 1,752.1 and category `PRE_DELIVERY_SHORTAGE`; the gap never counts the new order |
| T4a | Delivery timing | All drops arrive on `a + k·R` within the window; no drop before day `a` |
| T4b | Delivery timing | Same units arriving later give a worse post-order position |
| T4c | Delivery timing | Committed deliveries count only from their arrival day |
| T5a | Supplier fill | `f_plan` gross-up is exact (Example D) |
| T5b | Supplier fill | Planned and realised fill can differ, and only planned fill enters sizing |
| T5c | Supplier fill | Fill-rate exposure is ≥ 0 and grows as `f_low` falls |
| T5d | Supplier fill | `f_plan` = 100% reproduces F1 |
| T6 | Case and MOQ | Every drop is 0 or a multiple of the case size ≥ MOQ × case; overage = order − gross need, in [0, max(case, MOQ × case)); need ≤ 0 means no forced MOQ |
| T7 | Conservation | Per series-day: opening + received = sold + expired + closing; closing = next opening; no negatives; all integers; in all policies and scenarios |
| T8 | Determinism | Two runs are byte-identical; scenario-separated ids; policy-separated ids |
| T9a | Approval safeguards | No record has an approval, execution or authorisation status, or a non-empty `approval_event_id` |
| T9b | Approval safeguards | Christmas points are all `MANDATORY_ESCALATION` with `escalation_required` |
| T9c | Approval safeguards | Missing bounds or unsupported arrangement: no quantity and a mandatory review |
| T9d | Approval safeguards | The run script refuses to write if an approval event appears |
| T9e | Approval safeguards | Lead-time warning alone creates no case |
| T10 | Wording | Banned-wording test extended to the inventory and comparison outputs |
| T11 | Regression | Policy P1 inside the new code reproduces the protected v1.1 run's orders, deliveries and weekly outcomes exactly |
| T12 | Protection | Every protected run checksum is unchanged; new runs write only new folders |

### 10.2 Acceptance criteria for the implementation checkpoint

1. All of T1–T12 pass, along with the existing suite of 338 tests.
2. Conservation, chronology and leakage checks pass in every policy × scenario.
3. Residual shortfalls in P2 are zero, or each one has a named structural cause.
4. P1 reproduces the protected v1.1 replay exactly (T11).
5. The worked examples A–D are reproduced to the unit.
6. The comparison report follows section 7 and the wording rules.
7. No approved or executed status appears anywhere.
8. The v1 assumption set is untouched.

---

## 11. Operational limitations

1. **Data:**
   - Recorded sales are censored, so they are not unconstrained demand.
   - Opening stock and batch dates are synthetic.
   - There are no real on-hand, expiry or receipt records.
2. **Weekly forecast only.** Daily use is a weekly figure split by an assumed uniform profile. It is not a daily
   forecast.
3. **Assumed delivery arrangements:**
   - Weekday and weekend drops for short-life items are assumed.
   - There are no supplier calendars, order cut-off times, delivery slots or bank-holiday closures.
4. **Assumed and illustrative values:**
   - Transit age (1 day) is assumed.
   - Lead times are observed values but are treated as fixed. Lead-time variability is not modelled.
   - Case sizes, MOQ, service targets and margins are all ASSUMED placeholders.
5. **Missing constraints:**
   - There is no shelf space, store capacity or supplier capacity constraint. `Supply_Capacity` is undefined.
   - There are no transfers, expedited deliveries or substitutes.
6. **One supplier per product; no multi-week optimisation.** The engine looks one coverage window ahead. H4 is used
   only for the trend divergence check.
7. **Stock rotation.** Expiry is end of day, and selling is strictly oldest first. Real shelves may not rotate
   perfectly.
8. **Excess stock.** Expected-expiry figures are heuristics. Acting on excess stock (markdowns) belongs to the later
   waste-risk and pricing engines.
9. **Evidence limits.** Comparison results describe the synthetic replay only. They cannot show real waste reduction
   or lost sales avoided.

---

## 12. Implementation stages (each stops for your review)

| Stage | Content | Output |
|---|---|---|
| 5B-3a | Pure time-phased calculator `src/dpe/decision/inventory.py`: stock projection, per-drop sizing, coverage, exposure; unit tests T1, T3–T6 | tests only, no run |
| 5B-3b | Recommendation categories, approval record schema, review queue v1.2; tests T9, T10 | tests only |
| 5B-3c | Simulator v1.2 with a pluggable sizing policy (P0, P1, P2); regression T11 against the protected v1.1 run; leakage, conservation and determinism tests T2, T7, T8 | tests only |
| 5B-3d | New assumption-set version AS-…-v2 (DRAFT) for the new parameters (`planning_fill_rate_pct`, `f_low`, baseline window, thresholds). v1 stays untouched. | new JSON, validated |
| 5B-3e | Worked-example run, then full comparison run (3 policies × 3 scenarios + sensitivity); protect with checksums; comparison report | new protected runs, report, STOP |

---

## 13. Decisions requiring your approval

| # | Decision | Recommendation |
|---|---|---|
| D1 | Adopt time-phased, expiry-aware sizing (section 3) as the design for P2 | Approve |
| D2 | Depletion rate for existing stock **before** arrival: p50 (expected) or the planning rate (cautious) | p50, consistent with v1.1. The planning rate is used inside the window. |
| D3 | Planning fill rate: F1 (100% plus exposure), F2 (assumed rate) or F3 (as-of observed); value of `f_low` for exposure | F1 default; F2 as sensitivity; F3 only with real receipts; `f_low` = 75% |
| D4 | Recommendation categories and precedence (section 4.1) | Approve |
| D5 | No remedies for pre-delivery shortages (expedite, transfer) without documented evidence | Approve |
| D6 | Whether `SHORT_LIFE_ARRANGEMENT_ASSUMED` alone requires review | Warning only, until a supplier arrangement is documented |
| D7 | Rounding: always round up to cases and MOQ, or allow round-down when the overage would expire unsold | Round up (current); report overage |
| D8 | `Supply_Capacity`: leave unused until its unit and period are defined | Leave unused |
| D9 | Christmas escalations excluded from any bulk or default approval | Approve |
| D10 | Include an illustrative cost proxy (assumed margins) in the comparison | Optional; label as ASSUMED |
| D11 | Baseline definition P0 (4-week average, expiry-blind netting) and the pre-registered thresholds in section 7.4 | Approve before any comparison run |
| D12 | New parameters go into a new assumption-set version (v2, DRAFT); AS-2026-10-22-v1 is not edited | Approve |
