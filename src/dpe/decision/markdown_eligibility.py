"""Stage 7B: markdown review eligibility (read-only, deterministic, state 1 of 4 only).

Decides whether a person should LOOK AT a line for a possible markdown. It never proposes a discount size or a new
price, never predicts sales, margin or waste effects, and never approves or executes anything (decisions M1, M7, M8).
Inputs are saved evidence only: the Stage 6B waste-risk assessment, the saved decisions (common shortage indicator),
the protected forecast contract (Christmas in any horizon), the verified panel (recorded price and discount in the
origin week, known at the decision) and the saved review cases. Rules: docs/STAGE_7A_PRICING_MARKDOWN_DESIGN.md
section 4; parameters from assumption set v4 (DRAFT).

Classification, first match wins (one final class; every applicable blocker is still recorded):
  1 NOT_CONSIDERED                waste-risk category not in the eligible categories (Low)
  2 INSUFFICIENT_INFORMATION      waste risk Insufficient information, or no dated batch evidence
  3 BLOCKED                       High/Moderate with at least one blocker, in the documented order:
                                  CHRISTMAS_ESCALATION, SHORTAGE_BEFORE_DELIVERY, ALREADY_ON_PROMOTION,
                                  PRODUCT_EXCLUDED, TOO_LATE_TO_ACT
  4 ELIGIBLE_FOR_MARKDOWN_REVIEW  otherwise
An open inventory review case is a WARNING only, never a blocker (decision M6).
"""
from __future__ import annotations

import math

import pandas as pd

CLASSES = ("ELIGIBLE_FOR_MARKDOWN_REVIEW", "BLOCKED", "INSUFFICIENT_INFORMATION", "NOT_CONSIDERED")
CLASS_LABELS = {"ELIGIBLE_FOR_MARKDOWN_REVIEW": "Eligible for markdown review", "BLOCKED": "Blocked",
                "INSUFFICIENT_INFORMATION": "Insufficient information", "NOT_CONSIDERED": "Not considered"}
BLOCKER_LABELS = {
    "CHRISTMAS_ESCALATION": "Christmas week — follow the escalation process first",
    "SHORTAGE_BEFORE_DELIVERY": "Stock may run short before the next delivery — a markdown would make that worse",
    "ALREADY_ON_PROMOTION": "Already on a recorded promotion this week",
    "PRODUCT_EXCLUDED": "Product is on the exclusion list",
    "TOO_LATE_TO_ACT": "Too few sellable days left after the investigate-by day",
}
INSUFFICIENT_LABELS = {
    "WASTE_RISK_INSUFFICIENT": "Waste risk could not be judged (missing forecast range, zero demand or unsupported supplier)",
    "MISSING_BATCH_DATE": "No dated batch evidence, so timing cannot be judged",
}
WARNING_LABELS = {"OPEN_INVENTORY_REVIEW_CASE": "An inventory review case is already open for this line (warning only)"}
MISSING_DATA_LABELS = {
    "D1_PURCHASE_COST": "Real purchase cost per unit",
    "D2_SHELF_AND_REGULAR_PRICE": "Verified shelf price and regular (non-promotion) price",
    "D3_BATCH_STOCK_AND_EXPIRY": "Stock on hand by batch with real expiry dates",
    "D4_MARKDOWN_RESPONSE_HISTORY": "Markdown history showing how sales actually responded",
    "D5_ALTERNATIVE_VALUES": "Value of alternatives (donation, staff sale, disposal)",
    "D6_PRICING_RULES": "Pricing rules (legal limits, supplier and brand agreements)",
    "D7_STORE_OPERATIONS": "Store markdown operations (times, labels, staff)",
    "D8_APPROVAL_OWNERSHIP": "Who may approve a markdown, and their limits",
    "D9_CONFIRMED_SUPPLIER_SCHEDULES": "Confirmed supplier delivery schedules",
}
GUIDANCE = {
    "ELIGIBLE_FOR_MARKDOWN_REVIEW": ("Check dates and quantity on the shelf before {by}. With the store team, consider "
                                     "whether a markdown, a smaller next order or another option is appropriate. No "
                                     "discount size is proposed."),
    "BLOCKED": "A markdown review is not appropriate now: {why}.",
    "INSUFFICIENT_INFORMATION": "Not enough information to judge timing — check the shelf and decide manually.",
    "NOT_CONSIDERED": "No unusual waste expected from current stock — no markdown review needed.",
}
LIFECYCLE_STATE = "STATE_1_ELIGIBILITY_ONLY"  # states 2 (proposed), 3 (approved) and 4 (executed) are not built
STATUS = "HYPOTHETICAL_UNAPPROVED"
EXECUTION = "NOT_EXECUTED"
PROVENANCE = {
    "waste_risk_category": "Stage 6B advisory assessment (SIMULATED × FORECAST, ASSUMED thresholds)",
    "earliest_batch_last_day": "SIMULATED delivery dates (units left per batch not saved)",
    "sellable_days_after_investigate_by": "calculated from SIMULATED delivery dates",
    "recorded_price_origin_week": "RECORDED (apparently synthetic dataset; currency assumed GBP) — context only",
    "recorded_discount_pct_origin_week": "RECORDED (apparently synthetic dataset) — used only for ALREADY_ON_PROMOTION",
    "christmas": "RECORDED calendar via the forecast contract (any horizon)",
    "shortage": "SIMULATED × FORECAST common indicator (std_pre_delivery_shortage)",
    "eligibility": "ASSUMED rules (assumption set v4, DRAFT)",
}


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def classify(waste_category: str, has_batch_date: bool, blockers: list[str], eligible_categories) -> str:
    """One final class by the Stage 7A precedence."""
    if waste_category == "INSUFFICIENT_INFORMATION":
        return "INSUFFICIENT_INFORMATION"
    if waste_category not in eligible_categories:
        return "NOT_CONSIDERED"
    if not has_batch_date:
        return "INSUFFICIENT_INFORMATION"
    if blockers:
        return "BLOCKED"
    return "ELIGIBLE_FOR_MARKDOWN_REVIEW"


def blockers_for(christmas: bool, shortage: bool, discount_pct, product_id: int, exclusions, sellable_days,
                 min_days: int, order) -> list[str]:
    """Every applicable blocker, in the documented order."""
    found = set()
    if christmas:
        found.add("CHRISTMAS_ESCALATION")
    if shortage:
        found.add("SHORTAGE_BEFORE_DELIVERY")
    if not _missing(discount_pct) and float(discount_pct) > 0:
        found.add("ALREADY_ON_PROMOTION")
    if int(product_id) in {int(p) for p in exclusions}:
        found.add("PRODUCT_EXCLUDED")
    if not _missing(sellable_days) and sellable_days < min_days:
        found.add("TOO_LATE_TO_ACT")
    return [b for b in order if b in found]


def assess(waste: pd.DataFrame, decisions: pd.DataFrame, contract: pd.DataFrame, panel: pd.DataFrame,
           params: dict) -> pd.DataFrame:
    """One read-only eligibility row per waste-risk row. `waste` is the Stage 6B assessment for the same policy and
    scenario; nothing is modified."""
    order = params["markdown_blocker_order"]
    eligible_cats = params["markdown_eligible_waste_categories"]
    min_days = params["markdown_min_sellable_days_after_investigate_by"]
    exclusions = params["markdown_product_exclusions"]
    xmas = (contract.assign(_x=contract["target_week"].isin((51, 52)))
            .groupby(["store_id", "product_id", "origin_week"])["_x"].any().rename("christmas_any_horizon").reset_index()
            .rename(columns={"store_id": "Store_ID", "product_id": "Product_ID"}))
    rec = panel[["Store_ID", "Product_ID", "week_index", "Price", "Discount_Percent"]].rename(
        columns={"week_index": "origin_week", "Price": "recorded_price_origin_week",
                 "Discount_Percent": "recorded_discount_pct_origin_week"})
    shortage = decisions[["Store_ID", "Product_ID", "origin_week", "std_pre_delivery_shortage"]]
    m = (waste.merge(shortage, on=["Store_ID", "Product_ID", "origin_week"], how="left")
         .merge(xmas, on=["Store_ID", "Product_ID", "origin_week"], how="left")
         .merge(rec, on=["Store_ID", "Product_ID", "origin_week"], how="left"))
    rows = []
    for r in m.itertuples(index=False):
        has_batch = not _missing(r.earliest_batch_last_day) and not _missing(r.investigate_by_day)
        sellable = (int(r.earliest_batch_last_day) - int(r.investigate_by_day)) if has_batch else None
        shortage_flag = (not _missing(r.std_pre_delivery_shortage)) and bool(r.std_pre_delivery_shortage)
        blockers = blockers_for(bool(r.christmas_any_horizon) if not _missing(r.christmas_any_horizon) else False,
                                shortage_flag, r.recorded_discount_pct_origin_week, r.Product_ID, exclusions,
                                sellable, min_days, order)
        cls = classify(r.category, has_batch, blockers, eligible_cats)
        insufficient = []
        if cls == "INSUFFICIENT_INFORMATION":
            insufficient.append("WASTE_RISK_INSUFFICIENT" if r.category == "INSUFFICIENT_INFORMATION" else "MISSING_BATCH_DATE")
        # Warning only (M6), shown where a markdown review is actually considered.
        warnings = ["OPEN_INVENTORY_REVIEW_CASE"] if isinstance(r.review_case_type, str) and cls != "NOT_CONSIDERED" else []
        if cls == "ELIGIBLE_FOR_MARKDOWN_REVIEW":
            guidance = GUIDANCE[cls].format(by=r.investigate_by_label)
        elif cls == "BLOCKED":
            guidance = GUIDANCE[cls].format(why="; ".join(BLOCKER_LABELS[b].lower() for b in blockers))
        else:
            guidance = GUIDANCE[cls]
        rows.append({
            "Store_ID": r.Store_ID, "Product_ID": r.Product_ID, "product_category": r.product_category,
            "origin_week": r.origin_week, "target_week": r.target_week, "decision_day": r.decision_day,
            "waste_risk_category": r.category, "projected_existing_expiry_units": r.projected_existing_expiry_units,
            "projected_expiry_pct_of_p50": r.projected_expiry_pct_of_p50,
            "earliest_batch_last_day": r.earliest_batch_last_day, "earliest_batch_last_day_label": r.earliest_batch_last_day_label,
            "investigate_by_day": r.investigate_by_day, "investigate_by_label": r.investigate_by_label,
            "sellable_days_after_investigate_by": sellable,
            "recorded_price_origin_week": r.recorded_price_origin_week,
            "recorded_discount_pct_origin_week": r.recorded_discount_pct_origin_week,
            "christmas_any_horizon": bool(r.christmas_any_horizon) if not _missing(r.christmas_any_horizon) else False,
            "shortage_before_delivery": shortage_flag,
            "eligibility": cls, "eligibility_label": CLASS_LABELS[cls],
            "blocker_codes": "|".join(blockers), "insufficient_codes": "|".join(insufficient),
            "warning_codes": "|".join(warnings),
            "reasons": "; ".join([BLOCKER_LABELS[b] for b in blockers] + [INSUFFICIENT_LABELS[i] for i in insufficient]),
            "waste_reasons": r.main_reasons,
            "guidance": guidance,
            "review_case_ref": r.review_case_ref, "review_case_type": r.review_case_type,
            "missing_data_for_numerical_discount": "|".join(params["markdown_required_data_before_numerical_discount"]),
            "lifecycle_state": LIFECYCLE_STATE, "status": STATUS, "execution_status": EXECUTION,
            "approval_event_id": None, "proposal_id": None,
            "scenario_id": r.scenario_id, "policy_id": r.policy_id,
        })
    return pd.DataFrame(rows)


def summary(a: pd.DataFrame) -> dict:
    counts = a["eligibility"].value_counts()
    blocked = a[a["eligibility"] == "BLOCKED"]["blocker_codes"].str.split("|").explode()
    return {"rows": int(len(a)), **{c: int(counts.get(c, 0)) for c in CLASSES},
            "blocked_by_reason": {k: int(v) for k, v in blocked.value_counts().items()},
            "with_open_inventory_case_warning": int(a["warning_codes"].str.contains("OPEN_INVENTORY_REVIEW_CASE").sum()),
            "proposals_created": 0, "approvals_created": 0}
