# Step 5B-1: forecast contract (v1.0)

- **Status:** complete. **No model was retrained, no forecast changed, and no database created.** Inventory, waste-risk and pricing are not implemented. **Awaiting review.**
- **Date:** 2026-10-22
- **Contract run** (protected): `outputs/runs/20261022-081926_forecast_contract/`
- **Code:** `src/dpe/decision/forecast_contract.py`
- **Entry point:** `scripts/build_forecast_contract.py`
- **Tests:** `tests/test_forecast_contract.py`

> The data is *apparently synthetic; provenance unconfirmed*. The forecasts are **research candidates, not production models** (DECISION 17).

---

## 1. What the contract is

The contract is **one standard table that every later module reads**: inventory, waste-risk, pricing, the database and the dashboard. Each row is one forecast: *for this store and product, made at the end of this week, for this future week*.

| Horizon | Method (approved) | Source (protected, not refitted) | Pooled backtest WAPE |
|---|---|---|---|
| H1 (1 week ahead) | Random Forest, S0 | `20261021-180522_rf_backtest` | 25.92% |
| H4 (4 weeks ahead) | Four-week moving average | `20261021-175029_baseline_backtest` | 29.41% |

CatBoost is not in the contract (exploratory only, DECISION 21).

**Coverage:**
- Target weeks 29–52 of 2024, all 720 store-product series.
- **17,280 rows per horizon**, 34,560 in total.
- H1 rows match the protected predictions **exactly**, and so do H4 rows. This is tested row by row.

## 2. Two files: what you knew, and what happened

| File | Contains | Available when the decision is made? |
|---|---|---|
| `forecast_contract.csv` | Forecast, uncertainty bounds, last observed sales, as-of reference price, known calendar, risk and limitation codes | **Yes.** Every field uses only information from the origin week or earlier, plus the published holiday calendar. |
| `forecast_replay_evaluation.csv` | Sales actually observed in the target week, error, whether the sales fell inside the bounds, whether the week was discounted | **No: replay only.** Used for evaluation; never an input to a decision. |

The two files share the same keys (model, horizon, store, product, origin week, target week). The contract file never contains replay fields; validation rejects it if it does.

## 3. Contract fields (`forecast_contract.csv`, fixed order)

| Field | Meaning |
|---|---|
| `contract_version` | `1.0` |
| `forecast_run_id`, `source_run_id` | This contract run; the protected run the forecast came from |
| `model_name`, `model_role`, `forecast_method` | `random_forest` / `H1_research_candidate` / `RF_S0_300T_D12_SEED42`, or `mean_4w` / `H4_research_candidate` / `MEAN_4W` |
| `horizon_weeks`, `scenario` | 1 or 4; `S0` (no plans) |
| `store_id`, `product_id`, `product_category`, `region` | Identifiers and static attributes |
| `origin_week`, `origin_date` | The last week with known sales: the decision point (Monday date) |
| `target_week`, `target_date` | The week being forecast; `target = origin + horizon` |
| `predicted_units` | Forecast of **units sold** in the target week |
| `lower_p10_units`, `median_p50_units`, `upper_p90_units` | Uncertainty bounds (section 4). Empty when unavailable. |
| `uncertainty_status` | `AVAILABLE` or `UNAVAILABLE_INSUFFICIENT_HISTORY` |
| `uncertainty_method`, `uncertainty_error_target_weeks`, `uncertainty_n_errors` | Method code; which past target weeks the errors came from; how many errors |
| `last_observed_units` | Units sold in the origin week |
| `reference_price_asof` | Median implied pre-discount price, Price / (1 − discount), over weeks ≤ origin |
| `target_holiday_calendar` | Regional holiday flag for the target week (a known-in-advance calendar; assumption) |
| `risk_flags` | Row-specific warnings (section 5) |
| `limitation_codes` | The standing warnings (section 5) |
| `unit` | `units_sold_per_week` |
| `provenance`, `dataset_label`, `status` | `PROV_V1`, `SYNTHETIC_UNCONFIRMED`, `RESEARCH_CANDIDATE_NOT_PRODUCTION` |

Every code is explained in `contract_manifest.json` → `code_dictionary`. The manifest also records field availability, method details, validation results and the contract file's SHA-256.

## 4. Uncertainty bounds: how they are calculated

- **What is used.** For a forecast made at origin week *T*, the engine looks only at **past forecasts of the same model, horizon and product category whose target week is ≤ *T***. Those sales were already known at *T*.
- **How the bounds are set.**
  1. It takes the 10th, 50th and 90th percentiles of actual ÷ forecast across those past forecasts.
  2. It multiplies the new forecast by them.
- **Minimum history.** At least **4 past target weeks** are required. Otherwise the bounds are left **empty** with `uncertainty_status = UNAVAILABLE_INSUFFICIENT_HISTORY`. Nothing is borrowed from another model, another horizon, or later weeks.
- **Amendment to the Step 5A design.** Section 4.1 of the design proposed a fallback for the first RF fold. It was replaced by "unavailable", as instructed for 5B-1.

| Horizon | Rows with bounds unavailable | Origins affected | First origin with bounds |
|---|---|---|---|
| H1 | **2,880** (16.7%) | 28–31 (target weeks 29–32) | 32, using errors from target weeks 29–32 |
| H4 | **5,040** (29.2%) | 25–31 (target weeks 29–35) | 32 (target week 36) |

**How good are the bounds?** This uses the replay file, after the fact. It shows how often actual sales fell inside p10–p90; the ideal is about 80%.

| Group | H1 | H4 |
|---|---|---|
| All categories | **78.2%** | **73.4%** |
| Bakery | 75.8% | 65.8% |
| Beverages | 80.8% | 75.7% |
| Dairy | 80.2% | 79.9% |
| Meat | 76.1% | 72.1% |
| Christmas weeks 51–52 only | 66.8% | 56.2% |

- **Pooled coverage is inside the design's 70–90% band for both horizons.**
- **H4 Bakery is below the band, and the Christmas weeks are well below.** The bounds there are too narrow, as the `CHRISTMAS_BIAS` limitation warns.
- **The H1 errors come from several fold models.** The RF was refitted at the start of each test fold, so the error history spans models. The bounds describe the forecasting *process*, not one fixed model.

## 5. Warnings carried on every row

**`limitation_codes`** (the same on every row; documented by the Step 3C–4D evaluations):

| Code | Meaning |
|---|---|
| `SALES_NOT_DEMAND` | Recorded sales may not equal unconstrained demand; stockouts are not recorded |
| `CHRISTMAS_BIAS` | Weeks 51–52 were under-forecast in backtests (Bakery and Meat by up to about 50%); bounds come from earlier weeks |
| `DISCOUNT_WEEK_BIAS` | S0 forecasts don't know planned discounts; discounted weeks were under-forecast by about 15% |
| `WEEKLY_GRANULARITY` | Weekly totals: no daily expiry or stockout timing can be inferred |
| `SYNTHETIC_DATA` | The historical data appears synthetic |
| `RESEARCH_CANDIDATE` | Not approved for production |

**`risk_flags`** (row-specific; all computable at the origin):

| Flag | When |
|---|---|
| `DISCOUNT_STATUS_UNKNOWN_S0` | Every row: the target-week discount plan is unknown |
| `CHRISTMAS_PERIOD` | Target week 51 or 52 |
| `HOLIDAY_TARGET_WEEK` | Holiday calendar flag set for the target week |
| `HOLIDAY_AT_ORIGIN` | The origin week was a holiday, so recent sales may be inflated |
| `UNCERTAINTY_UNAVAILABLE` | Fewer than 4 weeks of errors at the origin |

Whether a target week was actually discounted is **not** in the contract. It cannot be known in advance under S0, and it appears only in the replay file.

## 6. Example: how a store manager would read it

> **Store 505 (North West), White Sandwich Loaf (product 1001, Bakery, 2-day shelf life).**
> Decision made after the week of 28 Oct 2024 (origin week 44). Last week's sales: **1,357**.
>
> | | Next week (4 Nov, H1, Random Forest) | Four weeks ahead (25 Nov, H4, 4-week average) |
> |---|---|---|
> | Forecast | **1,038 units** | **1,191 units** |
> | Likely range (p10–p90) | **635 – 1,477** | **658 – 1,674** |
> | Median | 997 | — |
> | Flags | discount status unknown | discount status unknown; **holiday target week** |
> | Reference price (as of 28 Oct) | £2.39 | £2.39 |
>
> **Reading:**
> - Expect about 1,000 loaves next week. In roughly 8 of 10 similar past cases, sales fell between about 635 and 1,480.
> - Last week's 1,357 was high compared with the forecast. The model does not simply repeat last week.
> - If a promotion is planned for that week, the forecast does not know about it. Discounted weeks have tended to sell about 15% more than forecast.
> - For 25 Nov (a holiday week in this region), the range is wider. Treat it as a planning signal, not a firm number.
> - With a 2-day shelf life, the weekly figure says nothing about which day the bread sells or expires.
>
> **What happened** (replay file; not known on 28 Oct): 1,018 sold, inside the range. The week turned out to be discounted.

## 7. Leakage and integrity checks

| Check | Result |
|---|---|
| Source integrity | Checksums of both protected prediction runs verified before reading; the panel rebuilt from raw and compared with the protected panel |
| Exact alignment | Every contract row joins 1:1 to its protected prediction; `predicted_units` equals the source forecast exactly; H1 is only RF, H4 only mean_4w, no CatBoost |
| Future scrambling | All sales, prices, discounts, marketing and weather after a cut-off, *and* all prediction actuals after it, replaced with random values. Every contract row with origin ≤ cut-off is unchanged (three cut-offs). |
| As-of uncertainty | The last error week is ≤ the origin for every row; the quantiles were recomputed independently for a sample row |
| No borrowing | H1 bounds are unchanged when H4 errors are altered |
| As-of reference price and last sales | Recomputed from weeks ≤ origin |
| Mutation check (outside the repository) | Letting the bounds see errors up to the target week, or using a whole-year reference price, both made the scrambling test fail |
| Validation | Columns and order, unique keys, approved model per horizon, target = origin + horizon, Monday dates, date gap = horizon, forecasts finite and ≥ 0, bounds present if and only if available, monotone and ≥ 0, no missing fields, known codes, unit, status, label, replay rows matching contract rows. **Nine kinds of violation are each confirmed to be rejected.** |
| Reproducibility | Building twice gives identical tables; the manifest hash equals the file hash |

## 8. Assumptions needing your approval

1. **Holiday calendar known in advance.** The target-week holiday flag comes from the 2024 data. No calendar exists after 23 Dec 2024.
2. **Origin week fully observed.** Sales and prices for week *T* are known when the forecast for *T* + *h* is made.
3. **Reference price definition:** median implied pre-discount price over weeks ≤ origin. This relies on Price appearing to be post-discount, which is undocumented.
4. **Uncertainty settings:** p10/p50/p90; minimum 4 error weeks; pooled by product category.
5. **Unavailable instead of fallback** for early origins (applied here as you instructed). This leaves 2,880 H1 and 5,040 H4 rows without bounds, which downstream modules must handle, for example by escalating.

## 9. Files

| File | Change |
|---|---|
| `src/dpe/decision/__init__.py`, `src/dpe/decision/forecast_contract.py` | New |
| `scripts/build_forecast_contract.py` | New |
| `tests/test_forecast_contract.py` | New (25 tests) |
| `src/dpe/config.py` | Contract run added to the protected paths |
| `docs/CHECKSUMS.sha256` | Contract run's 5 file hashes |
| `docs/STEP_5B1_FORECAST_CONTRACT.md` | This document |
| `docs/DECISIONS.md`, `docs/CHANGELOG.md` | Appended |
| `outputs/runs/20261022-081926_forecast_contract/` | The contract (protected) |
| `outputs/runs/20261022-081829_forecast_contract/` | **Superseded** first build. Identical numbers, but long text repeated on every row (33 MB). Replaced by row codes plus a manifest dictionary. Kept, not used. |
