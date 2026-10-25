"""Stage 7B: assumption set v4 (config/assumptions/assumption_set_v4.json), DRAFT.

v4 carries every v3 parameter forward unchanged and adds the markdown-review eligibility parameters only. Validated by
the v1 rules (assumptions.validate, V1-V8) and then Y1-Y8. v1, v2 and v3 are never modified.

  Y1  schema_version 4.0, version 4, a new assumption_set_id
  Y2  supersedes names v3 and its recorded content hash; v3 (and through it v2, v1) still validate unchanged and DRAFT
  Y3  every v3 parameter carried forward with value, provenance and allowed range unchanged
  Y4  every parameter has unit, scope, provenance, evidence, rationale, allowed_range and sensitivity_range
  Y5  all markdown parameters present, ASSUMED and unsupported by business data
  Y6  numerical discounts and approval functionality disabled; open inventory cases are warnings only
  Y7  scenarios identical to v3
  Y8  status DRAFT, production_use false; approval and audit requirements documented as not implemented
"""
from __future__ import annotations

from pathlib import Path

from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v3 as C

V4_FILE = A.ASSUMPTION_DIR / "assumption_set_v4.json"
V3_ID, V3_CONTENT_SHA256 = "AS-2026-10-23-v3", "cb46de1bb2acfba85e8aa763138436a9bfb5cfd0b8d42820da5bebc2be4f63d9"
REQUIRED_V4_PARAMETERS = ("markdown_eligible_waste_categories", "markdown_min_sellable_days_after_investigate_by",
                          "markdown_blocker_order", "markdown_product_exclusions", "markdown_open_inventory_case_effect",
                          "markdown_numerical_discounts_enabled", "markdown_approval_functionality_enabled",
                          "markdown_required_data_before_numerical_discount")


def load(path: Path = V4_FILE) -> dict:
    doc = A.load(path)
    validate(doc, C.load())
    return doc


def validate(doc: dict, v3: dict) -> dict:
    errs = []
    if doc.get("schema_version") != "4.0" or doc.get("version") != 4 or \
            doc.get("assumption_set_id") in (None, V3_ID, C.V2_ID, B.V1_ID):
        errs.append("v4 needs schema 4.0, version 4 and its own assumption_set_id")
    sup = doc.get("supersedes") or {}
    if sup.get("assumption_set_id") != V3_ID or sup.get("content_sha256") != V3_CONTENT_SHA256:
        errs.append("supersedes must reference v3 and its recorded content hash")
    if A.content_sha256(v3) != V3_CONTENT_SHA256 or v3["approval"]["status"] != "DRAFT":
        errs.append("assumption set v3 has changed: it must stay DRAFT with its recorded content hash")
    params = {p.get("key"): p for p in doc["parameters"]}
    for p in v3["parameters"]:
        q = params.get(p["key"])
        if q is None or q["value"] != p["value"] or q["provenance"] != p["provenance"] or q["allowed_range"] != p["allowed_range"]:
            errs.append(f"v3 parameter {p['key']} missing or changed")
    for key, p in params.items():
        missing = [f for f in B.REQUIRED_FIELDS if f not in p or p[f] in (None, "")]
        if missing:
            errs.append(f"{key}: missing {missing}")
    for key in REQUIRED_V4_PARAMETERS:
        if key not in params:
            errs.append(f"missing v4 parameter {key}")
        elif params[key]["provenance"] != "ASSUMED" or params[key]["supported_by_observed_business_data"] is not False:
            errs.append(f"{key} must be ASSUMED and unsupported by business data")
    g = {k: p["value"] for k, p in params.items()}
    if g.get("markdown_numerical_discounts_enabled") is not False or g.get("markdown_approval_functionality_enabled") is not False:
        errs.append("numerical discounts and approval functionality must stay disabled")
    if g.get("markdown_open_inventory_case_effect") != "WARNING_ONLY":
        errs.append("open inventory cases must be warnings only")
    if doc["scenarios"] != v3["scenarios"]:
        errs.append("scenarios must be identical to v3")
    if doc["approval"].get("status") != "DRAFT" or doc["approval"].get("approved_by") or doc.get("production_use") is not False:
        errs.append("v4 must stay DRAFT, unapproved and production_use false")
    if "not implemented" not in str(doc.get("approval_and_audit_requirements", {}).get("status", "")):
        errs.append("approval and audit requirements must be documented as not implemented")
    if errs:
        raise A.AssumptionError("Assumption set v4 invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
            "content_sha256": A.content_sha256(doc), "parameters": len(params),
            "added_parameters": [k for k, p in params.items() if p.get("added_in_version") == 4]}


def markdown_values(doc: dict) -> dict:
    return {p["key"]: p["value"] for p in doc["parameters"] if p["key"].startswith("markdown_")}
