"""Turn computed results into structured findings and a draft markdown report.

Each section separates: what the data shows / possible explanations (hypotheses) /
what cannot be concluded. The discount section deliberately uses 'descriptive discount
lift' and never describes discount effects as price sensitivity estimates.
"""
from __future__ import annotations

import math

import pandas as pd

from dpe.eda.data import DATASET_LABEL, ONE_YEAR_NOTE, PRICE_NOTE, WASTE_RATE_DEFINITION
from dpe.eda.analysis import pareto_share

# Within-product wastage-ratio gap (fraction of units) below which discount-level waste
# differences are reported as product mix rather than a within-product change.
MIX_GAP_THRESHOLD = 0.001
# |lag-1 autocorrelation| of within-product log price below which price is described as noise-like.
NOISE_AUTOCORR_THRESHOLD = 0.1


def _timing_unrelated(dt: dict) -> bool:
    """Discount share varies < 5 points by month, < 2 points holiday vs not, and |rho| with marketing < 0.1."""
    return bool(dt["share_discounted_max_month"] - dt["share_discounted_min_month"] < 0.05
                and abs(dt["share_discounted_holiday"] - dt["share_discounted_non_holiday"]) < 0.02
                and abs(dt["rho_discount_vs_log_marketing_within_product"]) < 0.1)


def _pct(x, digits=1) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.{digits}f}%"


def _num(x, digits=0) -> str:
    return "n/a" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:,.{digits}f}"


def _corr_text(row) -> str:
    return f"rho {_num(row['rho'], 2)} (95% CI {_num(row['ci_low'], 2)} to {_num(row['ci_high'], 2)}, n={row['n']:,})"


def _scope(corrs: pd.DataFrame, scope: str = "All products"):
    hit = corrs[corrs["scope"] == scope]
    return None if hit.empty else hit.iloc[0]


def _section(title, shows, hypotheses, cannot):
    return {"title": title, "shows": shows, "hypotheses": hypotheses, "cannot_conclude": cannot}


def _coef_text(row, digits=3) -> str:
    p = row["p_value"]
    p_txt = "p<0.001" if p < 0.001 else f"p={p:.2g}"
    return f"{_num(row['coef'], digits)} (95% CI {_num(row['ci_low'], digits)} to {_num(row['ci_high'], digits)}, {p_txt})"


def _ci_includes_zero(row) -> bool:
    return bool(row["ci_low"] <= 0 <= row["ci_high"])


def build_findings(r: dict) -> dict:
    q = r["quality"]
    comp, ranges, cap, pv = q["completeness"], q["ranges"], q["waste_cap"], q["price_variation"]
    ref = q["referential"].set_index("check")
    sections = []

    sections.append(_section(
        "Data and provenance",
        [f"{comp['actual_rows']:,} store-product-weeks: {comp['products']} products x {comp['stores']} stores x "
         f"{comp['weeks']} weeks ({comp['first_week']} to {comp['last_week']}); {comp['missing_rows']} missing combinations.",
         f"Missing values in the joined table: {ranges['missing_values_in_analysis_frame']}; "
         f"rows with wastage above units sold: {ranges['wastage_exceeds_units_sold']}.",
         f"Weather regions without stores: {ref.loc['weather regions without stores', 'examples'] or 'none'}.",
         f"Row-level waste rate ranges {_pct(cap['min'])} to {_pct(cap['max'])}; {_pct(cap['share_of_rows_at_max'])} "
         "of rows sit at the maximum.",
         f"Recorded price varies within products (median CV {_pct(pv['median_price_cv_within_product'])}) and differs "
         f"between stores for {_pct(pv['share_product_weeks_with_differing_store_prices'])} of product-weeks."],
        ["The regular structure, fixed product waste ratios and noise-like store-level price variation are typical of "
         "generated teaching data."],
        [f"{DATASET_LABEL}: results describe this dataset and may not reflect real shopper behaviour.",
         PRICE_NOTE]))

    w = r["weekly"]
    peak, low = w.loc[w["units"].idxmax()], w.loc[w["units"].idxmin()]
    months = r["months"]
    best_m = months.loc[months["mean_weekly_units"].idxmax()]
    hol = r["holiday"]["summary"]
    ols = r["ols_table"].set_index("term")
    hol_ols = ols.loc["Holiday_Flag"]
    all_regions = int((w["holiday_row_share"] >= 1).sum())
    some_regions = int(((w["holiday_row_share"] > 0) & (w["holiday_row_share"] < 1)).sum())
    lb = r["ljung_box"]
    lb_text = "; ".join(f"lag {int(x.lag)}: p={x.lb_pvalue:.3g}" for x in lb.itertuples()) if len(lb) else "n/a"
    sections.append(_section(
        "Weekly trends and within-year patterns",
        [f"Total units sold {_num(w['units'].sum())}; highest week {peak['WeekDate']:%d %b} ({_num(peak['units'])}), "
         f"lowest week {low['WeekDate']:%d %b} ({_num(low['units'])}).",
         f"Highest average weekly units in month {int(best_m['month'])} ({_num(best_m['mean_weekly_units'])} per week).",
         f"Holiday vs non-holiday weeks within the same store-product (unadjusted): median difference "
         f"{_num(hol['median'], 1)}% ({_pct(hol['share_positive'])} of {hol['n']} series higher in holiday weeks).",
         f"Adjusted for product, store and week effects (and the other regression terms): holiday coefficient "
         f"{_coef_text(hol_ols)}" + ("; no detectable association beyond the calendar week." if _ci_includes_zero(hol_ols)
                                     else "."),
         f"Holiday flags cover all regions in {all_regions} weeks and only some regions in {some_regions} weeks, so "
         "week effects absorb most of the holiday contrast.",
         f"Ljung-Box autocorrelation test on weekly totals: {lb_text}."],
        ["The unadjusted holiday difference may mainly reflect the calendar weeks in which holidays fall (for example "
         "New Year, Easter and Christmas) rather than the holiday flag itself.",
         "Within-year peaks may coincide with calendar events or promotions recorded in the data."],
        [ONE_YEAR_NOTE, "Holiday differences are descriptive; holidays may coincide with other changes."]))

    cats, prods = r["categories"], r["products"]
    top_cat, top_prod = cats.iloc[0], prods.iloc[0]
    k_top = max(1, int(math.ceil(0.2 * len(prods))))
    sections.append(_section(
        "Products and categories",
        [f"Largest category by units: {top_cat['Product_Category']} ({_pct(top_cat['share_of_units'])} of units).",
         f"Top product: {top_prod['Product_Name']} ({_num(top_prod['units'])} units).",
         f"The top {k_top} of {len(prods)} products ({_pct(k_top / len(prods))}) account for "
         f"{_pct(pareto_share(prods))} of units."],
        ["Category volume differences may reflect purchase frequency and pack sizes."],
        ["Recorded sales value uses recorded price, which may differ from actual revenue."]))

    stores, regions = r["stores"], r["regions"]
    sections.append(_section(
        "Stores and regions",
        [f"Highest units per 1,000 sq ft: store {int(stores.iloc[0]['Store_ID'])} ({stores.iloc[0]['Region']}); "
         f"lowest: store {int(stores.iloc[-1]['Store_ID'])} ({stores.iloc[-1]['Region']}).",
         f"Highest units per store by region: {regions.iloc[0]['Region']} ({regions.iloc[0]['stores']} stores)."],
        ["Store size, location and local demand may all contribute."],
        ["Regions with one or two stores give unstable regional comparisons."]))

    wr = r["waste_rule"]["summary"]
    ratios = wr["distinct_nominal_ratios"]
    sections.append(_section(
        "Wastage",
        [f"Overall waste rate {_pct(r['overall_waste_rate'])} ({WASTE_RATE_DEFINITION.lower()}).",
         "By category: " + "; ".join(f"{c.Product_Category} {_pct(c.waste_rate)}" for c in cats.itertuples()) + ".",
         f"Wastage equals floor(k x units sold) in {_pct(wr['share_rows_floor_rule'], 2)} of rows (within 1 unit in "
         f"{_pct(wr['share_rows_within_1_unit'], 2)}), where k is a fixed ratio per product; {len(ratios)} distinct "
         f"ratios from {_pct(min(ratios))} to {_pct(max(ratios))} of units sold.",
         f"The maximum waste rate ({_pct(wr['max_equivalent_waste_rate'])}) is the highest product ratio "
         f"(wastage = {_pct(wr['max_nominal_ratio'])} of units sold), not a cap reached by other products."],
        ["The fixed ratios, tiered by category and shelf life, look like a data-generation rule."],
        ["Fixed wastage ratios do not represent real-world waste behaviour; here wastage carries no information beyond "
         "units sold and product.",
         "Store, region and month waste differences reflect product mix only."]))

    price_all = _scope(r["price"]["correlations"])
    price_undisc = _scope(r["price_undiscounted"]["correlations"])
    lp = ols.loc["log_price"]
    rule = r["price_rule"]
    by_level = rule["by_level"].set_index("Discount_Percent") if len(rule["by_level"]) else pd.DataFrame()
    adjusted_txt = (f"With discount level, marketing, weather, holiday and product, store and week fixed effects: "
                    f"log-price coefficient {_coef_text(lp)}"
                    + ("; no detectable association between recorded price and units sold beyond what these terms "
                       "account for." if _ci_includes_zero(lp) else "; a conditional association."))
    price_shows = [
        f"Unadjusted, within products, recorded price and units sold: "
        f"{_corr_text(price_all) if price_all is not None else 'n/a'}.",
        f"Unadjusted, undiscounted rows only: {_corr_text(price_undisc) if price_undisc is not None else 'n/a'}.",
        adjusted_txt]
    if rule["summary"].get("consistent_with_post_discount_price") and len(by_level):
        top_d = int(by_level.index.max())
        price_shows.append(
            f"Recorded price is lower in discounted rows by about the discount (for example "
            f"{_num(by_level.loc[top_d, 'log_price_gap_vs_0pct'], 2)} log points at {top_d}%, against "
            f"log(1 - {top_d / 100:.2f}) = {_num(by_level.loc[top_d, 'log_1_minus_discount'], 2)}), which suggests "
            "recorded price is the post-discount price.")
    price_hyp = []
    if price_all is not None and price_all["rho"] < 0:
        price_hyp.append("The weak unadjusted negative correlation is consistent with discounted weeks having both lower "
                         "recorded prices and higher units.")
    lag1 = rule["summary"].get("lag1_autocorr_within_product_log_price", float("nan"))
    if abs(lag1) < NOISE_AUTOCORR_THRESHOLD:
        price_hyp.append(f"Outside discounts, price variation behaves like row-level noise (week-to-week "
                         f"autocorrelation {_num(lag1, 2)}), which would explain why it shows no consistent "
                         "association with units.")
    else:
        price_hyp.append(f"Recorded prices persist from week to week (autocorrelation {_num(lag1, 2)}); prices may "
                         "also have been set in response to expected demand.")
    sections.append(_section(
        "Price (descriptive)",
        price_shows,
        price_hyp,
        ["These results do not show that lower prices increase sales, nor that price has no effect on demand; prices "
         "were not randomly assigned and the data-generating process is unknown.",
         "No price elasticity is estimated; recorded price does not support a reliable elasticity estimate here.",
         PRICE_NOTE]))

    disc = r["discount"]
    base = disc.loc[disc["Discount_Percent"] == 0]
    top = disc.loc[disc["Discount_Percent"].idxmax()]
    dt = r["discount_timing"]
    d_ols = ols.loc["Discount_Percent"]
    lift_txt = (f"median within-series descriptive lift at {int(top['Discount_Percent'])}% vs 0%: "
                f"{_num(top.get('median_descriptive_lift_pct', float('nan')), 1)}%")
    mix = r["discount_mix"].set_index("Discount_Percent")
    gap_col = "within_product_waste_ratio_gap_vs_0pct"
    max_gap = float(mix[gap_col].abs().max()) if gap_col in mix else float("nan")
    sections.append(_section(
        "Discounts (descriptive discount lift)",
        [f"{_pct(pv['share_rows_discounted'])} of rows carry a discount; levels {pv['discount_levels']}.",
         f"Mean units per store-product-week: {_num(base['mean_units'].iloc[0] if len(base) else float('nan'), 1)} at 0% vs "
         f"{_num(top['mean_units'], 1)} at {int(top['Discount_Percent'])}%; {lift_txt}.",
         f"Conditional association per discount point (regression with fixed effects): {_coef_text(d_ols, 4)} "
         "in log units.",
         f"Share of rows discounted ranges {_pct(dt['share_discounted_min_month'])} to "
         f"{_pct(dt['share_discounted_max_month'])} by month; holiday {_pct(dt['share_discounted_holiday'])} vs "
         f"non-holiday {_pct(dt['share_discounted_non_holiday'])}; within-product rho with marketing spend "
         f"{_num(dt['rho_discount_vs_log_marketing_within_product'], 2)}.",
         "Waste rate by discount level: " + "; ".join(
             f"{int(d.Discount_Percent)}% {_pct(d.waste_rate)}" for d in disc.itertuples())
         + f". Within a product the wastage ratio moves by at most {_num(max_gap * 100, 2)} percentage points between "
           "levels" + (", so these differences reflect product mix." if max_gap < MIX_GAP_THRESHOLD
                       else "; product mix explains only part of these differences.")],
        [("Discount timing shows no clear link with month, holiday weeks or marketing spend, so these observed factors "
          "do not account for the difference; unobserved factors or the data-generation process may.")
         if _timing_unrelated(dt) else
         "Discounted weeks may coincide with other promotional activity or seasonal demand."],
        ["These are descriptive differences; they do not show that discounts cause higher sales.",
         "Recorded Price appears to be after discount (see the price section); this is not confirmed by documentation.",
         "Margin, cannibalisation, stock-outs and forward buying are not observed."]))

    mk = _scope(r["marketing"]["correlations"])
    temp = _scope(r["temperature"]["correlations"])
    rain = _scope(r["rainfall"]["correlations"])
    temp_m = _scope(r["temperature_month_adjusted"])
    rain_m = _scope(r["rainfall_month_adjusted"])
    sections.append(_section(
        "Marketing and weather",
        [f"Within products, marketing spend and units: {_corr_text(mk) if mk is not None else 'n/a'}.",
         f"Within products, temperature and units: {_corr_text(temp) if temp is not None else 'n/a'}; after also "
         f"removing month effects: {_corr_text(temp_m) if temp_m is not None else 'n/a'}.",
         f"Within products, rainfall and units: {_corr_text(rain) if rain is not None else 'n/a'}; after also removing "
         f"month effects: {_corr_text(rain_m) if rain_m is not None else 'n/a'}."],
        ["Marketing may be targeted at products or weeks already expected to sell well.",
         "Temperature and rainfall associations largely track the season (category-specific seasonal patterns)."],
        ["Weather values are recorded actuals, not forecasts; they cannot be used as known-in-advance inputs.",
         "Associations are not causal effects."]))

    ops = r["operations"]["correlations"]
    sections.append(_section(
        "Shelf life, suppliers and operations",
        [f"{row.relationship}: rho {_num(row.rho, 2)} (n={row.n})" for row in ops.itertuples()],
        ["Shelf life and category overlap strongly, so supplier and shelf-life differences may reflect product mix.",
         "The shelf-life pattern follows the fixed waste-ratio tiers described in the wastage section."],
        ["With 48 products and 10 suppliers, these comparisons have little statistical power.",
         "The fixed ratios are an apparent data-generation rule, not evidence of how shelf life affects real waste."]))

    out = r["outliers"]
    sections.append(_section(
        "Outliers and unusual demand",
        [f"{out['total_flagged']:,} store-product-weeks ({_pct(out['share_flagged'], 2)}) have |robust z| > 3.5; "
         f"{out['total_iqr_flagged']:,} fall outside 1.5 x IQR."],
        ["Flagged weeks may correspond to promotions, holidays or data errors; they need review, not deletion."],
        ["Outlier flags are statistical, not confirmed errors."]))

    return {"dataset_label": DATASET_LABEL, "price_note": PRICE_NOTE, "sections": sections}


def render_markdown(findings: dict, run_id: str) -> str:
    lines = [f"# EDA findings (draft) — run {run_id}", "",
             f"> **{findings['dataset_label']}.** {findings['price_note']}", "",
             "All statements are descriptive. Causal claims are not made.", ""]
    for s in findings["sections"]:
        lines += [f"## {s['title']}", "", "**What the data shows**", ""] + [f"- {x}" for x in s["shows"]]
        lines += ["", "**Possible explanations (hypotheses)**", ""] + [f"- {x}" for x in s["hypotheses"]]
        lines += ["", "**What we cannot conclude**", ""] + [f"- {x}" for x in s["cannot_conclude"]] + [""]
    return "\n".join(lines)
