"""Phase 2: dynamic pricing policy, pricing replay v1.3, evaluation rules and assumption set v7 (DRAFT)."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v6 as V6
from dpe.decision import assumptions_v7 as V7
from dpe.decision import dynamic_pricing as DP
from dpe.decision import pricing_evaluation as PE
from dpe.decision import replay as RP
from dpe.decision import replay_pricing as RPP
from dpe.forecast.panel import load_verified_panel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dashboard"))
import dashboard_data as D  # noqa: E402

SERIES = [(500, 1010), (500, 1018), (500, 1030), (500, 1034), (501, 1030), (501, 1034), (502, 1030), (502, 1034),
          (503, 1010), (503, 1018), (503, 1019), (504, 1018)]  # lines with eligible decisions under SC3 / P2


@pytest.fixture(scope="module")
def params():
    return V7.dynamic_pricing_values(V7.load())


@pytest.fixture(scope="module")
def inputs():
    panel, _ = load_verified_panel()
    contract = pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")
    return contract, panel


@pytest.fixture(scope="module")
def sc3(inputs, params):
    contract, panel = inputs
    return PE.run_scenario("SC3", contract, panel, B.load(), params, series=SERIES)


# ------------------------------------------------------------------------------------------------ v7 and policy
def test_v7_is_a_valid_draft_with_the_approved_conditions_and_v1_v6_are_unchanged():
    doc = V7.load()
    s = V7.validate(doc, V6.load())
    assert s["assumption_set_id"] == "AS-2026-10-23-v7" and s["status"] == "DRAFT" and s["parameters"] == 89
    assert len(s["added_parameters"]) == 13 and doc["production_use"] is False
    g = {p["key"]: p["value"] for p in doc["parameters"]}
    assert (g["dynamic_pricing_cooldown_days"], g["dynamic_pricing_max_events_per_window"],
            g["dynamic_pricing_event_window_days"]) == (7, 2, 28)
    assert g["dynamic_pricing_markdown_only"] is True and g["dynamic_pricing_ordering_interaction"] == "ORDERS_FIXED_TO_PRICING_OFF_PASS"
    assert g["dynamic_pricing_event_counting_rule"] == "COUNTED_AT_SELECTION_ON_DECISION_DAY"
    assert g["pricing_cooldown_days"] == "NOT_DEFINED"  # the v5 demonstration parameter is carried forward unchanged
    files = {"assumption_set_v1.json": "42116041", "assumption_set_v2.json": "2119a2d4", "assumption_set_v3.json": "2b600cbe",
             "assumption_set_v4.json": "be102a5a", "assumption_set_v5.json": "30e91da1", "assumption_set_v6.json": "2d7bc7fe"}
    for f, prefix in files.items():
        assert hashlib.sha256((A.ASSUMPTION_DIR / f).read_bytes()).hexdigest().startswith(prefix)
    expected = config.load_expected_checksums()
    for rel in ("config/assumptions/assumption_set_v7.json", "config/evaluation/evaluation_policy_phase2_v1.json",
                "docs/PHASE_2_DYNAMIC_PRICING_DESIGN.md"):
        assert expected[rel] == config.sha256_file(config.PROJECT_ROOT / rel), rel


@pytest.mark.parametrize("mutate,message", [
    (lambda d: _p(d, "dynamic_pricing_cooldown_days").update(value=3), "approved value"),
    (lambda d: _p(d, "dynamic_pricing_max_events_per_window").update(value=4), "approved value"),
    (lambda d: _p(d, "dynamic_pricing_markdown_only").update(value=False), "allowed set"),
    (lambda d: _p(d, "dynamic_pricing_ordering_interaction").update(value="PRICE_AWARE"), "allowed set"),
    (lambda d: _p(d, "discount_steps_pct").update(value=[5, 10]), "changed"),
    (lambda d: d.update(production_use=True), "production_use"),
])
def test_invalid_v7_files_are_rejected(mutate, message):
    bad = copy.deepcopy(V7.load())
    mutate(bad)
    bad["approval"]["content_sha256"] = A.content_sha256(bad)
    with pytest.raises(A.AssumptionError, match=message):
        A.validate(bad)
        V7.validate(bad, V6.load())


def _p(doc, key):
    return next(p for p in doc["parameters"] if p["key"] == key)


def test_evaluation_policy_is_frozen_and_registered_before_the_run(registry_scope):
    policy = json.loads(PE.POLICY_FILE.read_text(encoding="utf-8"))
    assert policy["status"] == "FROZEN_BEFORE_COMPARISON" and policy["scope"]["true_responses"] == list(PE.TRUTHS)
    checks = PE.prerun_checks()
    assert checks["all_passed"] and checks["evaluation_policy_registered"] and checks["assumption_v7_registered"]


# --------------------------------------------------------------------------------------------- critical validation
def test_pricing_off_reproduces_the_protected_p2_replay_exactly(inputs, params):
    """E1-E3 for SC1 on all 720 lines: orders, deliveries, stock flows, unmet and expiry identical to the protected run."""
    contract, panel = inputs
    v2 = B.load()
    values = A.resolve(v2, "SC1")
    off = RPP.simulate(contract, panel, values, policy="P2", assumption_sha=A.content_sha256(v2),
                       contract_run=config.FORECAST_CONTRACT_RUN_ID)
    shadow = RPP.simulate(contract, panel, values, dict(params, dynamic_pricing_max_events_per_window=0), policy="P2",
                          pricing=True, true_response="R3_HIGH", fixed=off)
    pre = PE.prerequisites("SC1", off, shadow, D.markdown_review("SC1", "P2"))
    assert all(pre["E1_pricing_off_equals_protected_P2"].values()), pre
    assert all(pre["E2_fixed_orders_no_markdown_equal_pricing_off"].values()), pre
    assert pre["E3_in_loop_eligibility_equals_saved_markdown_review"]["passed"], pre
    assert pre["passed"] and int((shadow["pricing_log"]["eligibility"] == "ELIGIBLE_FOR_MARKDOWN_REVIEW").sum()) == 91


# ------------------------------------------------------------------------------------------------- guards
def _event(day, end):
    return {"decision_day": day, "window_end_day": end}


def test_cooldown_event_limit_and_overlap_use_selection_days(params):
    assert DP.guard_check([], 232, params) == []
    assert "COOLDOWN" in DP.guard_check([_event(230, 231)], 232, params)  # 2 days after a selection
    assert DP.guard_check([_event(225, 226)], 232, params) == []  # exactly 7 days: allowed
    assert DP.guard_check([_event(218, 219), _event(225, 226)], 232, params) == ["EVENT_LIMIT"]  # 2 in the last 28 days
    assert DP.guard_check([_event(204, 205), _event(225, 226)], 232, params) == []  # day 204 is outside (232-28, 232]
    assert "WINDOW_IN_FORCE" in DP.guard_check([_event(225, 233)], 232, params)


def test_event_counting_rule_is_applied_consistently_in_the_replay(sc3, params):
    """Events are counted when selected; every selection is applied, and only selected windows change prices."""
    for t, e in sc3["truths"].items():
        log, days = e["result"]["pricing_log"], e["days"]
        ev = log[log["outcome"] == DP.SELECTED]
        assert len(ev) > 0 and e["gates"]["G4_eligibility_and_timing_guards"] and e["gates"]["G5_chronology"]
        assert set(days.loc[days["markdown_pct"] > 0, "event_id"]) == set(ev["event_id"])  # applied == selected
        for _, g in ev.sort_values("decision_day").groupby(["Store_ID", "Product_ID"]):
            dd = g["decision_day"].tolist()
            assert all(b - a >= 7 for a, b in zip(dd, dd[1:]))
            assert all(sum(1 for y in dd if x - 28 < y <= x) <= 2 for x in dd)
        blocked = log[log["outcome"] == "GUARD_BLOCKED"]
        assert (blocked["markdown_pct"] == 0).all() and blocked["guard_codes"].str.len().gt(0).all()


def test_decide_respects_eligibility_markdown_only_and_review_tags(params):
    state = {"waste_risk_category": "HIGH", "at_risk_units": 500.0, "earliest_batch_last_day": 235,
             "investigate_by_day": 234, "sellable_days_after_investigate_by": 1, "shortage_before_delivery": False,
             "christmas_any_horizon": False, "eligibility": "ELIGIBLE_FOR_MARKDOWN_REVIEW", "blocker_codes": ""}
    row = {"lower_p10_units": 2000.0, "median_p50_units": 3000.0, "upper_p90_units": 4000.0}
    r = DP.decide((504, 1018), 33, 232, state, row, 2.64, 28, 8, 2.64, False, [], False, params)
    assert r["outcome"] == DP.SELECTED and 0 < r["markdown_pct"] <= 25 and r["markdown_price"] < 2.64
    assert (r["window_start_day"], r["window_end_day"]) == (234, 235) and "PENDING_HUMAN_REVIEW" in r["review_tags"]
    assert (r["status"], r["approval_status"], r["execution_status"], r["application"]) == (
        "SIMULATED", "HYPOTHETICAL_UNAPPROVED", "NOT_EXECUTED", "SIMULATED_AS_IF_APPROVED")
    assert r["approval_event_id"] is None and r["proposal_id"] is None
    assert "MANDATORY_REVIEW" in DP.decide((504, 1018), 33, 232, state, row, 2.64, 28, 8, 2.64, False, [], True,
                                           params)["review_tags"]  # open inventory review case
    blocked = DP.decide((504, 1018), 33, 232, {**state, "eligibility": "BLOCKED", "blocker_codes": "CHRISTMAS_ESCALATION"},
                        row, 2.64, 28, 8, 2.64, False, [], False, params)
    assert blocked["outcome"] == "NOT_ELIGIBLE" and blocked["markdown_pct"] == 0 and blocked["markdown_price"] is None
    promo = DP.decide((504, 1018), 33, 232, state, row, 2.64, 28, 8, 2.64, True, [], False, params)
    assert promo["outcome"] != DP.SELECTED  # an overlapping promotion blocks every step


def test_priced_demand_applies_the_true_response_only_on_markdown_days():
    class Inner:
        decided_through_origin = 33
        log = []

        def week_demand(self, series, week):
            return [10, 10, 10, 10, 10, 10, 11]

    pdm = RPP.PricedDemand(Inner(), 1.6)
    pdm.markdown_days[(1, 2)] = {RP.day_index(34, 3): 20}
    out = pdm.week_demand((1, 2), 34)
    assert out == [10, 10, 13, 10, 10, 10, 11]  # floor(10 x 1.32 + 0.5) = 13
    assert pdm.week_demand((9, 9), 34) == [10, 10, 10, 10, 10, 10, 11]
    assert RPP.PricedDemand(Inner(), 0.0).week_demand((1, 2), 34) == [10, 10, 10, 10, 10, 10, 11]


# ----------------------------------------------------------------------------------------------- pricing runs
def test_every_hard_gate_passes_and_ordering_never_changes(sc3):
    for t, e in sc3["truths"].items():
        assert e["gates"]["passed"], (t, e["gates"])
        assert e["gates"]["G2_ordering_unchanged"]
        days = e["days"]
        assert (days["price"] <= days["reference_price"] + 1e-12).all()  # markdown only
    assert sc3["truths"]["R0_NO_RESPONSE"]["gates"]["G7_no_response_demand_equals_baseline"]


def test_belief_and_truth_are_separate(sc3):
    """The first decision of every line cannot depend on the true response (it is not an input to pricing)."""
    logs = {t: e["result"]["pricing_log"] for t, e in sc3["truths"].items()}
    first = min(logs["R0_NO_RESPONSE"]["origin_week"])
    cols = ["Store_ID", "Product_ID", "outcome", "markdown_pct", "window_start_day", "window_end_day", "explanation"]
    ref = logs["R0_NO_RESPONSE"].query("origin_week == @first")[cols].reset_index(drop=True)
    for t, log in logs.items():
        pd.testing.assert_frame_equal(log.query("origin_week == @first")[cols].reset_index(drop=True), ref)
    # with no response, markdowns only give money away: nothing extra sells and nothing less expires
    d0 = sc3["truths"]["R0_NO_RESPONSE"]["measures"]["delta"]
    assert d0["sim_sold_units"] == 0 and d0["sim_expired_units"] == 0 and d0["gross_profit"] < 0


def test_no_look_ahead_future_demand_cannot_change_earlier_decisions(inputs, params):
    contract, panel = inputs
    v2 = B.load()
    values = A.resolve(v2, "SC3")
    def run(p):
        off = RPP.simulate(contract, p, values, policy="P2", series=SERIES[:6])
        return RPP.simulate(contract, p, values, params, policy="P2", pricing=True, true_response="R2_CENTRAL", fixed=off,
                            series=SERIES[:6])["pricing_log"]
    base = run(panel)
    scrambled = panel.copy()
    future = scrambled["week_index"] >= 43
    scrambled.loc[future, "Units_Sold"] = scrambled.loc[future, "Units_Sold"] * 3 + 7
    alt = run(scrambled)
    cols = ["Store_ID", "Product_ID", "origin_week", "outcome", "markdown_pct", "window_start_day", "eligibility"]
    pd.testing.assert_frame_equal(base[base.origin_week <= 41][cols].reset_index(drop=True),
                                  alt[alt.origin_week <= 41][cols].reset_index(drop=True))


def test_deterministic_repeatability(inputs, params, sc3):
    contract, panel = inputs
    again = PE.run_scenario("SC3", contract, panel, B.load(), params, series=SERIES)
    for t in PE.TRUTHS:
        pd.testing.assert_frame_equal(again["truths"][t]["result"]["pricing_log"], sc3["truths"][t]["result"]["pricing_log"])
        pd.testing.assert_frame_equal(again["truths"][t]["days"], sc3["truths"][t]["days"])


def test_gross_profit_accounting_and_paired_costs(sc3):
    base = sc3["base_days"]
    for t, e in sc3["truths"].items():
        days, m = e["days"], e["measures"]
        assert days["received_cost"].sum() == pytest.approx(base["received_cost"].sum())  # identical receipts
        assert days["revenue"].to_numpy() == pytest.approx((days["sim_sold_units"] * days["price"]).to_numpy())
        assert m["delta"]["gross_profit"] == pytest.approx(m["delta"]["revenue"])  # disposal 0%: only revenue moves
        assert m["benefits"]["gross_profit_gain"] * m["harms"]["gross_profit_loss"] == 0


def test_thresholds_follow_the_frozen_rules():
    def mk(events, gp, expired, unmet, base_expired_cost=100.0, base_sold=1000.0):
        return {"markdown_events": events, "delta": {"gross_profit": gp, "sim_expired_units": expired,
                                                    "sim_unmet_units_illustrative": unmet},
                "baseline": {"expired_cost": base_expired_cost, "sim_sold_units": base_sold}}
    th = PE.thresholds({"R0_NO_RESPONSE": mk(3, -25.0, 0, 0), "R1_LOW": mk(3, -10.5, -5, 0),
                        "R2_CENTRAL": mk(3, 0.0, -1, 5), "R3_HIGH": mk(3, -0.01, -9, 6)})
    assert th["T4_R0_NO_RESPONSE"] == "PASS" and th["T3_R1_LOW"] == "FAIL" and th["T1_R2_CENTRAL"] == "PASS"
    assert th["T2_R3_HIGH"] == "FAIL" and th["T5_UNMET_R2_CENTRAL"] == "PASS" and th["T5_UNMET_R3_HIGH"] == "FAIL"
    none = PE.thresholds({t: mk(0, 0.0, 0, 0) for t in PE.TRUTHS})
    assert set(none.values()) == {"NOT_APPLICABLE"}


def test_protected_outputs_unchanged_after_pricing_runs(sc3, protected_registry):
    bad = [rel for rel, digest in protected_registry.items()
           if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    assert not bad
