"""Phase 2: assumption set v7 (config/assumptions/assumption_set_v7.json), DRAFT.

v7 carries every v6 parameter forward unchanged and adds the dynamic-pricing research parameters only. Validated by the
v1 rules (assumptions.validate, V1-V8) and then X1-X7. v1-v6 are never modified.

  X1  schema_version 7.0, version 7, a new assumption_set_id
  X2  supersedes names v6 and its recorded content hash; v6 still validates unchanged and DRAFT
  X3  every v6 parameter carried forward with value, provenance and allowed range unchanged
  X4  every parameter has unit, scope, provenance, evidence, rationale, allowed_range and sensitivity_range
  X5  all v7 parameters present, ASSUMED and unsupported by business data
  X6  the approved conditions hold: markdown only, orders fixed to the pricing-off pass, 7-day cooldown, at most 2 events
      in any 28 days, all four true responses; approval and execution off (v6)
  X7  scenarios identical to v6; status DRAFT and production_use false; dynamic_pricing statement present
"""
from __future__ import annotations

from pathlib import Path

from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v6 as V6

V7_FILE = A.ASSUMPTION_DIR / "assumption_set_v7.json"
V6_ID, V6_CONTENT_SHA256 = "AS-2026-10-23-v6", "024fb42dfd0a1670f249f12f23cf9d7aec0641801b21e3524239326c614e3c34"
REQUIRED_V7_PARAMETERS = ("dynamic_pricing_research_enabled", "dynamic_pricing_markdown_only",
                          "dynamic_pricing_ordering_interaction", "dynamic_pricing_cooldown_days",
                          "dynamic_pricing_max_events_per_window", "dynamic_pricing_event_window_days",
                          "dynamic_pricing_event_counting_rule", "dynamic_pricing_overlap_rule",
                          "dynamic_pricing_true_response_scenarios", "dynamic_pricing_demand_rounding_rule",
                          "dynamic_pricing_revenue_price_rule", "dynamic_pricing_mandatory_review_markdown_pct",
                          "dynamic_pricing_simulation_convention")
APPROVED = {"dynamic_pricing_markdown_only": True, "dynamic_pricing_ordering_interaction": "ORDERS_FIXED_TO_PRICING_OFF_PASS",
            "dynamic_pricing_cooldown_days": 7, "dynamic_pricing_max_events_per_window": 2,
            "dynamic_pricing_event_window_days": 28,
            "dynamic_pricing_true_response_scenarios": ["R0_NO_RESPONSE", "R1_LOW", "R2_CENTRAL", "R3_HIGH"]}


def load(path: Path = V7_FILE) -> dict:
    doc = A.load(path)
    validate(doc, V6.load())
    return doc


def validate(doc: dict, v6: dict) -> dict:
    errs = []
    if doc.get("schema_version") != "7.0" or doc.get("version") != 7 or doc.get("assumption_set_id") in (None, V6_ID):
        errs.append("v7 needs schema 7.0, version 7 and its own assumption_set_id")
    sup = doc.get("supersedes") or {}
    if sup.get("assumption_set_id") != V6_ID or sup.get("content_sha256") != V6_CONTENT_SHA256:
        errs.append("supersedes must reference v6 and its recorded content hash")
    if A.content_sha256(v6) != V6_CONTENT_SHA256 or v6["approval"]["status"] != "DRAFT":
        errs.append("assumption set v6 has changed: it must stay DRAFT with its recorded content hash")
    params = {p.get("key"): p for p in doc["parameters"]}
    for p in v6["parameters"]:
        q = params.get(p["key"])
        if q is None or q["value"] != p["value"] or q["provenance"] != p["provenance"] or q["allowed_range"] != p["allowed_range"]:
            errs.append(f"v6 parameter {p['key']} missing or changed")
    for key, p in params.items():
        missing = [f for f in B.REQUIRED_FIELDS if f not in p or p[f] in (None, "")]
        if missing:
            errs.append(f"{key}: missing {missing}")
    for key in REQUIRED_V7_PARAMETERS:
        if key not in params:
            errs.append(f"missing v7 parameter {key}")
        elif params[key]["provenance"] != "ASSUMED" or params[key]["supported_by_observed_business_data"] is not False:
            errs.append(f"{key} must be ASSUMED and unsupported by business data")
    g = {k: p["value"] for k, p in params.items()}
    for key, value in APPROVED.items():
        if g.get(key) != value:
            errs.append(f"{key} must equal the approved value {value!r}")
    if g.get("discount_recommendation_approval_enabled") is not False or \
            g.get("discount_recommendation_execution_enabled") is not False:
        errs.append("approval and execution must stay disabled")
    if doc["scenarios"] != v6["scenarios"]:
        errs.append("scenarios must be identical to v6")
    if doc["approval"].get("status") != "DRAFT" or doc["approval"].get("approved_by") or doc.get("production_use") is not False:
        errs.append("v7 must stay DRAFT, unapproved and production_use false")
    if "NOT VALIDATED FOR LIVE USE" not in doc["statements"].get("dynamic_pricing", ""):
        errs.append("dynamic_pricing statement must say the result is not validated for live use")
    if errs:
        raise A.AssumptionError("Assumption set v7 invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
            "content_sha256": A.content_sha256(doc), "parameters": len(params),
            "added_parameters": [k for k, p in params.items() if p.get("added_in_version") == 7]}


def dynamic_pricing_values(doc: dict) -> dict:
    """Phase 1 recommendation parameters (v6) plus every v7 parameter, plus the waste-risk and markdown rules."""
    keys = ("waste_risk_high_pct_of_p50", "waste_risk_moderate_pct_of_p50", "markdown_eligible_waste_categories",
            "markdown_min_sellable_days_after_investigate_by", "markdown_product_exclusions", "markdown_blocker_order")
    g = {p["key"]: p["value"] for p in doc["parameters"]}
    v7 = {p["key"]: p["value"] for p in doc["parameters"] if p.get("added_in_version") == 7}
    return {**V6.recommendation_values(doc), **{k: g[k] for k in keys}, **v7}
