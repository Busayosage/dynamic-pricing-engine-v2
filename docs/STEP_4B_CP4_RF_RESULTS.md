# Step 4B, checkpoint 4: Random Forest training and evaluation (S0)

- **Status:** CP4 is implemented and run. **No model has been selected, deployed or promoted. No acceptance verdict is given** (that is CP5; thresholds remain provisional).
- **Date:** 2026-10-21
- **Results run:** `outputs/runs/20261021-180522_rf_backtest/` (run time 288 s)
- **Benchmark run:** `outputs/runs/20261021-175029_baseline_backtest/` (now protected)

> The dataset is *apparently synthetic; provenance unconfirmed*. The results describe this dataset only. Feature importance shows how the model uses its inputs. It is **not** evidence of causal effects.

---

## 1. What was done

| Item | Implementation |
|---|---|
| Baseline run protected | `20261021-175029_baseline_backtest` added to the protected paths (`config.BASELINE_RUN_DIR`); its 7 files recorded in `CHECKSUMS.sha256`; writes blocked (tested) |
| Models | One Random Forest per **horizon** (H1, H4) and **fold** (F1–F6): 12 fits, plus 2 reproducibility refits |
| Configuration | `n_estimators=300`, `max_depth=12`, `random_state=42`, `n_jobs=-1`. Imported from `dpe.reference_baseline.RF_PARAMS`, so it is identical to the original. **No tuning.** |
| Features | The CP2 S0 as-of feature list: 26 history, 4 static numeric, 3 target-week calendar, plus one-hot identity. That is 106 model inputs. **Excluded:** target-week price, discount, marketing and weather; wastage at any lag. |
| Training cut-off | CP3 rule, asserted per fold and horizon: training targets ≤ the earliest test origin (start − *h*); training origins ≤ start − 2*h* |
| Preprocessing | The only learned transformation is the one-hot encoding. Its category lists are fitted on **each fold's training rows only**, and a category unseen in training raises an error. There is no imputer or scaler, because there are no missing values and trees need no scaling. Forecasts are clipped at 0. |
| Comparison | RF, last_week and mean_4w are scored on **identical rows**: 2,880 per fold and horizon, 17,280 per horizon |
| Analysis-only columns | Category, region, target-week holiday and target-week discount status are joined from the panel **after** prediction. Discount status is used only for error analysis. |
| Code | `src/dpe/forecast/models.py`, `src/dpe/forecast/rf_backtest.py`, `scripts/run_rf_backtest.py`; `features.py` (now allows the `fold` metadata column) |

---

## 2. Headline results (pooled over 6 folds, 17,280 rows per horizon)

| Horizon | Model | MAE | RMSE | WAPE | Bias |
|---|---|---|---|---|---|
| **H1** | last_week | 550.1 | 802.5 | 34.08% | −1.29% |
| | mean_4w | 450.2 | 654.5 | 27.89% | −2.17% |
| | **random_forest** | **418.3** | **607.2** | **25.92%** | **−1.76%** |
| **H4** | last_week | 564.8 | 822.9 | 34.99% | −2.63% |
| | mean_4w | 474.7 | 686.6 | 29.41% | −2.85% |
| | **random_forest** | **465.4** | **665.2** | **28.84%** | **−0.50%** |

**RF against the four-week average:**

| Horizon | WAPE change | Folds where RF is better | Stores where RF is better |
|---|---|---|---|
| **H1** | −1.97 points (**−7.1% relative**) | 6 of 6 | 15 of 15 |
| **H4** | −0.57 points (**−1.9% relative**) | 5 of 6 | 9 of 15 |

Provisional gates are **not** applied here. For orientation only, the proposed G1 levels were −5% relative for H1 and −3% for H4.

### Results for each fold (WAPE %, with RF bias)

| Fold | Target weeks | H1 last_week | H1 mean_4w | **H1 RF** | H1 RF bias | H4 last_week | H4 mean_4w | **H4 RF** | H4 RF bias |
|---|---|---|---|---|---|---|---|---|---|
| F1 | 29–32 | 34.08 | 27.97 | **26.32** | +3.59 | 36.00 | 30.74 | **30.54** | +9.35 |
| F2 | 33–36 | 34.97 | 28.50 | **26.04** | +2.66 | 35.90 | 30.11 | **29.93** | +7.87 |
| F3 | 37–40 | 33.42 | 26.58 | **24.47** | −1.44 | 34.09 | 27.09 | **25.84** | +2.57 |
| F4 | 41–44 | 33.56 | 26.68 | **24.78** | −2.88 | 32.78 | 26.72 | **25.74** | −3.20 |
| F5 | 45–48 | 34.22 | 27.38 | **25.52** | −1.70 | 33.55 | 28.15 | **26.84** | −4.11 |
| F6 | 49–52 | 34.25 | 29.94 | **28.05** | −9.16 | 37.38 | 33.14 | 33.50 | −12.52 |
| RF − mean_4w (points) | | | | −1.65 to −2.46 | | | | **+0.36** (F6) to −1.31 | |

**Reference window** (targets 45–52):

| Horizon | RF WAPE | mean_4w WAPE |
|---|---|---|
| H1 | 26.86% | 28.74% |
| H4 | 30.37% | 30.80% |

The original Oct 2025 RF scored 27.94% on the same weeks, but it used same-week discount, price, marketing and actual weather, and a single training cut-off. **The two numbers are not directly comparable**, and no claim of improvement over the original is made.

---

## 3. Segment performance (pooled WAPE %; RF − mean_4w in brackets)

| Segment | H1 RF | H4 RF |
|---|---|---|
| Bakery | 27.48 (−2.09) | 32.32 (−0.38) |
| Beverages | 24.82 (−1.69) | 27.62 (−0.59) |
| Dairy | 24.87 (−2.23) | 25.46 (−1.87) |
| **Meat** | 28.71 (−1.47) | **35.87 (+3.51)** |
| Regions (6) | RF better in all 6 (by 1.1–2.4) | RF better in 5 of 6; North East +0.52 |
| Stores (15) | RF better in 15 (by 1.51–2.57) | RF better in 9; range −1.93 to +0.66 |
| Holiday target weeks | 27.81 (−1.73); bias −6.2% | 32.75 (+0.63); bias −9.1% |
| Non-holiday target weeks | 25.45 (−2.03); bias −0.7% | 27.87 (−0.87); bias +1.6% |
| **Discounted target weeks** (analysis only) | 27.94 (−1.45); **bias −15.9%** | 30.35 (−1.04); **bias −14.7%** |
| Undiscounted target weeks | 25.21 (−2.16); bias +3.2% | 28.31 (−0.41); bias +4.5% |

**Discount bias is unchanged by the RF.** Like the baselines, the S0 forest cannot know about an upcoming discount. Discounted weeks are under-forecast by about 15–16% and undiscounted weeks over-forecast by 3–5%. This is the gap scenario S1 is meant to measure. It is not run in CP4.

---

## 4. Christmas weeks (targets 51 = 16 Dec, 52 = 23 Dec)

| Horizon | Week | last_week WAPE / bias | mean_4w WAPE / bias | **RF WAPE / bias** |
|---|---|---|---|---|
| H1 | 51 | 36.4% / −17.5% | 33.1% / −17.3% | **32.0% / −17.1%** |
| H1 | 52 | 32.9% / −2.9% | 31.0% / −15.2% | **28.5% / −13.8%** |
| H4 | 51 | 39.6% / −18.6% | 35.7% / −18.6% | **37.0% / −18.8%** |
| H4 | 52 | 40.3% / −20.0% | 36.4% / −20.6% | **38.1% / −21.1%** |

| Horizon | Model | Weeks 51–52 combined (WAPE / bias) | All other weeks (WAPE / bias) |
|---|---|---|---|
| H1 | RF | 30.2% / −15.4% | 25.4% / −0.2% |
| H1 | mean_4w | 32.0% / −16.2% | 27.4% / −0.5% |
| H4 | RF | 37.6% / −20.0% | 27.8% / +1.8% |
| H4 | mean_4w | 36.0% / −19.6% | 28.6% / −0.9% |

- **No model anticipates the Christmas rise.** The December run-up never occurs in any training fold, and the S0 features carry no "weeks before Christmas" information.
- For H4 the RF is **worse** than the four-week average in weeks 51–52.
- Weeks 45–50 behave normally: RF bias between −0.1% and −5.0%.
- Weeks 51–52 alone account for most of the F6 bias (H1 −9.2%, H4 −12.5%).

---

## 5. Overfitting and instability

1. **Train/test gap.**
   - In-sample training WAPE is 18.1–19.9% (H1) and 16.3–19.0% (H4), against test WAPE of 24.5–28.1% (H1) and 25.7–33.5% (H4).
   - The gap is **5.5–8.3 points for H1**, fairly stable across folds.
   - It is **7.5–14.5 points for H4**, largest in F1, F2 (the smallest training sets: 10,080 and 12,960 rows) and F6.
   - Depth-12 trees on noisy weekly data fit some noise. The H4 gap points to weaker generalisation when training data is short.
2. **The H4 RF over-forecasts Meat in the early folds:**

   | H4 fold | Meat bias | Meat WAPE (RF / mean_4w) |
   |---|---|---|
   | F1 | **+41.4%** | 47.7% / 34.8% |
   | F2 | **+40.2%** | 46.2% / 35.1% |
   | F3 | +24.2% | 34.7% / 29.1% |
   | F4–F6 | normal | — |

   **Likely mechanism** (diagnosis, not tested by changing the model):
   - The H4 F1 model's latest training target is week 25 (June), so it has **never seen a July or August target month**. For H4 F2 the latest is week 29, which gives only a few July targets.
   - Trees cannot extrapolate. Unseen months fall into the same branch as the latest months seen, which coincides with Meat's early-June to mid-July high period (EDA_FINDINGS §2.1).
   - Meat falls back from week 30, so the model keeps forecasting the high level.
   - This is a **one-year-of-data limitation** of the `target_month` feature, similar to the week-of-year problem identified in the Step 4A audit. **It is not leakage**: the forecasts only use information available at the origin.
3. **H4 fold-level bias swings** from +9.4% (F1) to −12.5% (F6). Pooled H4 bias (−0.5%) looks good only because these errors cancel.
4. **Reproducibility.** Refitting F1 gave forecasts that differ by at most **9.1 × 10⁻¹³ units** (H1 and H4). The run manifest records this as `identical: false` under its strict zero-difference rule. The cause is floating-point summation order with `n_jobs=-1` (parallel trees). The automated test with `n_jobs=1` is exactly identical. Equality within 1 × 10⁻⁹ is proposed as the reproducibility criterion for CP5.
5. **Feature importance** (impurity-based, mean across folds; **not causal**).
   - `store_cat_mean_4` (the store × category four-week mean at the origin) takes **0.84 (H1) and 0.79 (H4)** of total importance.
   - Every other input is at or below 0.02. `target_month` is second for H4 at 0.02.
   - Reading: the forest mainly sorts rows by their store × category level and then refines with series history. Impurity importance also favours high-cardinality continuous inputs, so the small values for the other inputs do not mean they are useless.

---

## 6. Tests (`tests/test_forecast_models.py`, 16 tests)

| Test | What it proves |
|---|---|
| `test_rf_params_are_the_original_configuration` | Settings equal the reference (300, 12, −1, 42); defaults are not a tuned set |
| `test_only_s0_is_enabled_in_cp4` | S1–S3 cannot be run through the CP4 encoder |
| `test_encoder_categories_come_from_training_rows_only` | Categories come from training rows; unseen categories are refused; an unfitted encoder is refused |
| `test_fold_encoders_are_fitted_on_their_training_rows` | Every fold records a training-only encoder |
| `test_training_targets_available_by_earliest_test_origin` (H1, H4) | Last training target = earliest test origin < first test target, per fold |
| `test_scrambling_after_the_latest_test_origin_does_not_change_forecasts` (H1, H4) | Scrambling every value after the fold's last origin (all test targets included) leaves the RF forecasts identical; only the labels change |
| `test_model_inputs_exclude_future_values_and_raw_identifiers` | No plan, oracle, price, marketing, weather, wastage, week-number, supplier or label column; identifiers only as one-hot |
| `test_segment_columns_are_attached_after_prediction` | Discount status is analysis-only; segment values match the panel |
| `test_refit_gives_identical_forecasts` | Same seed gives identical forecasts |
| `test_rf_and_baselines_are_scored_on_identical_rows` | Three models on identical keys per fold and horizon; forecasts finite and ≥ 0; actuals equal the panel; origin = target − *h* |
| `test_metrics_and_diagnostics_are_complete` | Pooled, fold and segment tables; importances sum to 1 per fit; train/test diagnostics present |
| `test_christmas_tables_select_only_weeks_51_and_52` | Christmas tables are restricted to weeks 51–52 |
| `test_rf_pipeline_writes_only_a_new_folder` | Exactly one new folder; refuses to overwrite; manifest records no tuning and no selection |
| `test_baseline_run_is_recorded_unchanged_and_write_blocked` | CP3 run byte-identical and protected |

**Full suite: 193 passed, 0 failed** (177 earlier + 16 new). `test_all_recorded_checksums_still_match` covers every protected file.

---

## 7. Outputs (`outputs/runs/20261021-180522_rf_backtest/`)

| File | Content |
|---|---|
| `predictions.csv` | 103,680 rows (3 models × 2 horizons × 17,280): keys, origin and target, fold, model, actual, forecast, analysis-only segments |
| `metrics/*.csv` | pooled, by_fold, by_target_week, reference_window, christmas_weeks, christmas_combined, excluding_christmas, by_Product_Category, by_Store_ID, by_Region, by_target_holiday, by_target_discounted |
| `comparison_rf_vs_mean4w_by_fold.csv` | WAPE difference and relative change per fold and horizon |
| `training_metadata.csv` | Rows, cut-offs, inputs, fit time, train and test WAPE per fold and horizon |
| `feature_importance_by_fold.csv`, `feature_importance_summary.csv` | Impurity importances per fit; mean, min, max and rank |
| `feature_lists.json` | Pre-encoding S0 feature list; the 106 model inputs per fold |
| `manifest.json` | Versions, configuration and its source, rules, preprocessing, reproducibility check, "no tuning / nothing selected" |

---

## 8. Open points for CP5 (decisions, not actions taken)

1. **H4 Meat instability and `target_month`.** Changing features *because of* these test results would be test-fold tuning. Any remedy needs a pre-agreed rule, assessed on an inner validation split inside each training window. Options include dropping `target_month`, or replacing it with a feature that does not extrapolate.
2. **Christmas.** No S0 model handles weeks 51–52. Options are a documented limitation, or bias reported excluding those weeks.
3. **Provisional gates.** The facts above (H1 −7.1% relative and 6/6 folds; H4 −1.9% relative, 5/6 folds, 9/15 stores, Meat +3.5 points) need to be assessed against the reviewed thresholds and the two-way bootstrap in CP5.
4. **Reproducibility criterion.** Use a 1 × 10⁻⁹ tolerance with `n_jobs=-1`, or run with `n_jobs=1` for bit-exact reruns.
5. **Protect this run** once CP5 is approved, because CP5 will read it.

**Unchanged:**
- `src/dpe/reference_baseline.py` (only its `RF_PARAMS` constant is read)
- the original RF recovery run and all historical runs
- raw and reference data, `legacy/`
- SQLite, Airtable, GitHub and backups
