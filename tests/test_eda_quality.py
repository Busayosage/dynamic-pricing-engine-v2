"""Data-quality tests: the real V2 data (invariants and reconciliation) and the check functions."""
import numpy as np
import pandas as pd
import pytest

from dpe.config import REFERENCE_DIR
from dpe.eda import analysis as A
from dpe.eda import quality as Q
from dpe.eda.data import KEYS, build_analysis_frame, load_raw


@pytest.fixture(scope="module")
def real():
    raw = load_raw()  # checksum-verified, V2 data/raw only
    return raw, build_analysis_frame(raw)


# ----------------------------------------------------------------- real data
def test_real_grid_is_complete(real):
    _, df = real
    c = Q.completeness(df)
    assert (c["products"], c["stores"], c["weeks"]) == (48, 15, 52)
    assert c["actual_rows"] == c["expected_rows"] == 37_440 and c["missing_rows"] == 0


def test_real_keys_unique_no_nulls_and_mondays(real):
    _, df = real
    assert not df.duplicated(subset=KEYS).any()
    assert df.isna().sum().sum() == 0
    assert df["WeekDate"].min() == pd.Timestamp("2024-01-01")
    assert df["WeekDate"].max() == pd.Timestamp("2024-12-23")
    assert (df["WeekDate"].dt.dayofweek == 0).all()


def test_real_referential_integrity_only_wales_unused(real):
    raw, _ = real
    ref = Q.referential_integrity(raw).set_index("check")
    assert ref.loc["weather regions without stores", "count"] == 1
    assert ref.loc["weather regions without stores", "examples"] == "Wales"
    assert ref.drop(index="weather regions without stores")["count"].sum() == 0


def test_real_duplicates_and_ranges(real):
    raw, df = real
    dup = Q.duplicate_summary(raw)
    assert dup["exact_duplicate_rows"].sum() == 0 and dup["duplicate_keys"].sum() == 0
    assert all(v == 0 for v in Q.range_checks(df).values())


def test_real_waste_rate_bounds_and_cap(real):
    _, df = real
    assert df["waste_rate"].between(0, 1).all()
    cap = Q.waste_rate_cap_check(df)
    assert cap["max"] == pytest.approx(0.13, abs=0.001)
    assert cap["cap_suspected"]


def test_real_join_matches_oct_2025_merged_reference(real):
    _, df = real
    ref = pd.read_csv(REFERENCE_DIR / "merged_dataset.csv", parse_dates=["WeekDate"])
    m = df.merge(ref, on=KEYS, suffixes=("", "_ref"), validate="one_to_one")
    assert len(m) == len(df) == len(ref)
    for col in ["Units_Sold", "Wastage_Units", "Price", "Region", "Supplier_Name", "Avg_Temperature", "Holiday_Flag"]:
        assert (m[col] == m[f"{col}_ref"]).all(), col


def test_real_totals_reconcile_with_legacy_notebook(real):
    _, df = real
    assert df["Units_Sold"].sum() == 61_482_249
    assert df["Wastage_Units"].sum() == 4_786_490
    assert round(df["Units_Sold"].mean(), 2) == 1642.15
    disc = A.discount_summary(df).set_index("Discount_Percent")
    assert round(disc.loc[0, "mean_units"], 2) == 1574.22
    assert round(disc.loc[25, "mean_units"], 2) == 2382.44


# ------------------------------------------------------- check functions
def test_duplicate_and_completeness_checks_detect_problems(eda_raw):
    raw = dict(eda_raw)
    raw["weekly_sales"] = pd.concat([raw["weekly_sales"], raw["weekly_sales"].iloc[[0]]], ignore_index=True)
    dup = Q.duplicate_summary(raw).set_index("table")
    assert dup.loc["weekly_sales", "exact_duplicate_rows"] == 1
    df = build_analysis_frame(eda_raw).iloc[1:]
    assert Q.completeness(df)["missing_rows"] == 1


def test_referential_and_range_checks_detect_problems(eda_raw):
    raw = dict(eda_raw)
    bad = raw["weekly_sales"].iloc[[0]].assign(Product_ID=9999)
    raw["weekly_sales"] = pd.concat([raw["weekly_sales"], bad], ignore_index=True)
    ref = Q.referential_integrity(raw).set_index("check")
    assert ref.loc["sales products missing from product table", "count"] == 1
    df = build_analysis_frame(eda_raw)
    df.loc[0, "Units_Sold"] = -1
    df.loc[1, "Wastage_Units"] = 10_000
    r = Q.range_checks(df)
    # Row 0 (units -1, wastage 5) also has wastage > units sold, so it trips both rules; row 1 trips one.
    expected = {k: 0 for k in r} | {"negative_units_sold": 1, "wastage_exceeds_units_sold": 2}
    assert r == expected


def test_profile_reports_nulls(eda_raw):
    df = build_analysis_frame(eda_raw)
    df.loc[0:4, "Price"] = np.nan
    prof = Q.profile_table(df).set_index("column")
    assert prof.loc["Price", "nulls"] == 5
