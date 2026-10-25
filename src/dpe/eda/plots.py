"""Chart functions. Each returns a matplotlib Figure with a title, labelled axes (with units)
and a methodology note. Nothing is saved here; saving is done by dpe.eda.outputs."""
from __future__ import annotations

import textwrap

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from dpe.eda.data import DATASET_LABEL, ONE_YEAR_NOTE, WASTE_RATE_DEFINITION

DESCRIPTIVE_NOTE = "Descriptive association only; not evidence of a causal effect."


NOTE_FONTSIZE = 7.5


def _finish(fig, ax, title: str, xlabel: str, ylabel: str, note: str):
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    # Wrap the note to the figure width: an unwrapped long note widens the saved image
    # (bbox_inches="tight") and squashes the plot.
    chars_per_line = int(fig.get_figwidth() * 72 / (NOTE_FONTSIZE * 0.55))
    lines = textwrap.wrap(f"Note: {note}", width=chars_per_line) + [f"Source: V2 data/raw. {DATASET_LABEL}."]
    fig.text(0.01, 0.01, "\n".join(lines), fontsize=NOTE_FONTSIZE, ha="left", va="bottom", color="#444444")
    note_height = (len(lines) * NOTE_FONTSIZE * 1.35 + 8) / (fig.get_figheight() * 72)
    fig.tight_layout(rect=(0, min(0.35, note_height + 0.02), 1, 1))
    return fig


def _date_axis(ax):
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))


# ---------------------------------------------------------------- data quality
def completeness_heatmap(matrix: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(11, 4.5))
    im = ax.imshow(matrix.to_numpy(), aspect="auto", cmap="viridis",
                   vmin=0, vmax=max(1, int(np.nanmax(matrix.to_numpy()))))
    ax.set_yticks(range(len(matrix.index)), [str(s) for s in matrix.index], fontsize=7)
    step = max(1, len(matrix.columns) // 12)
    ax.set_xticks(range(0, len(matrix.columns), step),
                  [pd.Timestamp(c).strftime("%d %b") for c in matrix.columns[::step]], fontsize=7, rotation=45)
    fig.colorbar(im, ax=ax, label="Products with a sales row (count)")
    return _finish(fig, ax, "Data completeness: products recorded per store and week",
                   "Week starting (Monday, 2024)", "Store_ID",
                   "A uniform colour means every product has a row in every store-week.")


# -------------------------------------------------------------- time patterns
def weekly_units_wastage(weekly: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.plot(weekly["WeekDate"], weekly["units"] / 1000, color="#1f77b4", label="Units sold")
    ax2 = ax.twinx()
    ax2.plot(weekly["WeekDate"], weekly["waste"] / 1000, color="#d62728", label="Wastage units")
    ax2.set_ylabel("Wastage units (thousands)", color="#d62728")
    for _, row in weekly.loc[weekly["holiday_row_share"] >= 0.5].iterrows():
        ax.axvspan(row["WeekDate"], row["WeekDate"] + pd.Timedelta(days=7), color="grey", alpha=0.15, lw=0)
    _date_axis(ax)
    lines = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    ax.legend(lines, [l.get_label() for l in lines], loc="upper left", fontsize=8)
    return _finish(fig, ax, "Weekly units sold and wastage, 2024", "Week (2024)", "Units sold (thousands)",
                   "Shaded weeks: holiday flag set for at least half of store rows (holidays vary by region). "
                   + ONE_YEAR_NOTE)


def category_index(index_df: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(11, 5))
    for col in index_df.columns:
        ax.plot(index_df.index, index_df[col], label=str(col))
    ax.axhline(100, color="grey", lw=0.8, ls="--")
    _date_axis(ax)
    ax.legend(title="Category", fontsize=8)
    return _finish(fig, ax, "Weekly units by category, indexed to each category's average week",
                   "Week (2024)", "Units sold index (category's 2024 weekly average = 100)",
                   "Index removes size differences between categories so their shapes can be compared. The base is "
                   "each category's average week, not week 1 (a holiday week). " + ONE_YEAR_NOTE)


def acf_weekly(weekly: pd.DataFrame, lags: int = 12):
    from statsmodels.graphics.tsaplots import plot_acf

    fig, ax = plt.subplots(figsize=(9, 4.5))
    plot_acf(weekly["units"].to_numpy(), lags=min(lags, len(weekly) - 1), ax=ax)
    return _finish(fig, ax, "Autocorrelation of total weekly units sold", "Lag (weeks)",
                   "Autocorrelation (-1 to 1)",
                   f"Shaded band: approximate 95% limits for no autocorrelation; based on {len(weekly)} weekly "
                   "points. Points outside the band indicate autocorrelation at that lag.")


# ----------------------------------------------------- products and categories
def category_units_waste(categories: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(categories["Product_Category"], categories["units"] / 1e6, color="#4c72b0")
    for bar, wr in zip(bars, categories["waste_rate"]):
        ax.annotate(f"waste {wr:.1%}", (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    ha="center", va="bottom", fontsize=8)
    return _finish(fig, ax, "Units sold by category, with waste rate", "Product category",
                   "Units sold, 2024 (millions)", WASTE_RATE_DEFINITION + ".")


def top_bottom_products(products: pd.DataFrame, n: int = 10):
    p = products.sort_values("units", ascending=False)
    sel = pd.concat([p.head(n), p.tail(n)]).drop_duplicates("Product_ID").sort_values("units")
    colours = ["#55a868" if pid in set(p.head(n)["Product_ID"]) else "#c44e52" for pid in sel["Product_ID"]]
    fig, ax = plt.subplots(figsize=(9, 7))
    ax.barh(sel["Product_Name"], sel["units"] / 1000, color=colours)
    ax.tick_params(axis="y", labelsize=7)
    top_cats = ", ".join(sorted(p.head(n)["Product_Category"].unique()))
    bottom_cats = ", ".join(sorted(p.tail(n)["Product_Category"].unique()))
    return _finish(fig, ax, f"Top and bottom {n} products by units sold", "Units sold, 2024 (thousands)",
                   "Product", f"Green = top sellers ({top_cats}), red = lowest sellers ({bottom_cats}), across all "
                   "stores. The ranking largely reflects category.")


def pareto_curve(products: pd.DataFrame, top_fraction: float = 0.2):
    p = products.sort_values("units", ascending=False)
    cum = p["units"].cumsum() / p["units"].sum() * 100
    k = max(1, int(np.ceil(top_fraction * len(p))))
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(np.arange(1, len(p) + 1), cum.to_numpy(), marker="o", ms=3)
    ax.axhline(80, color="grey", ls="--", lw=0.8)
    return _finish(fig, ax, "Cumulative share of units sold by product rank", "Products ranked by units sold",
                   "Cumulative share of units sold (%)",
                   f"Dashed line marks 80% of units. Top {k} of {len(p)} products ({k / len(p):.1%}) = "
                   f"{cum.iloc[k - 1]:.1f}% of units.")


def weekly_units_by_category_box(df: pd.DataFrame):
    cats = sorted(df["Product_Category"].unique())
    data = [df.loc[df["Product_Category"] == c, "Units_Sold"].to_numpy() for c in cats]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.boxplot(data, showfliers=False)
    ax.set_xticks(range(1, len(cats) + 1), cats)
    return _finish(fig, ax, "Distribution of weekly units per store-product, by category", "Product category",
                   "Units sold per store-product-week", "Boxes show quartiles; whiskers 1.5 x IQR; outliers hidden.")


# --------------------------------------------------------------- stores, regions
def store_units_per_sqft(stores: pd.DataFrame):
    s = stores.sort_values("units_per_1000_sqft", ascending=False)
    regions = sorted(s["Region"].unique())
    cmap = plt.get_cmap("tab10")
    colour = {r: cmap(i % 10) for i, r in enumerate(regions)}
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(s["Store_ID"].astype(str), s["units_per_1000_sqft"] / 1000, color=[colour[r] for r in s["Region"]])
    # Explicit patches: legend entries from empty bar calls do not carry the bar colours.
    ax.legend(handles=[Patch(facecolor=colour[r], label=r) for r in regions], title="Region", fontsize=7)
    return _finish(fig, ax, "Units sold per 1,000 sq ft of store space", "Store_ID",
                   "Units sold per 1,000 sq ft, 2024 (thousands)", "Normalises for store size; colour shows region.")


def region_comparison(regions: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(regions["Region"], regions["units_per_store"] / 1e6, color="#8172b2")
    for bar, wr, n in zip(bars, regions["waste_rate"], regions["stores"]):
        ax.annotate(f"{n} store{'s' if n != 1 else ''}\nwaste {wr:.1%}",
                    (bar.get_x() + bar.get_width() / 2, bar.get_height()), ha="center", va="bottom", fontsize=7)
    ax.tick_params(axis="x", labelrotation=20)
    return _finish(fig, ax, "Average units sold per store, by region", "Region",
                   "Units sold per store, 2024 (millions)",
                   "Regions have different numbers of stores; " + WASTE_RATE_DEFINITION + ". Regional waste rates "
                   "are near-identical because every store stocks the same products with fixed waste ratios.")


# ------------------------------------------------------------------------ waste
def waste_rate_hist(df: pd.DataFrame, cap: dict, rule: dict):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(df["waste_rate"].dropna() * 100, bins=50, color="#dd8452")
    ax.axvline(cap["max"] * 100, color="black", ls="--", lw=1, label=f"maximum {cap['max']:.1%}")
    ax.legend(fontsize=8)
    return _finish(fig, ax, "Distribution of waste rate per store-product-week", "Waste rate (%)",
                   "Number of store-product-weeks",
                   f"Row-level rate = wastage / (units sold + wastage). Spikes match {len(rule['distinct_nominal_ratios'])} "
                   f"fixed product wastage ratios; the maximum equals wastage of {rule['max_nominal_ratio']:.1%} of units "
                   f"sold ({cap['share_of_rows_at_max']:.1%} of rows). Apparent data-generation rule.")


def waste_heatmap(pivot: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(10, 4))
    im = ax.imshow(pivot.to_numpy() * 100, aspect="auto", cmap="OrRd")
    ax.set_yticks(range(len(pivot.index)), [str(i) for i in pivot.index])
    ax.set_xticks(range(len(pivot.columns)), [pd.Timestamp(2024, int(m), 1).strftime("%b") for m in pivot.columns])
    fig.colorbar(im, ax=ax, label="Waste rate (%)")
    return _finish(fig, ax, "Waste rate by category and month", "Month (2024)", "Product category",
                   WASTE_RATE_DEFINITION + ", per category and month. " + ONE_YEAR_NOTE)


# ------------------------------------------------ relationships (descriptive)
def binned_relationship(rel: dict, title: str, xlabel: str, note: str, scopes=None):
    b = rel["binned"]
    scopes = [] if b.empty else (scopes or list(b["scope"].unique()))
    fig, ax = plt.subplots(figsize=(9, 5))
    for scope in scopes:
        g = b[b["scope"] == scope]
        ax.plot(g["x_mid"], g["units_index"], marker="o", label=scope)
    ax.axhline(100, color="grey", ls="--", lw=0.8)
    ax.legend(fontsize=8)
    return _finish(fig, ax, title, xlabel, "Units sold index (product average = 100)",
                   note + " Both axes compare each product with its own average. " + DESCRIPTIVE_NOTE)


def price_relationship_chart(rel: dict, rel_undiscounted: dict, ols_table: pd.DataFrame):
    """Unadjusted relationship (all rows) next to undiscounted rows only, with the adjusted coefficient."""
    parts = []
    for r, label in [(rel, "All rows (unadjusted)"), (rel_undiscounted, "Undiscounted rows only")]:
        b = r["binned"]
        if not b.empty:
            parts.append(b[b["scope"] == "All products"].assign(scope=label))
    combined = {"binned": pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()}
    lp = ols_table.set_index("term").loc["log_price"]
    includes_zero = lp["ci_low"] <= 0 <= lp["ci_high"]
    adjusted = (f"Adjusted for discount, marketing, weather, holiday and product/store/week effects: log-price "
                f"coefficient {lp['coef']:.3f} (95% CI {lp['ci_low']:.3f} to {lp['ci_high']:.3f})"
                + ("; no detectable association." if includes_zero else "."))
    return binned_relationship(
        combined, "Units sold vs recorded price, within products",
        "Recorded price relative to product average (log points)",
        "Points are equal-sized bins of price deviation. The all-rows slope mixes in discount weeks (lower recorded "
        "price, higher units). " + adjusted)


def marketing_relationship_chart(rel: dict):
    return binned_relationship(
        rel, "Units sold vs marketing spend, within products",
        "Marketing spend relative to product average (log points)", "Points are equal-sized bins of spend deviation.",
        scopes=["All products"])


def temperature_relationship_chart(rel: dict, month_adjusted: pd.DataFrame):
    adj = month_adjusted.set_index("scope")["rho"]
    adj_txt = ", ".join(f"{s} {v:.2f}" for s, v in adj.items())
    return binned_relationship(
        rel, "Units sold vs temperature, within products, by category",
        "Temperature relative to the product's average conditions (deg C)",
        "Recorded weekly average temperature by region; actual, not forecast, weather. The pattern largely tracks the "
        f"season: after also removing month effects, rho = {adj_txt}.")


def discount_levels(disc: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.errorbar(disc["Discount_Percent"], disc["mean_units"], yerr=disc["ci95_units"], fmt="o-", capsize=4)
    return _finish(fig, ax, "Average units sold at each recorded discount level", "Discount (%)",
                   "Mean units per store-product-week",
                   "Descriptive discount lift only: discounts were not randomly assigned; recorded Price appears to be "
                   "after discount (undocumented). y-axis does not start at zero. Error bars: approx. 95% CI (rows are "
                   "not independent).")


# ------------------------------------------------------------------ operations
def shelf_life_waste(products: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(8, 5))
    for cat, g in products.groupby("Product_Category"):
        ax.scatter(g["Shelf_Life_Days"], g["waste_rate"] * 100, label=str(cat), s=30)
    ax.set_xscale("log")
    ax.legend(title="Category", fontsize=8)
    return _finish(fig, ax, "Shelf life vs waste rate, by product", "Shelf life (days, log scale)",
                   "Waste rate, 2024 (%)", "Category strongly overlaps with shelf life. Steps follow fixed product "
                   "waste ratios (apparent data-generation rule, not real-world waste behaviour). " + DESCRIPTIVE_NOTE)


def supplier_waste(suppliers: pd.DataFrame):
    s = suppliers.sort_values("waste_rate", ascending=False)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(s["Supplier_Name"].astype(str), s["waste_rate"] * 100, color="#64b5cd")
    ax.tick_params(axis="x", labelrotation=35, labelsize=7)
    return _finish(fig, ax, "Waste rate by supplier", "Supplier", "Waste rate, 2024 (%)",
                   "Suppliers serve different product mixes, so differences mostly reflect category. " + DESCRIPTIVE_NOTE)


def outliers_by_week(by_week: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.bar(by_week["WeekDate"], by_week["flagged"], width=5, color="#937860")
    _date_axis(ax)
    return _finish(fig, ax, "Unusual store-product-weeks by week", "Week (2024)",
                   "Rows flagged (|robust z| > 3.5)",
                   "Robust z uses each store-product series' median and median absolute deviation.")


CHARTS = {
    "01_completeness_heatmap": lambda r: completeness_heatmap(r["quality"]["completeness_matrix"]),
    "02_weekly_units_wastage": lambda r: weekly_units_wastage(r["weekly"]),
    "03_category_index": lambda r: category_index(r["category_index"]),
    "04_acf_weekly_units": lambda r: acf_weekly(r["weekly"]),
    "05_category_units_waste": lambda r: category_units_waste(r["categories"]),
    "06_top_bottom_products": lambda r: top_bottom_products(r["products"]),
    "07_pareto_products": lambda r: pareto_curve(r["products"]),
    "08_units_box_by_category": lambda r: weekly_units_by_category_box(r["df"]),
    "09_store_units_per_sqft": lambda r: store_units_per_sqft(r["stores"]),
    "10_region_comparison": lambda r: region_comparison(r["regions"]),
    "11_waste_rate_hist": lambda r: waste_rate_hist(r["df"], r["quality"]["waste_cap"], r["waste_rule"]["summary"]),
    "12_waste_category_month": lambda r: waste_heatmap(r["waste_category_month"]),
    "13_price_relationship": lambda r: price_relationship_chart(r["price"], r["price_undiscounted"], r["ols_table"]),
    "14_discount_levels": lambda r: discount_levels(r["discount"]),
    "15_marketing_relationship": lambda r: marketing_relationship_chart(r["marketing"]),
    "16_temperature_relationship": lambda r: temperature_relationship_chart(r["temperature"],
                                                                          r["temperature_month_adjusted"]),
    "17_shelf_life_waste": lambda r: shelf_life_waste(r["operations"]["products"]),
    "18_supplier_waste": lambda r: supplier_waste(r["operations"]["suppliers"]),
    "19_outliers_by_week": lambda r: outliers_by_week(r["outliers"]["by_week"]),
}
