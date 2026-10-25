"""CP3 orchestration: baseline backtest over the six folds for H1 and H4, saved to a new run folder.

No machine-learning model is trained or tuned here.
"""
from __future__ import annotations

import platform
from datetime import datetime
from pathlib import Path

import pandas as pd

from dpe.config import new_run_dir
from dpe.forecast import backtest as B
from dpe.forecast.baselines import BASELINES, assert_identical_populations, baseline_predictions
from dpe.forecast.evaluate import baseline_metrics
from dpe.forecast.features import MIN_HISTORY_WEEKS, attach_target, build_features
from dpe.forecast.panel import holiday_calendar, load_verified_panel

HORIZONS = (1, 4)
PROVISIONAL_NOTE = ("Acceptance thresholds in docs/STEP_4A_FORECAST_DESIGN.md section 10 are provisional "
                    "(section 14) and are not applied in CP3.")


def compute_baselines(panel: pd.DataFrame, folds: list[B.Fold], horizons=HORIZONS) -> dict:
    """Pure computation (writes nothing): fold plans, baseline predictions and metrics."""
    calendar = holiday_calendar(panel)
    plans, preds = [], []
    for h in horizons:
        rows = attach_target(build_features(panel, calendar, h, "S0"), panel)
        for fold in folds:
            plan = B.fold_plan(fold, h)
            test = B.select_test_rows(rows, plan)
            train = B.select_training_rows(rows, plan)
            B.assert_fold_boundaries(train, test, plan)
            plans.append({**plan.__dict__, "test_rows": int(len(test)), "train_rows_available": int(len(train)),
                          "test_series": int(test.groupby(["Store_ID", "Product_ID"]).ngroups)})
            preds.append(baseline_predictions(test))
    predictions = pd.concat(preds, ignore_index=True)
    for h, g in predictions.groupby("horizon"):
        assert_identical_populations(g)
    targets = {h: set(map(tuple, g[["Store_ID", "Product_ID", "target_week"]].drop_duplicates().to_numpy()))
               for h, g in predictions.groupby("horizon")}
    same_targets = len({frozenset(v) for v in targets.values()}) == 1
    return {"plans": pd.DataFrame(plans), "predictions": predictions,
            "metrics": baseline_metrics(predictions, B.REFERENCE_WINDOW), "same_targets_across_horizons": same_targets}


def run_baseline_backtest(panel: pd.DataFrame | None = None, run_id: str | None = None, folds=None,
                          horizons=HORIZONS, check_reference: bool = True) -> Path:
    from dpe.eda.data import DATASET_LABEL
    from dpe.eda.outputs import save_json, save_table
    from dpe.forecast.reference_check import reference_naive_check

    source = "injected panel (tests)"
    panel_info = {}
    if panel is None:
        panel, panel_info = load_verified_panel()
        source = panel_info["panel_run"]
    folds = folds or B.make_folds()
    r = compute_baselines(panel, folds, horizons)
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_baseline_backtest"
    run_dir = new_run_dir(run_id)

    save_table(r["predictions"], run_dir / "baseline_predictions.csv")
    save_table(r["plans"], run_dir / "folds.csv")
    for name, table in r["metrics"].items():
        save_table(table, run_dir / f"metrics_{name}.csv")
    ref = reference_naive_check(r["predictions"]) if check_reference else {"note": "skipped (tests)"}
    save_json(ref, run_dir / "reference_naive_check.json")
    save_json({
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "step": "4B CP3 - baseline forecasts and chronological backtest folds (no model training)",
        "dataset_label": DATASET_LABEL,
        "panel_source": source, "panel_verification": panel_info,
        "versions": {"python": platform.python_version(), "pandas": pd.__version__},
        "horizons": list(horizons), "scenario": "S0",
        "min_history_weeks": MIN_HISTORY_WEEKS,
        "folds": [f.__dict__ for f in folds],
        "fold_rule": "training targets <= earliest test origin (test_start - h); training origins <= test_start - 2h",
        "baselines": {k: v[1] for k, v in BASELINES.items()},
        "metrics": {"WAPE_pct": "100 x sum|forecast - actual| / sum(actual)",
                    "Bias_pct": "100 x sum(forecast - actual) / sum(actual); negative = under-forecast",
                    "MAE": "mean |forecast - actual|", "RMSE": "sqrt(mean (forecast - actual)^2)",
                    "pooled": "computed over all rows of all folds, not an average of fold metrics"},
        "identical_scoring_population": True,
        "same_target_rows_for_H1_and_H4": r["same_targets_across_horizons"],
        "reference_naive_equivalent": ref.get("equivalent"),
        "provisional_thresholds": PROVISIONAL_NOTE,
        "models_trained": [],
    }, run_dir / "manifest.json")
    return run_dir
