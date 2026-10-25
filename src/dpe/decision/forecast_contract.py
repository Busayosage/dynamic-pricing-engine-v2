"""Step 5B-1: the forecast output contract read by every downstream decision module.

Built from the protected out-of-sample predictions only (no retraining):
- H1: Random Forest, from the CP4 run (20261021-180522_rf_backtest)
- H4: four-week moving average, from the CP3 run (20261021-175029_baseline_backtest)

Two outputs, deliberately separate:
- forecast_contract.csv - DECISION-TIME fields only: everything a business user could have known at the forecast
  origin T (forecast, as-of uncertainty bounds, last observed sales, as-of reference price, known calendar).
- forecast_replay_evaluation.csv - REPLAY-ONLY fields: what happened in the target week (observed sales, errors,
  interval hit, discount status). These were not available when the decision would have been made.

Uncertainty (as of origin T): multiplicative bounds from the empirical distribution of actual/forecast for the same
model, horizon and product category, using only rows whose TARGET week is <= T (their actuals were observed by T).
At least MIN_ERROR_WEEKS distinct target weeks are required; otherwise the bounds are UNAVAILABLE (NaN) with an
explicit status - nothing is borrowed from other models or future periods.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pandas as pd

from dpe import config

CONTRACT_VERSION = "1.0"
UNIT = "units_sold_per_week"
MIN_ERROR_WEEKS = 4
QUANTILES = MappingProxyType({"lower": 0.10, "median": 0.50, "upper": 0.90})
CHRISTMAS_WEEKS = (51, 52)
DATASET_LABEL = "Apparently synthetic dataset; provenance unconfirmed"
STATUS = "RESEARCH_CANDIDATE_NOT_PRODUCTION"

METHODS = MappingProxyType({
    1: {"model_name": "random_forest", "model_role": "H1_research_candidate", "source_run_id": config.RF_BACKTEST_RUN_ID,
        "source_file": "predictions.csv",
        "description": "Random Forest, S0 features, 300 trees, depth 12, seed 42 (CP4); pooled backtest WAPE 25.92%"},
    4: {"model_name": "mean_4w", "model_role": "H4_research_candidate", "source_run_id": config.BASELINE_RUN_ID,
        "source_file": "baseline_predictions.csv",
        "description": "Mean of the four most recent observed weeks at the origin (CP3); pooled backtest WAPE 29.41%"},
})

# Known limitations, documented by the Step 3C-4D evaluations. Static text on every row: retrospective knowledge,
# NOT information derived from the target week.
LIMITATIONS = MappingProxyType({
    "SALES_NOT_DEMAND": "Recorded sales may not equal unconstrained demand (stockouts are not recorded).",
    "CHRISTMAS_BIAS": "Backtests under-forecast weeks 51-52 (Bakery and Meat by up to ~50%); bounds come from earlier "
                      "weeks and are likely too narrow there.",
    "DISCOUNT_WEEK_BIAS": "S0 forecasts do not know planned discounts; discounted weeks were under-forecast by ~15%.",
    "WEEKLY_GRANULARITY": "Weekly totals: no daily expiry or stockout timing can be inferred.",
    "SYNTHETIC_DATA": "Historical data appears synthetic; results describe this dataset, not real shoppers.",
    "RESEARCH_CANDIDATE": "Research candidate model; not approved for production (DECISION 17).",
})

# Decision-time contract: fixed column order (contract stability is tested).
CONTRACT_COLUMNS = [
    "contract_version", "forecast_run_id", "source_run_id", "model_name", "model_role", "forecast_method",
    "horizon_weeks", "scenario", "store_id", "product_id", "product_category", "region",
    "origin_week", "origin_date", "target_week", "target_date",
    "predicted_units", "lower_p10_units", "median_p50_units", "upper_p90_units",
    "uncertainty_status", "uncertainty_method", "uncertainty_error_target_weeks", "uncertainty_n_errors",
    "last_observed_units", "reference_price_asof", "target_holiday_calendar",
    "risk_flags", "limitation_codes", "unit", "provenance", "dataset_label", "status",
]
REPLAY_COLUMNS = [
    "forecast_run_id", "model_name", "horizon_weeks", "store_id", "product_id", "origin_week", "target_week",
    "observed_units", "error_units", "abs_error_units", "abs_pct_error", "within_p10_p90", "target_was_discounted",
    "availability",
]
FIELD_AVAILABILITY = {c: "DECISION_TIME" for c in CONTRACT_COLUMNS} | {
    c: "REPLAY_ONLY" for c in REPLAY_COLUMNS if c not in CONTRACT_COLUMNS}
REPLAY_ONLY_FIELDS = ("observed_units", "error_units", "abs_error_units", "abs_pct_error", "within_p10_p90",
                      "target_was_discounted")
PROVENANCE = ("OBSERVED: ids, dates, calendar, last_observed_units, prices (history <= origin); "
              "CALCULATED: predicted_units (protected out-of-sample run), bounds and reference_price_asof (as of origin)")
# Rows carry short codes; the full text is stored once in the manifest's code dictionary.
METHOD_CODES = MappingProxyType({1: "RF_S0_300T_D12_SEED42", 4: "MEAN_4W"})
UNCERTAINTY_CODE = "ASOF_RATIO_QUANTILES_P10_P50_P90_MIN4W_V1"
PROVENANCE_CODE = "PROV_V1"
DATASET_CODE = "SYNTHETIC_UNCONFIRMED"
UNCERTAINTY_TEXT = (f"Empirical actual/forecast ratio quantiles {dict(QUANTILES)} by model, horizon and product category, "
                    f"using only errors whose target week <= origin; at least {MIN_ERROR_WEEKS} target weeks required, "
                    "otherwise UNAVAILABLE.")


def code_dictionary() -> dict:
    return {"forecast_method": {METHOD_CODES[h]: m["description"] for h, m in METHODS.items()},
            "uncertainty_method": {UNCERTAINTY_CODE: UNCERTAINTY_TEXT},
            "provenance": {PROVENANCE_CODE: PROVENANCE},
            "dataset_label": {DATASET_CODE: DATASET_LABEL},
            "limitation_codes": dict(LIMITATIONS),
            "risk_flags": {"DISCOUNT_STATUS_UNKNOWN_S0": "Target-week discount plan unknown to S0 forecasts",
                           "CHRISTMAS_PERIOD": "Target week 51 or 52",
                           "HOLIDAY_TARGET_WEEK": "Regional holiday calendar flag set for the target week",
                           "HOLIDAY_AT_ORIGIN": "Origin week was a holiday (recent sales may be inflated)",
                           "UNCERTAINTY_UNAVAILABLE": "Fewer than 4 weeks of observed errors at the origin"}}


# ------------------------------------------------------------------ inputs
def load_protected_predictions() -> pd.DataFrame:
    """H1 RF rows (CP4) and H4 mean_4w rows (CP3) after verifying both runs' checksums."""
    from dpe.forecast.acceptance import _verify_run_checksums

    parts = []
    for h, m in METHODS.items():
        _verify_run_checksums(m["source_run_id"])
        p = pd.read_csv(config.OUTPUT_ROOT / m["source_run_id"] / m["source_file"], parse_dates=["origin_date", "target_date"])
        parts.append(p[(p["model"] == m["model_name"]) & (p["horizon"] == h)])
    return pd.concat(parts, ignore_index=True)


# -------------------------------------------------------------- calculations
def asof_reference_price(panel: pd.DataFrame) -> pd.DataFrame:
    """Per series and week T: median of the implied pre-discount price Price / (1 - d) over weeks <= T."""
    p = panel[["Store_ID", "Product_ID", "week_index", "Price", "Discount_Percent"]].sort_values(
        ["Store_ID", "Product_ID", "week_index"]).copy()
    p["implied"] = p["Price"] / (1 - p["Discount_Percent"] / 100)
    p["reference_price_asof"] = (p.groupby(["Store_ID", "Product_ID"])["implied"]
                                 .transform(lambda s: s.expanding().median()))
    return p[["Store_ID", "Product_ID", "week_index", "reference_price_asof"]]


def asof_uncertainty(predictions: pd.DataFrame, origins_by_horizon: dict[int, list[int]]) -> pd.DataFrame:
    """Ratio quantiles per (horizon, origin, category) from errors with target_week <= origin only."""
    e = predictions.assign(ratio=predictions["actual"] / predictions["forecast"])
    rows = []
    for h, origins in origins_by_horizon.items():
        eh = e[e["horizon"] == h]
        for T in sorted(set(origins)):
            known = eh[eh["target_week"] <= T]
            for cat in sorted(eh["Product_Category"].unique()):
                k = known[known["Product_Category"] == cat]
                weeks = sorted(k["target_week"].unique())
                base = {"horizon": h, "origin_week": T, "Product_Category": cat, "uncertainty_n_errors": int(len(k)),
                        "uncertainty_error_target_weeks": f"{weeks[0]}-{weeks[-1]}" if weeks else ""}
                if len(weeks) >= MIN_ERROR_WEEKS:
                    q = k["ratio"].quantile(list(QUANTILES.values())).to_numpy()
                    rows.append({**base, "q_lower": q[0], "q_median": q[1], "q_upper": q[2], "uncertainty_status": "AVAILABLE"})
                else:
                    rows.append({**base, "q_lower": np.nan, "q_median": np.nan, "q_upper": np.nan,
                                 "uncertainty_status": "UNAVAILABLE_INSUFFICIENT_HISTORY"})
    return pd.DataFrame(rows)


def _risk_flags(row) -> str:
    flags = ["DISCOUNT_STATUS_UNKNOWN_S0"]  # S0 forecasts never know the target-week discount plan
    if row["target_week"] in CHRISTMAS_WEEKS:
        flags.append("CHRISTMAS_PERIOD")
    if row["target_holiday_calendar"] == 1:
        flags.append("HOLIDAY_TARGET_WEEK")
    if row["origin_holiday"] == 1:
        flags.append("HOLIDAY_AT_ORIGIN")
    if row["uncertainty_status"] != "AVAILABLE":
        flags.append("UNCERTAINTY_UNAVAILABLE")
    return "|".join(flags)


def build_contract(predictions: pd.DataFrame, panel: pd.DataFrame, forecast_run_id: str) -> dict[str, pd.DataFrame]:
    """Decision-time contract and replay-only evaluation table from protected predictions and the panel."""
    base_cols = ["Store_ID", "Product_ID", "origin_week", "origin_date", "target_week", "target_date", "horizon",
                 "model", "actual", "forecast"]
    pred = predictions[base_cols].copy()
    # Static attributes (known at every origin) and the target-week discount status (REPLAY ONLY) from the panel,
    # attached identically for both horizons.
    static = panel.drop_duplicates(["Store_ID", "Product_ID"])[["Store_ID", "Product_ID", "Product_Category", "Region"]]
    pred = pred.merge(static, on=["Store_ID", "Product_ID"], how="left", validate="many_to_one")
    disc = panel[["Store_ID", "Product_ID", "week_index", "Discount_Percent"]].rename(columns={"week_index": "target_week"})
    pred = pred.merge(disc, on=["Store_ID", "Product_ID", "target_week"], how="left", validate="many_to_one")
    pred["target_discounted"] = pred.pop("Discount_Percent") > 0
    origins = {h: sorted(g["origin_week"].unique()) for h, g in pred.groupby("horizon")}
    unc = asof_uncertainty(pred, origins)
    ref = asof_reference_price(panel)
    cal = panel[["Store_ID", "Product_ID", "week_index", "Holiday_Flag", "Units_Sold"]]
    c = pred.merge(unc, on=["horizon", "origin_week", "Product_Category"], how="left", validate="many_to_one")
    c = c.merge(ref.rename(columns={"week_index": "origin_week"}), on=["Store_ID", "Product_ID", "origin_week"],
                how="left", validate="many_to_one")
    c = c.merge(cal.rename(columns={"week_index": "origin_week", "Holiday_Flag": "origin_holiday",
                                    "Units_Sold": "last_observed_units"}),
                on=["Store_ID", "Product_ID", "origin_week"], how="left", validate="many_to_one")
    c = c.merge(cal[["Store_ID", "Product_ID", "week_index", "Holiday_Flag"]].rename(
        columns={"week_index": "target_week", "Holiday_Flag": "target_holiday_calendar"}),
        on=["Store_ID", "Product_ID", "target_week"], how="left", validate="many_to_one")
    c["predicted_units"] = c["forecast"].astype(float)
    for name, q in (("lower_p10_units", "q_lower"), ("median_p50_units", "q_median"), ("upper_p90_units", "q_upper")):
        c[name] = c["predicted_units"] * c[q]
    c["risk_flags"] = c.apply(_risk_flags, axis=1)
    meta = {h: METHODS[h] for h in METHODS}
    out = pd.DataFrame({
        "contract_version": CONTRACT_VERSION, "forecast_run_id": forecast_run_id,
        "source_run_id": c["horizon"].map(lambda h: meta[h]["source_run_id"]),
        "model_name": c["model"], "model_role": c["horizon"].map(lambda h: meta[h]["model_role"]),
        "forecast_method": c["horizon"].map(METHOD_CODES),
        "horizon_weeks": c["horizon"].astype(int), "scenario": "S0",
        "store_id": c["Store_ID"].astype(int), "product_id": c["Product_ID"].astype(int),
        "product_category": c["Product_Category"], "region": c["Region"],
        "origin_week": c["origin_week"].astype(int), "origin_date": c["origin_date"].dt.strftime("%Y-%m-%d"),
        "target_week": c["target_week"].astype(int), "target_date": c["target_date"].dt.strftime("%Y-%m-%d"),
        "predicted_units": c["predicted_units"], "lower_p10_units": c["lower_p10_units"],
        "median_p50_units": c["median_p50_units"], "upper_p90_units": c["upper_p90_units"],
        "uncertainty_status": c["uncertainty_status"],
        "uncertainty_method": UNCERTAINTY_CODE,
        "uncertainty_error_target_weeks": c["uncertainty_error_target_weeks"],
        "uncertainty_n_errors": c["uncertainty_n_errors"].astype(int),
        "last_observed_units": c["last_observed_units"].astype(int),
        "reference_price_asof": c["reference_price_asof"].round(4),
        "target_holiday_calendar": c["target_holiday_calendar"].astype(int),
        "risk_flags": c["risk_flags"], "limitation_codes": "|".join(LIMITATIONS), "unit": UNIT,
        "provenance": PROVENANCE_CODE, "dataset_label": DATASET_CODE, "status": STATUS,
    })[CONTRACT_COLUMNS]
    out = out.sort_values(["horizon_weeks", "store_id", "product_id", "origin_week"]).reset_index(drop=True)

    r = c.sort_values(["horizon", "Store_ID", "Product_ID", "origin_week"]).reset_index(drop=True)
    within = ((r["actual"] >= r["lower_p10_units"]) & (r["actual"] <= r["upper_p90_units"])).astype("boolean")
    within[r["uncertainty_status"] != "AVAILABLE"] = pd.NA
    replay = pd.DataFrame({
        "forecast_run_id": forecast_run_id, "model_name": r["model"], "horizon_weeks": r["horizon"].astype(int),
        "store_id": r["Store_ID"].astype(int), "product_id": r["Product_ID"].astype(int),
        "origin_week": r["origin_week"].astype(int), "target_week": r["target_week"].astype(int),
        "observed_units": r["actual"].astype(int), "error_units": r["predicted_units"] - r["actual"],
        "abs_error_units": (r["predicted_units"] - r["actual"]).abs(),
        "abs_pct_error": 100 * (r["predicted_units"] - r["actual"]).abs() / r["actual"],
        "within_p10_p90": within,
        "target_was_discounted": r["target_discounted"].astype(bool),
        "availability": "REPLAY_ONLY - not available at the forecast origin",
    })[REPLAY_COLUMNS]
    return {"contract": out, "replay": replay, "uncertainty": unc}


# -------------------------------------------------------------- validation
def validate_contract(contract: pd.DataFrame, replay: pd.DataFrame | None = None) -> dict:
    """Raise ValueError on any contract violation; return a summary."""
    errs = []
    if list(contract.columns) != CONTRACT_COLUMNS:
        errs.append("columns differ from CONTRACT_COLUMNS")
    leaked = set(REPLAY_ONLY_FIELDS) & set(contract.columns)
    if leaked:
        errs.append(f"replay-only fields in contract: {sorted(leaked)}")
    key = ["model_name", "horizon_weeks", "store_id", "product_id", "origin_week"]
    if contract.duplicated(subset=key).any():
        errs.append("duplicate keys")
    if not contract["horizon_weeks"].isin(list(METHODS)).all():
        errs.append("horizon not in {1, 4}")
    approved = contract["horizon_weeks"].map(lambda h: METHODS[h]["model_name"] if h in METHODS else None)
    if not (contract["model_name"] == approved).all():
        errs.append("model does not match the approved method for its horizon")
    if (contract["target_week"] != contract["origin_week"] + contract["horizon_weeks"]).any():
        errs.append("target_week != origin_week + horizon")
    od, td = pd.to_datetime(contract["origin_date"]), pd.to_datetime(contract["target_date"])
    if (od.dt.dayofweek != 0).any() or (td.dt.dayofweek != 0).any():
        errs.append("dates must be Mondays")
    if ((td - od) != pd.to_timedelta(contract["horizon_weeks"] * 7, unit="D")).any():
        errs.append("target_date != origin_date + horizon weeks")
    if not (np.isfinite(contract["predicted_units"]).all() and (contract["predicted_units"] >= 0).all()):
        errs.append("predicted_units must be finite and >= 0")
    bounds = ["lower_p10_units", "median_p50_units", "upper_p90_units"]
    avail = contract["uncertainty_status"] == "AVAILABLE"
    if contract.loc[avail, bounds].isna().any().any() or not contract.loc[~avail, bounds].isna().all().all():
        errs.append("bounds present iff uncertainty_status == AVAILABLE")
    b = contract.loc[avail, bounds]
    if ((b["lower_p10_units"] > b["median_p50_units"]) | (b["median_p50_units"] > b["upper_p90_units"])
            | (b["lower_p10_units"] < 0)).any():
        errs.append("bounds must be >= 0 and monotone")
    if not contract["uncertainty_status"].isin(["AVAILABLE", "UNAVAILABLE_INSUFFICIENT_HISTORY"]).all():
        errs.append("unknown uncertainty_status")
    required = [c for c in CONTRACT_COLUMNS if c not in bounds]
    if contract[required].isna().any().any():
        errs.append(f"missing values in {contract[required].columns[contract[required].isna().any()].tolist()}")
    if not (contract["unit"] == UNIT).all() or not (contract["status"] == STATUS).all():
        errs.append("unit/status must be constant")
    if not (contract["dataset_label"] == DATASET_CODE).all():
        errs.append("dataset label missing")
    codes = code_dictionary()
    for col in ("forecast_method", "uncertainty_method", "provenance"):
        if not contract[col].isin(list(codes[col])).all():
            errs.append(f"{col} has codes missing from the code dictionary")
    flags = set("|".join(contract["risk_flags"]).split("|")) | set("|".join(contract["limitation_codes"]).split("|"))
    if not flags <= set(codes["risk_flags"]) | set(codes["limitation_codes"]):
        errs.append("unknown risk or limitation codes")
    if replay is not None:
        jk = ["model_name", "horizon_weeks", "store_id", "product_id", "origin_week", "target_week"]
        j = contract[jk].merge(replay[jk], on=jk, how="outer", indicator=True)
        if not (j["_merge"] == "both").all():
            errs.append("replay rows do not match contract rows")
    if errs:
        raise ValueError("Forecast contract invalid: " + "; ".join(errs))
    return {"rows": int(len(contract)),
            "rows_by_horizon": {f"H{h}": int(n) for h, n in contract.groupby("horizon_weeks").size().items()},
            "unavailable_bounds_by_horizon": {f"H{h}": int((g["uncertainty_status"] != "AVAILABLE").sum())
                                              for h, g in contract.groupby("horizon_weeks")}}


def coverage_summary(contract: pd.DataFrame, replay: pd.DataFrame) -> pd.DataFrame:
    """Replay-only evaluation of the p10-p90 interval (where available)."""
    j = replay.merge(contract[["horizon_weeks", "store_id", "product_id", "origin_week", "product_category",
                               "uncertainty_status"]], on=["horizon_weeks", "store_id", "product_id", "origin_week"])
    j = j[j["uncertainty_status"] == "AVAILABLE"].copy()
    j["within"] = j["within_p10_p90"].astype(float)
    pooled = j.groupby("horizon_weeks").agg(rows=("within", "size"), coverage_p10_p90=("within", "mean")).reset_index()
    pooled["product_category"] = "ALL"
    by_cat = (j.groupby(["horizon_weeks", "product_category"]).agg(rows=("within", "size"),
                                                                   coverage_p10_p90=("within", "mean")).reset_index())
    xmas = (j[j["target_week"].isin(CHRISTMAS_WEEKS)].groupby("horizon_weeks")
            .agg(rows=("within", "size"), coverage_p10_p90=("within", "mean")).reset_index())
    xmas["product_category"] = "ALL (weeks 51-52)"
    return pd.concat([pooled, by_cat, xmas], ignore_index=True)[["horizon_weeks", "product_category", "rows",
                                                                 "coverage_p10_p90"]]


# --------------------------------------------------------------------- run
def run_forecast_contract(run_id: str | None = None, predictions: pd.DataFrame | None = None,
                          panel: pd.DataFrame | None = None) -> Path:
    from dpe.eda.outputs import save_json, save_table
    from dpe.forecast.panel import load_verified_panel

    panel_info = {"note": "injected panel (tests)"}
    if panel is None:
        panel, panel_info = load_verified_panel()
    predictions = predictions if predictions is not None else load_protected_predictions()
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_forecast_contract"
    r = build_contract(predictions, panel, run_id)
    summary = validate_contract(r["contract"], r["replay"])
    cov = coverage_summary(r["contract"], r["replay"])
    run_dir = config.new_run_dir(run_id)
    save_table(r["contract"], run_dir / "forecast_contract.csv")
    save_table(r["replay"], run_dir / "forecast_replay_evaluation.csv")
    save_table(r["uncertainty"], run_dir / "uncertainty_quantiles_asof.csv")
    save_table(cov, run_dir / "interval_coverage_replay.csv")
    save_json({
        "contract_version": CONTRACT_VERSION, "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "step": "5B-1 forecast contract (no retraining; built from protected out-of-sample predictions)",
        "methods": {f"H{h}": dict(m) for h, m in METHODS.items()},
        "sources_checksum_verified": [m["source_run_id"] for m in METHODS.values()],
        "panel": panel_info, "unit": UNIT,
        "uncertainty": {"method": "empirical actual/forecast ratio quantiles by model, horizon, category",
                        "quantiles": dict(QUANTILES), "min_error_weeks": MIN_ERROR_WEEKS,
                        "rule": "only errors whose target week <= origin; otherwise UNAVAILABLE (NaN), never borrowed"},
        "reference_price_asof": "median of Price / (1 - Discount_Percent/100) over weeks <= origin, per store-product",
        "field_availability": FIELD_AVAILABILITY,
        "code_dictionary": code_dictionary(),
        "limitations": dict(LIMITATIONS),
        "validation": summary,
        "dataset_label": DATASET_LABEL, "status": STATUS,
        "contract_sha256": hashlib.sha256((run_dir / "forecast_contract.csv").read_bytes()).hexdigest(),
    }, run_dir / "contract_manifest.json")
    return run_dir
