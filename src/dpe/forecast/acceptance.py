"""CP5: acceptance review of the CP4 Random Forest against the four-week moving average.

Reads the protected CP3 baseline and CP4 Random Forest predictions; never retrains, tunes or edits them.

1. Independent verification: checksums, row alignment, fold membership, origins, actual sales,
   baseline values recomputed from the panel, and every reported metric recomputed.
2. Dependence-aware bootstrap of the relative WAPE improvement (two-way: store-product series x
   four-week target-week blocks), plus sensitivity variants.
3. The provisional gates of STEP_4A section 10, evaluated with the thresholds exactly as written there
   (GATE_THRESHOLDS is frozen and tested). Status rules, including INCONCLUSIVE, are fixed below.
4. Diagnostics from existing predictions: H4 Meat instability, Christmas weeks, reproducibility.
5. A recommendation per horizon from a fixed decision rule.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pandas as pd

from dpe import config
from dpe.forecast import backtest as B
from dpe.forecast.evaluate import metrics_table

RF, BASELINE = "random_forest", "mean_4w"
KEYS = ["fold", "horizon", "Store_ID", "Product_ID", "origin_week", "target_week"]

# Thresholds exactly as in STEP_4A section 10 (provisional per section 14). Not revised after results.
GATE_THRESHOLDS = MappingProxyType({
    "G1_min_relative_improvement_pct": MappingProxyType({1: 5.0, 4: 3.0}),
    "G2_min_folds_improved": 5,
    "G3_max_fold_worse_points": 1.0,
    "G4_max_abs_pooled_bias_pct": 5.0,
    "G5_max_abs_fold_bias_pct": 10.0,
    "G6_max_category_worse_points": 2.0,
    "G7_min_stores_improved": 13,
    "G8_ci_level": 0.95,
})
STATUS_RULES = {
    "improved": "strictly lower WAPE than mean_4w (ties count as not improved)",
    "bounds": "'at least' and 'within' thresholds are inclusive",
    "G0": "PASS if every leakage/integrity test file passes; FAIL if any fails; INCONCLUSIVE if not run",
    "G8": ("PASS if the primary (series x week-block) 95% interval of relative improvement lies above 0 and the "
           "store x week-block sensitivity interval also lies above 0; FAIL if the primary interval does not lie "
           "above 0; INCONCLUSIVE if the primary lies above 0 but the sensitivity does not"),
}
DECISION_RULE = (
    "ACCEPT_RANDOM_FOREST if every gate is PASS; RETAIN_FOUR_WEEK_AVERAGE if G1 (accuracy) or G8 "
    "(significance) is FAIL; otherwise REQUIRE_FURTHER_VALIDATION (G0 failure, any INCONCLUSIVE gate, or "
    "consistency/bias/segment gates failing despite accuracy and significance)."
)
BOOTSTRAP = MappingProxyType({"replicates": 2000, "seed": 20261021, "ci": "percentile",
                              "primary": "series x week-block", "blocks": "the six 4-week fold blocks"})
REPRO_TOLERANCE = MappingProxyType({"atol_units": 1e-6, "rtol": 1e-9})
LEAKAGE_TEST_FILES = ("tests/test_forecast_features.py", "tests/test_forecast_panel.py",
                      "tests/test_forecast_backtest.py", "tests/test_forecast_models.py")


# ------------------------------------------------------------------ loading
def _verify_run_checksums(run_id: str) -> list[str]:
    expected = {k: v for k, v in config.load_expected_checksums().items() if k.startswith(f"outputs/runs/{run_id}/")}
    if not expected:
        raise ValueError(f"No recorded checksums for {run_id}")
    for rel, digest in expected.items():
        if config.sha256_file(config.PROJECT_ROOT / rel) != digest:
            raise ValueError(f"Checksum mismatch: {rel}")
    return sorted(expected)


def load_predictions() -> dict:
    """CP3 baseline and CP4 predictions from the protected runs (checksums verified first)."""
    evidence = {"cp3_files": _verify_run_checksums(config.BASELINE_RUN_ID),
                "cp4_files": _verify_run_checksums(config.RF_BACKTEST_RUN_ID)}
    dates = ["origin_date", "target_date"]
    cp3 = pd.read_csv(config.BASELINE_RUN_DIR / "baseline_predictions.csv", parse_dates=dates)
    cp4 = pd.read_csv(config.RF_BACKTEST_RUN_DIR / "predictions.csv", parse_dates=dates)
    cp4_metrics = {n: pd.read_csv(config.RF_BACKTEST_RUN_DIR / "metrics" / f"{n}.csv") for n in ("pooled", "by_fold")}
    cp3_metrics = {n: pd.read_csv(config.BASELINE_RUN_DIR / f"metrics_{n}.csv") for n in ("pooled", "by_fold")}
    manifest = json.loads((config.RF_BACKTEST_RUN_DIR / "manifest.json").read_text(encoding="utf-8"))
    return {"cp3": cp3, "cp4": cp4, "cp4_metrics": cp4_metrics, "cp3_metrics": cp3_metrics, "cp4_manifest": manifest,
            "evidence": evidence}


# ------------------------------------------------------------- verification
def _metrics_match(recomputed: pd.DataFrame, reported: pd.DataFrame, by: list[str]) -> float:
    m = recomputed.merge(reported, on=by, suffixes=("", "_rep"), validate="one_to_one")
    if len(m) != len(reported) or len(m) != len(recomputed):
        raise AssertionError(f"Metric tables do not align on {by}")
    cols = ["n", "actual_total", "MAE", "RMSE", "WAPE_pct", "Bias_pct"]
    return float(max(np.abs(m[c] - m[f"{c}_rep"]).max() for c in cols))


def verify(cp3: pd.DataFrame, cp4: pd.DataFrame, panel: pd.DataFrame, cp4_metrics: dict, cp3_metrics: dict,
           folds: list[B.Fold] | None = None, tol: float = 1e-9) -> dict:
    """Independent checks; raises AssertionError on any failure and returns the evidence."""
    folds = folds or B.make_folds()
    out = {}
    # Same baseline rows in CP3 and CP4 (CP4 recomputed them; they must be identical).
    b4 = cp4[cp4["model"] != RF]
    j = cp3.merge(b4, on=KEYS + ["model"], how="outer", suffixes=("_cp3", "_cp4"), indicator=True)
    if not (j["_merge"] == "both").all():
        raise AssertionError("CP3 and CP4 baseline rows differ")
    out["cp3_cp4_baseline_rows_identical"] = bool((j["forecast_cp3"] == j["forecast_cp4"]).all()
                                                   and (j["actual_cp3"] == j["actual_cp4"]).all())
    if not out["cp3_cp4_baseline_rows_identical"]:
        raise AssertionError("CP3 and CP4 baseline forecasts or actuals differ")
    # Identical populations: every model scores the same rows in every fold and horizon.
    for (f, h), g in cp4.groupby(["fold", "horizon"]):
        sets = [frozenset(map(tuple, m[KEYS].to_numpy())) for _, m in g.groupby("model")]
        if len(sets) != 3 or len(set(sets)) != 1:
            raise AssertionError(f"{f} H{h}: models scored on different rows")
    if cp4.duplicated(subset=KEYS + ["model"]).any():
        raise AssertionError("Duplicate prediction rows")
    out["rows_per_model_and_horizon"] = {f"H{h}_{m}": int(n) for (h, m), n in cp4.groupby(["horizon", "model"]).size().items()}
    # Fold membership and origins.
    fold_of = {w: f.fold for f in folds for w in range(f.test_start, f.test_end + 1)}
    if not (cp4["target_week"].map(fold_of) == cp4["fold"]).all():
        raise AssertionError("Rows assigned to the wrong fold")
    if not ((cp4["origin_week"] == cp4["target_week"] - cp4["horizon"]).all()
            and ((cp4["target_date"] - cp4["origin_date"]) == pd.to_timedelta(cp4["horizon"] * 7, unit="D")).all()):
        raise AssertionError("Origin does not equal target - horizon")
    out["fold_membership_and_origins_verified"] = True
    # Actual sales and baseline values recomputed from the panel.
    units = panel.pivot_table(index=["Store_ID", "Product_ID"], columns="week_index", values="Units_Sold")
    idx = pd.MultiIndex.from_arrays([cp4["Store_ID"], cp4["Product_ID"]])
    u = units.reindex(idx).to_numpy()
    col = {w: i for i, w in enumerate(units.columns)}
    t = cp4["target_week"].map(col).to_numpy()
    o = cp4["origin_week"].map(col).to_numpy()
    r = np.arange(len(cp4))
    if not (u[r, t] == cp4["actual"].to_numpy()).all():
        raise AssertionError("Actual sales do not match the panel")
    lw = cp4["model"] == "last_week"
    if not np.array_equal(u[r, o][lw], cp4.loc[lw, "forecast"].to_numpy()):
        raise AssertionError("last_week forecasts do not equal units at the origin")
    m4 = (cp4["model"] == BASELINE).to_numpy()
    mean4 = np.mean([u[r, o - k] for k in range(4)], axis=0)
    if not np.allclose(mean4[m4], cp4.loc[m4, "forecast"].to_numpy(), rtol=0, atol=1e-9):
        raise AssertionError("mean_4w forecasts do not equal the mean of weeks T-3..T")
    rf = cp4[cp4["model"] == RF]
    if not (np.isfinite(rf["forecast"]).all() and (rf["forecast"] >= 0).all()):
        raise AssertionError("Random Forest forecasts must be finite and non-negative")
    out["actuals_and_baselines_recomputed_from_panel"] = True
    # Every reported metric recomputed from the rows.
    diffs = {
        "cp4_pooled": _metrics_match(metrics_table(cp4, ["horizon", "model"]), cp4_metrics["pooled"], ["horizon", "model"]),
        "cp4_by_fold": _metrics_match(metrics_table(cp4, ["horizon", "model", "fold"]), cp4_metrics["by_fold"],
                                      ["horizon", "model", "fold"]),
        "cp3_pooled": _metrics_match(metrics_table(cp3, ["horizon", "model"]), cp3_metrics["pooled"], ["horizon", "model"]),
        "cp3_by_fold": _metrics_match(metrics_table(cp3, ["horizon", "model", "fold"]), cp3_metrics["by_fold"],
                                      ["horizon", "model", "fold"]),
    }
    if max(diffs.values()) > tol:
        raise AssertionError(f"Reported metrics differ from recomputed values: {diffs}")
    out["max_abs_metric_difference"] = diffs
    return out


# ---------------------------------------------------------------- bootstrap
def cell_sums(cp4: pd.DataFrame, horizon: int, cluster=("Store_ID", "Product_ID")) -> dict:
    """Per (cluster, week block) sums of |error| for RF and mean_4w, and of actual units."""
    sub = cp4[cp4["horizon"] == horizon]
    a = sub[sub["model"] == RF].set_index(KEYS)
    b = sub[sub["model"] == BASELINE].set_index(KEYS).reindex(a.index)
    d = pd.DataFrame({"abs_rf": (a["forecast"] - a["actual"]).abs(), "abs_base": (b["forecast"] - b["actual"]).abs(),
                      "actual": a["actual"]}).reset_index()
    d["cluster"] = d[list(cluster)].astype(str).agg("_".join, axis=1)
    sums = d.groupby(["cluster", "fold"])[["abs_rf", "abs_base", "actual"]].sum()
    clusters, blocks = sorted(d["cluster"].unique()), sorted(d["fold"].unique())
    full = pd.MultiIndex.from_product([clusters, blocks], names=["cluster", "fold"])
    sums = sums.reindex(full, fill_value=0.0)
    shape = (len(clusters), len(blocks))
    return {k: sums[k].to_numpy().reshape(shape) for k in ("abs_rf", "abs_base", "actual")} | {
        "clusters": clusters, "blocks": blocks}


def two_way_bootstrap(cells: dict, replicates: int, seed: int, resample_clusters=True, resample_blocks=True) -> dict:
    """Each replicate draws clusters and week blocks with replacement, independently; a cell's weight is
    (times its cluster was drawn) x (times its block was drawn). Paired: both models use the same weights."""
    A, Bm, Y = cells["abs_rf"], cells["abs_base"], cells["actual"]
    nc, nb = A.shape
    rng = np.random.default_rng(seed)
    rel, pts = np.empty(replicates), np.empty(replicates)
    for i in range(replicates):
        wc = rng.multinomial(nc, np.full(nc, 1 / nc)) if resample_clusters else np.ones(nc)
        wb = rng.multinomial(nb, np.full(nb, 1 / nb)) if resample_blocks else np.ones(nb)
        a, b, y = wc @ A @ wb, wc @ Bm @ wb, wc @ Y @ wb
        rel[i] = 100 * (1 - a / b)
        pts[i] = 100 * (a - b) / y
    point_rel = 100 * (1 - A.sum() / Bm.sum())
    point_pts = 100 * (A.sum() - Bm.sum()) / Y.sum()
    return {"point_relative_improvement_pct": float(point_rel), "point_wape_difference_points": float(point_pts),
            "ci95_relative_improvement_pct": [float(np.percentile(rel, 2.5)), float(np.percentile(rel, 97.5))],
            "ci95_wape_difference_points": [float(np.percentile(pts, 2.5)), float(np.percentile(pts, 97.5))],
            "share_replicates_rf_better": float(np.mean(rel > 0)), "n_clusters": int(nc), "n_blocks": int(nb),
            "replicates": int(replicates), "seed": int(seed), "_draws": rel}


def bootstrap_all(cp4: pd.DataFrame, horizons=(1, 4), replicates=None, seed=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    replicates = replicates or BOOTSTRAP["replicates"]
    seed = seed if seed is not None else BOOTSTRAP["seed"]
    variants = [("series x week-block (primary)", ("Store_ID", "Product_ID"), True, True),
                ("store x week-block (sensitivity)", ("Store_ID",), True, True),
                ("series only", ("Store_ID", "Product_ID"), True, False),
                ("week-block only", ("Store_ID", "Product_ID"), False, True)]
    rows, draws = [], {}
    for h in horizons:
        for name, cluster, rc, rb in variants:
            res = two_way_bootstrap(cell_sums(cp4, h, cluster), replicates, seed, rc, rb)
            draws[f"H{h} | {name}"] = res.pop("_draws")
            lo, hi = res["ci95_relative_improvement_pct"]
            rows.append({"horizon": h, "variant": name, **{k: v for k, v in res.items() if not isinstance(v, list)},
                         "ci95_rel_low": lo, "ci95_rel_high": hi,
                         "ci95_points_low": res["ci95_wape_difference_points"][0],
                         "ci95_points_high": res["ci95_wape_difference_points"][1],
                         "excludes_zero_improvement": bool(lo > 0)})
    return pd.DataFrame(rows), pd.DataFrame(draws)


# -------------------------------------------------------------------- gates
def _status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def evaluate_gates(cp4: pd.DataFrame, boot: pd.DataFrame, leakage: dict, horizon: int) -> list[dict]:
    T = GATE_THRESHOLDS
    sub = cp4[cp4["horizon"] == horizon]
    pooled = metrics_table(sub, ["model"]).set_index("model")
    fold = metrics_table(sub, ["model", "fold"]).pivot(index="fold", columns="model")
    cat = metrics_table(sub, ["model", "Product_Category"]).pivot(index="Product_Category", columns="model", values="WAPE_pct")
    store = metrics_table(sub, ["model", "Store_ID"]).pivot(index="Store_ID", columns="model", values="WAPE_pct")
    rel = 100 * (1 - pooled.loc[RF, "WAPE_pct"] / pooled.loc[BASELINE, "WAPE_pct"])
    fold_diff = fold["WAPE_pct"][RF] - fold["WAPE_pct"][BASELINE]
    fold_bias = fold["Bias_pct"][RF]
    cat_diff = cat[RF] - cat[BASELINE]
    store_better = int((store[RF] < store[BASELINE]).sum())
    b = boot[boot["horizon"] == horizon].set_index("variant")
    prim, sens = b.loc["series x week-block (primary)"], b.loc["store x week-block (sensitivity)"]
    g8 = ("FAIL" if not prim["excludes_zero_improvement"]
          else "PASS" if sens["excludes_zero_improvement"] else "INCONCLUSIVE")
    leak = leakage.get("status", "INCONCLUSIVE")
    worst_fold = fold_diff.idxmax()
    worst_bias = fold_bias.abs().idxmax()
    worst_cat = cat_diff.idxmax()
    return [
        {"gate": "G0", "criterion": "Leakage and integrity tests pass", "threshold": "all pass",
         "observed": leakage.get("summary", "not run"), "status": leak},
        {"gate": "G1", "criterion": "Relative WAPE improvement vs mean_4w",
         "threshold": f">= {T['G1_min_relative_improvement_pct'][horizon]:.1f}%", "observed": f"{rel:.2f}%",
         "status": _status(rel >= T["G1_min_relative_improvement_pct"][horizon])},
        {"gate": "G2", "criterion": "Folds where RF WAPE is lower", "threshold": f">= {T['G2_min_folds_improved']} of 6",
         "observed": f"{int((fold_diff < 0).sum())} of {len(fold_diff)}",
         "status": _status(int((fold_diff < 0).sum()) >= T["G2_min_folds_improved"])},
        {"gate": "G3", "criterion": "Worst fold: RF WAPE minus mean_4w", "threshold": f"<= +{T['G3_max_fold_worse_points']:.1f} points",
         "observed": f"{fold_diff.max():+.2f} points ({worst_fold})",
         "status": _status(fold_diff.max() <= T["G3_max_fold_worse_points"])},
        {"gate": "G4", "criterion": "Pooled RF bias", "threshold": f"within +/-{T['G4_max_abs_pooled_bias_pct']:.0f}%",
         "observed": f"{pooled.loc[RF, 'Bias_pct']:+.2f}%",
         "status": _status(abs(pooled.loc[RF, "Bias_pct"]) <= T["G4_max_abs_pooled_bias_pct"])},
        {"gate": "G5", "criterion": "Largest per-fold RF bias", "threshold": f"within +/-{T['G5_max_abs_fold_bias_pct']:.0f}%",
         "observed": f"{fold_bias[worst_bias]:+.2f}% ({worst_bias})",
         "status": _status(fold_bias.abs().max() <= T["G5_max_abs_fold_bias_pct"])},
        {"gate": "G6", "criterion": "Worst category: RF WAPE minus mean_4w",
         "threshold": f"<= +{T['G6_max_category_worse_points']:.1f} points",
         "observed": f"{cat_diff.max():+.2f} points ({worst_cat})",
         "status": _status(cat_diff.max() <= T["G6_max_category_worse_points"])},
        {"gate": "G7", "criterion": "Stores where RF WAPE is lower", "threshold": f">= {T['G7_min_stores_improved']} of 15",
         "observed": f"{store_better} of {len(store)}", "status": _status(store_better >= T["G7_min_stores_improved"])},
        {"gate": "G8", "criterion": "95% bootstrap interval of relative improvement excludes zero",
         "threshold": "lower bound > 0 (primary and store sensitivity)",
         "observed": (f"primary [{prim['ci95_rel_low']:.2f}%, {prim['ci95_rel_high']:.2f}%]; "
                      f"store [{sens['ci95_rel_low']:.2f}%, {sens['ci95_rel_high']:.2f}%]"), "status": g8},
    ]


def decide(gates: list[dict]) -> str:
    s = {g["gate"]: g["status"] for g in gates}
    if all(v == "PASS" for v in s.values()):
        return "ACCEPT_RANDOM_FOREST"
    if s.get("G1") == "FAIL" or s.get("G8") == "FAIL":
        return "RETAIN_FOUR_WEEK_AVERAGE"
    return "REQUIRE_FURTHER_VALIDATION"


# -------------------------------------------------------------- diagnostics
def month_coverage(panel: pd.DataFrame, folds=None, horizons=(1, 4)) -> pd.DataFrame:
    """Target months present in each fold's training targets vs its test targets."""
    folds = folds or B.make_folds()
    month = panel.drop_duplicates("week_index").set_index("week_index")["WeekDate"].dt.month
    rows = []
    for h in horizons:
        for f in folds:
            p = B.fold_plan(f, h)
            train_m = sorted(set(month.loc[p.train_target_min:p.train_target_max]))
            test_m = sorted(set(month.loc[f.test_start:f.test_end]))
            rows.append({"horizon": h, "fold": f.fold, "train_target_weeks": f"{p.train_target_min}-{p.train_target_max}",
                         "train_months": train_m, "test_months": test_m,
                         "test_months_unseen_in_training": sorted(set(test_m) - set(train_m))})
    return pd.DataFrame(rows)


def _units_at(panel: pd.DataFrame, store, product, week) -> np.ndarray:
    u = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"]
    return u.reindex(pd.MultiIndex.from_arrays([store, product, week])).to_numpy(dtype=float)


def ratio_to_origin(cp4: pd.DataFrame, panel: pd.DataFrame, folds=None) -> pd.DataFrame:
    """Per horizon, fold and category: actual and forecasts relative to sales in the origin week (test rows),
    and the target/origin ratio the model saw in its training pairs whose target lay in the last training month.
    Uses existing predictions and the panel only."""
    folds = folds or B.make_folds()
    month = panel.drop_duplicates("week_index").set_index("week_index")["WeekDate"].dt.month
    p = cp4[cp4["model"].isin([RF, BASELINE])].copy()
    p["origin_units"] = _units_at(panel, p["Store_ID"], p["Product_ID"], p["origin_week"])
    test = (p.groupby(["horizon", "fold", "Product_Category", "model"])
            .apply(lambda g: pd.Series({"actual_over_origin": g["actual"].sum() / g["origin_units"].sum(),
                                        "forecast_over_origin": g["forecast"].sum() / g["origin_units"].sum()}),
                   include_groups=False).reset_index())
    test = test.pivot_table(index=["horizon", "fold", "Product_Category"], columns="model",
                            values=["actual_over_origin", "forecast_over_origin"])
    test.columns = [f"{a}_{b}" if a == "forecast_over_origin" else a for a, b in test.columns]
    test = test.loc[:, ~test.columns.duplicated()].reset_index()
    cats = panel.drop_duplicates(["Store_ID", "Product_ID"])[["Store_ID", "Product_ID", "Product_Category"]]
    rows = []
    for h in sorted(p["horizon"].unique()):
        for f in folds:
            plan = B.fold_plan(f, h)
            last_month = month[plan.train_target_max]
            targets = [w for w in range(plan.train_target_min, plan.train_target_max + 1) if month[w] == last_month]
            pairs = cats.merge(pd.DataFrame({"target_week": targets}), how="cross")
            pairs["origin_week"] = pairs["target_week"] - h
            pairs["t"] = _units_at(panel, pairs.Store_ID, pairs.Product_ID, pairs.target_week)
            pairs["o"] = _units_at(panel, pairs.Store_ID, pairs.Product_ID, pairs.origin_week)
            for c, g in pairs.groupby("Product_Category"):
                rows.append({"horizon": h, "fold": f.fold, "Product_Category": c, "last_training_month": int(last_month),
                             "train_last_month_target_over_origin": g["t"].sum() / g["o"].sum()})
    return test.merge(pd.DataFrame(rows), on=["horizon", "fold", "Product_Category"])


def meat_and_month_diagnostics(cp4: pd.DataFrame, panel: pd.DataFrame) -> dict:
    cov = month_coverage(panel)
    ratios = ratio_to_origin(cp4, panel)
    p = cp4[cp4["model"].isin([RF, BASELINE])]
    meat = p[p["Product_Category"] == "Meat"]
    meat_week = metrics_table(meat, ["horizon", "model", "target_week"])
    tot = meat.groupby(["horizon", "model", "target_week"]).agg(actual=("actual", "sum"), forecast=("forecast", "sum"))
    meat_week = meat_week.merge(tot.reset_index(), on=["horizon", "model", "target_week"])
    level = (panel[panel["Product_Category"] == "Meat"].groupby("week_index")["Units_Sold"].sum())
    meat_level = pd.DataFrame({"week_index": level.index, "meat_units": level.values,
                               "index_vs_annual_mean": 100 * level.values / level.mean()})
    return {"month_coverage": cov, "ratio_to_origin": ratios, "meat_by_target_week": meat_week,
            "meat_weekly_level": meat_level}


def christmas_diagnostics(cp4: pd.DataFrame, panel: pd.DataFrame) -> dict:
    late = cp4[cp4["target_week"].between(45, 52)]
    by_cat_week = metrics_table(late, ["horizon", "model", "Product_Category", "target_week"])
    pre = panel[panel["week_index"].between(45, 50)].groupby("Product_Category")["Units_Sold"].sum() / 6
    w = panel[panel["week_index"].isin([51, 52])].groupby(["Product_Category", "week_index"])["Units_Sold"].sum()
    uplift = (w / pre.reindex(w.index.get_level_values(0)).to_numpy() * 100 - 100).rename("uplift_vs_weeks_45_50_pct")
    hol = panel.drop_duplicates("week_index").set_index("week_index")
    nat = panel.groupby("week_index")["Holiday_Flag"].mean()
    train_holidays = sorted(int(w) for w in nat[(nat > 0) & (nat.index <= 48)].index)
    return {"by_category_week": by_cat_week, "uplift": uplift.reset_index(),
            "context": {"weeks": {"51": str(hol.loc[51, "WeekDate"].date()), "52": str(hol.loc[52, "WeekDate"].date())},
                        "holiday_weeks_available_to_F6_training": train_holidays,
                        "national_holiday_share_51_52": [float(nat[51]), float(nat[52])]}}


def reproducibility_review(cp4: pd.DataFrame, manifest: dict) -> dict:
    checks = manifest.get("reproducibility_check", {})
    max_diff = max((v["max_abs_difference"] for v in checks.values()), default=float("nan"))
    rf = cp4[cp4["model"] == RF]
    actual = rf.groupby("horizon")["actual"].sum()
    n = rf.groupby("horizon").size()
    eps = float(np.finfo(float).eps)
    return {
        "observed_max_abs_difference_units": max_diff,
        "observed_in_runs": sorted(checks),
        "strict_bit_exact": bool(max_diff == 0),
        "median_rf_forecast_units": float(rf["forecast"].median()),
        "relative_to_median_forecast": float(max_diff / rf["forecast"].median()),
        "float64_machine_epsilon": eps,
        "differences_in_units_of_epsilon_x_median": float(max_diff / (eps * rf["forecast"].median())),
        "max_possible_wape_change_pct_points": {f"H{h}": float(100 * max_diff * n[h] / actual[h]) for h in n.index},
        "explanation": ("With n_jobs=-1, scikit-learn sums the 300 tree predictions in parallel threads; the order of "
                        "floating-point additions can vary between runs and float addition is not associative, so "
                        "results can differ in the last bits. The difference is a few machine epsilons relative to "
                        "the forecast size; single-threaded refits (n_jobs=1, tested) are bit-identical."),
        "proposed_tolerance": dict(REPRO_TOLERANCE),
        "within_proposed_tolerance": bool(max_diff <= REPRO_TOLERANCE["atol_units"]),
        "status": ("Bit-exact reproducibility is NOT claimed for n_jobs=-1. Reproducible within the proposed "
                   "tolerance (pending approval)."),
    }


# ------------------------------------------------------------ leakage tests
def run_leakage_tests() -> dict:
    """Run the forecasting leakage/integrity test files in a subprocess and summarise the outcome."""
    cmd = [sys.executable, "-m", "pytest", *LEAKAGE_TEST_FILES, "-rA", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, cwd=config.PROJECT_ROOT, capture_output=True, text=True)
    lines = proc.stdout.splitlines()
    passed = sum(1 for line in lines if line.startswith("PASSED"))
    failed = sum(1 for line in lines if line.startswith(("FAILED", "ERROR")))
    status = "PASS" if proc.returncode == 0 and failed == 0 and passed > 0 else "FAIL"
    return {"status": status, "summary": f"{passed} passed, {failed} failed", "files": list(LEAKAGE_TEST_FILES),
            "exit_code": proc.returncode}


# ------------------------------------------------------------------ the run
def assessment_dimensions(gates: dict, boot: pd.DataFrame, decision: dict, christmas: dict) -> dict:
    out = {}
    for h, gl in gates.items():
        s = {g["gate"]: g["status"] for g in gl}
        prim = boot[(boot["horizon"] == h) & (boot["variant"] == "series x week-block (primary)")].iloc[0]
        out[f"H{h}"] = {
            "statistical_significance": (f"G8 {s['G8']}: relative improvement {prim['point_relative_improvement_pct']:.2f}% "
                                         f"(95% CI {prim['ci95_rel_low']:.2f}% to {prim['ci95_rel_high']:.2f}%)"),
            "predictive_accuracy": {k: s[k] for k in ("G1", "G2", "G3", "G6", "G7")},
            "bias": {k: s[k] for k in ("G4", "G5")},
            "recommendation": decision[h],
            "operational_deployment_suitability": (
                "NOT YET SUITABLE for any horizon: apparently synthetic data with unconfirmed provenance; one year of "
                "history; Christmas weeks 51-52 under-forecast by ~14-21% by every model; discounted weeks "
                "under-forecast by ~15% in S0; no holiday calendar beyond 2024-12-23; reproducibility only within "
                "a tolerance not yet approved. A statistical PASS is not a deployment approval."),
        }
    return out


def run_acceptance(run_id: str | None = None, data: dict | None = None, panel: pd.DataFrame | None = None,
                   leakage: dict | None = None, replicates: int | None = None, folds=None) -> Path:
    from dpe.eda.data import DATASET_LABEL
    from dpe.eda.outputs import save_json, save_table
    from dpe.forecast.panel import load_verified_panel

    data = data or load_predictions()
    panel_info = {"note": "injected panel (tests)"}
    if panel is None:
        panel, panel_info = load_verified_panel()
    leakage = leakage or run_leakage_tests()
    cp3, cp4 = data["cp3"], data["cp4"]
    verification = verify(cp3, cp4, panel, data["cp4_metrics"], data["cp3_metrics"], folds)
    horizons = sorted(cp4["horizon"].unique())
    boot, draws = bootstrap_all(cp4, horizons, replicates)
    gates = {h: evaluate_gates(cp4, boot, leakage, h) for h in horizons}
    decision = {h: decide(g) for h, g in gates.items()}
    matrix = pd.DataFrame([{"horizon": f"H{h}", **g} for h, gl in gates.items() for g in gl])
    meat = meat_and_month_diagnostics(cp4, panel)
    xmas = christmas_diagnostics(cp4, panel)
    repro = reproducibility_review(cp4, data.get("cp4_manifest", {}))
    dims = assessment_dimensions(gates, boot, decision, xmas)

    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_cp5_acceptance"
    run_dir = config.new_run_dir(run_id)
    save_table(matrix, run_dir / "acceptance_matrix.csv")
    save_table(boot, run_dir / "bootstrap" / "bootstrap_summary.csv")
    save_table(draws, run_dir / "bootstrap" / "bootstrap_replicates_relative_improvement_pct.csv")
    save_table(meat["month_coverage"], run_dir / "diagnostics" / "target_month_coverage.csv")
    save_table(meat["ratio_to_origin"], run_dir / "diagnostics" / "forecast_and_actual_relative_to_origin_week.csv")
    save_table(meat["meat_by_target_week"], run_dir / "diagnostics" / "meat_by_target_week.csv")
    save_table(meat["meat_weekly_level"], run_dir / "diagnostics" / "meat_weekly_level.csv")
    save_table(xmas["by_category_week"], run_dir / "diagnostics" / "weeks_45_52_by_category.csv")
    save_table(xmas["uplift"], run_dir / "diagnostics" / "christmas_uplift_vs_weeks_45_50.csv")
    save_json(repro, run_dir / "diagnostics" / "reproducibility_review.json")
    save_json({"recommendations": {f"H{h}": d for h, d in decision.items()}, "dimensions": dims,
               "decision_rule": DECISION_RULE}, run_dir / "recommendations.json")
    save_json(verification, run_dir / "verification.json")
    save_json({
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "step": "4B CP5 - acceptance review (no retraining, tuning, selection, deployment or promotion)",
        "dataset_label": DATASET_LABEL,
        "inputs": {"cp3_run": config.BASELINE_RUN_ID, "cp4_run": config.RF_BACKTEST_RUN_ID,
                   "checksums_verified": data.get("evidence"), "panel": panel_info},
        "comparison": f"{RF} vs {BASELINE} (better baseline in every fold in CP3)",
        "gate_thresholds": {k: (dict(v) if isinstance(v, MappingProxyType) else v) for k, v in GATE_THRESHOLDS.items()},
        "thresholds_source": "STEP_4A_FORECAST_DESIGN.md section 10, unchanged (provisional per section 14)",
        "status_rules": STATUS_RULES, "decision_rule": DECISION_RULE,
        "bootstrap": {**dict(BOOTSTRAP), "procedure": (
            "Per horizon: sum |error| of each model and actual units into cells (series or store) x (fold block). "
            "Each replicate draws clusters with replacement and, independently, the 6 week blocks with replacement; "
            "cell weight = cluster count x block count; statistic = 100 x (1 - weighted sum|e_RF| / weighted "
            "sum|e_mean_4w|); 95% percentile interval. Both models share every replicate's weights (paired).")},
        "leakage_tests": leakage,
        "reproducibility_tolerance_proposed": dict(REPRO_TOLERANCE),
        "models_retrained_or_tuned": [], "models_selected_deployed_or_promoted": [],
    }, run_dir / "manifest.json")
    return run_dir
