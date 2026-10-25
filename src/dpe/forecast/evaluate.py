"""CP3 scoring: MAE, RMSE, WAPE and signed percentage bias, per fold and pooled.

WAPE = sum|forecast - actual| / sum(actual); Bias% = 100 x sum(forecast - actual) / sum(actual)
(negative = under-forecast). Pooled metrics are computed over all rows, not averaged over folds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def score(actual, forecast) -> dict:
    a = np.asarray(actual, dtype=float)
    f = np.asarray(forecast, dtype=float)
    if a.shape != f.shape or a.size == 0:
        raise ValueError("actual and forecast must be non-empty and the same length")
    err = f - a
    total = a.sum()
    return {"n": int(a.size), "actual_total": float(total),
            "MAE": float(np.mean(np.abs(err))), "RMSE": float(np.sqrt(np.mean(err ** 2))),
            "WAPE_pct": float(100 * np.abs(err).sum() / total) if total else float("nan"),
            "Bias_pct": float(100 * err.sum() / total) if total else float("nan")}


def metrics_table(predictions: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    rows = [{**dict(zip(by, k if isinstance(k, tuple) else (k,))), **score(g["actual"], g["forecast"])}
            for k, g in predictions.groupby(by, sort=True)]
    return pd.DataFrame(rows)


def baseline_metrics(predictions: pd.DataFrame, reference_window: tuple[int, int] | None = None) -> dict:
    out = {"by_fold": metrics_table(predictions, ["horizon", "model", "fold"]),
           "pooled": metrics_table(predictions, ["horizon", "model"])}
    if reference_window:
        lo, hi = reference_window
        win = predictions[predictions["target_week"].between(lo, hi)]
        out["reference_window"] = metrics_table(win, ["horizon", "model"]).assign(target_weeks=f"{lo}-{hi}")
    return out
