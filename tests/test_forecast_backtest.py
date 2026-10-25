"""CP3: folds, training/test boundaries, baselines, scoring populations, metrics and the original-naive
equivalence check. No model is trained."""
import json
import shutil
import uuid

import numpy as np
import pandas as pd
import pytest

from dpe import config
from dpe.config import FORECAST_PANEL_RUN_DIR, UnsafeWriteError, assert_safe_output
from dpe.forecast import backtest as B
from dpe.forecast.baselines import assert_identical_populations, baseline_predictions
from dpe.forecast.evaluate import metrics_table, score
from dpe.forecast.features import attach_target, build_features
from dpe.forecast.panel import build_panel, holiday_calendar
from dpe.forecast.pipeline import compute_baselines, run_baseline_backtest
from dpe.forecast.reference_check import reference_naive_check

from conftest import forecast_raw

SMALL_FOLDS = dict(first_target=19, last_target=30, fold_weeks=4)  # F1 19-22, F2 23-26, F3 27-30


@pytest.fixture(scope="module")
def panel():
    return build_panel(forecast_raw())


@pytest.fixture(scope="module")
def rows(panel):
    cal = holiday_calendar(panel)
    return {h: attach_target(build_features(panel, cal, h), panel) for h in (1, 4)}


@pytest.fixture(scope="module")
def small(panel):
    return compute_baselines(panel, B.make_folds(**SMALL_FOLDS))


# -------------------------------------------------------------------- folds
def test_default_folds_cover_weeks_29_to_52_without_overlap():
    folds = B.make_folds()
    assert [(f.fold, f.test_start, f.test_end) for f in folds] == [
        ("F1", 29, 32), ("F2", 33, 36), ("F3", 37, 40), ("F4", 41, 44), ("F5", 45, 48), ("F6", 49, 52)]
    covered = [w for f in folds for w in range(f.test_start, f.test_end + 1)]
    assert covered == list(range(29, 53))  # contiguous, each week exactly once
    with pytest.raises(ValueError):
        B.make_folds(29, 50, 4)


@pytest.mark.parametrize("h", [1, 4])
def test_fold_plan_training_cutoffs(h):
    for f in B.make_folds():
        p = B.fold_plan(f, h)
        assert p.earliest_test_origin == f.test_start - h
        assert p.train_target_max == f.test_start - h < f.test_start
        assert p.train_origin_max == f.test_start - 2 * h
        assert p.train_target_min == 8 + h and p.train_origin_min == 8
    f1 = B.make_folds()[0]
    assert (B.fold_plan(f1, 1).train_target_max, B.fold_plan(f1, 4).train_target_max) == (28, 25)
    with pytest.raises(ValueError, match="no training origins"):
        B.fold_plan(B.Fold("X", 12, 15), 4)


@pytest.mark.parametrize("h", [1, 4])
def test_boundaries_hold_including_the_edge_week(rows, h):
    for f in B.make_folds(**SMALL_FOLDS):
        p = B.fold_plan(f, h)
        test, train = B.select_test_rows(rows[h], p), B.select_training_rows(rows[h], p)
        B.assert_fold_boundaries(train, test, p)
        # Edge: the last training target is exactly the earliest test origin; the next week is excluded.
        assert train["target_week"].max() == p.earliest_test_origin
        assert not (train["target_week"] == p.earliest_test_origin + 1).any()
        assert set(test["target_week"]) == set(range(f.test_start, f.test_end + 1))
        assert (test["origin_week"] == test["target_week"] - h).all()


@pytest.mark.parametrize("h", [1, 4])
def test_boundary_check_detects_leaks(rows, h):
    p = B.fold_plan(B.make_folds(**SMALL_FOLDS)[1], h)
    test, train = B.select_test_rows(rows[h], p), B.select_training_rows(rows[h], p)
    late = rows[h][rows[h]["target_week"] == p.earliest_test_origin + 1].assign(fold=p.fold)
    with pytest.raises(AssertionError, match="training target"):
        B.assert_fold_boundaries(pd.concat([train, late]), test, p)
    with pytest.raises(AssertionError):
        B.assert_fold_boundaries(pd.concat([train, test]), test, p)
    with pytest.raises(AssertionError, match="origin"):
        B.assert_fold_boundaries(train, test.assign(origin_week=test["origin_week"] + 1), p)


# ---------------------------------------------------------------- baselines
@pytest.mark.parametrize("h", [1, 4])
def test_baselines_use_origin_week_values_only(panel, small, h):
    preds = small["predictions"][small["predictions"]["horizon"] == h]
    units = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"]
    for _, r in preds.sample(60, random_state=h).iterrows():
        T = r["origin_week"]
        assert T == r["target_week"] - h
        hist = [units[(r.Store_ID, r.Product_ID, w)] for w in range(T - 3, T + 1)]
        expected = hist[-1] if r["model"] == "last_week" else np.mean(hist)
        assert r["forecast"] == pytest.approx(expected)
        assert r["actual"] == units[(r.Store_ID, r.Product_ID, r.target_week)]


@pytest.mark.parametrize("h", [1, 4])
def test_baselines_ignore_intervening_and_target_weeks(panel, small, h):
    """Scrambling weeks T+1..T+h (H4: the three intervening weeks and the target) leaves forecasts unchanged."""
    T = 22
    rng = np.random.default_rng(5)
    scrambled = panel.copy()
    later = scrambled["week_index"].between(T + 1, T + h)
    scrambled.loc[later, "Units_Sold"] = rng.integers(1, 50_000, int(later.sum()))
    f = build_features(scrambled, holiday_calendar(scrambled), h, origins=[T])
    got = baseline_predictions(attach_target(f, panel).assign(fold="F"))
    base = small["predictions"]
    want = base[(base["horizon"] == h) & (base["origin_week"] == T)]
    cols = ["model", "Store_ID", "Product_ID", "forecast"]
    pd.testing.assert_frame_equal(got[cols].sort_values(cols[:3]).reset_index(drop=True),
                                  want[cols].sort_values(cols[:3]).reset_index(drop=True))


def test_identical_scoring_populations_and_same_targets(small):
    p = small["predictions"]
    for (fold, h), g in p.groupby(["fold", "horizon"]):
        keys = [set(map(tuple, m[["Store_ID", "Product_ID", "target_week"]].to_numpy())) for _, m in g.groupby("model")]
        assert len(keys) == 2 and keys[0] == keys[1] and len(keys[0]) == 9 * 4
    assert small["same_targets_across_horizons"]
    with pytest.raises(AssertionError, match="different population"):
        assert_identical_populations(p[p["horizon"] == 1].drop(index=p.index[0]))
    with pytest.raises(AssertionError, match="Duplicate"):
        assert_identical_populations(pd.concat([p[p["horizon"] == 1], p[p["horizon"] == 1].iloc[[0]]]))


def test_prediction_keys_preserved(small):
    p = small["predictions"]
    for c in ("fold", "Store_ID", "Product_ID", "origin_week", "origin_date", "target_week", "target_date", "horizon"):
        assert p[c].notna().all(), c
    assert ((p["target_date"] - p["origin_date"]) == pd.to_timedelta(p["horizon"] * 7, unit="D")).all()


# ------------------------------------------------------------------ metrics
def test_metric_formulas():
    s = score([10, 20, 30], [12, 18, 33])
    assert s["MAE"] == pytest.approx(7 / 3) and s["RMSE"] == pytest.approx(np.sqrt(17 / 3))
    assert s["WAPE_pct"] == pytest.approx(100 * 7 / 60) and s["Bias_pct"] == pytest.approx(100 * 3 / 60)
    with pytest.raises(ValueError):
        score([], [])


def test_pooled_metrics_use_all_rows_not_fold_averages(small):
    p = small["predictions"]
    pooled = small["metrics"]["pooled"].set_index(["horizon", "model"])
    for (h, m), g in p.groupby(["horizon", "model"]):
        assert pooled.loc[(h, m), "WAPE_pct"] == pytest.approx(100 * (g.forecast - g.actual).abs().sum() / g.actual.sum())
        assert pooled.loc[(h, m), "n"] == len(g)
    by_fold = metrics_table(p, ["horizon", "model", "fold"])
    assert by_fold["n"].sum() == len(p)


# ------------------------------------------------------- reference check
def _fake_reference(tmp_path, preds):
    rep = (preds.rename(columns={"target_date": "WeekDate", "actual": "Units_Sold", "forecast": "pred_naive"})
           [["Store_ID", "Product_ID", "WeekDate", "Units_Sold", "pred_naive"]].assign(pred_rf=0.0))
    rep.to_csv(tmp_path / "rep.csv", index=False)
    rep.drop(columns=["Store_ID", "Product_ID"]).to_csv(tmp_path / "orig.csv", index=False)
    return tmp_path / "rep.csv", tmp_path / "orig.csv"


def _window_predictions():
    """H1 last_week rows for targets 45-52 (2 series), as produced by the pipeline."""
    rows = []
    for s, p in ((500, 1000), (501, 1000)):
        for t in range(45, 53):
            d = pd.Timestamp("2024-01-01") + pd.Timedelta(weeks=t - 1)
            rows.append({"fold": "F", "Store_ID": s, "Product_ID": p, "origin_week": t - 1,
                         "origin_date": d - pd.Timedelta(weeks=1), "target_week": t, "target_date": d,
                         "horizon": 1, "model": "last_week", "actual": float(t * 10 + s), "forecast": float(t + s)})
    return pd.DataFrame(rows)


def test_reference_check_confirms_equivalence_and_reports_differences(tmp_path):
    preds = _window_predictions()
    rep, orig = _fake_reference(tmp_path, preds)
    ok = reference_naive_check(preds, rep, orig)
    assert ok["equivalent"] and ok["keyed_vs_v2_reproduction"]["forecast_rows_equal"] == 16
    assert not ok["positional_vs_oct_2025_original"]["has_store_product_ids"]
    changed = preds.copy()
    changed.loc[3, "forecast"] += 1
    bad = reference_naive_check(changed, rep, orig)
    assert not bad["equivalent"] and bad["keyed_vs_v2_reproduction"]["forecast_rows_different"] == 1
    missing = reference_naive_check(preds.iloc[1:], rep, orig)
    assert missing["keyed_vs_v2_reproduction"]["rows_only_reference"] == 1 and not missing["equivalent"]
    assert "H4" in ok["not_compared"]


# ------------------------------------------------------------ real data
@pytest.fixture(scope="module")
def real():
    from dpe.forecast.panel import load_verified_panel

    panel, _ = load_verified_panel()
    return compute_baselines(panel, B.make_folds())


def test_real_backtest_populations(real):
    plans = real["plans"]
    assert (plans["test_rows"] == 2880).all() and (plans["test_series"] == 720).all() and len(plans) == 12
    p = real["predictions"]
    assert len(p) == 2 * 2 * 6 * 2880
    assert real["same_targets_across_horizons"]


def test_real_h1_naive_equals_original_benchmark_row_by_row(real):
    ref = reference_naive_check(real["predictions"])
    assert ref["equivalent"], ref
    k = ref["keyed_vs_v2_reproduction"]
    assert k["rows_matched_on_store_product_target_date"] == 5760 and k["max_abs_forecast_difference"] == 0.0
    original = json.loads((config.VERIFIED_RUN_DIR / "metrics.json").read_text())["naive"]
    win = real["metrics"]["reference_window"].set_index(["horizon", "model"]).loc[(1, "last_week")]
    assert win["MAE"] == pytest.approx(original["MAE"]) and win["WAPE_pct"] == pytest.approx(100 * original["WAPE"])


# ------------------------------------------------------- outputs and safety
def test_pipeline_writes_only_a_new_folder(panel):
    existing = {p.name for p in config.OUTPUT_ROOT.iterdir()}
    run_id = f"_pytest_{uuid.uuid4().hex}_baseline_backtest"
    run_dir = run_baseline_backtest(panel=panel, run_id=run_id, folds=B.make_folds(**SMALL_FOLDS),
                                    check_reference=False)
    try:
        assert {p.name for p in config.OUTPUT_ROOT.iterdir()} - existing == {run_id}
        names = sorted(p.name for p in run_dir.iterdir())
        assert names == ["baseline_predictions.csv", "folds.csv", "manifest.json", "metrics_by_fold.csv",
                         "metrics_pooled.csv", "metrics_reference_window.csv", "reference_naive_check.json"]
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["models_trained"] == [] and "provisional" in manifest["provisional_thresholds"]
        with pytest.raises(FileExistsError):
            run_baseline_backtest(panel=panel, run_id=run_id, folds=B.make_folds(**SMALL_FOLDS), check_reference=False)
    finally:
        shutil.rmtree(run_dir)


def test_forecast_panel_run_is_recorded_unchanged_and_write_blocked():
    expected = {k: v for k, v in config.load_expected_checksums().items()
                if k.startswith(f"outputs/runs/{config.FORECAST_PANEL_RUN_ID}/")}
    assert len(expected) == 3
    for rel, digest in expected.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(FORECAST_PANEL_RUN_DIR / "forecast_panel.csv")
