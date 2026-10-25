"""Stage 5B-3b: hypothetical inventory recommendations and review queue v1.2.

Worked examples A-C reuse the frozen 5B-3a inputs (SYNTHETIC replay states, protected contract quantiles)."""
from __future__ import annotations

import dataclasses
import inspect
import itertools

import numpy as np
import pytest

from conftest import fake_contract_predictions, forecast_raw
from dpe.decision import assumptions as A
from dpe.decision import forecast_contract as FC
from dpe.decision import inventory as I
from dpe.decision import inventory_review as Q
from dpe.decision import recommendations as R
from dpe.decision import replay as RP
from dpe.forecast.panel import build_panel

QA = (2530.948652976413, 4023.912707273916, 5835.916169470104)
QB = (635.2352398488395, 997.2655983603486, 1476.8995617447497)
QC = (2432.21920809664, 3837.6681743260383, 5576.8117384916095)
BANNED = ("probability of stockout", "chance of stockout", "% probability", "stockout probability:",
          "observed lost sale", "will run out on", "expires on", "stockout on", "on day ", "approved by", "confirmed arrangement")
DOC = A.load()
V1, V2 = A.resolve(DOC, "SC1"), A.resolve(DOC, "SC2")


def ctx(values=V1, store=500, product=1034, cat="Dairy", origin=33, shelf=10, lead=2, q=QA, status="AVAILABLE", **kw):
    return R.context_from_values(values, store_id=store, product_id=product, product_category=cat, origin_week=origin,
                                 decision_day=RP.day_index(origin + 1, 1), shelf_life_days=shelf, lead_time_days=lead,
                                 p10=q[0], p50=q[1], p90=q[2], uncertainty_status=status,
                                 assumption_content_sha256=A.content_sha256(DOC), **kw)


def rec(c, lots=(), committed=()):
    r = R.recommend(c, R.plan_for(c, list(lots), list(committed)))
    R.assert_safe(r)
    return r


def rec_a():
    return rec(ctx(), [I.Lot(235, 227, 4214)])


def rec_b():
    return rec(ctx(store=505, product=1001, cat="Bakery", origin=44, shelf=2, lead=3, q=QB),
               committed=[I.Delivery(d, d, 204) for d in (309, 310, 311)])


def rec_c():
    return rec(ctx(V2, product=1024, origin=32, shelf=16, lead=2, q=QC), [I.Lot(239, 225, 638)])


# ------------------------------------------------------------------------------------ worked examples
def test_worked_example_a_routine_with_expiry_escalation():
    r = rec_a()
    assert r["primary_category"] == "ROUTINE_REPLENISHMENT_PROPOSAL" and r["proposed_order_units"] == 4176
    assert r["reason_codes"] == ["EXPIRY_BEFORE_COVERAGE", "TARGET_ABOVE_P90_CAPPED"]
    assert r["case_type"] == "RISK_ESCALATION" and r["material_reasons"] == ["EXPIRY_BEFORE_COVERAGE"]
    assert r["supplier_arrangement"]["status"] == "ASSUMED_STANDARD_WEEKLY_UNCONFIRMED"
    assert r["evidence"]["calculated"]["existing_stock_expected_expiry_units_projection"] == pytest.approx(1396.906)
    assert "1,396.9 units of existing stock are projected to expire" in r["explanation"]


def test_worked_example_b_routine_short_life_without_weekly_case():
    r = rec_b()
    assert r["primary_category"] == "ROUTINE_REPLENISHMENT_PROPOSAL" and r["proposed_order_units"] == 1428
    assert r["case_type"] is None and r["material_reasons"] == []
    assert {"SHORT_LIFE_ARRANGEMENT_ASSUMED", "WEEKEND_DELIVERY_ASSUMED", "LIFE_LEAD_TIME_TIGHT",
            "PRE_DELIVERY_GAP_HIGHER_DEMAND_ONLY"} == set(r["warnings"])
    sa = r["supplier_arrangement"]
    assert sa["standing_confirmation_required"] and sa["daily_drops"] and sa["weekend_drop_days"] == ["Saturday", "Sunday"]
    assert [d["proposed_units"] for d in r["deliveries"]] == [204] * 7


def test_worked_example_c_shortage_before_delivery():
    r = rec_c()
    assert r["primary_category"] == "SHORTAGE_BEFORE_PROPOSED_DELIVERY" and r["proposed_order_units"] == 5580
    assert r["case_type"] == "RISK_ESCALATION" and "PRE_DELIVERY_SHORTAGE" in r["material_reasons"]
    assert r["evidence"]["calculated"]["pre_delivery_gap_units"] == {"p10": 404.38, "p50": 1006.715, "p90": 1752.062}
    assert "about 404.4 to 1,752.1 units" in r["explanation"] and "neither is assumed or arranged" in r["explanation"]


# ------------------------------------------------------------------------------------- every category
def test_category_no_actionable_missing_bounds():
    r = rec(ctx(q=(None, None, None), status="UNAVAILABLE_INSUFFICIENT_HISTORY"), [I.Lot(240, 230, 100)])
    assert r["primary_category"] == "NO_ACTIONABLE_RECOMMENDATION_MANDATORY_REVIEW"
    assert r["proposed_order_units"] == 0 and r["deliveries"] == [] and not r["proposal_eligible"]
    assert r["case_type"] == "MANDATORY_REVIEW" and "UNCERTAINTY_UNAVAILABLE" in r["reason_codes"]


def test_category_no_actionable_unsupported_arrangement():
    r = rec(ctx(lead=7))
    assert r["primary_category"] == "NO_ACTIONABLE_RECOMMENDATION_MANDATORY_REVIEW" and r["proposed_order_units"] == 0
    assert r["case_type"] == "MANDATORY_REVIEW" and r["reason_codes"][0] == "UNSUPPORTED_DELIVERY_ARRANGEMENT"
    assert r["supplier_arrangement"]["status"] == "UNSUPPORTED"
    assert not r["supplier_arrangement"]["standing_confirmation_required"]


def _with_residual(c, lots=(), committed=(), residual=50.0):
    plan = R.plan_for(c, list(lots), list(committed))
    return dataclasses.replace(plan, residual_shortfall_units=residual)


def test_category_shortage_remaining_after_order():
    # Unreachable with the 5B-3a calculator today (it always covers the window); reserved for future constraints.
    c = ctx()
    r = R.recommend(c, _with_residual(c, [I.Lot(235, 227, 4214)]))
    assert r["primary_category"] == "SHORTAGE_REMAINING_AFTER_PROPOSED_ORDER"
    assert "SHORTAGE_REMAINING_AFTER_ORDER" in r["material_reasons"] and r["case_type"] == "RISK_ESCALATION"
    assert "50.0 units of planned demand remain uncovered" in r["explanation"]


def test_category_no_replenishment_required():
    r = rec(ctx(), [I.Lot(260, 230, 100_000)])
    assert r["primary_category"] == "NO_REPLENISHMENT_REQUIRED" and r["proposed_order_units"] == 0
    assert r["proposal_eligible"] and "No replenishment required" in r["explanation"]


def test_category_routine():
    r = rec(ctx(), [I.Lot(260, 230, 2000)])
    assert r["primary_category"] == "ROUTINE_REPLENISHMENT_PROPOSAL" and r["proposed_order_units"] > 0
    assert r["case_type"] is None and r["bulk_approval_allowed"]


# --------------------------------------------------------------------------------------- precedence
def test_precedence_safety_blocks_first():
    c = ctx(origin=50, q=(None, None, None), status="UNAVAILABLE_INSUFFICIENT_HISTORY")  # Christmas + missing bounds
    r = rec(c)
    assert r["primary_category"] == "NO_ACTIONABLE_RECOMMENDATION_MANDATORY_REVIEW" and r["proposed_order_units"] == 0
    assert r["case_type"] == "MANDATORY_ESCALATION"  # case type: Christmas outranks mandatory review
    assert r["reason_codes"][:2] == ["UNCERTAINTY_UNAVAILABLE", "CHRISTMAS_PERIOD"]


def test_precedence_residual_before_pre_delivery_shortage():
    c = ctx(V2, product=1024, origin=32, shelf=16, lead=2, q=QC)
    r = R.recommend(c, _with_residual(c, [I.Lot(239, 225, 638)]))
    assert r["primary_category"] == "SHORTAGE_REMAINING_AFTER_PROPOSED_ORDER"
    assert {"SHORTAGE_REMAINING_AFTER_ORDER", "PRE_DELIVERY_SHORTAGE"} <= set(r["reason_codes"])


def test_precedence_is_deterministic_over_all_combinations():
    base = R.plan_for(ctx(), [I.Lot(235, 227, 4214)], [])
    for sized, residual, gap, zero in itertools.product((True, False), (0.0, 9.0), (0.0, 9.0), (True, False)):
        plan = dataclasses.replace(base, status="SIZED" if sized else "NOT_SIZED_UNCERTAINTY_UNAVAILABLE",
                                   residual_shortfall_units=residual, ordered_units=0 if zero else 10,
                                   pre_delivery_gap_units={"p10": gap, "p50": gap, "p90": gap})
        c = ctx() if sized else ctx(status="UNAVAILABLE_INSUFFICIENT_HISTORY")
        got = {R.classify(c, plan)[0] for _ in range(3)}
        expected = (R.CATEGORIES[0] if not sized else R.CATEGORIES[1] if residual else R.CATEGORIES[2] if gap
                    else R.CATEGORIES[3] if zero else R.CATEGORIES[4])
        assert got == {expected}


def test_combined_risk_reasons_in_one_recommendation_and_one_case():
    c = ctx(V2, product=1024, origin=32, shelf=16, lead=2, q=QC, h1_point=QC[1], h4_point=QC[1] * 1.5,
            fill_shortfall_last_week=True, risk_flags="HOLIDAY_TARGET_WEEK")
    r = rec(c, [I.Lot(239, 225, 638)])
    assert {"PRE_DELIVERY_SHORTAGE", "FILL_RATE_SHORTFALL_LAST_WEEK", "TREND_DIVERGENCE"} <= set(r["material_reasons"])
    assert "HOLIDAY_TARGET_WEEK" in r["warnings"]
    cases = Q.weekly_cases([r, r])
    assert len(cases) == 1 and cases[0]["reason_codes"] == r["material_reasons"]
    assert r["reason_codes"] == sorted(r["reason_codes"], key=R.REASON_ORDER.__getitem__)


# ----------------------------------------------------------------------------------- supplier feasibility
def test_weekend_drop_alone_creates_a_standing_case_not_a_weekly_case():
    recs = [rec(ctx(store=505, product=1001, cat="Bakery", origin=o, shelf=2, lead=3, q=QB),
                committed=[I.Delivery(RP.day_index(o + 1, k), RP.day_index(o + 1, k), 204) for k in (1, 2, 3)])
            for o in (40, 41, 42, 43, 44)]
    assert all(r["case_type"] is None for r in recs)
    assert Q.weekly_cases(recs) == []
    standing = Q.standing_cases(recs)
    assert len(standing) == 1 and standing[0]["decision_weeks"] == [40, 41, 42, 43, 44]
    assert standing[0]["case_id"] == "CASE-S-SC1-505-1001-SUPPLIER-ARRANGEMENT" and standing[0]["daily_drops"]
    assert standing[0]["status"] == "PENDING_REVIEW" and standing[0]["approval_event_id"] is None
    assert "SHORT_LIFE_ARRANGEMENT_ASSUMED" in standing[0]["evidence_warnings"]


def test_long_life_weekend_arrival_needs_confirmation_only():
    r = rec(ctx(lead=5), [I.Lot(260, 230, 6000)])  # Monday + 5 days = Saturday
    assert r["supplier_arrangement"]["weekend_drop_days"] == ["Saturday"] and r["case_type"] is None
    assert "WEEKEND_DELIVERY_ASSUMED" in r["warnings"] and r["supplier_arrangement"]["standing_confirmation_required"]


def test_late_delivery_on_assumed_arrangement_escalates_weekly():
    r = rec(ctx(store=505, product=1001, cat="Bakery", origin=44, shelf=2, lead=3, q=QB))  # nothing before day 312
    assert r["primary_category"] == "SHORTAGE_BEFORE_PROPOSED_DELIVERY"
    assert {"PRE_DELIVERY_SHORTAGE", "ARRANGEMENT_FEASIBILITY_RISK"} <= set(r["material_reasons"])
    s = Q.standing_cases([r])
    assert s[0]["decisions_with_feasibility_risk"] == [44]
    assert Q.weekly_cases([r])[0]["standing_case_id"] == s[0]["case_id"]


def test_expiry_before_coverage_escalates_and_minor_expiry_is_a_warning():
    assert "EXPIRY_BEFORE_COVERAGE" in rec_a()["material_reasons"]  # 1,396.9 = 34.7% of p50 > 15% high band
    minor = rec(ctx(), [I.Lot(235, 227, 2 * QA[1] / 7 + 2 * QA[2] / 7 + 200)])  # about 200 units expire
    assert "EXPIRY_BEFORE_COVERAGE_MINOR" in minor["warnings"] and "EXPIRY_BEFORE_COVERAGE" not in minor["reason_codes"]


def test_post_order_gap_escalates():
    c = ctx(store=505, product=1001, cat="Bakery", origin=44, shelf=2, lead=3, q=QB)
    r = R.recommend(c, _with_residual(c, committed=[I.Delivery(d, d, 204) for d in (309, 310, 311)], residual=12.0))
    assert r["case_type"] == "RISK_ESCALATION"
    assert {"SHORTAGE_REMAINING_AFTER_ORDER", "ARRANGEMENT_FEASIBILITY_RISK"} <= set(r["material_reasons"])


def test_no_arrangement_is_ever_labelled_confirmed():
    recs = [rec_a(), rec_b(), rec_c(), rec(ctx(lead=7)), rec(ctx(lead=5), [I.Lot(260, 230, 6000)])]
    for r in recs:
        assert "CONFIRMED" not in r["supplier_arrangement"]["status"].replace("UNCONFIRMED", "")
        assert r["supplier_arrangement"]["provenance"] == "ASSUMED"
    for c in Q.standing_cases(recs):
        assert "CONFIRMED" not in c["arrangement_status"].replace("UNCONFIRMED", "")


# ----------------------------------------------------------------------------------------- queue v1.2
def test_weekly_case_deduplication_and_stable_ids():
    a, c = rec_a(), rec_c()
    cases = Q.weekly_cases([a, c, a, c, a])
    assert [x["case_id"] for x in cases] == ["CASE-W-SC1-500-1034-O33", "CASE-W-SC2-500-1024-O32"]
    assert Q.queue_summary(cases, [])["duplicate_weekly_cases"] == 0
    tampered = dict(a, proposed_order_units=1)
    with pytest.raises(ValueError):
        Q.weekly_cases([a, tampered])
    assert Q.weekly_cases([c, a]) == Q.weekly_cases([a, c])  # input order does not matter


def test_standing_case_deduplication_across_weeks_and_scenarios():
    def b(values, o):
        return rec(ctx(values, store=505, product=1001, cat="Bakery", origin=o, shelf=2, lead=3, q=QB),
                   committed=[I.Delivery(RP.day_index(o + 1, k), RP.day_index(o + 1, k), 204) for k in (1, 2, 3)])
    recs = [b(V1, 40), b(V1, 41), b(V1, 40), b(V2, 40)]
    s = Q.standing_cases(recs)
    assert [x["case_id"] for x in s] == ["CASE-S-SC1-505-1001-SUPPLIER-ARRANGEMENT", "CASE-S-SC2-505-1001-SUPPLIER-ARRANGEMENT"]
    assert s[0]["decision_weeks"] == [40, 41] and s[1]["decision_weeks"] == [40]
    assert Q.queue_summary(Q.weekly_cases(recs), s)["standing_supplier_confirmation_cases"] == 2


# ---------------------------------------------------------------------------------- approval safety
def test_christmas_is_mandatory_escalation_and_never_bulk_approvable():
    r = rec(ctx(origin=50), [I.Lot(370, 345, 500)])
    assert r["target_week"] == 51 and r["case_type"] == "MANDATORY_ESCALATION" and r["escalation_required"]
    assert not r["bulk_approval_allowed"] and r["proposed_order_units"] > 0  # still only a hypothetical proposal
    case = Q.weekly_cases([r])[0]
    assert case["case_type"] == "MANDATORY_ESCALATION" and case["bulk_approval_allowed"] is False
    with pytest.raises(AssertionError):
        R.assert_safe(dict(r, bulk_approval_allowed=True))


def test_missing_bounds_mandatory_review_and_zero_quantity():
    r = rec(ctx(status="UNAVAILABLE_INSUFFICIENT_HISTORY"), [I.Lot(240, 230, 100)])
    assert r["case_type"] == "MANDATORY_REVIEW" and r["proposed_order_units"] == 0
    with pytest.raises(AssertionError):
        R.assert_safe(dict(r, proposed_order_units=24))


def test_no_fabricated_approval_events_and_no_execution():
    recs = [rec_a(), rec_b(), rec_c(), rec(ctx(product=1098, origin=50)), rec(ctx(product=1099, lead=7))]
    for r in recs:
        assert (r["status"], r["execution_status"], r["approval_event_id"], r["actions_taken"]) == \
            ("HYPOTHETICAL_UNAPPROVED", "NOT_EXECUTED", None, [])
    weekly, standing = Q.weekly_cases(recs), Q.standing_cases(recs)
    assert all(c["status"] == "PENDING_REVIEW" and c["approval_event_id"] is None and not c["bulk_approval_allowed"]
               for c in weekly + standing)
    assert Q.queue_summary(weekly, standing)["approved_or_executed"] == 0
    for unsafe in ({"status": "APPROVED"}, {"execution_status": "EXECUTED"}, {"approval_event_id": "EV-1"},
                   {"actions_taken": ["SUPPLIER_ORDER_SENT"]}):
        with pytest.raises(AssertionError):
            R.assert_safe(dict(recs[0], **unsafe))


def test_modules_have_no_approval_execution_or_external_actions():
    for mod in (R, Q):
        names = [n.lower() for n, obj in vars(mod).items() if callable(obj) and getattr(obj, "__module__", "") == mod.__name__]
        assert not any(w in n for n in names for w in ("approve", "execute", "send", "submit", "transfer", "expedite", "price"))
        src = inspect.getsource(mod)
        assert not any(w in src for w in ("open(", "sqlite", "requests", "airtable", "to_csv", "write_text"))


# ------------------------------------------------------------------------------- explanation and provenance
def test_explanations_and_provenance():
    for r in (rec_a(), rec_b(), rec_c(), rec(ctx(lead=7)), rec(ctx(origin=50))):
        ev = r["evidence"]
        assert set(ev) == {"observed", "forecast", "assumed", "calculated", "stock_state"}
        assert ev["assumed"]["assumption_set_id"] == "AS-2026-10-22-v1" and ev["assumed"]["assumption_status"] == "DRAFT"
        assert ev["assumed"]["assumption_content_sha256"] == A.content_sha256(DOC)
        assert ev["stock_state"]["provenance"] == "SIMULATED_REPLAY_STATE"
        for key in ("store_id", "product_id", "decision_date", "primary_category", "proposed_order_units", "reason_codes",
                    "supplier_arrangement", "status", "explanation"):
            assert key in r
        text = r["explanation"].lower()
        assert text.startswith("hypothetical, unapproved proposal") and "not executed" in text
        assert not any(b in text for b in BANNED)
        assert "lost sale" not in text and "unmet" not in text


# ---------------------------------------------------------------------------------- leakage, determinism
def test_determinism():
    assert rec_a() == rec_a() and rec_c() == rec_c()
    recs = [rec_a(), rec_b(), rec_c()]
    assert Q.weekly_cases(recs) == Q.weekly_cases(list(reversed(recs)))
    assert Q.standing_cases(recs) == Q.standing_cases(list(reversed(recs)))


@pytest.fixture(scope="module")
def captured():
    panel = build_panel(forecast_raw())
    contract = FC.build_contract(fake_contract_predictions(panel), panel, "TEST")["contract"]
    v = {**V1, "opening_cover_multiplier": 0.05}
    h4 = contract[contract["horizon_weeks"] == 4].set_index(["store_id", "product_id", "origin_week"])["predicted_units"]
    orig = RP._decide

    def run(p):
        seen = {}

        def spy(k, T, D0, a, h1, hh4, st, values, schedule):
            row = h1.loc[(*k, T)] if (*k, T) in h1.index else None
            if row is not None:
                c = R.context_from_values(
                    values, store_id=int(k[0]), product_id=int(k[1]), product_category=a["Product_Category"],
                    origin_week=int(T), decision_day=D0, shelf_life_days=int(a["Shelf_Life_Days"]),
                    lead_time_days=int(a["Lead_Time_Days"]), p10=row["lower_p10_units"], p50=row["median_p50_units"],
                    p90=row["upper_p90_units"], uncertainty_status=row["uncertainty_status"], risk_flags=row["risk_flags"],
                    h1_point=row["predicted_units"], h4_point=h4.get((*k, T)),
                    fill_shortfall_last_week=any(dl["delivered_units"] < dl["ordered_units"]
                                                 for d in range(D0 - 7, D0) for dl in st.received.get(d, [])))
                lots = [I.Lot(e, ar, q, i) for e, ar, q, i in st.lots]
                committed = [I.Delivery(d, dl["expiry_day"], dl["ordered_units"], dl["delivery_id"])
                             for d, dls in sorted(st.scheduled.items()) for dl in dls]
                seen[(k, T)] = R.recommend(c, R.plan_for(c, lots, committed))
            return orig(k, T, D0, a, h1, hh4, st, values, schedule)

        RP._decide = spy
        try:
            RP.simulate(contract, p, v)
        finally:
            RP._decide = orig
        return seen

    cutoff = 21
    p2 = panel.copy()
    later = p2["week_index"] > cutoff
    p2.loc[later, "Units_Sold"] = np.random.default_rng(11).permutation(p2.loc[later, "Units_Sold"].to_numpy())
    return run(panel), run(p2), cutoff


def test_scrambled_future_sales_leave_earlier_recommendations_unchanged(captured):
    base, scrambled, cutoff = captured
    early = [k for k in base if k[1] <= cutoff]
    assert early and all(base[k] == scrambled[k] for k in early)
    later = [k for k in base if k[1] > cutoff + 1]
    assert any(base[k] != scrambled[k] for k in later)  # the test can see a difference


def test_simulator_states_give_safe_complete_records(captured):
    base, _, _ = captured
    recs = list(base.values())
    for r in recs:
        R.assert_safe(r)
        assert r["primary_category"] in R.CATEGORIES and all(code in R.REASONS for code in r["reason_codes"])
    weekly, standing = Q.weekly_cases(recs), Q.standing_cases(recs)
    s = Q.queue_summary(weekly, standing)
    assert s["duplicate_weekly_cases"] == 0 and s["approved_or_executed"] == 0
    short_life = {(r["store_id"], r["product_id"]) for r in recs if r["supplier_arrangement"]["arrangement"] == "SHORT_LIFE_RECURRING_DROPS"}
    assert len(standing) == len(short_life) > 0
    assert len({c["case_id"] for c in weekly}) == len(weekly)
