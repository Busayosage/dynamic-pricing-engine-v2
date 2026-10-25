"""Phase 2: per-decision dynamic pricing policy (SIMULATED RESEARCH — NOT VALIDATED FOR LIVE USE).

Called by the pricing replay (`replay_pricing.py`) once per store-product at every weekly decision, AFTER the
replenishment order has been decided. It only reads decision-time information:

  1 state assessment   the Stage 6B waste-risk class and the Stage 7B eligibility rules (`waste_risk.classify`,
                       `markdown_eligibility.blockers_for` / `classify`, unchanged) applied to the current simulated
                       state: standard expiry projection, batches already received, the forecast contract row for the
                       origin, Christmas in any horizon and the recorded promotion in the origin week
  2 temporal guards    7-day cooldown between selections, at most 2 events in any rolling 28 days, no selection while
                       an earlier window is still in force (assumption set v7)
  3 pricing choice     the Phase 1 engine (`discount_recommendation.recommend_line`, unchanged) with the v6 BELIEF
                       (decision weights over R1-R3); the TRUE response used to simulate outcomes is never visible here
  4 review tags        PENDING_HUMAN_REVIEW on every selection; MANDATORY_REVIEW for deep or repeat markdowns or an
                       open inventory review case

Event counting rule (v7): an event is counted on the decision day it is SELECTED. Every selected markdown is applied in
the simulation (as if approved), so selected and hypothetically applied events are the same set, and the cooldown,
rolling limit and overlap rule all use selection days and selected windows.
Markdown only: options are 0-25% reductions from the reference price; a price above the reference is impossible.
"""
from __future__ import annotations

import math

from dpe.decision import discount_recommendation as R
from dpe.decision import markdown_eligibility as M
from dpe.decision import waste_risk as W

STATUS = "SIMULATED"
APPROVAL_STATUS = "HYPOTHETICAL_UNAPPROVED"
EXECUTION_STATUS = "NOT_EXECUTED"
APPLICATION = "SIMULATED_AS_IF_APPROVED"
SELECTED = "MARKDOWN_SELECTED"
GUARD_LABELS = {
    "COOLDOWN": "Fewer than 7 days since the last markdown selection for this line",
    "EVENT_LIMIT": "Already two markdown events in the last 28 days",
    "WINDOW_IN_FORCE": "An earlier markdown window is still in force",
}
OUTCOME_LABELS = {
    SELECTED: "Markdown selected (simulated, as if approved)",
    "NOT_ELIGIBLE": "No markdown — not eligible for markdown review",
    "GUARD_BLOCKED": "No markdown — blocked by a timing guard",
    **{k: f"No markdown — {v.split(' — ', 1)[-1].lower()}" for k, v in R.STATUS_LABELS.items() if k != R.RECOMMEND},
}


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def earliest_batch_last_day(received: dict, decision_day: int):
    """Earliest last sellable day among deliveries received before the decision day and still in date on it — the same
    rule as `waste_risk.earliest_batch_expiry`, applied to the simulated state (units left per batch not used)."""
    days = [dl["expiry_day"] for day, dls in received.items() if day < decision_day for dl in dls
            if dl["delivered_units"] > 0 and dl["expiry_day"] >= decision_day]
    return min(days) if days else None


def assess_state(product_id: int, decision_day: int, arrangement: str, h1row, h4row, std: dict, batch_last_day,
                 christmas_any_horizon: bool, recorded_discount_pct, params: dict) -> dict:
    """Waste-risk class and markdown eligibility at the decision, from decision-time information only."""
    bounds = h1row is not None and h1row["uncertainty_status"] == "AVAILABLE" and \
        (h4row is None or h4row["uncertainty_status"] == "AVAILABLE")
    supported = arrangement != "UNSUPPORTED"
    proj = std.get("std_existing_expiry_projection_units")
    p50 = None if h1row is None else h1row["median_p50_units"]
    cat, _ = W.classify(proj, p50, params["waste_risk_high_pct_of_p50"], params["waste_risk_moderate_pct_of_p50"],
                        bounds, supported)
    units = None if _missing(proj) else round(max(0.0, float(proj)), 1)
    has_batch = batch_last_day is not None
    investigate = int(max(decision_day, batch_last_day - 1)) if cat in ("HIGH", "MODERATE") and has_batch else None
    sellable = (int(batch_last_day) - investigate) if investigate is not None else None
    shortage = (not _missing(std.get("std_pre_delivery_shortage"))) and bool(std.get("std_pre_delivery_shortage"))
    blockers = M.blockers_for(christmas_any_horizon, shortage, recorded_discount_pct, product_id,
                              params["markdown_product_exclusions"], sellable,
                              params["markdown_min_sellable_days_after_investigate_by"], params["markdown_blocker_order"])
    eligibility = M.classify(cat, has_batch and investigate is not None, blockers, params["markdown_eligible_waste_categories"])
    return {"waste_risk_category": cat, "at_risk_units": units, "earliest_batch_last_day": batch_last_day,
            "investigate_by_day": investigate, "sellable_days_after_investigate_by": sellable,
            "shortage_before_delivery": shortage, "christmas_any_horizon": christmas_any_horizon,
            "eligibility": eligibility, "blocker_codes": "|".join(blockers)}


def guard_check(history: list[dict], decision_day: int, params: dict) -> list[str]:
    """Timing guards on this line's earlier SELECTED events (selection days and selected windows)."""
    found = []
    if history:
        last = history[-1]
        if decision_day - last["decision_day"] < params["dynamic_pricing_cooldown_days"]:
            found.append("COOLDOWN")
        if any(e["window_end_day"] >= decision_day for e in history):
            found.append("WINDOW_IN_FORCE")
    recent = [e for e in history if decision_day - params["dynamic_pricing_event_window_days"] < e["decision_day"] <= decision_day]
    if len(recent) >= params["dynamic_pricing_max_events_per_window"]:
        found.append("EVENT_LIMIT")
    return found


def decide(k, T: int, decision_day: int, state: dict, h1row, reference_price, gross_margin_pct, min_margin_pct,
           recorded_price, promotion_active: bool, history: list[dict], open_review_case: bool, params: dict) -> dict:
    """One pricing record for one line at one decision. `history` holds this line's earlier SELECTED events."""
    rec = {"Store_ID": k[0], "Product_ID": k[1], "origin_week": T, "decision_day": decision_day, "target_week": T + 1,
           **state, "reference_price": reference_price, "recorded_price_origin_week": recorded_price,
           "promotion_active": promotion_active, "guard_codes": "", "outcome": None, "markdown_pct": 0,
           "markdown_price": None, "window_start_day": None, "window_end_day": None, "window_days": None,
           "expected_delta_belief": None, "downside_delta_belief": None, "phase1_status": None, "explanation": "",
           "review_tags": "", "event_id": None, "status": STATUS, "approval_status": APPROVAL_STATUS,
           "execution_status": EXECUTION_STATUS, "application": None, "approval_event_id": None, "proposal_id": None}
    if state["eligibility"] != "ELIGIBLE_FOR_MARKDOWN_REVIEW":
        rec.update(outcome="NOT_ELIGIBLE", explanation=f"No markdown: {M.CLASS_LABELS[state['eligibility']].lower()}"
                   + (f" ({state['blocker_codes'].replace('|', ', ').lower()})" if state["blocker_codes"] else "") + ".")
        return rec
    guards = guard_check(history, decision_day, params)
    if guards:
        rec.update(outcome="GUARD_BLOCKED", guard_codes="|".join(guards),
                   explanation="No markdown: " + "; ".join(GUARD_LABELS[g].lower() for g in guards) + ".")
        return rec
    window = R.window_days(state["investigate_by_day"], state["earliest_batch_last_day"])
    p = h1row
    line, _ = R.recommend_line(reference_price, gross_margin_pct, min_margin_pct, state["at_risk_units"], window,
                               None if p is None else p["lower_p10_units"], None if p is None else p["median_p50_units"],
                               None if p is None else p["upper_p90_units"], promotion_active, recorded_price, params)
    rec.update(phase1_status=line["recommendation_status"], expected_delta_belief=line.get("expected_delta"),
               downside_delta_belief=line.get("downside_delta"), explanation=line["explanation"])
    if line["recommendation_status"] != R.RECOMMEND:
        rec["outcome"] = line["recommendation_status"]
        return rec
    d = int(line["recommended_markdown_pct"])
    if not 0 < d <= params["max_discount_pct"]:
        raise AssertionError("markdown outside (0, max] — markdown-only rule violated")
    repeat = any(decision_day - params["dynamic_pricing_event_window_days"] < e["decision_day"] for e in history)
    tags = ["PENDING_HUMAN_REVIEW"]
    if d >= params["dynamic_pricing_mandatory_review_markdown_pct"] or repeat or open_review_case:
        tags.append("MANDATORY_REVIEW")
    rec.update(outcome=SELECTED, markdown_pct=d, markdown_price=reference_price * (1 - d / 100),
               window_start_day=state["investigate_by_day"], window_end_day=int(state["earliest_batch_last_day"]),
               window_days=window, review_tags="|".join(tags), application=APPLICATION,
               event_id=f"DPE-{k[0]}-{k[1]}-O{T}")
    return rec
