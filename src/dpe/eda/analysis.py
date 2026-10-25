"""Descriptive summaries. Waste rates are always ratios of sums (see data.WASTE_RATE_DEFINITION)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dpe.eda.data import CHILLED_CATEGORIES, KEYS, SERIES_KEYS
from dpe.eda.stats import multiway_demean, paired_difference, spearman_with_ci

# Largest gap (log points) between the observed within-product price gap and log(1 - discount)
# still treated as "consistent with recorded price being after discount".
POST_DISCOUNT_TOLERANCE = 0.02


def _summarise(df: pd.DataFrame, by) -> pd.DataFrame:
    out = df.groupby(by, observed=True).agg(
        rows=("Units_Sold", "size"),
        units=("Units_Sold", "sum"),
        waste=("Wastage_Units", "sum"),
        recorded_sales_value=("recorded_sales_value", "sum"),
        mean_price=("Price", "mean"),
    )
    out["waste_rate"] = out["waste"] / (out["units"] + out["waste"])
    return out.reset_index()


# ------------------------------------------------------------------ time patterns
def weekly_trend(df: pd.DataFrame) -> pd.DataFrame:
    w = _summarise(df, "WeekDate")
    hol = df.groupby("WeekDate")["Holiday_Flag"].mean().rename("holiday_row_share").reset_index()
    w = w.merge(hol, on="WeekDate", how="left")
    w["units_rolling_4w"] = w["units"].rolling(4).mean()
    return w


def category_weekly_index(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly units per category indexed to that category's average week (= 100).

    The average week is used as the base, not the first week, because week 1 is a holiday
    week and an unusual base distorts the comparison between categories.
    """
    pv = df.pivot_table(index="WeekDate", columns="Product_Category", values="Units_Sold", aggfunc="sum")
    return pv / pv.mean() * 100


def month_profile(df: pd.DataFrame) -> pd.DataFrame:
    m = _summarise(df, "month")
    weeks = df.groupby("month")["WeekDate"].nunique().rename("weeks_in_month").reset_index()
    m = m.merge(weeks, on="month")
    m["mean_weekly_units"] = m["units"] / m["weeks_in_month"]
    return m


def holiday_comparison(df: pd.DataFrame) -> dict:
    """Within each store-product series: mean units in holiday vs non-holiday weeks."""
    m = df.groupby(SERIES_KEYS + ["Holiday_Flag"])["Units_Sold"].mean().unstack("Holiday_Flag")
    if 0 not in m.columns or 1 not in m.columns:
        return {"table": pd.DataFrame(), "summary": paired_difference([])}
    m = m.dropna(subset=[0, 1])
    pct = (m[1] / m[0] - 1) * 100
    table = pd.DataFrame({"mean_units_non_holiday": m[0], "mean_units_holiday": m[1],
                          "pct_difference": pct}).reset_index()
    return {"table": table, "summary": paired_difference(pct.to_numpy())}


# ----------------------------------------------------------- products and stores
def category_summary(df: pd.DataFrame) -> pd.DataFrame:
    c = _summarise(df, "Product_Category")
    c["share_of_units"] = c["units"] / c["units"].sum()
    c["share_of_recorded_value"] = c["recorded_sales_value"] / c["recorded_sales_value"].sum()
    return c.sort_values("units", ascending=False).reset_index(drop=True)


def product_ranking(df: pd.DataFrame) -> pd.DataFrame:
    p = _summarise(df, ["Product_ID", "Product_Name", "Product_Category"])
    p = p.sort_values("units", ascending=False).reset_index(drop=True)
    p["rank_units"] = np.arange(1, len(p) + 1)
    p["cumulative_share_units"] = p["units"].cumsum() / p["units"].sum()
    p["rank_recorded_value"] = p["recorded_sales_value"].rank(ascending=False, method="min").astype(int)
    return p


def pareto_share(products: pd.DataFrame, top_fraction: float = 0.2) -> float:
    k = max(1, int(np.ceil(top_fraction * len(products))))
    return float(products.sort_values("units", ascending=False)["units"].head(k).sum() / products["units"].sum())


def store_summary(df: pd.DataFrame) -> pd.DataFrame:
    s = _summarise(df, ["Store_ID", "Region", "Store_Size", "Cold_Storage_Capacity"])
    s["units_per_1000_sqft"] = s["units"] / (s["Store_Size"] / 1000)
    return s.sort_values("units_per_1000_sqft", ascending=False).reset_index(drop=True)


def region_summary(df: pd.DataFrame) -> pd.DataFrame:
    r = _summarise(df, "Region")
    stores = df.groupby("Region")["Store_ID"].nunique().rename("stores").reset_index()
    r = r.merge(stores, on="Region")
    r["units_per_store"] = r["units"] / r["stores"]
    return r.sort_values("units_per_store", ascending=False).reset_index(drop=True)


def series_summary(df: pd.DataFrame) -> pd.DataFrame:
    """One row per store-product series (used for group tests, which need independent units)."""
    s = _summarise(df, SERIES_KEYS + ["Product_Category", "Region"])
    return s


# ---------------------------------------------------------------------- wastage
def waste_by_category_month(df: pd.DataFrame) -> pd.DataFrame:
    s = _summarise(df, ["Product_Category", "month"])
    return s.pivot(index="Product_Category", columns="month", values="waste_rate")


# ------------------------------------------------- price, discount, marketing, weather
def discount_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Descriptive discount lift: raw level means plus within store-product comparisons with 0%."""
    lvl = _summarise(df, "Discount_Percent")
    g = df.groupby("Discount_Percent")["Units_Sold"]
    lvl["mean_units"] = g.mean().to_numpy()
    lvl["sem_units"] = g.sem().to_numpy()
    lvl["ci95_units"] = 1.96 * lvl["sem_units"]
    lvl["share_of_rows"] = lvl["rows"] / lvl["rows"].sum()
    sm = df.groupby(SERIES_KEYS + ["Discount_Percent"])["Units_Sold"].mean().unstack("Discount_Percent")
    if 0 in sm.columns:
        lift = sm.div(sm[0], axis=0) - 1
        within = pd.DataFrame({
            "Discount_Percent": lift.columns.to_numpy(),
            "series_compared": lift.notna().sum().to_numpy(),
            "median_descriptive_lift_pct": (lift.median() * 100).to_numpy(),
            "mean_descriptive_lift_pct": (lift.mean() * 100).to_numpy(),
        })
        lvl = lvl.merge(within, on="Discount_Percent", how="left")
    return lvl


def within_product_relationship(df: pd.DataFrame, x_col: str, log_x: bool = True,
                                n_bins: int = 10, by_category: bool = True) -> dict:
    """Relationship between x and units sold *within* each product (both demeaned by product).

    units_index = 100 x geometric-mean units relative to the product's own average.
    """
    d = df[["Product_ID", "Product_Category", x_col, "Units_Sold"]].copy()
    x = np.log(d[x_col].astype(float)) if log_x else d[x_col].astype(float)
    ly = np.log(d["Units_Sold"].astype(float))
    d["x_rel"] = x - x.groupby(d["Product_ID"]).transform("mean")
    d["y_rel"] = ly - ly.groupby(d["Product_ID"]).transform("mean")
    scopes = [("All products", d)]
    if by_category:
        scopes += [(str(c), g) for c, g in d.groupby("Product_Category")]
    binned, corrs = [], []
    for scope, g in scopes:
        corrs.append({"scope": scope, **spearman_with_ci(g["x_rel"], g["y_rel"])})
        if g["x_rel"].nunique() < 2:
            continue
        bins = pd.qcut(g["x_rel"], q=n_bins, duplicates="drop")
        b = (g.groupby(bins, observed=True)
             .agg(x_mid=("x_rel", "median"), y_mean=("y_rel", "mean"), rows=("y_rel", "size"))
             .reset_index(names="bin"))
        b["bin"] = b["bin"].astype(str)
        b["scope"] = scope
        b["units_index"] = np.exp(b["y_mean"]) * 100
        binned.append(b)
    return {
        "x_col": x_col,
        "log_x": log_x,
        "binned": pd.concat(binned, ignore_index=True) if binned else pd.DataFrame(),
        "correlations": pd.DataFrame(corrs),
    }


def month_adjusted_correlations(df: pd.DataFrame, x_col: str) -> pd.DataFrame:
    """Spearman of x with log units after removing store-product series means and month means.

    A seasonality check: if an association largely disappears here, it mostly tracks the season.
    """
    scopes = [("All products", df)] + [(str(c), g) for c, g in df.groupby("Product_Category")]
    rows = []
    for scope, g in scopes:
        series = g["Store_ID"].astype(str) + "_" + g["Product_ID"].astype(str)
        x = multiway_demean(g[x_col], [series, g["month"]])
        y = multiway_demean(np.log(g["Units_Sold"].astype(float)), [series, g["month"]])
        rows.append({"scope": scope, "adjustment": "store-product series + month", **spearman_with_ci(x, y)})
    return pd.DataFrame(rows)


# ------------------------------------------------- data-generation diagnostics
def price_generation_check(df: pd.DataFrame) -> dict:
    """Does recorded price look like a pre-discount price x (1 - discount)?

    For each discount level: mean within-product log-price gap vs 0% rows, compared with log(1 - d).
    Also reports how noise-like the remaining price variation is (lag-1 autocorrelation within series).
    """
    d = df[SERIES_KEYS + ["WeekDate", "Discount_Percent", "Price"]].copy()
    lp = np.log(d["Price"].astype(float))
    d["lp_rel"] = lp - lp.groupby(d["Product_ID"]).transform("mean")
    implied = lp - np.log(1 - d["Discount_Percent"] / 100)
    d["implied_rel"] = implied - implied.groupby(d["Product_ID"]).transform("mean")
    if 0 not in set(d["Discount_Percent"]):
        return {"by_level": pd.DataFrame(), "summary": {"consistent_with_post_discount_price": None}}
    base, base_implied = d.loc[d["Discount_Percent"] == 0, ["lp_rel", "implied_rel"]].mean()
    t = d.groupby("Discount_Percent").agg(rows=("lp_rel", "size"), mean_rel=("lp_rel", "mean"),
                                          implied_rel=("implied_rel", "mean"),
                                          implied_sd=("implied_rel", "std")).reset_index()
    t["log_price_gap_vs_0pct"] = t["mean_rel"] - base
    t["log_1_minus_discount"] = np.log(1 - t["Discount_Percent"] / 100)
    t["gap_minus_log_1_minus_discount"] = t["log_price_gap_vs_0pct"] - t["log_1_minus_discount"]
    t["implied_pre_discount_gap_vs_0pct"] = t["implied_rel"] - base_implied
    t = t.drop(columns=["mean_rel", "implied_rel"]).rename(columns={"implied_sd": "implied_pre_discount_sd"})

    s = d.sort_values(SERIES_KEYS + ["WeekDate"])
    lag1 = s.groupby(SERIES_KEYS)["lp_rel"].shift(1)
    max_dev = float(t["gap_minus_log_1_minus_discount"].abs().max())
    discounted = (t["Discount_Percent"] > 0).any()
    return {"by_level": t, "summary": {
        "max_abs_gap_minus_log_1_minus_discount": max_dev,
        "tolerance": POST_DISCOUNT_TOLERANCE,
        "consistent_with_post_discount_price": bool(discounted and max_dev <= POST_DISCOUNT_TOLERANCE),
        "lag1_autocorr_within_product_log_price": float(s["lp_rel"].corr(lag1)),
        "interpretation": "pattern check only; the source does not document whether Price is before or after discount",
    }}


def waste_generation_check(df: pd.DataFrame, decimals: int = 3) -> dict:
    """Is wastage a fixed product ratio of units sold, i.e. floor(k x units)?

    k (the nominal ratio) is each product's highest observed wastage/units ratio, rounded to
    `decimals` places; flooring means observed ratios sit at or just below k.
    """
    d = df[["Product_ID", "Product_Name", "Product_Category", "Shelf_Life_Days", "Units_Sold", "Wastage_Units"]].copy()
    d["ratio"] = d["Wastage_Units"] / d["Units_Sold"]
    d["k"] = d.groupby("Product_ID")["ratio"].transform("max").round(decimals)
    rule = np.floor(d["k"] * d["Units_Sold"] + 1e-9)
    d["floor_match"] = d["Wastage_Units"] == rule
    d["within_1"] = (d["Wastage_Units"] - rule).abs() <= 1
    products = (d.groupby(["Product_ID", "Product_Name", "Product_Category", "Shelf_Life_Days"])
                .agg(rows=("ratio", "size"), nominal_ratio_k=("k", "first"), min_ratio=("ratio", "min"),
                     max_ratio=("ratio", "max"), share_rows_floor_rule=("floor_match", "mean"),
                     share_rows_within_1_unit=("within_1", "mean"))
                .reset_index().sort_values(["Product_Category", "Shelf_Life_Days", "Product_ID"]))
    products["equivalent_waste_rate"] = products["nominal_ratio_k"] / (1 + products["nominal_ratio_k"])
    k_max = float(products["nominal_ratio_k"].max())
    return {"products": products.reset_index(drop=True), "summary": {
        "share_rows_floor_rule": float(d["floor_match"].mean()),
        "share_rows_within_1_unit": float(d["within_1"].mean()),
        "distinct_nominal_ratios": sorted(float(x) for x in products["nominal_ratio_k"].unique()),
        "max_nominal_ratio": k_max,
        "max_equivalent_waste_rate": k_max / (1 + k_max),
        "interpretation": "apparent data-generation rule; not evidence about real-world waste behaviour",
    }}


def discount_mix_check(df: pd.DataFrame) -> pd.DataFrame:
    """Per discount level: category mix of rows and within-product wastage-ratio gap vs 0%.

    Separates product-mix differences between discount levels from changes within a product.
    """
    ratio = df["Wastage_Units"] / df["Units_Sold"]
    rel = ratio - ratio.groupby(df["Product_ID"]).transform("mean")
    mix = pd.crosstab(df["Discount_Percent"], df["Product_Category"], normalize="index").add_prefix("share_")
    out = pd.DataFrame({"rows": df.groupby("Discount_Percent").size(),
                        "within_product_waste_ratio_rel": rel.groupby(df["Discount_Percent"]).mean()})
    if 0 in out.index:
        out["within_product_waste_ratio_gap_vs_0pct"] = out["within_product_waste_ratio_rel"] - out.loc[0, "within_product_waste_ratio_rel"]
    return out.drop(columns="within_product_waste_ratio_rel").join(mix).reset_index()


def discount_timing(df: pd.DataFrame) -> dict:
    """Is discounting concentrated in particular months, holiday weeks or high-marketing rows?"""
    disc = df["Discount_Percent"] > 0
    by_month = disc.groupby(df["month"]).mean()
    by_hol = disc.groupby(df["Holiday_Flag"]).mean()
    lm = np.log(df["Marketing_Spend"].astype(float))
    return {
        "share_discounted_min_month": float(by_month.min()),
        "share_discounted_max_month": float(by_month.max()),
        "share_discounted_holiday": float(by_hol.get(1, np.nan)),
        "share_discounted_non_holiday": float(by_hol.get(0, np.nan)),
        "rho_discount_vs_log_marketing_within_product": spearman_with_ci(
            df["Discount_Percent"] - df["Discount_Percent"].groupby(df["Product_ID"]).transform("mean"),
            lm - lm.groupby(df["Product_ID"]).transform("mean"))["rho"],
    }


# --------------------------------------------------------------------- operations
def operations_summary(df: pd.DataFrame) -> dict:
    prod = product_ranking(df)[["Product_ID", "Product_Name", "Product_Category", "units", "waste", "waste_rate"]]
    attrs = df.drop_duplicates("Product_ID")[["Product_ID", "Shelf_Life_Days", "Supplier_ID", "Supplier_Name",
                                              "Lead_Time_Days", "Supply_Capacity"]]
    prod = prod.merge(attrs, on="Product_ID", how="left")

    suppliers = _summarise(df, ["Supplier_ID", "Supplier_Name", "Lead_Time_Days", "Supply_Capacity"])
    n_prod = df.groupby("Supplier_ID")["Product_ID"].nunique().rename("products").reset_index()
    suppliers = suppliers.merge(n_prod, on="Supplier_ID").sort_values("waste_rate", ascending=False)

    chilled = df[df["Product_Category"].isin(CHILLED_CATEGORIES)]
    chilled_stores = _summarise(chilled, ["Store_ID", "Store_Size", "Cold_Storage_Capacity"]) if len(chilled) else pd.DataFrame()
    if len(chilled_stores):
        chilled_stores["cold_storage_per_1000_sqft"] = chilled_stores["Cold_Storage_Capacity"] / (chilled_stores["Store_Size"] / 1000)

    corr_rows = [
        {"relationship": "shelf life vs waste rate (products, all categories)",
         **spearman_with_ci(prod["Shelf_Life_Days"], prod["waste_rate"])},
        {"relationship": "supplier lead time vs waste rate (products)",
         **spearman_with_ci(prod["Lead_Time_Days"], prod["waste_rate"])},
    ]
    for cat, g in prod.groupby("Product_Category"):
        corr_rows.append({"relationship": f"shelf life vs waste rate (within {cat})",
                          **spearman_with_ci(g["Shelf_Life_Days"], g["waste_rate"])})
    if len(chilled_stores):
        corr_rows.append({"relationship": "cold storage per 1,000 sq ft vs chilled waste rate (stores)",
                          **spearman_with_ci(chilled_stores["cold_storage_per_1000_sqft"], chilled_stores["waste_rate"])})
    return {"products": prod, "suppliers": suppliers.reset_index(drop=True),
            "chilled_stores": chilled_stores, "correlations": pd.DataFrame(corr_rows)}


# ----------------------------------------------------------------------- outliers
def outlier_flags(df: pd.DataFrame, threshold: float = 3.5) -> pd.DataFrame:
    """Robust z-score within each store-product series (median / MAD), with an IQR cross-check."""
    keys = [df[k] for k in SERIES_KEYS]
    units = df["Units_Sold"].astype(float)
    med = units.groupby(keys).transform("median")
    mad = (units - med).abs().groupby(keys).transform("median")
    z = (0.6745 * (units - med) / mad.replace(0, np.nan)).fillna(0.0)
    q1 = units.groupby(keys).transform(lambda s: s.quantile(0.25))
    q3 = units.groupby(keys).transform(lambda s: s.quantile(0.75))
    iqr = q3 - q1
    out = df[KEYS + ["Product_Category", "Units_Sold"]].copy()
    out["series_median"] = med
    out["robust_z"] = z
    out["is_outlier"] = out["robust_z"].abs() > threshold
    out["is_iqr_outlier"] = (units < q1 - 1.5 * iqr) | (units > q3 + 1.5 * iqr)
    return out


def outlier_summary(flags: pd.DataFrame, top_n: int = 20) -> dict:
    by_week = flags.groupby("WeekDate").agg(flagged=("is_outlier", "sum"), iqr_flagged=("is_iqr_outlier", "sum")).reset_index()
    by_category = flags.groupby("Product_Category").agg(flagged=("is_outlier", "sum"), rows=("is_outlier", "size")).reset_index()
    top = flags.loc[flags["is_outlier"]].reindex(
        flags.loc[flags["is_outlier"], "robust_z"].abs().sort_values(ascending=False).index).head(top_n)
    return {"total_flagged": int(flags["is_outlier"].sum()), "total_iqr_flagged": int(flags["is_iqr_outlier"].sum()),
            "share_flagged": float(flags["is_outlier"].mean()), "by_week": by_week,
            "by_category": by_category, "top": top.reset_index(drop=True)}
