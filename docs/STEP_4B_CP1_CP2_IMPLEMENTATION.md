# Step 4B, checkpoints 1–2: forecasting panel and leakage-safe features

- **Status:** CP1 and CP2 are implemented and tested. **No model has been trained.** CP3–CP5 are not started and await approval.
- **Date:** 2026-10-21
- **Design basis:** [STEP_4A_FORECAST_DESIGN.md](STEP_4A_FORECAST_DESIGN.md), including the amendments recorded in its section 14.

> The dataset is *apparently synthetic; provenance unconfirmed*. Recorded `Price` appears to be after discount, but this is undocumented. Wastage is a fixed product ratio of units sold.

---

## 1. What was built

### CP1: Groundwork
| Item | Result |
|---|---|
| Final EDA run protected | `20261021-162605_eda` added to `INTERNAL_PROTECTED_ROOTS` in `src/dpe/config.py`; its 60 files recorded in `docs/CHECKSUMS.sha256`; write attempts raise `UnsafeWriteError` (tested) |
| Clean weekly panel | `dpe.forecast.panel.build_panel()`: one row per Store_ID × Product_ID × WeekDate, from the checksum-verified V2 raw files through the same joins as the EDA |
| Validation | 37,440 rows = 720 series × 52 consecutive Monday weeks (2024-01-01 to 2024-12-23); 48 products, 15 stores; keys unique and never missing; no missing values |
| Reconciliation | Units 61,482,249 and wastage 4,786,490. Every one of the 52 weekly totals and all 4 category totals match the final EDA run's `weekly_trend.csv` and `category_summary.csv` exactly. |
| Identifiers | `Store_ID`, `Product_ID`, `WeekDate` and a 1-based `week_index` on every row |
| Artefact | `outputs/runs/20261021-171758_forecast_panel/`: `forecast_panel.csv`, `holiday_calendar.csv`, `panel_manifest.json` (input hashes, summary, reconciliation, column roles, assumptions, output hashes) |

### CP2: Leakage-safe features
Every forecast row carries `Store_ID`, `Product_ID`, `origin_week`, `origin_date`, `target_week`, `target_date`, `horizon` and `scenario`, where `target_week = origin_week + horizon`.

**Two horizons share one builder:** H1 (`horizon=1`) and H4 (`horizon=4`). History is anchored at the origin for both horizons, so H4 cannot read weeks *T* + 1 to *T* + 3. Each horizon will get its own model (the direct strategy); predictions are never fed back in as inputs.

**The builder takes three separate inputs**, so the information boundary is built in:
1. **History:** panel rows observed up to the origin. Every feature is a backward-looking window ending at the origin.
2. **Calendar:** the known-in-advance regional holiday flag, the national-holiday share and the month of the target week.
3. **Plans:** target-week values, used only by scenarios S1–S3.

**Explicit feature list** (`features.feature_columns(scenario)`):

| Group | Features |
|---|---|
| Recent sales (26 history features in total) | `y_t0`, `y_tm1`, `y_tm2`, `y_tm3`, `y_tm7` |
| Rolling | `mean/std/min/max` over 4 and 8 weeks ending at *T*; `ewm_mean` (α = 0.3); `expanding_mean` |
| Trend | `trend_4v4` (last 4 weeks minus the previous 4); `ratio_t0_mean_8` |
| Context at origin | `disc_t0`, `disc_tm1`, `disc_share_4`, `undisc_mean_8` (mean of undiscounted weeks; falls back to the observed 8-week mean); `holiday_t0` |
| Hierarchy at origin | `prod_total_t0`, `prod_total_mean_4`, `store_cat_mean_4`, `series_share_8` |
| Static numeric | `Shelf_Life_Days`, `Store_Size`, `Cold_Storage_Capacity`, `Lead_Time_Days` |
| Static identity (one-hot only) | `Product_ID`, `Store_ID`, `Product_Category`, `Region` |
| Target-week calendar | `target_month`, `target_holiday`, `target_national_holiday_share` |
| S1 | + `plan_discount` |
| S2 | + `plan_discount`, `plan_marketing`, `plan_price` |
| S3 (diagnostic, not deployable) | S2 + `oracle_temperature`, `oracle_rainfall` |

**Never used** in any scenario:
- wastage, at any lag
- `Week_Number` and week-of-year
- `Supplier_ID`
- raw target-week `Price`, `Discount_Percent`, `Marketing_Spend` or weather columns

**Enforcement.** `check_feature_frame()` rejects forbidden columns, undeclared columns, duplicate forecast rows and mis-aligned target weeks. `model_matrix()` turns identifiers into fixed one-hot columns, so no identifier is ever a continuous number. It rejects unknown categories and non-finite values.

**Eligibility.** An origin needs 8 observed weeks (*T* ≥ 8), so the first target is week 9 for H1 and week 12 for H4.
- Origins without enough history are **excluded, not padded**.
- A missing week or a missing value makes the builder **raise an error**. Nothing is filled with zero.
- On the real data this gives 31,680 H1 rows (origins 8–51) and 29,520 H4 rows (origins 8–48).

---

## 2. Files created or changed

| File | Change |
|---|---|
| `src/dpe/config.py` | Added `FINAL_EDA_RUN_ID`/`FINAL_EDA_RUN_DIR` to the protected roots |
| `docs/CHECKSUMS.sha256` | Appended the 60 final-EDA-run file hashes |
| `src/dpe/forecast/__init__.py` | New: package |
| `src/dpe/forecast/panel.py` | New: `build_panel`, `validate_panel`, `reconcile_with_eda`, `holiday_calendar`, `write_panel_run`, column roles |
| `src/dpe/forecast/scenarios.py` | New: S0–S3 definitions, target-week inputs, deployability and assumptions |
| `src/dpe/forecast/features.py` | New: `history_features`, `build_features`, `attach_target`, `check_feature_frame`, `static_categories`, `model_matrix` |
| `scripts/build_forecast_panel.py` | New: CP1 entry point (verify inputs, build, validate, reconcile, save) |
| `tests/test_forecast_features.py` | New: 33 synthetic-panel tests |
| `tests/test_forecast_panel.py` | New: 10 real-data and integrity tests |
| `docs/STEP_4B_CP1_CP2_IMPLEMENTATION.md` | New: this document |
| `docs/STEP_4A_FORECAST_DESIGN.md` | Appended section 14 (amendments); no earlier text changed |
| `docs/DECISIONS.md`, `docs/CHANGELOG.md` | Appended entries |

Unchanged:
- `src/dpe/reference_baseline.py`, the EDA code, raw and reference data, `legacy/`
- every existing run folder
- SQLite, Airtable, GitHub, the original projects and backups

---

## 3. Leakage tests (all passing)

| Test | What it proves | Horizons and scope |
|---|---|---|
| `test_truncation_invariance` | Features at origin *T* are identical, to the exact value, whether or not weeks after *T* exist in the history | H1, H4 × S0–S3, every eligible origin (synthetic) |
| `test_real_truncation_invariance_at_boundaries` | The same on the real data at the first eligible origin (8), an early backtest origin (28) and the last labelled origin (51 / 48) | H1, H4 × S0, S1 |
| `test_future_scrambling_does_not_change_s0` | Replacing every weekly value after *T* (units, wastage, price, discount, marketing, weather) with random numbers leaves S0 features unchanged | H1, H4, every origin |
| `test_future_scrambling_changes_only_declared_plan_inputs` | Under S2, scrambling the future changes only `plan_*` columns. The test also confirms a change is detected when one is allowed. | H1, H4 |
| `test_target_week_values_do_not_reach_s0` | Changing only target-week price, discount, marketing and weather leaves S0 unchanged | H4 |
| `test_wastage_is_never_read` | Rewriting all wastage values leaves every feature unchanged, even in S3 | H1, H4 |
| `test_origin_target_alignment_and_lags` | `target = origin + h`; `y_t0` = sales in the origin week (not week *T* + *h* − 1); exact values for every lag and window | H1, H4 |
| `test_boundary_origins_and_targets` | First origin 8; first target 9 / 12; last target = last calendar week; origin 7 gives no row; an origin whose target is off the calendar gives no row | H1, H4 |
| `test_hierarchy_features_use_origin_week_only` | Product totals and series share use only rows dated ≤ *T* | H1 |
| `test_missing_week_raises_instead_of_zero_fill`, `test_no_missing_history_on_eligible_rows` | Gaps and NaNs raise errors; eligible rows have complete history | H1, H4 |
| `test_check_rejects_forbidden_or_undeclared_columns` | Wastage, raw discount, `Week_Number_wx_*`, `Supplier_ID` and undeclared columns are rejected | — |
| `test_model_matrix_uses_identifiers_only_as_one_hot` | Identifiers are one-hot only; fixed column order for any subset; unknown categories rejected | — |
| `test_final_eda_run_is_recorded_unchanged_and_write_blocked`, `test_all_recorded_checksums_still_match` | Raw data, reference data, legacy copies and all three protected runs are byte-identical | — |

**Mutation check.** This confirms the tests can actually fail. A throwaway script outside the repository injected three deliberate leaks into the feature builder:
- next-week sales
- a whole-series mean
- wastage

The truncation and scrambling tests caught the first two. The wastage test caught the third; truncation alone cannot catch it, because past wastage counts as history.

**Test results:** the full suite passes, **157 passed, 0 failed** (114 existing + 43 new).

---

## 4. Assumptions

1. **Holiday calendar known in advance.** `Holiday_Flag` comes from `weather_data.csv` but is treated as a published regional calendar. It is recorded in the panel manifest and in scenario S0.
2. **Hierarchy features need all stores' sales for the origin week.** `prod_total_*` and `series_share_8` assume every store's sales for week *T* are available when forecasting at *T*. Otherwise these features must be lagged one more week.
3. **Plans in backtests.** For S1–S3, the recorded target-week values stand in for supplied plans. S3 uses actual weather as a perfect forecast and is diagnostic only.
4. **Price semantics.** `plan_price` is the recorded price, which appears to be after discount (undocumented).
5. **Origin semantics.** Sales for week *T* are fully observed when the forecast for *T* + *h* is made.

---

## 5. Unresolved issues

1. **Calendar beyond the data.** Forecasts for targets after 2024-12-23 cannot be built, because no calendar exists for 2025. Deployment needs a calendar source.
2. **Christmas run-up is unlearnable.** Weeks 50–52 never appear in any training fold, and week-of-year is deliberately excluded. The F6 fold is expected to be hard. This is unchanged from the design.
3. **`expanding_mean` changes meaning over time.** It averages 8 weeks at origin 8 and 51 weeks at origin 51. This is not leakage, but the feature drifts within the year.
4. **R0 replica not built yet.** It will be created at CP4 from `dpe.reference_baseline`, which stays untouched.
5. **Not yet write-protected:** the superseded EDA runs (`…162317_eda`, `…162452_eda`) and the new panel run. I propose protecting the panel run at CP3, once it is the agreed backtest input.
6. **Acceptance thresholds remain provisional** (design section 14). They will be reviewed with the backtest results.

---

## 6. How to re-run

```
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe scripts\build_forecast_panel.py
```

The second command always creates a new panel run folder and never overwrites.
