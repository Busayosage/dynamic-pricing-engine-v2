# Step 4A: forecasting improvement design and leakage audit

- **Status:** design only. No forecasting code has been written or changed and no model has been trained. **Approval is required before Step 4B.**
- **Date:** 2026-10-21
- **Inputs reviewed:**
  - `src/dpe/reference_baseline.py`
  - `legacy/perishable_project/src/baseline_model.py` (reference copy)
  - `outputs/runs/20261021-133846_reference_rf/` (manifest, metrics, predictions)
  - `docs/STEP_3B_REPRODUCTION.md`
  - `docs/EDA_FINDINGS.md`
  - `tests/test_reference_features.py`

> **Standing caveats.** The dataset is *apparently synthetic; provenance unconfirmed*. It covers one year (52 weeks, 2024), 48 products and 15 stores. Results will describe this dataset only. Recorded `Price` appears to be after discount, but this is undocumented. Wastage is a fixed product ratio of units sold (EDA_FINDINGS §3.2).

---

## 1. Summary

- **The reference Random Forest is reproduced exactly**: WAPE 27.9%, MAE 487.2, against the naive model's 34.2%. However, it **is not a deployable forecast.** It reads the target week's own price, discount, marketing spend and actual weather, and it is scored on a single 8-week window.
- **The improved design separates three things:**
  1. **What is known at the moment a forecast is made.** This is the "as-of" principle: every feature is computed only from data dated on or before the forecast origin.
  2. **Two horizons:** one week ahead and four weeks ahead.
  3. **Scenarios for commercial plans.** Future discounts, marketing and prices are used only in clearly labelled scenarios that assume they are supplied as plans.
- **Evaluation:** six 4-week rolling backtest folds covering weeks 29–52. All models are scored on identical rows. The acceptance gates are set in advance.
- **Expectation.** The deployable model will very likely score worse than the reference's 27.9%, because the reference was helped by information it would not have in practice. That is the honest number to beat. The reference result is kept only as context.

---

## 2. Review of the reference implementation

| Item | Reference behaviour |
|---|---|
| Rows | 37,440 raw rows. The first 8 weeks of every series are dropped because lag 8 is missing, leaving 31,680. |
| Split | Train on targets 2024-02-26 to 2024-10-28 (25,920 rows); validate on 2024-11-04 to 2024-12-23 (5,760 rows). |
| Model | `RandomForestRegressor(n_estimators=300, max_depth=12, random_state=42)`, fitted once |
| Features | 105: same-week price, discount, marketing, temperature, rainfall and holiday; `lag_1/2/4/8`, `roll_mean_4/8`, `roll_std_4`; week of year, month, quarter; 47 product dummies, 3 category dummies; numeric `Supplier_ID`, `Store_Size`, `Cold_Storage_Capacity`, `Shelf_Life_Days`; **35 `Week_Number_wx` dummies** |
| Excluded | Target, `WeekDate`, same-week `Wastage_Units`, `Store_ID`, `Product_ID`, `Region` |
| Validation WAPE by week (RF) | 24.4–26.4% for 4 Nov to 9 Dec, then **34.1% (16 Dec) and 33.0% (23 Dec)** |
| Validation WAPE by week (naive) | 32.9–36.4% in every week, which points to large week-to-week noise |

---

## 3. Leakage and deployment audit of every reference feature

Category key:
- **TL** = target leakage
- **FI** = future information (not known at forecast time)
- **DA** = unrealistic deployment assumption
- **EV** = evaluation-design weakness

| Feature(s) | Verdict | Finding | Treatment in Step 4B |
|---|---|---|---|
| `Wastage_Units` (same week) | **TL, correctly excluded** | Wastage = ⌊k × units⌋ of the same week, so it is effectively the target. | Keep excluded at every lag: lagged wastage only restates lagged units. A test asserts it never appears. |
| `Price` (target week) | **FI** | Not known in advance unless a price plan exists. It also appears to embed the discount (Price ≈ base × (1 − d)). | Scenario S2 only, as a planned price |
| `Discount_Percent` (target week) | **FI** | The strongest demand association in the data (+0.016 log units per point). Unknown at forecast time without a promotion plan. | Scenarios S1/S2 only, as a planned discount |
| `Marketing_Spend` (target week) | **FI** | Same issue | Scenario S2 only, as planned spend |
| `Avg_Temperature`, `Rainfall` (target week) | **FI** | Recorded actuals, not forecasts. The EDA shows they add almost nothing beyond the season (month-adjusted ρ ≈ −0.01). | Scenario S3 only: a labelled, non-deployable "weather oracle" diagnostic |
| `Holiday_Flag` (target week) | **DA (acceptable with assumption)** | Holiday calendars are normally known in advance. Here the flag is sourced from the weather file and varies by region (2 weeks cover all 6 regions, 8 cover only some). | Allowed in all scenarios as a **known calendar input**. The assumption is recorded in the manifest. |
| `lag_1`, `lag_2`, `lag_4`, `lag_8` | OK for h = 1 only | Built with `groupby().shift()` and verified by tests. For h = 4, `lag_1`–`lag_3` of the target week are **not yet observed**. | Rebuilt relative to the forecast **origin**, not the target week (section 6) |
| `roll_mean_4/8`, `roll_std_4` | OK for h = 1 only | `shift(1).rolling()` correctly excludes the target week. For h = 4 the window overlaps unobserved weeks. | Anchored at the origin (section 6) |
| `weekofyear`, `month`, `quarter` | DA / EV | Deterministic, so not leakage. But with one year, validation weeks 45–52 never appear in training, so trees treat them as the largest week seen (44). | Keep target-week `month` and holiday calendar. **Drop `weekofyear`** (it cannot generalise from one year) and `quarter` (redundant with month). |
| `Week_Number_wx_*` (35 dummies) | **EV (serious)** | An artefact of the weather join: one dummy per *training* week (W10–W44; W09 is the dropped base). Every validation row has all 35 set to 0, so the model treats **every validation week as if it were week 9**. | Drop |
| `Product_Name_*`, `Product_Category_*` dummies | OK | Static attributes | Keep (product identity as one-hot; category) |
| `Supplier_ID` (numeric) | DA (minor) | An arbitrary code used as a number | Replace with `Lead_Time_Days` (static). Supplier identity is already implied by product. |
| `Store_Size`, `Cold_Storage_Capacity`, `Shelf_Life_Days` | OK | Static | Keep. Add `Store_ID` one-hot and `Region`; static identity is not leakage. |
| Validation `lag_1` inside the window | OK (stated assumption) | One-step rolling forecasts use last week's actuals as they arrive. That is realistic for weekly re-forecasting. | Kept for h = 1. The model is not refitted inside a fold. |
| `fillna(0.0)` on features | DA (latent) | Masks missing history as zero sales. It has no effect today because rows without lags are dropped first. | Replace with explicit exclusion plus a test (section 8) |
| Single 8-week holdout | **EV** | One window, which contains the two Christmas weeks that never occur in training. | Six-fold rolling backtest (section 7) |
| Fixed hyperparameters | OK | Not tuned on validation | Kept fixed in 4B. Any later tuning uses only inner training weeks. |

**Conclusion.** No target leakage was found. **Four future-information inputs** (price, discount, marketing, weather), **one serious encoding artefact** (`Week_Number_wx`) and **one evaluation weakness** (single window) make the reference result unsuitable as a deployable benchmark.

---

## 4. Forecast definitions

- **Grain:** one forecast per store × product × target week (720 series).
- **Origin week *T*:** the last week whose sales are fully observed when the forecast is made.
- **Horizon *h*:** the target week is *t* = *T* + *h*.
  - **Pipeline H1:** *h* = 1, the next-week forecast for replenishment.
  - **Pipeline H4:** *h* = 4, a four-week-ahead forecast for ordering and promotion planning.
- **Strategy: direct.** Each horizon has its own model, trained on (features at *o*, actual at *o* + *h*) pairs. **No recursive use of the model's own predictions**, so H4 never feeds predicted weeks *T* + 1 to *T* + 3 back in as if they were actuals.
- **Output:** non-negative point forecast of units sold (predictions are clipped at 0), plus keys, origin, horizon, scenario, fold and model name.

---

## 5. What is available at each prediction date

| Information | Available at origin *T* for target *T* + *h*? | Used in |
|---|---|---|
| Units sold, weeks ≤ *T* | Yes | All |
| Units sold, weeks *T* + 1 … *T* + *h* | **No** | Never |
| Wastage, any week | Observable for weeks ≤ *T*, but redundant (deterministic from units) | Never |
| Price / discount / marketing, weeks ≤ *T* | Yes (history) | All, as history-context features |
| Discount plan for *T* + *h* | Only if a promotion plan is supplied | S1, S2 |
| Price and marketing plan for *T* + *h* | Only if a commercial plan is supplied | S2 |
| Weather, weeks ≤ *T* | Yes, but not useful beyond season (EDA) | Not used |
| Weather for *T* + *h* | **No** (no forecasts in the data) | S3 diagnostic only (actuals used as a perfect forecast) |
| Holiday calendar for *T* + *h* (by region) | Yes, as a known calendar (assumption) | All |
| Calendar month of *T* + *h* | Yes (deterministic) | All |
| Product, store, supplier attributes | Yes (static) | All |

### Scenarios (explicit, never mixed)

| ID | Name | Target-week inputs beyond history and calendar | Deployable? | Purpose |
|---|---|---|---|---|
| **S0** | No plans | none | **Yes** | Primary forecast; acceptance is judged here |
| **S1** | Promotion plan known | `Discount_Percent` | Yes, *if* a discount plan exists | Value of knowing planned discounts |
| **S2** | Full commercial plan | S1 + `Marketing_Spend`, recorded `Price` (as planned price) | Yes, *if* all plans exist | Upper bound with plans. The EDA expects no gain from base price. |
| **S3** | Weather oracle (diagnostic) | S2 + actual `Avg_Temperature`, `Rainfall` | **No** | Measures how much actual-weather information helped the reference. Never eligible for acceptance. |
| **R0** | Reference replica (diagnostic) | The reference's 105 features, h = 1 only | **No** | Places the 27.9% reference on the new backtest folds for comparison |

---

## 6. Proposed leakage-safe features (identical definitions for H1 and H4, anchored at origin *T*)

Notation: *y*ₛ is units sold in week *s* for the series.

| Group | Features | Notes |
|---|---|---|
| Recent sales | *y*_T, *y*_{T−1}, *y*_{T−2}, *y*_{T−3}, *y*_{T−7} | For H1 these equal the reference `lag_1/2/3/4/8`. For H4 they correspond to lags 4/5/6/7/11 of the target. |
| Rolling statistics | mean, std, min and max over weeks *T*−3…*T* and *T*−7…*T*; exponentially weighted mean (α = 0.3) up to *T* | Every window ends at *T* |
| Trend / momentum | mean(*T*−3…*T*) − mean(*T*−7…*T*−4); *y*_T / mean(*T*−7…*T*) | |
| Series level | Expanding mean of the series up to *T* | Uses all history ≤ *T* only |
| Promotion-adjusted history | Discount at *T* and *T*−1; share of weeks *T*−3…*T* discounted; mean units in **undiscounted** weeks within *T*−7…*T* (falls back to the 8-week mean if none) | Discounted weeks inflate recent sales; the model needs to know |
| Holiday-adjusted history | Holiday flag at *T* (series' region) | The same for a holiday-inflated *y*_T |
| Hierarchy (as of *T*) | Product total across all stores: value at *T* and 4-week mean; store × category 4-week mean; series share of product (8-week) | Computed only from rows dated ≤ *T* |
| Static | Product one-hot, category, shelf life, store one-hot, region, store size, cold storage, supplier lead time | |
| Target-week calendar | Month of *T* + *h*; holiday flag of *T* + *h* for the series' region; national-holiday indicator (share of regions flagged = 1) | Known calendar (assumption) |
| Scenario inputs | S1: discount at *T* + *h*. S2: + marketing and price at *T* + *h*. S3: + temperature and rainfall at *T* + *h*. | Added only in the named scenario |

**Deliberately excluded:**
- Wastage at any lag (redundant and target-derived).
- Week of year (one year only).
- `Week_Number_wx` dummies.
- Same-week-last-year sales (not available).
- Learned Christmas or event flags. The run-up weeks 50–52 never appear in any training fold, so no model can learn them; see section 10.

**Encodings.** One-hot only, built from the fixed product and store lists. No target encoding is used, so no fold statistics can leak from test weeks.

---

## 7. Rolling backtest design

### 7.1 Folds (blocks of target weeks)

Week *n* is the *n*-th Monday of 2024: week 1 = 1 Jan, week 29 = 15 Jul, week 52 = 23 Dec.

| Fold | Target weeks | Dates | Notes |
|---|---|---|---|
| F1 | 29–32 | 15 Jul – 5 Aug | |
| F2 | 33–36 | 12 Aug – 2 Sep | Contains the w35 holiday |
| F3 | 37–40 | 9 Sep – 30 Sep | |
| F4 | 41–44 | 7 Oct – 28 Oct | |
| F5 | 45–48 | 4 Nov – 25 Nov | First half of the reference window |
| F6 | 49–52 | 2 Dec – 23 Dec | Christmas run-up; national holiday w52 |

F5 + F6 together equal the reference validation window and are also reported as "reference window".

### 7.2 Training cut-off per fold and horizon

For fold block [*b*, *b* + 3] and horizon *h*:
- **Earliest origin in the block:** *T*_min = *b* − *h*.
- **Training pairs:** all (*o*, *o* + *h*) with *o* ≥ 8 (full history) and *o* + *h* ≤ *T*_min. Every training target has been observed by *T*_min.
- **Test rows:** each target *t* in the block, using origin *t* − *h*. Features are computed from data ≤ *t* − *h*.
- **No refitting inside the block.** For H1, later origins in the block use newly observed actuals as inputs, which is realistic weekly re-forecasting. For H4 all origins lie between *T*_min and *b* − 1.

Training-set sizes:

| Fold | H1 training targets | H4 training targets |
|---|---|---|
| F1 | weeks 9–28 (14,400 rows) | weeks 12–25 (10,080 rows) |
| F6 | weeks 9–48 (28,800 rows) | weeks 12–45 (24,480 rows) |

### 7.3 Identical observations

- In each fold and horizon, every model predicts **the same 2,880 rows** (720 series × 4 target weeks). The pipeline asserts identical key sets before scoring.
- H1 and H4 are scored on the **same target weeks**, so the two horizons are directly comparable.
- **Total per horizon:** 17,280 scored rows across 6 folds.

### 7.4 Models compared

| Model | Definition |
|---|---|
| Naive | ŷ = *y*_T (last observed week). For H1 this reproduces the reference naive exactly; a continuity test checks weeks 45–52 against `validation_predictions.csv`. |
| 4-week average | ŷ = mean(*y*_{T−3} … *y*_T) |
| RF-S0, RF-S1, RF-S2 | Random Forest on section 6 features per scenario, with the reference hyperparameters (300 trees, depth 12, seed 42) |
| RF-S3 | Diagnostic only |
| R0 | Reference replica (H1 diagnostic only) |

About 54 model fits in total; well within the run time of a laptop.

---

## 8. Insufficient lag history and four-week-ahead leakage

**Insufficient history:**
- A row is eligible only if its origin has **8 observed weeks** (*T* ≥ 8). Weeks 1–8 serve only as history.
- The first trainable target is **week 9 for H1** and **week 12 for H4**.
- **No zero-filling or imputation** of missing lags. The reference `fillna(0.0)` is not reused; a test asserts that no eligible row has a missing history feature.
- Baselines are scored on exactly the same eligible rows.
- **Deployment cold start** (not present in this data; documented only). A series with fewer than 8 observed weeks gets the mean of its available weeks, scaled by the product's store share, or the store × category mean if there are none. Such forecasts are flagged `cold_start = True` and excluded from model metrics.

**Four-week-ahead leakage controls:**
1. Every H4 feature is computed from data ≤ *T*. No feature is defined relative to the target week, so weeks *T* + 1 … *T* + 3 are unreachable by construction.
2. Training pairs require *o* + 4 ≤ *T*_min. A training target is never later than the forecast origin of the first test row.
3. There is no recursion, so unobserved weeks are never replaced by predictions.
4. Hierarchical aggregates (product totals and the like) are recomputed **as of each origin**, never from the full panel.
5. Scenario inputs for *T* + 4 (plans) are attached only in S1–S3 and only for the target week.

**Leakage tests** (part of 4B, all must pass):

| Test | What it proves |
|---|---|
| Truncation invariance | Features at origin *T* computed from the full panel equal those computed from the panel truncated after *T*, for sampled origins and both horizons |
| Future perturbation | Multiplying every value after *T* by 10 leaves S0 features and predictions at *T* unchanged. In S1, only the planned target-week discount may change. |
| Lag alignment | On a synthetic panel with *y* = week index, *y*_T equals target − *h*, for H1 and H4 |
| Training cut-off | In every fold, max(training target week) ≤ *T*_min and max(training origin) ≤ *T*_min − *h* |
| Feature whitelist | S0 contains no target-week price, discount, marketing or weather column. No wastage column exists in any scenario. No `Week_Number_wx` or week-of-year column. |
| Minimum history | No eligible row has origin < 8; no missing history feature; no zero-filled lags |
| Identical evaluation rows | All models share identical keys per fold and horizon; H1 and H4 share target weeks |
| Naive continuity | H1 naive equals the reference `pred_naive` for weeks 45–52 (max diff 0) |
| Reproducibility | Two runs with the same seed give identical predictions |

---

## 9. Metrics and reporting

For each model × scenario × horizon, the following are reported per fold, pooled, and for the reference window:

| Metric | Formula |
|---|---|
| MAE | mean |ŷ − *y*| |
| RMSE | √mean (ŷ − *y*)² |
| WAPE | Σ|ŷ − *y*| / Σ*y* (primary metric) |
| Bias | Σ(ŷ − *y*) / Σ*y* (negative = under-forecast) |
| R² | For continuity with the reference only |

**Breakdowns** (pooled across folds, per horizon):
- by category (4)
- by store (15)
- by region (6; flagged when n < 3 stores)
- by target-week discount status
- by target-week holiday status
- by fold

**Uncertainty.** A week-level bootstrap (2,000 resamples of the 24 target weeks) gives a 95% interval for the WAPE difference between RF-S0 and the best baseline. Fold-to-fold standard deviation of WAPE is also reported.

**Charts** (in the run folder):
- WAPE by fold per model
- bias by fold
- WAPE by category and by store (RF-S0 vs best baseline)
- actual vs forecast totals per target week

---

## 10. Acceptance criteria (proposed; set before any results are seen)

Judged on **RF-S0, separately for H1 and H4**. The "best baseline" is whichever of naive and 4-week average has the lower pooled WAPE for that horizon.

| Gate | Criterion |
|---|---|
| **G0 Integrity** (hard) | All leakage tests in section 8 pass; outputs reproducible; predictions finite and ≥ 0; identical evaluation rows |
| **G1 Accuracy** | Pooled WAPE at least **5% lower (relative)** than the best baseline for H1, and at least **3% lower** for H4 |
| **G2 Consistency** | RF-S0 beats the best baseline in **≥ 5 of 6 folds**, and is never worse than it by more than **1.0 WAPE point** in any fold |
| **G3 Bias** | Pooled \|bias\| ≤ **5%**; each fold \|bias\| ≤ **10%** |
| **G4 Segments** | No category's pooled WAPE worse than the best baseline by > 2 points; ≥ 13 of 15 stores improved |
| **G5 Significance** | The 95% bootstrap interval of the WAPE difference excludes 0 |

**Outcomes:**
- **All gates pass:** RF-S0 is accepted for that horizon.
- **G0 passes but another gate fails:** the **best baseline is the accepted model** for that horizon. This is a valid result, and the failure is documented.
- **The F6 (Christmas) fold.** It is expected to stress G2 and G3, because the Christmas run-up never appears in training. If F6 is the *only* failure, it is reported as a documented limitation and needs your explicit decision.
- **S1/S2** may be accepted separately as "conditional on supplied plans", using the same gates against the same baselines. S3 and R0 are never accepted.

---

## 11. Files, tests, outputs and documentation (Step 4B)

**New code** (reference code is untouched):

| File | Purpose |
|---|---|
| `src/dpe/forecast/__init__.py` | Package |
| `src/dpe/forecast/panel.py` | Load verified raw data into a complete store × product × week panel with week index, calendar and holiday calendar |
| `src/dpe/forecast/features.py` | As-of feature builder `features_at_origin(panel, origin, horizon, scenario)` and the training-pair builder |
| `src/dpe/forecast/scenarios.py` | Scenario definitions (S0–S3, R0), column whitelists and the recorded assumptions |
| `src/dpe/forecast/baselines.py` | Naive and 4-week average |
| `src/dpe/forecast/models.py` | RF wrapper (fixed parameters, seed, clipping) |
| `src/dpe/forecast/backtest.py` | Fold generation, training cut-offs, prediction table with identical-row assertions |
| `src/dpe/forecast/evaluate.py` | Metrics, breakdowns, bootstrap, acceptance gates |
| `src/dpe/forecast/report.py` | Charts and draft results markdown |
| `src/dpe/forecast/pipeline.py` | Orchestration into a new run folder |
| `scripts/run_forecast_backtest.py` | Entry point |
| `src/dpe/config.py` | Add the final EDA run `20261021-162605_eda` to the protected paths; record its checksums |

**New tests:**
- `tests/test_forecast_features.py`: truncation, perturbation, alignment, whitelist, minimum history
- `tests/test_forecast_backtest.py`: folds, cut-offs, identical rows, naive continuity, reproducibility (on a small synthetic panel)
- `tests/test_forecast_evaluate.py`: metric formulas, breakdown reconciliation, gate logic
- `tests/test_forecast_outputs.py`: new run folder only, protected runs unchanged

The test fixture is a small synthetic panel (for example 3 products × 2 stores × 30 weeks) with known values. Unit tests train no full model; one end-to-end test uses a tiny forest on the fixture.

**Outputs** (new folder `outputs/runs/<timestamp>_forecast_backtest/`):
- `predictions.csv`: keys, origin, target, horizon, fold, scenario, model, actual, forecast
- `folds.csv`
- `feature_sets.json`
- `metrics_overall.csv`, `metrics_by_fold.csv`, `metrics_by_category.csv`, `metrics_by_store.csv`, `metrics_by_segment.csv`
- `bootstrap.json`, `acceptance.json`
- `charts/`
- `results_draft.md`
- `manifest.json`: input hashes, versions, parameters, assumptions

**Documentation:**
- `docs/STEP_4B_BACKTEST_RESULTS.md`
- `docs/DECISIONS.md` entries: horizon definitions, scenario rules, holiday-calendar assumption, acceptance thresholds
- `docs/CHANGELOG.md`

**Preserved and never written:**
- `data/raw`, `data/reference`, `legacy/`
- `outputs/runs/20261021-133846_reference_rf`
- `outputs/runs/20261021-160432_eda`, `outputs/runs/20261021-162605_eda`, and the superseded EDA runs
- the original projects and backups, SQLite, Airtable, GitHub

---

## 12. Implementation checkpoints (plain language)

1. **CP1: Groundwork.**
   - Protect the final EDA run.
   - Build the clean weekly table every forecast will read from (one row per store, product and week) and check it against the known totals.
   - *No models yet.*
2. **CP2: The "what did we know at the time?" feature builder.**
   - Write the code that, for any forecast date, collects only information available on that date.
   - Prove it with the leakage tests. For example, scrambling every future number must not change a single feature.
   - *I recommend stopping here so you can review the leakage tests before anything is trained.*
3. **CP3: Baselines and the backtest calendar.**
   - Set up the six test periods and the two simple benchmarks (last week's sales; the average of the last four weeks).
   - Confirm the simple benchmark matches the original project's naive forecast exactly.
4. **CP4: Train and score the Random Forests.**
   - Train one model per test period, horizon and scenario, using only data from before each test period.
   - Score every model on exactly the same rows.
5. **CP5: Results and decision.**
   - Produce the accuracy tables, charts and the pass/fail verdict for each acceptance gate.
   - Write the results document.
   - *Stop for your approval.* No model is adopted and no pricing work starts without it.

**Estimated scope:** about 900–1,300 lines of code and tests across 10 new modules, plus 4 test files. A single backtest run is expected to take minutes, not hours.

---

## 13. Open decisions for approval

1. Approve the **acceptance thresholds** in section 10 (5%/3% relative WAPE gain, 5 of 6 folds, bias limits), or adjust them before results exist.
2. Approve treating the **holiday flag as a known calendar** in all scenarios.
3. Approve the **scenario set** (S0 primary; S1/S2 conditional; S3/R0 diagnostic only).
4. Approve **fixed reference hyperparameters** for 4B, with no tuning.
5. Approve a **review stop after CP2** (recommended) or running CP1–CP5 continuously.

---

## 14. Amendments made at Step 4B approval (CP1–CP2), 2026-10-21

These were added when CP1–CP2 were approved. Where they conflict with earlier sections, they replace them.

1. **Acceptance thresholds are provisional.** The section 10 gates will be reviewed against the CP5 backtest results before any model is accepted. They are not final pass/fail rules yet.
2. **Bootstrap must respect dependence across weeks and series.** This replaces the plain week-level bootstrap in section 9.
   - **Method:** a two-way cluster bootstrap.
     - Resample the 720 store-product series with replacement.
     - Independently resample **blocks of 4 consecutive target weeks** (the 6 fold blocks) with replacement.
     - Each (series, week) cell is weighted by (times its series was drawn) × (times its week block was drawn).
     - The WAPE difference is computed on the **paired** predictions of the two models over the same weighted cells.
   - **Settings:** 2,000 replicates; 95% percentile interval.
   - **Sensitivity check:** store-level clusters (15) in place of series. Stores share local shocks, so this tests whether series-level clustering is too optimistic.
   - **Caveat:** with only 6 week blocks the interval is coarse, and the report will say so.
3. **Naive continuity claim (section 7.4) is limited to equivalent definitions.**
   - The H1 naive baseline may be called equivalent to the reference naive *only* for H1 targets in weeks 45–52. Those rows have the same origins (target − 1), the same target weeks and the same inputs (the prior week's actual units).
   - The CP3 test must check origins, targets and values row by row before the claim is made.
   - No H4 result is compared with the reference naive.
4. **R0 needs its own definition at CP4.** The reference model was evaluated on targets 45–52 with one training cut-off (week 44). Any R0 fold result is labelled "reference feature set on the new folds", not "the reference result".
5. **Feature list as implemented.** `docs/STEP_4B_CP1_CP2_IMPLEMENTATION.md` and `dpe.forecast.features.feature_columns()` are authoritative. Supplier identity is not used, because it is implied by product.
6. **Extra assumption.** The hierarchy features need all stores' week-*T* sales to be available at origin *T*. If deployment cannot guarantee that, those features must be lagged one week.
