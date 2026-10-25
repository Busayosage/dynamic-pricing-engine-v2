# Step 4B, checkpoint 3: baseline forecasts and chronological backtest folds

- **Status:** CP3 is implemented and run. **No machine-learning model was trained or tuned.** CP4 and CP5 are not started and await approval.
- **Date:** 2026-10-21
- **Builds on:** [STEP_4B_CP1_CP2_IMPLEMENTATION.md](STEP_4B_CP1_CP2_IMPLEMENTATION.md) and [STEP_4A_FORECAST_DESIGN.md](STEP_4A_FORECAST_DESIGN.md) (including the section 14 amendments).
- **Results run:** `outputs/runs/20261021-175029_baseline_backtest/`

> The dataset is *apparently synthetic; provenance unconfirmed*. The baselines describe this dataset only. **Acceptance thresholds remain provisional** (design section 14) and are not applied here.

---

## 1. What was built

| Item | Implementation |
|---|---|
| Panel run protected | `20261021-171758_forecast_panel` added to the protected paths (`config.FORECAST_PANEL_RUN_DIR`); its 3 files recorded in `CHECKSUMS.sha256`; writes blocked (tested) |
| Verified input | `panel.load_verified_panel()` checks the panel run's checksums, rebuilds the panel from the checksum-verified raw files, and confirms the two are equal value for value before use |
| Folds | `backtest.make_folds()`: six non-overlapping 4-week target blocks covering weeks 29–52 exactly once (table below) |
| Training boundary | `backtest.fold_plan()`. For fold start *b* and horizon *h*: training targets ≤ *b* − *h* (the earliest test origin); training origins between 8 and *b* − 2*h*. `assert_fold_boundaries()` rejects any later training target or origin, any shared row, and any test row whose origin ≠ target − *h*. |
| Baselines | `baselines.py`. **last_week** = units in the origin week *T* (`y_t0`). **mean_4w** = mean units of weeks *T*−3…*T* (`mean_4`). Both read only the leakage-tested history features at the origin, so H4 never sees weeks *T* + 1…*T* + 3. |
| Keys on every prediction | `fold`, `Store_ID`, `Product_ID`, `origin_week`, `origin_date`, `target_week`, `target_date`, `horizon`, `model`, `actual`, `forecast` |
| Identical populations | `assert_identical_populations()`: both baselines have the same rows in every fold and horizon. H1 and H4 share the same 17,280 store-product-target rows. |
| Metrics | `evaluate.py`: MAE, RMSE, WAPE % and signed Bias % (negative = under-forecast). Pooled values are computed over all rows, never as an average of fold values. |
| Original-naive check | `reference_check.py`: row-by-row comparison, restricted to definitions that are equivalent (section 4) |
| Pipeline and entry point | `pipeline.run_baseline_backtest()`; `scripts/run_baseline_backtest.py`. Writes a new folder only. |

### Folds and training boundaries

| Fold | Target weeks | H1: last training target / origin | H4: last training target / origin | H1 / H4 pairs available for training (CP4) |
|---|---|---|---|---|
| F1 | 29–32 (15 Jul – 5 Aug) | 28 / 27 | 25 / 21 | 14,400 / 10,080 |
| F2 | 33–36 | 32 / 31 | 29 / 25 | 17,280 / 12,960 |
| F3 | 37–40 | 36 / 35 | 33 / 29 | 20,160 / 15,840 |
| F4 | 41–44 | 40 / 39 | 37 / 33 | 23,040 / 18,720 |
| F5 | 45–48 | 44 / 43 | 41 / 37 | 25,920 / 21,600 |
| F6 | 49–52 (2 – 23 Dec) | 48 / 47 | 45 / 41 | 28,800 / 24,480 |

- **Test rows:** each fold scores 2,880 rows (720 series × 4 target weeks) per horizon and model.
- **Training rows:** only counted in CP3. Nothing was trained.

---

## 2. Baseline results

### H1 (one week ahead)

| Fold | last_week WAPE | last_week Bias | mean_4w WAPE | mean_4w Bias |
|---|---|---|---|---|
| F1 | 34.08% | +0.43% | 27.97% | +2.36% |
| F2 | 34.97% | +0.59% | 28.50% | +0.98% |
| F3 | 33.42% | −1.06% | 26.58% | −1.91% |
| F4 | 33.56% | −0.74% | 26.68% | −2.19% |
| F5 | 34.22% | −0.56% | 27.38% | −1.19% |
| F6 | 34.25% | −5.56% | 29.94% | −9.56% |
| **Pooled (17,280 rows)** | **34.08%** | **−1.29%** | **27.89%** | **−2.17%** |

| H1 pooled | MAE | RMSE |
|---|---|---|
| last_week | 550.1 | 802.5 |
| mean_4w | 450.2 | 654.5 |

### H4 (four weeks ahead)

| Fold | last_week WAPE | last_week Bias | mean_4w WAPE | mean_4w Bias |
|---|---|---|---|---|
| F1 | 36.00% | +4.26% | 30.74% | +4.36% |
| F2 | 35.90% | +1.21% | 30.11% | +2.53% |
| F3 | 34.09% | −2.34% | 27.09% | −1.69% |
| F4 | 32.78% | −3.43% | 26.72% | −4.71% |
| F5 | 33.55% | −2.04% | 28.15% | −3.35% |
| F6 | 37.38% | −11.53% | 33.15% | −12.13% |
| **Pooled (17,280 rows)** | **34.99%** | **−2.63%** | **29.41%** | **−2.85%** |

| H4 pooled | MAE | RMSE |
|---|---|---|
| last_week | 564.8 | 822.9 |
| mean_4w | 474.7 | 686.6 |

**Best baseline: mean_4w**, for both horizons and in all 12 fold-horizon combinations. It becomes the benchmark the CP4 models must beat.

### Reference window (target weeks 45–52, the original holdout)

| Horizon | Model | MAE | RMSE | WAPE | Bias |
|---|---|---|---|---|---|
| H1 | last_week | 597.105 | 878.517 | 34.239% | −3.21% |
| H1 | mean_4w | 501.168 | 741.932 | 28.738% | −5.63% |
| H4 | last_week | 620.502 | 917.511 | 35.580% | −7.08% |
| H4 | mean_4w | 537.132 | 792.330 | 30.800% | −8.01% |

---

## 3. Leakage and integrity tests (`tests/test_forecast_backtest.py`, 20 tests)

| Test | What it proves |
|---|---|
| `test_default_folds_cover_weeks_29_to_52_without_overlap` | Six folds, contiguous, each target week exactly once; invalid splits rejected |
| `test_fold_plan_training_cutoffs` (H1, H4) | For every fold: last training target = start − *h* < start; last training origin = start − 2*h*; F1 cut-offs 28 (H1) and 25 (H4) |
| `test_boundaries_hold_including_the_edge_week` (H1, H4) | On a 30-week synthetic panel, the last training target equals the earliest test origin exactly and the next week is excluded; test origins = target − *h* |
| `test_boundary_check_detects_leaks` (H1, H4) | A training row one week too late, overlapping train/test rows, or a shifted origin all raise errors |
| `test_baselines_use_origin_week_values_only` (H1, H4) | Each forecast equals the panel's units at *T* (last_week) or the mean of *T*−3…*T* (mean_4w), recomputed independently |
| `test_baselines_ignore_intervening_and_target_weeks` (H1, H4) | Scrambling weeks *T* + 1…*T* + *h* leaves every forecast unchanged. For H4 this covers the three intervening weeks and the target. |
| `test_identical_scoring_populations_and_same_targets` | Both models share identical rows per fold and horizon; H1 and H4 share target rows; a missing or duplicated row is detected |
| `test_prediction_keys_preserved` | Keys present on every prediction; target_date = origin_date + *h* weeks |
| `test_metric_formulas`, `test_pooled_metrics_use_all_rows_not_fold_averages` | Hand-checked MAE, RMSE, WAPE and Bias; pooled values recomputed from rows |
| `test_reference_check_confirms_equivalence_and_reports_differences` | On synthetic files: equivalence confirmed when equal; a one-row difference or a missing row is reported, not hidden |
| `test_real_backtest_populations` | Real data: 12 fold-horizon plans × 2,880 rows × 720 series; 69,120 predictions |
| `test_real_h1_naive_equals_original_benchmark_row_by_row` | Real data: 5,760 of 5,760 rows identical; MAE and WAPE equal the verified reference naive |
| `test_pipeline_writes_only_a_new_folder` | Writes exactly one new folder; refuses to overwrite; manifest records no trained models |
| `test_forecast_panel_run_is_recorded_unchanged_and_write_blocked` | Panel run byte-identical; writes blocked |

**Full suite: 177 passed, 0 failed** (157 earlier + 20 new). `test_all_recorded_checksums_still_match` confirms that every protected file is byte-identical.

---

## 4. Original naive benchmark: equivalence check

**Where equivalence can hold.** The original naive forecast for target week *t* is `lag_1`, the units sold in week *t* − 1 of the same series. That is exactly the H1 last_week baseline: origin *t* − 1, target *t*, same input.

**Scope of the check.** It applies only to **H1 targets 45–52**, the original holdout.

**Result** (`reference_naive_check.json`):

| Comparison | Result |
|---|---|
| Keyed match with the V2 reproduction (`outputs/runs/20261021-133846_reference_rf/validation_predictions.csv`) on Store_ID, Product_ID and target date | 5,760 of 5,760 rows matched; 0 unmatched on either side; actuals equal; every origin = target − 1 week; **forecast differences: 0 rows, max 0.0** |
| Positional match with the Oct 2025 original (`data/reference/validation_predictions.csv`) | That file has **no Store_ID or Product_ID**, so it can only be compared by row position with the reproduction (verified aligned in Step 3B). 5,760 rows; dates, actuals and naive forecasts identical (max difference 0.0). |
| Metrics | H1 last_week on weeks 45–52: MAE 597.105, WAPE 34.239%, identical to the original naive |

**Verdict.** The H1 last-week baseline is **equivalent to the original naive benchmark** for target weeks 45–52. Neither historical file was modified.

**Not comparable, and not claimed:**
- **H4:** the original has no four-week-ahead forecast.
- **mean_4w:** the original had no such baseline.
- **Folds F1–F4:** the original holdout covered weeks 45–52 only.

---

## 5. Unexpected findings

1. **A four-week average almost matches the original Random Forest.**
   - On the original holdout, H1 mean_4w scores **28.74% WAPE** against the reference RF's **27.94%**. That gap is only 0.8 points, even though the RF used same-week discount, price, marketing and actual weather.
   - **Reading:** weekly sales are dominated by week-to-week variation that recent history cannot predict. The EDA saw the same thing: naive WAPE is flat at 33–36% in every week, and price behaves like noise.
   - **For CP4:** the realistic bar is mean_4w (27.9% H1, 29.4% H4 pooled), not 27.9% "from the RF". Gains from a deployable S0 model may be small.
2. **Discounted weeks are systematically under-forecast.** The baselines cannot know about a coming discount:

   | H1 mean_4w | Bias |
   |---|---|
   | Discounted target weeks (23% of rows) | **−16.0%** |
   | Undiscounted target weeks | **+2.7%** |

   Undiscounted weeks are over-forecast because recent discount weeks inflate the average. H4 shows the same pattern (−16.6% / +2.0%). This is the gap that scenario S1 (a known discount plan) is designed to measure.
3. **The Christmas weeks carry most of the bias.**
   - Weeks 45–50 have mean_4w bias between −3.2% and +0.3%.
   - **Weeks 51–52** have bias of −15% to −17% (H1) and −19% to −21% (H4), and WAPE of 31–36%.
   - That pulls F6 bias to −9.6% (H1) and −12.1% (H4), both beyond the provisional ±10% per-fold limit for H4.

   No baseline can anticipate the December rise. The provisional gates need review against this before CP5.
4. **The horizon costs little.** H4 mean_4w is only 1.5 WAPE points worse than H1 pooled (29.4% vs 27.9%). In F4 and F5, H4 last_week even scores slightly better than H1. This fits a noise-dominated series, where one older week is about as informative as the latest one. It is not a sign of leakage: the H4 tests prove weeks *T* + 1…*T* + 3 are never read.

---

## 6. Assumptions and open issues

1. **Assumptions unchanged** from CP1–CP2: the known holiday calendar; all stores' week-*T* sales available at origin *T*; origin week fully observed.
2. **Baselines use S0 only.** They need no plans. Scenarios matter from CP4 onwards.
3. **Provisional gates.** The ±10% per-fold bias gate (G3) looks likely to fail for F6 even for the baselines. The CP5 review should decide whether to judge bias excluding weeks 51–52, or to accept a documented Christmas limitation.
4. **Bootstrap not run yet.** The two-way series × week-block bootstrap (design section 14) is a CP5 item.
5. **Superseded EDA runs** (`…162317_eda`, `…162452_eda`) and the new baseline run are not yet write-protected. I propose protecting the baseline run when CP4 is approved, because CP4/CP5 will compare against it.

---

## 7. Files created or changed

| File | Change |
|---|---|
| `src/dpe/config.py` | Added `FORECAST_PANEL_RUN_ID`/`FORECAST_PANEL_RUN_DIR` to the protected roots |
| `docs/CHECKSUMS.sha256` | Appended the 3 panel-run file hashes |
| `src/dpe/forecast/panel.py` | Added `load_verified_panel()` |
| `src/dpe/forecast/backtest.py` | New: folds, fold plans, train/test selection, boundary assertions |
| `src/dpe/forecast/baselines.py` | New: last_week and mean_4w; identical-population check |
| `src/dpe/forecast/evaluate.py` | New: metrics; pooled, per-fold and reference-window tables |
| `src/dpe/forecast/reference_check.py` | New: original-naive equivalence check |
| `src/dpe/forecast/pipeline.py` | New: baseline backtest orchestration |
| `scripts/run_baseline_backtest.py` | New: entry point |
| `tests/test_forecast_backtest.py` | New: 20 tests |
| `docs/STEP_4B_CP3_BASELINES.md` | New: this document |
| `docs/CHANGELOG.md` | Appended the CP3 entry |

**Run folder** `outputs/runs/20261021-175029_baseline_backtest/`:
- `baseline_predictions.csv`: 69,120 rows
- `folds.csv`
- `metrics_by_fold.csv`, `metrics_pooled.csv`, `metrics_reference_window.csv`
- `reference_naive_check.json`
- `manifest.json`

**Unchanged:**
- `src/dpe/reference_baseline.py` and all EDA code
- raw and reference data, `legacy/`
- every earlier run folder
- SQLite, Airtable, GitHub, the original projects and backups

**Re-run** (creates a new folder; never overwrites):

```
.venv\Scripts\python.exe scripts\run_baseline_backtest.py
```
