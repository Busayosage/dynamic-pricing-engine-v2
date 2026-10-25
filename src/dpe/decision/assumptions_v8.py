"""Amendment A1: assumption set v8 (config/assumptions/assumption_set_v8.json), DRAFT.

v8 carries every v7 parameter forward unchanged and adds only `dynamic_pricing_cooldown_basis`
(END_OF_PREVIOUS_MARKDOWN_WINDOW). Validated by the v1 rules and then W1-W5. v1-v7 are never modified.

  W1  schema_version 8.0, version 8, a new assumption_set_id
  W2  supersedes names v7 and its recorded content hash; v7 still validates unchanged and DRAFT
  W3  every v7 parameter carried forward unchanged (value, provenance, allowed range), approved conditions included
  W4  the single added parameter is the cooldown basis, ASSUMED and unsupported by business data
  W5  scenarios identical to v7; DRAFT, production_use false; cooldown_amendment statement present
"""
from __future__ import annotations

from pathlib import Path

from dpe.decision import assumptions as A
from dpe.decision import assumptions_v7 as V7

V8_FILE = A.ASSUMPTION_DIR / "assumption_set_v8.json"
V7_ID, V7_CONTENT_SHA256 = "AS-2026-10-23-v7", "9f3d33db855d6ce0bec2d38a84dafa7080b02f2eeb5ba37ec32186774a38f0fc"


def load(path: Path = V8_FILE) -> dict:
    doc = A.load(path)
    validate(doc, V7.load())
    return doc


def validate(doc: dict, v7: dict) -> dict:
    errs = []
    if doc.get("schema_version") != "8.0" or doc.get("version") != 8 or doc.get("assumption_set_id") in (None, V7_ID):
        errs.append("v8 needs schema 8.0, version 8 and its own assumption_set_id")
    sup = doc.get("supersedes") or {}
    if sup.get("assumption_set_id") != V7_ID or sup.get("content_sha256") != V7_CONTENT_SHA256:
        errs.append("supersedes must reference v7 and its recorded content hash")
    if A.content_sha256(v7) != V7_CONTENT_SHA256 or v7["approval"]["status"] != "DRAFT":
        errs.append("assumption set v7 has changed: it must stay DRAFT with its recorded content hash")
    params = {p.get("key"): p for p in doc["parameters"]}
    for p in v7["parameters"]:
        q = params.get(p["key"])
        if q is None or q["value"] != p["value"] or q["provenance"] != p["provenance"] or q["allowed_range"] != p["allowed_range"]:
            errs.append(f"v7 parameter {p['key']} missing or changed")
    added = [k for k, p in params.items() if p.get("added_in_version") == 8]
    if added != ["dynamic_pricing_cooldown_basis"]:
        errs.append(f"v8 may add only dynamic_pricing_cooldown_basis, found {added}")
    elif params["dynamic_pricing_cooldown_basis"]["provenance"] != "ASSUMED" or \
            params["dynamic_pricing_cooldown_basis"]["supported_by_observed_business_data"] is not False:
        errs.append("dynamic_pricing_cooldown_basis must be ASSUMED and unsupported by business data")
    if doc["scenarios"] != v7["scenarios"]:
        errs.append("scenarios must be identical to v7")
    if doc["approval"].get("status") != "DRAFT" or doc["approval"].get("approved_by") or doc.get("production_use") is not False:
        errs.append("v8 must stay DRAFT, unapproved and production_use false")
    if "END of the previous" not in doc["statements"].get("cooldown_amendment", ""):
        errs.append("cooldown_amendment statement missing")
    if errs:
        raise A.AssumptionError("Assumption set v8 invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
            "content_sha256": A.content_sha256(doc), "parameters": len(params), "added_parameters": added}


def dynamic_pricing_values(doc: dict) -> dict:
    g = {p["key"]: p["value"] for p in doc["parameters"]}
    return {**V7.dynamic_pricing_values(doc), "dynamic_pricing_cooldown_basis": g["dynamic_pricing_cooldown_basis"]}
