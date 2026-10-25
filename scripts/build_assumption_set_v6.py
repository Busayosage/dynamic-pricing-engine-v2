"""Build config/assumptions/assumption_set_v6.json from v5 (v5 is only read; refuses to overwrite an existing v6)."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from dpe.decision import assumptions as A  # noqa: E402
from dpe.decision import assumptions_v5 as V5  # noqa: E402

out = A.ASSUMPTION_DIR / "assumption_set_v6.json"
assert not out.exists(), "v6 already exists - never overwrite"
v5 = V5.load()
doc = copy.deepcopy(v5)
doc["schema_version"] = "6.0"
doc["assumption_set_id"] = "AS-2026-10-23-v6"
doc["version"] = 6
doc["supersedes"] = {"assumption_set_id": v5["assumption_set_id"], "version": 5, "content_sha256": A.content_sha256(v5),
                     "file": "config/assumptions/assumption_set_v5.json",
                     "relationship": "v1-v5 are preserved unchanged (DRAFT); v6 adds discount-recommendation research "
                                     "parameters only"}
doc["approval"] = {"status": "DRAFT", "approved_by": None, "approved_at": None,
                   "design_basis": "docs/PHASE_1_DISCOUNT_RECOMMENDATION_ENGINE.md (awaiting review)",
                   "content_sha256": None}
doc["statements"]["discount_recommendation"] = (
    "SIMULATED RESEARCH RECOMMENDATION - NOT VALIDATED FOR LIVE USE. The engine ranks permitted markdown steps for "
    "lines eligible for markdown review under explicitly ASSUMED demand-response scenarios. The responses are not "
    "estimated causal elasticities; the central 1.6% per point value is the non-causal historical association and is "
    "used only as one stated scenario. Prices are an estimated reference-price proxy, costs follow an assumed margin, "
    "stock and expiry are SIMULATED and demand is FORECAST. Nothing is proposed, approved or executed, and no result "
    "may be presented as a forecast of extra sales, reduced waste or improved profit.")


def param(key, value, unit, rationale, allowed, sensitivity, scope="global", provenance="ASSUMED",
          evidence="NONE_ILLUSTRATIVE"):
    return {"key": key, "value": value, "unit": unit, "granularity": "global", "scope": scope, "provenance": provenance,
            "evidence": evidence, "supported_by_observed_business_data": False, "rationale": rationale,
            "allowed_range": allowed, "sensitivity_range": sensitivity, "added_in_version": 6}


doc["parameters"] += [
    param("discount_recommendation_research_enabled", True, "flag",
          "Research ranking only; approvals, proposals and execution stay disabled", {"set": [True]}, {"none": True}),
    param("discount_recommendation_approval_enabled", False, "flag", "No approval functionality exists",
          {"set": [False]}, {"none": True}),
    param("discount_recommendation_execution_enabled", False, "flag", "No price is ever changed",
          {"set": [False]}, {"none": True}),
    param("demand_response_scenarios_pct_per_point",
          {"R0_NO_RESPONSE": 0.0, "R1_LOW": 1.0, "R2_CENTRAL": 1.6, "R3_HIGH": 3.0},
          "% more units demanded per markdown point",
          "Stated research scenarios, not estimates. R2 equals the non-causal historical association; R1 (1% per "
          "point) is close to revenue-neutral for small markdowns and loses money at every step; R3 is a strong "
          "near-expiry response. R0 is a stress test only.",
          {"min": 0, "max": 10}, {"scale": [0.5, 1.5]}),
    param("demand_response_decision_weights", {"R1_LOW": 0.25, "R2_CENTRAL": 0.5, "R3_HIGH": 0.25},
          "weight (sums to 1)",
          "Research weights for the expected outcome; not probabilities estimated from data. R0 is excluded and "
          "reported as a stress test.", {"min": 0, "max": 1, "sum": 1}, {"values": [[0.5, 0.5, 0.0], [0.0, 0.5, 0.5]]}),
    param("recommendation_downside_scenario", "R1_LOW", "scenario key",
          "The downside guard is checked under this scenario with the forecast p90 baseline (most full-price sales "
          "given away)", {"set": ["R0_NO_RESPONSE", "R1_LOW"]}, {"values": ["R0_NO_RESPONSE"]}),
    param("recommendation_max_downside_loss_pct_of_at_risk_cost", 25, "% of illustrative at-risk stock cost",
          "An option may not lose more than this share of the stock value at stake under the downside scenario",
          {"min": 0, "max": 100}, {"values": [10, 50]}),
    param("recommendation_min_expected_benefit_gbp", 1.0, "GBP",
          "Expected benefits below this are treated as no material benefit", {"min": 0, "max": 1000},
          {"values": [0, 10]}),
    param("recommendation_min_expected_benefit_pct_of_at_risk_cost", 2, "% of illustrative at-risk stock cost",
          "Expected benefit must also be material relative to what is at stake", {"min": 0, "max": 100},
          {"values": [0, 5]}),
    param("expiry_disposal_cost_pct_of_unit_cost", 0, "% of illustrative unit cost per expired unit",
          "No disposal-cost evidence exists; neutral default, varied in sensitivity", {"min": 0, "max": 100},
          {"values": [0, 20]}),
    param("price_evidence_conflict_tolerance_pct", 25, "% difference recorded vs reference price",
          "If the recorded shelf price that week differs from the reference proxy by more than this, the price "
          "evidence conflicts and no recommendation is made", {"min": 0, "max": 100}, {"values": [10, 50]}),
    param("markdown_window_rule", "INVESTIGATE_BY_DAY_TO_EARLIEST_BATCH_LAST_DAY_INCLUSIVE", "rule",
          "The markdown would run from the investigate-by day to the last sellable day of the oldest batch",
          {"set": ["INVESTIGATE_BY_DAY_TO_EARLIEST_BATCH_LAST_DAY_INCLUSIVE"]}, {"none": True}),
    param("baseline_window_demand_rule", "H1_FORECAST_WEEKLY_QUANTILE_DIVIDED_EVENLY_BY_7_TIMES_WINDOW_DAYS", "rule",
          "Full-price demand in the window from the protected 1-week forecast (p10/p50/p90), spread evenly over days",
          {"set": ["H1_FORECAST_WEEKLY_QUANTILE_DIVIDED_EVENLY_BY_7_TIMES_WINDOW_DAYS"]}, {"none": True},
          provenance="CALCULATED", evidence="DERIVED_FROM_FORECAST_AND_ASSUMPTION"),
]
doc["approval"]["content_sha256"] = A.content_sha256(doc)
A.validate(doc)
out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(out, A.content_sha256(doc), len(doc["parameters"]))
