"""Replay simulator correction checkpoint (v1.1, 23 Oct 2026): lead-time warning, pre/post-order coverage,
Christmas and approval safety. Uses the synthetic fixtures; the Christmas test uses the protected real contract."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from conftest import fake_contract_predictions, forecast_raw
from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import forecast_contract as FC
from dpe.decision import replay as RP
from dpe.decision import review_queue as RQ
from dpe.forecast.panel import build_panel

KEY = ["store_id", "product_id", "origin_week"]


@pytest.fixture(scope="module")
def panel():
    return build_panel(forecast_raw())


@pytest.fixture(scope="module")
def contract(panel):
    return FC.build_contract(fake_contract_predictions(panel), panel, "TEST")["contract"]


@pytest.fixture(scope="module")
def values():
    return A.resolve(A.load(), "SC1")


@pytest.fixture(scope="module")
def lean(contract, panel, values):
    """SC1 with almost no opening stock: shortage pressure exists before any new order can arrive."""
    return RP.simulate(contract, panel, {**values, "opening_cover_multiplier": 0.05})


def _point(contract):
    """A decision point with bounds available at both horizons, outside Christmas and holidays."""
    g = contract.groupby(KEY).agg(ok=("uncertainty_status", lambda s: (s == "AVAILABLE").all()),
                                  hol=("risk_flags", lambda s: s.str.contains("HOLIDAY_TARGET_WEEK").any()),
                                  xmas=("target_week", lambda s: s.isin(RP.CHRISTMAS_WEEKS).any()))
    g = g[g["ok"] & ~g["hol"] & ~g["xmas"]]
    return g.index[0]


def _case(contract, values, flags, cfg=None):
    s, p, o = _point(contract)
    dec = pd.DataFrame([{"Store_ID": s, "Product_ID": p, "origin_week": o, "flags": flags}])
    one = contract[(contract["store_id"] == s) & (contract["product_id"] == p) & (contract["origin_week"] == o)]
    return RQ.build_cases(one, dec, {**values, **(cfg or {})}).iloc[0]


# 1. lead-time warning alone ------------------------------------------------------------------------------
def test_lead_time_warning_alone_does_not_escalate(contract, values):
    assert values["life_lead_time_tight_is_material_trigger"] is False
    c = _case(contract, values, "LIFE_LEAD_TIME_TIGHT")
    assert c["case_type"] is None and c["approval_status"] is None
    assert c["warnings"] == "LIFE_LEAD_TIME_TIGHT" and c["material_trigger_count"] == 0


def test_lead_time_warning_alone_in_a_full_run_creates_no_case(contract, panel, values):
    v = {**values, "lead_time_adjustment_days": 1}  # makes the synthetic short-life series lead-time tight
    res = RP.simulate(contract, panel, v)
    assert res["attributes"]["life_lead_time_tight"].any()
    cases = RQ.build_cases(contract, res["decisions"], v)
    only = cases[(cases["warnings"].str.contains("LIFE_LEAD_TIME_TIGHT")) & (cases["material_trigger_count"] == 0)
                 & ~cases["reasons"].str.contains("CHRISTMAS|UNCERTAINTY_UNAVAILABLE|UNSUPPORTED")]
    assert len(only) > 0 and only["case_type"].isna().all()
    assert RQ.case_summary(cases)["lead_time_warning_only_no_case"] == len(only)


# 2. lead-time warning combined with a material risk --------------------------------------------------------
@pytest.mark.parametrize("other,expected", [
    ("PRE_ORDER_SHORTAGE", "RISK_ESCALATION"),
    ("WASTE_HIGH_EXISTING_STOCK", "RISK_ESCALATION"),
    ("UNSUPPORTED_DELIVERY_ARRANGEMENT", "MANDATORY_REVIEW"),
])
def test_lead_time_warning_with_material_risk_escalates(contract, values, other, expected):
    c = _case(contract, values, f"LIFE_LEAD_TIME_TIGHT|{other}")
    assert c["case_type"] == expected and c["approval_status"] == "PENDING_REVIEW"
    reasons = c["reasons"].split("|")
    assert other in reasons and "LIFE_LEAD_TIME_TIGHT_WARNING" in reasons  # warning preserved as evidence
    assert "LIFE_LEAD_TIME_TIGHT" in c["warnings"]


def test_legacy_rule_is_available_only_as_an_explicit_switch(contract, values):
    c = _case(contract, values, "LIFE_LEAD_TIME_TIGHT", {"life_lead_time_tight_is_material_trigger": True})
    assert c["case_type"] == "RISK_ESCALATION" and c["warnings"] == ""


# 3. shortage detected before ordering ----------------------------------------------------------------------
def test_pre_order_shortage_unit():
    q = (35, 70, 105)  # p10, p50, p90 weekly: 5, 10, 15 units per day
    # No stock, nothing committed, the new order arrives on day 4: days 1-3 cannot be covered at any rate.
    assert RP.coverage_position([], {}, 1, 4, 1, *q) == "BELOW_P10_RATE"
    assert RP.coverage_position([[10, 1, 45, "x"]], {}, 1, 4, 1, *q) == "COVERS_P90_RATE"
    assert RP.coverage_position([[10, 1, 30, "x"]], {}, 1, 4, 1, *q) == "COVERS_P50_RATE"
    assert RP.coverage_position([[10, 1, 15, "x"]], {}, 1, 4, 1, *q) == "COVERS_P10_RATE_ONLY"
    # A committed delivery on day 2 counts; a large order arriving on day 4 does not help days 1-3.
    assert RP.coverage_position([[10, 1, 15, "x"]], {2: [(10, 30)]}, 1, 4, 1, *q) == "COVERS_P90_RATE"
    assert RP.coverage_position([[10, 1, 5, "x"]], {4: [(10, 500)]}, 1, 4, 1, *q) == "BELOW_P10_RATE"
    # Stock expiring on day 1 is no use on days 2-3.
    assert RP.coverage_position([[1, 1, 500, "x"]], {}, 1, 4, 1, *q) == "BELOW_P10_RATE"


def test_pre_order_shortage_is_not_hidden_by_the_replenishment_order(lean):
    d = lean["decisions"]
    first = d[(d["origin_week"] == lean["origins"][0]) & (d["ordered_units"] > 0)]
    hit = first[first["flags"].str.contains("PRE_ORDER_SHORTAGE")]
    assert len(hit) > 0 and hit["pre_order_coverage"].isin(RP.SHORTAGE_POSITIONS).all()
    # The order covers its own window, yet the pre-order shortage is still reported.
    addressed = hit[hit["order_addresses_window"] == True]  # noqa: E712
    assert len(addressed) > 0 and addressed["flags"].str.contains("PRE_ORDER_SHORTAGE").all()
    # Evidence (not calibration): flagged series do show simulated unmet units before the new order arrives.
    daily = lean["daily"]
    unmet = []
    for r in hit.itertuples():
        days = daily[(daily["Store_ID"] == r.Store_ID) & (daily["Product_ID"] == r.Product_ID)
                     & (daily["day"] >= r.decision_day) & (daily["day"] < r.arrival_day)]
        unmet.append(days["sim_unmet_units_illustrative"].sum())
    assert np.mean(np.array(unmet) > 0) > 0.5


# 4. post-order coverage reflects delivery timing -----------------------------------------------------------
def test_post_order_coverage_reflects_arrival_day():
    q = (35, 70, 105)
    # Window days 4-10; 100 units arriving on day 4 cover 10/day (70) but not 15/day (105).
    assert RP.coverage_position([], {4: [(20, 100)]}, 1, 11, 4, *q) == "COVERS_P50_RATE"
    # The same units arriving on day 7 leave days 4-6 uncovered.
    assert RP.coverage_position([], {7: [(20, 100)]}, 1, 11, 4, *q) == "BELOW_P10_RATE"
    # Drops on their own days, each lasting until its expiry.
    assert RP.coverage_position([], {4: [(6, 30)], 7: [(9, 30)], 10: [(12, 10)]}, 1, 11, 4, *q) == "COVERS_P50_RATE"
    # A drop that expires before the window ends cannot cover the last days.
    assert RP.coverage_position([], {4: [(6, 300)]}, 1, 11, 4, *q) == "BELOW_P10_RATE"


def test_post_order_coverage_in_the_simulator_uses_scheduled_arrivals(lean):
    d, dl = lean["decisions"], lean["deliveries"]
    row = d[(d["ordered_units"] > 0) & (d["delivery_arrangement"] == "SHORT_LIFE_RECURRING_DROPS")].iloc[0]
    mine = dl[dl["order_id"] == row["order_id"]]
    assert mine["arrival_day"].min() == row["arrival_day"] == row["decision_day"] + row["effective_lead_time_days"]
    assert len(mine) == row["n_deliveries"] > 1
    assert row["pre_arrival_days"] == row["effective_lead_time_days"]
    assert row["post_order_coverage"] in RP.COVERAGE_POSITIONS and row["pre_order_coverage"] in RP.COVERAGE_POSITIONS
    assert (mine["authorisation"] == RP.DELIVERY_AUTHORISATION).all()


# 5. Christmas actions remain unapproved -------------------------------------------------------------------
def test_christmas_actions_remain_unapproved(values):
    from dpe.forecast.panel import load_verified_panel

    real = pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")
    panel, _ = load_verified_panel()
    series = [(505, 1001), (505, 1025)]
    r = RP.simulate(real, panel, values, series=series)
    d = r["decisions"]
    xmas = d[d["flags"].str.contains("CHRISTMAS_PERIOD")]
    assert len(xmas) > 0 and xmas["target_week"].isin(RP.CHRISTMAS_WEEKS).all()
    assert xmas["escalation_required"].all() and xmas["approval_event_id"].isna().all()
    assert set(xmas["action_status"]) <= {"HYPOTHETICAL_UNAPPROVED", "REVIEW_REQUIRED_NO_ACTION"}
    assert set(d["action_status"]) <= {"HYPOTHETICAL_UNAPPROVED", "REVIEW_REQUIRED_NO_ACTION", "NO_ACTION_PROPOSED"}
    assert d["approval_event_id"].isna().all()
    assert (r["deliveries"]["authorisation"] == RP.DELIVERY_AUTHORISATION).all()
    c = real[real.set_index(["store_id", "product_id"]).index.isin(series)]
    cases = RQ.build_cases(c, d, values)
    xc = cases[cases["reasons"].str.contains("CHRISTMAS_PERIOD")]
    assert len(xc) > 0 and (xc["case_type"] == "MANDATORY_ESCALATION").all()
    assert (xc["approval_status"] == "PENDING_REVIEW").all() and xc["approval_event_id"].isna().all()
    assert RQ.case_summary(cases)["approved_cases"] == 0


# 6. conservation remains intact ---------------------------------------------------------------------------
def test_daily_stock_conservation_intact_after_correction(lean):
    c = RP.check_conservation(lean["daily"], lean["weekly"])
    assert all(c[k] for k in ("daily_balanced", "weekly_balanced", "closing_equals_next_opening",
                              "no_negative_values", "unmet_equals_demand_minus_sold"))
    assert (lean["daily"]["simulator_version"] == "1.1").all()


# 7 / 8. no future-data leakage; scrambled future sales leave earlier decisions unchanged -----------------------
@pytest.mark.parametrize("cutoff", [16, 21, 25])
def test_scrambled_future_sales_leave_earlier_decisions_unchanged(contract, panel, values, lean, cutoff):
    rng = np.random.default_rng(100 + cutoff)
    p2 = panel.copy()
    later = p2["week_index"] > cutoff
    p2.loc[later, "Units_Sold"] = rng.permutation(p2.loc[later, "Units_Sold"].to_numpy())
    got = RP.simulate(contract, p2, {**values, "opening_cover_multiplier": 0.05})
    early = lambda df: df[df["origin_week"] <= cutoff].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(early(got["decisions"]), early(lean["decisions"]))
    assert early(lean["decisions"])["flags"].str.contains("PRE_ORDER_SHORTAGE").any()
    assert not got["daily"].equals(lean["daily"])  # later weeks did change: the test can see a difference


def test_coverage_does_not_read_actual_deliveries(contract, panel, values):
    """Supplier shortfalls (fill rate) are unknown at decision time: the first decision must not change."""
    v = {**values, "opening_cover_multiplier": 0.05}
    base = RP.simulate(contract, panel, v)
    low = RP.simulate(contract, panel, {**v, "delivery_fill_rate_pct": 60})
    o = base["origins"][0]
    cols = ["pre_order_coverage", "post_order_coverage", "ordered_units", "flags"]
    f = lambda r: r["decisions"].loc[r["decisions"]["origin_week"] == o, cols].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(f(base), f(low))
    assert all(week == decided + 1 for week, decided in base["demand_log"])
