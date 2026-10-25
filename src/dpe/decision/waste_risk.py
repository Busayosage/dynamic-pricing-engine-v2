"""Stage 6B: waste-risk intelligence (advisory, read-only, deterministic).

Classifies every simulated decision (store x product x decision week) by the projected expiry of stock ALREADY ON
HAND, using only saved outputs: the protected comparison run (decisions, deliveries, weekly outcomes, review cases),
the protected forecast contract and the verified panel (recorded wastage). Nothing is simulated, written, ordered,
priced, approved or escalated. Design: docs/STAGE_6A_WASTE_RISK_DESIGN.md (decisions U1-U7); thresholds from assumption
set v3 (DRAFT).

Classification (first match wins):
  INSUFFICIENT_INFORMATION  forecast bounds unavailable, arrangement UNSUPPORTED, projection missing, or p50 <= 0 with no
                            projected expiry (the share is undefined: never classified Low because of that)
  HIGH                      projected existing-stock expiry >= high% of typical weekly p50, or p50 <= 0 with positive
                            projected expiry (every unit is a large share of zero expected sales)
  MODERATE                  >= moderate% and < high%
  LOW                       < moderate%
The planned ordering buffer, low-sales exposure, recorded wastage and recent simulated expiry are CONTEXT ONLY.

The projection used is the common indicator `std_existing_expiry_projection_units` (5B-3a calculator: p50 depletion to
arrival, then planning-rate depletion), identical in rule for every policy; for P2 it equals the recommendation field.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

CATEGORIES = ("HIGH", "MODERATE", "LOW", "INSUFFICIENT_INFORMATION")
CATEGORY_LABELS = {"HIGH": "High expiry risk", "MODERATE": "Moderate expiry risk", "LOW": "Low expiry risk",
                   "INSUFFICIENT_INFORMATION": "Insufficient information"}
INVESTIGATION = {
    "HIGH": ("Check dates on the shelf before the investigate-by day, and consider with the store team whether the next "
             "order should be smaller. (A markdown review is not available yet.)"),
    "MODERATE": "Check stock rotation and dates at the next delivery.",
    "LOW": "No action needed beyond routine checks.",
    "INSUFFICIENT_INFORMATION": ("The forecast range is missing, typical demand is zero, or the delivery arrangement is "
                                 "unsupported — judge this line manually."),
}
REASONS = {
    "CURRENT_STOCK_PROJECTED_TO_EXPIRE": "Stock already in store may go out of date before it sells",
    "ZERO_TYPICAL_DEMAND": "Typical demand forecast is zero, so any unsold stock is at risk",
    "BATCH_LAST_DAY_BEFORE_NEXT_DELIVERY": "A batch reaches its last sellable day before the next delivery arrives",
    "FRESH_SHORT_SHELF_LIFE": "Fresh product with only a few sellable days",
    "LONGER_RANGE_FORECAST_LOWER": "The longer-range forecast is noticeably lower than next week's",
    "HOLIDAY_OR_CHRISTMAS_WEEK": "Holiday or Christmas week — demand is harder to predict",
    "RECENT_SIMULATED_EXPIRY": "Stock of this line went out of date in the replay in recent weeks (simulated)",
    "FORECAST_RANGE_MISSING": "No forecast range yet (too little history)",
    "UNSUPPORTED_ARRANGEMENT": "Supplier cannot deliver in time (unsupported arrangement)",
    "NO_PROJECTION": "No expiry projection was saved for this decision",
}
PROVENANCE = {
    "projected_existing_expiry_units": "SIMULATED stock × FORECAST demand — planning projection, not a prediction",
    "projected_expiry_pct_of_p50": "calculated from the projection and the FORECAST p50",
    "typical_weekly_demand_p50": "FORECAST (protected contract, 1 week ahead)",
    "planned_buffer_units": "SIMULATED order × FORECAST p50 × ASSUMED service target — context only",
    "low_sales_buffer_units": "SIMULATED order × FORECAST p10 — context only",
    "recorded_wastage_pct_4w": "RECORDED historical wastage (apparently synthetic dataset) — context only",
    "recent_simulated_expiry_pct_4w": "SIMULATED replay outcome — context only",
    "investigate_by_day": "SIMULATED delivery dates (units left per batch are not saved)",
    "remaining_life_days": "RECORDED shelf life minus ASSUMED transit age",
    "category": "ASSUMED thresholds (assumption set v3, DRAFT)",
}
STATUS = "ADVISORY_HYPOTHETICAL"
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
TOL = 0.5  # half a unit: projections below this are treated as zero


def day_label(day) -> str | None:
    if day is None or (isinstance(day, float) and math.isnan(day)):
        return None
    d = int(day)
    return f"{WEEKDAYS[(d - 1) % 7]}, week {(d - 1) // 7 + 1}"


def classify(projected_units, p50, high_pct: float, moderate_pct: float, bounds_available: bool = True,
             arrangement_supported: bool = True) -> tuple[str, float | None]:
    """(category, share of weekly p50 in %). The share is None whenever it is undefined."""
    if not bounds_available or not arrangement_supported or projected_units is None or \
            (isinstance(projected_units, float) and math.isnan(projected_units)):
        return "INSUFFICIENT_INFORMATION", None
    units = max(0.0, float(projected_units))
    if p50 is None or (isinstance(p50, float) and math.isnan(p50)):
        return "INSUFFICIENT_INFORMATION", None
    if float(p50) <= 0:
        return ("HIGH" if units > TOL else "INSUFFICIENT_INFORMATION"), None
    share = 100 * units / float(p50)
    if share >= high_pct:
        return "HIGH", share
    if share >= moderate_pct:
        return "MODERATE", share
    return "LOW", share


# --------------------------------------------------------------------------------------------- context
def planned_buffer(deliveries: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """Per order: units above typical (p50) and low (p10) demand within each delivery's own sellable days."""
    o = deliveries[deliveries["kind"] == "ORDER"].merge(
        decisions[["order_id", "median_p50_units", "lower_p10_units"]], on="order_id", how="inner")
    life = o["expiry_day"] - o["arrival_day"] + 1
    o = o.assign(buffer=(o["ordered_units"] - o["median_p50_units"] / 7 * life).clip(lower=0),
                 low=(o["ordered_units"] - o["lower_p10_units"] / 7 * life).clip(lower=0))
    return o.groupby("order_id")[["buffer", "low"]].sum().rename(columns={"buffer": "planned_buffer_units",
                                                                          "low": "low_sales_buffer_units"})


def recorded_wastage(panel: pd.DataFrame, window: int) -> pd.DataFrame:
    """As-of recorded wastage %: weeks origin-window+1 .. origin (never a later week)."""
    p = panel.sort_values(["Store_ID", "Product_ID", "week_index"])
    g = p.groupby(["Store_ID", "Product_ID"])
    w = g["Wastage_Units"].transform(lambda s: s.rolling(window, min_periods=window).sum())
    s = g["Units_Sold"].transform(lambda s: s.rolling(window, min_periods=window).sum())
    out = p[["Store_ID", "Product_ID", "week_index"]].rename(columns={"week_index": "origin_week"})
    out["recorded_wastage_pct_4w"] = np.where(s > 0, 100 * w / s.where(s > 0), np.nan)
    return out


def recent_simulated_expiry(weekly: pd.DataFrame, window: int) -> pd.DataFrame:
    """Expired / received over the simulated weeks origin-window+1 .. origin (all simulated before the decision)."""
    w = weekly.sort_values(["Store_ID", "Product_ID", "week"])
    g = w.groupby(["Store_ID", "Product_ID"])
    e = g["sim_expired_units"].transform(lambda s: s.rolling(window, min_periods=1).sum())
    r = g["sim_received_units"].transform(lambda s: s.rolling(window, min_periods=1).sum())
    out = w[["Store_ID", "Product_ID", "week"]].rename(columns={"week": "origin_week"})
    out["recent_simulated_expiry_pct_4w"] = np.where(r > 0, 100 * e / r.where(r > 0), np.nan)
    out["recent_simulated_expiry_units_4w"] = e
    return out


def earliest_batch_expiry(deliveries: pd.DataFrame, decisions: pd.DataFrame) -> pd.Series:
    """Earliest last-sellable day among batches delivered before the decision day and still in date on it."""
    d = decisions[["Store_ID", "Product_ID", "decision_day"]].reset_index()
    dl = deliveries[deliveries["delivered_units"] > 0][["Store_ID", "Product_ID", "arrival_day", "expiry_day"]]
    m = d.merge(dl, on=["Store_ID", "Product_ID"])
    m = m[(m["arrival_day"] < m["decision_day"]) & (m["expiry_day"] >= m["decision_day"])]
    return m.groupby("index")["expiry_day"].min().reindex(decisions.index)


# --------------------------------------------------------------------------------------------- assess
def assess(decisions: pd.DataFrame, deliveries: pd.DataFrame, weekly: pd.DataFrame, contract: pd.DataFrame,
           panel: pd.DataFrame, cases: pd.DataFrame, params: dict) -> pd.DataFrame:
    """One advisory waste-risk row per saved decision. Inputs are saved tables; nothing is modified."""
    high, moderate = params["waste_risk_high_pct_of_p50"], params["waste_risk_moderate_pct_of_p50"]
    max_reasons = params["waste_risk_max_reasons"]
    h1 = contract[contract["horizon_weeks"] == 1][["store_id", "product_id", "origin_week", "median_p50_units",
                                                   "lower_p10_units", "upper_p90_units", "predicted_units",
                                                   "uncertainty_status", "risk_flags"]]
    h4 = contract[contract["horizon_weeks"] == 4][["store_id", "product_id", "origin_week", "predicted_units",
                                                   "uncertainty_status"]].rename(
        columns={"predicted_units": "h4_predicted_units", "uncertainty_status": "h4_uncertainty_status"})
    keys = {"store_id": "Store_ID", "product_id": "Product_ID"}
    d = (decisions.merge(h1.rename(columns=keys), on=["Store_ID", "Product_ID", "origin_week"], how="left")
         .merge(h4.rename(columns=keys), on=["Store_ID", "Product_ID", "origin_week"], how="left"))
    d = d.join(planned_buffer(deliveries, d), on="order_id")
    d = d.merge(recorded_wastage(panel, params["waste_risk_recorded_wastage_window_weeks"]),
                on=["Store_ID", "Product_ID", "origin_week"], how="left")
    d = d.merge(recent_simulated_expiry(weekly, params["waste_risk_simulated_history_window_weeks"]),
                on=["Store_ID", "Product_ID", "origin_week"], how="left")
    d["earliest_batch_last_day"] = earliest_batch_expiry(deliveries, d)
    d = _link_cases(d, cases)

    rows = []
    for r in d.itertuples(index=False):
        bounds = r.uncertainty_status == "AVAILABLE" and (not isinstance(r.h4_uncertainty_status, str)
                                                          or r.h4_uncertainty_status == "AVAILABLE")
        supported = r.delivery_arrangement != "UNSUPPORTED"
        proj = r.std_existing_expiry_projection_units
        cat, share = classify(proj, r.median_p50_units, high, moderate, bounds, supported)
        units = None if proj is None or (isinstance(proj, float) and math.isnan(proj)) else max(0.0, float(proj))
        reasons = []
        if not bounds:
            reasons.append("FORECAST_RANGE_MISSING")
        if not supported:
            reasons.append("UNSUPPORTED_ARRANGEMENT")
        if units is None and bounds and supported:
            reasons.append("NO_PROJECTION")
        if units is not None and units > TOL:
            reasons.append("CURRENT_STOCK_PROJECTED_TO_EXPIRE")
        if isinstance(r.median_p50_units, float) and not math.isnan(r.median_p50_units) and r.median_p50_units <= 0:
            reasons.append("ZERO_TYPICAL_DEMAND")
        arrival = r.arrival_day if not (isinstance(r.arrival_day, float) and math.isnan(r.arrival_day)) \
            else r.decision_day + r.effective_lead_time_days
        batch = r.earliest_batch_last_day
        has_batch = not (isinstance(batch, float) and math.isnan(batch))
        if units is not None and units > TOL and has_batch and batch < arrival:
            reasons.append("BATCH_LAST_DAY_BEFORE_NEXT_DELIVERY")
        if r.delivery_arrangement == "SHORT_LIFE_RECURRING_DROPS":
            reasons.append("FRESH_SHORT_SHELF_LIFE")
        flags = str(r.flags) if isinstance(r.flags, str) else ""
        if ("TREND_DIVERGENCE" in flags and isinstance(r.h4_predicted_units, float)
                and r.h4_predicted_units < r.predicted_units):
            reasons.append("LONGER_RANGE_FORECAST_LOWER")
        if "HOLIDAY_TARGET_WEEK" in flags or "CHRISTMAS_PERIOD" in flags or \
                (isinstance(r.risk_flags, str) and "HOLIDAY_TARGET_WEEK" in r.risk_flags):
            reasons.append("HOLIDAY_OR_CHRISTMAS_WEEK")
        if isinstance(r.recent_simulated_expiry_units_4w, (int, float)) and r.recent_simulated_expiry_units_4w > 0:
            reasons.append("RECENT_SIMULATED_EXPIRY")
        investigate = None
        if cat in ("HIGH", "MODERATE") and has_batch:
            investigate = int(max(r.decision_day, batch - 1))
        rows.append({
            "Store_ID": r.Store_ID, "Product_ID": r.Product_ID, "product_category": r.product_category,
            "origin_week": r.origin_week, "target_week": r.target_week, "decision_day": r.decision_day,
            "decision_label": day_label(r.decision_day),
            "category": cat, "category_label": CATEGORY_LABELS[cat],
            "projected_existing_expiry_units": None if units is None else round(units, 1),
            "projected_expiry_pct_of_p50": None if share is None else round(share, 2),
            "projected_expiry_days_of_sales": None if share is None else round(share * 7 / 100, 2),
            "typical_weekly_demand_p50": None if isinstance(r.median_p50_units, float) and math.isnan(r.median_p50_units)
            else round(float(r.median_p50_units), 1),
            "planned_buffer_units": round(float(np.nan_to_num(r.planned_buffer_units)), 1),
            "low_sales_buffer_units": round(float(np.nan_to_num(r.low_sales_buffer_units)), 1),
            "recorded_wastage_pct_4w": None if isinstance(r.recorded_wastage_pct_4w, float) and math.isnan(r.recorded_wastage_pct_4w)
            else round(float(r.recorded_wastage_pct_4w), 2),
            "recent_simulated_expiry_pct_4w": None if isinstance(r.recent_simulated_expiry_pct_4w, float)
            and math.isnan(r.recent_simulated_expiry_pct_4w) else round(float(r.recent_simulated_expiry_pct_4w), 2),
            "remaining_life_days": r.remaining_life_days,
            "earliest_batch_last_day": None if not has_batch else int(batch),
            "earliest_batch_last_day_label": day_label(batch) if has_batch else None,
            "investigate_by_day": investigate, "investigate_by_label": day_label(investigate),
            "reason_codes": "|".join(reasons[:max_reasons]), "all_reason_codes": "|".join(reasons),
            "main_reasons": "; ".join(REASONS[c] for c in reasons[:max_reasons]),
            "suggested_investigation": INVESTIGATION[cat],
            "review_case_ref": r.review_case_ref, "review_case_type": r.review_case_type,
            "review_status": "PENDING_REVIEW (existing case)" if isinstance(r.review_case_type, str) else "ADVISORY — no review case",
            "status": STATUS, "creates_review_case": False, "approval_event_id": None,
            "scenario_id": r.scenario_id, "policy_id": r.policy_id, "simulator_version": r.simulator_version,
        })
    return pd.DataFrame(rows)


def _link_cases(d: pd.DataFrame, cases: pd.DataFrame) -> pd.DataFrame:
    """Reference existing review cases (never creates one). P2 queue v1.2 has case ids; the v1.1 queue does not."""
    c = cases[cases["case_type"].notna()].copy()
    if "case_id" in c.columns:
        c["review_case_ref"] = c["case_id"]
    else:
        c["review_case_ref"] = ("v1.1 queue · store " + c["store_id"].astype(str) + " · product " + c["product_id"].astype(str)
                                + " · origin " + c["origin_week"].astype(str))
    c = c.rename(columns={"store_id": "Store_ID", "product_id": "Product_ID", "case_type": "review_case_type"})
    c = c[["Store_ID", "Product_ID", "origin_week", "review_case_ref", "review_case_type"]].drop_duplicates(
        ["Store_ID", "Product_ID", "origin_week"])
    return d.merge(c, on=["Store_ID", "Product_ID", "origin_week"], how="left")


def summary(assessment: pd.DataFrame) -> dict:
    counts = assessment["category"].value_counts()
    return {"decisions": int(len(assessment)), **{c: int(counts.get(c, 0)) for c in CATEGORIES},
            "projected_existing_expiry_units": round(float(assessment["projected_existing_expiry_units"].fillna(0).sum()), 1),
            "planned_buffer_units": round(float(assessment["planned_buffer_units"].sum()), 1),
            "linked_to_existing_review_case": int(assessment["review_case_type"].notna().sum()),
            "review_cases_created": 0}


def category_comparison(panel: pd.DataFrame, weekly: pd.DataFrame, attributes: pd.DataFrame) -> pd.DataFrame:
    """Recorded historical wastage (share of units sold) beside simulated expiry (share of units received), per category.
    DIFFERENT MEASURES: recorded wastage is a historical record of an apparently synthetic dataset; simulated expiry is
    an outcome of the replay under assumed stock and supply. They are shown side by side, not as equivalents."""
    cat = attributes.drop_duplicates("Product_ID").set_index("Product_ID")["Product_Category"]
    weeks = weekly["week"].unique()
    rec_all = panel.groupby("Product_Category")[["Wastage_Units", "Units_Sold"]].sum()
    rec_win = panel[panel["week_index"].isin(weeks)].groupby("Product_Category")[["Wastage_Units", "Units_Sold"]].sum()
    sim = weekly.assign(cat=weekly["Product_ID"].map(cat)).groupby("cat")[["sim_expired_units", "sim_received_units"]].sum()
    out = pd.DataFrame({
        "recorded_wastage_pct_of_sold_full_year": 100 * rec_all["Wastage_Units"] / rec_all["Units_Sold"],
        "recorded_wastage_pct_of_sold_same_weeks": 100 * rec_win["Wastage_Units"] / rec_win["Units_Sold"],
        "simulated_expired_pct_of_received": 100 * sim["sim_expired_units"] / sim["sim_received_units"].where(sim["sim_received_units"] > 0),
    }).round(2)
    out.index.name = "category"
    return out.reset_index()
