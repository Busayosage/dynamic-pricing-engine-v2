"""Step 5B-3b: inventory review queue v1.2 (weekly operational cases + standing supplier-confirmation cases).

Built from `recommendations.recommend` records. The accepted v1.1 queue (review_queue.py) is unchanged and remains the
queue of policy P1.

  * Weekly case: at most one per scenario x store x product x decision week, only when the recommendation has a case
    type. Every applicable reason is combined into that one case; overlapping flags never create a second case.
  * Standing case: at most one per scenario x store x product series whose delivery arrangement is assumed and needs
    supplier confirmation (recurring short-life drops, daily drops or weekend deliveries). It is kept apart from the
    weekly queue, so an assumed weekend drop alone never creates repeated weekly escalations.

Every case is PENDING_REVIEW with no approval event. Nothing in this module approves, rejects or executes anything.
Christmas cases and all mandatory cases are marked as excluded from any bulk or default approval.
"""
from __future__ import annotations

from dpe.decision.recommendations import CASE_TYPE_RANK, REASON_ORDER, REASONS

QUEUE_VERSION = "1.2"
CASE_STATUS = "PENDING_REVIEW"


def weekly_case_id(rec: dict) -> str:
    return f"CASE-W-{rec['scenario_id']}-{rec['store_id']}-{rec['product_id']}-O{rec['origin_week']}"


def standing_case_id(rec: dict) -> str:
    return f"CASE-S-{rec['scenario_id']}-{rec['store_id']}-{rec['product_id']}-SUPPLIER-ARRANGEMENT"


def _ordered(codes) -> list[str]:
    return sorted(dict.fromkeys(codes), key=REASON_ORDER.__getitem__)


def weekly_cases(recs: list[dict]) -> list[dict]:
    """One case per decision point that needs review; identical duplicate inputs collapse, conflicting ones fail."""
    by_id: dict[str, dict] = {}
    for rec in recs:
        if not rec["case_type"]:
            continue
        cid = weekly_case_id(rec)
        if cid in by_id:
            if by_id[cid]["recommendation_id"] != rec["recommendation_id"] or by_id[cid]["_source"] != rec:
                raise ValueError(f"Conflicting recommendations for one decision point: {cid}")
            continue
        material = [r for r in rec["reason_codes"] if REASONS[r][0] in ("BLOCK", "MANDATORY", "MATERIAL")]
        by_id[cid] = {
            "case_id": cid, "queue_version": QUEUE_VERSION, "case_kind": "WEEKLY_OPERATIONAL",
            "scenario_id": rec["scenario_id"], "store_id": rec["store_id"], "product_id": rec["product_id"],
            "product_category": rec["product_category"], "origin_week": rec["origin_week"],
            "target_week": rec["target_week"], "recommendation_id": rec["recommendation_id"],
            "primary_category": rec["primary_category"], "case_type": rec["case_type"],
            "reason_codes": _ordered(material), "warnings": list(rec["warnings"]),
            "proposed_order_units": rec["proposed_order_units"],
            "supplier_arrangement_status": rec["supplier_arrangement"]["status"],
            "standing_case_id": standing_case_id(rec) if rec["supplier_arrangement"]["standing_confirmation_required"] else None,
            "status": CASE_STATUS, "approval_event_id": None,
            "bulk_approval_allowed": False,
            "explanation": rec["explanation"], "_source": rec,
        }
    out = sorted(by_id.values(), key=lambda c: (-CASE_TYPE_RANK[c["case_type"]], c["scenario_id"], c["store_id"],
                                                c["product_id"], c["origin_week"]))
    return [{k: v for k, v in c.items() if k != "_source"} for c in out]


def standing_cases(recs: list[dict]) -> list[dict]:
    """One supplier-confirmation case per series with an assumed arrangement, listing the decisions relying on it."""
    by_id: dict[str, dict] = {}
    for rec in sorted(recs, key=lambda r: (r["scenario_id"], r["store_id"], r["product_id"], r["origin_week"])):
        sa = rec["supplier_arrangement"]
        if not sa["standing_confirmation_required"]:
            continue
        cid = standing_case_id(rec)
        c = by_id.setdefault(cid, {
            "case_id": cid, "queue_version": QUEUE_VERSION, "case_kind": "STANDING_SUPPLIER_CONFIRMATION",
            "scenario_id": rec["scenario_id"], "store_id": rec["store_id"], "product_id": rec["product_id"],
            "product_category": rec["product_category"], "reason_codes": ["SUPPLIER_CONFIRMATION_REQUIRED"],
            "arrangement": sa["arrangement"], "arrangement_status": sa["status"], "drop_interval_days": set(),
            "daily_drops": False, "weekend_drop_days": set(), "first_origin_week": rec["origin_week"],
            "decision_weeks": [], "decisions_with_feasibility_risk": [], "evidence_warnings": set(),
            "status": CASE_STATUS, "approval_event_id": None, "bulk_approval_allowed": False,
            "question": ("Confirm whether the supplier can deliver on the assumed schedule (including any daily or "
                         "weekend drops). Until confirmed, the arrangement remains ASSUMED and unconfirmed."),
        })
        if rec["origin_week"] in c["decision_weeks"]:
            continue  # the same decision supplied twice
        c["decision_weeks"].append(rec["origin_week"])
        if sa["drop_interval_days"] is not None:
            c["drop_interval_days"].add(sa["drop_interval_days"])
        c["daily_drops"] = c["daily_drops"] or sa["daily_drops"]
        c["weekend_drop_days"].update(sa["weekend_drop_days"])
        c["evidence_warnings"].update(w for w in rec["warnings"] if w in ("SHORT_LIFE_ARRANGEMENT_ASSUMED", "WEEKEND_DELIVERY_ASSUMED"))
        if "ARRANGEMENT_FEASIBILITY_RISK" in rec["reason_codes"]:
            c["decisions_with_feasibility_risk"].append(rec["origin_week"])
    order = {d: i for i, d in enumerate(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"))}
    for c in by_id.values():
        c["drop_interval_days"] = sorted(c["drop_interval_days"])
        c["weekend_drop_days"] = sorted(c["weekend_drop_days"], key=order.__getitem__)
        c["evidence_warnings"] = _ordered(c["evidence_warnings"])
    return [by_id[k] for k in sorted(by_id)]


def contract_gate_cases(contract, simulated_keys: set, scenario_id: str) -> list[dict]:
    """Cases for contract decision points that were NOT simulated (e.g. origins before the replay starts), using the
    same contract gates as the v1.1 queue: Christmas in any horizon -> MANDATORY_ESCALATION; bounds unavailable in
    any horizon -> MANDATORY_REVIEW. No recommendation exists for these points, so no quantity is proposed."""
    key = ["store_id", "product_id", "origin_week"]
    c = contract.assign(_x=contract["target_week"].isin((51, 52)), _m=contract["uncertainty_status"] != "AVAILABLE")
    g = c.groupby(key).agg(christmas=("_x", "any"), missing=("_m", "any"),
                           product_category=("product_category", "first")).reset_index()
    out = []
    for r in g.itertuples(index=False):
        if (int(r.store_id), int(r.product_id), int(r.origin_week)) in simulated_keys or not (r.christmas or r.missing):
            continue
        reasons = _ordered((["UNCERTAINTY_UNAVAILABLE"] if r.missing else []) + (["CHRISTMAS_PERIOD"] if r.christmas else []))
        stub = {"scenario_id": scenario_id, "store_id": int(r.store_id), "product_id": int(r.product_id),
                "origin_week": int(r.origin_week)}
        out.append({
            "case_id": weekly_case_id(stub), "queue_version": QUEUE_VERSION, "case_kind": "WEEKLY_CONTRACT_GATE",
            **stub, "product_category": r.product_category, "target_week": int(r.origin_week) + 1,
            "recommendation_id": None, "primary_category": "NO_ACTIONABLE_RECOMMENDATION_MANDATORY_REVIEW",
            "case_type": "MANDATORY_ESCALATION" if r.christmas else "MANDATORY_REVIEW", "reason_codes": reasons,
            "warnings": [], "proposed_order_units": 0, "supplier_arrangement_status": None, "standing_case_id": None,
            "status": CASE_STATUS, "approval_event_id": None, "bulk_approval_allowed": False,
            "explanation": ("No simulated decision exists for this decision point (outside the replay window); "
                            f"contract gates require review: {', '.join(reasons)}. No quantity is proposed. "
                            "Status: pending review, unapproved, not executed."),
        })
    return out


def queue_summary(weekly: list[dict], standing: list[dict]) -> dict:
    by_type: dict[str, int] = {}
    for c in weekly:
        by_type[c["case_type"]] = by_type.get(c["case_type"], 0) + 1
    keys = [(c["scenario_id"], c["store_id"], c["product_id"], c["origin_week"]) for c in weekly]
    return {"weekly_cases": len(weekly), "weekly_by_type": dict(sorted(by_type.items())),
            "standing_supplier_confirmation_cases": len(standing),
            "duplicate_weekly_cases": len(keys) - len(set(keys)),
            "approved_or_executed": sum(c["approval_event_id"] is not None or c["status"] != CASE_STATUS
                                        for c in weekly + standing)}
