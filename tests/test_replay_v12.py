"""Stage 5B-3c: replay simulator v1.2 with policies P0, P1 and P2.

P1 regression runs against the protected v1.1 runs (real data). The other tests use the synthetic fixtures, except the
Christmas test, which needs the real contract's week 47-51 origins. No comparison run is created."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import pytest

from conftest import fake_contract_predictions, forecast_raw
from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import forecast_contract as FC
from dpe.decision import inventory as INV
from dpe.decision import recommendations as REC
from dpe.decision import replay as RP
from dpe.decision import replay_v12 as V
from dpe.forecast.panel import build_panel

DOC = A.load()
SCENARIOS = ("SC1", "SC2", "SC3")
ALLOWED_STATUS = {"HYPOTHETICAL_UNAPPROVED", "REVIEW_REQUIRED_NO_ACTION"}


@pytest.fixture(scope="module")
def panel():
    return build_panel(forecast_raw())


@pytest.fixture(scope="module")
def contract(panel):
    return FC.build_contract(fake_contract_predictions(panel), panel, "TEST")["contract"]


@pytest.fixture(scope="module")
def runs(contract, panel):
    return {(p, sc): V.simulate(contract, panel, A.resolve(DOC, sc), p) for p in V.POLICIES for sc in SCENARIOS}


def _rt(df):
    return pd.read_csv(io.StringIO(df.to_csv(index=False)))


# ------------------------------------------------------------------------------ P1 regression (real data)
@pytest.fixture(scope="module")
def real():
    from dpe.forecast.panel import load_verified_panel

    p, _ = load_verified_panel()
    return pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv"), p


@pytest.mark.parametrize("sc", SCENARIOS)
def test_p1_reproduces_the_protected_v11_full_replay_exactly(real, sc):
    contract, panel = real
    v = A.resolve(DOC, sc)
    r = V.simulate(contract, panel, v, "P1")
    prot = config.REPLAY_SIMULATION_V11_RUN_DIR / sc
    for name in ("decisions", "deliveries", "weekly", "daily"):
        old = pd.read_csv(prot / f"{name}.csv")
        cols = [c for c in old.columns if c != "simulator_version"]
        pd.testing.assert_frame_equal(_rt(r[name])[cols], old[cols], check_exact=True, obj=f"{sc}/{name}")
    cases = V.review(r, contract, v, V.unit_share(panel))["cases"]
    pd.testing.assert_frame_equal(_rt(cases), pd.read_csv(prot / "review_cases.csv"), check_exact=True)


def test_p1_reproduces_the_protected_v11_worked_example_exactly(real):
    contract, panel = real
    series = [(505, 1001), (505, 1025)]
    prot = config.REPLAY_WORKED_EXAMPLE_V11_RUN_DIR
    for sc in SCENARIOS:
        v = A.resolve(DOC, sc)
        r = V.simulate(contract, panel, v, "P1", series=series, trace=True)
        for name in ("decisions", "deliveries", "weekly", "daily", "sales_trace"):
            old = pd.read_csv(prot / sc / f"{name}.csv")
            cols = [c for c in old.columns if c != "simulator_version"]
            pd.testing.assert_frame_equal(_rt(r[name])[cols], old[cols], check_exact=True)
        cases = V.review(r, contract, v, V.unit_share(panel), series=series)["cases"]
        pd.testing.assert_frame_equal(_rt(cases), pd.read_csv(prot / sc / "review_cases.csv"), check_exact=True)


def test_simulator_v11_code_is_unchanged():
    import hashlib
    import json

    m = json.loads((config.REPLAY_SIMULATION_V11_RUN_DIR / "manifest.json").read_text(encoding="utf-8"))
    code = config.PROJECT_ROOT / "src" / "dpe" / "decision"
    for name in ("replay.py", "review_queue.py", "assumptions.py"):
        assert hashlib.sha256((code / name).read_bytes()).hexdigest() == m["code_sha256"][name], name


# ------------------------------------------------------------------------------ policy selection and state
def test_policy_selection(runs):
    with pytest.raises(ValueError):
        V.get_policy("P9")
    basis = {"P0": {"P0_HISTORICAL_4_WEEK_AVERAGE_EXPIRY_BLIND"}, "P1": {"PLANNING_WEIGHT_P50_P90_HEURISTIC"},
             "P2": {"P2_TIME_PHASED_EXPIRY_AWARE"}}
    for (p, sc), r in runs.items():
        d = r["decisions"]
        assert set(d["policy_id"]) == {p} and set(d["simulator_version"]) == {"1.2"}
        assert set(d.loc[d["ordered_units"] > 0, "order_basis"]) <= basis[p]
        assert (r["deliveries"]["policy_id"] == p).all()
    assert not runs[("P0", "SC1")]["decisions"]["ordered_units"].equals(runs[("P2", "SC1")]["decisions"]["ordered_units"])


def test_states_are_independent_between_policies_and_scenarios(contract, panel, runs):
    fresh = V.simulate(contract, panel, A.resolve(DOC, "SC2"), "P2")
    for name in ("decisions", "deliveries", "daily", "weekly"):
        pd.testing.assert_frame_equal(fresh[name], runs[("P2", "SC2")][name])
    assert fresh["recommendations"] == runs[("P2", "SC2")]["recommendations"]
    for (p, sc), r in runs.items():
        assert r["deliveries"]["delivery_id"].str.startswith(f"{sc}-").all()
        assert set(r["decisions"]["scenario_id"]) == {sc}


def test_same_window_initial_state_and_demand_for_every_policy(runs):
    for sc in SCENARIOS:
        base = runs[("P1", sc)]
        for p in ("P0", "P2"):
            r = runs[(p, sc)]
            assert r["origins"] == base["origins"]
            pd.testing.assert_series_equal(r["daily"]["sim_demand_units_illustrative"], base["daily"]["sim_demand_units_illustrative"])
            init = lambda x: x["deliveries"][x["deliveries"]["kind"] == "INITIAL_SCHEDULE"].drop(columns="policy_id")  # noqa: E731
            pd.testing.assert_frame_equal(init(r).reset_index(drop=True), init(base).reset_index(drop=True))
            first = lambda x: x["daily"].groupby(["Store_ID", "Product_ID"])["sim_opening_units"].first()  # noqa: E731
            pd.testing.assert_series_equal(first(r), first(base))


# --------------------------------------------------------------------------------------- P2 behaviour
class _Recorder(V.P2Policy):
    seen: list = []

    def decide(self, k, T, D0, a, h1, h4, st, values, schedule, ctx):
        lots, committed = V._state_inputs(st)
        rec = super().decide(k, T, D0, a, h1, h4, st, values, schedule, ctx)
        self.seen.append((rec, lots, committed, ctx["recommendations"][-1]))
        return rec


def test_p2_orders_equal_the_expiry_aware_calculator_on_its_own_state(contract, panel, monkeypatch):
    _Recorder.seen = []
    monkeypatch.setitem(V.POLICY_CLASSES, "P2", _Recorder)
    v = A.resolve(DOC, "SC3")  # excess stock: expiry inside the window matters
    r = V.simulate(contract, panel, v, "P2")
    assert len(_Recorder.seen) == len(r["decisions"])
    expiring = 0
    for rec, lots, committed, recommendation in _Recorder.seen:
        if not recommendation["proposal_eligible"]:
            assert rec["ordered_units"] == 0
            continue
        a = r["attributes"].set_index(["Store_ID", "Product_ID"]).loc[(rec["Store_ID"], rec["Product_ID"])]
        row = contract[(contract.horizon_weeks == 1) & (contract.store_id == rec["Store_ID"])
                       & (contract.product_id == rec["Product_ID"]) & (contract.origin_week == rec["origin_week"])].iloc[0]
        plan = INV.plan_order(lots, committed, rec["decision_day"], int(a["effective_lead_time_days"]),
                              int(a["remaining_life_days"]), row.lower_p10_units, row.median_p50_units, row.upper_p90_units,
                              v["service_target_pct"][a["Product_Category"]], v["case_size_units"][a["Product_Category"]],
                              v["moq_cases_per_delivery"])
        assert rec["ordered_units"] == plan.ordered_units
        expiring += (plan.existing_stock_expected_expiry_units or 0) > 0
    assert expiring > 0
    sized = r["decisions"][r["decisions"]["order_basis"] == "P2_TIME_PHASED_EXPIRY_AWARE"]
    assert not sized["std_post_order_shortfall"].astype(bool).any()  # expiry-aware sizing always covers the window


def test_p2_recommendation_precedence_in_the_simulator(runs):
    for sc in SCENARIOS:
        for r in runs[("P2", sc)]["recommendations"]:
            REC.assert_safe(r)
            codes = set(r["reason_codes"])
            if r["primary_category"] == REC.CATEGORIES[2]:
                assert "PRE_DELIVERY_SHORTAGE" in codes and "SHORTAGE_REMAINING_AFTER_ORDER" not in codes
            if "UNCERTAINTY_UNAVAILABLE" in codes or "UNSUPPORTED_DELIVERY_ARRANGEMENT" in codes:
                assert r["primary_category"] == REC.CATEGORIES[0] and r["proposed_order_units"] == 0
    cats = {r["primary_category"] for sc in SCENARIOS for r in runs[("P2", sc)]["recommendations"]}
    assert {REC.CATEGORIES[2], REC.CATEGORIES[4]} <= cats


def test_review_queue_compatibility(contract, runs):
    for sc in SCENARIOS:
        v = A.resolve(DOC, sc)
        q1, q2 = V.review(runs[("P1", sc)], contract, v), V.review(runs[("P2", sc)], contract, v)
        assert q1["queue_version"] == "1.1" and q2["queue_version"] == "1.2"
        # Mandatory classifications are contract gates: identical for both queues.
        t1, t2 = q1["summary"]["weekly_by_type"], q2["summary"]["weekly_by_type"]
        for t in ("MANDATORY_REVIEW", "MANDATORY_ESCALATION"):
            assert t1.get(t, 0) == t2.get(t, 0)
        ids = [c["case_id"] for c in q2["cases"]]
        assert len(ids) == len(set(ids)) and q2["summary"]["duplicate_weekly_cases"] == 0
        assert q2["summary"]["approved_or_executed"] == 0
        gate = [c for c in q2["cases"] if c["case_kind"] == "WEEKLY_CONTRACT_GATE"]
        assert gate and all(c["origin_week"] < runs[("P2", sc)]["origins"][0] and c["proposed_order_units"] == 0 for c in gate)


def test_standing_confirmation_cases_are_deduplicated(runs):
    for sc in SCENARIOS:
        r = runs[("P2", sc)]
        q = V.review(r, _contract_stub(r), A.resolve(DOC, sc))
        standing = q["standing"]
        short_life = r["attributes"].query("delivery_arrangement == 'SHORT_LIFE_RECURRING_DROPS'")
        assert len(standing) == len(short_life) > 0
        assert len({c["case_id"] for c in standing}) == len(standing)
        assert all(sorted(c["decision_weeks"]) == r["origins"] for c in standing)
        weekly_standing_refs = [c["standing_case_id"] for c in q["cases"] if c.get("standing_case_id")]
        assert set(weekly_standing_refs) <= {c["case_id"] for c in standing}


def _contract_stub(result):
    """Contract rows for the simulated points only (no out-of-window gate cases), for queue-only checks."""
    d = result["decisions"]
    return pd.DataFrame({"store_id": d["Store_ID"], "product_id": d["Product_ID"], "origin_week": d["origin_week"],
                         "target_week": d["target_week"], "uncertainty_status": "AVAILABLE",
                         "product_category": d["product_category"], "risk_flags": "", "horizon_weeks": 1})


def test_missing_uncertainty_blocks_every_policy(contract, panel, runs):
    c2 = contract.copy()
    T = runs[("P1", "SC1")]["origins"][3]
    hit = (c2["horizon_weeks"] == 1) & (c2["origin_week"] == T) & (c2["store_id"] == 500) & (c2["product_id"] == 1000)
    c2.loc[hit, ["lower_p10_units", "median_p50_units", "upper_p90_units"]] = np.nan
    c2.loc[hit, "uncertainty_status"] = "UNAVAILABLE_INSUFFICIENT_HISTORY"
    v = A.resolve(DOC, "SC1")
    for p in V.POLICIES:
        r = V.simulate(c2, panel, v, p, origins=runs[("P1", "SC1")]["origins"])
        row = r["decisions"].query("Store_ID == 500 and Product_ID == 1000 and origin_week == @T").iloc[0]
        assert row["ordered_units"] == 0 and row["action_status"] == "REVIEW_REQUIRED_NO_ACTION"
        cases = V.review(r, c2, v)["cases"]
        cases = cases if isinstance(cases, list) else cases.to_dict("records")
        case = [c for c in cases if (c["store_id"], c["product_id"], c["origin_week"]) == (500, 1000, T)][0]
        assert case["case_type"] == "MANDATORY_REVIEW"


def test_christmas_escalation_in_every_policy(real):
    contract, panel = real
    series = [(505, 1001), (505, 1025)]
    v = A.resolve(DOC, "SC1")
    for p in V.POLICIES:
        r = V.simulate(contract, panel, v, p, series=series)
        q = V.review(r, contract, v, series=series)
        cases = q["cases"] if isinstance(q["cases"], list) else q["cases"].to_dict("records")
        xmas = [c for c in cases if c["case_type"] == "MANDATORY_ESCALATION"]
        assert sorted({c["origin_week"] for c in xmas}) == [47, 48, 50, 51] and len(xmas) == 8
        if p == "P2":
            assert all(c["bulk_approval_allowed"] is False and c["status"] == "PENDING_REVIEW" for c in xmas)
            recs = [x for x in r["recommendations"] if x["origin_week"] in (47, 48, 50, 51)]
            assert all(x["case_type"] == "MANDATORY_ESCALATION" and x["escalation_required"] for x in recs)


# ------------------------------------------------------------------------------- integrity and timing
def test_inventory_conservation_for_every_policy_and_scenario(runs):
    for r in runs.values():
        c = RP.check_conservation(r["daily"], r["weekly"])
        assert all(c[k] for k in ("daily_balanced", "weekly_balanced", "closing_equals_next_opening",
                                  "no_negative_values", "unmet_equals_demand_minus_sold"))


def test_delivery_timing_and_rules_for_every_policy(runs):
    for (p, sc), r in runs.items():
        v = A.resolve(DOC, sc)
        dl, d = r["deliveries"], r["decisions"]
        orders = dl[dl["kind"] == "ORDER"].merge(d[["order_id", "decision_day", "effective_lead_time_days",
                                                    "remaining_life_days", "product_category"]], on="order_id")
        a = orders["decision_day"] + orders["effective_lead_time_days"]
        assert ((orders["arrival_day"] - a) % orders["remaining_life_days"].clip(upper=7) == 0).all()
        assert ((orders["arrival_day"] >= a) & (orders["arrival_day"] < a + 7)).all()
        assert (orders["expiry_day"] == orders["arrival_day"] + orders["remaining_life_days"] - 1).all()
        case = orders["product_category"].map(v["case_size_units"])
        assert ((orders["ordered_units"] % case == 0) & (orders["ordered_units"] >= case * v["moq_cases_per_delivery"])).all()
        assert (dl["authorisation"] == RP.DELIVERY_AUTHORISATION).all()


def test_every_action_is_hypothetical_unapproved_and_not_executed(runs):
    for r in runs.values():
        d = r["decisions"]
        assert set(d["action_status"]) <= ALLOWED_STATUS and d["approval_event_id"].isna().all()
        for x in r["recommendations"]:
            assert (x["status"], x["execution_status"], x["approval_event_id"], x["actions_taken"]) == \
                ("HYPOTHETICAL_UNAPPROVED", "NOT_EXECUTED", None, [])


def test_standardised_indicators_are_computed_for_every_policy(runs):
    for r in runs.values():
        s = V.standard_risk_summary(r)
        assert s["decisions_assessed"] == int(r["decisions"]["std_pre_delivery_shortage"].notna().sum()) > 0


def test_determinism(contract, panel, runs):
    again = V.simulate(contract, panel, A.resolve(DOC, "SC1"), "P0")
    for name in ("decisions", "deliveries", "daily"):
        pd.testing.assert_frame_equal(again[name], runs[("P0", "SC1")][name])


# --------------------------------------------------------------------------------------- leakage
@pytest.mark.parametrize("cutoff", [16, 22])
def test_scrambled_future_sales_leave_earlier_decisions_unchanged(contract, panel, runs, cutoff):
    p2 = panel.copy()
    later = p2["week_index"] > cutoff
    p2.loc[later, "Units_Sold"] = np.random.default_rng(cutoff).permutation(p2.loc[later, "Units_Sold"].to_numpy())
    for p in V.POLICIES:
        got = V.simulate(contract, p2, A.resolve(DOC, "SC1"), p)
        base = runs[(p, "SC1")]
        early = lambda df: df[df["origin_week"] <= cutoff].reset_index(drop=True)  # noqa: E731
        pd.testing.assert_frame_equal(early(got["decisions"]), early(base["decisions"]))
        assert [x for x in got["recommendations"] if x["origin_week"] <= cutoff] == \
            [x for x in base["recommendations"] if x["origin_week"] <= cutoff]
        assert not got["daily"].equals(base["daily"])


def test_reads_happen_only_after_or_at_the_decision(runs):
    for (p, sc), r in runs.items():
        assert all(week == decided + 1 for week, decided in r["demand_log"])
        assert all(week <= origin for week, origin in r["sales_reads"])
        if p == "P0":
            assert r["sales_reads"]
    guard = V._AsOfSales({(1, 1, 5): 10}, None)
    guard.decided_origin = 4
    with pytest.raises(RP.ChronologyError):
        guard[(1, 1, 5)]


def test_realised_receipts_never_enter_planning(contract, panel):
    """Changing only the realised fill rate must leave the first decision of every policy unchanged."""
    v = A.resolve(DOC, "SC1")
    for p in V.POLICIES:
        base = V.simulate(contract, panel, v, p)
        low = V.simulate(contract, panel, {**v, "delivery_fill_rate_pct": 60, "over_delivery_pct_short_life": 20}, p)
        o = base["origins"][0]
        f = lambda r: r["decisions"][r["decisions"]["origin_week"] == o].reset_index(drop=True)  # noqa: E731
        pd.testing.assert_frame_equal(f(base), f(low))
        assert not base["daily"].equals(low["daily"])
