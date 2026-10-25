"""CP5: frozen thresholds, gate and decision rules, dependence-aware bootstrap, independent verification,
diagnostics and output safety. Nothing is retrained."""
import json
import shutil
import uuid

import numpy as np
import pandas as pd
import pytest

from dpe import config
from dpe.config import RF_BACKTEST_RUN_DIR, UnsafeWriteError, assert_safe_output
from dpe.forecast import acceptance as A
from dpe.forecast import backtest as B


# ---------------------------------------------------------------- thresholds
def test_thresholds_are_exactly_the_design_values():
    T = A.GATE_THRESHOLDS
    assert dict(T["G1_min_relative_improvement_pct"]) == {1: 5.0, 4: 3.0}
    assert (T["G2_min_folds_improved"], T["G3_max_fold_worse_points"], T["G4_max_abs_pooled_bias_pct"],
            T["G5_max_abs_fold_bias_pct"], T["G6_max_category_worse_points"], T["G7_min_stores_improved"],
            T["G8_ci_level"]) == (5, 1.0, 5.0, 10.0, 2.0, 13, 0.95)
    with pytest.raises(TypeError):
        T["G2_min_folds_improved"] = 4  # frozen: cannot be revised at run time


# ------------------------------------------------------------- synthetic data
def _synthetic(rf_error=9.0, base_error=10.0, rf_bias_sign=1):
    """6 folds x 4 weeks x 15 stores x 2 products; actual 100; mean_4w over by base_error; RF off by rf_error."""
    rows = []
    for fi, f in enumerate(B.make_folds()):
        for t in range(f.test_start, f.test_end + 1):
            for s in range(500, 515):
                for p, cat in ((1000, "Bakery"), (1001, "Meat")):
                    for model, fc in (("last_week", 100 + 2 * base_error), ("mean_4w", 100 + base_error),
                                      ("random_forest", 100 + rf_bias_sign * rf_error)):
                        rows.append({"fold": f.fold, "horizon": 1, "Store_ID": s, "Product_ID": p,
                                     "origin_week": t - 1, "target_week": t, "model": model, "actual": 100.0,
                                     "forecast": fc, "Product_Category": cat})
    return pd.DataFrame(rows)


def _boot(primary_low, sens_low, h=1):
    return pd.DataFrame([{"horizon": h, "variant": "series x week-block (primary)", "ci95_rel_low": primary_low,
                          "ci95_rel_high": 9.0, "excludes_zero_improvement": primary_low > 0},
                         {"horizon": h, "variant": "store x week-block (sensitivity)", "ci95_rel_low": sens_low,
                          "ci95_rel_high": 9.0, "excludes_zero_improvement": sens_low > 0}])


PASS_LEAK = {"status": "PASS", "summary": "ok"}


def _status(gates):
    return {g["gate"]: g["status"] for g in gates}


# ------------------------------------------------------------- gate logic
def test_gates_pass_with_inclusive_bounds():
    # RF error 9 vs 10: 10% relative improvement; RF bias +9% (inside +/-10%, outside +/-5%)
    s = _status(A.evaluate_gates(_synthetic(9.0), _boot(1.0, 1.0), PASS_LEAK, 1))
    assert s["G1"] == s["G2"] == s["G3"] == s["G5"] == s["G6"] == s["G7"] == s["G8"] == s["G0"] == "PASS"
    assert s["G4"] == "FAIL"
    # Bias exactly 10% sits on the inclusive per-fold limit.
    assert _status(A.evaluate_gates(_synthetic(10.0, 11.0), _boot(1.0, 1.0), PASS_LEAK, 1))["G5"] == "PASS"
    assert _status(A.evaluate_gates(_synthetic(10.5, 11.0), _boot(1.0, 1.0), PASS_LEAK, 1))["G5"] == "FAIL"


def test_accuracy_gates_fail_when_rf_is_not_better():
    s = _status(A.evaluate_gates(_synthetic(10.0, 10.0, rf_bias_sign=-1), _boot(-1.0, -1.0), PASS_LEAK, 1))
    assert s["G1"] == "FAIL" and s["G2"] == "FAIL" and s["G7"] == "FAIL" and s["G8"] == "FAIL"
    assert s["G3"] == "PASS"  # equal WAPE is not "worse by more than 1 point"


def test_g8_inconclusive_when_sensitivity_disagrees_and_g0_inconclusive_when_not_run():
    s = _status(A.evaluate_gates(_synthetic(), _boot(0.5, -0.2), {}, 1))
    assert s["G8"] == "INCONCLUSIVE" and s["G0"] == "INCONCLUSIVE"


def test_decision_rule():
    def gates(**over):
        base = {f"G{i}": "PASS" for i in range(9)}
        base.update(over)
        return [{"gate": k, "status": v} for k, v in base.items()]
    assert A.decide(gates()) == "ACCEPT_RANDOM_FOREST"
    assert A.decide(gates(G1="FAIL")) == "RETAIN_FOUR_WEEK_AVERAGE"
    assert A.decide(gates(G8="FAIL")) == "RETAIN_FOUR_WEEK_AVERAGE"
    assert A.decide(gates(G5="FAIL")) == "REQUIRE_FURTHER_VALIDATION"
    assert A.decide(gates(G8="INCONCLUSIVE")) == "REQUIRE_FURTHER_VALIDATION"
    assert A.decide(gates(G0="FAIL")) == "REQUIRE_FURTHER_VALIDATION"


# ---------------------------------------------------------------- bootstrap
def _cells(ratio=0.5, n_clusters=10, n_blocks=6, seed=0):
    rng = np.random.default_rng(seed)
    base = rng.uniform(50, 150, (n_clusters, n_blocks))
    return {"abs_rf": ratio * base, "abs_base": base, "actual": 10 * base}


def test_bootstrap_constant_ratio_gives_a_degenerate_interval():
    r = A.two_way_bootstrap(_cells(0.5), 300, 1)
    assert r["point_relative_improvement_pct"] == pytest.approx(50.0)
    assert r["ci95_relative_improvement_pct"] == pytest.approx([50.0, 50.0])
    r0 = A.two_way_bootstrap(_cells(1.0), 300, 1)
    assert r0["ci95_relative_improvement_pct"] == pytest.approx([0.0, 0.0])


def test_bootstrap_is_seeded_paired_and_respects_both_dimensions():
    rng = np.random.default_rng(3)
    base = rng.uniform(50, 150, (12, 6))
    cells = {"abs_rf": base * rng.uniform(0.7, 1.1, base.shape), "abs_base": base, "actual": 10 * base}
    a, b = A.two_way_bootstrap(cells, 400, 7), A.two_way_bootstrap(cells, 400, 7)
    np.testing.assert_array_equal(a["_draws"], b["_draws"])
    both = A.two_way_bootstrap(cells, 2000, 7)
    series_only = A.two_way_bootstrap(cells, 2000, 7, resample_blocks=False)
    blocks_only = A.two_way_bootstrap(cells, 2000, 7, resample_clusters=False)
    width = lambda r: np.diff(r["ci95_relative_improvement_pct"])[0]  # noqa: E731
    assert width(both) >= max(width(series_only), width(blocks_only)) * 0.9  # two-way is not narrower
    fixed = A.two_way_bootstrap(cells, 50, 7, resample_clusters=False, resample_blocks=False)
    assert fixed["ci95_relative_improvement_pct"][0] == pytest.approx(fixed["point_relative_improvement_pct"])


def test_cell_sums_reconcile_with_row_errors():
    p = _synthetic(9.0)
    c = A.cell_sums(p, 1)
    assert c["abs_rf"].shape == (30, 6) and c["blocks"] == [f"F{i}" for i in range(1, 7)]
    rf = p[p.model == "random_forest"]
    assert c["abs_rf"].sum() == pytest.approx((rf.forecast - rf.actual).abs().sum())
    assert A.cell_sums(p, 1, ("Store_ID",))["abs_rf"].shape == (15, 6)


# ------------------------------------------------------------ verification
@pytest.fixture(scope="module")
def real():
    from dpe.forecast.panel import load_verified_panel

    data = A.load_predictions()
    panel, _ = load_verified_panel()
    return data, panel


def test_real_runs_verify_independently(real):
    data, panel = real
    v = A.verify(data["cp3"], data["cp4"], panel, data["cp4_metrics"], data["cp3_metrics"])
    assert v["cp3_cp4_baseline_rows_identical"] and v["fold_membership_and_origins_verified"]
    assert v["actuals_and_baselines_recomputed_from_panel"]
    assert set(v["rows_per_model_and_horizon"].values()) == {17_280}
    assert max(v["max_abs_metric_difference"].values()) < 1e-9


@pytest.mark.parametrize("break_it", ["baseline_forecast", "fold_label", "actual", "metric"])
def test_verification_detects_corruption(real, break_it):
    data, panel = real
    cp3, cp4 = data["cp3"].copy(), data["cp4"].copy()
    m4 = {k: v.copy() for k, v in data["cp4_metrics"].items()}
    i = cp4.index[cp4["model"] == "mean_4w"][0]
    if break_it == "baseline_forecast":
        cp4.loc[i, "forecast"] += 1
    elif break_it == "fold_label":
        cp4.loc[cp4["fold"] == "F2", "fold"] = "F3"
    elif break_it == "actual":
        rf = cp4.index[cp4["model"] == "random_forest"][0]
        cp4.loc[rf, "actual"] += 1
    else:
        m4["pooled"].loc[0, "WAPE_pct"] += 0.01
    with pytest.raises(AssertionError):
        A.verify(cp3, cp4, panel, m4, data["cp3_metrics"])


def test_real_bootstrap_is_reproducible_with_its_seed(real):
    data, _ = real
    a, _ = A.bootstrap_all(data["cp4"], (4,), replicates=100)
    b, _ = A.bootstrap_all(data["cp4"], (4,), replicates=100)
    pd.testing.assert_frame_equal(a, b)
    assert set(a["n_blocks"]) == {6} and set(a["n_clusters"]) == {720, 15}


# ------------------------------------------------------------- diagnostics
def test_month_coverage_and_reproducibility_review(real):
    data, panel = real
    cov = A.month_coverage(panel).set_index(["horizon", "fold"])
    assert cov.loc[(4, "F1"), "train_months"] == [3, 4, 5, 6] and cov.loc[(4, "F1"), "test_months_unseen_in_training"] == [7, 8]
    rep = A.reproducibility_review(data["cp4"], data["cp4_manifest"])
    assert not rep["strict_bit_exact"] and rep["within_proposed_tolerance"]
    assert "NOT claimed" in rep["status"]
    assert rep["observed_max_abs_difference_units"] < 1e-11


# --------------------------------------------------------- outputs and safety
def test_acceptance_writes_only_a_new_folder(real):
    data, panel = real
    existing = {p.name for p in config.OUTPUT_ROOT.iterdir()}
    run_id = f"_pytest_{uuid.uuid4().hex}_cp5_acceptance"
    run_dir = A.run_acceptance(run_id=run_id, data=data, panel=panel, leakage=PASS_LEAK, replicates=50)
    try:
        assert {p.name for p in config.OUTPUT_ROOT.iterdir()} - existing == {run_id}
        for name in ("acceptance_matrix.csv", "recommendations.json", "verification.json", "manifest.json",
                     "bootstrap/bootstrap_summary.csv", "diagnostics/reproducibility_review.json",
                     "diagnostics/forecast_and_actual_relative_to_origin_week.csv"):
            assert (run_dir / name).is_file(), name
        matrix = pd.read_csv(run_dir / "acceptance_matrix.csv")
        assert len(matrix) == 2 * 9 and set(matrix["status"]) <= {"PASS", "FAIL", "INCONCLUSIVE"}
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["models_retrained_or_tuned"] == [] and manifest["models_selected_deployed_or_promoted"] == []
        with pytest.raises(FileExistsError):
            A.run_acceptance(run_id=run_id, data=data, panel=panel, leakage=PASS_LEAK, replicates=50)
    finally:
        shutil.rmtree(run_dir)


def test_cp5_run_is_recorded_unchanged_and_write_blocked():
    expected = {k: v for k, v in config.load_expected_checksums().items()
                if k.startswith(f"outputs/runs/{config.CP5_ACCEPTANCE_RUN_ID}/")}
    assert len(expected) == 13
    for rel, digest in expected.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(config.CP5_ACCEPTANCE_RUN_DIR / "acceptance_matrix.csv")


def test_rf_run_is_recorded_unchanged_and_write_blocked():
    expected = {k: v for k, v in config.load_expected_checksums().items()
                if k.startswith(f"outputs/runs/{config.RF_BACKTEST_RUN_ID}/")}
    assert len(expected) == 19
    for rel, digest in expected.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(RF_BACKTEST_RUN_DIR / "predictions.csv")
