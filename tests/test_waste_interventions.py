"""Phase 3: waste intervention intelligence (advisory, read-only) and assumption set v9 (DRAFT)."""
from __future__ import annotations

import copy
import inspect
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v8 as V8
from dpe.decision import assumptions_v9 as V9
from dpe.decision import discount_recommendation as R
from dpe.decision import waste_interventions as WI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dashboard"))
import dashboard_data as D  # noqa: E402

KEY = ["Store_ID", "Product_ID", "origin_week"]


@pytest.fixture(scope="module")
def sc1():
    return D.waste_interventions("SC1")


@pytest.fixture(scope="module")
def sc3():
    return D.waste_interventions("SC3")


def _row(**kw):
    base = dict(ordered_units=500, shortage_before_delivery=False, planned_buffer_units=0.0, at_risk_units=800.0,
                Region="London", eligibility="ELIGIBLE_FOR_MARKDOWN_REVIEW", blocker_codes="", phase1_status=R.RECOMMEND,
                phase1_markdown_pct=20)
    base.update(kw)
    return SimpleNamespace(**base)


# ------------------------------------------------------------------------------------------------- v9
def test_v9_is_a_valid_draft_and_v1_v8_are_unchanged(protected_registry):
    doc = V9.load()
    s = V9.validate(doc, V8.load())
    assert s["assumption_set_id"] == "AS-2026-10-24-v9" and s["status"] == "DRAFT" and s["parameters"] == 97
    assert len(s["added_parameters"]) == 7 and doc["production_use"] is False
    assert "INVESTIGATE ONLY" in doc["statements"]["waste_interventions"]
    bad = [r for r, d in protected_registry.items() if config.sha256_file(config.PROJECT_ROOT / r) != d]
    assert not bad  # v1-v8, protected runs and evaluations untouched


@pytest.mark.parametrize("mutate,message", [
    (lambda d: _p(d, "waste_intervention_transfer_pairing_rule").update(value="ANY_STORE"), "allowed set"),
    (lambda d: _p(d, "dynamic_pricing_cooldown_basis").update(value="SELECTION_DAY"), "allowed set"),
    (lambda d: d.update(production_use=True), "production_use"),
])
def test_invalid_v9_files_are_rejected(mutate, message):
    bad = copy.deepcopy(V9.load())
    mutate(bad)
    bad["approval"]["content_sha256"] = A.content_sha256(bad)
    with pytest.raises(A.AssumptionError, match=message):
        A.validate(bad)
        V9.validate(bad, V8.load())


def _p(doc, key):
    return next(p for p in doc["parameters"] if p["key"] == key)


# -------------------------------------------------------------------- 1 read-only, unapproved, not executed
def test_module_is_read_only_and_nothing_is_executed(sc1, sc3):
    src = inspect.getsource(WI)
    for forbidden in ("to_csv", "write_text", "open(", "sqlite", "requests.", "save_table", "save_json"):
        assert forbidden not in src, forbidden
    for lines, opts in (sc1, sc3):
        assert set(lines["execution_status"]) == {"NOT_EXECUTED"} and lines["approval_event_id"].isna().all()
        assert set(opts["execution_status"]) == {"NOT_EXECUTED"} and set(opts["review_status"]) == {"PENDING_HUMAN_INVESTIGATION"}
        s = WI.summarise(lines, opts)
        assert s["actions_executed"] == 0 and s["approvals_created"] == 0


# ------------------------------------------------------------------------------ correct at-risk identification
def test_at_risk_lines_follow_the_saved_waste_risk(sc1, sc3):
    for sc, (lines, opts), n in (("SC1", sc1, 134), ("SC3", sc3, 724)):
        w = D.waste_risk(sc, "P2")
        assert len(lines) == len(w) == 14400
        at = lines[lines.line_outcome == "INVESTIGATIONS_SUGGESTED"]
        assert len(at) == n and set(at.waste_risk_category) <= {"HIGH", "MODERATE"}
        assert set(lines.loc[lines.waste_risk_category == "LOW", "line_outcome"]) == {"NO_INTERVENTION_NEEDED"}
        assert len(opts) == 5 * n and (opts.groupby(KEY).size() == 5).all()


# ------------------------------------------------------------------- 2 missing evidence -> INSUFFICIENT EVIDENCE
def test_missing_evidence_returns_insufficient_evidence():
    md = WI.assess_markdown(_row(eligibility="INSUFFICIENT_INFORMATION"), None)
    assert md["status"] == WI.INSUFFICIENT
    md = WI.assess_markdown(_row(phase1_status=R.EVIDENCE), None)
    assert md["status"] == WI.INSUFFICIENT and "not good enough" in md["explanation"]
    no = WI.assess_no_action([], WI.INSUFFICIENT, R.EVIDENCE)
    assert no["status"] == WI.INSUFFICIENT and "INSUFFICIENT EVIDENCE" in no["explanation"]


def test_only_donation_left_means_insufficient_evidence_investigate(sc3):
    lines, opts = sc3
    x = lines[lines.current_stock_outcome == "INSUFFICIENT_EVIDENCE_INVESTIGATE"]
    assert len(x) > 0
    o = opts.merge(x[KEY], on=KEY)
    active = o[o.status.isin(WI.ACTIVE) & (o.decision_group == "CURRENT_STOCK")]
    assert set(active.option) == {"DONATION_OR_DISPOSAL"}  # nothing better than level 0
    assert x.manager_summary.str.contains("INSUFFICIENT EVIDENCE").all()


# ---------------------------------------------------------------------------- 3 transfer and donation ceilings
def test_transfer_and_donation_never_exceed_investigation(sc1, sc3):
    for _, opts in (sc1, sc3):
        assert set(opts.loc[opts.option == "TRANSFER", "status"]) <= {WI.OPPORTUNITY, WI.NA}
        assert set(opts.loc[opts.option == "DONATION_OR_DISPOSAL", "status"]) <= {WI.INVESTIGATE, WI.NA}
        t = opts[(opts.option == "TRANSFER") & (opts.status == WI.OPPORTUNITY)]
        assert t.explanation.str.contains("do not assume it is feasible").all()
        d = opts[(opts.option == "DONATION_OR_DISPOSAL") & (opts.status == WI.INVESTIGATE)]
        assert d.explanation.str.contains("never assumed to be possible").all() and (d.evidence_level == 0).all()
    small = WI.assess_donation(_row(at_risk_units=40.0), 100)
    assert small["status"] == WI.NA


# ----------------------------------------------------------------- 4 markdown reuse is faithful (no re-ranking)
def test_markdown_option_matches_saved_eligibility_phase1_and_a1(sc1):
    lines, opts = sc1
    mk = opts[opts.option == "MARKDOWN"].merge(D.markdown_review("SC1", "P2")[KEY + ["eligibility"]], on=KEY)
    p1 = D.discount_recommendations("SC1", "P2")[0][KEY + ["recommendation_status", "recommended_markdown_pct"]]
    mk = mk.merge(p1, on=KEY)
    cand = mk[mk.status == WI.CANDIDATE]
    assert (cand.recommendation_status == R.RECOMMEND).all() and len(cand) == int((mk.recommendation_status == R.RECOMMEND).sum())
    assert set(mk.loc[mk.eligibility == "BLOCKED", "status"]) == {WI.BLOCKED}
    for r in cand.itertuples():
        assert f"ranks a {int(r.recommended_markdown_pct)}% markdown first" in r.evidence_for
    a1 = D.dp_decisions("SC1", "R2_CENTRAL", "A1")
    sel = a1[a1.outcome == "MARKDOWN_SELECTED"][KEY + ["markdown_pct"]].merge(cand[KEY + ["evidence_for"]], on=KEY)
    for r in sel.itertuples():
        assert f"a {int(r.markdown_pct)}% markdown was simulated" in r.evidence_for


# ----------------------------------------------------------------------------------- 5 transfer pairing rule
def test_transfer_pairs_follow_the_rule_and_match_the_design_counts(sc1, sc3):
    for sc, (lines, opts), n in (("SC1", sc1, 25), ("SC3", sc3, 9)):
        t = opts[(opts.option == "TRANSFER") & (opts.status == WI.OPPORTUNITY)].merge(lines[KEY + ["Region"]], on=KEY)
        assert len(t) == n
        dec = D.decisions(sc, "P2")[KEY + ["std_pre_delivery_shortage"]]
        stores = pd.read_csv(D.STORES_FILE)[["Store_ID", "Region"]]
        for r in t.itertuples():
            receivers = [int(s) for s in re.findall(r"store (\d+)", r.evidence_for)]
            assert receivers and r.Store_ID not in receivers
            for s in receivers:
                row = dec[(dec.Store_ID == s) & (dec.Product_ID == r.Product_ID) & (dec.origin_week == r.origin_week)].iloc[0]
                assert bool(row.std_pre_delivery_shortage)
                assert stores.set_index("Store_ID").loc[s, "Region"] == r.Region


# ------------------------------------------------------------- current stock vs future order are kept apart
def test_future_order_is_separate_and_never_saves_current_stock(sc3):
    lines, opts = sc3
    rep = opts[opts.option == "REPLENISHMENT_REVIEW"]
    assert set(rep.decision_group) == {"FUTURE_ORDER"} and rep.investigation_rank.isna().all()
    assert rep[rep.status == WI.CANDIDATE].explanation.str.contains("would not save the stock already in the store").all()
    assert "REPLENISHMENT_REVIEW" not in set(lines.current_stock_first.dropna())
    rev = lines[lines.future_order_outcome == "REVIEW_NEXT_ORDER"]
    assert len(rev) == 556 and rev.manager_summary.str.contains("cannot save the stock already in store").all()
    blocked = WI.assess_replenishment(_row(planned_buffer_units=300.0, shortage_before_delivery=True))
    assert blocked["status"] == WI.BLOCKED  # never trim an order when the line may run short


# ----------------------------------------------------------------------- prioritisation by evidence quality
def test_investigation_order_uses_evidence_level_not_value(sc1):
    lines, opts = sc1
    cur = opts[(opts.decision_group == "CURRENT_STOCK") & opts.investigation_rank.notna()]
    for _, g in cur.groupby(KEY):
        g = g.sort_values("investigation_rank")
        assert list(g.evidence_level) == sorted(g.evidence_level, reverse=True)
    first = lines[lines.current_stock_first.notna()]
    mk = opts[(opts.option == "MARKDOWN") & (opts.status == WI.CANDIDATE)][KEY]
    assert set(map(tuple, first[first.current_stock_first == "MARKDOWN"][KEY].to_numpy())) == set(map(tuple, mk.to_numpy()))


# -------------------------------------------------------------------------------------------- 6 no look-ahead
def test_no_look_ahead_later_weeks_cannot_change_earlier_assessments():
    params = D.intervention_params()
    inputs = [D.waste_risk("SC3", "P2"), D.decisions("SC3", "P2"), D.markdown_review("SC3", "P2"),
              D.discount_recommendations("SC3", "P2")[0], D.dp_decisions("SC3", "R2_CENTRAL", "A1"), D.reference_prices()]
    stores = pd.read_csv(D.STORES_FILE)
    full, fo = WI.assess(*inputs, stores, params)
    cut = [x[x["origin_week"] <= 40] for x in inputs]
    early, eo = WI.assess(*cut, stores, params)
    pd.testing.assert_frame_equal(full[full.origin_week <= 40].reset_index(drop=True), early.reset_index(drop=True))
    pd.testing.assert_frame_equal(fo[fo.origin_week <= 40].reset_index(drop=True), eo.reset_index(drop=True))


# ---------------------------------------------------------------------------------- 7 values and wording
def test_values_are_illustrative_and_never_claimed_as_savings(sc1):
    lines, opts = sc1
    at = lines[lines.line_outcome == "INVESTIGATIONS_SUGGESTED"]
    gm = D.intervention_params()["gross_margin_pct"]
    assert at.estimated_retail_value.to_numpy() == pytest.approx((at.at_risk_units * at.reference_price).to_numpy())
    cost = at.at_risk_units * at.reference_price * (1 - at.product_category.map(gm) / 100)
    assert at.assumed_cost_value.to_numpy() == pytest.approx(cost.to_numpy())
    assert at.manager_summary.str.contains("not a saving").all()
    text = " ".join(at.manager_summary) + " " + " ".join(opts.explanation) + " " + " ".join(opts.evidence_for)
    for claim in (r"\bwill save\b", r"\bsaves\b", r"reduces? waste", r"profit (gain|increase|improvement)", r"\boptimal\b",
                  r"\bguarantee", r"has been (transferred|donated|ordered|discounted)"):
        assert not re.search(claim, text, re.IGNORECASE), claim
    assert at.manager_summary.str.contains("evidence quality, not financial benefit").all()


# ------------------------------------------------------------------------------- 8 determinism and integrity
def test_deterministic_and_protected_outputs_unchanged(sc1, protected_registry):
    again = D.waste_interventions("SC1")
    pd.testing.assert_frame_equal(again[0], sc1[0])
    pd.testing.assert_frame_equal(again[1], sc1[1])
    bad = [r for r, d in protected_registry.items() if config.sha256_file(config.PROJECT_ROOT / r) != d]
    assert not bad
