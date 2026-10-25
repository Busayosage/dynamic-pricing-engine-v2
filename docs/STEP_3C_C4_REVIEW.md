# Step 3C-C4: EDA visual review and quality assurance

- **Run reviewed:** `outputs/runs/20261021-160432_eda` (created 2026-10-21 16:04:41)
- **Review date:** 2026-10-21
- **Status:** review complete. Proposed pipeline changes are listed in section 8 and **have not been applied**. Awaiting approval before any regeneration, Step 3C-C5 or Step 4.

> **Standing caveats.** The dataset is *apparently synthetic; provenance unconfirmed*. Every result below describes this dataset only and may not reflect real shopper behaviour. All relationships are statistical associations. None is presented as a causal effect, and no price elasticity is estimated. The meaning of recorded `Price` relative to `Discount_Percent` is not documented in the source. Section 4.1 gives strong evidence about it, but that evidence is still an inference.

---

## 1. Scope and method

| Item | What was done |
|---|---|
| Charts | All 19 PNGs opened and inspected visually. Axes, scales, labels, notes and interpretation were checked against the underlying tables. |
| Tables | All 31 CSVs loaded. Key totals were recomputed independently from `data/raw/weekly_sales.csv`, and key statistics were re-derived. |
| Narrative | `findings_draft.md`, `findings.json` and `eda_manifest.json` were cross-checked line by line. |
| Investigations | Read-only Python scripts were run on the checksum-verified analysis frame from the session scratchpad. They are not part of the repository, and nothing was written into the project except this report. |
| Integrity | SHA-256 hashes of `outputs/`, `data/`, `database/`, `src/`, `scripts/` and `tests/` (111 files) were taken before the review and compared afterwards (section 10). |

---

## 2. Summary verdict

- **Numbers:** all key totals reconcile exactly with the raw data: 37,440 rows, 61,482,249 units and 4,786,490 wastage units. These figures agree across the weekly, category, product, store and region tables. Every statistic quoted in `findings_draft.md` matches its source table.
- **Narrative:** `findings_draft.md` and `findings.json` are textually identical. The manifest agrees with both. Three interpretations need correcting: **price** (section 5), **waste rate by discount level** (section 4.3) and **"unknown whether Price reflects the discount"** (section 4.1).
- **Charts:** 1 rendering defect (chart 09 legend), 2 charts that can mislead (03 and 13) and 5 minor presentation issues. None of them changes a reported number.
- **Investigations:** three of the four "unusual" results come from **simple, nearly deterministic rules in how the data was generated**:
  - recorded price ≈ random base price × (1 − discount)
  - wastage = ⌊k_product × units sold⌋
  - k_product is set by category and shelf-life tier

  These rules change how the data can be used for pricing and inventory.

---

## 3. Chart review (19 charts)

Severity: **High** = can mislead or is visibly wrong; **Med** = interpretation needs a note; **Low** = cosmetic.

| # | Chart | Axes / scale / labels | Interpretation check | Issue | Sev. |
|---|---|---|---|---|---|
| 01 | Completeness heatmap | OK. Colour scale 0–48 products. | Uniform: all 48 products present in every store-week. Matches `completeness`. | None | – |
| 02 | Weekly units and wastage | Dual axis, both labelled, holiday shading explained. | Peaks match the table: 23 Dec high (1,483,999), 26 Aug low (1,074,503). Wastage tracks units closely, as section 4.3 predicts. | The two axes have different ranges, so the lines look more alike than they are. Acceptable with the existing note. | Low |
| 03 | Category index | Labelled. | The index base is **week 1 (1 Jan), a holiday week** where 60% of rows carry the holiday flag. Bakery's week-1 units (529k) are 155% of its annual weekly mean (342k), so Bakery appears to "fall to 45". Against its own mean the trough is about 70. | The base week distorts the level comparison. Recommend indexing to each category's annual weekly mean. | **High** |
| 04 | ACF of weekly units | OK. 95% band shown. | Only lag 1 (0.57) clearly exceeds the band. The Ljung-Box significance at lags 4 and 8 is driven mainly by lags 1–3. Consistent with the table. | None (could add "lag 1 only" to the note) | Low |
| 05 | Category units with waste | OK. Waste-rate definition in note. | Matches `category_summary`. | None | – |
| 06 | Top / bottom 10 products | OK. | The top 10 are **all Dairy** and the bottom 10 are **all Meat**, so the chart mostly shows category level. | Add a note that the ranking mostly reflects category | Low |
| 07 | Pareto | OK. 80% line. | Draft says "top 20% of products = 33.3% of units". That is actually the **top 10 of 48 (20.8%)**. The top 9 (18.75%) give 30.0%. | Wording precision | Low |
| 08 | Box plot by category | OK. Outliers hidden (stated). | Consistent with category medians. | None | – |
| 09 | Store units per 1,000 sq ft | Values and axis correct: 1,049k units per 1,000 sq ft for store 505 (3,146,686 units / 3.0). | Ranking matches `store_summary`. | **Legend defect:** every legend patch is the same blue, so bars cannot be matched to regions. Cause: `plots.store_units_per_sqft` builds the legend from empty `ax.bar([], [])` calls, which do not carry the colour. | **High** |
| 10 | Region comparison | OK. | Matches `region_summary`. Every bar is labelled "waste 7.2%" (true range 7.18–7.25%) because all stores stock the same 48 products with fixed waste ratios (section 4.3). | "1 stores" grammar. The identical waste labels add nothing; note why instead. | Low |
| 11 | Waste-rate histogram | OK. | Strongly discrete spikes, one per product-level waste ratio (14 values), plus the 13.04% maximum. Supports section 4.3. | Could annotate that the spikes are product ratios | Low |
| 12 | Waste by category × month | OK. | Each row is constant across months: waste rate does not vary over time within a category. Correct, and itself a finding. | None | – |
| 13 | Price relationship | Narrow y-range (97–108) makes small differences look large. | This is the **unadjusted** within-product relationship. Its downward slope is explained by discount weeks, which have both lower recorded prices and higher units (section 4.1). Once discount is held fixed, no slope remains. | Can mislead without a note or an adjusted panel. Recommend adding a "discount-adjusted" panel or note. | **High** |
| 14 | Discount levels | y-axis starts at about 1,550, not 0. CIs shown. | Matches `discount_summary`. | Note that the axis is truncated | Low |
| 15 | Marketing relationship | OK. | The top spend bin (+0.65 log points) jumps to index 113. Lower bins are close to flat. Marketing is unrelated to discount (ρ = 0.007). | None (note that the top bin is a few spike weeks) | Low |
| 16 | Temperature relationship | OK. | Beverages ↑ and Bakery ↓ with temperature, but **after removing month, all categories' correlations are close to 0** (Beverages 0.06, Bakery −0.05). The chart shows seasonality, not a separate temperature association. | Caption should say the pattern largely tracks the season | Med |
| 17 | Shelf life vs waste | Log x-axis, labelled. | Step pattern by category and shelf-life tier. Matches section 4.4. | None | – |
| 18 | Supplier waste | OK. Note says the differences reflect category mix. | Matches `operations_suppliers`. | None | – |
| 19 | Outliers by week | OK. | Peaks in week of 25 Mar (43, Easter), 1 Jan (22), 16 Dec (31) and 23 Dec (27). Matches `outliers_by_week`. | None | – |

---

## 4. Investigations

### 4.1 Near-zero recorded-price association

**Recorded price appears to be the post-discount price.** Within products, the average gap in log recorded price between discounted and undiscounted rows almost exactly equals log(1 − discount):

| Discount | Within-product log-price gap vs 0% | log(1 − d) |
|---|---|---|
| 5% | −0.049 | −0.051 |
| 10% | −0.107 | −0.105 |
| 15% | −0.161 | −0.163 |
| 20% | −0.231 | −0.223 |
| 25% | −0.296 | −0.288 |

After dividing by (1 − d), the implied pre-discount price has the same mean (within ±0.011 log points) and the same spread (SD about 0.49) at every discount level. Within a store-product series, the median recorded price in discount weeks is 86.8% of the price in non-discount weeks.

**The rest of the price variation behaves like row-level noise.** Leaving discount aside:
- Week-to-week autocorrelation of within-product log price in the same series is **0.007**.
- Prices differ between stores in 100% of product-weeks.
- There is a median of 420 distinct prices per product, and the max/min price ratio per product has a median of 5.8×.

The manifest's within-product price-vs-discount ρ (−0.10) is weak only because this noise (SD about 0.5 log points) is much larger than the discount signal (up to 0.29).

**Adjusted regressions** (series + week fixed effects, SEs clustered by product). These reproduce the pipeline result.

| Model | log-price coefficient (95% CI) | Reading |
|---|---|---|
| A: log price only | −0.019 (−0.031 to −0.008) | The small negative association reflects the discount weeks |
| B: log price + discount | +0.008 (−0.002 to 0.017), p = 0.13 | No detectable association once discount is held fixed |
| C: full pipeline model | +0.008 (−0.002 to 0.017), p = 0.12 | Same as the run's `associational_regression` table |
| B by category | Bakery +0.013 (0.002 to 0.024); Beverages, Dairy, Meat CIs include 0 | Bakery's small positive coefficient is not interpretable as demand behaviour |

**Conclusion.** The near-zero adjusted association is explained if recorded price = (noise-like base price) × (1 − discount). Discount carries the demand association, and the base-price component carries none that can be detected. This is an inference from the data pattern. It is not confirmed by documentation.

### 4.2 Unusually strong discount association

- **Size:** after series and week adjustment, log-units gaps against 0% are +0.062 (5%), +0.136 (10%), +0.214 (15%), +0.312 (20%) and +0.415 (25%). In percentages that is about +6%, +15%, +24%, +37% and +51%. The per-point slope rises from 1.24% to 1.66% (convex). The pipeline's linear coefficient is 0.0161 per point.
- **Consistency:** the 25% lift is similar across categories: Bakery 53%, Beverages 47%, Dairy 52%, Meat 54%.
- **Discount timing is unrelated to the obvious confounders:**
  - Share of rows discounted by month is flat (22.2–24.5%).
  - Holiday vs non-holiday: 23.5% vs 23.1%.
  - Weekly total units vs share discounted: ρ = 0.03.
  - Discount vs marketing within series and week: ρ = 0.007.
  - Bakery is somewhat over-represented among discounted rows (28% vs about 20–25%).
- **Reading:** discounts look as if they were assigned independently of season, holidays and marketing, with a large, smooth, category-independent uplift. That is typical of a programmed effect in a data generator. Because no observed confounding exists, the association is "clean" **within this dataset**. It is still not evidence of a causal effect, it says nothing about real shoppers, and it ignores margin, cannibalisation, stock-outs and forward buying, none of which is observed.

### 4.3 Wastage ceiling

- **Rule:** in **99.93%** of rows, `Wastage_Units = floor(k × Units_Sold)`, where *k* is a fixed per-product ratio. Every row is within ±1 unit of this rule. The residual is uncorrelated with units (r = 0.001).
- **14 distinct ratios:** 0.025, 0.040, 0.044, 0.052, 0.060, 0.068, 0.085, 0.090, 0.095, 0.100, 0.105, 0.140, 0.148, 0.150. They are set by category and shelf-life tier:

| Category | Shelf life (days) → k |
|---|---|
| Bakery | 2–3 → 0.150; 4 → 0.148; 5 → 0.140 |
| Meat | 3 → 0.105; 4 → 0.100; 5 → 0.095; 6 → 0.090; 7 → 0.085 |
| Dairy | 8 → 0.068; 10 → 0.060; 12 → 0.052; 14 → 0.044; 16–21 → 0.040 |
| Beverages | 82–356 → 0.025 (all) |

- **The "ceiling":** the maximum waste rate of **13.04% is 0.15 / 1.15**, meaning wastage equal to 15% of units sold. It applies only to the five Bakery products with a 2–3 day shelf life (White Sandwich Loaf, Croissant 4-pack, Cinnamon Rolls, Banana Bread, Donuts). About 80% of their rows sit exactly at 15%; the rest are just below because of the floor rounding. So it is the highest product ratio rather than a cap being hit, and "9.3% of rows at the maximum" is simply the share of rows from those five products.
- **Consequences:**
  - Waste does not vary by month (chart 12), store (7.15–7.27%) or region (7.18–7.25%) except through product mix.
  - **The draft's "waste rate by discount level" (7.0% at 0% vs 7.8–8.0% when discounted) is a category-mix effect.** Bakery, the highest-waste category, is over-represented among discounted rows. Within a single product the ratio does not move with discount; for Beverages it is 0.0245–0.0247, and that tiny drift is floor rounding.
- **Leakage check:** wastage is a same-week function of the target. The Random Forest feature matrix already excludes same-week `Wastage_Units` (`src/dpe/reference_baseline.py:179`). No change is needed.

### 4.4 Shelf-life relationship

- Shelf life vs product waste rate: ρ = −0.96 (n = 48). After removing category means: ρ = −0.73. Within Beverages: ρ = −0.13, because all 12 Beverages products share k = 0.025.
- The relationship is a **step function**, the k tiers in section 4.3, not a noisy trend. Shelf life is unrelated to product volume (ρ = 0.05).
- **Reading:** this describes how waste was generated in this dataset, not an estimate of how shelf life affects waste. The small numbers (48 products, 4–12 distinct shelf-life values per category) and the category overlap make any wider generalisation unsafe.

---

## 5. Corrected price interpretation

The draft hypothesis *"Lower recorded prices may coincide with higher sales"* rests on the small unadjusted correlation (ρ = −0.02). The adjusted regression does not support it. Here is replacement text for the **Price (descriptive)** section, for approval. It has not been applied to the run outputs.

**What the data shows**
- Without adjustment, within-product recorded price and units sold have a very weak negative correlation: ρ = −0.02 (95% CI −0.03 to −0.01, n = 37,440).
- With discount level and product, store and week fixed effects, the log-price coefficient is +0.008 (95% CI −0.002 to 0.017, p = 0.12). That is no detectable association between recorded price and units sold beyond what discount level accounts for.
- Recorded price is lower in discounted weeks by about the discount (for example −0.30 log points at 25%, against log 0.75 = −0.29). This suggests recorded price is the post-discount price.

**Possible explanations (hypotheses)**
- The weak unadjusted correlation is consistent with discounted weeks having both lower recorded prices and higher units.
- The rest of the price variation behaves like row-level noise: week-to-week autocorrelation is about 0.01, and prices differ between stores in every week. That would explain why it shows no association with units.

**What we cannot conclude**
- These results do not show that lower prices increase sales. They also do not show that price has no effect on demand. Prices were not randomly assigned, and the process that generated the data is unknown.
- No price elasticity is estimated. The post-discount reading of `Price` is an inference and is not documented in the source.

Related corrections:
- In the **Discounts** section, replace *"It is unknown whether recorded Price already reflects the discount"* with *"The data strongly suggests recorded Price is after discount (section 4.1); this is not confirmed by documentation."*
- In the same section, add *"Waste-rate differences between discount levels reflect category mix: within a product, the waste ratio does not change with discount."*

---

## 6. Wastage denominators and rounding

**Definition used everywhere in the run:** waste rate = wastage / (units sold + wastage). This holds for the row-level `waste_rate` column (checked exactly), the pooled category, region, store, supplier and discount figures, and charts 05, 10, 11, 12, 17 and 18. **No inconsistency in denominators was found.**

| Measure | Overall | Bakery | Beverages | Dairy | Meat |
|---|---|---|---|---|---|
| Pooled W / (U + W) **(used)** | **7.223%** | 12.838% | 2.404% | 4.684% | 8.665% |
| Pooled W / U (alternative) | 7.785% | 14.729% | 2.463% | 4.914% | 9.487% |
| Mean of row W / (U + W) | 7.132% | 12.828% | 2.393% | 4.670% | 8.638% |

**Why reported figures differ slightly:**
- **Rounding:** 7.223% → "7.2%", 12.838% → "12.8%", 6.987% (0% discount) → "7.0%", and the row maximum 13.043% → "13.0%". Chart 17 shows the 2–3 day Bakery products at about 13.0%, which is 13.04% rounded.
- **Pooled vs row mean:** the pooled rate weights by volume, the row mean weights every row equally. The gap is about 0.09 points overall.
- **W/U vs W/(U+W):** the generating ratio k is defined on W/U. For example, the "15%" Bakery ratio appears as 13.04%, and Beverages' 2.5% appears as 2.44% (a product's 2.46% pooled is reduced further by floor rounding). Anyone comparing with legacy figures should check which denominator they used. For example, 7.8% (W/U) vs 7.2% (W/(U+W)).
- **"Waste rate ranges 2.1% to 13.0%":** the minimum, 2.11%, is a low-volume Beverages row where flooring removes proportionally more. It is correct but sits below the 2.44% nominal Beverages rate.

---

## 7. The five most valuable findings for forecasting, inventory and pricing

1. **Recorded price ≈ noise-like base price × (1 − discount); only discount carries a demand association.** *(Pricing)* The base-price component shows no adjusted association with units. This dataset therefore cannot support estimating demand response to base price. A pricing engine built on it would rely on the discount relationship plus explicit assumptions, not on a learned price elasticity.
2. **Discount shows a large, smooth, convex, category-consistent association** (about +6% at 5% up to about +51% at 25%, adjusted). Discount timing is unrelated to season, holidays or marketing. *(Pricing, forecasting)* It is the most usable lever signal, but it most likely reflects the generator. It should be treated as a stated assumption for scenario modelling, with margin effects handled separately (`Price` already looks net of discount).
3. **Wastage is deterministic: ⌊k_product × units⌋, with k set by category and shelf-life tier (2.5%–15% of units).** *(Inventory)* Waste carries no information beyond units sold and product, so waste forecasts reduce to demand forecast × k. The data cannot show overstock/understock trade-offs or store-level waste performance. Same-week wastage must never be a demand feature; the Random Forest already excludes it.
4. **Seasonality is category-specific and explains the weather associations.** *(Forecasting)*
   - Beverages peak in summer and Bakery dips.
   - Meat steps up from early June to mid-July (not explained by discount or marketing).
   - All categories spike at New Year, the Easter week and Christmas.
   - Temperature and rainfall correlations drop to about 0 after month controls.
   - The holiday coefficient is about 0 once week is controlled, because only 2 holiday weeks are national and 8 are regional.

   With a single year, the week-of-year pattern cannot be validated out of sample. Recorded weather is actual, not forecast.
5. **Demand is dominated by stable product and category levels, with short memory and event-driven extremes.** *(Forecasting, inventory)*
   - Fixed effects plus covariates give R² = 0.73.
   - Category explains most series-level variation (Kruskal-Wallis ε² = 0.70).
   - Weekly totals have lag-1 autocorrelation of 0.57 with little beyond.
   - 302 robust-z outliers (0.81%) cluster in Easter and Christmas weeks and in Bakery and Meat. They behave like event effects to model, not errors to remove.
   - All 15 stores stock all 48 products every week; large London stores sell the most but have the lowest units per sq ft.

---

## 8. Recommended improvements (proposed, **not applied**)

These need approval because they change the EDA pipeline and would need a new run folder. The existing run would stay untouched.

| ID | File | Change | Reason |
|---|---|---|---|
| P1 | `src/dpe/eda/plots.py` (`store_units_per_sqft`) | Build legend handles with `matplotlib.patches.Patch(color=…, label=…)` | Fixes chart 09 legend colours |
| P2 | `src/dpe/eda/report.py` | Replace price-section text with section 5 wording, pulling the regression CI and p-value from `ols_table` | Removes the unsupported price claim |
| P3 | `src/dpe/eda/report.py` | Discount section: post-discount price evidence plus mix note on waste by discount level | Sections 4.1 and 4.3 |
| P4 | `src/dpe/eda/analysis.py` (`category_weekly_index`) and chart 03 | Index to each category's annual weekly mean | Week-1 holiday base distorts levels |
| P5 | `src/dpe/eda/analysis.py` and quality step | New tables `price_by_discount_level` (log gap vs log(1 − d)) and `waste_generating_rule` (k per product, floor-match share) | Records the two generating rules as reproducible checks |
| P6 | Chart 13 | Add discount-adjusted panel (price / (1 − d)) or a caption stating the adjusted coefficient | Chart can mislead |
| P7 | Chart 16 and temperature/rainfall tables | Add month-adjusted correlations; caption "largely seasonal" | Section 4.2 / chart review |
| P8 | Report / chart 10 / chart 14 | Pareto wording "top 10 of 48 (20.8%)"; "1 store"; truncated-axis note; drop identical regional waste labels | Cosmetic accuracy |
| P9 | `report.py` holiday text | Report the adjusted holiday coefficient (≈0) and note that only 2 holiday weeks are national | Avoid over-reading the 6.1% |
| P10 | `tests/` | Unit tests for P1, P4 and P5 (legend colours, index base, rule detection on synthetic data) | Keep the suite protective |

Estimated scope: small to moderate, about 150–250 lines across 4 files plus tests. No changes to forecasting, pricing logic or the Random Forest run.

---

## 9. Verified findings, limitations and unresolved questions

### 9.1 Verified findings

These were independently re-derived in this review.

- Grid complete: 48 products × 15 stores × 52 weeks = 37,440 rows. No duplicates, nulls or range violations. Wales has weather data but no stores.
- Totals: 61,482,249 units and 4,786,490 wastage units, reconciled in all five aggregate tables.
- Discount means: 1,574.22 at 0% and 2,382.44 at 25%. These match the legacy notebook and the October 2025 reference (also asserted by tests).
- Category shares: Dairy 39.9%, Bakery 29.0%, Beverages 19.9%, Meat 11.3% of units. Top product: Mozzarella 250g with 2,093,430 units.
- Recorded price behaves as post-discount (section 4.1). The adjusted log-price coefficient is not distinguishable from 0.
- Discount: adjusted association about +51% at 25%; timing unrelated to month, holidays and marketing.
- Wastage = ⌊k × units⌋ in 99.93% of rows, with 14 tier ratios; the 13.04% maximum is k = 0.15.
- Waste-rate denominator is consistent across every output (section 6).
- Temperature and rainfall associations largely vanish after month adjustment. The holiday association vanishes after week adjustment.

### 9.2 Limitations

- Apparently synthetic data, provenance unconfirmed. Generator rules (sections 4.1–4.3) dominate several relationships.
- One year only, so no annual recurrence can be shown and week-of-year effects cannot be validated.
- Small numbers of products (48), stores (15), suppliers (10) and stores per region (1–4).
- Regression SEs are clustered on 48 products. The fixed effects absorb most temperature variance (only 5.3% remains) and most holiday variance (only 22.6% remains), so those coefficients are weakly identified.
- The BH multiple-testing adjustment covers only `group_tests`. The per-category correlations are unadjusted.
- The investigation scripts in this review are read-only and outside the repository. Their results are not yet reproducible from the pipeline; P5 would fix that.

### 9.3 Unresolved questions (need your input or documentation)

1. Can the source confirm that `Price` is the post-discount price? If so, "recorded sales value" is net revenue.
2. Which waste-rate definition should the project standardise on: W / (U + W) (7.2%, current) or W / U (7.8%)? Which did the legacy reports use?
3. Is there any real (non-synthetic) data planned? If not, which generator behaviours (discount uplift, fixed waste ratios) are acceptable as modelling assumptions for Step 4?
4. What causes the Meat step-up from early June to mid-July? Discount share and marketing do not explain it.
5. For forecasting, will weather forecasts be available at prediction time? The Random Forest currently uses same-week recorded weather, which is not known in advance in real use. This is noted for later and has not been changed here.
6. Should regional holidays be modelled separately from national ones?

---

## 10. Integrity and protected assets

- No files under `outputs/`, `data/`, `database/`, `src/`, `scripts/` or `tests/` were created, modified or deleted. 111 SHA-256 hashes were compared before and after.
- The EDA run `20261021-160432_eda` and the verified Random Forest run `20261021-133846_reference_rf` are unchanged.
- No charts were regenerated and the pipeline was not changed. SQLite, Airtable, GitHub, backups and the original projects were not touched.
- The only file added to the project is this report: `docs/STEP_3C_C4_REVIEW.md`.
