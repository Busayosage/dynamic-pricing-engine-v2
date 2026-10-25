"""Stage 8B: assumption set v5 (config/assumptions/assumption_set_v5.json), DRAFT.

v5 carries every v4 parameter forward unchanged and adds the pricing-demonstration parameters only. Validated by the v1
rules (assumptions.validate, V1-V8) and then Z1-Z7. v1-v4 are never modified.

  Z1  schema_version 5.0, version 5, a new assumption_set_id
  Z2  supersedes names v4 and its recorded content hash; v4 (and through it v1-v3) still validate unchanged and DRAFT
  Z3  every v4 parameter carried forward with value, provenance and allowed range unchanged
  Z4  every parameter has unit, scope, provenance, evidence, rationale, allowed_range and sensitivity_range
  Z5  all pricing parameters present, ASSUMED and unsupported by business data; displayed steps = 0 + discount_steps_pct
  Z6  demonstration mode on; recommendations, proposals and cooldown enforcement off; cooldown duration not invented
  Z7  scenarios identical to v4; status DRAFT and production_use false
"""
from __future__ import annotations

from pathlib import Path

from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v4 as V4

V5_FILE = A.ASSUMPTION_DIR / "assumption_set_v5.json"
V4_ID, V4_CONTENT_SHA256 = "AS-2026-10-23-v4", "bde13a20df120ea4e452bfb36f45ee6bb24581efa191216b403f46a2c076a1a5"
REQUIRED_V5_PARAMETERS = ("pricing_demo_mode", "pricing_base_price_rule", "pricing_cost_rule",
                          "pricing_display_markdown_steps_pct", "pricing_display_decimals", "pricing_cooldown_days",
                          "pricing_cooldown_enforced", "pricing_recommendation_enabled", "pricing_proposals_enabled",
                          "pricing_show_at_risk_stock_cost")


def load(path: Path = V5_FILE) -> dict:
    doc = A.load(path)
    validate(doc, V4.load())
    return doc


def validate(doc: dict, v4: dict) -> dict:
    errs = []
    if doc.get("schema_version") != "5.0" or doc.get("version") != 5 or doc.get("assumption_set_id") in (None, V4_ID):
        errs.append("v5 needs schema 5.0, version 5 and its own assumption_set_id")
    sup = doc.get("supersedes") or {}
    if sup.get("assumption_set_id") != V4_ID or sup.get("content_sha256") != V4_CONTENT_SHA256:
        errs.append("supersedes must reference v4 and its recorded content hash")
    if A.content_sha256(v4) != V4_CONTENT_SHA256 or v4["approval"]["status"] != "DRAFT":
        errs.append("assumption set v4 has changed: it must stay DRAFT with its recorded content hash")
    params = {p.get("key"): p for p in doc["parameters"]}
    for p in v4["parameters"]:
        q = params.get(p["key"])
        if q is None or q["value"] != p["value"] or q["provenance"] != p["provenance"] or q["allowed_range"] != p["allowed_range"]:
            errs.append(f"v4 parameter {p['key']} missing or changed")
    for key, p in params.items():
        missing = [f for f in B.REQUIRED_FIELDS if f not in p or p[f] in (None, "")]
        if missing:
            errs.append(f"{key}: missing {missing}")
    for key in REQUIRED_V5_PARAMETERS:
        if key not in params:
            errs.append(f"missing v5 parameter {key}")
        elif params[key]["provenance"] != "ASSUMED" or params[key]["supported_by_observed_business_data"] is not False:
            errs.append(f"{key} must be ASSUMED and unsupported by business data")
    g = {k: p["value"] for k, p in params.items()}
    if g.get("pricing_display_markdown_steps_pct") != [0] + list(g.get("discount_steps_pct", [])):
        errs.append("displayed markdown steps must be 0 plus discount_steps_pct")
    if g.get("pricing_demo_mode") is not True or g.get("pricing_recommendation_enabled") is not False or \
            g.get("pricing_proposals_enabled") is not False or g.get("pricing_cooldown_enforced") is not False:
        errs.append("demonstration mode must be on; recommendations, proposals and cooldown enforcement off")
    if g.get("pricing_cooldown_days") != "NOT_DEFINED":
        errs.append("no cooldown duration may be invented")
    if doc["scenarios"] != v4["scenarios"]:
        errs.append("scenarios must be identical to v4")
    if doc["approval"].get("status") != "DRAFT" or doc["approval"].get("approved_by") or doc.get("production_use") is not False:
        errs.append("v5 must stay DRAFT, unapproved and production_use false")
    if errs:
        raise A.AssumptionError("Assumption set v5 invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
            "content_sha256": A.content_sha256(doc), "parameters": len(params),
            "added_parameters": [k for k, p in params.items() if p.get("added_in_version") == 5]}


def pricing_values(doc: dict) -> dict:
    keys = ("gross_margin_pct", "min_margin_pct", "max_discount_pct", "discount_steps_pct")
    return {p["key"]: p["value"] for p in doc["parameters"] if p["key"].startswith("pricing_") or p["key"] in keys}
