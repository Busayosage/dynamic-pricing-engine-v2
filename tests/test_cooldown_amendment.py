"""Amendment A1: 7-day cooldown measured from the END of the previous markdown window (assumption set v8, DRAFT).

The frozen Phase 2 rule (v7, selection-day cooldown) and its protected run stay unchanged; A1 is a separate version."""
from __future__ import annotations

import copy
import io

import pandas as pd
import pytest

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v7 as V7
from dpe.decision import assumptions_v8 as V8
from dpe.decision import dynamic_pricing as DP
from dpe.decision import dynamic_pricing_a1 as DPA1
from dpe.decision import pricing_evaluation as PE
from dpe.decision import replay_pricing as RPP
from dpe.decision import replay_pricing_a1 as RPA1
from dpe.forecast.panel import load_verified_panel

RUN = config.PROJECT_ROOT / "outputs" / "runs" / "20261023-233225_dynamic_pricing_evaluation"
STATE = {"waste_risk_category": "HIGH", "at_risk_units": 500.0, "earliest_batch_last_day": 249, "investigate_by_day": 248,
         "sellable_days_after_investigate_by": 1, "shortage_before_delivery": False, "christmas_any_horizon": False,
         "eligibility": "ELIGIBLE_FOR_MARKDOWN_REVIEW", "blocker_codes": ""}
ROW = {"lower_p10_units": 2000.0, "median_p50_units": 3000.0, "upper_p90_units": 4000.0}


@pytest.fixture(scope="module")
def params():
    return V8.dynamic_pricing_values(V8.load())


def _rt(df):
    return pd.read_csv(io.StringIO(df.to_csv(index=False)))


def _ev(day, start, end):
    return {"decision_day": day, "window_start_day": start, "window_end_day": end}


# ----------------------------------------------------------------------------------------------- v8 and protection
def test_v8_adds_only_the_cooldown_basis_and_v7_is_unchanged(protected_registry):
    doc = V8.load()
    s = V8.validate(doc, V7.load())
    assert s["added_parameters"] == ["dynamic_pricing_cooldown_basis"] and s["parameters"] == 90 and s["status"] == "DRAFT"
    g = {p["key"]: p["value"] for p in doc["parameters"]}
    assert g["dynamic_pricing_cooldown_basis"] == "END_OF_PREVIOUS_MARKDOWN_WINDOW"
    assert (g["dynamic_pricing_cooldown_days"], g["dynamic_pricing_max_events_per_window"],
            g["dynamic_pricing_event_window_days"]) == (7, 2, 28)
    assert A.content_sha256(V7.load()) == V8.V7_CONTENT_SHA256
    expected = protected_registry
    for rel in ("config/assumptions/assumption_set_v7.json", "config/evaluation/evaluation_policy_phase2_v1.json",
                "docs/PHASE_2_DYNAMIC_PRICING_DESIGN.md"):
        assert expected[rel] == config.sha256_file(config.PROJECT_ROOT / rel)
    bad = [r for r, d in expected.items() if config.sha256_file(config.PROJECT_ROOT / r) != d]
    assert not bad  # the protected Phase 2 run and every earlier output are untouched


@pytest.mark.parametrize("mutate,message", [
    (lambda d: _p(d, "dynamic_pricing_cooldown_basis").update(value="SELECTION_DAY"), "allowed set"),
    (lambda d: _p(d, "dynamic_pricing_cooldown_days").update(value=14), "changed"),
    (lambda d: d.update(production_use=True), "production_use"),
])
def test_invalid_v8_files_are_rejected(mutate, message):
    bad = copy.deepcopy(V8.load())
    mutate(bad)
    bad["approval"]["content_sha256"] = A.content_sha256(bad)
    with pytest.raises(A.AssumptionError, match=message):
        A.validate(bad)
        V8.validate(bad, V7.load())


def _p(doc, key):
    return next(p for p in doc["parameters"] if p["key"] == key)


# ----------------------------------------------------------------------------------------------------- the rule
def test_cooldown_counts_seven_complete_days_after_the_previous_window_ends(params):
    history = [_ev(232, 234, 235)]  # previous markdown ended on day 235
    for start in range(236, 243):  # days 236..242 would start inside the 7 complete days
        assert DPA1.guard_check(history, 239, start, params) == ["COOLDOWN"], start
    assert DPA1.guard_check(history, 239, 243, params) == []  # 236..242 elapsed in full: day 243 is allowed
    # the v7 rule (decision-day basis) would have allowed the weekly repeat that A1 now blocks
    assert DP.guard_check(history, 239, V7.dynamic_pricing_values(V7.load())) == []


def test_rolling_limit_and_no_overlap_are_kept(params):
    assert DPA1.guard_check([_ev(211, 212, 213), _ev(218, 219, 220)], 232, 233, params) == ["EVENT_LIMIT"]  # both in (204, 232]
    assert DPA1.guard_check([_ev(225, 226, 240)], 232, 248, params) == ["WINDOW_IN_FORCE"]
    assert DPA1.guard_check([], 232, 233, params) == []


def test_cooldown_blocks_an_otherwise_eligible_repeat_and_allows_it_after_the_full_interval(params):
    first = DPA1.decide((501, 1030), 33, 232, {**STATE, "investigate_by_day": 234, "earliest_batch_last_day": 235}, ROW,
                        2.64, 28, 8, 2.64, False, [], False, params)
    assert first["outcome"] == DP.SELECTED and first["window_end_day"] == 235
    week_after = DPA1.decide((501, 1030), 34, 239, {**STATE, "investigate_by_day": 240, "earliest_batch_last_day": 241},
                             ROW, 2.64, 28, 8, 2.64, False, [first], False, params)
    assert week_after["outcome"] == "GUARD_BLOCKED" and week_after["guard_codes"] == "COOLDOWN"
    assert week_after["markdown_pct"] == 0 and week_after["markdown_price"] is None and week_after["event_id"] is None
    assert week_after["eligibility"] == "ELIGIBLE_FOR_MARKDOWN_REVIEW" and "complete days" in week_after["explanation"]
    two_weeks = DPA1.decide((501, 1030), 35, 246, {**STATE, "investigate_by_day": 247, "earliest_batch_last_day": 248},
                            ROW, 2.64, 28, 8, 2.64, False, [first], False, params)
    assert two_weeks["outcome"] == DP.SELECTED and two_weeks["window_start_day"] >= 235 + 8
    # same state without history: the A1 policy chooses exactly what the frozen v7 policy chooses
    v7 = DP.decide((501, 1030), 33, 232, {**STATE, "investigate_by_day": 234, "earliest_batch_last_day": 235}, ROW,
                   2.64, 28, 8, 2.64, False, [], False, V7.dynamic_pricing_values(V7.load()))
    assert {k: v for k, v in first.items()} == v7


def test_amendment_needs_v8_parameters():
    with pytest.raises(ValueError, match="v8"):
        DPA1.guard_check([_ev(232, 234, 235)], 239, 240, V7.dynamic_pricing_values(V7.load()))


# ------------------------------------------------------------------------------------------- in the replay (SC3)
@pytest.fixture(scope="module")
def sc3_lines():
    """Lines whose protected v7 run has a markdown starting < 8 days after the previous one ended (A1 would block)."""
    d = pd.read_csv(RUN / "SC3" / "R2_CENTRAL" / "pricing_decisions.csv")
    s = d[d.outcome == DP.SELECTED].sort_values("decision_day")
    hit = []
    for k, g in s.groupby(["Store_ID", "Product_ID"]):
        if (g["window_start_day"].to_numpy()[1:] < g["window_end_day"].to_numpy()[:-1] + 8).any():
            hit.append(k)
    assert len(hit) == 19
    return hit[:5]


@pytest.fixture(scope="module")
def runs(sc3_lines, params):
    panel, _ = load_verified_panel()
    contract = pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")
    values = A.resolve(B.load(), "SC3")
    off = RPP.simulate(contract, panel, values, policy="P2", series=sc3_lines)
    v7p = V7.dynamic_pricing_values(V7.load())
    v13 = RPP.simulate(contract, panel, values, v7p, policy="P2", pricing=True, true_response="R2_CENTRAL", fixed=off,
                       series=sc3_lines)
    v14 = RPA1.simulate(contract, panel, values, params, policy="P2", pricing=True, true_response="R2_CENTRAL", fixed=off,
                        series=sc3_lines)
    return {"contract": contract, "off": off, "v13": v13, "v14": v14}


def test_frozen_v13_still_reproduces_the_protected_run_for_these_lines(runs, sc3_lines):
    saved = pd.read_csv(RUN / "SC3" / "R2_CENTRAL" / "pricing_decisions.csv")
    saved = saved[saved.set_index(["Store_ID", "Product_ID"]).index.isin(sc3_lines)].reset_index(drop=True)
    pd.testing.assert_frame_equal(_rt(runs["v13"]["pricing_log"]), saved)


def test_a1_replay_blocks_the_repeats_and_keeps_every_other_safeguard(runs, params):
    v13, v14 = runs["v13"]["pricing_log"], runs["v14"]["pricing_log"]
    key = ["Store_ID", "Product_ID", "origin_week"]
    m = v13.merge(v14, on=key, suffixes=("_v13", "_v14"))
    newly = m[(m.outcome_v13 == DP.SELECTED) & (m.outcome_v14 == "GUARD_BLOCKED")]
    assert len(newly) >= 1 and newly["guard_codes_v14"].str.contains("COOLDOWN").all()
    sel = v14[v14.outcome == DP.SELECTED].sort_values("decision_day")
    repeats_allowed = 0
    for _, g in sel.groupby(["Store_ID", "Product_ID"]):
        starts, ends = g["window_start_day"].to_numpy(), g["window_end_day"].to_numpy()
        assert (starts[1:] >= ends[:-1] + 8).all()  # every repeat waited 7 complete days
        repeats_allowed += len(g) - 1
    assert repeats_allowed >= 1  # a repeat markdown is still allowed after the full interval
    days_off = RPP.price_days(runs["off"], runs["contract"], params)
    days = RPA1.price_days(runs["v14"], runs["contract"], params)
    gates = PE.hard_gates(runs["v14"], runs["off"], days_off, days, params)
    assert gates["passed"], gates  # ordering unchanged, markdown only, chronology, labels, conservation
    assert len(v14) == len(v13)  # one pricing record per line and week in both versions
