"""CP2: leakage-safe ("as-of") features for one-week-ahead (H1) and four-week-ahead (H4) forecasts.

Every forecast row has an explicit origin week T (the last week with observed sales) and target
week T + h. Feature values come from three separate inputs, so the information boundary is
structural rather than a convention:

- history: panel rows dated on or before the origin. Every history feature is a backward-looking
  window ending at T, so it cannot read weeks after T.
- calendar: the known-in-advance regional holiday calendar and month of the target week.
- plans: target-week values (discount, marketing, price, weather) used ONLY in scenarios S1-S3.

The same history definitions serve both horizons (a direct strategy: one model per horizon, no
recursion on predictions). Origins without MIN_HISTORY_WEEKS of observed weeks are excluded; missing
history is never filled with zero. Wastage is never read. Store_ID and Product_ID are carried as
keys and enter models only as one-hot identity columns, never as continuous numbers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dpe.forecast.panel import SERIES_KEYS, STATIC_ATTRIBUTES, validate_panel
from dpe.forecast.scenarios import get_scenario

MIN_HISTORY_WEEKS = 8
HORIZONS = {"H1": 1, "H4": 4}
EWM_ALPHA = 0.3

ROW_ID_COLUMNS = ["Store_ID", "Product_ID", "origin_week", "origin_date", "target_week", "target_date",
                  "horizon", "scenario"]
HISTORY_FEATURES = [
    "y_t0", "y_tm1", "y_tm2", "y_tm3", "y_tm7",
    "mean_4", "std_4", "min_4", "max_4", "mean_8", "std_8", "min_8", "max_8",
    "ewm_mean", "expanding_mean", "trend_4v4", "ratio_t0_mean_8",
    "disc_t0", "disc_tm1", "disc_share_4", "undisc_mean_8", "holiday_t0",
    "prod_total_t0", "prod_total_mean_4", "store_cat_mean_4", "series_share_8",
]
STATIC_NUMERIC = ["Shelf_Life_Days", "Store_Size", "Cold_Storage_Capacity", "Lead_Time_Days"]
STATIC_CATEGORICAL = ["Product_ID", "Store_ID", "Product_Category", "Region"]  # one-hot only
CALENDAR_FEATURES = ["target_month", "target_holiday", "target_national_holiday_share"]
# Allowed alongside features but never model inputs: the label and the backtest fold name.
METADATA_COLUMNS = ("target_units", "fold")

# Never allowed as a model input, in any scenario.
FORBIDDEN_ALWAYS = ("Wastage_Units", "waste", "Week_Number", "week_of_year", "weekofyear", "Supplier_ID")
# Target-week commercial/weather values: allowed only as a scenario's declared inputs.
TARGET_WEEK_VALUE_COLUMNS = ("Price", "Discount_Percent", "Marketing_Spend", "Avg_Temperature", "Rainfall")


def feature_columns(scenario: str = "S0") -> list[str]:
    """The explicit, ordered list of feature columns (before one-hot encoding) for a scenario."""
    extra = list(get_scenario(scenario).target_week_inputs)
    return HISTORY_FEATURES + STATIC_NUMERIC + STATIC_CATEGORICAL + CALENDAR_FEATURES + extra


def _rolling(grouped, window: int, how: str) -> pd.Series:
    r = getattr(grouped.rolling(window, min_periods=window), how)()
    return r.reset_index(level=list(range(r.index.nlevels - 1)), drop=True)


def history_features(history: pd.DataFrame) -> pd.DataFrame:
    """One row per series and origin week; each value uses weeks <= that origin only."""
    validate_panel(history)  # complete grid of consecutive weeks: rolling windows count real weeks
    h = history.sort_values(SERIES_KEYS + ["week_index"]).reset_index(drop=True)
    g = h.groupby(SERIES_KEYS, sort=False)
    y = h["Units_Sold"].astype(float)
    gy = y.groupby([h[k] for k in SERIES_KEYS], sort=False)

    out = h[SERIES_KEYS + ["week_index", "WeekDate"]].rename(
        columns={"week_index": "origin_week", "WeekDate": "origin_date"})
    out["y_t0"] = y
    for k in (1, 2, 3, 7):
        out[f"y_tm{k}"] = gy.shift(k)
    for w in (4, 8):
        for how in ("mean", "std", "min", "max"):
            out[f"{how}_{w}"] = _rolling(gy, w, how)
    out["ewm_mean"] = gy.transform(lambda s: s.ewm(alpha=EWM_ALPHA, adjust=False).mean())
    out["expanding_mean"] = gy.cumsum() / (g.cumcount() + 1)
    prev_4 = (8 * out["mean_8"] - 4 * out["mean_4"]) / 4  # mean of weeks T-7..T-4
    out["trend_4v4"] = out["mean_4"] - prev_4
    out["ratio_t0_mean_8"] = out["y_t0"] / out["mean_8"]

    disc = h["Discount_Percent"].astype(float)
    gd = disc.groupby([h[k] for k in SERIES_KEYS], sort=False)
    out["disc_t0"] = disc
    out["disc_tm1"] = gd.shift(1)
    out["disc_share_4"] = _rolling((disc > 0).astype(float).groupby([h[k] for k in SERIES_KEYS], sort=False), 4, "mean")
    undisc = disc == 0
    u_sum = _rolling(y.where(undisc, 0.0).groupby([h[k] for k in SERIES_KEYS], sort=False), 8, "sum")
    u_cnt = _rolling(undisc.astype(float).groupby([h[k] for k in SERIES_KEYS], sort=False), 8, "sum")
    # Fallback uses real history (8-week mean), never a fabricated value.
    out["undisc_mean_8"] = (u_sum / u_cnt).where(u_cnt > 0, out["mean_8"])
    out["holiday_t0"] = h["Holiday_Flag"].astype(float)

    prod = h.groupby(["Product_ID", "week_index"], sort=True)["Units_Sold"].sum().astype(float).rename("prod_total_t0")
    prod = prod.reset_index()
    pg = prod.groupby("Product_ID", sort=False)["prod_total_t0"]
    prod["prod_total_mean_4"] = _rolling(pg, 4, "mean")
    prod["prod_total_sum_8"] = _rolling(pg, 8, "sum")
    sc = (h.groupby(["Store_ID", "Product_Category", "week_index"], sort=True)["Units_Sold"].sum().astype(float)
          .rename("store_cat_total").reset_index())
    sc["store_cat_mean_4"] = _rolling(sc.groupby(["Store_ID", "Product_Category"], sort=False)["store_cat_total"], 4, "mean")

    out = out.merge(prod.rename(columns={"week_index": "origin_week"}), on=["Product_ID", "origin_week"], how="left")
    out = out.merge(h[SERIES_KEYS + ["week_index", "Product_Category"]].rename(columns={"week_index": "origin_week"}),
                    on=SERIES_KEYS + ["origin_week"], how="left")
    out = out.merge(sc[["Store_ID", "Product_Category", "week_index", "store_cat_mean_4"]]
                    .rename(columns={"week_index": "origin_week"}),
                    on=["Store_ID", "Product_Category", "origin_week"], how="left")
    out["series_share_8"] = (out["mean_8"] * 8) / out["prod_total_sum_8"]
    return out.drop(columns=["prod_total_sum_8", "Product_Category"])


def build_features(history: pd.DataFrame, calendar: pd.DataFrame, horizon: int, scenario: str = "S0",
                   plans: pd.DataFrame | None = None, origins=None) -> pd.DataFrame:
    """Feature rows for forecasts made at each eligible origin T for target T + horizon.

    history  : panel rows observed so far (weeks <= the latest origin of interest).
    calendar : known-in-advance calendar (dpe.forecast.panel.holiday_calendar), covering target weeks.
    plans    : target-week values for scenario inputs (required for S1-S3; ignored for S0).
    origins  : optional subset of origin weeks to return.
    Origins whose target week is not on the calendar are dropped (the target is unknown).
    """
    if int(horizon) != horizon or horizon < 1:
        raise ValueError(f"horizon must be a positive whole number of weeks, got {horizon!r}")
    sc = get_scenario(scenario)
    hist = history_features(history)
    hist = hist[hist["origin_week"] >= MIN_HISTORY_WEEKS]
    if origins is not None:
        hist = hist[hist["origin_week"].isin(list(origins))]
    if hist[HISTORY_FEATURES].isna().any().any():
        bad = hist[HISTORY_FEATURES].columns[hist[HISTORY_FEATURES].isna().any()].tolist()
        raise ValueError(f"Eligible origins have missing history features {bad}; history is not filled")

    static = history.drop_duplicates(SERIES_KEYS)[SERIES_KEYS + STATIC_ATTRIBUTES]
    f = hist.merge(static, on=SERIES_KEYS, how="left", validate="many_to_one")
    f["horizon"] = int(horizon)
    f["scenario"] = scenario
    f["target_week"] = f["origin_week"] + int(horizon)
    f["target_date"] = f["origin_date"] + pd.Timedelta(weeks=int(horizon))

    cal = calendar.rename(columns={"week_index": "target_week", "WeekDate": "calendar_date", "month": "target_month",
                                   "Holiday_Flag": "target_holiday",
                                   "national_holiday_share": "target_national_holiday_share"})
    f = f.merge(cal[["Region", "target_week", "calendar_date"] + CALENDAR_FEATURES],
                on=["Region", "target_week"], how="inner", validate="many_to_one")
    if (f["calendar_date"] != f["target_date"]).any():
        raise ValueError("Calendar dates do not match origin date + horizon")
    f = f.drop(columns="calendar_date")

    if sc.target_week_inputs:
        if plans is None:
            raise ValueError(f"Scenario {scenario} needs target-week plans: {sorted(sc.target_week_inputs.values())}")
        p = plans[SERIES_KEYS + ["week_index"] + sorted(set(sc.target_week_inputs.values()))].copy()
        p = p.rename(columns={"week_index": "target_week"})
        for feat, col in sc.target_week_inputs.items():
            p[feat] = p[col]
        n = len(f)
        f = f.merge(p[SERIES_KEYS + ["target_week"] + list(sc.target_week_inputs)],
                    on=SERIES_KEYS + ["target_week"], how="inner", validate="one_to_one")
        if len(f) != n:
            raise ValueError(f"Scenario {scenario}: plans missing for {n - len(f)} forecast rows")

    f[["target_month", "target_holiday"]] = f[["target_month", "target_holiday"]].astype(int)
    cols = ROW_ID_COLUMNS + [c for c in feature_columns(scenario) if c not in ROW_ID_COLUMNS]
    out = f[cols].sort_values(["Store_ID", "Product_ID", "origin_week"]).reset_index(drop=True)
    check_feature_frame(out, scenario)
    return out


def attach_target(features: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """Add the actual units of the target week as `target_units` (a label, never a feature)."""
    t = panel[SERIES_KEYS + ["week_index", "Units_Sold"]].rename(
        columns={"week_index": "target_week", "Units_Sold": "target_units"})
    out = features.merge(t, on=SERIES_KEYS + ["target_week"], how="left", validate="one_to_one")
    if out["target_units"].isna().any():
        raise ValueError(f"{int(out['target_units'].isna().sum())} rows have no observed target week")
    return out


def check_feature_frame(features: pd.DataFrame, scenario: str) -> None:
    """Raise if identifiers are missing/duplicated or a forbidden/undeclared column is present."""
    missing = [c for c in ROW_ID_COLUMNS if c not in features.columns]
    if missing:
        raise ValueError(f"Feature frame is missing identifier columns {missing}")
    if features.duplicated(subset=["Store_ID", "Product_ID", "origin_week", "horizon", "scenario"]).any():
        raise ValueError("Duplicate forecast rows")
    expected = set(ROW_ID_COLUMNS) | set(feature_columns(scenario)) | set(METADATA_COLUMNS)
    unexpected = [c for c in features.columns if c not in expected]
    if unexpected:
        raise ValueError(f"Undeclared columns in feature frame: {unexpected}")
    for c in features.columns:
        if any(bad.lower() in c.lower() for bad in FORBIDDEN_ALWAYS):
            raise ValueError(f"Forbidden column in feature frame: {c}")
        if c in TARGET_WEEK_VALUE_COLUMNS:
            raise ValueError(f"Raw weekly value column {c} must not appear; scenario inputs are renamed plan_*/oracle_*")
    if (features["target_week"] != features["origin_week"] + features["horizon"]).any():
        raise ValueError("target_week must equal origin_week + horizon")


def static_categories(panel: pd.DataFrame) -> dict[str, list]:
    """Fixed category lists for one-hot encoding (from the full static attribute table)."""
    return {c: sorted(panel[c].unique().tolist()) for c in STATIC_CATEGORICAL}


def model_matrix(features: pd.DataFrame, scenario: str, categories: dict[str, list]) -> pd.DataFrame:
    """Numeric model inputs in a fixed column order. Identifiers become one-hot columns only."""
    check_feature_frame(features, scenario)
    cols = feature_columns(scenario)
    numeric = [c for c in cols if c not in STATIC_CATEGORICAL]
    X = features[numeric].astype(float)
    parts = [X]
    for c in STATIC_CATEGORICAL:
        cats = categories[c]
        unknown = set(features[c].unique()) - set(cats)
        if unknown:
            raise ValueError(f"Unknown {c} values {sorted(unknown)[:5]}")
        dummies = pd.get_dummies(pd.Categorical(features[c], categories=cats), prefix=f"{c}=", prefix_sep="",
                                 dtype=float)
        dummies.index = features.index
        parts.append(dummies)
    X = pd.concat(parts, axis=1)
    if not np.isfinite(X.to_numpy()).all():
        raise ValueError("Model matrix has missing or infinite values")
    for c in ("Store_ID", "Product_ID", "Supplier_ID"):
        if c in X.columns:
            raise ValueError(f"Identifier {c} must not be a continuous model input")
    return X
