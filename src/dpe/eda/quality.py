"""Data-quality checks: structure, missing values, duplicates, completeness, integrity, ranges."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dpe.eda.data import KEYS
from dpe.eda.stats import spearman_with_ci, within_group_demean

TABLE_KEYS = {
    "weekly_sales": ["Week_Number", "Product_ID", "Store_ID"],
    "product_details": ["Product_ID"],
    "store_info": ["Store_ID"],
    "supplier_info": ["Supplier_ID"],
    "weather_data": ["Week_Number", "Region"],
}


def profile_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in df.columns:
        s = df[col]
        orderable = (pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)) or \
            pd.api.types.is_datetime64_any_dtype(s)
        rows.append({
            "column": col,
            "dtype": str(s.dtype),
            "non_null": int(s.notna().sum()),
            "nulls": int(s.isna().sum()),
            "null_pct": float(s.isna().mean() * 100),
            "n_unique": int(s.nunique(dropna=True)),
            "min": s.min() if orderable else None,
            "max": s.max() if orderable else None,
        })
    return pd.DataFrame(rows)


def duplicate_summary(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, df in raw.items():
        keys = [k for k in TABLE_KEYS.get(name, []) if k in df.columns]
        rows.append({
            "table": name,
            "rows": len(df),
            "exact_duplicate_rows": int(df.duplicated().sum()),
            "key_columns": ", ".join(keys),
            "duplicate_keys": int(df.duplicated(subset=keys).sum()) if keys else None,
        })
    return pd.DataFrame(rows)


def completeness(df: pd.DataFrame) -> dict:
    n_p, n_s, n_w = df["Product_ID"].nunique(), df["Store_ID"].nunique(), df["WeekDate"].nunique()
    expected = n_p * n_s * n_w
    actual = int(df.drop_duplicates(subset=KEYS).shape[0])
    return {"products": n_p, "stores": n_s, "weeks": n_w, "expected_rows": expected,
            "actual_rows": actual, "missing_rows": expected - actual,
            "first_week": str(df["WeekDate"].min().date()), "last_week": str(df["WeekDate"].max().date())}


def completeness_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Products with a sales row, per store (rows) and week (columns)."""
    return df.pivot_table(index="Store_ID", columns="WeekDate", values="Product_ID",
                          aggfunc="nunique", fill_value=0)


def _examples(values) -> str:
    values = sorted(set(values), key=str)
    return ", ".join(map(str, values[:5])) + (" ..." if len(values) > 5 else "")


def referential_integrity(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    sales, prod = raw["weekly_sales"], raw["product_details"]
    store, sup, wx = raw["store_info"], raw["supplier_info"], raw["weather_data"]
    checks = {
        "sales products missing from product table": set(sales.Product_ID) - set(prod.Product_ID),
        "sales stores missing from store table": set(sales.Store_ID) - set(store.Store_ID),
        "product suppliers missing from supplier table": set(prod.Supplier_ID) - set(sup.Supplier_ID),
        "store regions missing from weather table": set(store.Region) - set(wx.Region),
        "weather regions without stores": set(wx.Region) - set(store.Region),
        "products never sold": set(prod.Product_ID) - set(sales.Product_ID),
        "suppliers with no products": set(sup.Supplier_ID) - set(prod.Supplier_ID),
    }
    return pd.DataFrame([{"check": k, "count": len(v), "examples": _examples(v)} for k, v in checks.items()])


def range_checks(df: pd.DataFrame) -> dict:
    return {
        "negative_units_sold": int((df.Units_Sold < 0).sum()),
        "zero_units_sold": int((df.Units_Sold == 0).sum()),
        "negative_wastage": int((df.Wastage_Units < 0).sum()),
        "wastage_exceeds_units_sold": int((df.Wastage_Units > df.Units_Sold).sum()),
        "non_positive_price": int((df.Price <= 0).sum()),
        "discount_outside_0_100": int(((df.Discount_Percent < 0) | (df.Discount_Percent > 100)).sum()),
        "negative_marketing_spend": int((df.Marketing_Spend < 0).sum()),
        "missing_values_in_analysis_frame": int(df.isna().sum().sum()),
    }


def waste_rate_cap_check(df: pd.DataFrame, tolerance: float = 0.0005) -> dict:
    wr = df["waste_rate"].dropna()
    mx = float(wr.max())
    share_at_max = float((wr >= mx - tolerance).mean())
    return {"min": float(wr.min()), "median": float(wr.median()), "p95": float(wr.quantile(0.95)),
            "p99": float(wr.quantile(0.99)), "max": mx, "share_of_rows_at_max": share_at_max,
            "cap_suspected": bool(share_at_max > 0.01)}


def price_variation(df: pd.DataFrame) -> dict:
    per_product = df.groupby("Product_ID")["Price"].agg(["nunique", "mean", "std"])
    stores_per_product_week = df.groupby(["Product_ID", "WeekDate"])["Price"].nunique()
    rel = within_group_demean(df, ["Price", "Discount_Percent"], "Product_ID")
    corr = spearman_with_ci(rel["Price"], rel["Discount_Percent"])
    return {
        "median_distinct_prices_per_product": float(per_product["nunique"].median()),
        "median_price_cv_within_product": float((per_product["std"] / per_product["mean"]).median()),
        "max_distinct_prices_same_product_week": int(stores_per_product_week.max()),
        "share_product_weeks_with_differing_store_prices": float((stores_per_product_week > 1).mean()),
        "within_product_price_vs_discount_rho": corr["rho"],
        "discount_levels": sorted(int(x) for x in df["Discount_Percent"].unique()),
        "share_rows_discounted": float((df["Discount_Percent"] > 0).mean()),
    }


def run_quality(raw: dict[str, pd.DataFrame], df: pd.DataFrame) -> dict:
    return {
        "profile": profile_table(df),
        "duplicates": duplicate_summary(raw),
        "completeness": completeness(df),
        "completeness_matrix": completeness_matrix(df),
        "referential": referential_integrity(raw),
        "ranges": range_checks(df),
        "waste_cap": waste_rate_cap_check(df),
        "price_variation": price_variation(df),
    }
