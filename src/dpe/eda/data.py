"""Load the V2 raw datasets and build one analysis table keyed by Store_ID, Product_ID, WeekDate."""
from __future__ import annotations

import numpy as np
import pandas as pd

from dpe.config import RAW_FILES, raw_path, verify_raw_inputs

KEYS = ["Store_ID", "Product_ID", "WeekDate"]
SERIES_KEYS = ["Store_ID", "Product_ID"]
CHILLED_CATEGORIES = ("Dairy", "Meat")

DATASET_LABEL = "Apparently synthetic dataset; provenance unconfirmed"
PRICE_NOTE = (
    "Price is used as recorded. The data does not say whether it is before or after any discount, "
    "so 'recorded sales value' (units x recorded price) may differ from actual revenue."
)
WASTE_RATE_DEFINITION = "Waste rate = total wastage units / (total units sold + total wastage units)"
ONE_YEAR_NOTE = (
    "Only one year (2024) is available: patterns are within-year and cannot be shown to recur annually."
)


def load_raw(verify: bool = True) -> dict[str, pd.DataFrame]:
    """Read the five approved CSVs from V2 data/raw (checksum-verified by default)."""
    if verify:
        verify_raw_inputs()
    return {name.removesuffix(".csv"): pd.read_csv(raw_path(name)) for name in RAW_FILES}


def iso_week_to_monday(labels: pd.Series) -> pd.Series:
    """Convert labels like '2024-W01' to the Monday starting that ISO week."""
    out = pd.to_datetime(labels.astype(str).str.strip() + "-1", format="%G-W%V-%u", errors="coerce")
    if out.isna().any():
        raise ValueError(f"{int(out.isna().sum())} week labels could not be parsed as ISO weeks")
    return out


def waste_rate_of(units, waste) -> float:
    """Ratio of sums: total waste / (total units sold + total waste). Never a mean of row rates."""
    u = float(np.nansum(np.asarray(units, dtype=float)))
    w = float(np.nansum(np.asarray(waste, dtype=float)))
    total = u + w
    return w / total if total > 0 else float("nan")


def build_analysis_frame(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Join sales to product, store, supplier and weather tables (all many-to-one joins)."""
    sales = raw["weekly_sales"].copy()
    sales["WeekDate"] = iso_week_to_monday(sales["Week_Number"])

    weather = raw["weather_data"].copy()
    weather["WeekDate"] = iso_week_to_monday(weather["Week_Number"])
    weather = weather.drop(columns=["Week_Number"])

    df = (
        sales.merge(raw["product_details"], on="Product_ID", how="left", validate="many_to_one")
        .merge(raw["store_info"], on="Store_ID", how="left", validate="many_to_one")
        .merge(raw["supplier_info"], on="Supplier_ID", how="left", validate="many_to_one")
        .merge(weather, on=["Region", "WeekDate"], how="left", validate="many_to_one")
    )

    df["waste_rate"] = df["Wastage_Units"] / (df["Units_Sold"] + df["Wastage_Units"])
    df["recorded_sales_value"] = df["Units_Sold"] * df["Price"]
    df["is_discounted"] = df["Discount_Percent"] > 0
    df["month"] = df["WeekDate"].dt.month
    df["week_of_year"] = df["WeekDate"].dt.isocalendar().week.astype(int)

    df = df.sort_values(KEYS).reset_index(drop=True)
    if df.duplicated(subset=KEYS).any():
        raise ValueError("Duplicate Store_ID/Product_ID/WeekDate keys in analysis frame")
    return df
