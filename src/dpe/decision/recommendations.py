"""Step 5B-3b: hypothetical inventory recommendations from the 5B-3a calculator (deterministic, explainable).

Converts one `inventory.OrderPlan` plus its decision context into one recommendation record: a primary category, every
applicable reason code, the coverage / expiry / supplier evidence, provenance labels and a plain-English explanation.
Review cases are built from these records in `inventory_review.py`.

Nothing here approves, executes or sends anything. Every recommendation is HYPOTHETICAL_UNAPPROVED and NOT_EXECUTED;
no approval event is ever created; no supplier order, price change, stock transfer or expedited delivery occurs.
The DRAFT assumption set supplies illustrative ASSUMED values only, not validated business policy.

Primary category precedence (first match wins; safety blocks before routine proposals):
  1 NO_ACTIONABLE_RECOMMENDATION_MANDATORY_REVIEW   bounds missing / arrangement unsupported (quantity 0)
  2 SHORTAGE_REMAINING_AFTER_PROPOSED_ORDER         planning-rate gap left in the window after the order
  3 SHORTAGE_BEFORE_PROPOSED_DELIVERY               p50 gap before the new order can arrive
  4 NO_REPLENISHMENT_REQUIRED                       every delivery's net need is zero
  5 ROUTINE_REPLENISHMENT_PROPOSAL                  otherwise
Case type (independent of category): Christmas -> MANDATORY_ESCALATION; category 1 -> MANDATORY_REVIEW; any material
reason -> RISK_ESCALATION; warnings alone -> no weekly case.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from dpe.decision import inventory as INV

ENGINE_VERSION = "5B-3b-1.0"
STATUS = "HYPOTHETICAL_UNAPPROVED"
EXECUTION_STATUS = "NOT_EXECUTED"
CHRISTMAS_WEEKS = (51, 52)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ROUNDING_EXCESS_WARNING_PCT = 10.0  # readiness threshold T-X: report, not a gate

CATEGORIES = (
    "NO_ACTIONABLE_RECOMMENDATION_MANDATORY_REVIEW",
    "SHORTAGE_REMAINING_AFTER_PROPOSED_ORDER",
    "SHORTAGE_BEFORE_PROPOSED_DELIVERY",
    "NO_REPLENISHMENT_REQUIRED",
    "ROUTINE_REPLENISHMENT_PROPOSAL",
)
CASE_TYPE_RANK = {"MANDATORY_ESCALATION": 3, "MANDATORY_REVIEW": 2, "RISK_ESCALATION": 1}

# Stable reason codes: code -> (class, description). Classes: BLOCK (no actionable order, mandatory review),
# MANDATORY (mandatory escalation), MATERIAL (risk escalation), WARNING (evidence only), STANDING (supplier
# confirmation, kept out of weekly cases).
REASONS = {
    "UNCERTAINTY_UNAVAILABLE": ("BLOCK", "Forecast uncertainty bounds are unavailable; no quantity is proposed"),
    "UNSUPPORTED_DELIVERY_ARRANGEMENT": ("BLOCK", "Lead time of 7+ days or no remaining life on arrival; no quantity is proposed"),
    "CHRISTMAS_PERIOD": ("MANDATORY", "A target week (H1 or H4) is in the Christmas period; mandatory escalation, no bulk approval"),
    "SHORTAGE_REMAINING_AFTER_ORDER": ("MATERIAL", "A planning-rate gap remains in the coverage window after the proposed order"),
    "PRE_DELIVERY_SHORTAGE": ("MATERIAL", "The proposed delivery arrives too late to cover planned (p50) demand before it"),
    "EXPIRY_BEFORE_COVERAGE": ("MATERIAL", "Existing stock is projected to expire before it can cover planned demand (above the high waste band)"),
    "ARRANGEMENT_FEASIBILITY_RISK": ("MATERIAL", "The order relies on an unconfirmed delivery arrangement and still leaves a coverage or expiry gap"),
    "FILL_RATE_SHORTFALL_LAST_WEEK": ("MATERIAL", "A delivery received in the last 7 days was short of the ordered quantity"),
    "TREND_DIVERGENCE": ("MATERIAL", "H4 and H1 point forecasts differ by more than the threshold"),
    "PRE_DELIVERY_GAP_HIGHER_DEMAND_ONLY": ("WARNING", "A gap before delivery appears only at the p90 rate"),
    "EXPIRY_BEFORE_COVERAGE_MINOR": ("WARNING", "Some existing stock is projected to expire unused (at or below the high waste band)"),
    "SHORT_LIFE_ARRANGEMENT_ASSUMED": ("WARNING", "Recurring short-life drops rest on an assumed, unconfirmed supplier arrangement"),
    "WEEKEND_DELIVERY_ASSUMED": ("WARNING", "A proposed delivery falls on a Saturday or Sunday under an assumed arrangement"),
    "LIFE_LEAD_TIME_TIGHT": ("WARNING", "Effective lead time is at least the remaining life on arrival"),
    "TARGET_ABOVE_P90_CAPPED": ("WARNING", "Service target above 90%; planning target capped at p90"),
    "HOLIDAY_TARGET_WEEK": ("WARNING", "Regional holiday flag for the target week"),
    "ROUNDING_EXCESS_HIGH": ("WARNING", "Case/MOQ rounding adds more than 10% to the net need"),
    "SUPPLIER_CONFIRMATION_REQUIRED": ("STANDING", "Assumed daily, recurring or weekend deliveries need supplier confirmation"),
}
REASON_ORDER = {code: i for i, code in enumerate(REASONS)}


@dataclass(frozen=True)
class DecisionContext:
    """Everything known at the decision, apart from stock state. Values carry their provenance in `evidence`."""
    scenario_id: str
    store_id: int
    product_id: int
    product_category: str
    origin_week: int
    decision_day: int
    shelf_life_days: int                 # OBSERVED
    lead_time_days: int                  # OBSERVED
    lead_time_adjustment_days: int       # ASSUMED / SYNTHETIC
    transit_age_days: int                # ASSUMED
    p10: float | None                    # FORECAST (protected contract v1.0)
    p50: float | None
    p90: float | None
    uncertainty_status: str
    risk_flags: str = ""
    h1_point: float | None = None
    h4_point: float | None = None
    service_target_pct: float = 50.0     # ASSUMED
    case_size_units: int = 1             # ASSUMED
    moq_cases: int = 1                   # ASSUMED
    waste_high_above_pct: float = 15.0   # ASSUMED
    trend_divergence_threshold_pct: float = 30.0  # ASSUMED
    fill_shortfall_last_week: bool = False        # SIMULATED (replay receipts) or OBSERVED (live receipts)
    assumption_set_id: str = ""
    assumption_status: str = "DRAFT"
    assumption_content_sha256: str = ""
    forecast_contract_run: str = ""
    stock_state_provenance: str = "SIMULATED_REPLAY_STATE"
    decision_week_label: str | None = None  # e.g. dataset WeekDate of the target week, if the caller has it
    christmas_any_horizon: bool = False     # contract gate: any horizon's target week is Christmas (v1.1 queue rule)
    fill_stress_pct: float = 75.0           # ASSUMED illustrative stress for the reported exposure (orders unchanged)

    @property
    def target_week(self) -> int:
        return self.origin_week + 1

    @property
    def effective_lead_time_days(self) -> int:
        return self.lead_time_days + self.lead_time_adjustment_days

    @property
    def remaining_life_days(self) -> int:
        return self.shelf_life_days - self.transit_age_days


def context_from_values(values: dict, **kw) -> DecisionContext:
    """Fill the ASSUMED fields of a DecisionContext from one resolved assumption scenario (read-only). Assumption set
    v2 parameters are used when present; with v1 the 5B-3b defaults apply (high waste band, 75% stress)."""
    cat = kw["product_category"]
    if values.get("planning_fill_rate_pct", 100) != 100 or values.get("order_inflation_for_expected_shortfall", False):
        raise ValueError("Planning must expect 100% fulfilment and never inflate orders (decision D3)")
    kw.setdefault("assumption_status", values.get("assumption_status", "DRAFT"))
    kw.setdefault("assumption_content_sha256", values.get("assumption_content_sha256", ""))
    return DecisionContext(
        scenario_id=values["scenario_id"], service_target_pct=values["service_target_pct"][cat],
        case_size_units=values["case_size_units"][cat], moq_cases=values["moq_cases_per_delivery"],
        waste_high_above_pct=values.get("expiry_escalation_pct_of_p50", values["waste_band_pct"]["HIGH_above"]),
        trend_divergence_threshold_pct=values["trend_divergence_threshold_pct"],
        lead_time_adjustment_days=values["lead_time_adjustment_days"], transit_age_days=values["transit_age_days"],
        fill_stress_pct=values.get("stress_fill_rate_pct", 75.0),
        assumption_set_id=values["assumption_set_id"], **kw)


def week_day_label(day: int) -> str:
    return f"week {(day - 1) // 7 + 1} {WEEKDAYS[INV.dow_of(day) - 1]} (replay day {day})"


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def expiry_share_is_high(expected_expiry: float, p50, high_above_pct: float) -> bool:
    """Provisional material trigger: projected existing-stock expiry above high_above_pct of weekly p50. When p50 is
    zero, negative or unavailable the share is undefined, so any positive expiry is treated as material."""
    if expected_expiry <= INV.TOL:
        return False
    if _missing(p50) or not math.isfinite(float(p50)) or float(p50) <= 0:
        return True
    return 100 * expected_expiry / float(p50) > high_above_pct


def plan_for(ctx: DecisionContext, lots, committed) -> INV.OrderPlan:
    """Run the accepted 5B-3a calculator for this context (lots / committed deliveries at decision time only)."""
    return INV.plan_order(lots, committed, ctx.decision_day, ctx.effective_lead_time_days, ctx.remaining_life_days,
                          ctx.p10, ctx.p50, ctx.p90, ctx.service_target_pct, ctx.case_size_units, ctx.moq_cases,
                          fill_low_pct=ctx.fill_stress_pct, uncertainty_available=ctx.uncertainty_status == "AVAILABLE")


# ------------------------------------------------------------------------------------- supplier arrangement
def supplier_arrangement(plan: INV.OrderPlan) -> dict:
    """Arrangement status. Never 'confirmed': no supplier arrangement has been verified."""
    drops = [d for d in plan.drops if d.ordered_units > 0]
    weekend = sorted({INV.dow_of(d.arrival_day) for d in drops if INV.dow_of(d.arrival_day) >= 6})
    interval = (plan.drops[1].arrival_day - plan.drops[0].arrival_day) if len(plan.drops) > 1 else 7 if plan.drops else None
    if plan.arrangement == "UNSUPPORTED":
        status = "UNSUPPORTED"
    elif plan.arrangement == "SHORT_LIFE_RECURRING_DROPS" or weekend:
        status = "ASSUMED_UNCONFIRMED_REQUIRES_SUPPLIER_CONFIRMATION"
    else:
        status = "ASSUMED_STANDARD_WEEKLY_UNCONFIRMED"
    return {"arrangement": plan.arrangement, "status": status, "drop_interval_days": interval,
            "daily_drops": interval == 1, "weekend_drop_days": [WEEKDAYS[d - 1] for d in weekend],
            "standing_confirmation_required": status.startswith("ASSUMED_UNCONFIRMED_REQUIRES"),
            "provenance": "ASSUMED"}


# ---------------------------------------------------------------------------------------------- classify
def classify(ctx: DecisionContext, plan: INV.OrderPlan) -> tuple[str, list[str], str | None]:
    """(primary category, ordered reason codes, case type). Pure and deterministic."""
    reasons: list[str] = []
    flags = set(filter(None, (ctx.risk_flags or "").split("|")))
    if ctx.target_week in CHRISTMAS_WEEKS or ctx.christmas_any_horizon:
        reasons.append("CHRISTMAS_PERIOD")
    if "HOLIDAY_TARGET_WEEK" in flags:
        reasons.append("HOLIDAY_TARGET_WEEK")
    if plan.status == "NOT_SIZED_UNSUPPORTED_ARRANGEMENT":
        reasons.append("UNSUPPORTED_DELIVERY_ARRANGEMENT")
    if plan.status == "NOT_SIZED_UNCERTAINTY_UNAVAILABLE" or ctx.uncertainty_status != "AVAILABLE":
        reasons.append("UNCERTAINTY_UNAVAILABLE")
    if ctx.fill_shortfall_last_week:
        reasons.append("FILL_RATE_SHORTFALL_LAST_WEEK")
    if ctx.effective_lead_time_days >= ctx.remaining_life_days:
        reasons.append("LIFE_LEAD_TIME_TIGHT")
    sized = plan.status == "SIZED"
    arrangement = supplier_arrangement(plan)
    if sized:
        if plan.target_capped_at_p90:
            reasons.append("TARGET_ABOVE_P90_CAPPED")
        if plan.residual_shortfall_units > INV.TOL:
            reasons.append("SHORTAGE_REMAINING_AFTER_ORDER")
        gaps = plan.pre_delivery_gap_units
        if gaps["p50"] > INV.TOL:
            reasons.append("PRE_DELIVERY_SHORTAGE")
        elif gaps["p90"] > INV.TOL:
            reasons.append("PRE_DELIVERY_GAP_HIGHER_DEMAND_ONLY")
        exp = plan.existing_stock_expected_expiry_units or 0.0
        if exp > INV.TOL:
            reasons.append("EXPIRY_BEFORE_COVERAGE" if expiry_share_is_high(exp, ctx.p50, ctx.waste_high_above_pct)
                           else "EXPIRY_BEFORE_COVERAGE_MINOR")
        if (ctx.h4_point is not None and ctx.h1_point
                and abs(ctx.h4_point / ctx.h1_point - 1) * 100 > ctx.trend_divergence_threshold_pct):
            reasons.append("TREND_DIVERGENCE")
        net = sum(d.net_need_units for d in plan.drops if d.ordered_units > 0)
        if net > 0 and 100 * plan.rounding_excess_units / net > ROUNDING_EXCESS_WARNING_PCT:
            reasons.append("ROUNDING_EXCESS_HIGH")
        if arrangement["arrangement"] == "SHORT_LIFE_RECURRING_DROPS":
            reasons.append("SHORT_LIFE_ARRANGEMENT_ASSUMED")
        if arrangement["weekend_drop_days"]:
            reasons.append("WEEKEND_DELIVERY_ASSUMED")
        if arrangement["standing_confirmation_required"] and {
                "SHORTAGE_REMAINING_AFTER_ORDER", "PRE_DELIVERY_SHORTAGE", "EXPIRY_BEFORE_COVERAGE"} & set(reasons):
            reasons.append("ARRANGEMENT_FEASIBILITY_RISK")
    reasons = sorted(dict.fromkeys(reasons), key=REASON_ORDER.__getitem__)

    if not sized:
        category = CATEGORIES[0]
    elif "SHORTAGE_REMAINING_AFTER_ORDER" in reasons:
        category = CATEGORIES[1]
    elif "PRE_DELIVERY_SHORTAGE" in reasons:
        category = CATEGORIES[2]
    elif plan.ordered_units == 0:
        category = CATEGORIES[3]
    else:
        category = CATEGORIES[4]

    kinds = {REASONS[r][0] for r in reasons}
    case_type = ("MANDATORY_ESCALATION" if "MANDATORY" in kinds else "MANDATORY_REVIEW" if "BLOCK" in kinds
                 else "RISK_ESCALATION" if "MATERIAL" in kinds else None)
    return category, reasons, case_type


# ---------------------------------------------------------------------------------------------- recommend
def recommendation_id(ctx: DecisionContext) -> str:
    return f"REC-{ctx.scenario_id}-{ctx.store_id}-{ctx.product_id}-O{ctx.origin_week}"


def recommend(ctx: DecisionContext, plan: INV.OrderPlan) -> dict:
    category, reasons, case_type = classify(ctx, plan)
    sized = plan.status == "SIZED"
    eligible = sized and category != CATEGORIES[0]
    arrangement = supplier_arrangement(plan)
    drops = [{"drop": d.drop, "arrival": week_day_label(d.arrival_day), "arrival_day": d.arrival_day,
              "days_covered": d.days_covered, "last_sellable_day": d.expiry_day,
              "net_need_units": round(d.net_need_units, 3), "proposed_units": d.ordered_units,
              "case_rounding_excess_units": round(d.case_rounding_excess_units, 3),
              "moq_excess_units": round(d.moq_excess_units, 3), "valid_case_and_moq": d.valid}
             for d in plan.drops] if sized else []
    rec = {
        "recommendation_id": recommendation_id(ctx), "engine_version": ENGINE_VERSION,
        "scenario_id": ctx.scenario_id, "store_id": ctx.store_id, "product_id": ctx.product_id,
        "product_category": ctx.product_category, "origin_week": ctx.origin_week, "target_week": ctx.target_week,
        "decision_day": ctx.decision_day, "decision_date": ctx.decision_week_label or week_day_label(ctx.decision_day),
        "primary_category": category, "reason_codes": reasons,
        "material_reasons": [r for r in reasons if REASONS[r][0] in ("BLOCK", "MANDATORY", "MATERIAL")],
        "warnings": [r for r in reasons if REASONS[r][0] == "WARNING"],
        "case_type": case_type, "review_required": case_type is not None,
        "bulk_approval_allowed": case_type is None,
        "escalation_required": case_type == "MANDATORY_ESCALATION",
        "proposal_eligible": eligible,
        "proposed_order_units": plan.ordered_units if eligible else 0,
        "deliveries": drops if eligible else [],
        "supplier_arrangement": arrangement,
        "status": STATUS, "execution_status": EXECUTION_STATUS, "approval_event_id": None,
        "actions_taken": [],
        "evidence": _evidence(ctx, plan),
        "provenance_note": ("OBSERVED: identifiers, shelf life, supplier lead time. FORECAST: protected contract p10/p50/p90. "
                            "ASSUMED: DRAFT assumption values and delivery arrangements. CALCULATED: quantities, gaps, "
                            f"positions and projections. {ctx.stock_state_provenance}: stock on hand and scheduled deliveries."),
    }
    rec["explanation"] = explain(rec)
    return rec


def _evidence(ctx: DecisionContext, plan: INV.OrderPlan) -> dict:
    r = lambda x: None if x is None else round(float(x), 3)  # noqa: E731
    calc = {"status": plan.status}
    if plan.status == "SIZED":
        calc.update({
            "planning_weight": r(plan.planning_weight), "weekly_planning_target_units": r(plan.weekly_planning_target_units),
            "arrival": week_day_label(plan.arrival_day),
            "usable_stock_at_arrival_units_p50_projection": r(plan.usable_at_arrival_units),
            "pre_delivery_gap_units": {k: r(v) for k, v in plan.pre_delivery_gap_units.items()},
            "pre_delivery_position": plan.pre_delivery_position,
            "post_order_shortfall_units": {k: r(v) for k, v in plan.post_order_shortfall_units.items()},
            "post_order_position": plan.post_order_position,
            "residual_shortfall_units_planning_rate": r(plan.residual_shortfall_units),
            "existing_stock_expected_expiry_units_projection": r(plan.existing_stock_expected_expiry_units),
            "rounding_excess_units": r(plan.rounding_excess_units),
            "fill_rate_exposure_illustrative": {k: (r(v) if isinstance(v, float) else v)
                                                for k, v in plan.fill_rate_exposure.items()},
            "note": plan.projection_note})
    return {
        "observed": {"store_id": ctx.store_id, "product_id": ctx.product_id, "shelf_life_days": ctx.shelf_life_days,
                     "supplier_lead_time_days": ctx.lead_time_days},
        "forecast": {"source": ctx.forecast_contract_run or "forecast contract v1.0", "p10_units": r(ctx.p10),
                     "p50_units": r(ctx.p50), "p90_units": r(ctx.p90), "uncertainty_status": ctx.uncertainty_status},
        "assumed": {"assumption_set_id": ctx.assumption_set_id, "assumption_status": ctx.assumption_status,
                    "assumption_content_sha256": ctx.assumption_content_sha256,
                    "service_target_pct": ctx.service_target_pct, "case_size_units": ctx.case_size_units,
                    "moq_cases": ctx.moq_cases, "transit_age_days": ctx.transit_age_days,
                    "lead_time_adjustment_days": ctx.lead_time_adjustment_days,
                    "remaining_life_days": ctx.remaining_life_days, "planned_fill_pct": 100.0,
                    "label": "ASSUMED illustrative values from a DRAFT set; not validated business policy"},
        "calculated": calc,
        "stock_state": {"provenance": ctx.stock_state_provenance,
                        "note": "replay stock is simulated; simulated unmet demand is illustrative and is never presented as lost sales"},
    }


def explain(rec: dict) -> str:
    ev = rec["evidence"]["calculated"]
    parts = [f"Hypothetical, unapproved proposal for store {rec['store_id']}, product {rec['product_id']} "
             f"({rec['product_category']}), decided {rec['decision_date']} for target week {rec['target_week']}."]
    cat = rec["primary_category"]
    if cat == CATEGORIES[0]:
        why = " and ".join(REASONS[r][1].split(";")[0].lower() for r in rec["reason_codes"] if REASONS[r][0] == "BLOCK")
        parts.append(f"No actionable recommendation: {why}. Proposed quantity 0; a person must review this decision.")
    else:
        if rec["proposed_order_units"]:
            parts.append(f"Proposed {rec['proposed_order_units']:,} units in {len(rec['deliveries'])} "
                         f"deliver{'y' if len(rec['deliveries']) == 1 else 'ies'}, first arrival {ev['arrival']}, "
                         "each rounded up to whole cases and the minimum order"
                         f" (rounding adds {ev['rounding_excess_units']:,.1f} units).")
        else:
            parts.append("No replenishment required: usable stock covers the planning target for the coverage window.")
        if cat == CATEGORIES[2]:
            g = ev["pre_delivery_gap_units"]
            parts.append(f"Shortage before the proposed delivery: about {g['p10']:,.1f} to {g['p90']:,.1f} units at the "
                         "p10-p90 rates cannot be covered by this order (heuristic). Expedited delivery or transfer "
                         "are options requiring evidence; neither is assumed or arranged.")
        if cat == CATEGORIES[1]:
            parts.append(f"About {ev['residual_shortfall_units_planning_rate']:,.1f} units of planned demand remain "
                         "uncovered after the proposed order (heuristic).")
        if "EXPIRY_BEFORE_COVERAGE" in rec["reason_codes"] or "EXPIRY_BEFORE_COVERAGE_MINOR" in rec["reason_codes"]:
            parts.append(f"About {ev['existing_stock_expected_expiry_units_projection']:,.1f} units of existing stock are "
                         "projected to expire before they can be used (a projection, not realised waste).")
    sa = rec["supplier_arrangement"]
    if sa["standing_confirmation_required"]:
        parts.append("Delivery arrangement is assumed and unconfirmed"
                     + (f" (weekend drops: {', '.join(sa['weekend_drop_days'])})" if sa["weekend_drop_days"] else "")
                     + "; a standing supplier-confirmation case applies to this store-product series.")
    if rec["case_type"]:
        parts.append(f"Review required ({rec['case_type']}): {', '.join(rec['material_reasons'])}.")
    if rec["warnings"]:
        parts.append(f"Warnings: {', '.join(rec['warnings'])}.")
    parts.append("Status: hypothetical, unapproved, not executed. No order, price change, transfer or expedited "
                 "delivery has been made. Coverage figures are planning positions, not stockout probabilities.")
    return " ".join(parts)


def assert_safe(rec: dict) -> None:
    """Raise if a record claims approval, execution or an action."""
    if (rec["status"] != STATUS or rec["execution_status"] != EXECUTION_STATUS or rec["approval_event_id"] is not None
            or rec["actions_taken"]):
        raise AssertionError(f"Unsafe recommendation state: {rec['recommendation_id']}")
    if rec["primary_category"] == CATEGORIES[0] and rec["proposed_order_units"] != 0:
        raise AssertionError(f"Blocked recommendation has a quantity: {rec['recommendation_id']}")
    if "CHRISTMAS_PERIOD" in rec["reason_codes"] and (rec["case_type"] != "MANDATORY_ESCALATION" or rec["bulk_approval_allowed"]):
        raise AssertionError(f"Christmas recommendation not escalated: {rec['recommendation_id']}")
