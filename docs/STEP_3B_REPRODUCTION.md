# Step 3b — Reproducible Random Forest baseline (prepared, not yet run)

Reference: legacy/perishable_project/src/baseline_model.py (unchanged copy).
Port: src/dpe/reference_baseline.py. Entry point: scripts/reproduce_reference_baseline.py.

## Changes from the original
| Area | Original | V2 |
|---|---|---|
| Input paths | Searched data/ then project root; missing files skipped with a warning | Only data/raw via config.raw_path(); SHA-256 verified first; missing file = error |
| Output paths | Wrote outputs/validation_predictions.csv, overwriting each run | New outputs/runs/<run_id>/ only; existing folder = error; every write passes assert_safe_output() |
| IDs | groupby().apply(include_groups=False) dropped Store_ID and Product_ID | groupby().shift()/transform(); IDs kept in data and outputs, still excluded from model inputs |
| Feature values | lags 1,2,4,8; rolling mean 4/8, std 4 on shifted series; calendar; same-week price/discount/marketing/weather | Identical (deliberately, for comparability) |
| Validation | Last 8 weeks, chronological | Identical, plus a hard check that all training weeks precede validation weeks |
| Model | RandomForestRegressor(300, depth 12, random_state=42) | Identical; fails loudly if scikit-learn is missing |
| Metrics | MAE, RMSE, R2 (printed only) | Same, plus WAPE and bias; saved to metrics.json |
| Outputs | WeekDate, Units_Sold, pred_naive, pred_rf | Store_ID, Product_ID, WeekDate, Units_Sold, pred_naive, pred_rf + run_manifest.json |

## Known limitations retained until Step 3c
- One-week-ahead lags only (no 4-week origin-based forecast).
- Week_Number_wx dummies from the weather join.
- Same-week weather, price, discount and marketing used as inputs.
- Single holdout; no rolling backtest.

The Oct 2025 scores are reference benchmarks only; results are not forced to match.

## Verified reproduction run — 21 Oct 2026

Run folder: outputs/runs/20261021-133846_reference_rf/ (created 2026-10-21 13:39:10 local; preserve unchanged)
Environment: Python 3.11.9, pandas 2.3.3, numpy 2.3.4, scikit-learn 1.7.2.
Inputs: all 5 raw files matched docs/CHECKSUMS.sha256 at run time.
Split: train 2024-02-26 to 2024-10-28 (25,920 rows); validation 2024-11-04 to 2024-12-23 (5,760 rows; 15 stores x 48 products x 8 weeks, keys unique). 105 model features.

| Model | MAE | RMSE | R2 | WAPE | Bias |
|---|---|---|---|---|---|
| Random Forest | 487.237 | 714.034 | 0.635 | 27.939% | -7.03% |
| Naive (last week) | 597.105 | 878.517 | 0.448 | 34.239% | -3.21% |

Comparison with Oct 2025 reference (data/reference/validation_predictions.csv): rows aligned (5,760 = 5,760; same dates and actuals);
naive predictions identical (max abs diff 0.0); Random Forest max abs diff 2.7e-12 (floating-point level). The original result is reproduced.

### Run file checksums (SHA-256)
```
23ec7b22baa3f6dc44f18538060dcfbe54bd938c49e19fa29c60796c857d716d  outputs/runs/20261021-133846_reference_rf/metrics.json
4d27cff319791617f68fcc60fecf4b1ff4f68b94f5b0094b2517e1b39dbcae6b  outputs/runs/20261021-133846_reference_rf/run_manifest.json
22555b7c016d4af9911ca535dabec4465223331d3351d94a922d782bb64dd507  outputs/runs/20261021-133846_reference_rf/validation_predictions.csv
```
