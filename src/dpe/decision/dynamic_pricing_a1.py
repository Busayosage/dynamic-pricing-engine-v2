"""Amendment A1 to the Phase 2 pricing policy: cooldown measured from the END of the previous markdown window.

Research-rule amendment approved 2026-10-23 (assumption set v8, DRAFT). `dynamic_pricing.py` (the frozen Phase 2
policy behind run 20261023-233225_dynamic_pricing_evaluation) is imported, never edited.

Rule: a new markdown for a store-product may START only after `dynamic_pricing_cooldown_days` (7) complete days have
elapsed since the previous simulated markdown window ENDED:

    candidate window start >= previous window end + 7 + 1

It is checked at the existing weekly decision against the candidate window start (the investigate-by day), so the
decision cadence is unchanged; a blocked line is reconsidered at the next weekly decision, never rescheduled. The rolling
2-in-28-days limit and the no-overlap rule are kept exactly as in v7 (`dynamic_pricing.guard_check` with its
selection-day cooldown switched off). Events are still counted when selected.
"""
from __future__ import annotations

from dpe.decision import dynamic_pricing as DP
from dpe.decision.dynamic_pricing import (APPLICATION, APPROVAL_STATUS, EXECUTION_STATUS, OUTCOME_LABELS,  # noqa: F401
                                          SELECTED, STATUS, _missing, assess_state, earliest_batch_last_day)

POLICY_VERSION = "A1"
GUARD_LABELS = {**DP.GUARD_LABELS,
                "COOLDOWN": "Fewer than 7 complete days since the previous markdown window for this line ended"}
_RESET = {"markdown_pct": 0, "markdown_price": None, "window_start_day": None, "window_end_day": None,
          "window_days": None, "expected_delta_belief": None, "downside_delta_belief": None, "phase1_status": None,
          "review_tags": "", "event_id": None, "application": None}


def cooldown_blocks(history: list[dict], window_start, params: dict) -> bool:
    """True when the candidate window would start before `cooldown_days` complete days after the latest window ended."""
    if not history or window_start is None:
        return False
    last_end = max(e["window_end_day"] for e in history)
    return int(window_start) < int(last_end) + params["dynamic_pricing_cooldown_days"] + 1


def guard_check(history: list[dict], decision_day: int, window_start, params: dict) -> list[str]:
    """A1 cooldown first, then the unchanged v7 overlap and rolling-limit guards."""
    if params.get("dynamic_pricing_cooldown_basis") != "END_OF_PREVIOUS_MARKDOWN_WINDOW":
        raise ValueError("amendment A1 needs assumption set v8 (cooldown basis END_OF_PREVIOUS_MARKDOWN_WINDOW)")
    rest = DP.guard_check(history, decision_day, dict(params, dynamic_pricing_cooldown_days=0))
    return (["COOLDOWN"] if cooldown_blocks(history, window_start, params) else []) + rest


def decide(k, T: int, decision_day: int, state: dict, h1row, reference_price, gross_margin_pct, min_margin_pct,
           recorded_price, promotion_active: bool, history: list[dict], open_review_case: bool, params: dict) -> dict:
    """Same inputs and record as `dynamic_pricing.decide`; only the cooldown basis differs."""
    guards = guard_check(history, decision_day, state.get("investigate_by_day"), params) \
        if state["eligibility"] == "ELIGIBLE_FOR_MARKDOWN_REVIEW" else []
    if not guards:  # the v7 policy with its own cooldown off: overlap and rolling limit are re-checked identically
        return DP.decide(k, T, decision_day, state, h1row, reference_price, gross_margin_pct, min_margin_pct,
                         recorded_price, promotion_active, history, open_review_case,
                         dict(params, dynamic_pricing_cooldown_days=0))
    rec = DP.decide(k, T, decision_day, {**state, "eligibility": "NOT_CONSIDERED", "blocker_codes": ""}, h1row,
                    reference_price, gross_margin_pct, min_margin_pct, recorded_price, promotion_active, history,
                    open_review_case, params)  # builds the empty record without running the pricing choice
    rec.update(_RESET, eligibility=state["eligibility"], blocker_codes=state["blocker_codes"], outcome="GUARD_BLOCKED",
               guard_codes="|".join(guards),
               explanation="No markdown: " + "; ".join(GUARD_LABELS[g].lower() for g in guards) + ".")
    return rec
