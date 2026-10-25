"""Step 5B-3d: assumption set v2 (config/assumptions/assumption_set_v2.json), DRAFT.

v2 carries the v1 parameters forward and adds the parameters of simulator v1.2 and the inventory recommendation
workflow, plus the SF75 supplier-fill stress scenario. `assumptions.py` (v1 rules V1-V8) is unchanged; v2 is validated
by those rules first and then by the additional rules W1-W10 below. v1 itself is never modified.

  W1  schema_version 2.0, version 2, a new assumption_set_id
  W2  supersedes names v1 and its recorded content hash, and v1 on disk still has that hash and DRAFT status
  W3  every parameter has unit, scope, provenance, evidence, rationale, allowed_range and sensitivity_range
  W4  every v1 parameter is carried forward with its value unchanged
  W5  all required v1.2 parameters are present
  W6  every scenario override (SC1-SC3 and SF75) is a known key inside its allowed range
  W7  SF75 = SC1 with only the realised fill rate at 75%; planning still expects 100%; no order inflation
  W8  status is DRAFT and production_use is false (no approval, no production claim)
  W9  no statement or rationale claims validation, production readiness or observed business support
  W10 configuration only: no parameter is OBSERVED except the v1 lead-time reference
"""
from __future__ import annotations

import re
from pathlib import Path

from dpe.decision import assumptions as A

V2_FILE = A.ASSUMPTION_DIR / "assumption_set_v2.json"
V1_ID, V1_CONTENT_SHA256 = "AS-2026-10-22-v1", "383d703dc3b08c160821d3cb9cceb6d4966c5ac59b255abb396a45655f9bb6fa"
SCENARIOS = ("SC1", "SC2", "SC3", "SF75")
REQUIRED_V2_PARAMETERS = ("planning_fill_rate_pct", "stress_fill_rate_pct", "order_inflation_for_expected_shortfall",
                          "pre_arrival_depletion_quantile", "coverage_assessment_quantiles", "expiry_escalation_pct_of_p50",
                          "rounding_excess_warning_pct", "p0_history_weeks", "p0_netting_rule", "missing_bounds_rule",
                          "standing_confirmation_rule", "supply_capacity_used")
REQUIRED_FIELDS = A.REQUIRED_FIELDS + ("sensitivity_range",)
FORBIDDEN_CLAIMS = re.compile(r"\b(production[- ]ready|production[- ]valid|validated (business )?policy|approved for "
                              r"production|verified business fact|guarantee[sd]?)\b", re.IGNORECASE)
NEGATION = re.compile(r"\b(not|never|none|no|nor|cannot|must not)\b", re.IGNORECASE)  # disclaimers are allowed


def load(path: Path = V2_FILE, v1_path: Path = A.DEFAULT_FILE) -> dict:
    doc = A.load(path)  # v1 rules V1-V8 (incl. the content hash)
    validate(doc, A.load(v1_path))
    return doc


def validate(doc: dict, v1: dict) -> dict:
    """Raise AssumptionError on any W1-W10 violation; return a summary."""
    errs = []
    if doc.get("schema_version") != "2.0" or doc.get("version") != 2:  # W1
        errs.append("schema_version must be 2.0 and version 2")
    if doc.get("assumption_set_id") in (None, V1_ID):
        errs.append("v2 needs its own assumption_set_id")
    sup = doc.get("supersedes") or {}  # W2
    if sup.get("assumption_set_id") != V1_ID or sup.get("content_sha256") != V1_CONTENT_SHA256:
        errs.append("supersedes must reference v1 and its recorded content hash")
    if A.content_sha256(v1) != V1_CONTENT_SHA256 or v1["approval"]["status"] != "DRAFT":
        errs.append("assumption set v1 has changed: it must stay DRAFT with its recorded content hash")
    params = {p.get("key"): p for p in doc["parameters"]}
    for key, p in params.items():  # W3
        missing = [f for f in REQUIRED_FIELDS if f not in p or p[f] in (None, "")]
        if missing:
            errs.append(f"{key}: missing {missing}")
    for p in v1["parameters"]:  # W4
        q = params.get(p["key"])
        if q is None:
            errs.append(f"v1 parameter {p['key']} not carried forward")
        elif q["value"] != p["value"] or q["provenance"] != p["provenance"] or q["allowed_range"] != p["allowed_range"]:
            errs.append(f"v1 parameter {p['key']} changed in value, provenance or allowed range")
    for key in REQUIRED_V2_PARAMETERS:  # W5
        if key not in params:
            errs.append(f"missing v2 parameter {key}")
    for sid in SCENARIOS:  # W6
        sc = doc["scenarios"].get(sid)
        if sc is None:
            errs.append(f"missing scenario {sid}")
            continue
        for k, v in sc["overrides"].items():
            if k not in params:
                errs.append(f"{sid}: override of unknown key {k}")
            else:
                A._check_range(params[k], v, errs)
    extra = set(doc["scenarios"]) - set(SCENARIOS)
    if extra:
        errs.append(f"unexpected scenarios {sorted(extra)}")
    sf = doc["scenarios"].get("SF75", {})  # W7
    if sf.get("overrides") != {"delivery_fill_rate_pct": 75} or sf.get("base_scenario") != "SC1":
        errs.append("SF75 must be SC1 with only delivery_fill_rate_pct = 75")
    if sf.get("expected_fulfilment_pct") != 100 or sf.get("realised_fulfilment_pct") != 75:
        errs.append("SF75 must state expected fulfilment 100% and realised 75%")
    for sid, sc in doc["scenarios"].items():
        for k in ("planning_fill_rate_pct", "order_inflation_for_expected_shortfall"):
            if k in sc["overrides"]:
                errs.append(f"{sid}: {k} may not be overridden")
    if params.get("planning_fill_rate_pct", {}).get("value") != 100:
        errs.append("planning_fill_rate_pct must be 100")
    if params.get("order_inflation_for_expected_shortfall", {}).get("value") is not False:
        errs.append("order_inflation_for_expected_shortfall must be false")
    if doc["approval"].get("status") != "DRAFT" or doc["approval"].get("approved_by") or doc.get("production_use") is not False:  # W8
        errs.append("v2 must stay DRAFT, unapproved and production_use false")
    texts = list(doc["statements"].values()) + [p.get("rationale", "") for p in doc["parameters"]]  # W9
    claims = sorted({m.group(0) for t in texts for m in FORBIDDEN_CLAIMS.finditer(str(t))
                     if not NEGATION.search(str(t)[max(0, m.start() - 60):m.start()])})
    if claims:
        errs.append(f"unsupported claims: {claims}")
    if any(p["supported_by_observed_business_data"] is not False for p in doc["parameters"] if p["provenance"] != "OBSERVED"):
        errs.append("only OBSERVED parameters may be supported by observed business data")
    observed = [k for k, p in params.items() if p["provenance"] == "OBSERVED"]  # W10
    if observed != ["lead_time_days"]:
        errs.append(f"unexpected OBSERVED parameters {observed}")
    if errs:
        raise A.AssumptionError("Assumption set v2 invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
            "content_sha256": A.content_sha256(doc), "parameters": len(params), "scenarios": list(doc["scenarios"]),
            "added_parameters": [k for k, p in params.items() if p.get("added_in_version") == 2]}


def resolve(doc: dict, scenario: str) -> dict:
    """Flat values for one v2 scenario (v1 resolve semantics)."""
    return A.resolve(doc, scenario)
