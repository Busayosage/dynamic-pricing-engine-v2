"""Stage 5B-3d: assumption set v2 (DRAFT) and the SF75 supplier-fill stress scenario."""
from __future__ import annotations

import copy
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from conftest import fake_contract_predictions, forecast_raw
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import forecast_contract as FC
from dpe.decision import recommendations as REC
from dpe.decision import replay_v12 as V
from dpe.forecast.panel import build_panel

V1_FILE_SHA256 = "42116041ee61d265fc2756726de61b57b271513d9d095d914116208b4d2ccd50"
V2_CONTENT_SHA256 = "ddc95ec125bb715ba63de9c2fe90de7319eb6cc38470c327c2585eb916cf989f"


@pytest.fixture(scope="module")
def v1():
    return A.load()


@pytest.fixture(scope="module")
def v2():
    return B.load()


@pytest.fixture(scope="module")
def panel():
    return build_panel(forecast_raw())


@pytest.fixture(scope="module")
def contract(panel):
    return FC.build_contract(fake_contract_predictions(panel), panel, "TEST")["contract"]


def rehash(doc):
    doc["approval"]["content_sha256"] = A.content_sha256(doc)
    return doc


def check(doc, v1):
    A.validate(rehash(doc))
    return B.validate(doc, v1)


# ------------------------------------------------------------------------------------- schema integrity
def test_v2_is_valid_draft_with_recorded_hash(v2, v1):
    s = B.validate(v2, v1)
    assert s["assumption_set_id"] == "AS-2026-10-23-v2" and s["version"] == 2 and s["status"] == "DRAFT"
    assert A.content_sha256(v2) == v2["approval"]["content_sha256"] == V2_CONTENT_SHA256
    assert s["parameters"] == 36 and s["scenarios"] == ["SC1", "SC2", "SC3", "SF75"]
    assert v2["production_use"] is False and v2["approval"]["approved_by"] is None


def test_every_parameter_is_fully_described(v2):
    for p in v2["parameters"]:
        for f in B.REQUIRED_FIELDS:
            assert f in p and p[f] not in (None, ""), (p["key"], f)
        assert p["provenance"] in A.PROVENANCES
        if p["provenance"] in ("ASSUMED", "SYNTHETIC"):
            assert p["supported_by_observed_business_data"] is False and p["evidence"] != "OBSERVED_DATA"
    added = [p for p in v2["parameters"] if p.get("added_in_version") == 2]
    assert [p["key"] for p in added] == list(B.REQUIRED_V2_PARAMETERS)
    assert all(p["provenance"] == "ASSUMED" for p in added)


# ------------------------------------------------------------------------------------ version separation
def test_versions_are_separate(v1, v2):
    assert v1["assumption_set_id"] == "AS-2026-10-22-v1" and v2["assumption_set_id"] != v1["assumption_set_id"]
    assert v2["supersedes"]["assumption_set_id"] == v1["assumption_set_id"]
    assert v2["supersedes"]["content_sha256"] == A.content_sha256(v1) == B.V1_CONTENT_SHA256
    assert A.DEFAULT_FILE.name == "assumption_set_v1.json"  # existing code and protected runs keep using v1
    assert "SF75" not in v1["scenarios"]
    assert not {p["key"] for p in v1["parameters"]} & set(B.REQUIRED_V2_PARAMETERS)
    assert A.resolve(v2, "SC1")["assumption_set_id"] == "AS-2026-10-23-v2"


def test_v1_is_immutable(v1):
    assert hashlib.sha256(A.DEFAULT_FILE.read_bytes()).hexdigest() == V1_FILE_SHA256
    assert A.content_sha256(v1) == B.V1_CONTENT_SHA256 and v1["approval"]["status"] == "DRAFT"
    tampered = rehash(copy.deepcopy(v1))
    tampered["parameters"][0]["value"]["Bakery"] = 50
    with pytest.raises(A.AssumptionError, match="v1 has changed"):
        B.validate(B.load(), rehash(tampered))


def test_v1_parameters_carried_forward_unchanged(v1, v2):
    by = {p["key"]: p for p in v2["parameters"]}
    for p in v1["parameters"]:
        assert by[p["key"]]["value"] == p["value"] and by[p["key"]]["allowed_range"] == p["allowed_range"]
        assert by[p["key"]]["provenance"] == p["provenance"]


# ------------------------------------------------------------------------------------ scenario definitions
def test_scenarios(v1, v2):
    for sid in ("SC1", "SC2", "SC3"):
        assert v2["scenarios"][sid] == v1["scenarios"][sid]
        r1, r2 = A.resolve(v1, sid), A.resolve(v2, sid)
        assert all(r2[k] == v for k, v in r1.items() if k not in ("assumption_set_id", "assumption_content_sha256"))
    sc1, sf = A.resolve(v2, "SC1"), A.resolve(v2, "SF75")
    diff = {k for k in sc1 if sc1[k] != sf[k]}
    assert diff == {"delivery_fill_rate_pct", "scenario_id", "scenario_name"}
    assert (sf["delivery_fill_rate_pct"], sf["planning_fill_rate_pct"], sf["stress_fill_rate_pct"]) == (75, 100, 75)
    assert sf["order_inflation_for_expected_shortfall"] is False
    assert v2["scenarios"]["SF75"]["adoption_threshold"] is None


# ---------------------------------------------------------------------------------- supplier-fill separation
def test_sf75_planning_expects_100_and_only_receipts_fall(v2, contract, panel):
    sc1, sf = A.resolve(v2, "SC1"), A.resolve(v2, "SF75")
    for p in V.POLICIES:
        a, b = V.simulate(contract, panel, sc1, p), V.simulate(contract, panel, sf, p)
        o = a["origins"][0]
        first = lambda r: r["decisions"][r["decisions"]["origin_week"] == o].drop(columns=["scenario_id", "order_id", "recommendation_id"], errors="ignore").reset_index(drop=True)  # noqa: E731
        pd.testing.assert_frame_equal(first(a), first(b))  # expected fulfilment: decisions identical before any receipt
        orders = b["deliveries"][b["deliveries"]["kind"] == "ORDER"]
        assert (orders["delivered_units"] == np.floor(orders["ordered_units"] * 0.75 + 1e-9).astype(int)).all()
        assert (a["deliveries"].query("kind == 'ORDER'")["delivered_units"]
                == a["deliveries"].query("kind == 'ORDER'")["ordered_units"]).all()
        assert b["weekly"]["sim_unmet_units_illustrative"].sum() > a["weekly"]["sim_unmet_units_illustrative"].sum()
    rec = V.simulate(contract, panel, sf, "P2")["recommendations"][0]
    assert rec["evidence"]["assumed"]["planned_fill_pct"] == 100.0
    exp = rec["evidence"]["calculated"].get("fill_rate_exposure_illustrative")
    assert exp is None or (exp["stress_fill_pct"] == 75 and exp["orders_adjusted"] is False)


def test_planning_rejects_expected_fulfilment_below_100_or_order_inflation(v2):
    v = A.resolve(v2, "SF75")
    kw = dict(store_id=1, product_id=1, product_category="Dairy", origin_week=10, decision_day=78, shelf_life_days=10,
              lead_time_days=2, p10=1.0, p50=2.0, p90=3.0, uncertainty_status="AVAILABLE")
    c = REC.context_from_values(v, **kw)
    assert c.fill_stress_pct == 75 and c.waste_high_above_pct == 15 and c.assumption_status == "DRAFT"
    assert c.assumption_content_sha256 == V2_CONTENT_SHA256
    for bad in ({"planning_fill_rate_pct": 90}, {"order_inflation_for_expected_shortfall": True}):
        with pytest.raises(ValueError):
            REC.context_from_values({**v, **bad}, **kw)


def test_v2_parameters_match_the_code(v2):
    g = {p["key"]: p["value"] for p in v2["parameters"]}
    assert g["rounding_excess_warning_pct"] == REC.ROUNDING_EXCESS_WARNING_PCT
    assert g["expiry_escalation_pct_of_p50"] == g["waste_band_pct"]["HIGH_above"]  # provisional: same level as v1
    assert g["p0_history_weeks"] == 4 and g["supply_capacity_used"] is False
    assert g["missing_bounds_rule"]["P2"] == "ANY_REQUIRED_HORIZON" and g["missing_bounds_rule"]["P1"] == "H1_ONLY_V11_GATE"


def test_p1_is_unaffected_by_the_v2_file(v1, v2, contract, panel):
    a = V.simulate(contract, panel, A.resolve(v1, "SC1"), "P1")["decisions"]
    b = V.simulate(contract, panel, A.resolve(v2, "SC1"), "P1")["decisions"]
    cols = [c for c in a.columns if c not in ("assumption_set_id",)]
    pd.testing.assert_frame_equal(a[cols], b[cols])


# --------------------------------------------------------------------------------------- leakage, determinism
def test_configuration_contains_no_data_derived_values(v2):
    observed = [p["key"] for p in v2["parameters"] if p["provenance"] == "OBSERVED"]
    assert observed == ["lead_time_days"] and isinstance(next(p for p in v2["parameters"] if p["key"] == "lead_time_days")["value"], str)
    assert "information_boundary" in v2["statements"] and "fulfilment" in v2["statements"]


def test_sf75_has_no_future_data_leakage(v2, contract, panel):
    sf = A.resolve(v2, "SF75")
    p2 = panel.copy()
    later = p2["week_index"] > 20
    p2.loc[later, "Units_Sold"] = np.random.default_rng(3).permutation(p2.loc[later, "Units_Sold"].to_numpy())
    for p in ("P0", "P2"):
        a, b = V.simulate(contract, panel, sf, p), V.simulate(contract, p2, sf, p)
        early = lambda r: r["decisions"][r["decisions"]["origin_week"] <= 20].reset_index(drop=True)  # noqa: E731
        pd.testing.assert_frame_equal(early(a), early(b))


def test_configuration_is_deterministic(v2):
    again = json.loads(B.V2_FILE.read_text(encoding="utf-8"))
    assert again == v2 and A.content_sha256(again) == A.content_sha256(v2)
    assert A.resolve(v2, "SF75") == A.resolve(again, "SF75")


# ------------------------------------------------------------------------------------- invalid parameters
def _param(doc, key):
    return next(p for p in doc["parameters"] if p["key"] == key)


@pytest.mark.parametrize("mutate,message", [
    (lambda d: _param(d, "stress_fill_rate_pct").update(value=120), "outside"),
    (lambda d: _param(d, "planning_fill_rate_pct").update(value=90), "not in allowed set"),
    (lambda d: _param(d, "order_inflation_for_expected_shortfall").update(value=True), "not in allowed set"),
    (lambda d: _param(d, "expiry_escalation_pct_of_p50").pop("sensitivity_range"), "missing"),
    (lambda d: _param(d, "case_size_units").update(value={"Bakery": 6, "Meat": 6, "Dairy": 12, "Beverages": 24}), "changed"),
    (lambda d: d["scenarios"]["SF75"]["overrides"].update(demand_multiplier=1.1), "SF75 must be SC1"),
    (lambda d: d["scenarios"]["SF75"]["overrides"].update(delivery_fill_rate_pct=150), "outside"),
    (lambda d: d["scenarios"]["SC2"]["overrides"].update(planning_fill_rate_pct=100), "may not be overridden"),
    (lambda d: d["scenarios"]["SC1"]["overrides"].update(not_a_parameter=1), "unknown key"),
    (lambda d: d["scenarios"].pop("SF75"), "missing scenario SF75"),
    (lambda d: d["approval"].update(status="APPROVED", approved_by="x", approved_at="2026-10-23"), "must stay DRAFT"),
    (lambda d: d.update(production_use=True), "production_use"),
    (lambda d: d["statements"].update(status="This file is production-ready."), "unsupported claims"),
    (lambda d: _param(d, "p0_netting_rule").update(value="NET_COMMITTED_TOO"), "not in allowed set"),
    (lambda d: _param(d, "p0_history_weeks").update(provenance="OBSERVED", evidence="OBSERVED_DATA",
                                                    supported_by_observed_business_data=True), "OBSERVED"),
    (lambda d: d.update(supersedes={"assumption_set_id": "AS-2026-10-22-v1", "content_sha256": "0" * 64}), "supersedes"),
    (lambda d: d.update(schema_version="1.0"), "schema_version"),
])
def test_invalid_v2_files_are_rejected(v1, v2, mutate, message):
    bad = copy.deepcopy(v2)
    mutate(bad)
    with pytest.raises(A.AssumptionError, match=message):
        check(bad, v1)


def test_an_edited_file_without_rehash_is_rejected(v2):
    bad = copy.deepcopy(v2)
    _param(bad, "stress_fill_rate_pct")["value"] = 80
    with pytest.raises(A.AssumptionError, match="content_sha256"):
        A.validate(bad)


# ------------------------------------------------------------------------------------- no production claims
def test_no_unsupported_production_claims(v2):
    assert v2["approval"]["status"] == "DRAFT" and v2["production_use"] is False
    assert "not for production use" in v2["statements"]["status"]
    rec = v2["evaluation_record"]
    assert rec["comparison_status"] == "NOT_RUN" and "exploratory" in rec["preliminary_exposure"]
    assert "unchanged" in rec["thresholds"]
    text = json.dumps(v2).lower()
    for phrase in ("production-ready", "production ready", "validated business policy", "guaranteed"):
        assert phrase not in text
