"""Step 4D challengers: XGBoost, CatBoost and per-series simple exponential smoothing (SES).

One fixed, pre-registered configuration per model (docs/STEP_4D_REPLACEMENT_POLICY.md section 5);
nothing is tuned. Every challenger reuses the CP2-CP4 machinery unchanged:
- S0 as-of features (dpe.forecast.features), the six folds and per-horizon training cut-offs
  (dpe.forecast.backtest, boundaries asserted), identical scored rows;
- XGBoost: identity one-hot encoded by the training-only encoder (the RF's 106 inputs);
- CatBoost: identity columns as native categorical features (static attributes known at every
  origin); its target statistics are learned inside fit() from the fold's training rows only;
- SES: smoothing level estimated per series from weeks <= the fold's earliest test origin only,
  then filtered forward through each test origin; forecast(T + h) = level at T.
Results are exploratory (folds previously examined in CP3-CP5).
"""
from __future__ import annotations

import time
import warnings
from types import MappingProxyType

import numpy as np
import pandas as pd

from dpe.forecast import backtest as B
from dpe.forecast.baselines import PREDICTION_KEYS
from dpe.forecast.evaluate import score
from dpe.forecast.features import STATIC_CATEGORICAL, check_feature_frame, feature_columns
from dpe.forecast.models import TrainOnlyEncoder

CHALLENGERS = ("xgboost", "catboost", "ses")
CAT_FEATURES = list(STATIC_CATEGORICAL)  # Product_ID, Store_ID, Product_Category, Region

CONFIGS = MappingProxyType({
    "xgboost": MappingProxyType({
        "objective": "reg:squarederror", "n_estimators": 500, "learning_rate": 0.05, "max_depth": 6,
        "min_child_weight": 10, "subsample": 0.8, "colsample_bytree": 0.8, "reg_lambda": 1.0,
        "tree_method": "hist", "random_state": 42, "n_jobs": 4}),
    "catboost": MappingProxyType({
        "loss_function": "RMSE", "iterations": 1000, "learning_rate": 0.05, "depth": 6, "l2_leaf_reg": 3,
        "random_seed": 42, "thread_count": 4, "allow_writing_files": False, "verbose": False}),
    "ses": MappingProxyType({"trend": None, "seasonal": None, "initialization_method": "estimated",
                             "smoothing_level_bounds": (0.05, 0.95)}),
})


# --------------------------------------------------------------- inputs
def catboost_frame(features: pd.DataFrame) -> pd.DataFrame:
    """S0 features with identity columns kept as categorical strings (no one-hot, no IDs as numbers)."""
    check_feature_frame(features, "S0")
    cols = feature_columns("S0")
    X = features[cols].copy()
    for c in cols:
        X[c] = X[c].astype(str) if c in CAT_FEATURES else X[c].astype(float)
    return X


# --------------------------------------------------------------- models
def fit_predict_xgboost(train: pd.DataFrame, test: pd.DataFrame, params) -> dict:
    from xgboost import XGBRegressor

    enc = TrainOnlyEncoder("S0").fit(train)
    X_train, X_test = enc.transform(train), enc.transform(test)
    model = XGBRegressor(**dict(params))
    model.fit(X_train, train["target_units"].astype(float))
    imp = model.get_booster().get_score(importance_type="gain")
    return {"model": model, "X_train": X_train, "X_test": X_test,
            "pred": np.clip(model.predict(X_test), 0, None), "fit_pred": np.clip(model.predict(X_train), 0, None),
            "importance": pd.DataFrame({"feature": X_train.columns,
                                        "importance": [imp.get(c, 0.0) for c in X_train.columns]}),
            "n_inputs": int(X_train.shape[1])}


def fit_predict_catboost(train: pd.DataFrame, test: pd.DataFrame, params) -> dict:
    from catboost import CatBoostRegressor

    X_train, X_test = catboost_frame(train), catboost_frame(test)
    model = CatBoostRegressor(**dict(params), cat_features=CAT_FEATURES)
    model.fit(X_train, train["target_units"].astype(float))
    return {"model": model, "X_train": X_train, "X_test": X_test,
            "pred": np.clip(model.predict(X_test), 0, None), "fit_pred": np.clip(model.predict(X_train), 0, None),
            "importance": pd.DataFrame({"feature": X_train.columns,
                                        "importance": model.get_feature_importance(type="PredictionValuesChange")}),
            "n_inputs": int(X_train.shape[1])}


BOOSTED = {"xgboost": fit_predict_xgboost, "catboost": fit_predict_catboost}


def _units_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.pivot(index=["Store_ID", "Product_ID"], columns="week_index", values="Units_Sold").astype(float)


def ses_fit_series(y_train: np.ndarray, params=None) -> tuple[float, float, int]:
    """(alpha, initial level, n warnings) from one series' training weeks."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    p = dict(params or CONFIGS["ses"])
    lo, hi = p.pop("smoothing_level_bounds")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        res = ExponentialSmoothing(y_train, trend=p["trend"], seasonal=p["seasonal"],
                                   initialization_method=p["initialization_method"],
                                   bounds={"smoothing_level": (lo, hi)}).fit()
    return float(res.params["smoothing_level"]), float(res.params["initial_level"]), len(caught)


def ses_levels(y: np.ndarray, alpha: float, level0: float) -> np.ndarray:
    """Level after each observed week: l_t = alpha*y_t + (1 - alpha)*l_{t-1}, l_0 = initial level."""
    out = np.empty(len(y))
    level = level0
    for i, v in enumerate(y):
        level = alpha * v + (1 - alpha) * level
        out[i] = level
    return out


def ses_predict(panel: pd.DataFrame, test: pd.DataFrame, plan: B.FoldPlan, params=None) -> dict:
    """SES forecasts for a fold's test rows; alpha from weeks <= earliest test origin only."""
    units = _units_matrix(panel)
    weeks = list(units.columns)
    if weeks != list(range(1, len(weeks) + 1)):
        raise ValueError("SES needs consecutive week indices starting at 1")
    t_fit, t_last = plan.earliest_test_origin, plan.latest_test_origin
    rows, alphas, n_warn = {}, [], 0
    for (s, p), y in units.iterrows():
        y = y.to_numpy()
        alpha, l0, w = ses_fit_series(y[:t_fit], params)
        n_warn += w
        levels = ses_levels(y[:t_last], alpha, l0)  # weeks 1..latest origin; never beyond
        rows[(s, p)] = levels
        alphas.append({"fold": plan.fold, "horizon": plan.horizon, "Store_ID": s, "Product_ID": p,
                       "alpha": alpha, "initial_level": l0, "fit_weeks": f"1-{t_fit}"})
    pred = np.array([rows[(s, p)][o - 1] for s, p, o in zip(test["Store_ID"], test["Product_ID"], test["origin_week"])])
    return {"pred": np.clip(pred, 0, None), "alphas": pd.DataFrame(alphas), "warnings": n_warn}


# --------------------------------------------------------- fold driver
def _prediction_frame(test: pd.DataFrame, model: str, pred: np.ndarray) -> pd.DataFrame:
    out = test[PREDICTION_KEYS + ["target_units"]].rename(columns={"target_units": "actual"})
    out.insert(len(PREDICTION_KEYS), "model", model)
    out["forecast"] = np.asarray(pred, dtype=float)
    if not (np.isfinite(out["forecast"]).all() and (out["forecast"] >= 0).all()):
        raise ValueError(f"{model}: forecasts must be finite and non-negative")
    return out


def run_fold(model: str, rows: pd.DataFrame, panel: pd.DataFrame, plan: B.FoldPlan, configs=CONFIGS) -> dict:
    """Fit (or smooth) one challenger for one fold and horizon; boundaries asserted first."""
    test = B.select_test_rows(rows, plan)
    train = B.select_training_rows(rows, plan)
    B.assert_fold_boundaries(train, test, plan)
    started = time.perf_counter()
    meta = {"model": model, "fold": plan.fold, "horizon": plan.horizon, "test_rows": int(len(test)),
            "earliest_test_origin": plan.earliest_test_origin}
    if model == "ses":
        r = ses_predict(panel, test, plan, configs["ses"])
        meta.update({"train_rows": 0, "train_target_max": plan.earliest_test_origin, "n_inputs": 1,
                     "ses_warnings": r["warnings"], "alpha_median": float(r["alphas"]["alpha"].median())})
        extra = {"alphas": r["alphas"]}
    else:
        r = BOOSTED[model](train, test, configs[model])
        fit = score(train["target_units"], r["fit_pred"])
        meta.update({"train_rows": int(len(train)), "train_target_max": int(train["target_week"].max()),
                     "train_origin_max": int(train["origin_week"].max()), "n_inputs": r["n_inputs"],
                     "train_WAPE_pct": fit["WAPE_pct"]})
        extra = {"importance": r["importance"].assign(model=model, fold=plan.fold, horizon=plan.horizon)}
    meta["seconds"] = round(time.perf_counter() - started, 2)
    return {"pred": _prediction_frame(test, model, r["pred"]), "meta": meta, **extra}


# ------------------------------------------------------ integrity checks
def negative_control(model: str, rows: pd.DataFrame, plan: B.FoldPlan, configs=CONFIGS, seed: int = 42) -> dict:
    """Fit on training targets permuted within the training rows; compare with a constant predictor."""
    test = B.select_test_rows(rows, plan)
    train = B.select_training_rows(rows, plan).copy()
    B.assert_fold_boundaries(train, test, plan)
    rng = np.random.default_rng(seed)
    train["target_units"] = rng.permutation(train["target_units"].to_numpy())
    r = BOOSTED[model](train, test, configs[model])
    constant = np.full(len(test), train["target_units"].mean())
    nc, const = score(test["target_units"], r["pred"]), score(test["target_units"], constant)
    return {"model": model, "fold": plan.fold, "horizon": plan.horizon,
            "negative_control_WAPE_pct": nc["WAPE_pct"], "constant_mean_WAPE_pct": const["WAPE_pct"],
            "ratio": nc["WAPE_pct"] / const["WAPE_pct"], "passes": bool(nc["WAPE_pct"] >= 0.9 * const["WAPE_pct"])}


def inner_sanity(model: str, rows: pd.DataFrame, plan: B.FoldPlan, configs=CONFIGS) -> dict:
    """Inner block = last 4 training target weeks of the outer fold. Sanity only; selects nothing."""
    inner = B.Fold(f"{plan.fold}-inner", plan.train_target_max - 3, plan.train_target_max)
    ip = B.fold_plan(inner, plan.horizon)
    test = B.select_test_rows(rows, ip)
    train = B.select_training_rows(rows, ip)
    B.assert_fold_boundaries(train, test, ip)
    if test["target_week"].max() > plan.train_target_max or test["target_week"].max() >= plan.test_start:
        raise AssertionError("Inner validation reached outer test weeks")
    r = BOOSTED[model](train, test, configs[model])
    m, lw = score(test["target_units"], r["pred"]), score(test["target_units"], test["y_t0"])
    return {"model": model, "outer_fold": plan.fold, "horizon": plan.horizon,
            "inner_target_weeks": f"{inner.test_start}-{inner.test_end}", "inner_train_target_max": ip.train_target_max,
            "inner_WAPE_pct": m["WAPE_pct"], "inner_last_week_WAPE_pct": lw["WAPE_pct"],
            "passes": bool(m["WAPE_pct"] < lw["WAPE_pct"]), "used_for_selection": False}


def reproducibility(model: str, rows: pd.DataFrame, panel: pd.DataFrame, plan: B.FoldPlan, first: pd.DataFrame,
                    configs=CONFIGS, atol: float = 1e-6) -> dict:
    again = run_fold(model, rows, panel, plan, configs)["pred"]["forecast"].to_numpy()
    diff = float(np.max(np.abs(again - first["forecast"].to_numpy())))
    return {"model": model, "fold": plan.fold, "horizon": plan.horizon, "max_abs_difference": diff,
            "bit_identical": bool(diff == 0), "within_tolerance": bool(diff <= atol), "tolerance_units": atol}
