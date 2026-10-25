# Step 4D-A: challenger model design (design only)

- **Status:** design only. Nothing was installed, implemented or trained. Protected runs, forecasting features and recorded decisions are unchanged. **Approval required before Step 4D-B.**
- **Date:** 2026-10-21
- **Builds on:**
  - [STEP_4A_FORECAST_DESIGN.md](STEP_4A_FORECAST_DESIGN.md) (with section 14 amendments)
  - [STEP_4B_CP1_CP2_IMPLEMENTATION.md](STEP_4B_CP1_CP2_IMPLEMENTATION.md), [STEP_4B_CP3_BASELINES.md](STEP_4B_CP3_BASELINES.md), [STEP_4B_CP4_RF_RESULTS.md](STEP_4B_CP4_RF_RESULTS.md), [STEP_4B_CP5_ACCEPTANCE.md](STEP_4B_CP5_ACCEPTANCE.md)
  - DECISIONS 1–17

> **Standing caveats.** The data is *apparently synthetic; provenance unconfirmed*, with one year (52 weeks), 48 products and 15 stores. The six backtest folds have **already been examined** in CP3–CP5. No result from this step can be confirmed without new, untouched data. Forecasting is one component of the project. **This step ends with a firm stop, followed by a return to pricing, inventory and waste decision support.**

---

## 1. Current position

| Horizon | Preferred research candidate | Pooled WAPE (6 folds) | Status |
|---|---|---|---|
| H1 | Random Forest, S0 (300 trees, depth 12, seed 42) | 25.92% | All 9 CP5 gates PASS; not approved for production (DECISIONS 13, 17) |
| H4 | Four-week moving average | 29.41% | Retained; the H4 RF failed G1, G5, G6, G7 and G8 (DECISION 14) |

**Leakage-safe architecture** (reused unchanged):

| Layer | Component |
|---|---|
| Input | Protected panel run `20261021-171758_forecast_panel`, verified and rebuilt from raw |
| Features | `dpe.forecast.features`: as-of S0 features at origin *T*. 26 history, 4 static numeric, 3 target-week calendar, one-hot identity. No target-week price, discount, marketing, weather or wastage. |
| Folds | `dpe.forecast.backtest`: six 4-week target blocks (weeks 29–52); training targets ≤ the earliest test origin |
| Encoder | One-hot categories fitted per fold on training rows only |
| Evaluation | `dpe.forecast.evaluate` (MAE, RMSE, WAPE, Bias) and `dpe.forecast.acceptance` (verification, two-way bootstrap, frozen gates, fixed decision rule) |
| Tests | 211 passing; 79 leakage and integrity tests in the forecasting files |

**Known weaknesses of every model so far** (CP4/CP5):
- **Christmas:** weeks 51–52 are under-forecast by 14–21% overall, and by up to about 50% for Bakery and Meat.
- **Discounts:** target weeks with a discount are under-forecast by about 15% in S0.
- **Meat at H4:** the RF over-forecasts by 24–41% in F1–F3, linked to the June step-up and to target months the model never saw in training.
- **Noise:** week-to-week noise dominates. The 4-week average reached 28.7% on the original holdout weeks.

---

## 2. Are the candidates appropriate?

| Method | Fit for this data | Expected value | Recommendation |
|---|---|---|---|
| **XGBoost** (gradient-boosted trees) | **Good.** Tabular data, up to about 29k training rows × 106 inputs, nonlinear interactions, no missing values | **Modest.** Weekly noise sets a floor. Boosting can fit structure the RF averages away, but can also chase noise. Regularisation matters more than capacity. | **Include** (one pre-registered configuration) |
| **CatBoost** | **Good, and different.** Native categorical handling (ordered target statistics) for Product, Store, Category and Region instead of one-hot; ordered boosting resists overfitting on small data | **Modest.** The most likely tree model to handle identity effects well. Its categorical encoding is learned, but inside each fold's training fit, which satisfies the training-only preprocessing rule. | **Include** (one configuration, native categoricals) |
| **LightGBM** | Good, but very close to XGBoost (histogram boosting, leaf-wise growth) | **Low *additional* value.** A third boosted-tree family adds a multiple comparison for little new information. | **Exclude** (approval point) |
| **Simple exponential smoothing (SES), per series** | **Good for noisy level series.** A classical, interpretable, low-variance baseline. Seasonal Holt-Winters is **not** possible with one year of data. | **Real value, especially for H4.** It is a stronger "simple" benchmark than the 4-week average. If it ties the trees, the trees are not worth their complexity. It needs **no new package** (`statsmodels` is already pinned). | **Include**, as a baseline-type challenger |

---

## 3. Fair comparison (identical protocol)

Every challenger uses **exactly** the CP3/CP4 protocol:
- **Data:** the same verified panel, S0 only, the same 6 folds, the same per-horizon training cut-offs, the same scored rows (2,880 per fold and horizon).
- **Features:** the same as-of S0 feature list.
  - **CatBoost exception:** CatBoost receives the four identity columns as native categorical features instead of one-hot. This is its defining property, and it is fitted on training rows only.
- **Models:** separate models per horizon (direct strategy); forecasts clipped at 0.
- **Comparisons**, pre-specified:
  - **(a) Against the incumbent:** H1 challengers vs the **H1 Random Forest**; H4 challengers vs the **four-week moving average**.
  - **(b) Against mean_4w on both horizons,** for continuity with the CP5 gates.
- **Incumbent predictions** are read from the protected CP3/CP4 runs, **not refitted**.

**Pre-registered configurations** (proposed; fixed before any challenger is trained; no tuning on the outer folds):

| Model | Configuration |
|---|---|
| XGBoost | `objective="reg:squarederror"`, `n_estimators=500`, `learning_rate=0.05`, `max_depth=6`, `min_child_weight=10`, `subsample=0.8`, `colsample_bytree=0.8`, `reg_lambda=1.0`, `tree_method="hist"`, `random_state=42` |
| CatBoost | `loss_function="RMSE"`, `iterations=1000`, `learning_rate=0.05`, `depth=6`, `l2_leaf_reg=3`, `random_seed=42`, `cat_features=[Product_ID, Store_ID, Product_Category, Region]`, fixed `thread_count` |
| SES (per series) | Smoothing level α estimated per series by `statsmodels` `SimpleExpSmoothing` on that fold's training weeks only (≤ the fold cut-off), bounded to [0.05, 0.95]. The level is then filtered forward with that fixed α up to each test origin *T*. The forecast for *T* + *h* is the level at *T*, the same for H1 and H4. |

**Squared-error objectives** keep the comparison like-for-like with the RF. An MAE-type objective would favour WAPE, but would be a second change at the same time.

---

## 4. The fold-reuse problem and the validation strategy

**The problem.**
- The six folds were used to compute the CP4 results, to set the CP5 verdicts, and to diagnose weaknesses (Meat, Christmas).
- Any new model judged on them is being judged on data we already know. If several challengers are tried, or settings are adjusted after looking, the winner's score is biased upward: the "winner's curse" or "garden of forking paths".

**Controls in this design:**
1. **One pre-registered configuration per challenger.** Settings are recorded in this document and frozen in code before any training. They are not chosen to fix Meat or Christmas.
2. **No outer-fold tuning.** The outer folds produce exactly one score per challenger and horizon.
3. **Inner development-validation, inside each outer fold's training window,** used for sanity and convergence checks only (Option A), or also for a three-value choice of tree count (Option B).
   - The inner validation block is the **last 4 training target weeks**.
   - Inner training targets must be ≤ (inner block start − *h*), the CP3 rule applied again.
   - Example: H1 F1 trains on targets 9–28, so its inner validation is targets 25–28, using inner training targets ≤ 24.
   - Outer test weeks are never touched by the inner step.
4. **Multiplicity correction.** There are 3 challengers × 2 horizons = 6 comparisons against incumbents. Significance uses a **Bonferroni-adjusted 99.17% interval** (1 − 0.05/6) from the existing two-way series × week-block bootstrap, with 5,000 replicates. With only 6 week blocks, the tails are coarse; this will be stated.
5. **A higher bar to replace an incumbent** (section 6), because the incumbent was chosen first.
6. **Every result labelled "exploratory: folds previously examined."**

| What this step **can** establish | What it **cannot** establish without new, untouched data |
|---|---|
| Whether a challenger, under an identical, leakage-safe protocol, has lower error than the incumbent **on these six folds** | Whether that advantage generalises to **future weeks** (2025 onwards) |
| Whether the difference survives a dependence-aware bootstrap and multiplicity correction | Performance on a **second Christmas**, or any recurring seasonality (one year only) |
| Consistency across folds, categories, stores, discount and holiday weeks | Whether patterns reflect **real shopper behaviour** rather than the data generator |
| Whether weaknesses (Meat, Christmas) are model-specific or shared by all models | A production-grade accuracy estimate |

**Confirmation route.** If a challenger meets the criteria, it becomes a *provisional* candidate. Its code and configuration are frozen (hashed), and it is confirmed **prospectively**: an incumbent-vs-challenger shadow comparison on the first ≥ 8–12 weeks of untouched data, before any promotion.

---

## 5. Metrics, diagnostics and bias checks

**Metrics** (unchanged definitions): MAE, RMSE, **WAPE** (primary), signed **Bias %**. Each is reported pooled, per fold and per horizon, plus:
- **Breakdowns:** by category (4), store (15), region (6, flagged when fewer than 3 stores), target-week holiday status, and target-week discount status (analysis only, never an input).
- **Overfitting:** in-sample vs test WAPE gap per fold.
- **Feature importance:** XGBoost gain, CatBoost prediction-values-change. Stated as **non-causal**.

**Focused diagnostics** (descriptive only; they do not change models):

| Diagnostic | Content |
|---|---|
| **Christmas** | Weeks 51 and 52 by category and model: WAPE, bias, and forecast vs actual uplift relative to weeks 45–50. Tests whether any challenger is less wrong, while noting that **no model has seen a Christmas**. |
| **Discount weeks** | Bias for discounted vs undiscounted target weeks (S0 cannot see discounts, so about −15% is expected for every model). This measures whether challengers inflate the over-forecast of *undiscounted* weeks. |
| **Meat** | H4 and H1, folds F1–F3 and target weeks 29–40: forecast/origin and actual/origin ratios, month-coverage flags. Shows whether the June step-up artefact is RF-specific or shared. |
| **Negative control** | On fold F3 per model and horizon, train once on **within-training permuted targets**. Expected result: about mean-level accuracy. Catches pipeline leakage that could hide behind good scores. |
| **Reproducibility** | Each challenger refit once on F1. Forecasts must agree within the approved **1e-6 units** (DECISION 16). Bit-exactness is not claimed for multithreaded runs. |

---

## 6. Acceptance criteria (pre-registered; incumbents keep their status unless all are met)

A challenger **replaces the incumbent for a horizon** only if **all** of the following hold:

1. **Integrity.** The 79 forecasting leakage and integrity tests and the new challenger tests pass. Rows, folds and origins are identical to CP3/CP4. Reproducibility holds within 1e-6. The negative control behaves as expected.
2. **The original nine CP5 gates against mean_4w**, with unchanged thresholds (DECISION 15). For H4 this includes G1 ≥ 3% and G8.
3. **Clear improvement over the incumbent:**
   - Pooled relative WAPE improvement **≥ 2.0%** over the incumbent (H1: vs the RF; H4: vs mean_4w, which gate 2 already requires at ≥ 3%).
   - **The Bonferroni-adjusted 99.17% two-way bootstrap interval** of that improvement lies above 0.
   - Better than the incumbent in **≥ 5 of 6 folds**.
   - No category worse than the incumbent by more than **1.0 WAPE point**.
4. **Bias no worse than the incumbent:** pooled |bias| not larger by more than 1 point; no extra fold outside ±10%.

**Possible outcomes for each horizon:**
- **Incumbent retained** (default).
- **Challenger provisional**: it meets all four criteria, and still requires prospective confirmation (section 4).
- **Inconclusive**: integrity checks pass but the evidence is mixed. The incumbent is retained.

No outcome is a production approval (DECISION 17).

---

## 7. Preventing synthetic-data artefacts from being read as business relationships

| Known artefact (EDA §3) | Safeguard |
|---|---|
| `Wastage = ⌊k_product × units⌋` | Wastage is never a model input (enforced and tested). Waste forecasts in later steps are labelled "k × forecast, a data artefact". |
| `Price ≈ base × (1 − discount)`, base price noise-like | S0 has no target-week price or discount, so the challengers cannot exploit it. No elasticity is inferred from any model. |
| Discount uplift (about +6% at 5%, about +51% at 25%), assigned independently of season | Not used in S0. Any later pricing use is an **explicit, adjustable assumption**, not a learned fact. |
| Step changes (Meat early June – mid-July; Bakery Easter; category Christmas peaks) | Reported as data features. Model behaviour around them is diagnosed, never "explained" as consumer behaviour. |
| One year only | No claim of seasonality, recurring patterns or annual effects |

**Rules:**
- Feature importances and segment results are described as "how the model uses inputs in this dataset".
- No causal or behavioural wording in any report.
- The existing wording tests are extended to the challenger report.

---

## 8. Experiment budget, reproducibility and packages

| Item | Budget |
|---|---|
| Models | XGBoost, CatBoost, SES (LightGBM excluded unless approved) |
| Configurations | **One per model** (Option A, recommended). Option B adds an inner-validation choice of tree count from {250, 500, 1000} for the boosted models only. |
| Main fits | 2 boosted models × 2 horizons × 6 folds = **24**. SES: 720 series × 6 folds × 2 horizons, smoothing only, in seconds. |
| Extra fits | Reproducibility refits 2 × 2 = 4; negative controls 3 models × 2 horizons = 6. Option B adds 3 × 24 = 72 small inner fits. |
| Expected run time | Under 30 minutes in total on this machine; to be confirmed by a timed first fold. |
| Rounds | **Exactly one comparison round.** No second round, no "one more model". |

**Reproducibility rules:**
- Fixed seeds.
- Fixed thread counts (`n_jobs` / `thread_count` recorded).
- Package versions in the manifest.
- Input checksums verified.
- New run folders only.
- Challenger code hashed in the manifest.
- 1e-6 tolerance (DECISION 16).

**Packages** (installing needs your approval; nothing installed yet):

| Package | Purpose | Note |
|---|---|---|
| `xgboost` | XGBoost challenger | Version to be pinned exactly after a compatibility check with Python 3.11, NumPy 2.3.4, pandas 2.3.3 and scikit-learn 1.7.2 |
| `catboost` | CatBoost challenger | Same check; must support NumPy 2.x |
| `statsmodels` | SES | Already pinned (0.14.6); no change |

Proposed home: `requirements-challenger.txt` (optional extras), so the core environment stays as approved. Installation goes into the existing V2 `.venv` only, after approval.

---

## 9. Implementation plan (Step 4D-B, after approval)

| Checkpoint | Content | Stop? |
|---|---|---|
| 4D-B1 | Install pinned packages; protect the CP5 inputs (already protected); add `dpe/forecast/challengers.py` (XGBoost, CatBoost, SES wrappers using existing features, folds and encoders); add tests on the synthetic panel (cut-offs, scrambling, alignment, CatBoost training-only categoricals, SES training-only α, reproducibility, negative control) | Stop for review of the tests |
| 4D-B2 | Single run: all challengers, both horizons, six folds; new run folder; incumbent predictions read from protected runs | — |
| 4D-B3 | Comparison and acceptance (section 6), diagnostics (section 5), `docs/STEP_4D_CHALLENGER_RESULTS.md` | **Firm stop** |

---

## 10. Firm stopping point

After 4D-B3, **forecasting model development stops**, whatever the outcome:
- If no challenger qualifies, the incumbents (H1 RF, H4 four-week average) stay as the research candidates.
- If one qualifies, it becomes a *provisional* candidate, awaiting prospective confirmation on new data. No further tuning follows.

Not part of this or any immediate step:
- more model families
- hyperparameter searches
- new features (including Christmas or `target_month` changes)
- S1/S2 scenario modelling

The project then moves to **Step 5: decision support** (section 11).

---

## 11. Handoff into decision support (outline for later approval; nothing built now)

**Forecast interface.** One table, read by everything downstream:

| Column | Meaning |
|---|---|
| `run_id`, `model`, `scenario` | Provenance |
| `horizon` | H1 or H4 |
| `Store_ID`, `Product_ID` | Identifiers (always present) |
| `origin_week`, `origin_date`, `target_week`, `target_date` | Explicit timing |
| `forecast` | Point forecast (units) |
| `error_quantiles` | From backtest errors by category and horizon (for safety stock) |
| `status_flags` | e.g. Christmas week, holiday, cold start |

**Step 5 components** (each a separate, approved design):

1. **Inventory planning.**
   - H1 for weekly replenishment, H4 for ordering.
   - Order quantity = forecast + safety stock from backtest error quantiles per category.
   - Shelf life and supplier lead time as constraints.
   - Explicit Christmas and discount-week overrides, flagged for human review.
2. **Waste-risk estimates.**
   - Expected waste = k_product × planned quantity, **labelled a data artefact**.
   - Real waste data would be needed for optimisation claims.
3. **Pricing recommendations, as decision support.**
   - Rule-based, transparent actions: hold, markdown candidate, promotion candidate, reduce supply.
   - Driven by forecast vs stock vs shelf life.
   - The discount uplift is entered as an **adjustable scenario assumption** (EDA §2.3), with ranges.
   - **No elasticity claims.** Every recommendation carries its reasons and assumptions.
4. **SQLite.**
   - A **new V2 database** in `dynamic-pricing-engine-v2/database/`, created by script.
   - Tables: `forecasts`, `recommendations`, `run_registry`; append-only by run_id.
   - **Never the original `pricing_system.db`**, and never `if_exists="replace"`, which the legacy v1 script uses (`legacy/dynamic_pricing_engine_v1/scripts/run_pricing_engine.py`).
5. **Airtable.**
   - Push to a designated sandbox base only, after approval.
   - Credentials from environment variables, never in code. The legacy `run_pricing_to_airtable.py` contained a hard-coded credential and was deliberately not copied.
   - Every push is explicitly confirmed.
6. **Dashboard.**
   - A local, read-only view of forecasts, recommendations, assumptions and data caveats.
   - Technology (static HTML vs an app framework) to be decided at Step 5. Any new package needs approval.
7. **GitHub.**
   - Only after the `.gitignore` review (DECISION 3) and a secrets scan.
   - Data and large outputs excluded or handled separately.
   - Push only with explicit approval.

---

## 12. Decisions requiring your approval

1. **Model scope:** include XGBoost, CatBoost and per-series SES; **exclude LightGBM**.
2. **Package installation:** `xgboost` and `catboost` into the V2 `.venv`, versions pinned after a compatibility check, listed in `requirements-challenger.txt`.
3. **Configuration policy:** **Option A**, one pre-registered configuration each with no tuning (recommended), or **Option B**, a three-value tree-count choice on inner validation only.
4. **The pre-registered configurations** in section 3, including CatBoost's native categoricals.
5. **Acceptance criteria** in section 6: the original nine gates **plus** ≥ 2% relative improvement over the incumbent, a Bonferroni-adjusted 99.17% two-way bootstrap interval above 0, ≥ 5/6 folds, ≤ 1-point category deterioration, and no bias deterioration.
6. **Labelling:** every result is "exploratory, folds previously examined"; a winner is at most "provisional, pending prospective confirmation".
7. **Budget and stop:** one round, about 34 fits (Option A), then a **firm stop** and the move to Step 5.
8. **Handoff order for Step 5:** inventory → waste-risk → pricing recommendations → SQLite → dashboard → Airtable → GitHub (each designed and approved separately).
