# EDA findings: Dynamic Pricing Engine V2

- **Step:** 3C-C5 (final EDA findings, after the corrections approved from [STEP_3C_C4_REVIEW.md](STEP_3C_C4_REVIEW.md))
- **Source run:** `outputs/runs/20261021-162605_eda` (38 tables, 19 charts, `findings.json`, `findings_draft.md`, `eda_manifest.json`)
- **Inputs:** the 5 raw CSVs in `data/raw`, SHA-256 verified before the run (hashes recorded in the run manifest)
- **Date:** 2026-10-21

> **Read this first.** The dataset is **apparently synthetic; provenance unconfirmed**. Every finding describes this dataset only and may not reflect real shopper behaviour.
> - All relationships are **statistical associations**, not causal effects.
> - **No price elasticity is estimated.** Recorded price does not support a reliable elasticity estimate here.
> - Discounts are **not** shown to cause higher sales.
> - The fixed wastage ratios are an **apparent data-generation rule**, not real-world waste behaviour.
> - The source does not document whether `Price` is before or after discount. The data pattern strongly suggests it is after discount (section 3.1), but that is an inference.

---

## 1. Data verified

| Check | Result |
|---|---|
| Grid | 48 products × 15 stores × 52 weeks (2024-01-01 to 2024-12-23) = **37,440 rows**, 0 missing combinations |
| Quality | 0 duplicates, 0 nulls, 0 range violations; every week starts on a Monday |
| Referential integrity | All keys match; Wales has weather data but no stores |
| Totals | **61,482,249 units sold, 4,786,490 wastage units**. These reconcile exactly across the weekly, category, product, store and region tables, the Oct 2025 merged reference and the legacy notebook. |
| Assortment | All 15 stores stock all 48 products in every week |

---

## 2. Verified findings

### 2.1 Demand patterns
- **Weekly range:** highest week 23 Dec (1,483,999 units), lowest week 26 Aug (1,074,503). December has the highest average weekly units (1,332,448).
- **Category-specific seasonality** (chart 03, indexed to each category's average week):
  - Beverages are low in spring and peak from August to October at about 140.
  - Bakery peaks in early January and the Easter week (about 185), with a trough near 66 in late summer.
  - Meat steps up from early June to mid-July (about 120, against about 93 the rest of the year).
  - All categories rise sharply in the final Christmas weeks.
- **Short memory:** weekly totals have lag-1 autocorrelation of 0.57, with little beyond lag 1. Ljung-Box tests at lags 4 and 8 are significant (p < 0.0001).
- **Holidays:**
  - Unadjusted, holiday weeks are 6.1% higher (median, within store-product series).
  - With product, store and week effects (plus the other regression terms), the holiday coefficient is −0.002 (95% CI −0.021 to 0.018): no detectable association beyond the calendar week.
  - Holiday flags cover all regions in only 2 weeks and some regions in 8.
- **Only one year** is available, so no pattern can be shown to recur annually.

### 2.2 Products, stores and regions
- **Categories:** Dairy has 39.9% of units, Bakery 29.0%, Beverages 19.9% and Meat 11.3%. The category explains most series-level variation (Kruskal-Wallis ε² = 0.70).
- **Products:** the top 10 products are all Dairy and the bottom 10 all Meat. The top 10 of 48 products (20.8%) account for 33.3% of units, so volume is not concentrated in a few products. The top product is Mozzarella 250g (2,093,430 units).
- **Stores:**
  - Store 505 (North West) sells the most units per 1,000 sq ft (1.05M).
  - Store 500 (London) sells the fewest per sq ft (0.61M), although London's three large stores sell the most units per store.
  - Regions with 1–2 stores give unstable comparisons.

### 2.3 Discounts (descriptive discount lift)
- **Coverage:** 23.2% of rows carry a discount. The levels are 0, 5, 10, 15, 20 and 25%.
- **Mean units:** 1,574 at 0% vs 2,382 at 25%. The median within-series descriptive lift at 25% is 50.5%.
- **Adjusted:** the conditional association is +0.0161 log units per discount point (95% CI 0.0156 to 0.0167). It is similar across categories.
- **Timing:** discounting is unrelated to the observed confounders.
  - The share of rows discounted is 22.2–24.5% in every month.
  - Holiday weeks 23.5% vs non-holiday 23.1%.
  - Within-product correlation with marketing spend: 0.00.
- **Waste by discount level:** rates are 7.0% at 0% and 7.8–8.0% when discounted. That difference is **product mix** (Bakery is over-represented among discounted rows). Within a product, the wastage ratio moves by at most 0.02 percentage points.
- **Not shown:** that discounts cause higher sales. Margin, cannibalisation, stock-outs and forward buying are not observed.

### 2.4 Price
- **Unadjusted:** within products, recorded price and units sold have ρ = −0.02 (95% CI −0.03 to −0.01).
- **Undiscounted rows only:** ρ = +0.01 (95% CI −0.00 to 0.02).
- **Adjusted** for discount, marketing, weather, holiday and product/store/week effects: log-price coefficient +0.008 (95% CI −0.002 to 0.017, p = 0.12). There is **no detectable association** between recorded price and units sold beyond these terms.
- **Reading:** the weak unadjusted negative correlation is consistent with discounted weeks having both lower recorded prices and higher units. Chart 13 now shows both the unadjusted and the undiscounted-only lines.

### 2.5 Marketing and weather
- **Marketing spend:** within products, ρ = 0.07. Adjusted, the coefficient is 0.033 per log point, roughly +2.3% units per doubling of spend.
- **Temperature and rainfall:** within products, ρ = 0.09 and −0.11. **After also removing month effects, both fall to −0.01** (95% CIs include 0). The weather associations largely track the season.
  - Category-level month-adjusted values stay small: |ρ| ≤ 0.06.
- **Not usable as advance inputs:** weather values are recorded actuals, not forecasts.

### 2.6 Wastage and operations
- **Waste rate** = wastage / (units sold + wastage), used consistently in every output.
  - Overall: 7.2%.
  - By category: Bakery 12.8%, Meat 8.7%, Dairy 4.7%, Beverages 2.4%.
  - The alternative wastage / units sold would give 7.8% overall.
- **Shelf life:** shelf life vs product waste rate gives ρ = −0.96 (n = 48). Supplier lead time shows no association (ρ = −0.06). Cold-storage capacity shows no association with chilled waste (ρ = 0.05, n = 15).
- **Outliers:** 302 store-product-weeks (0.81%) have |robust z| > 3.5. They cluster in the New Year, Easter and Christmas weeks and in Bakery and Meat, and are flagged for review, not deletion.

---

## 3. Data-generation diagnostics

These are new in Step 3C-C5 and recorded as reproducible tables in the run.

### 3.1 Recorded price looks like the post-discount price
Table: `diagnostic_price_by_discount_level`. Within products, the log-price gap between discounted and 0% rows matches log(1 − discount) to within **0.008 log points** at every level:

| Discount | Observed gap | log(1 − d) |
|---|---|---|
| 5% | −0.049 | −0.051 |
| 10% | −0.107 | −0.105 |
| 15% | −0.161 | −0.163 |
| 20% | −0.231 | −0.223 |
| 25% | −0.295 | −0.288 |

- Dividing by (1 − d) leaves the implied pre-discount price with the same centre (within 0.013 log points) and spread (SD 0.48–0.50) at every level.
- Leaving discount aside, recorded price behaves like row-level noise. Week-to-week autocorrelation within a series is **0.007**, and prices differ between stores in every product-week.

### 3.2 Wastage is a fixed product ratio of units sold
Table: `diagnostic_waste_generation_rule`.
- **Rule:** `Wastage_Units = floor(k × Units_Sold)` in **99.93%** of rows, and every row is within 1 unit of it.
- **14 ratios**, k = 2.5% to 15.0% of units sold, tiered by category and shelf life:
  - Bakery: 14.0–15.0%
  - Meat: 8.5–10.5%
  - Dairy: 4.0–6.8%
  - Beverages: 2.5%
- **The "ceiling":** the 13.0% maximum waste rate is simply the highest ratio, k = 15%, for the five Bakery products with a 2–3 day shelf life. It is not a cap that other products reach.
- **Consequences:**
  - Waste does not vary by month, store or region except through product mix.
  - The shelf-life correlation describes these tiers, not a real shelf-life effect.

### 3.3 Discount mix and timing
Table: `diagnostic_discount_mix`, plus `diagnostics.discount_timing` in the manifest. These record the category mix by discount level, the within-product waste-ratio gap, and the month, holiday and marketing timing checks summarised in section 2.3.

---

## 4. Limitations

1. **Synthetic, undocumented data.** Generator rules (sections 3.1–3.2) dominate several relationships. Results cannot be carried over to real stores.
2. **One year.** Week-of-year and holiday effects cannot be validated out of sample.
3. **Small units of analysis:** 48 products, 15 stores, 10 suppliers and 1–4 stores per region.
4. **Weak identification.** Week effects absorb most holiday variance (only 23% remains) and most temperature variance (only 5% remains), so those adjusted coefficients are imprecise. Regression standard errors are clustered on 48 products.
5. **Associations only.** Prices and discounts were not randomly assigned. Even where observed confounders are balanced (discount timing), unobserved factors or the generator may explain the pattern.
6. **Multiple testing.** The Benjamini-Hochberg adjustment covers `group_tests` only. Per-category correlations are unadjusted.
7. **Price semantics.** The post-discount reading of `Price` is inferred, not documented. "Recorded sales value" (units × recorded price) is therefore probably, but not certainly, net of discount.

---

## 5. Business implications

The implications below follow from this dataset's structure. Each is a design input for later steps, not a claim about real customers.

| Area | Implication |
|---|---|
| **Dynamic pricing** | The data contains **no usable base-price signal**. A pricing engine cannot learn demand response to list price from it. Discount depth is the only lever with a consistent demand association, and that association most likely reflects the generator. Any pricing rule built on it must state the uplift as an explicit, adjustable **assumption**, and must evaluate margin with post-discount `Price`, to avoid applying the discount twice. |
| **Demand forecasting** | Useful structure: product/category level, category-specific seasonality, event weeks (New Year, Easter, Christmas) and discount depth. Weather adds little beyond the season, and its recorded actuals are not available in advance. With one year of history, seasonal terms will be fitted from a single cycle. |
| **Inventory and waste** | Wastage is fully determined by units sold and the product ratio, so waste forecasts reduce to demand forecast × k. The data cannot show overstock/understock trade-offs, store waste performance or the effect of cold storage. **Same-week wastage must never be a demand feature.** The current Random Forest already excludes it (`src/dpe/reference_baseline.py:179`). |
| **Reporting** | Use one waste-rate definition: wastage / (units + wastage), currently 7.2%. Label it clearly, because wastage / units gives 7.8%. |

---

## 6. Recommendations (for approval; nothing here has been implemented)

1. **Confirm price semantics** with the data owner: is `Price` after discount? If confirmed, document it in `DECISIONS.md` and treat recorded sales value as net revenue.
2. **Forecasting (Step 4 candidates; not started):**
   - Evaluate category-specific seasonality and explicit event-week features.
   - Treat discount depth as a known-in-advance plan input.
   - Test whether removing same-week recorded weather (or replacing it with a forecast proxy) changes accuracy.
   - Compare all changes against the verified Random Forest baseline (MAE 487.2, WAPE 27.9%).
3. **Pricing logic:** state the discount-uplift curve (about +6% at 5% to about +51% at 25%, adjusted) as a scenario assumption with sensitivity ranges, not as a learned elasticity. Keep base-price changes out of the demand model unless real price-variation data becomes available.
4. **Inventory:** model waste as k × forecast demand per product and flag that this is a data artefact. Real waste data would be needed for any optimisation claim.
5. **Data:** obtain a second year, or real data, before drawing conclusions about seasonality, holidays or regional differences.

---

## 7. Unresolved questions

1. Is `Price` documented anywhere as pre- or post-discount?
2. Which waste-rate definition did the legacy reports use?
3. Is any real (non-synthetic) data planned? If not, which generator behaviours are acceptable as modelling assumptions?
4. What drives the Meat step-up from early June to mid-July? It is not explained by discount share or marketing.
5. Will weather forecasts be available at prediction time?
6. Should regional holidays be modelled separately from national ones?

---

## 8. Runs and reproducibility

| Run | Status |
|---|---|
| `20261021-133846_reference_rf` | Verified Random Forest recovery. Unchanged and write-protected. |
| `20261021-160432_eda` | First EDA run, reviewed in Step 3C-C4. Unchanged. Now write-protected, with its 53 file hashes in `docs/CHECKSUMS.sha256`. |
| `20261021-162317_eda` | Intermediate C5 run. **Superseded:** long chart captions widened charts 10, 13 and 16, and the binned charts' y-labels were clipped. Kept, not used. |
| `20261021-162452_eda` | Intermediate C5 run. **Superseded:** y-labels clipped on charts 13, 15 and 16. Kept, not used. |
| **`20261021-162605_eda`** | **Final C5 run; the basis for this document.** |

- **Reproduce** (creates another new run folder; never overwrites):

  ```
  .venv\Scripts\python.exe scripts\run_eda.py
  ```

- **Tests:** 114 passed, 0 failed (`.venv\Scripts\python.exe -m pytest`).
