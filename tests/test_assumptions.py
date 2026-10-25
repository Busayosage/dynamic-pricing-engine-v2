"""Step 5B-2 assumption file: acceptance criteria AF1-AF6 (schema, immutability, evidence, scenarios, feasibility,
non-causal uplift statement)."""
import copy
import json

import pytest

from dpe.decision import assumptions as A


@pytest.fixture(scope="module")
def doc():
    return A.load()


def _rehash(d):
    d["approval"]["content_sha256"] = A.content_sha256(d)
    return d


def _param(d, key):
    return next(p for p in d["parameters"] if p["key"] == key)


# AF1 ------------------------------------------------------------- schema
def test_real_file_validates_and_is_versioned(doc):
    s = A.validate(doc)
    assert s["assumption_set_id"] == "AS-2026-10-22-v1" and s["version"] == 1 and s["status"] == "DRAFT"
    assert A.DEFAULT_FILE.name == "assumption_set_v1.json"


@pytest.mark.parametrize("breakage", ["missing_field", "out_of_range", "min_margin_above_gross", "unknown_override",
                                      "extrapolation_enabled", "step_above_cap", "profile_sum", "bands_not_increasing",
                                      "missing_category", "non_integer_case"])
def test_schema_violations_are_rejected(doc, breakage):
    d = copy.deepcopy(doc)
    if breakage == "missing_field":
        del _param(d, "case_size_units")["unit"]
    elif breakage == "out_of_range":
        _param(d, "max_discount_pct")["value"] = 30
    elif breakage == "min_margin_above_gross":
        _param(d, "min_margin_pct")["value"]["Dairy"] = 40
    elif breakage == "unknown_override":
        d["scenarios"]["SC2"]["overrides"]["no_such_key"] = 1
    elif breakage == "extrapolation_enabled":
        _param(d, "allow_extrapolation_above_p90")["value"] = True
    elif breakage == "step_above_cap":
        _param(d, "max_discount_pct")["value"] = 20
    elif breakage == "profile_sum":
        _param(d, "daily_demand_profile")["value"][0] = 0.5
    elif breakage == "bands_not_increasing":
        _param(d, "waste_band_pct")["value"] = {"LOW_below": 20, "HIGH_above": 15}
    elif breakage == "missing_category":
        del _param(d, "gross_margin_pct")["value"]["Meat"]
    elif breakage == "non_integer_case":
        _param(d, "case_size_units")["value"]["Bakery"] = 12.5
    with pytest.raises(A.AssumptionError):
        A.validate(_rehash(d))


# AF2 ------------------------------------------------------------ immutability
def test_content_hash_detects_any_edit_and_approval_does_not_change_content(doc):
    d = copy.deepcopy(doc)
    _param(d, "case_size_units")["value"]["Bakery"] = 24  # edit without re-hashing
    with pytest.raises(A.AssumptionError, match="content_sha256"):
        A.validate(d)
    approved = copy.deepcopy(doc)
    approved["approval"].update(status="APPROVED", approved_by="reviewer", approved_at="2026-10-22")
    assert A.content_sha256(approved) == A.content_sha256(doc)
    A.validate(approved)
    edited = copy.deepcopy(approved)
    _param(edited, "moq_cases_per_delivery")["value"] = 3
    with pytest.raises(A.AssumptionError, match="new version"):
        A.validate(edited)
    unsigned = copy.deepcopy(doc)
    unsigned["approval"]["status"] = "APPROVED"
    with pytest.raises(A.AssumptionError, match="approved_by"):
        A.validate(unsigned)


# AF3 ------------------------------------------------------------- evidence
def test_illustrative_values_are_never_marked_as_observed_business_facts(doc):
    for p in doc["parameters"]:
        if p["provenance"] in ("ASSUMED", "SYNTHETIC"):
            assert p["supported_by_observed_business_data"] is False, p["key"]
            assert p["evidence"] != "OBSERVED_DATA", p["key"]
        assert {"unit", "scope", "provenance", "evidence", "rationale", "allowed_range", "granularity"} <= set(p)
    assert [p["key"] for p in doc["parameters"] if p["provenance"] == "OBSERVED"] == ["lead_time_days"]
    d = copy.deepcopy(doc)
    _param(d, "gross_margin_pct")["supported_by_observed_business_data"] = True
    with pytest.raises(A.AssumptionError, match="supported by business data"):
        A.validate(_rehash(d))


# AF4 --------------------------------------------------------------- scenarios
def test_scenarios_resolve_to_separate_parameter_sets(doc):
    sc = {s: A.resolve(doc, s) for s in A.SCENARIOS}
    assert (sc["SC1"]["delivery_fill_rate_pct"], sc["SC2"]["delivery_fill_rate_pct"]) == (100, 75)
    assert (sc["SC2"]["lead_time_adjustment_days"], sc["SC2"]["demand_multiplier"]) == (1, 1.15)
    assert (sc["SC3"]["over_delivery_pct_short_life"], sc["SC3"]["demand_multiplier"]) == (20, 0.85)
    assert sc["SC1"]["case_size_units"] == sc["SC3"]["case_size_units"]
    sc["SC1"]["case_size_units"]["Bakery"] = 99  # resolved copies are independent
    assert A.resolve(doc, "SC2")["case_size_units"]["Bakery"] == 12
    with pytest.raises(A.AssumptionError):
        A.resolve(doc, "SC9")


# AF5 ------------------------------------------------------------- feasibility
def test_feasibility_report_and_margin_direction(doc):
    f = A.feasibility(doc)
    assert {c: f[c]["largest_allowed_step_pct"] for c in A.CATEGORIES} == {"Bakery": 25, "Beverages": 25, "Dairy": 20, "Meat": 20}
    assert f["Dairy"]["max_discount_by_margin_pct"] == pytest.approx(21.74, abs=0.01)


def test_planning_weight_rule_and_cap():
    assert A.planning_weight(85) == (0.875, False)
    assert A.planning_weight(50) == (0.0, False)
    assert A.planning_weight(95) == (1.0, True)  # above 90: capped at p90, never extrapolated
    assert A.case_round(0, 12, 2) == 0 and A.case_round(1, 12, 2) == 24 and A.case_round(202.4, 12, 2) == 204


# AF6 ----------------------------------------------------------- statements
def test_statements_are_present_and_non_causal(doc):
    s = doc["statements"]
    assert "not a causal effect" in s["discount_uplift"] and "must not be used to promise" in s["discount_uplift"]
    assert "never observed lost sales" in s["demand"]
    assert "not calibrated stockout probabilities" in s["uncertainty"]
    d = copy.deepcopy(doc)
    d["statements"]["discount_uplift"] = "Discounts raise sales by 1.6% per point."
    with pytest.raises(A.AssumptionError, match="not causal"):
        A.validate(_rehash(d))
    assert json.loads(A.DEFAULT_FILE.read_text(encoding="utf-8"))["approval"]["content_sha256"] == A.content_sha256(doc)
