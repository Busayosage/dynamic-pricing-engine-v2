"""Step 4D Phase 2: the one-round challenger backtest (S0, six folds, H1 and H4).

Writes a new outputs/runs/<id>_challenger_backtest folder. Incumbent forecasts are NOT recomputed here;
challenger_eval.py reads them from the protected CP3/CP4 runs.
"""
from __future__ import annotations

import hashlib
import platform
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from dpe import config
from dpe.forecast import backtest as B
from dpe.forecast import challengers as C
from dpe.forecast.features import attach_target, build_features, feature_columns
from dpe.forecast.panel import holiday_calendar, load_verified_panel

HORIZONS = (1, 4)
CHECK_FOLDS = {"reproducibility": "F1", "negative_control": "F3", "inner_sanity": "F3"}
SEGMENT_COLUMNS = ["Product_Category", "Region", "target_holiday", "target_discounted"]


def _segments(pred: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    seg = panel[["Store_ID", "Product_ID", "week_index", "Product_Category", "Region", "Holiday_Flag",
                 "Discount_Percent"]].rename(columns={"week_index": "target_week", "Holiday_Flag": "target_holiday"})
    seg["target_discounted"] = seg.pop("Discount_Percent") > 0
    return pred.merge(seg, on=["Store_ID", "Product_ID", "target_week"], how="left", validate="many_to_one")


def compute_challengers(panel: pd.DataFrame, folds=None, horizons=HORIZONS, models=C.CHALLENGERS, configs=C.CONFIGS,
                        run_checks: bool = True) -> dict:
    folds = folds or B.make_folds()
    calendar = holiday_calendar(panel)
    preds, metas, imps, alphas = [], [], [], []
    checks = {"reproducibility": [], "negative_control": [], "inner_sanity": []}
    for h in horizons:
        rows = attach_target(build_features(panel, calendar, h, "S0"), panel)
        for model in models:
            for fold in folds:
                plan = B.fold_plan(fold, h)
                res = C.run_fold(model, rows, panel, plan, configs)
                preds.append(res["pred"])
                metas.append(res["meta"])
                if "importance" in res:
                    imps.append(res["importance"])
                if "alphas" in res:
                    alphas.append(res["alphas"])
                if not run_checks:
                    continue
                if fold.fold == CHECK_FOLDS["reproducibility"]:
                    checks["reproducibility"].append(C.reproducibility(model, rows, panel, plan, res["pred"], configs))
                if model in C.BOOSTED and fold.fold == CHECK_FOLDS["negative_control"]:
                    checks["negative_control"].append(C.negative_control(model, rows, plan, configs))
                if model in C.BOOSTED and fold.fold == CHECK_FOLDS["inner_sanity"]:
                    checks["inner_sanity"].append(C.inner_sanity(model, rows, plan, configs))
    predictions = _segments(pd.concat(preds, ignore_index=True), panel)
    return {"predictions": predictions, "training": pd.DataFrame(metas),
            "importance": pd.concat(imps, ignore_index=True) if imps else pd.DataFrame(),
            "ses_alphas": pd.concat(alphas, ignore_index=True) if alphas else pd.DataFrame(),
            "checks": {k: pd.DataFrame(v) for k, v in checks.items()}}


def _code_hashes() -> dict:
    base = Path(__file__).resolve().parent
    names = ["challengers.py", "challenger_run.py", "features.py", "backtest.py", "models.py", "panel.py"]
    return {n: hashlib.sha256((base / n).read_bytes()).hexdigest() for n in names}


def _versions() -> dict:
    out = {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__}
    for mod in ("xgboost", "catboost", "statsmodels", "sklearn"):
        try:
            out[mod] = __import__(mod).__version__
        except ImportError:
            out[mod] = None
    return out


def run_challenger_backtest(panel: pd.DataFrame | None = None, run_id: str | None = None, folds=None,
                            horizons=HORIZONS, models=C.CHALLENGERS, configs=C.CONFIGS, run_checks: bool = True) -> Path:
    from dpe.eda.data import DATASET_LABEL
    from dpe.eda.outputs import save_json, save_table

    panel_info = {"note": "injected panel (tests)"}
    if panel is None:
        panel, panel_info = load_verified_panel()
    folds = folds or B.make_folds()
    r = compute_challengers(panel, folds, horizons, models, configs, run_checks)
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_challenger_backtest"
    run_dir = config.new_run_dir(run_id)
    save_table(r["predictions"], run_dir / "predictions.csv")
    save_table(r["training"], run_dir / "training_metadata.csv")
    if len(r["importance"]):
        save_table(r["importance"], run_dir / "feature_importance_by_fold.csv")
    if len(r["ses_alphas"]):
        save_table(r["ses_alphas"], run_dir / "ses_parameters.csv")
    for name, table in r["checks"].items():
        save_table(table, run_dir / "checks" / f"{name}.csv")
    save_json({
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "step": "4D Phase 2 - one-round challenger backtest (exploratory; folds previously examined in CP3-CP5)",
        "dataset_label": DATASET_LABEL, "panel_verification": panel_info,
        "models": list(models), "configurations": {m: dict(configs[m]) for m in models},
        "configuration_policy": "Option A - one fixed pre-registered configuration per model; no tuning",
        "scenario": "S0", "s0_features": feature_columns("S0"),
        "catboost_categorical_features": C.CAT_FEATURES,
        "horizons": list(horizons), "folds": [f.__dict__ for f in folds],
        "check_folds": CHECK_FOLDS,
        "inner_validation_use": "sanity check only; never used to select a configuration",
        "versions": _versions(), "code_sha256": _code_hashes(),
        "incumbents": "not recomputed; read from protected runs by challenger_eval",
        "label": "EXPLORATORY",
    }, run_dir / "manifest.json")
    return run_dir
