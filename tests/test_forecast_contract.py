"""Step 5B-1 forecast contract: schema stability, validation, as-of uncertainty, leakage (future scrambling),
decision-time vs replay separation, alignment with the protected predictions, reproducibility, output safety."""
import json
import shutil
import uuid

import numpy as np
import pandas as pd
import pytest

from conftest import FAKE_FIRST_ORIGIN as FIRST_ORIGIN
from conftest import FAKE_LAST_TARGET as LAST_TARGET
from conftest import fake_contract_predictions as _fake_predictions
from conftest import forecast_raw
from dpe import config
from dpe.decision import forecast_contract as FC
from dpe.forecast.panel import build_panel


@pytest.fixture(scope="module")
def panel():
    return build_panel(forecast_raw())


@pytest.fixture(scope="module")
def preds(panel):
    return _fake_predictions(panel)


@pytest.fixture(scope="module")
def built(preds, panel):
    return FC.build_contract(preds, panel, "TEST_RUN")


# ------------------------------------------------------- schema stability
def test_contract_schema_is_stable_and_separates_replay_fields():
    assert FC.CONTRACT_VERSION == "1.0"
    assert FC.CONTRACT_COLUMNS[:8] == ["contract_version", "forecast_run_id", "source_run_id", "model_name",
                                       "model_role", "forecast_method", "horizon_weeks", "scenario"]
    assert len(FC.CONTRACT_COLUMNS) == 33 and len(set(FC.CONTRACT_COLUMNS)) == 33
    for f in FC.REPLAY_ONLY_FIELDS:
        assert f not in FC.CONTRACT_COLUMNS and FC.FIELD_AVAILABILITY[f] == "REPLAY_ONLY"
    assert all(FC.FIELD_AVAILABILITY[c] == "DECISION_TIME" for c in FC.CONTRACT_COLUMNS)
    assert {"SALES_NOT_DEMAND", "CHRISTMAS_BIAS", "DISCOUNT_WEEK_BIAS", "WEEKLY_GRANULARITY",
            "SYNTHETIC_DATA"} <= set(FC.LIMITATIONS)
    assert {h: m["model_name"] for h, m in FC.METHODS.items()} == {1: "random_forest", 4: "mean_4w"}


def test_built_contract_validates(built):
    s = FC.validate_contract(built["contract"], built["replay"])
    assert set(s["rows_by_horizon"]) == {"H1", "H4"}
    c = built["contract"]
    assert (c["limitation_codes"] == "|".join(FC.LIMITATIONS)).all()
    assert c["risk_flags"].str.contains("DISCOUNT_STATUS_UNKNOWN_S0").all()
    # Rows carry short codes; every code is explained once in the code dictionary.
    d = FC.code_dictionary()
    assert set(c["forecast_method"]) <= set(d["forecast_method"]) and set(c["dataset_label"]) == {"SYNTHETIC_UNCONFIRMED"}
    assert max(c[col].astype(str).str.len().max() for col in c.columns) <= 120


def test_validation_rejects_unknown_codes(built):
    c = built["contract"].copy()
    c.loc[0, "risk_flags"] += "|MYSTERY_FLAG"
    with pytest.raises(ValueError, match="unknown risk or limitation codes"):
        FC.validate_contract(c)


@pytest.mark.parametrize("corrupt", ["dup", "horizon", "target", "negative", "monotone", "bounds_when_unavailable",
                                     "missing", "replay_leak", "wrong_model"])
def test_validation_rejects_violations(built, corrupt):
    c = built["contract"].copy()
    avail = c.index[c["uncertainty_status"] == "AVAILABLE"][0]
    unavail = c.index[c["uncertainty_status"] != "AVAILABLE"][0]
    if corrupt == "dup":
        c = pd.concat([c, c.iloc[[0]]], ignore_index=True)
    elif corrupt == "horizon":
        c.loc[0, "horizon_weeks"] = 2
    elif corrupt == "target":
        c.loc[0, "target_week"] += 1
    elif corrupt == "negative":
        c.loc[0, "predicted_units"] = -1.0
    elif corrupt == "monotone":
        c.loc[avail, "lower_p10_units"] = c.loc[avail, "upper_p90_units"] + 1
    elif corrupt == "bounds_when_unavailable":
        c.loc[unavail, ["lower_p10_units", "median_p50_units", "upper_p90_units"]] = 1.0
    elif corrupt == "missing":
        c.loc[0, "reference_price_asof"] = np.nan
    elif corrupt == "replay_leak":
        c["observed_units"] = 1
    elif corrupt == "wrong_model":
        c.loc[c["horizon_weeks"] == 4, "model_name"] = "catboost"
    with pytest.raises(ValueError, match="Forecast contract invalid"):
        FC.validate_contract(c)


# ------------------------------------------------------------ uncertainty
def test_uncertainty_uses_only_errors_observed_by_the_origin(built, preds):
    c = built["contract"]
    avail = c[c["uncertainty_status"] == "AVAILABLE"]
    last_err = avail["uncertainty_error_target_weeks"].str.split("-").str[1].astype(int)
    assert (last_err <= avail["origin_week"]).all()
    # Independent recomputation for one row.
    row = avail.iloc[len(avail) // 2]
    cats = build_panel(forecast_raw()).drop_duplicates("Product_ID").set_index("Product_ID")["Product_Category"]
    e = preds[(preds["horizon"] == row["horizon_weeks"]) & (preds["target_week"] <= row["origin_week"])
              & (preds["Product_ID"].map(cats) == row["product_category"])]
    q = (e["actual"] / e["forecast"]).quantile([0.1, 0.5, 0.9]).to_numpy()
    assert row["uncertainty_n_errors"] == len(e)
    np.testing.assert_allclose([row["lower_p10_units"], row["median_p50_units"], row["upper_p90_units"]],
                               row["predicted_units"] * q)


def test_bounds_unavailable_until_four_error_weeks_and_never_borrowed(built, preds, panel):
    c = built["contract"]
    for h in (1, 4):
        first_target = FIRST_ORIGIN + h
        g = c[c["horizon_weeks"] == h]
        unavailable = g[g["origin_week"] < first_target + FC.MIN_ERROR_WEEKS - 1]
        assert (unavailable["uncertainty_status"] == "UNAVAILABLE_INSUFFICIENT_HISTORY").all()
        assert unavailable[["lower_p10_units", "median_p50_units", "upper_p90_units"]].isna().all().all()
        assert (g[g["origin_week"] >= first_target + FC.MIN_ERROR_WEEKS - 1]["uncertainty_status"] == "AVAILABLE").all()
        assert unavailable["risk_flags"].str.contains("UNCERTAINTY_UNAVAILABLE").all()
    # H1 bounds do not depend on H4 errors (no borrowing across models or horizons).
    other = preds.copy()
    other.loc[other["horizon"] == 4, "actual"] *= 3
    again = FC.build_contract(other, panel, "TEST_RUN")["contract"]
    h1 = ["lower_p10_units", "median_p50_units", "upper_p90_units"]
    pd.testing.assert_frame_equal(again[again.horizon_weeks == 1][h1], c[c.horizon_weeks == 1][h1])


# --------------------------------------------------------------- leakage
@pytest.mark.parametrize("cutoff", [14, 20, 26])
def test_future_scrambling_does_not_change_decision_time_fields(preds, panel, built, cutoff):
    """Scramble every value observed after the cutoff week (panel sales, prices, discounts, marketing, weather and
    prediction actuals). Decision-time rows with origin <= cutoff must not change. The holiday calendar is a
    known-in-advance input and is not scrambled."""
    rng = np.random.default_rng(cutoff)
    p2 = panel.copy()
    later = p2["week_index"] > cutoff
    for col in ("Units_Sold", "Wastage_Units", "Price", "Discount_Percent", "Marketing_Spend", "Avg_Temperature",
                "Rainfall"):
        p2.loc[later, col] = rng.integers(1, 30, int(later.sum())).astype(p2[col].dtype)
    pr2 = preds.copy()
    future = pr2["target_week"] > cutoff
    pr2.loc[future, "actual"] = rng.integers(1, 50_000, int(future.sum()))
    got = FC.build_contract(pr2, p2, "TEST_RUN")["contract"]
    want = built["contract"]
    keep_g, keep_w = got["origin_week"] <= cutoff, want["origin_week"] <= cutoff
    pd.testing.assert_frame_equal(got[keep_g].reset_index(drop=True), want[keep_w].reset_index(drop=True))
    # The replay table is allowed to change (it holds the target-week outcomes).
    assert not got.equals(want)


def test_reference_price_and_last_observed_sales_are_as_of_the_origin(built, panel):
    c = built["contract"]
    row = c.iloc[5]
    s = panel[(panel.Store_ID == row.store_id) & (panel.Product_ID == row.product_id) & (panel.week_index <= row.origin_week)]
    assert row["reference_price_asof"] == pytest.approx(
        round(float((s["Price"] / (1 - s["Discount_Percent"] / 100)).median()), 4))
    assert row["last_observed_units"] == int(s.loc[s.week_index == row.origin_week, "Units_Sold"].iloc[0])


def test_replay_table_holds_target_outcomes_only(built, panel):
    r, c = built["replay"], built["contract"]
    u = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"]
    assert (r["observed_units"].to_numpy() == u.loc[list(zip(r.store_id, r.product_id, r.target_week))].to_numpy()).all()
    assert (r["availability"].str.startswith("REPLAY_ONLY")).all()
    j = r.merge(c[["horizon_weeks", "store_id", "product_id", "origin_week", "uncertainty_status"]],
                on=["horizon_weeks", "store_id", "product_id", "origin_week"])
    assert j.loc[j.uncertainty_status != "AVAILABLE", "within_p10_p90"].isna().all()
    assert j.loc[j.uncertainty_status == "AVAILABLE", "within_p10_p90"].notna().all()


# --------------------------------------------------------- reproducibility
def test_build_is_deterministic(preds, panel, built):
    again = FC.build_contract(preds, panel, "TEST_RUN")
    pd.testing.assert_frame_equal(again["contract"], built["contract"])
    pd.testing.assert_frame_equal(again["replay"], built["replay"])


def test_run_writes_only_a_new_folder(preds, panel):
    existing = {p.name for p in config.OUTPUT_ROOT.iterdir()}
    run_id = f"_pytest_{uuid.uuid4().hex}_forecast_contract"
    run_dir = FC.run_forecast_contract(run_id=run_id, predictions=preds, panel=panel)
    try:
        assert {p.name for p in config.OUTPUT_ROOT.iterdir()} - existing == {run_id}
        assert sorted(p.name for p in run_dir.iterdir()) == ["contract_manifest.json", "forecast_contract.csv",
                                                              "forecast_replay_evaluation.csv",
                                                              "interval_coverage_replay.csv",
                                                              "uncertainty_quantiles_asof.csv"]
        m = json.loads((run_dir / "contract_manifest.json").read_text(encoding="utf-8"))
        assert m["contract_sha256"] == config.sha256_file(run_dir / "forecast_contract.csv")
        assert set(m["code_dictionary"]) >= {"forecast_method", "uncertainty_method", "provenance", "risk_flags",
                                             "limitation_codes", "dataset_label"}
        saved = pd.read_csv(run_dir / "forecast_contract.csv")
        assert list(saved.columns) == FC.CONTRACT_COLUMNS
        with pytest.raises(FileExistsError):
            FC.run_forecast_contract(run_id=run_id, predictions=preds, panel=panel)
    finally:
        shutil.rmtree(run_dir)


def test_protected_contract_run_is_unchanged_and_write_blocked():
    expected = {k: v for k, v in config.load_expected_checksums().items()
                if k.startswith(f"outputs/runs/{config.FORECAST_CONTRACT_RUN_ID}/")}
    assert len(expected) == 5
    for rel, digest in expected.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(config.UnsafeWriteError):
        config.assert_safe_output(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")
    saved = pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv", nrows=5)
    assert list(saved.columns) == FC.CONTRACT_COLUMNS


# ---------------------------------------------------------------- real data
@pytest.fixture(scope="module")
def real():
    from dpe.forecast.panel import load_verified_panel

    panel, _ = load_verified_panel()
    preds = FC.load_protected_predictions()
    return preds, FC.build_contract(preds, panel, "REAL_TEST")


def test_real_contract_aligns_exactly_with_protected_predictions(real):
    preds, r = real
    c = r["contract"]
    s = FC.validate_contract(c, r["replay"])
    assert s["rows_by_horizon"] == {"H1": 17_280, "H4": 17_280}
    j = c.merge(preds.rename(columns={"Store_ID": "store_id", "Product_ID": "product_id", "horizon": "horizon_weeks",
                                      "model": "model_name"}),
                on=["model_name", "horizon_weeks", "store_id", "product_id", "origin_week", "target_week"])
    assert len(j) == len(c) and (j["predicted_units"] == j["forecast"]).all()
    assert set(c.loc[c.horizon_weeks == 1, "model_name"]) == {"random_forest"}
    assert set(c.loc[c.horizon_weeks == 4, "model_name"]) == {"mean_4w"}
    assert "catboost" not in set(c["model_name"])
    assert s["unavailable_bounds_by_horizon"] == {"H1": 2_880, "H4": 5_040}


def test_real_interval_coverage_meets_the_design_band(real):
    _, r = real
    cov = FC.coverage_summary(r["contract"], r["replay"])
    pooled = cov[cov["product_category"] == "ALL"].set_index("horizon_weeks")["coverage_p10_p90"]
    assert 0.70 <= pooled[1] <= 0.90 and 0.70 <= pooled[4] <= 0.90  # Step 5A section 10 acceptance band


def test_real_christmas_rows_are_flagged(real):
    _, r = real
    c = r["contract"]
    assert c.loc[c.target_week.isin([51, 52]), "risk_flags"].str.contains("CHRISTMAS_PERIOD").all()
    assert not c.loc[~c.target_week.isin([51, 52]), "risk_flags"].str.contains("CHRISTMAS_PERIOD").any()
