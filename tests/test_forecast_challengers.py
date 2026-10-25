"""Step 4D challengers and replacement policy: frozen configurations, pinned packages, training cut-offs,
future-data scrambling, CatBoost categorical inputs, SES training-only smoothing, integrity checks and the
policy logic. Uses the synthetic 30-week panel and tiny model sizes; the real run uses the frozen CONFIGS."""
import json
import re
import shutil
import uuid
from importlib.metadata import version
from types import MappingProxyType

import numpy as np
import pandas as pd
import pytest

from conftest import forecast_raw
from dpe import config
from dpe.forecast import acceptance as A
from dpe.forecast import backtest as B
from dpe.forecast import challenger_eval as E
from dpe.forecast import challenger_run as RUN
from dpe.forecast import challengers as C
from dpe.forecast.features import STATIC_CATEGORICAL, attach_target, build_features, feature_columns
from dpe.forecast.panel import build_panel, holiday_calendar

SMALL_FOLDS = B.make_folds(first_target=19, last_target=30, fold_weeks=4)
TINY = MappingProxyType({
    "xgboost": {**C.CONFIGS["xgboost"], "n_estimators": 20, "max_depth": 3, "n_jobs": 1},
    "catboost": {**C.CONFIGS["catboost"], "iterations": 30, "depth": 3, "thread_count": 1},
    "ses": C.CONFIGS["ses"],
})
SCRAMBLE_COLS = ("Units_Sold", "Wastage_Units", "Price", "Discount_Percent", "Marketing_Spend", "Avg_Temperature",
                 "Rainfall")


@pytest.fixture(scope="module")
def panel():
    return build_panel(forecast_raw())


@pytest.fixture(scope="module")
def rows(panel):
    cal = holiday_calendar(panel)
    return {h: attach_target(build_features(panel, cal, h, "S0"), panel) for h in (1, 4)}


def _rows(panel, h):
    return attach_target(build_features(panel, holiday_calendar(panel), h, "S0"), panel)


def _scramble(panel, after_week, upto_week=None, seed=0):
    out = panel.copy()
    mask = out["week_index"] > after_week
    if upto_week is not None:
        mask &= out["week_index"] <= upto_week
    rng = np.random.default_rng(seed)
    for c in SCRAMBLE_COLS:
        out.loc[mask, c] = rng.integers(1, 50_000, int(mask.sum())).astype(out[c].dtype)
    return out


# --------------------------------------------------- frozen configuration
def test_configurations_are_frozen_and_match_the_policy():
    x, c, s = C.CONFIGS["xgboost"], C.CONFIGS["catboost"], C.CONFIGS["ses"]
    assert (x["n_estimators"], x["learning_rate"], x["max_depth"], x["min_child_weight"], x["subsample"],
            x["colsample_bytree"], x["reg_lambda"], x["random_state"]) == (500, 0.05, 6, 10, 0.8, 0.8, 1.0, 42)
    assert (c["iterations"], c["learning_rate"], c["depth"], c["l2_leaf_reg"], c["random_seed"],
            c["allow_writing_files"]) == (1000, 0.05, 6, 3, 42, False)
    assert s["smoothing_level_bounds"] == (0.05, 0.95) and s["trend"] is None and s["seasonal"] is None
    with pytest.raises(TypeError):
        C.CONFIGS["xgboost"]["n_estimators"] = 50
    assert C.CHALLENGERS == ("xgboost", "catboost", "ses") and "lightgbm" not in C.CHALLENGERS


def test_policy_rules_are_frozen():
    R = E.RULES
    assert R["R3a_min_relative_improvement_pct"] == 2.0 and R["R3c_min_folds_better"] == 5
    assert R["R3d_max_category_worse_points"] == 1.0 and R["R4a_max_pooled_abs_bias_increase_points"] == 1.0
    assert R["R3b_ci_level"] == pytest.approx(1 - 0.05 / 6) and R["R3b_replicates"] == 5000
    assert R["R1_4_reproducibility_atol_units"] == 1e-6 and R["R1_5_negative_control_min_ratio"] == 0.9
    assert dict(E.INCUMBENT) == {1: "random_forest", 4: "mean_4w"}
    with pytest.raises(TypeError):
        E.RULES["R3a_min_relative_improvement_pct"] = 0.5
    # The CP5 gates themselves are untouched.
    assert dict(A.GATE_THRESHOLDS["G1_min_relative_improvement_pct"]) == {1: 5.0, 4: 3.0}


def test_challenger_packages_are_pinned_and_core_pins_unchanged():
    def pins(path):
        text = (config.PROJECT_ROOT / path).read_text(encoding="utf-8")
        return dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", text, flags=re.M))
    ch, core = pins("requirements-challenger.txt"), pins("requirements.txt")
    assert {"xgboost", "catboost"} <= set(ch)
    for name, v in {**ch, **core}.items():
        assert version(name) == v, (name, version(name), v)


# ------------------------------------------------------ cut-offs and leakage
@pytest.mark.parametrize("model", C.CHALLENGERS)
@pytest.mark.parametrize("h", [1, 4])
def test_rows_cutoffs_and_alignment(panel, rows, model, h):
    plan = B.fold_plan(SMALL_FOLDS[1], h)
    res = C.run_fold(model, rows[h], panel, plan, TINY)
    test = B.select_test_rows(rows[h], plan)
    keys = ["Store_ID", "Product_ID", "origin_week", "target_week"]
    assert set(map(tuple, res["pred"][keys].to_numpy())) == set(map(tuple, test[keys].to_numpy()))
    assert (res["pred"]["origin_week"] == res["pred"]["target_week"] - h).all()
    assert (res["pred"]["forecast"] >= 0).all()
    assert res["meta"]["train_target_max"] == plan.earliest_test_origin < plan.test_start


@pytest.mark.parametrize("model", C.CHALLENGERS)
@pytest.mark.parametrize("h", [1, 4])
def test_scrambling_after_the_latest_origin_does_not_change_forecasts(panel, model, h):
    plan = B.fold_plan(SMALL_FOLDS[1], h)
    base = C.run_fold(model, _rows(panel, h), panel, plan, TINY)["pred"]
    scr = _scramble(panel, plan.latest_test_origin, seed=h)
    got = C.run_fold(model, _rows(scr, h), scr, plan, TINY)["pred"]
    np.testing.assert_array_equal(got["forecast"].to_numpy(), base["forecast"].to_numpy())
    assert not np.array_equal(got["actual"].to_numpy(), base["actual"].to_numpy())


def test_catboost_categorical_inputs_are_static_identity_only(rows):
    X = C.catboost_frame(rows[1])
    assert list(X.columns) == feature_columns("S0")
    assert [c for c in X.columns if X[c].dtype == object] == list(STATIC_CATEGORICAL)
    static = rows[1].groupby(["Store_ID", "Product_ID"])[["Product_Category", "Region"]].nunique()
    assert (static == 1).all().all()  # known at every origin: one value per series
    assert not {"target_units", "fold", "plan_discount"} & set(X.columns)


@pytest.mark.parametrize("model", ["xgboost", "catboost"])
def test_test_labels_never_reach_the_model(rows, model):
    plan = B.fold_plan(SMALL_FOLDS[2], 1)
    train, test = B.select_training_rows(rows[1], plan), B.select_test_rows(rows[1], plan)
    a = C.BOOSTED[model](train, test, TINY[model])["pred"]
    b = C.BOOSTED[model](train, test.assign(target_units=test["target_units"] * 0 + 1), TINY[model])["pred"]
    np.testing.assert_array_equal(a, b)


def test_ses_alpha_uses_only_weeks_up_to_the_earliest_test_origin(panel, rows):
    plan = B.fold_plan(SMALL_FOLDS[1], 4)
    test = B.select_test_rows(rows[4], plan)
    base = C.ses_predict(panel, test, plan)
    # Scramble weeks after the earliest test origin but within the fold's origins: alpha must not move.
    scr = _scramble(panel, plan.earliest_test_origin, plan.latest_test_origin, seed=3)
    moved = C.ses_predict(scr, test, plan)
    pd.testing.assert_frame_equal(base["alphas"], moved["alphas"])
    first = (test["origin_week"] == plan.earliest_test_origin).to_numpy()
    np.testing.assert_array_equal(base["pred"][first], moved["pred"][first])


def test_ses_level_matches_statsmodels_and_is_the_forecast(panel, rows):
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    plan = B.fold_plan(SMALL_FOLDS[0], 1)
    y = panel[(panel.Store_ID == 500) & (panel.Product_ID == 1000)].sort_values("week_index")["Units_Sold"].to_numpy(float)
    alpha, l0, _ = C.ses_fit_series(y[:plan.earliest_test_origin])
    res = ExponentialSmoothing(y[:plan.earliest_test_origin], initialization_method="estimated",
                               bounds={"smoothing_level": (0.05, 0.95)}).fit()
    levels = C.ses_levels(y[:plan.earliest_test_origin], alpha, l0)
    assert levels[-1] == pytest.approx(float(res.forecast(1)[0]), rel=1e-9)
    assert 0.05 <= alpha <= 0.95
    test = B.select_test_rows(rows[1], plan)
    out = C.ses_predict(panel, test, plan)
    one = test[(test.Store_ID == 500) & (test.Product_ID == 1000)]
    full = C.ses_levels(y[:plan.latest_test_origin], alpha, l0)
    got = out["pred"][((test.Store_ID == 500) & (test.Product_ID == 1000)).to_numpy()]
    np.testing.assert_allclose(got, [full[o - 1] for o in one["origin_week"]])


# --------------------------------------------------------- integrity checks
@pytest.mark.parametrize("model", ["xgboost", "catboost"])
def test_negative_control_and_inner_sanity(rows, model):
    plan = B.fold_plan(SMALL_FOLDS[2], 1)
    nc = C.negative_control(model, rows[1], plan, TINY)
    assert {"negative_control_WAPE_pct", "constant_mean_WAPE_pct", "ratio", "passes"} <= set(nc)
    inner = C.inner_sanity(model, rows[1], plan, TINY)
    lo, hi = map(int, inner["inner_target_weeks"].split("-"))
    assert hi == plan.train_target_max < plan.test_start and hi - lo == 3
    assert inner["used_for_selection"] is False and inner["inner_train_target_max"] == lo - 1


@pytest.mark.parametrize("model", C.CHALLENGERS)
def test_refit_reproducible_within_tolerance(panel, rows, model):
    plan = B.fold_plan(SMALL_FOLDS[0], 1)
    first = C.run_fold(model, rows[1], panel, plan, TINY)["pred"]
    r = C.reproducibility(model, rows[1], panel, plan, first, TINY)
    assert r["within_tolerance"] and r["tolerance_units"] == 1e-6


# ------------------------------------------------------------ policy logic
def test_outcome_logic():
    def rules(**over):
        base = {"R1.1": "PASS", "R1.5": "NOT_APPLICABLE", "R2.G1": "PASS", "R3a": "PASS", "R3b": "PASS", "R4a": "PASS"}
        base.update(over)
        return [{"rule": k, "status": v} for k, v in base.items()]
    assert E.outcome(rules()) == "PROVISIONAL_CHALLENGER"
    assert E.outcome(rules(R3b="FAIL")) == "RETAIN_INCUMBENT (insufficient evidence)"
    assert E.outcome(rules(**{"R2.G1": "FAIL"})) == "RETAIN_INCUMBENT (insufficient evidence)"
    assert E.outcome(rules(**{"R2.G8": "INCONCLUSIVE"})) == "RETAIN_INCUMBENT (insufficient evidence)"
    assert E.outcome(rules(**{"R1.1": "FAIL"})) == "RETAIN_INCUMBENT (integrity failure)"
    pooled = pd.DataFrame({"horizon": [1, 1, 1], "model": ["xgboost", "catboost", "ses"], "WAPE_pct": [25.0, 24.0, 26.0]})
    d = E.horizon_decision({"xgboost": "PROVISIONAL_CHALLENGER", "catboost": "PROVISIONAL_CHALLENGER",
                            "ses": "RETAIN_INCUMBENT (insufficient evidence)"}, pooled, 1)
    assert d["provisional_challenger"] == "catboost" and d["other_qualifiers"] == ["xgboost"]
    assert E.horizon_decision({"ses": "RETAIN_INCUMBENT (insufficient evidence)"}, pooled, 4)["decision"].startswith(
        "RETAIN_INCUMBENT (mean_4w)")


def _policy_frame(ch_err, inc_err=10.0, base_err=12.0):
    """6 folds x 4 weeks x 15 stores x 2 categories; actual 100; errors as given (all over-forecasts)."""
    rows = []
    for f in B.make_folds():
        for t in range(f.test_start, f.test_end + 1):
            for s in range(500, 515):
                for p, cat in ((1000, "Bakery"), (1001, "Meat")):
                    for m, e in (("random_forest", inc_err), ("mean_4w", base_err), ("xgboost", ch_err)):
                        rows.append({"fold": f.fold, "horizon": 1, "Store_ID": s, "Product_ID": p, "origin_week": t - 1,
                                     "target_week": t, "model": m, "actual": 100.0, "forecast": 100.0 + e,
                                     "Product_Category": cat})
    return pd.DataFrame(rows)


def test_incumbent_rules_with_inclusive_boundaries():
    def status(df):
        pb = E.pair_bootstrap(df, "xgboost", "random_forest", 1, E.RULES["R3b_ci_level"], 200, 1)
        return {r["rule"]: r["status"] for r in E.incumbent_rules(df, "xgboost", 1, pb)}
    assert status(_policy_frame(9.75))["R3a"] == "PASS"  # 2.5% better than the incumbent (10 -> 9.75)
    s = status(_policy_frame(9.85))
    assert s["R3a"] == "FAIL" and s["R3c"] == "PASS"     # 1.5%: better in every fold, but not by enough
    s = status(_policy_frame(11.0))
    assert s["R3a"] == "FAIL" and s["R3c"] == "FAIL" and s["R4a"] == "PASS"  # bias 11% vs 10%: within +1 point
    assert status(_policy_frame(11.5))["R4a"] == "FAIL"


def test_pair_bootstrap_level_is_bonferroni_and_wider_than_95(rows):
    rng = np.random.default_rng(0)
    df = _policy_frame(9.0)
    df.loc[df.model == "xgboost", "forecast"] += rng.normal(0, 3, int((df.model == "xgboost").sum()))
    wide = E.pair_bootstrap(df, "xgboost", "random_forest", 1, E.RULES["R3b_ci_level"], 1000, 5)["primary"]
    narrow = E.pair_bootstrap(df, "xgboost", "random_forest", 1, 0.95, 1000, 5)["primary"]
    assert wide["ci_low"] <= narrow["ci_low"] and wide["ci_high"] >= narrow["ci_high"]
    assert wide["ci_level"] == pytest.approx(0.991667, rel=1e-5)


def test_cp5_screen_reuses_the_unchanged_gates():
    df = _policy_frame(9.0)
    gates = E.cp5_screen(df, "xgboost", {"status": "PASS", "summary": "ok"}, [1])[1]
    adapter = df[df.model.isin(["xgboost", "mean_4w"])].replace({"model": {"xgboost": "random_forest"}})
    boot, _ = A.bootstrap_all(adapter, [1])
    assert gates == A.evaluate_gates(adapter, boot, {"status": "PASS", "summary": "ok"}, 1)
    assert [g["gate"] for g in gates] == [f"G{i}" for i in range(9)]


def test_alignment_check_detects_mismatches():
    df = _policy_frame(9.0)
    df["origin_date"] = pd.Timestamp("2024-01-01") + pd.to_timedelta((df["origin_week"] - 1) * 7, unit="D")
    df["target_date"] = df["origin_date"] + pd.Timedelta(weeks=1)
    cp4, ch = df[df.model != "xgboost"], df[df.model == "xgboost"]
    assert E.verify_alignment(cp4, ch)["xgboost"]["identical_rows_and_actuals"]
    bad = ch.copy()
    bad.loc[bad.index[0], "actual"] += 1
    assert not E.verify_alignment(cp4, bad)["xgboost"]["identical_rows_and_actuals"]
    assert not E.verify_alignment(cp4, ch.iloc[1:])["xgboost"]["identical_rows_and_actuals"]


# ------------------------------------------------------- protected Step 4D runs
@pytest.mark.parametrize("run_id,run_dir,n_files", [
    (config.CHALLENGER_RUN_ID, config.CHALLENGER_RUN_DIR, 8),
    (config.CHALLENGER_EVAL_RUN_ID, config.CHALLENGER_EVAL_RUN_DIR, 17),
])
def test_step_4d_runs_are_recorded_unchanged_and_write_blocked(run_id, run_dir, n_files):
    expected = {k: v for k, v in config.load_expected_checksums().items() if k.startswith(f"outputs/runs/{run_id}/")}
    assert len(expected) == n_files
    for rel, digest in expected.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(config.UnsafeWriteError):
        config.assert_safe_output(run_dir / "manifest.json")


# ---------------------------------------------------------- output safety
def test_challenger_run_writes_only_a_new_folder(panel):
    existing = {p.name for p in config.OUTPUT_ROOT.iterdir()}
    run_id = f"_pytest_{uuid.uuid4().hex}_challenger_backtest"
    run_dir = RUN.run_challenger_backtest(panel=panel, run_id=run_id, folds=SMALL_FOLDS, configs=TINY)
    try:
        assert {p.name for p in config.OUTPUT_ROOT.iterdir()} - existing == {run_id}
        m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert m["label"] == "EXPLORATORY" and m["configuration_policy"].startswith("Option A")
        assert set(m["code_sha256"]) >= {"challengers.py", "features.py"}
        p = pd.read_csv(run_dir / "predictions.csv")
        assert set(p["model"]) == set(C.CHALLENGERS) and len(p) == 3 * 2 * 3 * 36
        checks = {n: pd.read_csv(run_dir / "checks" / f"{n}.csv") for n in ("reproducibility", "negative_control",
                                                                             "inner_sanity")}
        assert len(checks["reproducibility"]) == 6 and len(checks["negative_control"]) == 4
        assert not (config.PROJECT_ROOT / "catboost_info").exists()  # CatBoost writes no files
        with pytest.raises(FileExistsError):
            RUN.run_challenger_backtest(panel=panel, run_id=run_id, folds=SMALL_FOLDS, configs=TINY, run_checks=False)
    finally:
        shutil.rmtree(run_dir)
