# Step 5A: retail decision engine design (design only)

- **Status:** design only. Nothing has been implemented, and no database, table, Airtable connection or GitHub push was created. No model was retrained and no package installed. The legacy v1 scripts were read, not executed. **Approval is required before Step 5B.**
- **Date:** 2026-10-22
- **Forecast inputs** (unchanged; DECISIONS 13–22):
  - **H1:** Random Forest, S0, WAPE 25.92% (protected run `20261021-180522_rf_backtest`)
  - **H4:** four-week moving average, WAPE 29.41% (protected run `20261021-175029_baseline_backtest`)
  - The H4 CatBoost result (27.78%) is an exploratory finding only. It is not used here.

> **Standing caveats.**
> - The data is *apparently synthetic; provenance unconfirmed*. One year of weekly data (2024), 48 products, 15 stores.
> - Recorded price appears to be after discount (undocumented).
> - Wastage follows a fixed generator rule (⌊k_product × units⌋).
> - No price elasticity can be inferred from this data.
> - The engine designed here is **decision support with human approval**. It is not automated pricing and not price optimisation.

---

## 1. Purpose and principles

The goal is to turn forecasts into **transparent, auditable, human-approved recommendations** for ordering, waste risk and pricing actions, for each store × product × week.

| Principle | Meaning in practice |
|---|---|
| Provenance on every number | Each value carries a tag: OBSERVED, CALCULATED, ASSUMED or SYNTHETIC (section 3) |
| Rules, not optimisation | Recommendations come from explicit, versioned rules with reason codes. No claim of optimal prices; no elasticity. |
| As-of discipline | A decision for origin week *T* uses only data, forecasts and assumptions available at *T*. The same truncation and scrambling tests apply as for forecasting. |
| Human in the loop | Every price action and every escalation requires approval. Nothing is applied automatically. |
| Safe by construction | Hard limits (price floor, maximum discount, margin floor, change frequency) are enforced in code and tested. Violations are impossible, not just discouraged. |
| Honest demonstration | Missing operational inputs are replaced only by labelled synthetic scenarios. Results are presented as "what the mechanism does under these assumptions". |

---

## 2. What exists in V2 today

### 2.1 Datasets (`data/raw`, checksum-verified)

| Table | Rows | Fields | Grain |
|---|---|---|---|
| `weekly_sales` | 37,440 | Week_Number, Product_ID, Store_ID, Units_Sold (194–10,413), Marketing_Spend (100–1,973), Discount_Percent (0/5/10/15/20/25), Wastage_Units (6–1,541), Price (0.42–12.00) | store × product × week |
| `product_details` | 48 | Product_ID, Product_Name, Product_Category (4), Shelf_Life_Days (2–356), Supplier_ID | product |
| `store_info` | 15 | Store_ID, Region (6), Store_Size (3,000–12,000), Cold_Storage_Capacity (634–3,788) | store |
| `supplier_info` | 10 | Supplier_ID, Supplier_Name, Lead_Time_Days (1–3), Supply_Capacity (11,306–71,976) | supplier |
| `weather_data` | 364 | Week_Number, Region (7, incl. Wales), Avg_Temperature, Rainfall, Holiday_Flag | region × week |

### 2.2 Reusable V2 architecture

| Component | Use in Step 5 |
|---|---|
| Verified forecasting panel | The source of sales history and static attributes (protected run `20261021-171758_forecast_panel`) |
| `dpe.forecast.features`, `backtest` | As-of rules, origin and target definitions, fold boundaries |
| Protected out-of-sample forecasts, target weeks 29–52, both horizons | The **replay demonstration** input. No retraining is needed. |
| `dpe.config` write guard and checksum registry | All new outputs go to new run folders; protected paths stay blocked |
| `dpe.eda.outputs` guarded writers | Never overwrite |

### 2.3 Legacy v1 (read only, never executed)

- **`run_forecast.py`:** per-product average of all history, written to the original `pricing_system.db` with `if_exists="replace"`.
- **`run_pricing_engine.py`:** four rules comparing *per-product totals* with *row-level averages*, written with `if_exists="replace"`.
- **Verdict:** not reused. The v1 rule names ("Increase Price", "Reduce Supply", "Discount Price", "Keep Stable") are a useful vocabulary reference only.

---

## 3. Business-input inventory

Provenance categories:

| Tag | Meaning |
|---|---|
| **OBSERVED** | In the raw data |
| **CALCULATED** | Derived reproducibly from observed data or forecasts |
| **ASSUMED** | A business parameter that does not exist in the data. Needs a value, a unit, a rationale and your approval. |
| **SYNTHETIC** | A simulated demonstration input, never presented as real |

| Business input | Status | What exists | What the engine would use | Needed for a real deployment |
|---|---|---|---|---|
| **Current stock on hand** | **Missing** | Nothing | **SYNTHETIC**: simulated stock from a replay inventory simulator (section 6.4) | Daily or weekly stock positions per store × product |
| **Incoming deliveries** | **Missing** | Nothing | **SYNTHETIC**: generated by the simulated ordering policy | Purchase orders, delivery schedule and actual receipts |
| **Supplier lead times** | Observed (partial) | `Lead_Time_Days` 1–3 per **supplier** | **OBSERVED**. With weekly decisions and lead time < 7 days, an order placed at the end of week *T* is **assumed** to arrive before week *T* + 1 starts. | Lead time per supplier × store, with variability and delivery days |
| **Product shelf life** | Observed | `Shelf_Life_Days` 2–356 per product | **OBSERVED**. Bakery (2–5 days) and some Meat (3–7 days) expire **within a week**: no carry-over. | Shelf life on receipt (remaining life), per lot |
| **Actual expiry dates** | **Missing** | Nothing | **SYNTHETIC**: lot age tracked in the simulator, from arrival week and shelf life | Lot or batch expiry dates |
| **Purchase cost** | **Missing** | Nothing | **ASSUMED**: category gross-margin percentages applied to the reference price (e.g. a margin per category; values for approval) | Supplier cost per product |
| **Selling price** | Observed (ambiguous) | `Price` per row, apparently **post-discount**, with noise-like variation (CV ~39%) | **CALCULATED** *reference price* = median of the implied pre-discount price, Price / (1 − d), over weeks ≤ origin, per store × product | Shelf (list) price and promotion price, separately |
| **Gross margin** | **Missing** | Nothing | **CALCULATED from ASSUMED cost** | Actual cost and price |
| **Stock holding cost** | **Missing** | Nothing | **ASSUMED**: % of cost per week, by category | Finance-provided holding and storage cost |
| **Historical wastage** | Observed (generator rule) | `Wastage_Units` = ⌊k × units⌋ in 99.93% of rows | **Context only.** Shown as "dataset waste ratio k (artefact)". **Never used to validate waste predictions.** | Recorded waste and markdown by reason, per lot |
| **Minimum order quantities** | **Missing** | Nothing | **ASSUMED**: MOQ and case pack per category | Supplier MOQ, case size, order multiples |
| Supplier capacity | Observed (unit unknown) | `Supply_Capacity` 11,306–71,976 | Informational warning only; the unit is undocumented | Capacity per period with units |
| Cold storage | Observed (unit unknown) | `Cold_Storage_Capacity` 634–3,788 | Informational for Dairy/Meat; not enforced (unit unknown) | Capacity in units or m³ |
| Planned discounts, marketing | Historical only | Recorded values | Not used in S0 forecasts. A *proposed* discount is an engine **output**, not an input. | Promotion calendar |
| Holiday calendar | Observed for 2024 | Regional `Holiday_Flag` | **OBSERVED** for replay weeks; none exists beyond 2024-12-23 | Published calendar for future weeks |
| Stockouts and lost sales | **Missing** | Nothing | **Assumption:** recorded sales = demand. **They may be censored by stock, and we cannot tell.** | Stockout flags or availability data |
| Daily sales profile | **Missing** | Weekly totals only | **Assumption:** uniform within the week (affects within-week expiry) | Daily or hourly sales |

**Key consequence.** The data supports **forecasting sales and explaining recommendations**. It does **not** support real inventory, waste or margin outcomes. Those can only be demonstrated under explicit assumptions.

---

## 4. Forecast output contract (H1 and H4)

**Single table:** `forecast_contract` (CSV in a run folder; later the SQLite table `forecasts`). One row per run × model × horizon × store × product × origin.

| Field | Type | Rule |
|---|---|---|
| `forecast_run_id` | text | Run folder id; provenance |
| `model_name`, `model_role` | text | e.g. `random_forest` / `H1_research_candidate`; `mean_4w` / `H4_research_candidate` |
| `model_code_sha256`, `source_run_id` | text | The protected run the forecast came from |
| `horizon` | int | 1 or 4 |
| `scenario` | text | `S0` |
| `store_id`, `product_id` | int | Always present |
| `origin_week`, `origin_date`, `target_week`, `target_date` | int/date | `target_week = origin_week + horizon`; Monday dates |
| `point_forecast` | float ≥ 0 | Units for the target week |
| `p10`, `p50`, `p90` | float ≥ 0 | Monotone: p10 ≤ p50 ≤ p90 (section 4.1) |
| `uncertainty_method`, `uncertainty_window` | text | e.g. `empirical_ratio_quantiles`, `targets 9–28, H1, Bakery` |
| `flags` | JSON list | `CHRISTMAS_WEEK` (51–52), `HOLIDAY_WEEK`, `DISCOUNT_UNKNOWN_S0`, `UNCALIBRATED_UNCERTAINTY`, `MEAT_STEP_RISK` (H4, weeks 29–40), `COLD_START` |
| `status` | text | Always `RESEARCH_CANDIDATE_NOT_PRODUCTION` |
| `dataset_label` | text | "Apparently synthetic dataset; provenance unconfirmed" |

**Producer.** An adapter reads the protected CP4 (H1 RF) and CP3 (H4 mean_4w) predictions for target weeks 29–52. Nothing is retrained.

**Validation (contract tests):**
- unique key
- all fields present
- horizon in {1, 4}
- target = origin + horizon
- forecasts finite and ≥ 0
- quantiles monotone
- reproducible within 1e-6 (DECISION 16)
- every row carries the dataset label and status

### 4.1 Uncertainty (as-of, no retraining)

Empirical quantiles of the ratio actual / forecast, by **category × horizon × model**:
- **Calibration window:** only target weeks **≤ the origin** whose actuals are already known.
  - For H1 RF: the earlier backtest folds.
  - For H4 mean_4w: every earlier eligible week, because a moving average needs no training.
- **First RF fold (F1):** no earlier out-of-sample RF residuals exist. It uses the mean_4w ratio distribution, widened by 10%, flagged `UNCALIBRATED_UNCERTAINTY`.
- **Calibration test:** empirical p10–p90 coverage on later folds, reported pooled and by category (section 10).

---

## 5. Decision engine overview (weekly cycle at origin week *T*)

```
forecast_contract (H1, H4) ─┐
assumption set (approved) ──┼─► inventory planner ─► waste-risk module ─► recommendation rules ─► safety controls ─► review queue
stock state (synthetic) ────┘        (order qty,         (expiring           (actions, reasons,     (floors, caps,      (human approval,
reference price (calculated)          stockout risk)      surplus)            explanation)           escalation)         audit trail)
```

**Grain:** store × product × decision week.

**Output:** one **recommendation record** with one primary action, optional secondary actions, reason codes, an explanation, the inputs snapshot, provenance tags and an approval status.

---

## 6. Inventory planning module

### 6.1 Policy
- **Type:** periodic review, order-up-to (*R*, *S*), weekly review (*R* = 1 week).
- **Lead time:** assumed less than one week, from the observed 1–3 days.

### 6.2 Quantities

| Quantity | Definition | Tag |
|---|---|---|
| Demand distribution for *T* + 1 | H1 point forecast with p10, p50, p90 | CALCULATED |
| Target level *S* | Forecast quantile at the target service level *z* (e.g. p80 or p90, by category; approval) | ASSUMED parameter, CALCULATED value |
| Order quantity | max(0, *S* − usable stock at the start of *T* + 1), rounded **up** to the case pack and ≥ MOQ | CALCULATED from ASSUMED pack and MOQ |
| Usable stock | On-hand lots whose remaining shelf life covers at least part of week *T* + 1 | SYNTHETIC in the demo |
| Stockout risk | P(demand > available) from the empirical forecast distribution | CALCULATED |
| Days of cover | usable stock / (forecast / 7) | CALCULATED |
| H4 role | Forward-looking signal: if H4 differs from H1 by more than a threshold, flag `TREND_DIVERGENCE` for ordering review. Also a supplier-capacity check (informational; unit unknown). | CALCULATED |

### 6.3 Shelf-life rules (weekly grain)
- **Shelf life < 7 days:** no carry-over. Stock not sold within the week expires.
- **Shelf life ≥ 7 days:** carry over by lots, first-in-first-out, until their age exceeds the shelf life.

### 6.4 Replay simulator (synthetic, demonstration only)
- **Start:** stock at week 28 = the order-up-to level.
- **Each week:**
  1. receive the order
  2. sell min(actual units, available), oldest lots first
  3. expire overdue lots
  4. record simulated on-hand, stockout and expired units
- **Always labelled SYNTHETIC.** Recorded sales are treated as demand (the censoring assumption).

---

## 7. Waste-risk module

- **Projected expiring surplus:** units expected to remain unsold at expiry, from usable stock, planned orders and the forecast distribution. Expected value plus a p90 case.
- **Risk bands:**

  | Band | Projected expiring surplus |
  |---|---|
  | LOW | < 5% of expected sales |
  | MEDIUM | 5–15% |
  | HIGH | > 15% |

  The thresholds are assumed and need approval.
- **Context only:** the dataset waste ratio *k* is displayed and labelled *"generator rule in this dataset; not a validated waste model"*.
- **Explicit statement in the module and dashboard:** historical wastage follows synthetic generator rules. It cannot validate real-world waste predictions. Simulated waste in the replay is an outcome of the stated assumptions, not a forecast of real waste.

---

## 8. Recommendation engine (rule-based; no optimisation claims)

### 8.1 Actions and triggers

| Action | Trigger (all thresholds ASSUMED, versioned, approval) | Primary reason codes |
|---|---|---|
| **MAINTAIN_PRICE** | Default: no other rule fires; stockout risk and waste risk are both within bands | `WITHIN_BANDS` |
| **CONSIDER_CONTROLLED_DISCOUNT** | Waste risk HIGH, shelf life < 7 days or lots near expiry, stockout risk low, and the discounted price stays ≥ the price floor. Proposed level is the smallest step in {5, 10, 15, 20, 25}% that brings projected surplus into the MEDIUM band under the **uplift assumption** (8.2). Capped by the safety controls. | `EXPIRING_SURPLUS`, `SHORT_SHELF_LIFE`, `UPLIFT_ASSUMPTION` |
| **REPLENISH** | Stockout risk > threshold (e.g. 20%) for *T* + 1. Recommends the order quantity from 6.2. | `STOCKOUT_RISK`, `BELOW_TARGET_LEVEL` |
| **REDUCE_FUTURE_ORDERING** | Waste risk MEDIUM or HIGH in ≥ 2 of the last 3 decision weeks, or usable stock > *S* by a margin. Recommends lowering the service level or target for that item. | `PERSISTENT_SURPLUS` |
| **INVESTIGATE_SHORTAGE** | Simulated stockout in the last week (sales hit availability), or actual > p90 in ≥ 2 of the last 3 weeks, or H4 is well above the H1 trend | `DEMAND_ABOVE_RANGE`, `POSSIBLE_CENSORED_SALES`, `TREND_DIVERGENCE` |
| **ESCALATE_HUMAN_REVIEW** | Any low-confidence condition: Christmas weeks 51–52; holiday target week; `UNCALIBRATED_UNCERTAINTY`; `MEAT_STEP_RISK`; a proposed discount ≥ 20%; conflicting actions (e.g. discount and replenish); margin floor binding; data-quality failure | `LOW_CONFIDENCE_PERIOD`, `CONFLICT`, `SAFETY_LIMIT_BINDING`, `DATA_QUALITY` |

### 8.2 Uplift assumption (for discount proposals only)
- **Default:** the EDA conditional association of about +1.6% units per discount point (log scale), shown with a **range of 50–150%** of that value.
- **Labelled:** *"assumption from a non-causal association in apparently synthetic data; not an elasticity"*.
- **Range check:** the recommendation is only made if it still keeps the price ≥ floor and reduces surplus at the **low** end of the range.

### 8.3 Combining actions
**Conflict resolution order:**
1. Safety and escalation
2. INVESTIGATE_SHORTAGE / REPLENISH
3. CONSIDER_CONTROLLED_DISCOUNT
4. REDUCE_FUTURE_ORDERING
5. MAINTAIN_PRICE

The first applicable action is primary; others are secondary. **A discount is never combined with a replenish signal without escalation.**

### 8.4 Explanation
Every record has:
- reason codes
- a plain-English explanation built from a template (e.g. *"Projected 22% of stock to expire before sale (shelf life 2 days); a 10% markdown is estimated (assumption range 0.8×–2.4× uplift) to reduce this to 9%; price stays above floor £1.24."*)
- the inputs snapshot (forecast, quantiles, stock, reference price, floor)
- the assumption set id
- provenance tags

---

## 9. Safety controls

All are enforced in code, versioned in the assumption set, tested, and logged when binding.

| Control | Rule |
|---|---|
| Price floor | proposed price ≥ max(cost × (1 + minimum margin), absolute floor). Cost is ASSUMED, so the floor is labelled "assumption-based". |
| Margin protection | Proposed gross margin ≥ the category minimum (ASSUMED). If binding, the action is downgraded to ESCALATE. |
| Maximum discount | ≤ 25% (the largest observed level). Configurable lower, never higher without approval. |
| Change frequency | At most one price recommendation per store × product per week. No discount on items flagged REPLENISH or INVESTIGATE_SHORTAGE. |
| Inventory constraints | Order ≥ MOQ and a multiple of the case pack. Supplier capacity and cold storage are informational only (unknown units). |
| No automatic execution | `requires_approval = TRUE` for every price action and every escalation. Status starts as `PENDING`. |
| Approval | A named reviewer records approve or reject with a comment. Only `APPROVED` records can be exported to downstream systems. |
| Audit trail | Append-only log of every run, recommendation, approval and export: actor, timestamp, payload hash. Updates and deletes are blocked. |
| Kill switch | A single configuration flag disables all price recommendations (inventory-only mode) |
| Provenance gate | Any recommendation relying on SYNTHETIC inputs is watermarked `DEMONSTRATION – SYNTHETIC INPUTS` in every output |

---

## 10. Acceptance tests (measurable)

| Area | Test | Pass criterion |
|---|---|---|
| Contract | Schema, keys, horizons, target = origin + h, ≥ 0, monotone quantiles, labels | 100% of rows valid; any violation fails the run |
| As-of decisions | Truncation and future-scrambling tests on the engine (as for features) | Identical decisions at origin *T* |
| Uncertainty | Empirical p10–p90 coverage on replay weeks with calibrated windows | Pooled coverage 70–90% per horizon (target 80%); per-category coverage reported. Outside the range: flagged, and the uncertainty method needs review. |
| Safety (property tests) | Randomised inputs and edge cases | **0** recommendations below the floor, above the maximum discount, below the margin floor, or with more than one price change per item-week |
| Approval | Every price action and escalation | `requires_approval = TRUE`, status `PENDING`, never auto-applied |
| Explainability | Every record | Non-empty reason codes, explanation, assumption-set id and provenance tags |
| Determinism | Same inputs and assumption set | Identical outputs (byte-identical CSV) |
| Escalation coverage | Weeks 51–52, holiday weeks, uncalibrated rows | 100% escalated |
| Audit | Attempted update or delete on the audit log | Rejected; all runs logged |
| Path safety | Writes | Only new V2 run folders and (later) the new V2 database. The original `pricing_system.db` path is blocked by the write guard. |
| Replay demo | Weeks 30–52, synthetic stock | KPIs computed and labelled synthetic. The simulated fill rate must be within 5 points of the configured service level (internal consistency), otherwise it is investigated. |

---

## 11. V2 SQLite schema (design only; nothing created)

**File:** `dynamic-pricing-engine-v2/database/dpe_v2.sqlite`. It is **new**, and separate from the original `dynamic-pricing-engine/database/pricing_system.db`, which is never opened. Created by a migration script with `PRAGMA foreign_keys = ON`. **Append-only by `run_id`. No `DROP` or `if_exists="replace"`.**

| Table | Key columns | Purpose |
|---|---|---|
| `run_registry` | `run_id` PK, run_type, created_at, code_sha256, input_hashes_json, parameters_json, dataset_label, status | Every pipeline run |
| `dim_product` | `product_id` PK, name, category, shelf_life_days, supplier_id FK, provenance | Observed attributes |
| `dim_store` | `store_id` PK, region, store_size, cold_storage_capacity, provenance | Observed attributes |
| `dim_supplier` | `supplier_id` PK, name, lead_time_days, supply_capacity, provenance | Observed attributes |
| `assumption_sets` | `assumption_set_id` PK, created_at, approved_by, approved_at, status | Versioned parameter sets |
| `assumptions` | (`assumption_set_id`, key) PK, value, unit, scope (global/category/product), provenance ∈ {ASSUMED, SYNTHETIC}, rationale | Every non-observed parameter |
| `forecasts` | `forecast_id` PK; UNIQUE (run_id, model_name, horizon, store_id, product_id, origin_week); point_forecast, p10, p50, p90, flags_json, status, source_run_id | The forecast contract |
| `inventory_state` | (run_id, store_id, product_id, week) PK, on_hand, on_order, lots_json, stockout_units, expired_units, provenance = SYNTHETIC | Simulator state |
| `inventory_plans` | `plan_id` PK, run_id, store_id, product_id, decision_week, target_level, order_qty, service_level, stockout_risk, days_of_cover | Planner output |
| `waste_risk` | `risk_id` PK, run_id, store_id, product_id, decision_week, projected_expiring_units, p90_expiring_units, risk_band, method_label | Waste-risk output |
| `recommendations` | `rec_id` PK, run_id, store_id, product_id, decision_week, primary_action (CHECK in the six actions), secondary_actions_json, reference_price, proposed_price, proposed_discount_pct, price_floor, reason_codes_json, explanation, inputs_snapshot_json, assumption_set_id FK, confidence, requires_approval, status (CHECK PENDING/APPROVED/REJECTED/EXPIRED), created_at | Decisions for review |
| `approvals` | `approval_id` PK, rec_id FK, decision, reviewer, decided_at, comment | Human decisions |
| `audit_log` | `event_id` PK autoincrement, ts, actor, event_type, entity, entity_id, payload_sha256, payload_json | Append-only. Triggers raise on UPDATE and DELETE. |
| `export_log` | `export_id` PK, rec_id FK, target (`airtable_sandbox`/`csv`), dry_run, status, ts | Outbound traffic |

**Constraints:**
- CHECK proposed_discount_pct between 0 and 25
- CHECK proposed_price ≥ price_floor when not null
- CHECK quantiles are monotone
- A trigger allows `recommendations.status` to change only through an `approvals` insert

---

## 12. Dashboard and Airtable (outline)

**Dashboard** (Step 5D). Recommended first version: a **static, read-only HTML report** generated from SQLite with the already-installed `matplotlib`. No new package; an interactive framework can be decided later.

| Page | Content |
|---|---|
| Overview | Data caveats banner (synthetic, research candidates, not production); run id; assumption-set id |
| Forecasts | H1 and H4 per store and product, with p10–p90; flags |
| Inventory | Order recommendations, stockout risk, days of cover (SYNTHETIC watermark) |
| Waste risk | Bands and projected surplus (watermarked, with the generator-rule statement) |
| Recommendations | Queue sorted by priority, with action, reasons, explanation, proposed price vs floor, and status |
| Audit | Recent runs, approvals and exports |

**Airtable** (Step 5E, after approval):
- **Direction:** one-way push of `PENDING` recommendations to a **designated sandbox base**. Approval decisions are pulled back into `approvals`.
- **Order:** dry-run CSV export first. The live push needs explicit approval for each run.
- **Credentials:** from environment variables only. The legacy `run_pricing_to_airtable.py` held a hard-coded credential and was not copied.
- **Watermark:** synthetic-input records are labelled in Airtable.
- **Logging:** every push goes to `export_log` and `audit_log`.
- **Tests:** no network access; the export is mocked.

**GitHub** (Step 5F): only after the `.gitignore` review (DECISION 3), a secrets scan, and a decision on whether data and outputs are excluded.

---

## 13. Staged implementation plan (each stage stops for review)

| Stage | Scope | Output | Tests |
|---|---|---|---|
| **5B-1** | Forecast contract adapter from protected runs; as-of empirical quantiles; flags | `forecast_contract.csv` in a new run folder | Contract validation, as-of uncertainty, coverage report |
| **5B-2** | Assumption registry (YAML or JSON, versioned) and provenance tagging; replay inventory simulator | Assumption set file; simulator module | Provenance on every field; simulator conservation (stock in = sold + expired + on hand) |
| **5B-3** | Inventory planner (order-up-to, MOQ and pack, stockout risk, days of cover) | `inventory_plans.csv` | Order rules, rounding, shelf-life carry-over, determinism |
| **5B-4** | Waste-risk module | `waste_risk.csv` | Bands, labels, "not a validated waste model" statement present |
| **5B-5** | Recommendation rules and safety controls | `recommendations.csv` (all PENDING) | Property tests (floors, caps, frequency), escalation coverage, explanations |
| **5B-6** | Replay demonstration, weeks 30–52, synthetic stock | Replay report: KPIs labelled SYNTHETIC | Consistency checks; truncation and scrambling at decision level |
| **5C** | Create the new V2 SQLite database and load the 5B outputs | `database/dpe_v2.sqlite` | Schema, constraints, triggers, path guard |
| **5D** | Static dashboard | HTML report in a run folder | Read-only; banner present; values match SQLite |
| **5E** | Airtable sandbox (dry run, then live with approval) | Export log | Mocked tests; credentials from environment variables only |
| **5F** | GitHub | Repository | `.gitignore`, secrets scan, approval |

No stage after 5B-6 starts without your approval.

---

## 14. Honest demonstration strategy

1. **Replay, not a fake future.** The demonstration runs over decision weeks 29–52 using the **out-of-sample** forecasts already produced and protected. Real recorded sales act as "what happened next".
2. **Synthetic inputs only where data is missing.** Stock, deliveries, lots and expiry are simulated. Cost, holding cost, MOQ, case packs and service levels come from one named, approved assumption set. Every such value is tagged and watermarked.
3. **Scenario comparison, not claims.** The replay compares the engine's ordering rules with a naive rule (order = last week's sales) under the **same** assumptions.
   - **Reported:** simulated fill rate, simulated expired units, simulated stockout weeks.
   - **Wording:** *"under these assumptions, the mechanism behaves as follows"*. Never *"reduces waste by X%"*.
4. **Sensitivity.** Key assumptions (service level, uplift range, margin) are varied over stated ranges, to show which conclusions are robust.
5. **Known blind spots shown, not hidden.** Christmas weeks, discount weeks and the Meat step-up appear as escalations with reasons.

**What it can demonstrate:**
- an auditable end-to-end workflow from data to forecast, plan, recommendation, approval and audit
- consistent, explainable decisions
- quantified forecast uncertainty
- safety limits that cannot be breached
- trade-offs between service level and simulated waste under transparent assumptions
- a prioritised human review queue

**What it cannot demonstrate:** real waste reduction, real revenue or margin gains, optimal prices, or price elasticity.

---

## 15. Decisions requiring your approval before implementation

1. **Scope and order:** stages 5B-1 to 5B-6 as section 13, each with a review stop.
2. **Assumption set v1:** category gross-margin %, minimum margin, holding cost %, MOQ and case packs, service levels (e.g. p80/p90 by category), waste-risk band thresholds, the uplift assumption and its range, maximum discount (25%), escalation thresholds. I will propose values with rationale at 5B-2 for your sign-off.
3. **Core modelling assumptions:**
   - lead time < 1 week, so orders arrive before the next week
   - recorded sales treated as demand (possible censoring acknowledged)
   - uniform within-week sales
   - no carry-over for shelf life < 7 days
4. **Reference price definition:** the median implied pre-discount price as of the origin.
5. **Uncertainty method:** as-of empirical ratio quantiles, with the F1 fallback flagged.
6. **Replay demonstration:** decision weeks 29–52, with the synthetic simulator and the naive comparison policy.
7. **Database:** the new file `database/dpe_v2.sqlite`, with the schema in section 11.
8. **Dashboard technology:** static HTML first, no new packages.
9. **Airtable and GitHub:** sandbox-only, dry run first, environment-variable credentials; GitHub after the `.gitignore` and secrets review. Both later, each with explicit approval.
