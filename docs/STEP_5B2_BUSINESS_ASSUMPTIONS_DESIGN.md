# Step 5B-2: business assumptions and scenario design (v2, amended)

- **Status:** design only. **Conditionally approved; version 2 addresses the seven amendments of 2026-10-22.**
  - Not created: the assumption JSON, the simulator, any inventory, waste or pricing engine, any database or table.
  - Unchanged: the forecast contract and protected runs. Nothing was retrained or installed, and nothing was connected.
- **Date:** 2026-10-22 (v1 earlier the same day; v2 replaces it)
- **Builds on:**
  - [STEP_5A_DECISION_ENGINE_DESIGN.md](STEP_5A_DECISION_ENGINE_DESIGN.md)
  - Forecast contract v1.0, `outputs/runs/20261022-081926_forecast_contract/`
  - DECISIONS 23–26
- **Conditions from the 5B-1 acceptance (unchanged):**

  | # | Condition |
  |---|---|
  | C1 | The 2024 holiday calendar is for **historical replay only**; no future holidays are inferred |
  | C2 | Each origin occurs **after** that week's sales and prices are finalised |
  | C3 | The reference price is an **estimated proxy**, not a verified shelf price |
  | C4 | The p10/p50/p90 bounds are **provisional**, not guaranteed coverage |
  | C5 | All 7,920 forecasts without bounds require a flagged **human-review** status |
  | C6 | Weekly forecasts are **never** presented as daily stockout or expiry predictions |

> **Every value marked ASSUMED or SYNTHETIC is an illustrative demonstration default.** None is supported by observed business data. The underlying data is *apparently synthetic; provenance unconfirmed*.

## Amendment log (v1 → v2)

| # | Amendment requested | Where addressed |
|---|---|---|
| A1 | Service levels and uncertainty: no calibrated-probability claims; explicit approximate planning thresholds; > 90% unsupported or separately justified | §3 |
| A2 | Explicit simulated within-week delivery and expiry schedule for shelf life < 7 days; one conservation rule | §4 |
| A3 | Order timing, lead-time calculation, mid-week arrivals; no assumption of start-of-week availability | §5 |
| A4 | Review queue: mandatory review and escalation, holiday prioritisation, no duplicate cases | §7 |
| A5 | Parameters kept as illustrative defaults, with validation rules, evidence status and the non-causal uplift statement | §2 |
| A6 | Bakery and Dairy examples recalculated, separating the plan, the simulated outcome and the action needing approval | §10 |
| A7 | Implementation acceptance criteria for the versioned assumption file and the stateful replay simulator | §11 |

**What changed from v1:**

| Topic | v1 | v2 |
|---|---|---|
| Stockout risk | "Stockout-risk bands" | **Coverage positions** (§3.2) |
| Service mapping | Normal-shape service factor | **Linear planning weight, capped at p90** (§3.1) |
| Short-life carry-over | "No carry-over" | **Day-level simulated drops, with carry-over across days and weeks until expiry** (§4) |
| Lead time | "Usable for the whole target week" | **Usable from the arrival day only** (§5) |
| Holiday weeks | Escalate (flag or escalate, undecided) | **Flag and prioritise; escalate only with a material trigger** (§7) |

---

## 1. Observed vs missing operational inputs

| Input | Status | Source / note | Granularity |
|---|---|---|---|
| Weekly units sold | **OBSERVED** | `weekly_sales.Units_Sold` | store × product × week |
| Recorded price, discount % | **OBSERVED** (price ambiguous) | Price appears post-discount (undocumented) | store × product × week |
| Shelf life | **OBSERVED** | 2–356 days. **22 of 48 products are below 7 days** (all 12 Bakery, 10 of 12 Meat). | product, days |
| Supplier lead time | **OBSERVED** | 1–3 days (Bakery and Meat suppliers 2–3) | supplier, days |
| Supplier capacity, cold storage | OBSERVED, **units unknown** | Informational only | supplier / store |
| Holiday calendar | OBSERVED, 2024 only | Replay only (C1) | region × week |
| Forecast and bounds | **CALCULATED** | Contract v1.0; bounds unavailable for 7,920 rows | store × product × origin × horizon |
| Reference price | **CALCULATED** proxy (C3) | Median Price / (1 − d), weeks ≤ origin | store × product × origin |
| Daily sales profile | **MISSING** | Only weekly totals exist; any daily split is SYNTHETIC | — |
| Stock, deliveries, lots, expiry dates | **MISSING** | SYNTHETIC simulator (§4–§6) | — |
| Cost, margin, holding cost, MOQ, case sizes, service targets | **MISSING** | ASSUMED defaults (§2) | — |
| Stockouts and lost sales | **MISSING** | Not recoverable; recorded sales are treated as demand (possibly censored) | — |

---

## 2. Assumption set v1: parameters, evidence and validation

**Proposed file** (created at implementation, **not now**): `config/assumptions/assumption_set_v1.json`. Plain JSON, immutable once approved; changes create v2, v3, …

### 2.1 File-level fields

| Field | Content |
|---|---|
| `assumption_set_id` | `AS-2026-10-22-v1` |
| `status` | `DRAFT` / `APPROVED` (never edited after approval) |
| `approved_by`, `approved_at` | Filled on approval |
| `currency` | `GBP (assumed; not stated in the data)` |
| `time_granularity` | `weekly decisions; daily simulation steps are SYNTHETIC` |
| `parameters[]` | Parameter records (§2.2) |
| `scenarios{}` | Overrides (§8) |
| `sha256` | Of the canonical file content; recorded by every run |

### 2.2 Parameter record fields

| Field | Meaning |
|---|---|
| `key`, `value`, `unit`, `granularity`, `scope` | What the parameter is and where it applies (global, category or product) |
| `provenance` | One of OBSERVED, CALCULATED, ASSUMED, SYNTHETIC |
| `evidence` | One of `OBSERVED_DATA`, `DERIVED_FROM_OBSERVED`, `NONE_ILLUSTRATIVE` |
| `supported_by_observed_business_data` | `true` / `false` |
| `rationale` | Why this value |
| `allowed_range`, `sensitivity_range` | Valid values; values tested in sensitivity runs |

### 2.3 Illustrative defaults (retained from v1, with evidence status)

| # | `key` | Default | Unit | Scope | Provenance | Evidence | Supported by business data? | Sensitivity range |
|---|---|---|---|---|---|---|---|---|
| 1 | `gross_margin_pct` | Bakery 45, Beverages 35, Meat 30, Dairy 28 | % of reference price | category | ASSUMED | NONE_ILLUSTRATIVE | **No** | ±10 points |
| 2 | `purchase_cost` | reference_price × (1 − margin/100) | GBP per unit | store × product × origin | CALCULATED from ASSUMED + proxy | DERIVED (proxy × assumption) | **No** | follows #1 |
| 3 | `min_margin_pct` (after discount) | Bakery 10, Beverages 10, Meat 8, Dairy 8 | % of discounted price | category | ASSUMED | NONE_ILLUSTRATIVE | **No** | 5–15 |
| 4 | `max_discount_pct` | 25 (hard cap) | % off reference price | global | ASSUMED | Largest observed level | **No** (observed in data, not a policy) | 10–25 |
| 5 | `discount_steps_pct` | 5, 10, 15, 20, 25 | % | global | ASSUMED | Observed levels | **No** | — |
| 6 | `holding_cost_pct_per_week` | 0.50 ambient (Bakery, Beverages); 0.75 chilled (Dairy, Meat) | % of cost per unit per week | category | ASSUMED | NONE_ILLUSTRATIVE | **No** | 0.25–1.50 |
| 7 | `service_target_pct` (business intent label) | Bakery 85, Meat 88, Dairy 92, Beverages 95 | % (intent, **not** a guaranteed probability) | category | ASSUMED | NONE_ILLUSTRATIVE | **No** | 50–90 supported; above 90 per §3.3 |
| 8 | `planning_weight` | from #7 by §3.1: Bakery 0.875, Meat 0.95, Dairy **1.00 (capped)**, Beverages **1.00 (capped)** | dimensionless, 0–1 | category | CALCULATED | Rule | **No** | 0–1 |
| 9 | `case_size_units` | Bakery 12, Meat 6, Dairy 12, Beverages 24 | units per case | category | ASSUMED | NONE_ILLUSTRATIVE | **No** | ×0.5 to ×2 |
| 10 | `moq_cases_per_delivery` | 2 | cases per delivery line | global | ASSUMED | NONE_ILLUSTRATIVE | **No** | 1–4 |
| 11 | `transit_age_days` | 1 | days of shelf life used before arrival | global | ASSUMED | NONE_ILLUSTRATIVE | **No** | 0–2 |
| 12 | `lead_time_days` | observed per supplier | days from order placement to arrival | supplier | OBSERVED | OBSERVED_DATA | Yes (as recorded) | +0 to +2 (scenario) |
| 13 | `opening_cover_weeks` | short-life 0; Dairy 0.5; Beverages 1.5 | weeks of the as-of 4-week average | category | SYNTHETIC | NONE_ILLUSTRATIVE | **No** | 0.25–3.0 |
| 14 | `delivery_fill_rate_pct` | 100 | % of ordered units delivered | supplier | SYNTHETIC | NONE_ILLUSTRATIVE | **No** | 60–100 |
| 15 | `daily_demand_profile` | uniform (1/7 per day) | share of the week's units per day | global | SYNTHETIC | NONE_ILLUSTRATIVE | **No** | uniform; weekend-heavy [.12,.12,.13,.14,.16,.18,.15] |
| 16 | `waste_band_pct` | LOW < 5, MEDIUM 5–15, HIGH > 15 | % of weekly p50 | global | ASSUMED | NONE_ILLUSTRATIVE | **No** | thresholds ±5 points |
| 17 | `discount_uplift_per_point` | +1.6% (log scale), assessed at 0.5×, 1.0× and 1.5× | units multiplier | global | ASSUMED | **Non-causal** EDA association in apparently synthetic data | **No** | 0.5×–1.5× |
| 18 | `scenario_multipliers` | as §8 | as stated | scenario | SYNTHETIC | NONE_ILLUSTRATIVE | **No** | as §8 |

**Discount-uplift statement** (stored with #17 and printed in every output that uses it):
> *The +1.6% per discount point figure is a statistical association observed in apparently synthetic historical data. It is not a causal effect and not an elasticity. It must not be used to promise, forecast or report additional sales, revenue or margin. It is used only to check whether a markdown could plausibly reduce a projected surplus within the safety limits, and the result is always presented for human approval.*

### 2.4 Validation rules (for the assumption file; tested at implementation)

| ID | Rule |
|---|---|
| V1 | Every parameter has `key`, `value`, `unit`, `granularity`, `scope`, `provenance`, `evidence`, `supported_by_observed_business_data`, `rationale` and `allowed_range` |
| V2 | Values lie in `allowed_range`. Margins 0–90; `min_margin_pct` < `gross_margin_pct` per category; `max_discount_pct` ≤ 25; every discount step ≤ the cap; holding cost 0–5%/week; case size and MOQ integers ≥ 1; `planning_weight` 0–1; fill rate 0–100; scenario multipliers 0.5–1.5; transit age 0 to (shelf life − 1); profile shares sum to 1 (tolerance 1e-9) |
| V3 | Waste-band thresholds strictly increasing |
| V4 | Every ASSUMED or SYNTHETIC parameter has `supported_by_observed_business_data = false` and `evidence = NONE_ILLUSTRATIVE` (or `DERIVED…` where marked) |
| V5 | Scenario overrides refer only to existing keys and stay inside `allowed_range` |
| V6 | `status = APPROVED` is required for demonstration runs. `DRAFT` runs are allowed only with a `DRAFT` watermark on every output. |
| V7 | The SHA-256 of the canonical JSON matches the recorded value. An `APPROVED` file whose hash changes is rejected (immutability). |
| V8 | Feasibility report per category: the largest discount step allowed by the margin floor, `min(cap, 1 − cost / (price × (1 − min_margin)))`. For example, Dairy at a 28% margin and 8% minimum allows 21.7%, so 20% is the largest step. A parameter set where no discount is possible for a category is allowed, but reported. |

---

## 3. Service targets and uncertainty: conservative planning thresholds (A1)

### 3.1 Planning weight: an explicit approximation, not a probability
The contract provides only p10, p50 and p90, and they are not calibrated. In the replay, actual sales exceeded p90 in **13.8%** of H1 rows and **17.8%** of H4 rows (expected 10%). By category:

| Category | H1 above p90 | H4 above p90 |
|---|---|---|
| Bakery | 18.6% | **31.4%** |
| Meat | 18.4% | 23.9% |
| Dairy | 11.7% | 13.4% |
| Beverages | 6.5% | 2.7% |

So the planning rule is stated as a **weight** between the two quantiles, not as a probability:

    planning_weight w = clip( (service_target_pct − 50) / 40 , 0 , 1 )
    weekly planning target  S_week = p50 + w × (p90 − p50)            (units per week)

- *w* = 0 plans at the median.
- *w* = 1 plans at p90.
- Targets in between interpolate linearly. This is a transparent approximation with no distributional claim.
- The "service target" is a **business intent label**. Outputs never say "X% probability of no stockout".

### 3.2 Coverage position (replaces "stockout-risk bands")
Planned usable stock for the coverage window (§5) is compared with the forecast quantiles for that window.

| Position | Condition | Planning meaning (approximate; **not** a calibrated probability) |
|---|---|---|
| `ABOVE_P90` | stock ≥ p90 | Shortage pressure low; surplus pressure likely |
| `P50_TO_P90` | p50 ≤ stock < p90 | Planned around the upper half of the forecast range |
| `P10_TO_P50` | p10 ≤ stock < p50 | **Shortage pressure:** planned below the median forecast (material trigger) |
| `BELOW_P10` | stock < p10 | **Severe shortage pressure** (material trigger; escalate) |

Each record also carries the reference table above ("historical replay exceedance of p90 for this category and horizon"). It is presented as **context, not a guarantee**.

### 3.3 Targets above 90%: unsupported by default
- **Default:** a target above 90% is **unsupported**. It is capped at *w* = 1 (p90) and flagged `TARGET_ABOVE_P90_CAPPED`. This applies to Dairy (92) and Beverages (95). The flag is informational and does not on its own create a review case.
- **Optional, separately justified extrapolation** (off by default; needs your approval):

      S_week = p90 + e × (p90 − p50),   e ≤ 0.25

  Every affected record is flagged `UNSUPPORTED_EXTRAPOLATION` and **requires review**. The justification (for example, a category with very high stockout cost) must be recorded in the assumption set.
- **Recommendation:** keep it off. The data cannot support quantiles beyond p90.

### 3.4 Missing bounds (C5)
Where `uncertainty_status = UNAVAILABLE_INSUFFICIENT_HISTORY`:
- no *w*, S_week, coverage position or waste band can be computed
- the point forecast is shown as **reference only**
- status is `HUMAN_REVIEW_REQUIRED`; there is no automatic order and no discount proposal (§7)

---

## 4. Short-life products: simulated within-week schedule (A2)

**Applies to** products whose **remaining life on arrival** is below 7 days:

    R = shelf_life_days − transit_age_days,   minimum 1

With `transit_age_days` = 1 this covers all 12 Bakery and 10 Meat products, and also Semi-Skimmed Milk (8 − 1 = 7: §4.5).

### 4.1 Time steps
The simulator runs in **daily steps** inside each week (day 1 = Monday … day 7 = Sunday). Decisions are still made **only weekly**, at origin weeks (C2). Every daily quantity is **SYNTHETIC**.

### 4.2 Daily demand (simulated split of the weekly total)
- Week *t* simulated demand = recorded units of week *t* × the scenario multiplier.
- It is split across days by `daily_demand_profile`, as **integers**, using the largest-remainder method. The seven daily values therefore **sum exactly** to the weekly integer.
- Example: 1,018 = [146, 146, 146, 145, 145, 145, 145].

### 4.3 Delivery schedule (drops)

| Item | Rule |
|---|---|
| Drop interval | *k* = min(R, 7) days. R = 1 means daily drops; R = 3 means a drop every 3 days, and so on. |
| What one weekly decision sets | The quantities of all drops whose **arrival day falls in its coverage window** (§5) |
| Drop quantity | roundup_to_case( w-target daily rate × days covered by the drop ), and ≥ MOQ |
| w-target daily rate | S_week / 7: a flat weekly rate, an assumption |
| Total constraint | The total over the window equals the sum of its drops, so rounding is explicit, never hidden |

### 4.4 Receipt, sale, expiry and carry-over (FIFO)
Each day, in this order:
1. **Receive** that day's drop: a lot with an expiry day of arrival day + R − 1. It is sellable on R days, including the arrival day.
2. **Sell** min(daily demand, available units), oldest expiry first. Unmet units are recorded as `sim_unmet_units` (simulated lost sales).
3. **Expire** at end of day every lot whose expiry day is today: `sim_expired_units`.
4. **Carry over** what remains to the next day, **including across the week boundary** (a Sunday lot with R ≥ 2 is sellable on Monday).

### 4.5 Long-life products (R ≥ 7)
Same daily engine, one delivery per coverage window, arriving on the arrival day (§5). Lots carry over until their expiry day, first in, first out.

### 4.6 Conservation rule (one rule, at every level)

    for every series and every day:   opening + received = sold + expired + closing     (all integers, ≥ 0)
    unmet = demand − sold   (≥ 0;  recorded separately, never in stock)

Weekly and run totals are sums of daily values. Any violation fails the run.

### 4.7 Inferred from data vs purely simulated

| Inferred from observed data | Purely simulated (SYNTHETIC) |
|---|---|
| Weekly units sold (treated as demand; possibly censored) | The split of the week into days |
| Shelf life, supplier lead time | Delivery days, drop sizes, lots and their expiry days |
| Forecast and bounds (contract) | Stock on hand, expired units, unmet units, fill rate |
| Reference price (proxy) | Anything at a time resolution below one week |

**Reporting rule (C6).** Outputs, explanations and the dashboard report **weekly aggregates** of simulated quantities only: weekly `sim_expired_units`, weekly `sim_unmet_units`, days with simulated unmet demand *count*. Daily values are kept for audit and conservation tests with the label `SIMULATED_DAILY_NOT_A_PREDICTION`, and are never shown as predicted stockout or expiry days.

---

## 5. Lead times and order timing (A3)

| Item | Rule |
|---|---|
| Decision time | Start of day 1 of week *T* + 1, immediately after week *T* is finalised (C2) and before trading |
| Order placement | At decision time, for all deliveries in the coverage window |
| Arrival day | Day 1 + LT of week *T* + 1, where LT = observed supplier lead time in days (+ scenario adjustment). LT = 3 means it arrives at the start of **Thursday**. |
| Availability | From the **arrival day only**. Demand on earlier days is served from stock carried over or earlier drops. **A 2–3-day lead time does not make stock available from Monday.** |
| Coverage window | The 7 consecutive days from the arrival day: days 1 + LT … 7 + LT, spanning the end of week *T* + 1 and the start of week *T* + 2 |
| Window demand target | S_week from the H1 contract row for target week *T* + 1, applied as a flat weekly rate over the window. **Assumption:** the first LT days of week *T* + 2 are assumed to sell at the same rate. H4 is used only as a trend check. |
| Short-life drops | Each drop in the window has its own arrival day. It is part of the weekly order but arrives on its scheduled day. |
| Order quantity | roundup_to_case( max(0, window target − usable stock expected at arrival that is still sellable in the window) ). Usable stock at arrival = current simulated stock − expected sales before arrival (p50 rate × LT days), counting only lots not expired by arrival. |
| Mid-week arrivals | Day-level availability means mid-week arrivals behave exactly as above. Shortfalls before arrival are recorded as `sim_unmet_units` and cannot be fixed by the current decision. That limitation is reported. |
| First simulated week | Opening stock (§6, step 1) and an initial drop schedule for days 1…LT, from as-of averages. All SYNTHETIC. |
| Lead time ≥ remaining life | Can occur in SC2 (LT + 1 day). Flag `LIFE_LEAD_TIME_TIGHT`; the row is a material trigger. |

---

## 6. Synthetic stock generation without future information

**Rule:** every synthetic quantity used at decision time for origin *T* is a function only of:
- (a) data dated ≤ *T*
- (b) the approved assumption set and scenario
- (c) simulator state produced by earlier decisions and past days

**Chronological loop**, for each origin *T* in order:
1. **First origin only:** opening stock = opening_cover_weeks × mean recorded sales of weeks *T* − 3…*T* (data ≤ *T*). Short-life items start at 0, plus the initial drop schedule.
2. **Decide** using the contract rows for origin *T* and the current state: orders, review cases, signals.
3. **Simulate days 1–7 of week *T* + 1:**
   1. receive drops arriving that day (× fill rate)
   2. sell simulated demand for that day (week *T* + 1 recorded sales × multiplier, split per §4.2)
   3. expire lots
   4. carry over

   **Week *T* + 1 sales are read only here, after the decision for *T*.**
4. Record state. Move to *T* + 1.

**Further guarantees:**
- No forecast error from a target week after *T* enters any decision at *T*. The contract already guarantees this.
- No randomness in v1.
- A truncation and scrambling test (§11) proves that decisions and states up to *T* do not change when data after *T* is scrambled.

---

## 7. Review queue: mandatory cases, prioritisation, no duplicates (A4)

**Case unit:** one **decision point** = store × product × origin week, covering both horizons. There is at most **one open case per decision point**. All reasons are listed inside it.

| Case type (highest first) | Created when | Can be closed without a human? |
|---|---|---|
| `MANDATORY_ESCALATION` | Any H1 or H4 target week is 51 or 52 (Christmas) | No |
| `MANDATORY_REVIEW` | Any contract row at the decision point has unavailable bounds | No |
| `RISK_ESCALATION` | A material risk trigger is present (below), with or without a holiday flag | No |
| `APPROVAL_REQUIRED` | A price action or policy change is proposed (discount, reduced ordering policy) | No |
| (no case) | Holiday flag only, or informational flags only | — (the flag is shown, and it raises priority if a case exists) |

**Material risk triggers:**
- coverage position `P10_TO_P50` or `BELOW_P10`
- waste band HIGH on existing stock
- a binding safety limit (price floor, margin floor, cap)
- a proposed discount ≥ 20%
- `UNSUPPORTED_EXTRAPOLATION`
- `LIFE_LEAD_TIME_TIGHT`
- a simulated fill-rate shortfall last week
- `TREND_DIVERGENCE` (H4 versus H1)

**Ordinary holiday weeks:**
- They get the flag `HOLIDAY_TARGET_WEEK` and a **priority boost**.
- They create or escalate a case **only together with** a material trigger.

**Priority within a type:**
- Ordered by score = type rank + holiday boost + short-life boost + share of the store's weekly units.
- Ties are broken by store and product id, so the order is deterministic.

**De-duplication** (computed from the contract):

| Trigger | Contract rows | Decision points (cases) | Overlaps |
|---|---|---|---|
| Missing bounds | 7,920 | **5,040** mandatory reviews | 0 with Christmas |
| Christmas | 2,880 | **2,880** mandatory escalations | 2,448 also holiday-flagged |
| Holiday target week | 6,336 | 5,760 flagged | 624 inside missing-bounds cases |
| **Mandatory cases in total** | — | **7,920** of 19,440 decision points | — |

- **Holiday-only decision points** (2,688) are flagged and prioritised, but are cases only when a material trigger applies.
- **Note:** the share of mandatory cases is high (41%) because the replay window starts before 4 weeks of errors exist. It falls to the Christmas share once bounds are available.

---

## 8. Scenarios (retained from v1)

Each scenario is a set of **SYNTHETIC** overrides. Forecasts are never told about the stress settings, and recorded sales on disk are never changed.

| Parameter | **SC1 Normal trading** | **SC2 Demand / supply pressure** | **SC3 Excess stock / expiry pressure** |
|---|---|---|---|
| Opening cover (long-life) | base | × 0.3 | × 2.0 |
| Delivery fill rate | 100% | **75%** | 100% |
| Over-delivery (short-life) | none | none | **+20%** |
| Lead time | observed | **+1 day** | observed |
| Simulated demand multiplier | 1.00 | **1.15** | **0.85** |
| Expected direction (sanity, not targets) | baseline | More shortage-pressure positions and RISK_ESCALATION than SC1 | More HIGH waste bands and APPROVAL_REQUIRED (discount / reduce ordering) than SC1, with **0** safety-limit violations |

---

## 9. Sensitivity design (retained)

**Method:** one at a time, over each `sensitivity_range` (§2.3), in SC1. The three most influential parameters are then repeated in SC2 and SC3.

**Reported per variation:**
- action and case mix
- % of decision points whose primary action changes
- weekly simulated KPIs: received, sold, expired, unmet units, weeks with unmet demand
- binding-limit counts

**Directional checks** (become tests):

| Change | Expected direction |
|---|---|
| Higher planning weight | Order quantity does not decrease |
| Higher minimum margin | Largest allowed discount does not increase |
| Larger case size | Order quantity does not decrease |
| Lower fill rate | Simulated unmet units do not decrease |
| Lower demand multiplier | Simulated expired units do not decrease |

---

## 10. Worked examples (recalculated under v2 rules) (A6)

Each example separates three things:
- **(P) the planning recommendation** at decision time
- **(S) the simulated outcome** in the replay (SYNTHETIC; uses sales that were not known at decision time)
- **(A) the action requiring approval**

### 10.1 Bakery: White Sandwich Loaf, store 505 (SC1)
- **Facts:** shelf life 2 days; supplier TrustedSource Provisions, **lead time 3 days**.
- **Contract row:** origin week 44, target week 45 (H1 RF). p10 635, p50 997, p90 1,477. Bounds AVAILABLE. Reference price £2.39 (proxy).

**(P) Planning recommendation:**
1. **Remaining life on arrival:** R = 2 − 1 = **1 day**, so **daily drops**, each sellable only on its arrival day.
2. **Timing:** the decision is at the start of Monday, week 45. Orders arrive from **Thursday** of week 45 (LT 3). The coverage window is Thursday of week 45 to Wednesday of week 46. Monday–Wednesday of week 45 were set by the previous decision.
3. **Planning weight:** service target 85, so *w* = (85 − 50)/40 = **0.875**. S_week = 997 + 0.875 × (1,477 − 997) = **1,417**. Daily rate 202.4, rounded up to cases of 12: **204 units per drop** (≥ MOQ of 24).
4. **Order:** **7 drops × 204 = 1,428 units (119 cases)** across the window.
5. **Coverage position:** `P50_TO_P90`, not a probability. Historical replay context: Bakery H1 sales exceeded p90 in 18.6% of weeks.
6. **Planned exposure if sales equal p50:** (1,428 − 997) / 997 = **43%**, a HIGH band. This is a weekly planning figure, not a prediction.
7. **Price limits** (assumed 45% margin): cost £1.31; the margin floor allows up to 38.9%; the **25% cap binds** at a lowest price of £1.79.

**(S) Simulated outcome:**
- **Week 45** (steady state, previous decision also 204 per day): recorded sales 1,018, split [146, 146, 146, 145, 145, 145, 145].
  - Each day: 204 received, 145–146 sold, 58–59 expired.

  | Received | Sold | Expired | Unmet | Opening / closing stock |
  |---|---|---|---|---|
  | 1,428 | 1,018 | **410** | 0 | 0 / 0 |

  Conservation holds: 0 + 1,428 = 1,018 + 410 + 0.
- **Lead-time consequence, week 46:** recorded sales 1,684 (about 241 per day). Monday–Wednesday drops were fixed at 204 by *this* decision, so the simulation records **111 unmet units** (37 per day) in those three days. The next decision (origin 45) cannot change them.
- These are simulated mechanics under assumptions, **not** a waste or stockout prediction.

**(A) Action requiring approval:**
- **None mandatory this week:** bounds are available, it isn't Christmas, the target week isn't a holiday, and the coverage position is not a shortage position.
- The HIGH planned exposure is logged as a signal. If it recurs in ≥ 2 of the last 3 decisions, an `APPROVAL_REQUIRED` case proposes **REDUCE_FUTURE_ORDERING** (lowering *w* for this item), which needs human approval.
- **What the planning weight changes:**

  | *w* | Drop | Window order | Planned exposure | Simulated week-45 expired / unmet |
  |---|---|---|---|---|
  | 0.875 (base) | 204 | 1,428 | 43% HIGH | 410 / 0 |
  | 0.50 | 180 | 1,260 | 26% HIGH | 242 / 0 |
  | 0.00 (p50) | 144 | 1,008 | 1% LOW | 0 / **10** |

### 10.2 Dairy: Semi-Skimmed Milk 4-pint, store 505 (SC1)
- **Facts:** shelf life 8 days; supplier PremiumGoods Wholesale, **lead time 3 days**.
- **Origin 44 → target 45 (H1):** p10 1,178, p50 1,842, p90 2,676. Reference price £2.69.
- **Origin 45 → target 46:** p50 1,837, p90 2,640. Reference price £2.64.

**(P) Planning recommendation at origin 44:**
1. **Remaining life on arrival:** R = 8 − 1 = **7 days**, so one delivery per window. It arrives on **Thursday** of week 45 and is sellable Thursday to Wednesday of week 46. That is exactly the coverage window.
2. **Planning target:** service target 92 is **above 90**, so it is **capped at p90** (*w* = 1, `TARGET_ABOVE_P90_CAPPED`, informational). Window target = 2,676.
3. **Order:** the previous lot expires on Wednesday of week 45, before arrival, so usable stock at arrival = 0. Order = **2,676 units (223 cases)**.
4. **Price limits** (assumed 28% margin): cost £1.94; the 8% margin floor gives a minimum price of £2.11, a 21.7% discount. **The largest step is 20%** (`SAFETY_LIMIT_BINDING: MIN_MARGIN` if more were sought).

**(S) Simulated outcome in week 45** (recorded sales 1,894, split [271, 271, 271, 271, 270, 270, 270]):
- Thursday–Sunday sell **1,081** from the new lot.
- Stock at the next decision: **1,595**, expiring end of Wednesday, week 46.

**(P) Planning recommendation at origin 45** (start of week 46; existing stock 1,595 expiring Wednesday):
1. **Expected sales before expiry** (Mon–Wed at the p50 rate): 3/7 × 1,837 = **787**.
2. **Projected surplus at expiry:** 1,595 − 787 = 808, which is 44% of the weekly p50: **HIGH**, on existing stock.
3. **Discount eligibility check** (largest allowed step 20%; uplift is an assumption, §2.3 #17):

   | Uplift assumption | Expected 3-day sales at 20% off | Surplus | Band |
   |---|---|---|---|
   | 0.5× | 924 | 671 (37%) | HIGH |
   | 1.0× | 1,084 | 511 (28%) | HIGH |
   | 1.5× | 1,272 | 323 (18%) | HIGH |

   **No allowed step brings the surplus to MEDIUM, even under the most favourable assumption.** So **no discount is proposed**.
4. **New order for the next window:** stock at arrival is expired, so the order is the p90 window target, **2,640**.

**(A) Action requiring approval at origin 45:**
- **`RISK_ESCALATION`**, with reasons `EXPIRING_SURPLUS_NOT_RESOLVABLE_WITHIN_LIMITS` and `TARGET_ABOVE_P90_CAPPED`.
- Plus an `APPROVAL_REQUIRED` proposal: **REDUCE_FUTURE_ORDERING** (review the capped p90 target for this item).
- **One case** for this decision point, with both reasons, not two.
- No price change is made without approval, and **no extra sales or revenue are claimed**.

**(S) Simulated outcome in week 46** (recorded sales 2,794, above p90; not known at origin 45):
- Monday–Wednesday sell **1,198** from the old lot.
- **397 units expire** on Wednesday, against 808 projected. Demand turned out unusually high.
- The new lot (2,640) arrives Thursday and covers Thursday–Sunday demand of 1,596.

**Reading.** The plan flagged a large surplus. The simulated outcome was smaller, because week 46 sold far above its forecast. That is exactly why the projected surplus is a *planning signal for review*, not a prediction.

---

## 11. Implementation handoff: acceptance criteria (A7)

### 11.1 Versioned assumption file

| ID | Criterion |
|---|---|
| AF1 | Schema validation: every V1–V8 rule passes; a missing field or out-of-range value raises an error |
| AF2 | Immutability: an `APPROVED` file's recomputed SHA-256 equals the recorded hash; any edit is rejected; changes require a new version id |
| AF3 | Evidence: 100% of ASSUMED and SYNTHETIC parameters have `supported_by_observed_business_data = false` |
| AF4 | Scenario overrides are valid (V5) and produce a fully resolved parameter set per scenario, which is recorded |
| AF5 | Feasibility report (V8) generated and stored with the run |
| AF6 | The non-causal uplift statement is present in the file and in every output that uses #17 |

### 11.2 Stateful chronological replay simulator

| ID | Criterion |
|---|---|
| S1 | **No future leakage.** Truncation test: for cut-offs *T*, the state and decisions up to *T* are identical with data after *T* removed. Scrambling test: the same with all sales, prices and contract actuals after *T* replaced at random. |
| S2 | **Chronology.** Week *T* + 1 sales are read only after the decision for origin *T*. This is checked by instrumented access logging in tests. |
| S3 | **Determinism.** The same inputs, assumption set and scenario give byte-identical outputs. |
| S4 | **Conservation.** For every series × day: opening + received = sold + expired + closing; unmet = demand − sold ≥ 0; all integers ≥ 0. Weekly totals equal the sums of daily values. |
| S5 | **Daily split.** Daily demand sums exactly to the weekly integer (largest remainder); profile shares are applied as specified. |
| S6 | **Lead time.** Stock ordered at origin *T* is first available on day 1 + LT of week *T* + 1, never earlier. Demand before arrival is served only by older stock. |
| S7 | **Short-life schedule.** Drop interval = min(R, 7); lots are sellable for exactly R days; first in, first out; carry-over across the week boundary when R ≥ 2. |
| S8 | **Rounding.** Every positive drop or delivery is a multiple of the case size and ≥ MOQ; no negative orders. |
| S9 | **Provenance.** All simulated columns are prefixed `sim_` and carry `scenario_id` and `assumption_set_id`. OBSERVED columns equal their sources. The `SIMULATED_DAILY_NOT_A_PREDICTION` label is on daily data. The watermark is on every output. |
| S10 | **Weekly reporting (C6).** No output or explanation field states a day of stockout or expiry. A banned-phrase test covers "on day", "expires on", "will run out on", "stockout on". |
| S11 | **Missing bounds (C5).** 100% of the affected decision points get `MANDATORY_REVIEW`, and none gets an automatic order or a discount. |
| S12 | **Christmas.** 100% of decision points with target week 51 or 52 get `MANDATORY_ESCALATION`. |
| S13 | **De-duplication.** At most one case per decision point; reasons are aggregated; holiday-only points create no case. |
| S14 | **Scenario direction.** SC2 shows more shortage positions and unmet units than SC1. SC3 shows more HIGH waste bands and expired units than SC1. All scenarios have 0 safety-limit violations. |
| S15 | **Sensitivity.** The §9 directional checks pass. The sensitivity report is generated. |
| S16 | **Safety limits** (enforced even though pricing is not built yet). Any discount value the simulator records is ≤ 25%, is a valid step, and is ≥ the margin floor. |
| S17 | **Performance.** A full SC1 replay (720 series × 27 decision weeks × 7 days) completes within a recorded time budget (target under 10 minutes). |

**Not part of this hand-off:** inventory, waste or pricing engines, SQLite, the dashboard, Airtable and GitHub.

---

## 12. Remaining risks

1. **Assumption dominance.** The outcomes mainly reflect the illustrative parameters. Mitigation: evidence fields, sensitivity analysis, watermarks.
2. **Uncalibrated bounds.** The p90 exceedance is 13.8–31.4% depending on category and horizon. Planning at p90 does not deliver 90%, and the coverage-position wording reflects that.
3. **The daily split is invented.** It drives simulated within-week unmet and expired units for short-life items. Mitigation: a profile sensitivity and weekly-only reporting.
4. **Flat-rate window assumption.** The first LT days of the next week are assumed to sell at the current week's forecast rate.
5. **High mandatory-case share** (7,920 of 19,440 decision points), mostly from missing bounds in the first replay weeks.
6. **Censored sales and the price proxy** still underlie everything.

---

## 13. Decisions requiring your approval

1. **Planning-weight rule** (§3.1): linear between p50 and p90, capped at p90. Targets above 90% are **unsupported by default** (flag only), with extrapolation disabled. Or approve the optional extrapolation (*e* ≤ 0.25, review mandatory).
2. **Coverage positions** (§3.2) replace probability bands, with `P10_TO_P50` and `BELOW_P10` as material triggers.
3. **Short-life schedule** (§4): `transit_age_days` = 1, drop interval min(R, 7), first in first out, day-level carry-over, uniform daily profile by default.
4. **Lead-time rules** (§5): decision and order at the start of Monday, arrival on day 1 + LT, a 7-day coverage window from arrival, and the flat-rate assumption for the next week's first LT days.
5. **Review-queue design** (§7): case types and precedence, material triggers, holiday prioritisation, one case per decision point.
6. **Evidence and validation rules** (§2.4) and the non-causal uplift statement (§2.3).
7. **Acceptance criteria** AF1–AF6 and S1–S17 for the next implementation stage.
8. **Approval to implement** the assumption file (as `DRAFT`, then `APPROVED` by you) and the replay simulator. Still no inventory, waste or pricing engine, database, dashboard, Airtable or GitHub.
