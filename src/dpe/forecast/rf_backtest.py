"""CP4: Random Forest backtest for H1 and H4 on the six CP3 folds, scenario S0 only.

For every fold and horizon: select training pairs observable at the earliest test origin (CP3
rule, asserted), fit the encoder and the forest on those rows only, predict the fold's test rows,
and score the forest and both baselines on exactly the same rows. Segment columns used for error
analysis (category, region, target-week holiday and discount status) are attached AFTER prediction
from the panel and are never model inputs. No hyperparameter is tuned; nothing is selected.
"""
from __future__ import annotations

import platform
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from dpe.config import new_run_dir
from dpe.forecast import backtest as B
from dpe.forecast.baselines import PREDICTION_KEYS, assert_identical_populations, baseline_predictions
from dpe.forecast.evaluate import metrics_table, score
from dpe.forecast.features import MIN_HISTORY_WEEKS, attach_target, build_features, feature_columns
from dpe.forecast.models import RF_PARAMS, TrainOnlyEncoder, fit_rf, predict
from dpe.forecast.panel import holiday_calendar, load_verified_panel

HORIZONS = (1, 4)
SCENARIO = "S0"
CHRISTMAS_WEEKS = (51, 52)  # 2024-12-16 and 2024-12-23
SEGMENTS = ["Product_Category", "Store_ID", "Region", "target_holiday", "target_discounted"]


def _fold_fit(rows: pd.DataFrame, plan: B.FoldPlan, rf_params: dict) -> dict:
    train = B.select_training_rows(rows, plan)
    test = B.select_test_rows(rows, plan)
    B.assert_fold_boundaries(train, test, plan)
    enc = TrainOnlyEncoder(SCENARIO).fit(train)
    X_train, X_test = enc.transform(train), enc.transform(test)
    started = time.perf_counter()
    model = fit_rf(X_train, train["target_units"], rf_params)
    fit_seconds = time.perf_counter() - started
    test_pred = predict(model, X_test)
    train_pred = predict(model, X_train)
    rf = test[PREDICTION_KEYS + ["target_units"]].rename(columns={"target_units": "actual"})
    rf.insert(len(PREDICTION_KEYS), "model", "random_forest")
    rf["forecast"] = test_pred
    fit_score = score(train["target_units"], train_pred)
    meta = {"fold": plan.fold, "horizon": plan.horizon, "train_rows": int(len(train)), "test_rows": int(len(test)),
            "train_target_min": int(train["target_week"].min()), "train_target_max": int(train["target_week"].max()),
            "train_origin_max": int(train["origin_week"].max()), "earliest_test_origin": plan.earliest_test_origin,
            "test_target_min": int(test["target_week"].min()), "test_target_max": int(test["target_week"].max()),
            "n_model_inputs": int(X_train.shape[1]), "fit_seconds": round(fit_seconds, 2),
            "train_WAPE_pct": fit_score["WAPE_pct"], "train_Bias_pct": fit_score["Bias_pct"],
            "encoder_categories_from": "training rows of this fold"}
    importance = pd.DataFrame({"fold": plan.fold, "horizon": plan.horizon, "feature": X_train.columns,
                               "importance": model.feature_importances_})
    return {"rf": rf, "baselines": baseline_predictions(test), "meta": meta, "importance": importance,
            "columns": list(X_train.columns), "test_index": test.index, "X_test": X_test, "model": model}


def _attach_segments(predictions: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Analysis-only columns (target-week attributes), joined after prediction."""
    seg = panel[["Store_ID", "Product_ID", "week_index", "Product_Category", "Region", "Holiday_Flag",
                 "Discount_Percent"]].rename(columns={"week_index": "target_week", "Holiday_Flag": "target_holiday"})
    seg["target_discounted"] = seg.pop("Discount_Percent") > 0
    out = predictions.merge(seg, on=["Store_ID", "Product_ID", "target_week"], how="left", validate="many_to_one")
    if out[["Product_Category", "Region"]].isna().any().any():
        raise ValueError("Segment attributes missing for some predictions")
    return out


def _comparison(by_fold: pd.DataFrame) -> pd.DataFrame:
    """RF vs mean_4w per horizon and fold (descriptive only; no acceptance verdict)."""
    piv = by_fold.pivot_table(index=["horizon", "fold"], columns="model", values="WAPE_pct")
    out = piv.reset_index()
    out["rf_minus_mean4w_WAPE_points"] = out["random_forest"] - out["mean_4w"]
    out["rf_relative_change_vs_mean4w_pct"] = 100 * (out["random_forest"] / out["mean_4w"] - 1)
    return out


def compute_rf_backtest(panel: pd.DataFrame, folds: list[B.Fold], horizons=HORIZONS, rf_params: dict | None = None,
                        check_reproducibility: bool = True) -> dict:
    rf_params = rf_params or RF_PARAMS
    calendar = holiday_calendar(panel)
    preds, metas, imps, feature_lists, repro = [], [], [], {}, {}
    for h in horizons:
        rows = attach_target(build_features(panel, calendar, h, SCENARIO), panel)
        for i, fold in enumerate(folds):
            plan = B.fold_plan(fold, h)
            res = _fold_fit(rows, plan, rf_params)
            preds += [res["rf"], res["baselines"]]
            metas.append(res["meta"])
            imps.append(res["importance"])
            feature_lists[f"H{h}_{fold.fold}"] = res["columns"]
            if check_reproducibility and i == 0:  # refit the first fold: identical forecasts expected
                again = _fold_fit(rows, plan, rf_params)
                diff = np.abs(again["rf"]["forecast"].to_numpy() - res["rf"]["forecast"].to_numpy())
                repro[f"H{h}_{fold.fold}"] = {"max_abs_difference": float(diff.max()), "identical": bool(diff.max() == 0)}
    predictions = _attach_segments(pd.concat(preds, ignore_index=True), panel)
    for h, g in predictions.groupby("horizon"):
        assert_identical_populations(g)
    lo, hi = B.REFERENCE_WINDOW
    metrics = {
        "pooled": metrics_table(predictions, ["horizon", "model"]),
        "by_fold": metrics_table(predictions, ["horizon", "model", "fold"]),
        "by_target_week": metrics_table(predictions, ["horizon", "model", "target_week"]),
        "reference_window": metrics_table(predictions[predictions["target_week"].between(lo, hi)], ["horizon", "model"]),
        "christmas_weeks": metrics_table(predictions[predictions["target_week"].isin(CHRISTMAS_WEEKS)],
                                         ["horizon", "model", "target_week"]),
        "christmas_combined": metrics_table(predictions[predictions["target_week"].isin(CHRISTMAS_WEEKS)],
                                            ["horizon", "model"]),
        "excluding_christmas": metrics_table(predictions[~predictions["target_week"].isin(CHRISTMAS_WEEKS)],
                                             ["horizon", "model"]),
    }
    for seg in SEGMENTS:
        metrics[f"by_{seg}"] = metrics_table(predictions, ["horizon", "model", seg])
    importance = pd.concat(imps, ignore_index=True)
    imp_summary = (importance.groupby(["horizon", "feature"])["importance"]
                   .agg(mean="mean", min="min", max="max").reset_index()
                   .sort_values(["horizon", "mean"], ascending=[True, False]))
    imp_summary["rank"] = imp_summary.groupby("horizon")["mean"].rank(ascending=False, method="first").astype(int)
    training = pd.DataFrame(metas)
    test_wape = metrics["by_fold"][metrics["by_fold"]["model"] == "random_forest"][["horizon", "fold", "WAPE_pct",
                                                                                   "Bias_pct"]]
    training = training.merge(test_wape.rename(columns={"WAPE_pct": "test_WAPE_pct", "Bias_pct": "test_Bias_pct"}),
                              on=["horizon", "fold"])
    training["test_minus_train_WAPE_points"] = training["test_WAPE_pct"] - training["train_WAPE_pct"]
    return {"predictions": predictions, "metrics": metrics, "comparison": _comparison(metrics["by_fold"]),
            "importance": importance, "importance_summary": imp_summary, "training": training,
            "feature_lists": feature_lists, "reproducibility": repro, "rf_params": rf_params}


def run_rf_backtest(panel: pd.DataFrame | None = None, run_id: str | None = None, folds=None, horizons=HORIZONS,
                    rf_params: dict | None = None, check_reproducibility: bool = True) -> Path:
    from dpe.eda.data import DATASET_LABEL
    from dpe.eda.outputs import save_json, save_table

    panel_info = {"note": "injected panel (tests)"}
    if panel is None:
        panel, panel_info = load_verified_panel()
    folds = folds or B.make_folds()
    r = compute_rf_backtest(panel, folds, horizons, rf_params, check_reproducibility)
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_rf_backtest"
    run_dir = new_run_dir(run_id)

    save_table(r["predictions"], run_dir / "predictions.csv")
    for name, table in r["metrics"].items():
        save_table(table, run_dir / "metrics" / f"{name}.csv")
    save_table(r["comparison"], run_dir / "comparison_rf_vs_mean4w_by_fold.csv")
    save_table(r["training"], run_dir / "training_metadata.csv")
    save_table(r["importance"], run_dir / "feature_importance_by_fold.csv")
    save_table(r["importance_summary"], run_dir / "feature_importance_summary.csv")
    save_json({"scenario": SCENARIO, "pre_encoding_features": feature_columns(SCENARIO),
               "model_input_columns_by_fold": r["feature_lists"]}, run_dir / "feature_lists.json")
    import sklearn

    save_json({
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "step": "4B CP4 - Random Forest backtest, S0 only (no tuning, no selection, no acceptance verdict)",
        "dataset_label": DATASET_LABEL,
        "panel_verification": panel_info,
        "versions": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
                     "scikit-learn": sklearn.__version__},
        "rf_params": r["rf_params"], "rf_params_source": "dpe.reference_baseline.RF_PARAMS (original configuration)",
        "hyperparameter_tuning": "none",
        "scenario": SCENARIO, "excluded_inputs": "target-week price, discount, marketing, weather; wastage at any lag",
        "horizons": list(horizons), "folds": [f.__dict__ for f in folds], "min_history_weeks": MIN_HISTORY_WEEKS,
        "training_rule": "per fold and horizon: training targets <= earliest test origin (test_start - h)",
        "preprocessing": "one-hot category lists fitted on each fold's training rows; no imputer or scaler; "
                         "forecasts clipped at 0",
        "analysis_only_columns": SEGMENTS,
        "christmas_weeks": list(CHRISTMAS_WEEKS),
        "feature_importance": "impurity-based (mean decrease in impurity) from each fitted forest; "
                              "describes model usage, not causal effects",
        "reproducibility_check": r["reproducibility"],
        "identical_scoring_population": True,
        "acceptance": "not evaluated in CP4; thresholds remain provisional (STEP_4A section 14)",
        "models_selected_or_promoted": [],
    }, run_dir / "manifest.json")
    return run_dir
