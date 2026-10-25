"""CP1: the clean weekly forecasting panel (one row per Store_ID x Product_ID x WeekDate).

Built from the checksum-verified V2 raw files through the same joins as the EDA, then
validated (complete grid, consecutive weeks, unique keys) and reconciled against the
final EDA run's tables. The panel is the only data source the feature builders read.

Column roles are explicit (see COLUMN_ROLES): history values, static attributes, the
holiday calendar, and columns that must never become model inputs (identifiers used
only as keys, and wastage, which is a same-week function of units sold).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from dpe.config import FINAL_EDA_RUN_DIR
from dpe.eda.data import build_analysis_frame, load_raw

KEYS = ["Store_ID", "Product_ID", "WeekDate"]
SERIES_KEYS = ["Store_ID", "Product_ID"]

EXPECTED = {"rows": 37_440, "products": 48, "stores": 15, "weeks": 52,
            "units": 61_482_249, "wastage": 4_786_490}

# Weekly values observed at the end of each week (history once the week has passed).
WEEKLY_VALUES = ["Units_Sold", "Wastage_Units", "Price", "Discount_Percent", "Marketing_Spend",
                 "Avg_Temperature", "Rainfall"]
# Fixed per series; known at any forecast origin.
STATIC_ATTRIBUTES = ["Product_Category", "Shelf_Life_Days", "Region", "Store_Size", "Cold_Storage_Capacity",
                     "Lead_Time_Days"]
# Known-in-advance calendar (assumption: the regional holiday calendar is published ahead of time).
CALENDAR = ["Holiday_Flag"]

COLUMN_ROLES = {
    "key": KEYS + ["week_index"],
    "weekly_value": WEEKLY_VALUES,
    "static": STATIC_ATTRIBUTES,
    "calendar": CALENDAR,
    "never_a_feature": ["Wastage_Units", "Store_ID", "Product_ID", "Supplier_ID"],
}
PANEL_COLUMNS = KEYS + ["week_index"] + WEEKLY_VALUES + STATIC_ATTRIBUTES + CALENDAR + ["Supplier_ID"]


def build_panel(raw: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Return the validated panel sorted by series then week, with a 1-based week_index."""
    raw = raw if raw is not None else load_raw()  # verifies raw checksums when loading from disk
    df = build_analysis_frame(raw)
    weeks = np.sort(df["WeekDate"].unique())
    df["week_index"] = df["WeekDate"].map({w: i + 1 for i, w in enumerate(weeks)}).astype(int)
    panel = df[PANEL_COLUMNS].sort_values(SERIES_KEYS + ["week_index"]).reset_index(drop=True)
    validate_panel(panel)
    return panel


def validate_panel(panel: pd.DataFrame, expected: dict | None = None) -> dict:
    """Structural checks; raises ValueError on any failure. `expected` adds exact-size checks."""
    missing = [c for c in KEYS + ["week_index", "Units_Sold"] if c not in panel.columns]
    if missing:
        raise ValueError(f"Panel is missing required columns: {missing}")
    if panel[KEYS].isna().any().any():
        raise ValueError("Panel has missing Store_ID, Product_ID or WeekDate values")
    if panel.duplicated(subset=KEYS).any():
        raise ValueError("Duplicate Store_ID/Product_ID/WeekDate rows in panel")
    if (panel["WeekDate"].dt.dayofweek != 0).any():
        raise ValueError("Every WeekDate must be a Monday")
    weeks = np.sort(panel["WeekDate"].unique())
    if len(weeks) > 1 and (np.diff(weeks) != np.timedelta64(7, "D")).any():
        raise ValueError("Panel weeks are not consecutive 7-day steps")
    n_series = panel.groupby(SERIES_KEYS).ngroups
    if len(panel) != n_series * len(weeks):
        raise ValueError(f"Incomplete grid: {len(panel)} rows for {n_series} series x {len(weeks)} weeks")
    if panel[[c for c in WEEKLY_VALUES + STATIC_ATTRIBUTES + CALENDAR if c in panel.columns]].isna().any().any():
        raise ValueError("Panel has missing values")
    summary = {"rows": int(len(panel)), "products": int(panel["Product_ID"].nunique()),
               "stores": int(panel["Store_ID"].nunique()), "weeks": int(len(weeks)),
               "series": int(n_series), "units": int(panel["Units_Sold"].sum()),
               "wastage": int(panel["Wastage_Units"].sum()) if "Wastage_Units" in panel else None,
               "first_week": str(pd.Timestamp(weeks[0]).date()), "last_week": str(pd.Timestamp(weeks[-1]).date())}
    if expected:
        bad = {k: (summary[k], v) for k, v in expected.items() if summary.get(k) != v}
        if bad:
            raise ValueError(f"Panel does not match expected values (actual, expected): {bad}")
    return summary


def reconcile_with_eda(panel: pd.DataFrame, eda_run_dir: Path = FINAL_EDA_RUN_DIR) -> dict:
    """Compare weekly and category totals with the final EDA run's tables (read-only)."""
    weekly = pd.read_csv(Path(eda_run_dir) / "tables" / "weekly_trend.csv", parse_dates=["WeekDate"])
    cats = pd.read_csv(Path(eda_run_dir) / "tables" / "category_summary.csv")
    pw = panel.groupby("WeekDate").agg(units=("Units_Sold", "sum"), waste=("Wastage_Units", "sum")).reset_index()
    w = pw.merge(weekly[["WeekDate", "units", "waste"]], on="WeekDate", how="outer", suffixes=("", "_eda"),
                 indicator=True)
    pc = panel.groupby("Product_Category").agg(units=("Units_Sold", "sum"),
                                               waste=("Wastage_Units", "sum")).reset_index()
    c = pc.merge(cats[["Product_Category", "units", "waste"]], on="Product_Category", how="outer",
                 suffixes=("", "_eda"), indicator=True)
    result = {
        "eda_run": Path(eda_run_dir).name,
        "weeks_compared": int(len(w)),
        "weeks_matched": bool((w["_merge"] == "both").all()),
        "weekly_units_equal": bool((w["units"] == w["units_eda"]).all()),
        "weekly_wastage_equal": bool((w["waste"] == w["waste_eda"]).all()),
        "categories_compared": int(len(c)),
        "category_units_equal": bool((c["_merge"] == "both").all() and (c["units"] == c["units_eda"]).all()),
        "category_wastage_equal": bool((c["_merge"] == "both").all() and (c["waste"] == c["waste_eda"]).all()),
        "total_units": int(panel["Units_Sold"].sum()), "eda_total_units": int(weekly["units"].sum()),
        "total_wastage": int(panel["Wastage_Units"].sum()), "eda_total_wastage": int(weekly["waste"].sum()),
    }
    result["reconciled"] = all(result[k] for k in ("weeks_matched", "weekly_units_equal", "weekly_wastage_equal",
                                                    "category_units_equal", "category_wastage_equal"))
    return result


def load_verified_panel() -> tuple[pd.DataFrame, dict]:
    """The protected CP1 panel: checksums verified, then compared value by value with a fresh rebuild
    from the checksum-verified raw files. Returns the (identical) rebuilt panel and the evidence."""
    from dpe.config import FORECAST_PANEL_RUN_DIR, FORECAST_PANEL_RUN_ID, PROJECT_ROOT, load_expected_checksums, sha256_file

    expected = {k: v for k, v in load_expected_checksums().items()
                if k.startswith(f"outputs/runs/{FORECAST_PANEL_RUN_ID}/")}
    if not expected:
        raise ValueError(f"No recorded checksums for the panel run {FORECAST_PANEL_RUN_ID}")
    for rel, digest in expected.items():
        if sha256_file(PROJECT_ROOT / rel) != digest:
            raise ValueError(f"Checksum mismatch for {rel}")
    saved = pd.read_csv(FORECAST_PANEL_RUN_DIR / "forecast_panel.csv", parse_dates=["WeekDate"])
    rebuilt = build_panel()
    pd.testing.assert_frame_equal(saved, rebuilt, check_dtype=False, check_exact=False, rtol=1e-12, atol=1e-9)
    return rebuilt, {"panel_run": FORECAST_PANEL_RUN_ID, "files_checksum_verified": sorted(expected),
                     "rebuilt_from_raw_equals_saved_panel": True}


def write_panel_run(panel: pd.DataFrame, reconciliation: dict | None, run_id: str | None = None,
                    input_hashes: dict | None = None) -> Path:
    """Save the panel, its calendar and a manifest to a brand-new outputs/runs/<run_id>/ folder."""
    from datetime import datetime

    from dpe.config import new_run_dir, sha256_file
    from dpe.eda.data import DATASET_LABEL
    from dpe.eda.outputs import save_json, save_table

    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_forecast_panel"
    run_dir = new_run_dir(run_id)
    save_table(panel, run_dir / "forecast_panel.csv")
    save_table(holiday_calendar(panel), run_dir / "holiday_calendar.csv")
    save_json({
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "step": "4B CP1 - clean weekly forecasting panel (no model training)",
        "dataset_label": DATASET_LABEL,
        "inputs_sha256": input_hashes or {"note": "not recorded"},
        "summary": validate_panel(panel),
        "reconciliation_with_final_eda": reconciliation,
        "column_roles": COLUMN_ROLES,
        "assumptions": ["Holiday_Flag (from weather_data.csv) is treated as a regional calendar known in advance.",
                        "Wastage_Units is kept for reconciliation only and is never a model input."],
        "outputs_sha256": {name: sha256_file(run_dir / name) for name in ("forecast_panel.csv", "holiday_calendar.csv")},
    }, run_dir / "panel_manifest.json")
    return run_dir


def holiday_calendar(panel: pd.DataFrame) -> pd.DataFrame:
    """Known-in-advance calendar per (Region, week): holiday flag, national share and month.

    national_holiday_share = share of the panel's store regions with a holiday that week.
    """
    cal = panel[["Region", "WeekDate", "week_index", "Holiday_Flag"]].drop_duplicates()
    if cal.duplicated(subset=["Region", "week_index"]).any():
        raise ValueError("Holiday flag differs within a region and week")
    share = cal.groupby("week_index")["Holiday_Flag"].mean().rename("national_holiday_share")
    cal = cal.merge(share, on="week_index")
    cal["month"] = cal["WeekDate"].dt.month
    return cal.sort_values(["Region", "week_index"]).reset_index(drop=True)
