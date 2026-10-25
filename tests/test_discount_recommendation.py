"""Phase 1: numerical discount recommendation engine (simulated research) and assumption set v6 (DRAFT)."""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pandas as pd
import pytest

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v5 as V5
from dpe.decision import assumptions_v6 as V6
from dpe.decision import discount_recommendation as R

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dashboard"))
import dashboard_data as D  # noqa: E402

# a Dairy-like line: 28% assumed margin, 8% floor -> 25% is below the floor
LINE = dict(base_price=2.64, gross_margin_pct=28, min_margin_pct=8, at_risk_units=500.0, window=2,
            q10=2000.0, q50=3000.0, q90=4000.0, promotion_active=False, recorded_price=2.64)


@pytest.fixture(scope="module")
def params():
    return V6.recommendation_values(V6.load())


def _line(params, **kw):
    return R.recommend_line(**{**LINE, **kw}, params=params)


def _with(params, **kw):
    p = copy.deepcopy(params)
    p.update(kw)
    return p


# ------------------------------------------------------------------------------------------------ v6
def test_v6_is_a_valid_draft_and_v1_v5_are_unchanged():
    doc = V6.load()
    s = V6.validate(doc, V5.load())
    assert s["assumption_set_id"] == "AS-2026-10-23-v6" and s["status"] == "DRAFT" and s["parameters"] == 76
    assert len(s["added_parameters"]) == 13 and doc["production_use"] is False
    files = {"assumption_set_v1.json": "42116041ee61d265fc2756726de61b57b271513d9d095d914116208b4d2ccd50",
             "assumption_set_v2.json": "2119a2d4d2ae2b26b42d073f94c382b2e6d17a513aa5a6e9f00ee6df3910269f",
             "assumption_set_v3.json": "2b600cbe58e1baa59b540049976ff1f6f5705634ddce108014379412d847b7ad",
             "assumption_set_v4.json": "be102a5aee4957e875bc9f5788bee317bbc3bc7e4ecf5b9d02b4e0cf5a66da48"}
    for f, digest in files.items():
        assert hashlib.sha256((A.ASSUMPTION_DIR / f).read_bytes()).hexdigest() == digest
    assert hashlib.sha256((A.ASSUMPTION_DIR / "assumption_set_v5.json").read_bytes()).hexdigest().startswith("30e91da1")
    v5 = {p["key"]: p["value"] for p in V5.load()["parameters"]}
    v6 = {p["key"]: p["value"] for p in doc["parameters"]}
    assert all(v6[k] == v for k, v in v5.items())
    assert v6["discount_recommendation_approval_enabled"] is False and v6["discount_recommendation_execution_enabled"] is False
    assert "NOT VALIDATED FOR LIVE USE" in doc["statements"]["discount_recommendation"]
    rel = "config/assumptions/assumption_set_v6.json"  # frozen in docs/CHECKSUMS.sha256 (integrity only, not approval)
    assert config.load_expected_checksums()[rel] == config.sha256_file(config.PROJECT_ROOT / rel)


@pytest.mark.parametrize("mutate,message", [
    (lambda d: _p(d, "discount_recommendation_approval_enabled").update(value=True), "allowed set"),
    (lambda d: _p(d, "discount_recommendation_execution_enabled").update(value=True), "allowed set"),
    (lambda d: _p(d, "demand_response_decision_weights").update(value={"R1_LOW": 0.5, "R2_CENTRAL": 0.6}), "sum"),
    (lambda d: _p(d, "demand_response_decision_weights").update(
        value={"R0_NO_RESPONSE": 0.2, "R1_LOW": 0.2, "R2_CENTRAL": 0.4, "R3_HIGH": 0.2}), "never weight R0"),
    (lambda d: _p(d, "min_margin_pct").update(value={"Bakery": 10, "Beverages": 10, "Meat": 8, "Dairy": 5}), "changed"),
    (lambda d: d.update(production_use=True), "production_use"),
])
def test_invalid_v6_files_are_rejected(mutate, message):
    bad = copy.deepcopy(V6.load())
    mutate(bad)
    bad["approval"]["content_sha256"] = A.content_sha256(bad)
    with pytest.raises(A.AssumptionError, match=message):
        A.validate(bad)
        V6.validate(bad, V5.load())


def _p(doc, key):
    return next(p for p in doc["parameters"] if p["key"] == key)


# ------------------------------------------------------------------------------------------ arithmetic
def test_discount_and_margin_calculations_at_full_precision(params):
    o = R.outcome(2.64, 1.9008, 10, 100, 50, 1.6)
    assert o["price"] == pytest.approx(2.376, abs=1e-12) and o["extra_units"] == pytest.approx(16, abs=1e-12)
    assert o["units_sold"] == pytest.approx(116) and o["expired_units"] == pytest.approx(34)
    assert o["gross_profit"] == pytest.approx(116 * 2.376 - 1.9008 * 150, abs=1e-9)
    # closed form while the at-risk cap does not bind: S0 x P0 x d x (r(1-d) - 1)
    assert o["delta_vs_full_price"] == pytest.approx(100 * 2.64 * 0.1 * (1.6 * 0.9 - 1), abs=1e-9)
    # extra sales can never exceed the stock at risk
    capped = R.outcome(2.64, 1.9008, 25, 1000, 5, 3.0)
    assert capped["extra_units"] == 5 and capped["expired_units"] == 0
    # disposal cost makes expired units more expensive, so it favours selling them
    assert R.outcome(2.64, 1.9008, 10, 100, 50, 1.6, 20)["delta_vs_full_price"] > o["delta_vs_full_price"]
    _, rows = _line(params)
    gm = {r["markdown_pct"]: r["gross_margin_pct"] for r in rows}
    assert gm[0] == pytest.approx(28.0) and gm[20] == pytest.approx(100 * (2.112 - 1.9008) / 2.112)


@pytest.mark.parametrize("kw", [dict(base_price=0), dict(base_price=-1), dict(unit_cost=2.64), dict(unit_cost=-0.1),
                                dict(base_price=float("nan")), dict(markdown_pct=100), dict(baseline_units=-1)])
def test_invalid_prices_and_costs_raise(kw):
    args = dict(base_price=2.64, unit_cost=1.9008, markdown_pct=10, baseline_units=100, at_risk_units=50,
                response_pct_per_point=1.6)
    args.update(kw)
    with pytest.raises(ValueError):
        R.outcome(**args)


@pytest.mark.parametrize("kw,gap", [(dict(base_price=None), "MISSING_BASE_PRICE_OR_MARGIN"),
                                    (dict(base_price=0.0), "MISSING_BASE_PRICE_OR_MARGIN"),
                                    (dict(gross_margin_pct=None), "MISSING_BASE_PRICE_OR_MARGIN"),
                                    (dict(q90=float("nan")), "MISSING_FORECAST_QUANTILES"),
                                    (dict(at_risk_units=None), "MISSING_AT_RISK_UNITS"),
                                    (dict(window=None), "MISSING_MARKDOWN_WINDOW"),
                                    (dict(recorded_price=4.0), "PRICE_EVIDENCE_CONFLICT")])
def test_missing_or_conflicting_commercial_evidence_gives_no_recommendation(params, kw, gap):
    line, rows = _line(params, **kw)
    assert line["recommendation_status"] == R.EVIDENCE and gap in line["evidence_gaps"] and rows == []
    assert line["recommended_markdown_pct"] is None and "No recommendation" in line["explanation"]


def test_missing_recorded_price_is_not_a_conflict(params):
    line, _ = _line(params, recorded_price=float("nan"))
    assert line["recommendation_status"] == R.RECOMMEND


# ------------------------------------------------------------------------------------------ constraints
def test_margin_floor_and_maximum_markdown(params):
    line, rows = _line(params)
    by = {r["markdown_pct"]: r for r in rows}
    assert "BELOW_MARGIN_FLOOR" in by[25]["blocker_codes"] and not by[25]["permitted"]
    assert line["recommendation_status"] == R.RECOMMEND and line["recommended_markdown_pct"] != 25
    line, rows = _line(_with(params, max_discount_pct=15))
    by = {r["markdown_pct"]: r for r in rows}
    assert "EXCEEDS_MAX_MARKDOWN" in by[20]["blocker_codes"] and line["recommended_markdown_pct"] <= 15
    assert all(r["permitted"] for r in rows if r["is_recommended"])


@pytest.mark.parametrize("kw,overrides", [(dict(promotion_active=True), {}),
                                          (dict(gross_margin_pct=10, min_margin_pct=9.9), {})])
def test_conflicting_constraints_block_every_option(params, kw, overrides):
    line, rows = _line(_with(params, **overrides), **kw)
    assert line["recommendation_status"] == R.CONSTRAINED and not any(r["permitted"] for r in rows)
    assert line["recommended_markdown_pct"] is None and "blocked" in line["explanation"]


def test_no_eligible_lines_gives_no_assessment():
    lines, outcomes = D.discount_recommendations("SC2", "P0")
    assert set(lines.recommendation_status) == {R.NOT_ELIGIBLE} and len(outcomes) == 0
    assert R.summary(lines)["assessed"] == 0


# ------------------------------------------------------------------------------------- decision method
def test_recommendation_is_the_highest_expected_permitted_option(params):
    line, rows = _line(params)
    permitted = [r for r in rows if r["permitted"]]
    best = max(permitted, key=lambda r: r["expected_delta"])
    assert line["recommended_markdown_pct"] == best["markdown_pct"] and best["rank"] == 1
    w = params["demand_response_decision_weights"]
    assert best["expected_delta"] == pytest.approx(sum(
        wt * best["cases"][f"{k[:2]}@p50"]["delta_vs_full_price"] for k, wt in w.items()))
    assert R.LABEL in line["explanation"] and "ranks above" in line["explanation"]
    assert line["runner_up_markdown_pct"] in {r["markdown_pct"] for r in permitted}


def test_demand_response_sensitivity(params):
    _, rows = _line(params)
    for r in rows:  # a stronger response never makes an option worse
        d = [r["cases"][c]["delta_vs_full_price"] for c in ("R0@p50", "R1@p50", "R2@p50", "R3@p50")]
        assert d == sorted(d)
        if r["markdown_pct"] > 0:  # with no response every markdown only gives money away
            assert r["stress_delta"] < 0
            s0 = 3000 / 7 * 2
            assert r["stress_delta"] == pytest.approx(-s0 * 2.64 * r["markdown_pct"] / 100)
    weak = _with(params, demand_response_decision_weights={"R1_LOW": 1.0})
    assert _line(weak)[0]["recommendation_status"] == R.KEEP  # revenue-neutral response cannot pay for a markdown
    strong = _with(params, demand_response_decision_weights={"R3_HIGH": 1.0})
    assert _line(strong)[0]["recommended_markdown_pct"] >= _line(params)[0]["recommended_markdown_pct"]


def test_keeping_the_full_price_can_rank_first(params):
    line, rows = _line(params, at_risk_units=2.0)  # almost nothing at risk: the cap binds, cannibalisation dominates
    assert line["recommendation_status"] == R.KEEP and line["recommended_markdown_pct"] is None
    assert all(r["expected_delta"] < line["min_expected_benefit"] for r in rows if r["permitted"])
    assert "keeping the full price ranks first" in line["explanation"]


def test_too_uncertain_when_the_downside_exceeds_the_limit(params):
    line, rows = _line(_with(params, recommendation_max_downside_loss_pct_of_at_risk_cost=0))
    assert line["recommendation_status"] == R.UNCERTAIN and line["recommended_markdown_pct"] is None
    assert line["considered_markdown_pct"] is not None and "too uncertain" in line["explanation"]


def test_deterministic_repeatability():
    a = D.discount_recommendations("SC1", "P2")
    b = D.discount_recommendations("SC1", "P2")
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])


# ------------------------------------------------------------------------------------------ real data
def test_saved_evidence_results_are_safe_and_labelled():
    lines, outcomes = D.discount_recommendations("SC1", "P2")
    s = R.summary(lines)
    assert (s["assessed"], s[R.RECOMMEND], s[R.EVIDENCE]) == (91, 41, 50)
    assert s["approvals_created"] == s["proposals_created"] == s["prices_changed"] == 0
    assert set(lines.status) == {"HYPOTHETICAL_UNAPPROVED"} and set(lines.execution_status) == {"NOT_EXECUTED"}
    assert lines.approval_event_id.isna().all() and lines.proposal_id.isna().all()
    rec = outcomes[outcomes.is_recommended]
    assert rec.permitted.all() and (rec.gross_margin_pct >= 8 - 1e-9).all() and (rec.markdown_pct <= 25).all()
    chosen = lines[lines.recommendation_status == R.RECOMMEND]
    assert chosen.explanation.str.contains("NOT VALIDATED FOR LIVE USE").all()


def test_protected_outputs_unchanged_after_assessment(protected_registry):
    D.discount_recommendations("SC3", "P2")
    bad = [rel for rel, digest in protected_registry.items()
           if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    assert not bad
