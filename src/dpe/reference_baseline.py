"""Reproducible V2 port of the Oct 2025 Random Forest baseline.

Reference copy (unchanged): legacy/perishable_project/src/baseline_model.py

Deliberate changes from the original (see docs/STEP_3B_REPRODUCTION.md):
1. Inputs are read only from V2 data/raw and checksum-verified first; no fallback search
   and no silent skipping of missing files.
2. Outputs go only to a new outputs/runs/<run_id>/ folder, through config.assert_safe_output.
3. Store_ID and Product_ID are preserved. The original used
   groupby().apply(include_groups=False), which silently dropped both columns. Lags and
   rolling features are now computed with groupby().shift()/transform(); the values and row
   order are the same, and the IDs are still excluded from the model's inputs.
4. A missing scikit-learn raises an error instead of quietly falling back to the naive model.
5. Extra reporting only (WAPE, bias, run manifest, comparison with the Oct 2025 reference).

Known limitations kept on purpose so this run is comparable with the reference
(to be corrected in Step 3c): one-week-ahead lags, Week_Number_wx dummies,
same-week weather/price/discount/marketing used as inputs, no rolling backtest.
"""
from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from dpe.config import (
    REFERENCE_DIR,
    assert_safe_output,
    new_run_dir,
    raw_path,
    verify_raw_inputs,
)

ID_COLUMNS = ["Store_ID", "Product_ID"]
LAGS = [1, 2, 4, 8]
N_VAL_WEEKS = 8
RF_PARAMS = {"n_estimators": 300, "max_depth": 12, "n_jobs": -1, "random_state": 42}


# --------------------------------------------------------------------------- loading
def _load_csv(name: str) -> pd.DataFrame:
    path = raw_path(name)
    df = pd.read_csv(path)
    print(f"[ok] Loaded {path.name} with shape {df.shape}.")
    return df


# --------------------------------------------------------------------- unchanged logic
def _parse_week_date(df: pd.DataFrame) -> pd.DataFrame:
    """Unchanged from the original."""
    for col in ("Week_Start_Date", "Date", "WeekStart", "week_start_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            df["WeekDate"] = df[col]
            break
    else:
        if "Week_Number" in df.columns:
            s = df["Week_Number"].astype(str).str.strip() + "-1"
            dt = pd.to_datetime(s, format="%Y-W%W-%w", errors="coerce")
            if dt.isna().mean() > 0.5:
                dt = pd.to_datetime(df["Week_Number"], errors="coerce")
            df["WeekDate"] = dt
        else:
            raise ValueError(
                "Could not infer weekly date. Provide 'Week_Start_Date' or 'Week_Number'."
            )

    if df["WeekDate"].isna().any():
        missing = int(df["WeekDate"].isna().sum())
        print(f"[warn] {missing} rows have invalid WeekDate and will be dropped.")
        df = df.loc[df["WeekDate"].notna()].copy()
    df["WeekDate"] = df["WeekDate"].dt.to_period("W").dt.start_time
    return df


def _safe_merge(left: pd.DataFrame, right: Optional[pd.DataFrame], on: str, how: str = "left") -> pd.DataFrame:
    """Unchanged from the original."""
    if right is None:
        return left
    if on not in left.columns or on not in right.columns:
        print(f"[warn] Cannot merge on '{on}'; column missing. Skipping merge.")
        return left
    return left.merge(right, on=on, how=how)


def _add_series_features(df: pd.DataFrame, keys: List[str]) -> pd.DataFrame:
    """Lag/rolling features per series. CHANGED: keeps the key columns (see module notes)."""
    if keys:
        grouped = df.groupby(keys, sort=False)["Units_Sold"]
        shift = grouped.shift
        roll = lambda window, how: grouped.transform(  # noqa: E731
            lambda s: getattr(s.shift(1).rolling(window), how)()
        )
    else:
        series = df["Units_Sold"]
        shift = series.shift
        roll = lambda window, how: getattr(series.shift(1).rolling(window), how)()  # noqa: E731

    for lag in LAGS:
        df[f"lag_{lag}"] = shift(lag)
    df["roll_mean_4"] = roll(4, "mean")
    df["roll_std_4"] = roll(4, "std")
    df["roll_mean_8"] = roll(8, "mean")
    return df


def build_features(sales: pd.DataFrame,
                   product: Optional[pd.DataFrame],
                   store: Optional[pd.DataFrame],
                   weather: Optional[pd.DataFrame]) -> pd.DataFrame:
    df = sales.copy()

    rename_map = {
        "UnitsSold": "Units_Sold",
        "units_sold": "Units_Sold",
        "store_id": "Store_ID",
        "product_id": "Product_ID",
    }
    df.rename(columns=rename_map, inplace=True)

    df = _parse_week_date(df)

    df = _safe_merge(df, product, on="Product_ID")
    df = _safe_merge(df, store, on="Store_ID")

    if weather is not None:
        weather = weather.copy()
        if "WeekDate" not in weather.columns:
            try:
                weather = _parse_week_date(weather)
            except Exception:
                pass
        if "Region" in df.columns and "Region" in weather.columns and "WeekDate" in weather.columns:
            df = df.merge(weather, on=["Region", "WeekDate"], how="left", suffixes=("", "_wx"))
        else:
            print("[warn] Weather merge skipped (needs Region and WeekDate).")

    keys = [c for c in ID_COLUMNS if c in df.columns]
    if not keys:
        keys = ["Product_ID"] if "Product_ID" in df.columns else ["Store_ID"] if "Store_ID" in df.columns else []

    # Same ordering as the original: by series, then chronologically.
    df = df.sort_values(keys + ["WeekDate"]) if keys else df.sort_values(["WeekDate"])
    df = df.reset_index(drop=True)

    if "Units_Sold" not in df.columns:
        raise ValueError("Expected 'Units_Sold' column in weekly_sales.csv")

    df = _add_series_features(df, keys)

    df["weekofyear"] = df["WeekDate"].dt.isocalendar().week.astype(int)
    df["month"] = df["WeekDate"].dt.month
    df["quarter"] = df["WeekDate"].dt.quarter

    for col in ["Price", "Discount_Percent", "Marketing_Spend"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    before = len(df)
    df = df.dropna(subset=[c for c in df.columns if c.startswith("lag_")])
    after = len(df)
    if before != after:
        print(f"[info] Dropped {before - after} rows without sufficient lag history.")

    return df


def make_feature_matrix(df: pd.DataFrame, target: str = "Units_Sold"):
    """Unchanged from the original: IDs, date, target and same-week wastage are excluded."""
    y = df[target].astype(float)
    drop_cols: List[str] = [
        target,
        "WeekDate",
        "Wastage_Units",
    ] + [c for c in ["Store_ID", "Product_ID", "Region"] if c in df.columns]
    drop_cols += [c for c in ["Week_Number", "Week_Start_Date", "Date", "WeekStart"] if c in df.columns]

    X_num = df.drop(columns=[c for c in drop_cols if c in df.columns], errors="ignore")
    cat_cols = [c for c in X_num.select_dtypes(include=["object", "category"]).columns if X_num[c].nunique() <= 50]
    X = pd.get_dummies(X_num, columns=cat_cols, drop_first=True)
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return X, y


def temporal_split(df: pd.DataFrame, n_val_weeks: int = N_VAL_WEEKS):
    """Unchanged logic; ADDED a hard check that training weeks precede validation weeks."""
    weeks = np.sort(df["WeekDate"].unique())
    if len(weeks) <= n_val_weeks:
        raise ValueError("Not enough weeks to create a validation split.")
    cutoff = weeks[-n_val_weeks]
    train = df[df["WeekDate"] < cutoff]
    valid = df[df["WeekDate"] >= cutoff]
    if not train.empty and not valid.empty and train["WeekDate"].max() >= valid["WeekDate"].min():
        raise AssertionError("Chronological split violated.")
    print(f"[split] Train weeks: {train['WeekDate'].min().date()} -> {train['WeekDate'].max().date()} ({train.shape[0]} rows)")
    print(f"[split] Valid weeks: {valid['WeekDate'].min().date()} -> {valid['WeekDate'].max().date()} ({valid.shape[0]} rows)")
    return train, valid


def metrics(y_true, y_pred) -> dict:
    """Unchanged from the original (MAE, RMSE, R2)."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {"MAE": mae, "RMSE": rmse, "R2": r2}


def extra_metrics(y_true, y_pred) -> dict:
    """ADDED reporting only: WAPE and bias as a share of actual units."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    total = np.sum(y_true)
    return {
        "WAPE": float(np.sum(np.abs(y_true - y_pred)) / total) if total else float("nan"),
        "Bias": float(np.sum(y_pred - y_true) / total) if total else float("nan"),
    }


def naive_last_week(valid: pd.DataFrame, keys: List[str]) -> np.ndarray:
    """Unchanged from the original."""
    if "lag_1" in valid.columns:
        pred = valid["lag_1"].copy()
    else:
        pred = pd.Series(np.nan, index=valid.index)

    if pred.isna().any():
        if keys and all(k in valid.columns for k in keys):
            med = valid.groupby(keys)["Units_Sold"].transform("median")
            pred = pred.fillna(med)
        pred = pred.fillna(valid["Units_Sold"].median())
    return pred.to_numpy()


def fit_model_rf(X_train: pd.DataFrame, y_train: pd.Series):
    """Same model and settings; CHANGED to fail loudly if scikit-learn is unavailable."""
    from sklearn.ensemble import RandomForestRegressor

    model = RandomForestRegressor(**RF_PARAMS)
    model.fit(X_train, y_train)
    return model


# ------------------------------------------------------------------------ outputs
def build_prediction_frame(valid_df: pd.DataFrame, preds: Dict[str, np.ndarray]) -> pd.DataFrame:
    """ADDED: prediction table that always carries Store_ID, Product_ID and WeekDate."""
    missing = [c for c in ID_COLUMNS if c not in valid_df.columns]
    if missing:
        raise ValueError(f"Prediction output is missing identifier columns: {missing}")
    out = valid_df[ID_COLUMNS + ["WeekDate", "Units_Sold"]].copy()
    for name, yhat in preds.items():
        yhat = np.asarray(yhat)
        if len(yhat) != len(out):
            raise ValueError(f"Prediction '{name}' has {len(yhat)} rows; expected {len(out)}.")
        out[f"pred_{name}"] = yhat
    if out.duplicated(subset=ID_COLUMNS + ["WeekDate"]).any():
        raise ValueError("Duplicate Store_ID/Product_ID/WeekDate rows in predictions.")
    return out


def compare_with_reference(out: pd.DataFrame) -> dict:
    """ADDED: compare with the Oct 2025 predictions (reference only; never forced to match)."""
    ref_path = REFERENCE_DIR / "validation_predictions.csv"
    ref = pd.read_csv(ref_path)
    result = {"reference_file": "data/reference/validation_predictions.csv",
              "reference_rows": int(len(ref)), "new_rows": int(len(out))}
    if len(ref) != len(out):
        result["aligned"] = False
        return result
    same_dates = (pd.to_datetime(ref["WeekDate"]).dt.date.values == out["WeekDate"].dt.date.values).all()
    same_actuals = (ref["Units_Sold"].to_numpy() == out["Units_Sold"].to_numpy()).all()
    result["aligned"] = bool(same_dates and same_actuals)
    for name in ("naive", "rf"):
        col = f"pred_{name}"
        if col in ref.columns and col in out.columns:
            result[f"max_abs_diff_{col}"] = float(np.max(np.abs(ref[col].to_numpy() - out[col].to_numpy())))
            result[f"reference_metrics_{name}"] = {k: float(v) for k, v in metrics(ref["Units_Sold"], ref[col]).items()}
    return result


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(assert_safe_output(path), index=False)


def _write_json(obj: dict, path: Path) -> None:
    safe = assert_safe_output(path)
    safe.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _package_versions() -> dict:
    import sklearn
    return {"python": platform.python_version(), "pandas": pd.__version__,
            "numpy": np.__version__, "scikit-learn": sklearn.__version__}


# --------------------------------------------------------------------------- run
def run(run_id: Optional[str] = None, n_val_weeks: int = N_VAL_WEEKS) -> Path:
    input_hashes = verify_raw_inputs()
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_reference_rf"
    run_dir = new_run_dir(run_id)
    print(f"[run] {run_id} -> {run_dir}")

    weekly_sales = _load_csv("weekly_sales.csv")
    product = _load_csv("product_details.csv")
    store = _load_csv("store_info.csv")
    weather = _load_csv("weather_data.csv")

    df = build_features(weekly_sales, product, store, weather)
    train_df, valid_df = temporal_split(df, n_val_weeks=n_val_weeks)
    keys = [k for k in ID_COLUMNS if k in df.columns]

    X_train, y_train = make_feature_matrix(train_df)
    X_valid, y_valid = make_feature_matrix(valid_df)
    X_valid = X_valid.reindex(columns=X_train.columns, fill_value=0.0)

    model = fit_model_rf(X_train, y_train)

    preds = {"naive": naive_last_week(valid_df, keys), "rf": model.predict(X_valid)}

    results = {}
    print("\n[results] Validation metrics:")
    for name, yhat in preds.items():
        m = {k: float(v) for k, v in metrics(y_valid, yhat).items()}
        m.update(extra_metrics(y_valid, yhat))
        results[name] = m
        print(f"- {name:>6}: MAE={m['MAE']:.3f} RMSE={m['RMSE']:.3f} R2={m['R2']:.3f} WAPE={m['WAPE']:.3%}")

    out = build_prediction_frame(valid_df, preds)
    _write_csv(out, run_dir / "validation_predictions.csv")
    _write_json(results, run_dir / "metrics.json")

    manifest = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_script": "legacy/perishable_project/src/baseline_model.py (ported)",
        "versions": _package_versions(),
        "inputs_sha256": input_hashes,
        "rf_params": RF_PARAMS,
        "n_val_weeks": n_val_weeks,
        "train_weeks": [str(train_df["WeekDate"].min().date()), str(train_df["WeekDate"].max().date())],
        "valid_weeks": [str(valid_df["WeekDate"].min().date()), str(valid_df["WeekDate"].max().date())],
        "rows": {"features": int(len(df)), "train": int(len(train_df)), "valid": int(len(valid_df))},
        "feature_columns": list(X_train.columns),
        "metrics": results,
        "reference_comparison": compare_with_reference(out),
    }
    _write_json(manifest, run_dir / "run_manifest.json")
    print(f"[ok] Wrote outputs to {run_dir}")
    return run_dir
