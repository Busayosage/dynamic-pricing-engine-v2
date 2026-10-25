"""Stage 6B: assumption set v3 (config/assumptions/assumption_set_v3.json), DRAFT.

v3 carries every v2 parameter forward unchanged and adds the waste-risk intelligence parameters only. It is validated by
the v1 rules (assumptions.validate, V1-V8) and then by X1-X8 below. v1 and v2 are never modified.

  X1  schema_version 3.0, version 3, a new assumption_set_id
  X2  supersedes names v2 and its recorded content hash; v2 (and through it v1) still validate unchanged and DRAFT
  X3  every v2 parameter is carried forward with value, provenance and allowed range unchanged
  X4  every parameter has unit, scope, provenance, evidence, rationale, allowed_range and sensitivity_range
  X5  all waste-risk parameters are present; moderate < high; advisory only; discounts disabled
  X6  scenarios identical to v2 (SC1, SC2, SC3, SF75)
  X7  status DRAFT and production_use false
  X8  new parameters are ASSUMED and not supported by observed business data
"""
from __future__ import annotations

from pathlib import Path

from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B

V3_FILE = A.ASSUMPTION_DIR / "assumption_set_v3.json"
V2_ID, V2_CONTENT_SHA256 = "AS-2026-10-23-v2", "ddc95ec125bb715ba63de9c2fe90de7319eb6cc38470c327c2585eb916cf989f"
REQUIRED_V3_PARAMETERS = ("waste_risk_high_pct_of_p50", "waste_risk_moderate_pct_of_p50", "waste_risk_zero_p50_rule",
                          "waste_risk_classification_driver", "waste_risk_recorded_wastage_window_weeks",
                          "waste_risk_simulated_history_window_weeks", "waste_risk_max_reasons",
                          "waste_risk_advisory_only", "waste_risk_discounts_enabled")


def load(path: Path = V3_FILE) -> dict:
    doc = A.load(path)
    validate(doc, B.load())
    return doc


def validate(doc: dict, v2: dict) -> dict:
    errs = []
    if doc.get("schema_version") != "3.0" or doc.get("version") != 3 or doc.get("assumption_set_id") in (None, V2_ID, B.V1_ID):
        errs.append("v3 needs schema 3.0, version 3 and its own assumption_set_id")
    sup = doc.get("supersedes") or {}
    if sup.get("assumption_set_id") != V2_ID or sup.get("content_sha256") != V2_CONTENT_SHA256:
        errs.append("supersedes must reference v2 and its recorded content hash")
    if A.content_sha256(v2) != V2_CONTENT_SHA256 or v2["approval"]["status"] != "DRAFT":
        errs.append("assumption set v2 has changed: it must stay DRAFT with its recorded content hash")
    params = {p.get("key"): p for p in doc["parameters"]}
    for p in v2["parameters"]:
        q = params.get(p["key"])
        if q is None or q["value"] != p["value"] or q["provenance"] != p["provenance"] or q["allowed_range"] != p["allowed_range"]:
            errs.append(f"v2 parameter {p['key']} missing or changed")
    for key, p in params.items():
        missing = [f for f in B.REQUIRED_FIELDS if f not in p or p[f] in (None, "")]
        if missing:
            errs.append(f"{key}: missing {missing}")
    for key in REQUIRED_V3_PARAMETERS:
        if key not in params:
            errs.append(f"missing v3 parameter {key}")
        elif params[key]["provenance"] != "ASSUMED" or params[key]["supported_by_observed_business_data"] is not False:
            errs.append(f"{key} must be ASSUMED and unsupported by business data")
    g = {k: p["value"] for k, p in params.items()}
    if not g.get("waste_risk_moderate_pct_of_p50", 0) < g.get("waste_risk_high_pct_of_p50", 0):
        errs.append("waste_risk_moderate_pct_of_p50 must be below waste_risk_high_pct_of_p50")
    if g.get("waste_risk_advisory_only") is not True or g.get("waste_risk_discounts_enabled") is not False:
        errs.append("waste risk must be advisory only with discounts disabled")
    if doc["scenarios"] != v2["scenarios"]:
        errs.append("scenarios must be identical to v2")
    for sid, sc in doc["scenarios"].items():
        for k, v in sc["overrides"].items():
            if k not in params:
                errs.append(f"{sid}: override of unknown key {k}")
            else:
                A._check_range(params[k], v, errs)
    if doc["approval"].get("status") != "DRAFT" or doc["approval"].get("approved_by") or doc.get("production_use") is not False:
        errs.append("v3 must stay DRAFT, unapproved and production_use false")
    if errs:
        raise A.AssumptionError("Assumption set v3 invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
            "content_sha256": A.content_sha256(doc), "parameters": len(params),
            "added_parameters": [k for k, p in params.items() if p.get("added_in_version") == 3]}


def waste_risk_values(doc: dict) -> dict:
    """The waste-risk parameters as a flat dict."""
    return {p["key"]: p["value"] for p in doc["parameters"] if p["key"].startswith("waste_risk_")}
