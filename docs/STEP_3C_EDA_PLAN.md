# Step 3C — Full EDA: implementation plan (PROPOSED, not executed)

Inputs: V2 data/raw only (checksum-verified). Outputs: a new outputs/runs/<YYYYMMDD-HHMMSS>_eda/ folder.
Environment: existing .venv (no new packages: pandas, numpy, scipy, statsmodels, matplotlib, seaborn, ipykernel).

## Pre-inspection facts that shape the EDA
- 37,440 sales rows = 48 products x 15 stores x 52 weeks (2024 only). One year means within-year patterns only; annual seasonality cannot be separated from trend.
- weather_data has 7 regions; "Wales" has no stores (unused, to be reported).
- Price differs across all 15 stores for the same product-week and varies widely within products (median CV ~39%). Whether Price is before or after discount is undocumented (price-discount corr -0.10).
- Waste rate (waste / (sold + waste)) ranges 2.1%-13.0% with the 95th percentile equal to the maximum: a hard cap at 13%.
- Discounts: 6 levels (0-25%), 23% of rows discounted.
- These patterns suggest a simulated teaching dataset; findings describe this dataset, not real shopper behaviour.

## Proposed files
| File | Contents |
|---|---|
| src/dpe/eda/__init__.py | package |
| src/dpe/eda/data.py | load_raw(), build_analysis_frame(): joins, ISO WeekDate, revenue, waste_rate, flags |
| src/dpe/eda/quality.py | profile_table, missing/duplicates, key completeness, referential integrity, range checks |
| src/dpe/eda/analysis.py | weekly_trend, category_summary, product_ranking, store_region_summary, wastage_summary, discount_summary, price_relationship, marketing_relationship, weather_relationship, operations_summary, outlier_flags |
| src/dpe/eda/stats.py | spearman_with_ci, within_group_demean, kruskal_effect, mann_whitney_effect, ljung_box, bh_adjust, associational_ols |
| src/dpe/eda/plots.py | one function per chart; returns a Figure; consistent labels and titles |
| src/dpe/eda/report.py | assembles findings.json and a draft findings markdown |
| scripts/run_eda.py | orchestrator: verify inputs -> tables, charts, stats -> new EDA run folder + eda_manifest.json |
| notebooks/01_eda.ipynb | narrative notebook on the .venv kernel; calls the functions above, no logic of its own |
| tests/test_eda_quality.py, test_eda_analysis.py, test_eda_stats.py, test_eda_outputs.py | automated checks |
| docs/EDA_FINDINGS.md | business findings report, written after the run is reviewed |
| config.py (small change) | add the verified run folder 20261021-133846_reference_rf to protected paths |

## Analyses and charts
| Area | Tables / checks | Charts |
|---|---|---|
| Structure & quality | dtypes, nulls, duplicates, 48x15x52 completeness, ID integrity, ranges, waste > sold, unused Wales | completeness heatmap (store x week) |
| Weekly trends & seasonality | weekly totals, 4-week rolling mean, month and week-of-year profiles, holiday vs non-holiday | total units and wastage by week (holiday weeks shaded); category index (week 1 = 100); ACF of weekly totals |
| Products & categories | units, revenue, waste rate by category; product ranks; Pareto share | category bars; top/bottom 10 products; Pareto curve; weekly-units boxplot by category |
| Stores & regions | units, revenue, units per 1,000 sq ft, waste rate by store and region | store bars coloured by region; region comparison |
| Wastage | waste units and rate by category, product, store, month; cap check | waste-rate histogram (13% cap marked); category x month heatmap |
| Price | within-product price vs units (product-demeaned, log-log binned) | binned scatter by category; price distribution by category |
| Discount | descriptive discount lift: raw and within product-store; waste rate by discount | mean units by discount level with 95% CI |
| Marketing | within-product association, binned | binned spend vs units |
| Weather | temperature, rainfall, holiday vs units by category | binned temperature vs units by category |
| Shelf life, suppliers, operations | waste rate vs shelf life, supplier lead time and capacity, cold storage | shelf life vs waste rate; waste rate by supplier |
| Outliers | robust z-score (MAD > 3.5) per store-product series; IQR cross-check | outlier count by week; top-20 table |

## Statistical approach and wording rules
- Within-product comparisons (demeaning by product or product-store) to avoid mixing cheap and expensive items.
- Spearman correlations with 95% confidence intervals; Kruskal-Wallis / Mann-Whitney with effect sizes (epsilon squared, rank-biserial). With 37,440 rows almost everything is "significant", so effect sizes lead.
- Rows from the same series are not independent: group tests run on store-product aggregates; regressions use cluster-robust errors by product.
- Ljung-Box on weekly totals; Benjamini-Hochberg correction across the test family.
- One associational OLS (log units on log price, discount, marketing, weather, holiday + product, store, week effects) labelled "conditional association", not elasticity.
- Report structure: What the data shows | Possible explanations (hypotheses) | What we cannot conclude.
- "Discount lift" is always called descriptive lift, never price elasticity. Price elasticity is deferred to a dedicated later step.

## Validation tests
1. Real-data invariants: 37,440 rows; unique keys; full 48x15x52 grid; no nulls; referential integrity; waste_rate within [0, 1].
2. Reconciliation with the legacy notebook: total units 61,482,249; total wastage 4,786,490; mean units 1,642.15; discount means (0% = 1,574.22, 25% = 2,382.44).
3. Synthetic-fixture unit tests: totals reconcile; waste rate is a ratio of sums (not a mean of ratios); demeaning is correct; an injected spike is flagged and normal points are not; correlation sign and confidence-interval coverage on known data.
4. Output safety: EDA writes only to a new run folder; writes to the verified run folder are refused; its checksums are unchanged; reference copies are unchanged.
5. Charts: each plot function returns a Figure with a title and axis labels; saved PNGs are non-empty (Agg backend).
6. Notebook (static): valid JSON, uses dpe functions, no absolute paths, no credentials.
7. Wording guard: the generated discount section never uses "elasticity".

## Execution order (each needs approval)
C1 write modules + tests -> C2 run tests -> C3 run EDA -> C4 review notebook and charts -> C5 write docs/EDA_FINDINGS.md.
Pending housekeeping: .gitignore additions (.pytest_cache/, .coverage, htmlcov/, .env.* with !.env.example, *.sqlite*, *.db-journal, *.db-wal).
