"""Step 5B-2: review cases, one per decision point (store x product x origin week), reasons aggregated.

Precedence: MANDATORY_ESCALATION (Christmas) > MANDATORY_REVIEW (unavailable bounds, unsupported delivery
arrangement) > RISK_ESCALATION (material trigger). HOLIDAY_TARGET_WEEK only flags and boosts priority; it never
creates a case on its own. Price and policy APPROVAL_REQUIRED cases belong to the later pricing / inventory
recommendation engines and are not generated here.

Version 1.1 (correction checkpoint 23 Oct 2026): LIFE_LEAD_TIME_TIGHT is an informational WARNING. On its own it
creates no case; it is kept in the `warnings` column and, when a case exists, in its reasons. It escalates only
together with a material operational risk (a material trigger, an unsupported arrangement or Christmas). Coverage
triggers are PRE_ORDER_SHORTAGE (shortage pressure before the new order can arrive) and POST_ORDER_SHORTFALL (the
proposed order does not cover the window). Every case is PENDING_REVIEW: nothing is approved without an explicit
approval event, and none exists in a replay.
"""
from __future__ import annotations

import pandas as pd

CHRISTMAS_WEEKS = (51, 52)
TYPE_RANK = {"MANDATORY_ESCALATION": 3, "MANDATORY_REVIEW": 2, "RISK_ESCALATION": 1}
QUEUE_VERSION = "1.1"
MATERIAL_TRIGGERS = ("PRE_ORDER_SHORTAGE", "POST_ORDER_SHORTFALL", "WASTE_HIGH_EXISTING_STOCK",
                     "FILL_RATE_SHORTFALL_LAST_WEEK", "TREND_DIVERGENCE")
WARNINGS = ("LIFE_LEAD_TIME_TIGHT", "TARGET_ABOVE_P90_CAPPED", "HOLIDAY_TARGET_WEEK")
APPROVAL_STATUS = "PENDING_REVIEW"


def build_cases(contract: pd.DataFrame, decisions: pd.DataFrame, values: dict, unit_share: pd.Series | None = None) -> pd.DataFrame:
    """All decision points in the contract (both horizons) plus simulator flags for simulated origins."""
    key = ["store_id", "product_id", "origin_week"]
    c = contract.copy()
    c["christmas"] = c["target_week"].isin(CHRISTMAS_WEEKS)
    c["missing"] = c["uncertainty_status"] != "AVAILABLE"
    c["holiday"] = c["risk_flags"].str.contains("HOLIDAY_TARGET_WEEK")
    dp = c.groupby(key).agg(christmas=("christmas", "any"), missing=("missing", "any"), holiday=("holiday", "any"),
                            product_category=("product_category", "first")).reset_index()
    sim = decisions.rename(columns={"Store_ID": "store_id", "Product_ID": "product_id"})[key + ["flags"]]
    dp = dp.merge(sim, on=key, how="left")
    dp["simulated"] = dp["flags"].notna()
    triggers = list(MATERIAL_TRIGGERS)
    if values.get("life_lead_time_tight_is_material_trigger", False):  # legacy v1.0 rule, sensitivity only
        triggers.append("LIFE_LEAD_TIME_TIGHT")
    rows = []
    for r in dp.itertuples(index=False):
        flags = set(r.flags.split("|")) if isinstance(r.flags, str) and r.flags else set()
        reasons = []
        if r.christmas:
            reasons.append("CHRISTMAS_PERIOD")
        if r.missing:
            reasons.append("UNCERTAINTY_UNAVAILABLE")
        if "UNSUPPORTED_DELIVERY_ARRANGEMENT" in flags:
            reasons.append("UNSUPPORTED_DELIVERY_ARRANGEMENT")
        material = [t for t in triggers if t in flags]
        reasons += material
        warnings = [w for w in WARNINGS if w in flags and w not in material]
        if r.christmas:
            ctype = "MANDATORY_ESCALATION"
        elif r.missing or "UNSUPPORTED_DELIVERY_ARRANGEMENT" in flags:
            ctype = "MANDATORY_REVIEW"
        elif material:
            ctype = "RISK_ESCALATION"
        else:
            ctype = None
        if ctype and "LIFE_LEAD_TIME_TIGHT" in warnings:
            reasons.append("LIFE_LEAD_TIME_TIGHT_WARNING")
        rows.append({"store_id": r.store_id, "product_id": r.product_id, "origin_week": r.origin_week,
                     "product_category": r.product_category, "case_type": ctype, "reasons": "|".join(reasons),
                     "warnings": "|".join(warnings), "holiday_flag": bool(r.holiday),
                     "material_trigger_count": len(material), "simulated_decision": bool(r.simulated),
                     "approval_status": APPROVAL_STATUS if ctype else None, "approval_event_id": None})
    out = pd.DataFrame(rows)
    short_life = {"Bakery", "Meat"}
    share = 0.0 if unit_share is None else out.set_index(key).index.map(lambda k: unit_share.get(k, 0.0))
    out["priority_score"] = (out["case_type"].map(TYPE_RANK).fillna(0) * 100
                             + out["holiday_flag"].astype(int) * 10 + out["product_category"].isin(short_life).astype(int) * 5
                             + out["material_trigger_count"] + pd.Series(share, index=out.index).fillna(0))
    out["scenario_id"] = values["scenario_id"]
    out["assumption_set_id"] = values["assumption_set_id"]
    out["queue_version"] = QUEUE_VERSION
    out = out.sort_values(["priority_score", "store_id", "product_id", "origin_week"],
                          ascending=[False, True, True, True]).reset_index(drop=True)
    return out


def case_summary(cases: pd.DataFrame) -> dict:
    open_cases = cases[cases["case_type"].notna()]
    return {"decision_points": int(len(cases)), "cases": int(len(open_cases)),
            "by_type": {k: int(v) for k, v in open_cases["case_type"].value_counts().items()},
            "holiday_only_flagged_no_case": int((cases["holiday_flag"] & cases["case_type"].isna()).sum()),
            "lead_time_warning_only_no_case": int((cases["warnings"].str.contains("LIFE_LEAD_TIME_TIGHT")
                                                   & cases["case_type"].isna()).sum()),
            "lead_time_warning_in_case": int(cases["reasons"].str.contains("LIFE_LEAD_TIME_TIGHT").sum()),
            "approved_cases": int(open_cases["approval_event_id"].notna().sum()),
            "duplicate_cases": int(open_cases.duplicated(subset=["store_id", "product_id", "origin_week"]).sum())}
