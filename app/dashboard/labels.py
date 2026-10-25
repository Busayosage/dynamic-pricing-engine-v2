"""Plain-English labels for the codes stored in the saved outputs. Display only: the codes themselves are unchanged
and remain visible in the dashboard's technical-detail sections."""
from __future__ import annotations

import re

REASONS = {
    "CHRISTMAS_PERIOD": "Christmas trading week — a manager must review",
    "UNCERTAINTY_UNAVAILABLE": "Forecast range not available — no automatic order",
    "UNSUPPORTED_DELIVERY_ARRANGEMENT": "Supplier cannot deliver in time — no automatic order",
    "PRE_DELIVERY_SHORTAGE": "Likely to run short before the next delivery arrives",
    "PRE_ORDER_SHORTAGE": "Likely to run short before the next delivery arrives",
    "SHORTAGE_REMAINING_AFTER_ORDER": "Still short after the proposed order",
    "POST_ORDER_SHORTFALL": "Still short after the proposed order",
    "EXPIRY_BEFORE_COVERAGE": "A large share of current stock may go out of date before it sells",
    "EXPIRY_BEFORE_COVERAGE_MINOR": "Some current stock may go out of date before it sells",
    "WASTE_HIGH_EXISTING_STOCK": "High expected waste from current stock",
    "ARRANGEMENT_FEASIBILITY_RISK": "Depends on an unconfirmed delivery schedule and still has a gap",
    "FILL_RATE_SHORTFALL_LAST_WEEK": "A delivery last week arrived short",
    "TREND_DIVERGENCE": "Short-range and longer-range forecasts disagree",
    "PRE_DELIVERY_GAP_HIGHER_DEMAND_ONLY": "Could run short before delivery, but only if demand is high",
    "SHORT_LIFE_ARRANGEMENT_ASSUMED": "Frequent fresh deliveries are assumed, not confirmed",
    "WEEKEND_DELIVERY_ASSUMED": "A weekend delivery is assumed, not confirmed",
    "LIFE_LEAD_TIME_TIGHT": "Delivery takes as long as the product's shelf life",
    "LIFE_LEAD_TIME_TIGHT_WARNING": "Delivery takes as long as the product's shelf life",
    "TARGET_ABOVE_P90_CAPPED": "Service target capped at the high-demand forecast",
    "HOLIDAY_TARGET_WEEK": "Holiday week",
    "ROUNDING_EXCESS_HIGH": "Rounding to full cases adds more than 10%",
    "SUPPLIER_CONFIRMATION_REQUIRED": "Supplier delivery schedule needs confirming",
}
CATEGORIES = {
    "ROUTINE_REPLENISHMENT_PROPOSAL": "Routine order",
    "NO_REPLENISHMENT_REQUIRED": "No order needed",
    "SHORTAGE_BEFORE_PROPOSED_DELIVERY": "Order proposed, but stock may run short before it arrives",
    "SHORTAGE_REMAINING_AFTER_PROPOSED_ORDER": "Order proposed, but still short afterwards",
    "NO_ACTIONABLE_RECOMMENDATION_MANDATORY_REVIEW": "No automatic order — a manager must decide",
}
CASE_TYPES = {
    "MANDATORY_ESCALATION": "Must be escalated",
    "MANDATORY_REVIEW": "Must be reviewed",
    "RISK_ESCALATION": "Review recommended",
    None: "No review needed",
}
POSITIONS = {
    "COVERS_P90_RATE": "Covered even if demand is high",
    "COVERS_P50_RATE": "Covered at typical demand",
    "COVERS_P10_RATE_ONLY": "Covered only if demand is low",
    "BELOW_P10_RATE": "Short even if demand is low",
}
ARRANGEMENTS = {
    "LONG_LIFE_WEEKLY": "One delivery per week",
    "SHORT_LIFE_RECURRING_DROPS": "Several fresh deliveries per week",
    "UNSUPPORTED": "Not supported (lead time too long)",
}
SUPPLIER_STATUS = {
    "ASSUMED_STANDARD_WEEKLY_UNCONFIRMED": "Standard weekly delivery — assumed, not confirmed",
    "ASSUMED_UNCONFIRMED_REQUIRES_SUPPLIER_CONFIRMATION": "Needs supplier confirmation — frequent or weekend deliveries assumed",
    "UNSUPPORTED": "Not supported — supplier cannot deliver in time",
}
ACTION_STATUS = {
    "HYPOTHETICAL_UNAPPROVED": "Hypothetical proposal — not approved, not ordered",
    "REVIEW_REQUIRED_NO_ACTION": "No order proposed — review required",
    "NO_ACTION_PROPOSED": "No order proposed",
}
WASTE_CATEGORIES = {"HIGH": "High expiry risk", "MODERATE": "Moderate expiry risk", "LOW": "Low expiry risk",
                    "INSUFFICIENT_INFORMATION": "Insufficient information"}
WASTE_REASONS = {
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
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ALL_CODES = {**REASONS, **CATEGORIES, **{k: v for k, v in CASE_TYPES.items() if k}, **POSITIONS, **ARRANGEMENTS,
             **SUPPLIER_STATUS, **ACTION_STATUS, **WASTE_REASONS}  # short words (HIGH, LOW) are not substituted
_CODE_RE = re.compile("|".join(sorted(map(re.escape, ALL_CODES), key=len, reverse=True)))


def reason(code: str) -> str:
    return REASONS.get(code, code.replace("_", " ").capitalize())


def reasons(codes) -> list[str]:
    out = []
    for c in codes:
        label = reason(c)
        if label not in out:
            out.append(label)
    return out


def case_type(code) -> str:
    return CASE_TYPES.get(code if isinstance(code, str) else None, str(code))


def label(table: dict, code) -> str:
    if not isinstance(code, str):
        return "—"
    return table.get(code, code.replace("_", " ").capitalize())


def humanize(text: str) -> str:
    """Replace any stored code inside an explanation sentence with its plain-English label."""
    if not isinstance(text, str):
        return ""
    return _CODE_RE.sub(lambda m: f"“{ALL_CODES[m.group(0)].lower()}”", text)


def day_label(day) -> str:
    """Replay day number (day 1 = Monday of week 1) as 'Wed, week 34'."""
    try:
        d = int(day)
    except (TypeError, ValueError):
        return "—"
    return f"{WEEKDAYS[(d - 1) % 7][:3]}, week {(d - 1) // 7 + 1}"
