"""Build config/assumptions/assumption_set_v9.json from v8 (v8 is only read; refuses to overwrite an existing v9).

v9 carries every v8 value forward unchanged and adds only the Phase 3 waste-intervention rule parameters."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dpe.decision import assumptions as A  # noqa: E402
from dpe.decision import assumptions_v8 as V8  # noqa: E402

out = A.ASSUMPTION_DIR / "assumption_set_v9.json"
assert not out.exists(), "v9 already exists - never overwrite"
v8 = V8.load()
doc = copy.deepcopy(v8)
doc["schema_version"] = "9.0"
doc["assumption_set_id"] = "AS-2026-10-24-v9"
doc["version"] = 9
doc["supersedes"] = {"assumption_set_id": v8["assumption_set_id"], "version": 8, "content_sha256": A.content_sha256(v8),
                     "file": "config/assumptions/assumption_set_v8.json",
                     "relationship": "v1-v8 are preserved unchanged (DRAFT); v9 adds Phase 3 waste-intervention rules only"}
doc["approval"] = {"status": "DRAFT", "approved_by": None, "approved_at": None,
                   "design_basis": "docs/PHASE_3_WASTE_INTERVENTION_DESIGN.md (implementation approved 2026-10-24); this "
                                   "file's content awaits review",
                   "content_sha256": None}
doc["statements"]["waste_interventions"] = (
    "ADVISORY INVESTIGATION SUPPORT ONLY. Waste-intervention options are classified from saved simulated, forecast and "
    "assumed evidence. No order change, transfer, markdown, donation or disposal is assumed to have happened, proposed "
    "for execution or approved. Stock transfer and donation or disposal are INVESTIGATE ONLY: distance, transport, cost, "
    "receiving capacity, batch stock, food safety, eligibility and recipients are unknown. Values at risk are "
    "illustrative (estimated retail value and assumed cost value), never savings. The investigation order follows "
    "evidence quality, not financial benefit, and is not a commercially optimal choice.")


def param(key, value, unit, rationale, allowed, sensitivity, provenance="ASSUMED"):
    return {"key": key, "value": value, "unit": unit, "granularity": "global", "scope": "global",
            "provenance": provenance, "evidence": "NONE_ILLUSTRATIVE", "supported_by_observed_business_data": False,
            "rationale": rationale, "allowed_range": allowed, "sensitivity_range": sensitivity, "added_in_version": 9}


doc["parameters"] += [
    param("waste_intervention_at_risk_categories", ["HIGH", "MODERATE"], "waste-risk classes",
          "Lines whose Stage 6B class is High or Moderate are assessed for interventions", {"set": [["HIGH", "MODERATE"]]},
          {"none": True}),
    param("waste_intervention_transfer_pairing_rule",
          "SAME_PRODUCT_SAME_REGION_SAME_DECISION_WEEK_RECEIVER_PROJECTED_SHORT", "rule",
          "A transfer opportunity needs another store in the same region, for the same product and decision week, whose "
          "simulated stock is projected to run short before its next delivery; region stands in for distance",
          {"set": ["SAME_PRODUCT_SAME_REGION_SAME_DECISION_WEEK_RECEIVER_PROJECTED_SHORT"]}, {"none": True}),
    param("waste_intervention_donation_min_units", 100, "units at risk",
          "Below this many projected-to-expire units a donation or disposal investigation is not suggested",
          {"min": 0, "max": 100000, "integer": True}, {"values": [50, 500]}),
    param("waste_intervention_evidence_levels",
          {"L2_SIMULATED_WITH_MODELLED_CONSEQUENCE": 2, "L1_SIMULATED_PATTERN_ONLY": 1, "L0_NO_EVIDENCE": 0},
          "evidence level", "Investigation order by evidence quality, never by financial benefit", {"min": 0, "max": 2},
          {"none": True}),
    param("waste_intervention_tie_order", ["MARKDOWN", "TRANSFER", "DONATION_OR_DISPOSAL"], "order",
          "Equal evidence: options needing fewer outside parties first (internal, then another store, then a third party)",
          {"set": [["MARKDOWN", "TRANSFER", "DONATION_OR_DISPOSAL"]]}, {"none": True}),
    param("waste_intervention_value_basis", "UNITS_X_REFERENCE_PRICE_AND_UNITS_X_ASSUMED_COST", "rule",
          "Estimated retail value = at-risk units x estimated reference price; assumed cost value = at-risk units x "
          "reference price x (1 - assumed margin). Illustrative only, never a saving",
          {"set": ["UNITS_X_REFERENCE_PRICE_AND_UNITS_X_ASSUMED_COST"]}, {"none": True}),
    param("waste_intervention_markdown_context_run", "A1_PREFERRED_RESEARCH_RUN_CENTRAL_RESPONSE", "source",
          "The dynamic-pricing context shown for a markdown comes from the preferred A1 research run under the central "
          "response; it is context only and never re-ranked", {"set": ["A1_PREFERRED_RESEARCH_RUN_CENTRAL_RESPONSE"]},
          {"none": True}),
]
doc["approval"]["content_sha256"] = A.content_sha256(doc)
A.validate(doc)
out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(out, A.content_sha256(doc), len(doc["parameters"]))
