"""CP3 baselines. Both read only the as-of history features at the forecast origin T, so for H4
they never see weeks T+1..T+3 (the builder's history ends at T; tested in test_forecast_features).

- last_week:  forecast = units sold in the origin week T            (feature y_t0)
- mean_4w:    forecast = mean units of weeks T-3..T                  (feature mean_4)
"""
from __future__ import annotations

import pandas as pd

BASELINES = {
    "last_week": ("y_t0", "Units sold in the last observed week (the forecast origin)."),
    "mean_4w": ("mean_4", "Mean units of the four most recent observed weeks, ending at the forecast origin."),
}
PREDICTION_KEYS = ["fold", "Store_ID", "Product_ID", "origin_week", "origin_date", "target_week", "target_date",
                   "horizon"]


def baseline_predictions(rows: pd.DataFrame) -> pd.DataFrame:
    """Long table: one row per forecast row and baseline, keys preserved, with the actual target units."""
    missing = [c for c in PREDICTION_KEYS + ["target_units"] if c not in rows.columns]
    if missing:
        raise ValueError(f"Rows are missing columns {missing}")
    parts = []
    for name, (col, _) in BASELINES.items():
        p = rows[PREDICTION_KEYS + ["target_units"]].rename(columns={"target_units": "actual"})
        p.insert(len(PREDICTION_KEYS), "model", name)
        p["forecast"] = rows[col].astype(float).to_numpy()
        parts.append(p)
    out = pd.concat(parts, ignore_index=True)
    if out[["actual", "forecast"]].isna().any().any():
        raise ValueError("Baseline forecasts or actuals contain missing values")
    return out


def assert_identical_populations(predictions: pd.DataFrame) -> None:
    """Every model must be scored on exactly the same (fold, horizon, series, target) rows."""
    keys = ["fold", "horizon", "Store_ID", "Product_ID", "origin_week", "target_week"]
    sets = {m: set(map(tuple, g[keys].to_numpy())) for m, g in predictions.groupby("model")}
    first = next(iter(sets.values()))
    for m, s in sets.items():
        if s != first:
            raise AssertionError(f"Model {m} is scored on a different population")
    if predictions.duplicated(subset=keys + ["model"]).any():
        raise AssertionError("Duplicate prediction rows")
