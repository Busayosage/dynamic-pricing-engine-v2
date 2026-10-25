"""Stage 8B: pricing intelligence demonstration (illustrative arithmetic, read-only) and assumption set v5 (DRAFT)."""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v4 as V4
from dpe.decision import assumptions_v5 as V5
from dpe.decision import pricing_demo as PD

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dashboard"))
import dashboard_data as D  # noqa: E402

V5_CONTENT_SHA256 = "21180c904444f6c29dae7105e07f8b1e09828920711fcb2dc48d8fce2658706a"
STEPS, DISPLAY = [5, 10, 15, 20, 25], [0, 5, 10, 15, 20, 25]


@pytest.fixture(scope="module")
def params():
    return V5.pricing_values(V5.load())


@pytest.fixture(scope="module")
def demo():
    return D.pricing_demo("SC1", "P2")


# ------------------------------------------------------------------------------------------------ v5
def test_v5_is_a_valid_draft_and_v1_v4_are_unchanged():
    doc = V5.load()
    s = V5.validate(doc, V4.load())
    assert s["assumption_set_id"] == "AS-2026-10-23-v5" and s["status"] == "DRAFT" and s["parameters"] == 63
    assert A.content_sha256(doc) == V5_CONTENT_SHA256 and doc["production_use"] is False
    files = {"assumption_set_v1.json": "42116041ee61d265fc2756726de61b57b271513d9d095d914116208b4d2ccd50",
             "assumption_set_v2.json": "2119a2d4d2ae2b26b42d073f94c382b2e6d17a513aa5a6e9f00ee6df3910269f",
             "assumption_set_v3.json": "2b600cbe58e1baa59b540049976ff1f6f5705634ddce108014379412d847b7ad",
             "assumption_set_v4.json": "be102a5aee4957e875bc9f5788bee317bbc3bc7e4ecf5b9d02b4e0cf5a66da48"}
    for f, digest in files.items():
        assert hashlib.sha256((A.ASSUMPTION_DIR / f).read_bytes()).hexdigest() == digest
    v4 = {p["key"]: p["value"] for p in V4.load()["parameters"]}
    v5 = {p["key"]: p["value"] for p in doc["parameters"]}
    assert all(v5[k] == v for k, v in v4.items())
    assert v5["pricing_cooldown_days"] == "NOT_DEFINED" and v5["pricing_cooldown_enforced"] is False
    assert v5["pricing_recommendation_enabled"] is False and v5["pricing_proposals_enabled"] is False


@pytest.mark.parametrize("mutate,message", [
    (lambda d: _p(d, "pricing_cooldown_days").update(value=7), "allowed set"),
    (lambda d: _p(d, "pricing_recommendation_enabled").update(value=True), "allowed set"),
    (lambda d: _p(d, "pricing_proposals_enabled").update(value=True), "allowed set"),
    (lambda d: _p(d, "min_margin_pct").update(value={"Bakery": 10, "Beverages": 10, "Meat": 8, "Dairy": 5}), "changed"),
    (lambda d: d.update(production_use=True), "production_use"),
])
def test_invalid_v5_files_are_rejected(mutate, message):
    bad = copy.deepcopy(V5.load())
    mutate(bad)
    bad["approval"]["content_sha256"] = A.content_sha256(bad)
    with pytest.raises(A.AssumptionError, match=message):
        A.validate(bad)
        V5.validate(bad, V4.load())


def _p(doc, key):
    return next(p for p in doc["parameters"] if p["key"] == key)


# ------------------------------------------------------------------------------------------ arithmetic
def test_cottage_cheese_arithmetic_at_full_precision():
    rows = {r["markdown_pct"]: r for r in PD.options(2.64, 28, 8, 25, STEPS, DISPLAY, False)}
    assert rows[0]["illustrative_unit_cost"] == pytest.approx(1.9008, abs=1e-12)
    expected = {0: (2.64, 0.7392, 28.0, 1.0), 5: (2.508, 0.6072, 24.2105263158, 1.2173913043),
                10: (2.376, 0.4752, 20.0, 1.5555555556), 15: (2.244, 0.3432, 15.2941176471, 2.1538461538),
                20: (2.112, 0.2112, 10.0, 3.5), 25: (1.98, 0.0792, 4.0, 9.3333333333)}
    for d, (price, gp, gm, units) in expected.items():
        r = rows[d]
        assert r["illustrative_price"] == pytest.approx(price, abs=1e-9)
        assert r["illustrative_gross_profit_per_unit"] == pytest.approx(gp, abs=1e-9)
        assert r["gross_margin_pct"] == pytest.approx(gm, abs=1e-8)
        assert r["units_to_preserve_gross_profit"] == pytest.approx(units, abs=1e-8)
    assert [rows[d]["status"] for d in DISPLAY] == [PD.FULL_PRICE] + [PD.PASSES] * 4 + [PD.BLOCKED]
    assert rows[25]["blocker_codes"] == "BELOW_MARGIN_FLOOR"
    assert PD.floor_price(2.64, 28, 8) == pytest.approx(2.0660869565, abs=1e-9)


def test_rounding_is_display_only():
    r = next(x for x in PD.options(2.64, 28, 8, 25, STEPS, DISPLAY, False) if x["markdown_pct"] == 5)
    assert r["illustrative_price"] == 2.64 * 0.95 and r["illustrative_price"] != round(r["illustrative_price"], 2)
    assert r["gross_margin_pct"] != round(r["gross_margin_pct"], 1)  # 24.2105…, not 24.2
    # Rounding a price first would change the margin: the module never does that.
    rounded_gm = 100 * (round(2.64 * 0.95, 2) - 1.9008) / round(2.64 * 0.95, 2)
    assert abs(rounded_gm - r["gross_margin_pct"]) > 1e-3


def test_margin_floor_boundary():
    # Price exactly at the floor passes; one hair below fails.
    base, gm, mn = 10.0, 30, 10
    cost = base * 0.7
    d_exact = 100 * (1 - (cost / 0.9) / base)  # 22.222...% leaves exactly 10% margin
    exact = PD.options(base, gm, mn, 25, [d_exact], [0, d_exact], False)[1]
    assert exact["gross_margin_pct"] == pytest.approx(10.0, abs=1e-9) and exact["status"] == PD.PASSES
    below = PD.options(base, gm, mn, 25, [d_exact + 1e-6], [0, d_exact + 1e-6], False)[1]
    assert below["status"] == PD.BLOCKED and "BELOW_MARGIN_FLOOR" in below["blocker_codes"]


def test_maximum_markdown_and_permitted_steps():
    rows = {r["markdown_pct"]: r for r in PD.options(10, 60, 5, 20, [5, 10, 15, 20], [0, 5, 20, 25, 30], False)}
    assert rows[20]["status"] == PD.PASSES
    assert rows[25]["blocker_codes"].split("|") == ["NOT_AN_ALLOWED_STEP", "EXCEEDS_MAX_MARKDOWN"]
    assert "EXCEEDS_MAX_MARKDOWN" in rows[30]["blocker_codes"]


def test_promotion_blocks_every_markdown_but_not_the_reference_row():
    rows = PD.options(2.64, 28, 8, 25, STEPS, DISPLAY, True)
    assert rows[0]["status"] == PD.FULL_PRICE
    assert all(r["status"] == PD.BLOCKED and r["blocker_codes"].startswith("OVERLAPPING_PROMOTION") for r in rows[1:])
    assert rows[-1]["blocker_codes"] == "OVERLAPPING_PROMOTION|BELOW_MARGIN_FLOOR"  # all reasons kept


@pytest.mark.parametrize("base,gm", [(None, 28), (float("nan"), 28), (0, 28), (-1, 28), (2.64, None)])
def test_missing_inputs_are_rejected(base, gm):
    with pytest.raises(ValueError):
        PD.options(base, gm, 8, 25, STEPS, DISPLAY, False)


def test_no_profit_case_has_no_preservation_multiplier():
    rows = PD.options(1.0, 10, 0, 25, STEPS, DISPLAY, False)  # 10% margin: a 10%+ markdown leaves no profit
    r10 = next(r for r in rows if r["markdown_pct"] == 10)
    assert r10["units_to_preserve_gross_profit"] is None and "NO_PROFIT_PER_UNIT" in r10["blocker_codes"]


# ------------------------------------------------------------------------------------------- assessment
def test_options_only_for_stage_7b_eligible_lines(demo):
    lines, opts = demo
    s = PD.summary(lines, opts)
    assert s["OPTIONS_SHOWN"] == 91 and s["MISSING_INPUT"] == 0 and s["options"] == 91 * 6
    eligible = lines[lines.eligibility == "ELIGIBLE_FOR_MARKDOWN_REVIEW"]
    assert (eligible.line_status == "OPTIONS_SHOWN").all()
    keys = set(zip(opts.Store_ID, opts.Product_ID, opts.origin_week))
    assert keys == set(zip(eligible.Store_ID, eligible.Product_ID, eligible.origin_week))
    assert lines[lines.line_status != "OPTIONS_SHOWN"].illustrative_unit_cost.isna().all()


def test_worked_example_line(demo):
    lines, opts = demo
    L = lines[(lines.Store_ID == 504) & (lines.Product_ID == 1030) & (lines.target_week == 40)].iloc[0]
    assert L.illustrative_base_price == pytest.approx(2.64) and L.illustrative_unit_cost == pytest.approx(1.9008)
    assert L.illustrative_at_risk_stock_cost == pytest.approx(2373.6 * 1.9008, rel=1e-6)
    assert L.cooldown_status.startswith("NOT_IMPLEMENTED") and L.recommended_option is None


def test_missing_reference_price_gives_missing_input(params):
    md = D.markdown_review("SC1", "P2")
    ref = D.reference_prices()
    e = md[md.eligibility == "ELIGIBLE_FOR_MARKDOWN_REVIEW"].iloc[0]
    hit = (ref.Store_ID == e.Store_ID) & (ref.Product_ID == e.Product_ID) & (ref.origin_week == e.origin_week)
    ref = ref.copy()
    ref.loc[hit, "reference_price_asof"] = np.nan
    lines, opts = PD.assess(md, ref, params)
    row = lines[(lines.Store_ID == e.Store_ID) & (lines.Product_ID == e.Product_ID) & (lines.origin_week == e.origin_week)].iloc[0]
    assert row.line_status == "MISSING_INPUT" and "reference price" in row.missing_inputs
    assert len(opts) == 90 * 6


@pytest.mark.parametrize("scenario,policy", [("SC3", "P2"), ("SC1", "P1"), ("SF75", "P0")])
def test_policy_and_scenario_consistency(scenario, policy):
    lines, opts = D.pricing_demo(scenario, policy)
    md = D.markdown_review(scenario, policy)
    assert (lines.line_status == "OPTIONS_SHOWN").sum() == (md.eligibility == "ELIGIBLE_FOR_MARKDOWN_REVIEW").sum()
    assert set(lines.policy_id) == {policy} and set(lines.scenario_id) == {scenario}
    if len(opts):
        assert set(opts.policy_id) == {policy} and set(opts.scenario_id) == {scenario}


def test_no_recommendation_prediction_or_execution(demo):
    lines, opts = demo
    assert lines.recommended_option.isna().all() and lines.proposal_id.isna().all() and lines.approval_event_id.isna().all()
    assert set(lines.execution_status) == {"NOT_EXECUTED"} and set(lines.state) == {"STATE_1B_DEMONSTRATION_ONLY"}
    for col in list(lines.columns) + list(opts.columns):
        assert not any(w in col for w in ("recommend_score", "uplift", "elasticity", "saving", "predicted", "optimal", "best"))
    src = Path(PD.__file__).read_text(encoding="utf-8")
    for forbidden in ("to_csv", "write_text", "open(", "simulate(", "sqlite", "requests", "discount_uplift"):
        assert forbidden not in src, forbidden


def test_determinism_and_no_future_data(params, demo):
    md = D.markdown_review("SC1", "P2")
    ref = D.reference_prices()
    a = PD.assess(md, ref, params)
    pd.testing.assert_frame_equal(a[1], demo[1])
    later = ref.copy()
    later.loc[later.origin_week > 42, "reference_price_asof"] = 99.0
    b = PD.assess(md, later, params)
    early = lambda df: df[df.origin_week <= 42].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(early(b[1]), early(a[1]))


def test_protected_files_unchanged(protected_registry):
    bad = [rel for rel, digest in protected_registry.items()
           if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    assert not bad
