"""Analysis functions on a small synthetic dataset with known values."""
import numpy as np
import pandas as pd
import pytest

from conftest import EDA_PRODUCTS, EDA_STORES, EDA_WEEKS
from dpe.eda import analysis as A
from dpe.eda.data import KEYS, build_analysis_frame, iso_week_to_monday, waste_rate_of

N_ROWS = len(EDA_PRODUCTS) * len(EDA_STORES) * EDA_WEEKS


@pytest.fixture
def df(eda_raw):
    return build_analysis_frame(eda_raw)


def test_iso_weeks_parse_to_mondays():
    s = iso_week_to_monday(pd.Series(["2024-W01", "2024-W52"]))
    assert list(s) == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-23")]
    with pytest.raises(ValueError):
        iso_week_to_monday(pd.Series(["not a week"]))


def test_analysis_frame_keys_and_joins(df):
    assert len(df) == N_ROWS
    assert not df.duplicated(subset=KEYS).any()
    assert not [c for c in df.columns if c.endswith(("_x", "_y"))]
    assert {"Supplier_Name", "Avg_Temperature", "Holiday_Flag", "Shelf_Life_Days"} <= set(df.columns)
    assert "Wales" not in set(df["Region"])
    assert df.isna().sum().sum() == 0


def test_waste_rate_is_ratio_of_sums_not_mean_of_ratios():
    assert waste_rate_of([90, 10], [10, 10]) == pytest.approx(20 / 120)
    assert waste_rate_of([90, 10], [10, 10]) != pytest.approx(np.mean([10 / 100, 10 / 20]))
    assert np.isnan(waste_rate_of([0], [0]))


def test_weekly_trend_reconciles(df):
    w = A.weekly_trend(df)
    assert len(w) == EDA_WEEKS
    assert w["units"].sum() == df["Units_Sold"].sum()
    first = df[df["WeekDate"] == df["WeekDate"].min()]
    assert w.iloc[0]["waste_rate"] == pytest.approx(waste_rate_of(first["Units_Sold"], first["Wastage_Units"]))
    assert w.loc[w["WeekDate"] == pd.Timestamp("2024-01-01"), "holiday_row_share"].iloc[0] == pytest.approx(6 / 9)


def test_month_profile_uses_weeks_in_month(df):
    m = A.month_profile(df)
    assert (m["mean_weekly_units"] == m["units"] / m["weeks_in_month"]).all()


def test_category_product_store_region_summaries(df):
    c = A.category_summary(df)
    assert c["units"].sum() == df["Units_Sold"].sum()
    assert c["share_of_units"].sum() == pytest.approx(1.0)
    p = A.product_ranking(df)
    assert p["cumulative_share_units"].is_monotonic_increasing
    assert p["cumulative_share_units"].iloc[-1] == pytest.approx(1.0)
    assert 0 < A.pareto_share(p) <= 1
    s = A.store_summary(df)
    assert np.allclose(s["units_per_1000_sqft"], s["units"] / (s["Store_Size"] / 1000))
    r = A.region_summary(df).set_index("Region")
    assert r.loc["London", "stores"] == 2 and r.loc["Midlands", "stores"] == 1


def test_holiday_comparison_is_within_series(df):
    h = A.holiday_comparison(df)
    assert len(h["table"]) == 2 * len(EDA_PRODUCTS)  # only London stores have holiday weeks
    assert h["summary"]["n"] == 2 * len(EDA_PRODUCTS)


def test_discount_summary(df):
    d = A.discount_summary(df).set_index("Discount_Percent")
    assert d["rows"].sum() == len(df)
    assert d.loc[0, "median_descriptive_lift_pct"] == pytest.approx(0.0)
    assert (d["ci95_units"] >= 0).all()


def test_within_product_relationship(df):
    rel = A.within_product_relationship(df, "Price", log_x=True, n_bins=4)
    scopes = set(rel["correlations"]["scope"])
    assert {"All products", "Bakery", "Dairy"} <= scopes
    assert (rel["binned"]["units_index"] > 0).all()
    assert rel["binned"]["rows"].groupby(rel["binned"]["scope"]).sum()["All products"] == len(df)


def test_operations_summary(df):
    ops = A.operations_summary(df)
    assert len(ops["products"]) == len(EDA_PRODUCTS)
    assert set(ops["suppliers"]["Supplier_ID"]) == {1, 2}
    assert "shelf life vs waste rate (products, all categories)" in set(ops["correlations"]["relationship"])


def test_category_index_is_based_on_each_category_average_week(df):
    idx = A.category_weekly_index(df)
    assert np.allclose(idx.mean(), 100.0)
    # Not anchored to week 1: the first row is not forced to 100.
    assert not np.allclose(idx.iloc[0], 100.0)


def _rule_frame(post_discount: bool, seed: int = 0) -> pd.DataFrame:
    """2 products x 2 stores x 40 weeks; noise-like base price, discounts 0/10/25%."""
    rng = np.random.default_rng(seed)
    rows = []
    for pid in (1, 2):
        for sid in (10, 11):
            for w in range(40):
                d = [0, 0, 10, 25][(w + sid) % 4]
                base = 3.0 * pid * np.exp(rng.normal(0, 0.02))
                units = int(500 + 20 * w + 100 * pid)
                rows.append({"Product_ID": pid, "Store_ID": sid, "WeekDate": pd.Timestamp("2024-01-01") + pd.Timedelta(weeks=w),
                             "Discount_Percent": d, "Price": base * (1 - d / 100) if post_discount else base,
                             "Units_Sold": units, "Wastage_Units": int(np.floor((0.05 * pid) * units)),
                             "Product_Name": f"P{pid}", "Product_Category": "Dairy", "Shelf_Life_Days": 7 * pid})
    return pd.DataFrame(rows)


def test_price_generation_check_detects_post_discount_prices():
    res = A.price_generation_check(_rule_frame(post_discount=True))
    t = res["by_level"].set_index("Discount_Percent")
    assert res["summary"]["consistent_with_post_discount_price"] is True
    assert t.loc[25, "log_price_gap_vs_0pct"] == pytest.approx(np.log(0.75), abs=0.02)
    assert t.loc[25, "implied_pre_discount_gap_vs_0pct"] == pytest.approx(0.0, abs=0.02)
    assert np.isfinite(res["summary"]["lag1_autocorr_within_product_log_price"])


def test_price_generation_check_rejects_prices_unrelated_to_discount():
    res = A.price_generation_check(_rule_frame(post_discount=False))
    assert res["summary"]["consistent_with_post_discount_price"] is False


def test_price_generation_check_without_undiscounted_rows():
    frame = _rule_frame(post_discount=True)
    res = A.price_generation_check(frame[frame["Discount_Percent"] > 0])
    assert res["by_level"].empty and res["summary"]["consistent_with_post_discount_price"] is None


def test_waste_generation_check_recovers_fixed_ratios():
    res = A.waste_generation_check(_rule_frame(post_discount=True))
    p = res["products"].set_index("Product_ID")
    assert res["summary"]["share_rows_floor_rule"] == 1.0
    assert p.loc[1, "nominal_ratio_k"] == pytest.approx(0.05) and p.loc[2, "nominal_ratio_k"] == pytest.approx(0.10)
    assert res["summary"]["max_equivalent_waste_rate"] == pytest.approx(0.10 / 1.10)


def test_waste_generation_check_flags_non_ratio_wastage():
    frame = _rule_frame(post_discount=True)
    frame["Wastage_Units"] = np.random.default_rng(1).integers(0, 60, len(frame))
    assert A.waste_generation_check(frame)["summary"]["share_rows_floor_rule"] < 0.5


def test_discount_mix_and_timing(df):
    mix = A.discount_mix_check(df).set_index("Discount_Percent")
    share_cols = [c for c in mix.columns if c.startswith("share_")]
    assert np.allclose(mix[share_cols].sum(axis=1), 1.0)
    assert mix.loc[0, "within_product_waste_ratio_gap_vs_0pct"] == pytest.approx(0.0)
    t = A.discount_timing(df)
    assert 0 <= t["share_discounted_min_month"] <= t["share_discounted_max_month"] <= 1


def test_month_adjusted_correlation_removes_pure_seasonal_association(df):
    seasonal = df.copy()
    # x depends only on month, and units follow the same monthly pattern: raw rho is high,
    # but after removing month effects nothing is left.
    seasonal["x"] = seasonal["month"].astype(float)
    seasonal["Units_Sold"] = (100 * seasonal["month"] + seasonal["Product_ID"] - 900).astype(int)
    adj = A.month_adjusted_correlations(seasonal, "x").set_index("scope")
    assert np.isnan(adj.loc["All products", "rho"]) or abs(adj.loc["All products", "rho"]) < 1e-6
    assert set(adj["adjustment"]) == {"store-product series + month"}


def test_outliers_flag_injected_spike_only(df):
    assert A.outlier_flags(df)["is_outlier"].sum() == 0
    spiked = df.copy()
    idx = spiked.index[(spiked.Store_ID == 500) & (spiked.Product_ID == 1000)][5]
    spiked.loc[idx, "Units_Sold"] *= 10
    flags = A.outlier_flags(spiked)
    assert flags["is_outlier"].sum() == 1
    assert flags.loc[idx, "is_outlier"]
    summary = A.outlier_summary(flags)
    assert summary["total_flagged"] == 1 and len(summary["top"]) == 1
