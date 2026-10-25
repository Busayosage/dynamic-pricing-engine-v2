"""CP4: Random Forest backtest - configuration, training-only preprocessing, training cut-offs, leakage,
reproducibility and prediction alignment. Uses a small synthetic panel and a tiny forest for speed;
the real run uses the original configuration (asserted below)."""
import json
import shutil
import uuid

import numpy as np
import pandas as pd
import pytest

from conftest import forecast_raw
from dpe import config
from dpe.config import BASELINE_RUN_DIR, UnsafeWriteError, assert_safe_output
from dpe.forecast import backtest as B
from dpe.forecast import rf_backtest as R
from dpe.forecast.features import attach_target, build_features, feature_columns
from dpe.forecast.models import RF_PARAMS, TrainOnlyEncoder
from dpe.forecast.panel import build_panel, holiday_calendar

TINY_RF = {"n_estimators": 12, "max_depth": 5, "n_jobs": 1, "random_state": 42}
SMALL_FOLDS = B.make_folds(first_target=19, last_target=30, fold_weeks=4)


@pytest.fixture(scope="module")
def panel():
    return build_panel(forecast_raw())


@pytest.fixture(scope="module")
def result(panel):
    return R.compute_rf_backtest(panel, SMALL_FOLDS, rf_params=TINY_RF)


def _rows(panel, h):
    return attach_target(build_features(panel, holiday_calendar(panel), h, "S0"), panel)


# ------------------------------------------------------------ configuration
def test_rf_params_are_the_original_configuration():
    from dpe.reference_baseline import RF_PARAMS as reference

    assert RF_PARAMS == {"n_estimators": 300, "max_depth": 12, "n_jobs": -1, "random_state": 42} == reference
    assert R.compute_rf_backtest.__defaults__[1] is None  # default params come from RF_PARAMS, not a tuned set


def test_only_s0_is_enabled_in_cp4():
    with pytest.raises(ValueError, match="not enabled"):
        TrainOnlyEncoder("S1")
    assert R.SCENARIO == "S0"


# ------------------------------------------------- preprocessing (train only)
def test_encoder_categories_come_from_training_rows_only(panel):
    rows = _rows(panel, 1)
    train = rows[rows["Store_ID"] != 502]
    enc = TrainOnlyEncoder().fit(train)
    assert enc.categories["Store_ID"] == [500, 501]
    assert set(enc.categories["Product_ID"]) == set(train["Product_ID"])
    with pytest.raises(ValueError, match="Unknown"):
        enc.transform(rows[rows["Store_ID"] == 502])  # unseen in training: refused, not silently encoded
    X = enc.transform(train)
    assert list(X.columns) == enc.columns and "Store_ID=502" not in X.columns
    with pytest.raises(RuntimeError):
        TrainOnlyEncoder().transform(train)


def test_fold_encoders_are_fitted_on_their_training_rows(result):
    t = result["training"]
    assert (t["encoder_categories_from"] == "training rows of this fold").all()


# ------------------------------------------------------- training cut-offs
@pytest.mark.parametrize("h", [1, 4])
def test_training_targets_available_by_earliest_test_origin(result, h):
    t = result["training"][result["training"]["horizon"] == h]
    assert len(t) == len(SMALL_FOLDS)
    for _, r in t.iterrows():
        assert r["train_target_max"] == r["earliest_test_origin"] < r["test_target_min"]
        assert r["earliest_test_origin"] == r["test_target_min"] - h
        assert r["train_origin_max"] <= r["earliest_test_origin"] - h


# ------------------------------------------------------------------ leakage
@pytest.mark.parametrize("h", [1, 4])
def test_scrambling_after_the_latest_test_origin_does_not_change_forecasts(panel, h):
    """Weeks after the fold's last forecast origin (including all test targets) cannot affect the forecasts."""
    plan = B.fold_plan(SMALL_FOLDS[1], h)
    base = R._fold_fit(_rows(panel, h), plan, TINY_RF)["rf"]
    scrambled = panel.copy()
    later = scrambled["week_index"] > plan.latest_test_origin
    rng = np.random.default_rng(h)
    for c in ("Units_Sold", "Wastage_Units", "Price", "Discount_Percent", "Marketing_Spend", "Avg_Temperature",
              "Rainfall"):
        scrambled.loc[later, c] = rng.integers(1, 50_000, int(later.sum())).astype(scrambled[c].dtype)
    got = R._fold_fit(_rows(scrambled, h), plan, TINY_RF)["rf"]
    np.testing.assert_array_equal(got["forecast"].to_numpy(), base["forecast"].to_numpy())
    assert not np.array_equal(got["actual"].to_numpy(), base["actual"].to_numpy())  # only the labels moved


def test_model_inputs_exclude_future_values_and_raw_identifiers(result):
    for name, cols in result["feature_lists"].items():
        joined = " ".join(cols).lower()
        for banned in ("plan_", "oracle_", "wastage", "week_number", "week_of_year", "supplier_id", "price",
                       "marketing", "temperature", "rainfall", "target_units", "target_discounted"):
            assert banned not in joined, (name, banned)
        assert "Store_ID" not in cols and "Product_ID" not in cols
        assert any(c.startswith("Store_ID=") for c in cols) and any(c.startswith("Product_ID=") for c in cols)


def test_segment_columns_are_attached_after_prediction(panel, result):
    # Segments that are also S0 inputs are known in advance (identity, region, holiday calendar);
    # the discount status of the target week is analysis-only and never an input.
    known_in_advance = {"Store_ID", "Product_Category", "Region", "target_holiday"}
    assert {s for s in R.SEGMENTS if s in feature_columns("S0")} <= known_in_advance
    assert "target_discounted" not in feature_columns("S0")
    p = result["predictions"]
    disc = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Discount_Percent"] > 0
    assert (p["target_discounted"].to_numpy() == disc.loc[list(zip(p.Store_ID, p.Product_ID, p.target_week))].to_numpy()).all()


# ------------------------------------------------------- reproducibility
def test_refit_gives_identical_forecasts(panel, result):
    assert all(v["identical"] for v in result["reproducibility"].values())
    again = R.compute_rf_backtest(panel, SMALL_FOLDS, rf_params=TINY_RF, check_reproducibility=False)
    a = result["predictions"].query("model == 'random_forest'")["forecast"].to_numpy()
    b = again["predictions"].query("model == 'random_forest'")["forecast"].to_numpy()
    np.testing.assert_array_equal(a, b)


# ------------------------------------------------------ prediction alignment
def test_rf_and_baselines_are_scored_on_identical_rows(panel, result):
    p = result["predictions"]
    keys = ["fold", "horizon", "Store_ID", "Product_ID", "origin_week", "target_week"]
    for (fold, h), g in p.groupby(["fold", "horizon"]):
        sets = [set(map(tuple, m[keys].to_numpy())) for _, m in g.groupby("model")]
        assert len(sets) == 3 and sets[0] == sets[1] == sets[2] and len(sets[0]) == 9 * 4
    rf = p[p["model"] == "random_forest"]
    assert np.isfinite(rf["forecast"]).all() and (rf["forecast"] >= 0).all()
    units = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"]
    assert (rf["actual"].to_numpy() == units.loc[list(zip(rf.Store_ID, rf.Product_ID, rf.target_week))].to_numpy()).all()
    assert (rf["origin_week"] == rf["target_week"] - rf["horizon"]).all()


def test_metrics_and_diagnostics_are_complete(result):
    m = result["metrics"]
    pooled = m["pooled"]
    assert set(pooled["model"]) == {"random_forest", "last_week", "mean_4w"}
    assert (pooled["n"] == len(SMALL_FOLDS) * 36).all()
    for name in ("by_fold", "by_target_week", "by_Product_Category", "by_Store_ID", "by_Region", "by_target_holiday",
                 "by_target_discounted"):
        assert {"MAE", "RMSE", "WAPE_pct", "Bias_pct"} <= set(m[name].columns), name
    c = result["comparison"]
    assert len(c) == 2 * len(SMALL_FOLDS) and "rf_minus_mean4w_WAPE_points" in c
    imp = result["importance"].groupby(["horizon", "fold"])["importance"].sum()
    assert np.allclose(imp, 1.0)
    assert {"train_WAPE_pct", "test_WAPE_pct", "test_minus_train_WAPE_points"} <= set(result["training"].columns)


def test_christmas_tables_select_only_weeks_51_and_52(result):
    assert result["metrics"]["christmas_weeks"].empty  # synthetic panel ends at week 30
    assert R.CHRISTMAS_WEEKS == (51, 52)


# ------------------------------------------------------- outputs and safety
def test_rf_pipeline_writes_only_a_new_folder(panel):
    existing = {p.name for p in config.OUTPUT_ROOT.iterdir()}
    run_id = f"_pytest_{uuid.uuid4().hex}_rf_backtest"
    run_dir = R.run_rf_backtest(panel=panel, run_id=run_id, folds=SMALL_FOLDS, rf_params=TINY_RF,
                                check_reproducibility=False)
    try:
        assert {p.name for p in config.OUTPUT_ROOT.iterdir()} - existing == {run_id}
        for name in ("predictions.csv", "manifest.json", "training_metadata.csv", "feature_lists.json",
                     "feature_importance_summary.csv", "comparison_rf_vs_mean4w_by_fold.csv", "metrics/pooled.csv"):
            assert (run_dir / name).is_file(), name
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["hyperparameter_tuning"] == "none" and manifest["models_selected_or_promoted"] == []
        assert manifest["scenario"] == "S0"
        with pytest.raises(FileExistsError):
            R.run_rf_backtest(panel=panel, run_id=run_id, folds=SMALL_FOLDS, rf_params=TINY_RF,
                              check_reproducibility=False)
    finally:
        shutil.rmtree(run_dir)


def test_baseline_run_is_recorded_unchanged_and_write_blocked():
    expected = {k: v for k, v in config.load_expected_checksums().items()
                if k.startswith(f"outputs/runs/{config.BASELINE_RUN_ID}/")}
    assert len(expected) == 7
    for rel, digest in expected.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(BASELINE_RUN_DIR / "metrics_pooled.csv")
