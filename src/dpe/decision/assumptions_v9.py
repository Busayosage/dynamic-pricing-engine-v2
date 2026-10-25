"""Phase 3: assumption set v9 (config/assumptions/assumption_set_v9.json), DRAFT.

v9 carries every v8 parameter forward unchanged and adds only the waste-intervention rule parameters. Validated by the
v1 rules and then U1-U5. v1-v8 are never modified.

  U1  schema_version 9.0, version 9, a new assumption_set_id
  U2  supersedes names v8 and its recorded content hash; v8 still validates unchanged and DRAFT
  U3  every v8 parameter carried forward unchanged (value, provenance, allowed range)
  U4  all v9 parameters present, ASSUMED and unsupported by business data
  U5  scenarios identical to v8; DRAFT, production_use false; waste_interventions statement says INVESTIGATE ONLY
"""
from __future__ import annotations

from pathlib import Path

from dpe.decision import assumptions as A
from dpe.decision import assumptions_v8 as V8

V9_FILE = A.ASSUMPTION_DIR / "assumption_set_v9.json"
V8_ID, V8_CONTENT_SHA256 = "AS-2026-10-23-v8", "7032e56f2a8b37fb39ea44e6f3dce154028e176cf0e31d67cfb4ac63bb811866"
REQUIRED_V9_PARAMETERS = ("waste_intervention_at_risk_categories", "waste_intervention_transfer_pairing_rule",
                          "waste_intervention_donation_min_units", "waste_intervention_evidence_levels",
                          "waste_intervention_tie_order", "waste_intervention_value_basis",
                          "waste_intervention_markdown_context_run")


def load(path: Path = V9_FILE) -> dict:
    doc = A.load(path)
    validate(doc, V8.load())
    return doc


def validate(doc: dict, v8: dict) -> dict:
    errs = []
    if doc.get("schema_version") != "9.0" or doc.get("version") != 9 or doc.get("assumption_set_id") in (None, V8_ID):
        errs.append("v9 needs schema 9.0, version 9 and its own assumption_set_id")
    sup = doc.get("supersedes") or {}
    if sup.get("assumption_set_id") != V8_ID or sup.get("content_sha256") != V8_CONTENT_SHA256:
        errs.append("supersedes must reference v8 and its recorded content hash")
    if A.content_sha256(v8) != V8_CONTENT_SHA256 or v8["approval"]["status"] != "DRAFT":
        errs.append("assumption set v8 has changed: it must stay DRAFT with its recorded content hash")
    params = {p.get("key"): p for p in doc["parameters"]}
    for p in v8["parameters"]:
        q = params.get(p["key"])
        if q is None or q["value"] != p["value"] or q["provenance"] != p["provenance"] or q["allowed_range"] != p["allowed_range"]:
            errs.append(f"v8 parameter {p['key']} missing or changed")
    for key in REQUIRED_V9_PARAMETERS:
        if key not in params:
            errs.append(f"missing v9 parameter {key}")
        elif params[key]["provenance"] != "ASSUMED" or params[key]["supported_by_observed_business_data"] is not False:
            errs.append(f"{key} must be ASSUMED and unsupported by business data")
    if doc["scenarios"] != v8["scenarios"]:
        errs.append("scenarios must be identical to v8")
    if doc["approval"].get("status") != "DRAFT" or doc["approval"].get("approved_by") or doc.get("production_use") is not False:
        errs.append("v9 must stay DRAFT, unapproved and production_use false")
    if "INVESTIGATE ONLY" not in doc["statements"].get("waste_interventions", ""):
        errs.append("waste_interventions statement must say transfer and donation are INVESTIGATE ONLY")
    if errs:
        raise A.AssumptionError("Assumption set v9 invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
            "content_sha256": A.content_sha256(doc), "parameters": len(params),
            "added_parameters": [k for k, p in params.items() if p.get("added_in_version") == 9]}


def intervention_values(doc: dict) -> dict:
    keys = ("gross_margin_pct",)
    g = {p["key"]: p["value"] for p in doc["parameters"]}
    return {**{k: g[k] for k in keys}, **{p["key"]: p["value"] for p in doc["parameters"] if p.get("added_in_version") == 9}}
