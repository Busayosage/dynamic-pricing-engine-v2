"""Build config/assumptions/assumption_set_v8.json from v7 (v7 is only read; refuses to overwrite an existing v8).

v8 is research-rule amendment A1 (approved 2026-10-23): the 7-day cooldown is measured from the END of the previous
simulated markdown window. Every v7 value is carried forward unchanged; v8 only adds the cooldown basis."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dpe.decision import assumptions as A  # noqa: E402
from dpe.decision import assumptions_v7 as V7  # noqa: E402

out = A.ASSUMPTION_DIR / "assumption_set_v8.json"
assert not out.exists(), "v8 already exists - never overwrite"
v7 = V7.load()
doc = copy.deepcopy(v7)
doc["schema_version"] = "8.0"
doc["assumption_set_id"] = "AS-2026-10-23-v8"
doc["version"] = 8
doc["supersedes"] = {"assumption_set_id": v7["assumption_set_id"], "version": 7, "content_sha256": A.content_sha256(v7),
                     "file": "config/assumptions/assumption_set_v7.json",
                     "relationship": "v1-v7 are preserved unchanged (DRAFT); v8 is research-rule amendment A1 only"}
doc["approval"] = {"status": "DRAFT", "approved_by": None, "approved_at": None,
                   "design_basis": "Cooldown clarification approved by the project owner on 2026-10-23 (amendment A1); "
                                   "this file's content awaits review",
                   "content_sha256": None}
doc["statements"]["cooldown_amendment"] = (
    "Amendment A1: the dynamic_pricing_cooldown_days (7) are complete days counted from the END of the previous "
    "simulated markdown window for the same store-product. A new markdown may start only on or after previous window "
    "end + 7 + 1. This replaces the v7 selection-day basis for runs made with v8; the v7 rule and every result made with "
    "it are preserved unchanged. The rolling 2-in-28-days limit and the no-overlap rule are kept.")
doc["parameters"].append({
    "key": "dynamic_pricing_cooldown_basis", "value": "END_OF_PREVIOUS_MARKDOWN_WINDOW", "unit": "rule",
    "granularity": "per store x product", "scope": "global", "provenance": "ASSUMED", "evidence": "NONE_ILLUSTRATIVE",
    "supported_by_observed_business_data": False,
    "rationale": "Approved amendment A1: new window start >= previous window end + cooldown days + 1 (cooldown days are "
                 "complete days with no markdown); checked at the weekly decision against the candidate window start",
    "allowed_range": {"set": ["END_OF_PREVIOUS_MARKDOWN_WINDOW"]}, "sensitivity_range": {"none": True},
    "added_in_version": 8})
doc["approval"]["content_sha256"] = A.content_sha256(doc)
A.validate(doc)
out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(out, A.content_sha256(doc), len(doc["parameters"]))
