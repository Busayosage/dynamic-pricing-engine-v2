# Step 4D: challenger replacement policy (pre-registered)

- **Written:** 2026-10-21, **before any challenger was implemented or trained.** It is implemented exactly in `dpe/forecast/challenger_eval.py`.
- **Scope:** Step 4D only.
- **Rules unchanged by this policy:**
  - The CP5 gates, their thresholds and their verdicts for the incumbents (DECISION 15)
  - DECISIONS 13–17
- **Status of results:** every challenger result is **exploratory**. The six folds (target weeks 29–52) were already examined in CP3–CP5.

---

## 1. Incumbents and why the comparisons are not equivalent

| Horizon | Incumbent | Source of incumbent forecasts | What a challenger must show |
|---|---|---|---|
| H1 | Random Forest, S0 | Protected CP4 run `20261021-180522_rf_backtest`, read and **not refitted** | It beats a **trained model** that already passed all nine CP5 gates |
| H4 | Four-week moving average | Protected CP3 run `20261021-175029_baseline_backtest` | It beats a **baseline**. CP5 gate G1 (≥ 3% vs mean_4w) is stricter here than the incumbent-relative rule R3a (≥ 2%), and both apply. |

- For H1, rule R2 (CP5 gates vs mean_4w) and rule R3 (vs RF) test **different things**.
- For H4 they overlap, because the incumbent *is* mean_4w.
- The results are reported separately and never pooled across horizons.

---

## 2. Rules: all must hold for a challenger to become provisional

### R1. Integrity (hard)
- **R1.1 Leakage tests.** The 79 forecasting leakage and integrity tests and the challenger tests all pass.
- **R1.2 Identical rows.** Challenger rows equal the CP4 rows: the same 2,880 keys per fold and horizon, the same origins and target weeks, and actuals equal to the panel.
- **R1.3 Valid forecasts.** Finite and ≥ 0.
- **R1.4 Reproducibility.** The F1 refit (boosted models) or a recomputation (SES) agrees within **1e-6 units** (DECISION 16).
- **R1.5 Negative control** (boosted models). A fit on **training targets randomly permuted** within the F3 training rows must have test WAPE **≥ 0.9 ×** the WAPE of a constant predictor (the training-target mean) on the same rows. SES has no feature-to-label mapping to permute, so this check does not apply to it.
- **R1.6 Inner sanity** (boosted models, F3). On the inner block (the last 4 training target weeks, with inner training targets ≤ inner start − *h*), the challenger's WAPE must be lower than last_week's. This is a **sanity check only**, never a configuration choice.

### R2. Eligibility screen: the nine CP5 gates against mean_4w, unchanged
The nine CP5 gates G0–G8 are applied to the challenger exactly as they were applied to the RF in CP5:
- same thresholds, same 95% two-way bootstrap, same store sensitivity
- same status rules: inclusive bounds; "improved" means strictly lower WAPE

All nine must be PASS.

### R3. Improvement over the incumbent

| Rule | Criterion |
|---|---|
| R3a | Pooled relative WAPE improvement over the incumbent **≥ 2.0%** |
| R3b | The **99.17%** two-way bootstrap interval of R3a lies above 0, for **both** the series × week-block (primary) and store × week-block (sensitivity) designs. 5,000 replicates, seed 20261022, percentile interval. 99.17% = 1 − 0.05/6, a Bonferroni correction for 3 challengers × 2 horizons. |
| R3c | Lower WAPE than the incumbent in **≥ 5 of 6** folds |
| R3d | No category with WAPE worse than the incumbent's by more than **1.0 point** |

### R4. Bias no worse than the incumbent

| Rule | Criterion |
|---|---|
| R4a | Pooled \|bias\| ≤ the incumbent's pooled \|bias\| + 1.0 point |
| R4b | Number of folds with \|bias\| > 10% ≤ the incumbent's number |

---

## 3. Outcomes (per horizon)

| Outcome | Condition |
|---|---|
| **PROVISIONAL_CHALLENGER** | R1–R4 all hold. If more than one challenger qualifies, the one with the lowest pooled WAPE is named; the others are reported. It remains **pending prospective confirmation on untouched data** and is not a production approval (DECISION 17). |
| **RETAIN_INCUMBENT: insufficient evidence** | R1 holds, but any of R2–R4 fails. This is the default. |
| **RETAIN_INCUMBENT: integrity failure** | Any R1 check fails. The challenger result is not interpreted. |

---

## 4. Interpretation limits

- **Not independent confirmation.** The bootstraps are conservative within-sample uncertainty statements on **reused folds**. A significant result says the difference is unlikely to be week-to-week or series-level noise *in these 24 target weeks*. It does **not** say the difference would recur on new data.
- **Coarse bootstrap.** With only 6 week blocks, the bootstrap tails are coarse.
- **Not behaviour.** Diagnostic patterns (Christmas, discount weeks, Meat, feature importance) describe model behaviour on apparently synthetic data, not shopper behaviour.

---

## 5. Fixed configurations (Option A; no tuning)

| Model | Configuration |
|---|---|
| XGBoost 3.2.0 | `objective="reg:squarederror"`, `n_estimators=500`, `learning_rate=0.05`, `max_depth=6`, `min_child_weight=10`, `subsample=0.8`, `colsample_bytree=0.8`, `reg_lambda=1.0`, `tree_method="hist"`, `random_state=42`, `n_jobs=4`. Inputs: the S0 feature list, with identity one-hot encoded by the training-only encoder (the same 106 inputs as the RF). |
| CatBoost 1.2.10 | `loss_function="RMSE"`, `iterations=1000`, `learning_rate=0.05`, `depth=6`, `l2_leaf_reg=3`, `random_seed=42`, `thread_count=4`, `allow_writing_files=False`, `verbose=False`. Inputs: the S0 feature list, with `Product_ID`, `Store_ID`, `Product_Category` and `Region` as **native categorical** features. |
| SES (statsmodels 0.14.6) | Per series and per fold/horizon: `ExponentialSmoothing(trend=None, seasonal=None, initialization_method="estimated", bounds={"smoothing_level": (0.05, 0.95)})`, fitted on that series' units for weeks 1 … *T*_min (the fold's earliest test origin). The level is then filtered forward with the fixed α through each test origin *T*. Forecast for *T* + *h* = level at *T*. |

**CatBoost categorical inputs are static identity attributes,** known at every forecast origin. Their ordered target statistics are computed by CatBoost **from the training rows of the fold only**. Test labels never enter, and the future-scrambling test checks this.

**Budget** (one round):
- 24 boosted fits (2 models × 2 horizons × 6 folds)
- 4 reproducibility refits
- 4 negative-control fits
- 4 inner-sanity fits
- SES on 720 series × 6 folds × 2 horizons

No second round.
