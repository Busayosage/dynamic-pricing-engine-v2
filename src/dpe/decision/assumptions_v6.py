"""Phase 1: assumption set v6 (config/assumptions/assumption_set_v6.json), DRAFT.

v6 carries every v5 parameter forward unchanged and adds the discount-recommendation research parameters only.
Validated by the v1 rules (assumptions.validate, V1-V8) and then Y1-Y7. v1-v5 are never modified.

  Y1  schema_version 6.0, version 6, a new assumption_set_id
  Y2  supersedes names v5 and its recorded content hash; v5 still validates unchanged and DRAFT
  Y3  every v5 parameter carried forward with value, provenance and allowed range unchanged
  Y4  every parameter has unit, scope, provenance, evidence, rationale, allowed_range and sensitivity_range
  Y5  all v6 parameters present and unsupported by business data; response scenarios include R0..R3 and the
      decision weights cover only scenarios that exist (R0 never weighted)
  Y6  research ranking on; approval and execution off
  Y7  scenarios identical to v5; status DRAFT and production_use false; the discount_recommendation statement is
      present and says the result is not validated for live use
"""
from __future__ import annotations

from pathlib import Path

from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v5 as V5

V6_FILE = A.ASSUMPTION_DIR / "assumption_set_v6.json"
V5_ID, V5_CONTENT_SHA256 = "AS-2026-10-23-v5", "21180c904444f6c29dae7105e07f8b1e09828920711fcb2dc48d8fce2658706a"
RESPONSE_SCENARIOS = ("R0_NO_RESPONSE", "R1_LOW", "R2_CENTRAL", "R3_HIGH")
REQUIRED_V6_PARAMETERS = ("discount_recommendation_research_enabled", "discount_recommendation_approval_enabled",
                          "discount_recommendation_execution_enabled", "demand_response_scenarios_pct_per_point",
                          "demand_response_decision_weights", "recommendation_downside_scenario",
                          "recommendation_max_downside_loss_pct_of_at_risk_cost", "recommendation_min_expected_benefit_gbp",
                          "recommendation_min_expected_benefit_pct_of_at_risk_cost",
                          "expiry_disposal_cost_pct_of_unit_cost", "price_evidence_conflict_tolerance_pct",
                          "markdown_window_rule", "baseline_window_demand_rule")


def load(path: Path = V6_FILE) -> dict:
    doc = A.load(path)
    validate(doc, V5.load())
    return doc


def validate(doc: dict, v5: dict) -> dict:
    errs = []
    if doc.get("schema_version") != "6.0" or doc.get("version") != 6 or doc.get("assumption_set_id") in (None, V5_ID):
        errs.append("v6 needs schema 6.0, version 6 and its own assumption_set_id")
    sup = doc.get("supersedes") or {}
    if sup.get("assumption_set_id") != V5_ID or sup.get("content_sha256") != V5_CONTENT_SHA256:
        errs.append("supersedes must reference v5 and its recorded content hash")
    if A.content_sha256(v5) != V5_CONTENT_SHA256 or v5["approval"]["status"] != "DRAFT":
        errs.append("assumption set v5 has changed: it must stay DRAFT with its recorded content hash")
    params = {p.get("key"): p for p in doc["parameters"]}
    for p in v5["parameters"]:
        q = params.get(p["key"])
        if q is None or q["value"] != p["value"] or q["provenance"] != p["provenance"] or q["allowed_range"] != p["allowed_range"]:
            errs.append(f"v5 parameter {p['key']} missing or changed")
    for key, p in params.items():
        missing = [f for f in B.REQUIRED_FIELDS if f not in p or p[f] in (None, "")]
        if missing:
            errs.append(f"{key}: missing {missing}")
    for key in REQUIRED_V6_PARAMETERS:
        if key not in params:
            errs.append(f"missing v6 parameter {key}")
        elif params[key]["supported_by_observed_business_data"] is not False:
            errs.append(f"{key} must be unsupported by business data")
    g = {k: p["value"] for k, p in params.items()}
    resp, weights = g.get("demand_response_scenarios_pct_per_point", {}), g.get("demand_response_decision_weights", {})
    if tuple(resp) != RESPONSE_SCENARIOS:
        errs.append(f"demand-response scenarios must be {RESPONSE_SCENARIOS}")
    if not set(weights) <= set(resp) or "R0_NO_RESPONSE" in weights:
        errs.append("decision weights must cover existing scenarios only and never weight R0")
    if g.get("discount_recommendation_research_enabled") is not True or \
            g.get("discount_recommendation_approval_enabled") is not False or \
            g.get("discount_recommendation_execution_enabled") is not False:
        errs.append("research ranking must be on; approval and execution off")
    if doc["scenarios"] != v5["scenarios"]:
        errs.append("scenarios must be identical to v5")
    if doc["approval"].get("status") != "DRAFT" or doc["approval"].get("approved_by") or doc.get("production_use") is not False:
        errs.append("v6 must stay DRAFT, unapproved and production_use false")
    if "NOT VALIDATED FOR LIVE USE" not in doc["statements"].get("discount_recommendation", ""):
        errs.append("discount_recommendation statement must say the result is not validated for live use")
    if errs:
        raise A.AssumptionError("Assumption set v6 invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
            "content_sha256": A.content_sha256(doc), "parameters": len(params),
            "added_parameters": [k for k, p in params.items() if p.get("added_in_version") == 6]}


def recommendation_values(doc: dict) -> dict:
    """Pricing parameters (as v5) plus every v6 parameter."""
    v6 = {p["key"]: p["value"] for p in doc["parameters"] if p.get("added_in_version") == 6}
    return {**V5.pricing_values(doc), **v6}
