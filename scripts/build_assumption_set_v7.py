"""Build config/assumptions/assumption_set_v7.json from v6 (v6 is only read; refuses to overwrite an existing v7)."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dpe.decision import assumptions as A  # noqa: E402
from dpe.decision import assumptions_v6 as V6  # noqa: E402

out = A.ASSUMPTION_DIR / "assumption_set_v7.json"
assert not out.exists(), "v7 already exists - never overwrite"
v6 = V6.load()
doc = copy.deepcopy(v6)
doc["schema_version"] = "7.0"
doc["assumption_set_id"] = "AS-2026-10-23-v7"
doc["version"] = 7
doc["supersedes"] = {"assumption_set_id": v6["assumption_set_id"], "version": 6, "content_sha256": A.content_sha256(v6),
                     "file": "config/assumptions/assumption_set_v6.json",
                     "relationship": "v1-v6 are preserved unchanged (DRAFT); v7 adds dynamic-pricing research parameters only"}
doc["approval"] = {"status": "DRAFT", "approved_by": None, "approved_at": None,
                   "design_basis": "docs/PHASE_2_DYNAMIC_PRICING_DESIGN.md (design approved with conditions 2026-10-23; "
                                   "this file's content awaits review)",
                   "content_sha256": None}
doc["statements"]["dynamic_pricing"] = (
    "SIMULATED RESEARCH - NOT VALIDATED FOR LIVE USE. Weekly markdown decisions are simulated inside the inventory "
    "replay. Orders are fixed to the pricing-off pass, so pricing never changes ordering. Prices never exceed the "
    "reference price. The response used to SELECT a markdown (v6 decision weights) is kept separate from the response "
    "used to SIMULATE what happens (one true-response scenario per run, including no response). Every markdown is "
    "recorded as SIMULATED, HYPOTHETICAL_UNAPPROVED and NOT_EXECUTED and is applied in the simulation only as if "
    "approved. No result may be presented as proven commercial benefit.")


def param(key, value, unit, rationale, allowed, sensitivity, provenance="ASSUMED", evidence="NONE_ILLUSTRATIVE"):
    return {"key": key, "value": value, "unit": unit, "granularity": "per store x product" if "cooldown" in key or
            "events" in key else "global", "scope": "global", "provenance": provenance, "evidence": evidence,
            "supported_by_observed_business_data": False, "rationale": rationale, "allowed_range": allowed,
            "sensitivity_range": sensitivity, "added_in_version": 7}


doc["parameters"] += [
    param("dynamic_pricing_research_enabled", True, "flag", "Simulation only; approval and execution remain disabled",
          {"set": [True]}, {"none": True}),
    param("dynamic_pricing_markdown_only", True, "flag", "Approved condition: the price never exceeds the reference price",
          {"set": [True]}, {"none": True}),
    param("dynamic_pricing_ordering_interaction", "ORDERS_FIXED_TO_PRICING_OFF_PASS", "rule",
          "Approved condition: replenishment is decided first and pricing must not change any ordering decision",
          {"set": ["ORDERS_FIXED_TO_PRICING_OFF_PASS"]}, {"none": True}),
    param("dynamic_pricing_cooldown_days", 7, "days between markdown selections",
          "Approved condition: at least 7 days between markdown decisions for a store-product", {"min": 0, "max": 56,
                                                                                               "integer": True},
          {"values": [14, 21]}),
    param("dynamic_pricing_max_events_per_window", 2, "markdown events",
          "Approved condition: at most two markdown events per store-product in any rolling window",
          {"min": 0, "max": 28, "integer": True}, {"values": [1, 3]}),
    param("dynamic_pricing_event_window_days", 28, "days (rolling)", "Approved condition: rolling 28-day period",
          {"min": 1, "max": 365, "integer": True}, {"none": True}),
    param("dynamic_pricing_event_counting_rule", "COUNTED_AT_SELECTION_ON_DECISION_DAY", "rule",
          "An event is counted on the decision day it is selected. Every selected markdown is applied in the "
          "simulation, so selected and hypothetically applied events are the same set; the rolling window and the "
          "cooldown both use selection days", {"set": ["COUNTED_AT_SELECTION_ON_DECISION_DAY"]}, {"none": True}),
    param("dynamic_pricing_overlap_rule", "NO_SELECTION_WHILE_AN_EARLIER_WINDOW_IS_STILL_IN_FORCE", "rule",
          "A new markdown cannot be selected while the window of an earlier one still includes the decision day or "
          "later; one price at a time", {"set": ["NO_SELECTION_WHILE_AN_EARLIER_WINDOW_IS_STILL_IN_FORCE"]},
          {"none": True}),
    param("dynamic_pricing_true_response_scenarios", ["R0_NO_RESPONSE", "R1_LOW", "R2_CENTRAL", "R3_HIGH"],
          "scenario keys", "Approved condition: every run is simulated under one true response, including no response",
          {"set": [["R0_NO_RESPONSE", "R1_LOW", "R2_CENTRAL", "R3_HIGH"]]}, {"none": True}),
    param("dynamic_pricing_demand_rounding_rule", "FLOOR_OF_DAILY_UNITS_TIMES_MULTIPLIER_PLUS_HALF", "rule",
          "Daily demand on a markdown day = floor(recorded daily units x (1 + true response x points / 100) + 0.5); "
          "integer units as in the replay", {"set": ["FLOOR_OF_DAILY_UNITS_TIMES_MULTIPLIER_PLUS_HALF"]}, {"none": True}),
    param("dynamic_pricing_revenue_price_rule", "REFERENCE_PRICE_OF_THE_ORIGIN_THAT_DECIDED_THE_WEEK", "rule",
          "Days of week w are priced at the estimated reference price of origin w - 1; markdown days at that "
          "decision's markdown price", {"set": ["REFERENCE_PRICE_OF_THE_ORIGIN_THAT_DECIDED_THE_WEEK"]}, {"none": True}),
    param("dynamic_pricing_mandatory_review_markdown_pct", 20, "% markdown",
          "Hypothetical markdowns at or above this depth, repeats inside the rolling window and lines with an open "
          "inventory review case are tagged MANDATORY_REVIEW", {"min": 0, "max": 25}, {"values": [15, 25]}),
    param("dynamic_pricing_simulation_convention", "SIMULATED_AS_IF_APPROVED", "label",
          "Inside the replay a selected markdown is applied only as if approved, so its consequences can be measured; "
          "no approval exists", {"set": ["SIMULATED_AS_IF_APPROVED"]}, {"none": True}),
]
doc["approval"]["content_sha256"] = A.content_sha256(doc)
A.validate(doc)
out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(out, A.content_sha256(doc), len(doc["parameters"]))
