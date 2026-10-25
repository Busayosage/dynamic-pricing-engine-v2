"""Step 4D Phase 3: evaluate challengers against the incumbents under the pre-registered replacement policy
(docs/STEP_4D_REPLACEMENT_POLICY.md). Reads, never modifies, the protected CP3/CP4 runs and the challenger run.

- R1 integrity, R2 the nine CP5 gates vs mean_4w (dpe.forecast.acceptance, unchanged, via an adapter that
  presents the challenger in the RF's place), R3 improvement over the incumbent with a Bonferroni-adjusted
  two-way bootstrap, R4 bias versus the incumbent.
- All results are EXPLORATORY: the folds were examined in CP3-CP5; significance here is not independent
  confirmation.
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
from dpe.forecast import acceptance as A
from dpe.forecast.evaluate import metrics_table

INCUMBENT = MappingProxyType({1: "random_forest", 4: "mean_4w"})
CHALLENGERS = ("xgboost", "catboost", "ses")
N_COMPARISONS = 6  # 3 challengers x 2 horizons
RULES = MappingProxyType({
    "R1_4_reproducibility_atol_units": 1e-6,
    "R1_5_negative_control_min_ratio": 0.9,
    "R3a_min_relative_improvement_pct": 2.0,
    "R3b_ci_level": 1 - 0.05 / N_COMPARISONS,
    "R3b_replicates": 5000,
    "R3b_seed": 20261022,
    "R3c_min_folds_better": 5,
    "R3d_max_category_worse_points": 1.0,
    "R4a_max_pooled_abs_bias_increase_points": 1.0,
    "R4b_fold_bias_limit_pct": 10.0,
})
EXPLORATORY = ("EXPLORATORY - the six folds were examined in CP3-CP5; bootstrap intervals are conservative "
               "within-sample statements on reused folds, not independent confirmation.")
LEAKAGE_FILES = A.LEAKAGE_TEST_FILES + ("tests/test_forecast_challengers.py",)
KEYS = A.KEYS


# ------------------------------------------------------------------ loading
def load_challenger_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    dates = ["origin_date", "target_date"]
    checks = {n: pd.read_csv(run_dir / "checks" / f"{n}.csv") if (run_dir / "checks" / f"{n}.csv").stat().st_size > 2
              else pd.DataFrame() for n in ("reproducibility", "negative_control", "inner_sanity")}
    return {"predictions": pd.read_csv(run_dir / "predictions.csv", parse_dates=dates), "checks": checks,
            "manifest": json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")), "run_dir": run_dir}


def verify_alignment(cp4: pd.DataFrame, ch: pd.DataFrame) -> dict:
    """Each challenger scores exactly the CP4 rows (keys, origins, targets) with identical actuals."""
    ref = cp4[cp4["model"] == A.RF][KEYS + ["actual", "origin_date", "target_date"]]
    out = {}
    for m, g in ch.groupby("model"):
        j = ref.merge(g[KEYS + ["actual", "origin_date", "target_date"]], on=KEYS, how="outer",
                      suffixes=("_cp4", "_ch"), indicator=True)
        ok = bool((j["_merge"] == "both").all() and (j["actual_cp4"] == j["actual_ch"]).all()
                  and (j["origin_date_cp4"] == j["origin_date_ch"]).all()
                  and (j["target_date_cp4"] == j["target_date_ch"]).all()
                  and not g.duplicated(subset=KEYS).any())
        out[m] = {"rows": int(len(g)), "identical_rows_and_actuals": ok,
                  "finite_non_negative": bool(np.isfinite(g["forecast"]).all() and (g["forecast"] >= 0).all())}
    return out


def combined_predictions(cp4: pd.DataFrame, ch: pd.DataFrame) -> pd.DataFrame:
    cols = KEYS + ["origin_date", "target_date", "model", "actual", "forecast", "Product_Category", "Region",
                   "target_holiday", "target_discounted"]
    return pd.concat([cp4[cols], ch[cols]], ignore_index=True)


# ---------------------------------------------------------------- bootstrap
def pair_cells(df: pd.DataFrame, a: str, b: str, horizon: int, cluster=("Store_ID", "Product_ID")) -> dict:
    """acceptance.cell_sums for an arbitrary pair (a = candidate, b = comparator)."""
    sub = df[(df["horizon"] == horizon) & df["model"].isin([a, b])].copy()
    sub["model"] = sub["model"].map({a: A.RF, b: A.BASELINE})
    return A.cell_sums(sub, horizon, cluster)


def pair_bootstrap(df: pd.DataFrame, a: str, b: str, horizon: int, level: float, replicates: int, seed: int) -> dict:
    lo_q, hi_q = 100 * (1 - level) / 2, 100 * (1 + level) / 2
    out = {}
    for name, cluster in (("primary", ("Store_ID", "Product_ID")), ("store_sensitivity", ("Store_ID",))):
        r = A.two_way_bootstrap(pair_cells(df, a, b, horizon, cluster), replicates, seed)
        d = r.pop("_draws")
        out[name] = {"point_relative_improvement_pct": r["point_relative_improvement_pct"],
                     "ci_level": level, "ci_low": float(np.percentile(d, lo_q)), "ci_high": float(np.percentile(d, hi_q)),
                     "share_replicates_better": float(np.mean(d > 0)), "replicates": replicates, "seed": seed,
                     "n_clusters": r["n_clusters"], "n_blocks": r["n_blocks"]}
    return out


# -------------------------------------------------------------------- rules
def cp5_screen(df: pd.DataFrame, challenger: str, leakage: dict, horizons) -> dict:
    """The nine CP5 gates, unchanged, with the challenger in the RF's place against mean_4w."""
    adapter = df[df["model"].isin([challenger, A.BASELINE])].copy()
    adapter["model"] = adapter["model"].replace({challenger: A.RF})
    boot, _ = A.bootstrap_all(adapter, horizons)
    return {h: A.evaluate_gates(adapter, boot, leakage, h) for h in horizons}


def _p(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def integrity_rules(challenger: str, horizon: int, leakage: dict, alignment: dict, checks: dict) -> list[dict]:
    def row(frame, col):
        if frame.empty:
            return None
        hit = frame[(frame["model"] == challenger) & (frame["horizon"] == horizon)]
        return None if hit.empty else hit.iloc[0][col]
    rep = row(checks["reproducibility"], "max_abs_difference")
    nc = row(checks["negative_control"], "ratio")
    inner = row(checks["inner_sanity"], "passes")
    boosted = challenger in ("xgboost", "catboost")
    a = alignment.get(challenger, {})
    return [
        {"rule": "R1.1", "criterion": "Leakage and integrity tests pass", "observed": leakage.get("summary", "not run"),
         "status": leakage.get("status", "FAIL")},
        {"rule": "R1.2", "criterion": "Identical rows, origins, targets and actuals to CP4",
         "observed": str(a.get("identical_rows_and_actuals")), "status": _p(bool(a.get("identical_rows_and_actuals")))},
        {"rule": "R1.3", "criterion": "Forecasts finite and >= 0", "observed": str(a.get("finite_non_negative")),
         "status": _p(bool(a.get("finite_non_negative")))},
        {"rule": "R1.4", "criterion": f"Refit agrees within {RULES['R1_4_reproducibility_atol_units']:g} units",
         "observed": "not run" if rep is None else f"{rep:.3g}",
         "status": "FAIL" if rep is None else _p(rep <= RULES["R1_4_reproducibility_atol_units"])},
        {"rule": "R1.5", "criterion": "Negative control WAPE >= 0.9 x constant-mean WAPE",
         "observed": "not applicable (SES)" if not boosted else ("not run" if nc is None else f"ratio {nc:.3f}"),
         "status": "NOT_APPLICABLE" if not boosted else ("FAIL" if nc is None else _p(nc >= RULES["R1_5_negative_control_min_ratio"]))},
        {"rule": "R1.6", "criterion": "Inner sanity: WAPE below last_week on inner block (no selection)",
         "observed": "not applicable (SES)" if not boosted else str(inner),
         "status": "NOT_APPLICABLE" if not boosted else ("FAIL" if inner is None else _p(bool(inner)))},
    ]


def incumbent_rules(df: pd.DataFrame, challenger: str, horizon: int, pboot: dict) -> list[dict]:
    inc = INCUMBENT[horizon]
    sub = df[df["horizon"] == horizon]
    pooled = metrics_table(sub, ["model"]).set_index("model")
    fold = metrics_table(sub, ["model", "fold"]).pivot(index="fold", columns="model")
    cat = metrics_table(sub, ["model", "Product_Category"]).pivot(index="Product_Category", columns="model",
                                                                 values="WAPE_pct")
    rel = 100 * (1 - pooled.loc[challenger, "WAPE_pct"] / pooled.loc[inc, "WAPE_pct"])
    folds_better = int((fold["WAPE_pct"][challenger] < fold["WAPE_pct"][inc]).sum())
    cat_worse = cat[challenger] - cat[inc]
    b_ch, b_inc = abs(pooled.loc[challenger, "Bias_pct"]), abs(pooled.loc[inc, "Bias_pct"])
    lim = RULES["R4b_fold_bias_limit_pct"]
    out_ch = int((fold["Bias_pct"][challenger].abs() > lim).sum())
    out_inc = int((fold["Bias_pct"][inc].abs() > lim).sum())
    p, s = pboot["primary"], pboot["store_sensitivity"]
    lvl = RULES["R3b_ci_level"] * 100
    return [
        {"rule": "R3a", "criterion": f"Relative WAPE improvement vs {inc}",
         "threshold": f">= {RULES['R3a_min_relative_improvement_pct']:.1f}%", "observed": f"{rel:.2f}%",
         "status": _p(rel >= RULES["R3a_min_relative_improvement_pct"])},
        {"rule": "R3b", "criterion": f"{lvl:.2f}% two-way bootstrap interval above 0 (primary and store)",
         "threshold": "both lower bounds > 0",
         "observed": f"primary [{p['ci_low']:.2f}%, {p['ci_high']:.2f}%]; store [{s['ci_low']:.2f}%, {s['ci_high']:.2f}%]",
         "status": _p(p["ci_low"] > 0 and s["ci_low"] > 0)},
        {"rule": "R3c", "criterion": f"Folds with lower WAPE than {inc}",
         "threshold": f">= {RULES['R3c_min_folds_better']} of 6", "observed": f"{folds_better} of {len(fold)}",
         "status": _p(folds_better >= RULES["R3c_min_folds_better"])},
        {"rule": "R3d", "criterion": f"Worst category vs {inc}", "threshold": f"<= +{RULES['R3d_max_category_worse_points']:.1f} points",
         "observed": f"{cat_worse.max():+.2f} points ({cat_worse.idxmax()})",
         "status": _p(cat_worse.max() <= RULES["R3d_max_category_worse_points"])},
        {"rule": "R4a", "criterion": f"Pooled |bias| vs {inc}", "threshold": f"<= {b_inc:.2f} + 1.0 points",
         "observed": f"{b_ch:.2f}%", "status": _p(b_ch <= b_inc + RULES["R4a_max_pooled_abs_bias_increase_points"])},
        {"rule": "R4b", "criterion": f"Folds with |bias| > {lim:.0f}% vs {inc}", "threshold": f"<= {out_inc}",
         "observed": f"{out_ch}", "status": _p(out_ch <= out_inc)},
    ]


def outcome(rules: list[dict]) -> str:
    r1 = [r for r in rules if r["rule"].startswith("R1")]
    if any(r["status"] == "FAIL" for r in r1):
        return "RETAIN_INCUMBENT (integrity failure)"
    if all(r["status"] in ("PASS", "NOT_APPLICABLE") for r in rules):
        return "PROVISIONAL_CHALLENGER"
    return "RETAIN_INCUMBENT (insufficient evidence)"


def horizon_decision(outcomes: dict, pooled: pd.DataFrame, horizon: int) -> dict:
    ok = [m for m, o in outcomes.items() if o == "PROVISIONAL_CHALLENGER"]
    if not ok:
        return {"decision": f"RETAIN_INCUMBENT ({INCUMBENT[horizon]})", "provisional_challenger": None}
    best = min(ok, key=lambda m: pooled.set_index(["horizon", "model"]).loc[(horizon, m), "WAPE_pct"])
    return {"decision": f"PROVISIONAL_CHALLENGER ({best}) - pending prospective confirmation; not a production approval",
            "provisional_challenger": best, "other_qualifiers": [m for m in ok if m != best]}


# -------------------------------------------------------------- diagnostics
def diagnostics(df: pd.DataFrame, panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    d = {
        "pooled": metrics_table(df, ["horizon", "model"]),
        "by_fold": metrics_table(df, ["horizon", "model", "fold"]),
        "by_category": metrics_table(df, ["horizon", "model", "Product_Category"]),
        "by_store": metrics_table(df, ["horizon", "model", "Store_ID"]),
        "by_region": metrics_table(df, ["horizon", "model", "Region"]),
        "by_holiday": metrics_table(df, ["horizon", "model", "target_holiday"]),
        "by_discount": metrics_table(df, ["horizon", "model", "target_discounted"]),
        "christmas_by_category": metrics_table(df[df["target_week"].isin([51, 52])],
                                               ["horizon", "model", "Product_Category", "target_week"]),
        "christmas_combined": metrics_table(df[df["target_week"].isin([51, 52])], ["horizon", "model"]),
        "excluding_christmas": metrics_table(df[~df["target_week"].isin([51, 52])], ["horizon", "model"]),
        "meat_by_fold": metrics_table(df[df["Product_Category"] == "Meat"], ["horizon", "model", "fold"]),
    }
    meat = df[(df["Product_Category"] == "Meat") & df["target_week"].between(29, 40)].copy()
    u = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"]
    meat["origin_units"] = u.reindex(pd.MultiIndex.from_arrays([meat.Store_ID, meat.Product_ID, meat.origin_week])).to_numpy()
    ratio = (meat.groupby(["horizon", "model", "fold"])
             .apply(lambda g: pd.Series({"actual_over_origin": g["actual"].sum() / g["origin_units"].sum(),
                                         "forecast_over_origin": g["forecast"].sum() / g["origin_units"].sum(),
                                         "Bias_pct": 100 * (g["forecast"] - g["actual"]).sum() / g["actual"].sum()}),
                    include_groups=False).reset_index())
    d["meat_weeks_29_40_ratio_to_origin"] = ratio
    return d


# ------------------------------------------------------------ leakage tests
def run_leakage_tests() -> dict:
    cmd = [sys.executable, "-m", "pytest", *LEAKAGE_FILES, "-rA", "-p", "no:cacheprovider"]
    proc = subprocess.run(cmd, cwd=config.PROJECT_ROOT, capture_output=True, text=True)
    lines = proc.stdout.splitlines()
    passed = sum(1 for x in lines if x.startswith("PASSED"))
    failed = sum(1 for x in lines if x.startswith(("FAILED", "ERROR")))
    return {"status": "PASS" if proc.returncode == 0 and failed == 0 and passed > 0 else "FAIL",
            "summary": f"{passed} passed, {failed} failed", "files": list(LEAKAGE_FILES), "exit_code": proc.returncode}


# ------------------------------------------------------------------- run
def evaluate(cp4: pd.DataFrame, ch_run: dict, panel: pd.DataFrame, leakage: dict, replicates: int | None = None) -> dict:
    ch = ch_run["predictions"]
    alignment = verify_alignment(cp4, ch)
    df = combined_predictions(cp4, ch)
    horizons = sorted(df["horizon"].unique())
    models = [m for m in CHALLENGERS if m in set(ch["model"])]
    reps = replicates or RULES["R3b_replicates"]
    rows, outcomes, boots = [], {h: {} for h in horizons}, []
    for m in models:
        screen = cp5_screen(df, m, leakage, horizons)
        for h in horizons:
            pb = pair_bootstrap(df, m, INCUMBENT[h], h, RULES["R3b_ci_level"], reps, RULES["R3b_seed"])
            boots += [{"horizon": h, "challenger": m, "incumbent": INCUMBENT[h], "design": k, **v} for k, v in pb.items()]
            rules = (integrity_rules(m, h, leakage, alignment, ch_run["checks"])
                     + [{"rule": f"R2.{g['gate']}", "criterion": f"CP5 {g['criterion']} (vs mean_4w)",
                         "threshold": g["threshold"], "observed": g["observed"], "status": g["status"]} for g in screen[h]]
                     + incumbent_rules(df, m, h, pb))
            outcomes[h][m] = outcome(rules)
            rows += [{"horizon": f"H{h}", "challenger": m, "incumbent": INCUMBENT[h], **r} for r in rules]
    diag = diagnostics(df, panel)
    decisions = {f"H{h}": {**horizon_decision(outcomes[h], diag["pooled"], h),
                           "challenger_outcomes": outcomes[h], "incumbent": INCUMBENT[h]} for h in horizons}
    return {"matrix": pd.DataFrame(rows), "bootstrap": pd.DataFrame(boots), "decisions": decisions,
            "alignment": alignment, "diagnostics": diag}


def run_challenger_evaluation(challenger_run_dir: Path, run_id: str | None = None, data: dict | None = None,
                              panel: pd.DataFrame | None = None, leakage: dict | None = None,
                              replicates: int | None = None) -> Path:
    from dpe.eda.data import DATASET_LABEL
    from dpe.eda.outputs import save_json, save_table
    from dpe.forecast.panel import load_verified_panel

    data = data or A.load_predictions()  # verifies CP3/CP4 checksums
    if panel is None:
        panel, _ = load_verified_panel()
    ch_run = load_challenger_run(challenger_run_dir)
    leakage = leakage or run_leakage_tests()
    r = evaluate(data["cp4"], ch_run, panel, leakage, replicates)
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_challenger_evaluation"
    run_dir = config.new_run_dir(run_id)
    save_table(r["matrix"], run_dir / "replacement_matrix.csv")
    save_table(r["bootstrap"], run_dir / "incumbent_bootstrap.csv")
    for name, t in r["diagnostics"].items():
        save_table(t, run_dir / "diagnostics" / f"{name}.csv")
    save_json({"label": EXPLORATORY, "decisions": r["decisions"]}, run_dir / "decisions.json")
    save_json(r["alignment"], run_dir / "alignment.json")
    save_json({
        "run_id": run_id, "created_at": datetime.now().isoformat(timespec="seconds"),
        "step": "4D Phase 3 - challenger evaluation under the pre-registered replacement policy",
        "dataset_label": DATASET_LABEL, "label": EXPLORATORY,
        "policy": "docs/STEP_4D_REPLACEMENT_POLICY.md", "rules": dict(RULES), "incumbents": dict(INCUMBENT),
        "cp5_gates": "dpe.forecast.acceptance unchanged (thresholds, 95% bootstrap, seed 20261021)",
        "inputs": {"cp3_cp4_checksums_verified": data.get("evidence"),
                   "challenger_run": Path(ch_run["run_dir"]).name},
        "leakage_tests": leakage, "models_retrained_or_tuned_for_evaluation": [],
        "models_selected_deployed_or_promoted": [],
    }, run_dir / "manifest.json")
    return run_dir
