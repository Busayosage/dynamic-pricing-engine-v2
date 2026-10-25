"""Stage 5B-3a: time-phased, expiry-aware inventory calculator (src/dpe/decision/inventory.py).

Worked examples A-C are the approved design examples (docs/STEP_5B3_INVENTORY_ENGINE_DESIGN.md section 8). Their
inputs were captured from the accepted v1.1 replay and are frozen here by hand; quantiles are the protected forecast
contract values. All units are SYNTHETIC."""
from __future__ import annotations

import copy
import inspect
import itertools

import numpy as np
import pytest

from conftest import fake_contract_predictions, forecast_raw
from dpe.decision import assumptions as A
from dpe.decision import forecast_contract as FC
from dpe.decision import inventory as I
from dpe.decision import replay as RP
from dpe.forecast.panel import build_panel

# Example inputs (store, product, origin): A = SC1 500/1034/33 Dairy, B = SC1 505/1001/44 Bakery, C = SC2 500/1024/32 Dairy
QA = (2530.948652976413, 4023.912707273916, 5835.916169470104)
QB = (635.2352398488395, 997.2655983603486, 1476.8995617447497)
QC = (2432.21920809664, 3837.6681743260383, 5576.8117384916095)


def example_a():
    return I.plan_order([I.Lot(235, 227, 4214)], [], 232, 2, 9, *QA, 92, 12, 2)


def example_b():
    committed = [I.Delivery(d, d, 204) for d in (309, 310, 311)]  # last week's daily drops, R = 1
    return I.plan_order([], committed, 309, 3, 1, *QB, 85, 12, 2)


def example_c():
    return I.plan_order([I.Lot(239, 225, 638)], [], 225, 3, 15, *QC, 92, 12, 2)


# ------------------------------------------------------------------------------------------- worked examples
def test_example_a_dairy_stock_expiring_inside_the_window():
    p = example_a()
    assert p.status == "SIZED" and p.arrangement == "LONG_LIFE_WEEKLY" and p.arrival_day == 234
    assert p.ordered_units == 4176 and len(p.drops) == 1
    d = p.drops[0]
    assert d.net_need_units == pytest.approx(5 * QA[2] / 7)  # Friday-Tuesday only: the batch expires on Thursday
    assert d.rounding_excess_units == pytest.approx(4176 - 5 * QA[2] / 7) and d.valid
    assert p.usable_at_arrival_units == pytest.approx(4214 - 2 * QA[1] / 7)  # D2: p50 depletion before arrival
    assert p.existing_stock_expected_expiry_units == pytest.approx(1396.9, abs=0.05)
    assert p.residual_shortfall_units == pytest.approx(0) and p.post_order_position == "COVERS_P90_RATE"
    assert p.target_capped_at_p90 and p.weekly_planning_target_units == pytest.approx(QA[2])


def test_example_b_bakery_daily_drops():
    p = example_b()
    assert p.arrangement == "SHORT_LIFE_RECURRING_DROPS" and p.ordered_units == 1428
    assert [d.ordered_units for d in p.drops] == [204] * 7
    assert [d.arrival_day for d in p.drops] == list(range(312, 319)) and all(d.expiry_day == d.arrival_day for d in p.drops)
    assert p.pre_delivery_position == "COVERS_P50_RATE" and p.post_order_position == "COVERS_P50_RATE"
    assert p.planning_weight == pytest.approx(0.875)
    assert all(d.rounding_excess_units == pytest.approx(204 - p.weekly_planning_target_units / 7) for d in p.drops)


def test_example_c_pre_delivery_shortage_gaps():
    p = example_c()
    gaps = {k: round(v, 1) for k, v in p.pre_delivery_gap_units.items()}
    assert gaps == {"p10": 404.4, "p50": 1006.7, "p90": 1752.1}
    assert p.pre_delivery_position == "BELOW_P10_RATE"
    assert p.ordered_units == 5580 and p.post_order_position == "COVERS_P90_RATE"  # the order cannot fix Mon-Wed


# ------------------------------------------------------------------------------- simulator conventions agree
def test_arrangement_and_drop_days_match_the_accepted_simulator():
    for R, lt in itertools.product(range(0, 20), range(0, 9)):
        assert I.delivery_arrangement(R, lt) == RP._arrangement(R, lt)
        arr = I.delivery_arrangement(R, lt)
        if arr != "UNSUPPORTED":
            assert I.drop_schedule(100, R, arr) == RP._drop_days(100, R, arr)
    assert I.dow_of(RP.day_index(34, 3)) == 3


# ----------------------------------------------------------------------------------------------- expiry
def test_stock_is_never_counted_after_expiry():
    rate = 70.0  # 10 a day
    _, table, short = I.project_stock([I.Lot(5, 1, 1000)], [], 1, 11, rate)
    assert [r["sellable_units_start"] > 0 for r in table] == [True] * 5 + [False] * 5
    assert table[4]["expired_end_of_day_units"] == pytest.approx(950) and short == pytest.approx(50)


def test_stock_expiring_before_arrival_contributes_nothing():
    p = I.plan_order([I.Lot(233, 225, 10_000)], [], 232, 2, 9, 700, 700, 700, 50, 1, 1)
    assert p.usable_at_arrival_units == 0 and p.ordered_units == 700


def test_stock_expiring_mid_window_covers_only_its_sellable_days():
    for expiry in range(234, 241):
        p = I.plan_order([I.Lot(expiry, 230, 100_000)], [], 232, 2, 9, 700, 700, 700, 50, 1, 1)
        assert p.drops[0].net_need_units == pytest.approx(100 * (240 - expiry))
        assert p.residual_shortfall_units == pytest.approx(0)


def test_new_drops_never_cover_days_after_their_own_expiry():
    for R in (1, 2, 3, 4, 5, 6):
        p = I.plan_order([], [], 8, 1, R, 70, 70, 70, 50, 1, 1)
        assert all(d.days_covered <= R and d.expiry_day == d.arrival_day + R - 1 for d in p.drops)
        assert sum(d.days_covered for d in p.drops) == 7 and p.residual_shortfall_units == pytest.approx(0)


# ----------------------------------------------------------------------------------------- delivery timing
def test_committed_delivery_counts_only_from_its_arrival_day():
    gaps, pos = I.pre_delivery_gap([], [I.Delivery(3, 20, 1000)], 1, 5, 70, 70, 70)
    assert gaps["p50"] == pytest.approx(20) and pos == "BELOW_P10_RATE"  # days 1-2 uncovered, 3-4 covered
    gaps, _ = I.pre_delivery_gap([], [I.Delivery(1, 20, 1000)], 1, 5, 70, 70, 70)
    assert gaps["p50"] == pytest.approx(0)


def test_proposed_delivery_is_not_counted_before_its_arrival():
    p = I.plan_order([], [], 1, 3, 30, 70, 70, 70, 50, 1, 1)
    assert p.arrival_day == 4 and p.drops[0].arrival_day == 4
    assert p.pre_delivery_gap_units["p50"] == pytest.approx(30)  # days 1-3: the new order does not help
    pre = [r for r in p.days if r["phase"] == "PRE_ARRIVAL_P50"]
    assert [r["day"] for r in pre] == [1, 2, 3] and all(r["received_units"] == 0 for r in pre)
    win = [r for r in p.days if r["phase"] == "WINDOW_PLANNING_RATE"]
    assert win[0]["day"] == 4 and win[0]["received_units"] == 70


def test_later_arrival_gives_worse_post_order_coverage():
    on_time = I.post_order_coverage([], [I.Delivery(4, 20, 100)], 4, 35, 70, 105, 70)
    late = I.post_order_coverage([], [I.Delivery(7, 20, 100)], 4, 35, 70, 105, 70)
    assert on_time[1] == "COVERS_P50_RATE" and late[1] == "BELOW_P10_RATE" and late[2] > on_time[2]


def test_drops_arrive_only_on_the_schedule():
    for R, lt in itertools.product((1, 2, 3, 4, 6, 9), (1, 2, 3)):
        p = I.plan_order([], [], 50, lt, R, 70, 70, 70, 50, 1, 1)
        a = 50 + lt
        assert all(d.arrival_day >= a and (d.arrival_day - a) % R == 0 and d.arrival_day < a + 7 for d in p.drops)


# ------------------------------------------------------------------------------------- case size and MOQ
@pytest.mark.parametrize("need,case,moq,expected", [
    (0, 12, 2, 0), (-5, 12, 2, 0), (0.4, 12, 2, 24), (24, 12, 2, 24), (24.0000000001, 12, 2, 24),
    (25, 12, 2, 36), (36, 12, 2, 36), (1, 6, 4, 24), (30, 6, 4, 30), (100, 24, 1, 120),
])
def test_case_size_and_moq_rounding(need, case, moq, expected):
    q = I.size_drop(need, case, moq)
    assert q == expected and I.validate_delivery(q, case, moq) == []
    ce, me, te = I.rounding_excess(need, q, case)
    assert te == pytest.approx(ce + me) and (q == 0 or te >= -1e-6)
    if q == 0:
        assert (ce, me, te) == (0.0, 0.0, 0.0)


def test_validate_delivery_detects_each_violation():
    assert I.validate_delivery(30, 12, 2) == ["NOT_WHOLE_CASES"]
    assert I.validate_delivery(12, 12, 2) == ["BELOW_MOQ"]
    assert "NEGATIVE" in I.validate_delivery(-24, 12, 2)
    assert "NOT_WHOLE_UNITS" in I.validate_delivery(24.5, 12, 2)
    assert I.validate_delivery(0, 12, 2) == [] and I.validate_delivery(48, 12, 2) == []


def test_each_drop_is_rounded_independently_and_excess_is_visible():
    # 3 drops (R = 3) of 30, 30 and 10 units of need; case 12, MOQ 2: 36 + 36 + 24 = 96 (a weekly total would be 72)
    p = I.plan_order([], [], 1, 1, 3, 70, 70, 70, 50, 12, 2)
    assert [d.ordered_units for d in p.drops] == [36, 36, 24] and p.ordered_units == 96
    assert [round(d.net_need_units, 6) for d in p.drops] == [30, 30, 10]
    assert [(round(d.case_rounding_excess_units, 6), round(d.moq_excess_units, 6)) for d in p.drops] == [(6, 0), (6, 0), (2, 12)]
    assert p.rounding_excess_units == pytest.approx(26) and all(d.valid for d in p.drops)


def test_moq_binds_on_small_needs():
    p = I.plan_order([], [], 1, 1, 30, 7, 7, 7, 50, 6, 4)
    assert p.ordered_units == 24 and p.drops[0].moq_excess_units == pytest.approx(24 - 7 - 5)


# ---------------------------------------------------------------------------- unsupported and unavailable
@pytest.mark.parametrize("R,lt", [(9, 7), (9, 8), (0, 2), (-1, 1)])
def test_unsupported_arrangements_are_not_sized(R, lt):
    p = I.plan_order([I.Lot(300, 1, 50)], [], 10, lt, R, 70, 70, 70, 50, 12, 2)
    assert p.status == "NOT_SIZED_UNSUPPORTED_ARRANGEMENT" and p.arrangement == "UNSUPPORTED"
    assert p.ordered_units == 0 and p.drops == [] and p.days == []


@pytest.mark.parametrize("q", [(None, 70, 70), (70, float("nan"), 70)])
def test_missing_uncertainty_bounds_are_not_sized(q):
    p = I.plan_order([], [], 10, 2, 9, *q, 50, 12, 2)
    assert p.status == "NOT_SIZED_UNCERTAINTY_UNAVAILABLE" and p.ordered_units == 0 and p.drops == []
    p = I.plan_order([], [], 10, 2, 9, 70, 70, 70, 50, 12, 2, uncertainty_available=False)
    assert p.status == "NOT_SIZED_UNCERTAINTY_UNAVAILABLE"


# --------------------------------------------------------------------------- zero stock and no negative orders
def test_zero_usable_stock():
    p = I.plan_order([], [], 1, 2, 9, 35, 70, 105, 70, 1, 1)
    assert p.usable_at_arrival_units == 0 and p.existing_stock_expected_expiry_units == 0
    assert p.pre_delivery_gap_units == pytest.approx({"p10": 10, "p50": 20, "p90": 30})
    assert p.drops[0].net_need_units == pytest.approx(7 * (70 + 0.5 * 35) / 7)


def test_ample_stock_gives_no_order_and_no_negative_quantity():
    p = I.plan_order([I.Lot(400, 1, 1_000_000)], [], 10, 2, 30, 70, 70, 70, 95, 12, 2)
    assert p.ordered_units == 0 and all(d.ordered_units == 0 and d.net_need_units == 0 for d in p.drops)
    assert p.rounding_excess_units == 0 and p.residual_shortfall_units == pytest.approx(0)


def test_random_inputs_never_give_negative_or_invalid_orders():
    rng = np.random.default_rng(7)
    for _ in range(300):
        R, lt = int(rng.integers(1, 15)), int(rng.integers(1, 7))
        D0 = 100
        lots = [I.Lot(int(D0 + rng.integers(-1, 20)), int(D0 - rng.integers(0, 5)), float(rng.integers(0, 2000)))
                for _ in range(int(rng.integers(0, 4)))]
        committed = [I.Delivery(int(D0 + rng.integers(0, lt + 1)), int(D0 + lt + rng.integers(0, 10)), int(rng.integers(0, 500)))
                     for _ in range(int(rng.integers(0, 3)))]
        q = sorted(float(x) for x in rng.uniform(0, 3000, 3))
        case, moq = int(rng.choice([1, 6, 12, 24])), int(rng.integers(1, 5))
        p = I.plan_order(lots, committed, D0, lt, R, *q, float(rng.uniform(40, 100)), case, moq)
        assert p.ordered_units >= 0 and all(d.ordered_units >= 0 and d.valid for d in p.drops)
        assert all(d.rounding_excess_units >= -1e-6 for d in p.drops)
        assert p.residual_shortfall_units == pytest.approx(0, abs=1e-6)  # sized drops always cover the window
        for r in p.days:
            assert min(r["served_units"], r["shortfall_units"], r["expired_end_of_day_units"]) >= -1e-9


def test_per_day_table_balances():
    p = example_a()
    rows = p.days
    for prev, nxt in zip(rows, rows[1:]):
        carried = prev["sellable_units_start"] - prev["served_units"] - prev["expired_end_of_day_units"]
        assert nxt["sellable_units_start"] == pytest.approx(carried + nxt["received_units"])


# ------------------------------------------------------------------------------------------- fill rate
def test_fill_rate_exposure_is_reported_without_inflating_orders():
    base = example_c()
    for f in (100, 90, 75, 60):
        p = I.plan_order([I.Lot(239, 225, 638)], [], 225, 3, 15, *QC, 92, 12, 2, fill_low_pct=f)
        assert p.ordered_units == base.ordered_units and p.fill_rate_exposure["orders_adjusted"] is False
    e = {f: I.plan_order([I.Lot(239, 225, 638)], [], 225, 3, 15, *QC, 92, 12, 2, fill_low_pct=f).fill_rate_exposure
         for f in (100, 90, 75, 60)}
    assert e[100]["total_exposure_units"] == 0 and e[100]["undelivered_units"]["new_order"] == 0
    assert e[90]["total_exposure_units"] < e[75]["total_exposure_units"] < e[60]["total_exposure_units"]
    assert e[75]["undelivered_units"]["new_order"] == 5580 - 4185  # simulator convention: rounded down
    assert base.fill_rate_exposure["routine_fill_pct"] == 100 and base.fill_rate_exposure["stress_fill_pct"] == 75


def test_order_quantities_unchanged_by_the_exposure_calculation():
    assert (example_a().ordered_units, example_b().ordered_units, example_c().ordered_units) == (4176, 1428, 5580)
    for f in (100, 75, 50):
        p = I.plan_order([I.Lot(235, 227, 4214)], [], 232, 2, 9, *QA, 92, 12, 2, fill_low_pct=f)
        assert [d.ordered_units for d in p.drops] == [4176]


# ------------------------------------------------------- two-period fill-rate exposure (5B-3a acceptance, decision 2)
def test_pre_arrival_exposure_from_a_short_committed_delivery():
    # 10 a day; 15 units committed on day 2; the new order arrives on day 4. Baseline gap 10 + 5 = 15; at 75% the
    # delivery is 11 units, gap 10 + 9 = 19: pre-arrival exposure 4, nothing carried into the window either way.
    e = I.plan_order([], [I.Delivery(2, 30, 15)], 1, 3, 30, 70, 70, 70, 50, 1, 1).fill_rate_exposure
    assert e["baseline_shortfall_units"]["pre_arrival"] == pytest.approx(15)
    assert e["stress_shortfall_units"]["pre_arrival"] == pytest.approx(19)
    assert e["pre_arrival_exposure_units"] == pytest.approx(4)
    assert e["post_arrival_from_pre_arrival_carryover_units"] == pytest.approx(0)
    assert e["undelivered_units"]["committed_pre_arrival"] == 4


def test_short_committed_delivery_reduces_stock_carried_into_the_window():
    # 100 units committed on day 2: 80 left on day 4, enough for the window, so no new order. At 75% only 55 are
    # left and the window is 15 short. That shortfall is post-arrival (carry-over), not pre-arrival.
    p = I.plan_order([], [I.Delivery(2, 30, 100)], 1, 3, 30, 70, 70, 70, 50, 1, 1)
    e = p.fill_rate_exposure
    assert p.ordered_units == 0 and e["pre_arrival_exposure_units"] == pytest.approx(0)
    assert e["post_arrival_from_pre_arrival_carryover_units"] == pytest.approx(15)
    assert e["post_arrival_from_window_deliveries_units"] == pytest.approx(0)


def test_post_arrival_exposure_from_the_new_order_arriving_short():
    p = I.plan_order([], [], 1, 3, 30, 70, 70, 70, 50, 1, 1)  # order 70 on day 4; at 75% only 52 arrive
    e = p.fill_rate_exposure
    assert p.ordered_units == 70 and e["undelivered_units"]["new_order"] == 18
    assert e["pre_arrival_exposure_units"] == pytest.approx(0)
    assert e["post_arrival_from_window_deliveries_units"] == pytest.approx(18)
    assert e["post_arrival_exposure_units"] == pytest.approx(18)


def test_exposure_periods_do_not_double_count():
    lots = [I.Lot(5, 1, 5)]
    committed = [I.Delivery(2, 12, 20), I.Delivery(6, 15, 30)]  # one before arrival (day 4), one inside the window
    p = I.plan_order(lots, committed, 1, 3, 9, 70, 70, 70, 50, 6, 2)
    e = p.fill_rate_exposure
    assert e["pre_arrival_exposure_units"] > 0 and e["post_arrival_from_window_deliveries_units"] > 0
    assert e["post_arrival_exposure_units"] == pytest.approx(e["post_arrival_from_pre_arrival_carryover_units"]
                                                             + e["post_arrival_from_window_deliveries_units"])
    assert e["total_exposure_units"] == pytest.approx(e["pre_arrival_exposure_units"] + e["post_arrival_exposure_units"])
    # Total equals stress minus baseline over one continuous walk; each day is counted in exactly one period.
    base, stress = e["baseline_shortfall_units"], e["stress_shortfall_units"]
    assert e["total_exposure_units"] == pytest.approx(stress["pre_arrival"] + stress["post_arrival"]
                                                      - base["pre_arrival"] - base["post_arrival"])
    rate = p.weekly_planning_target_units
    at_a, pre_days, s_pre = I.project_stock(lots, I._delivered_at(committed[:1], 75), 1, 4, 70)
    new = [I.Delivery(d.arrival_day, d.expiry_day, d.ordered_units) for d in p.drops if d.ordered_units]
    _, win_days, s_post = I.project_stock(at_a, I._delivered_at(committed[1:] + new, 75), 4, 11, rate)
    assert [r["day"] for r in pre_days] == [1, 2, 3] and [r["day"] for r in win_days] == list(range(4, 11))
    assert (s_pre, s_post) == pytest.approx((stress["pre_arrival"], stress["post_arrival"]))
    # The pre-arrival exposure does not depend on anything arriving in the window.
    e2 = I.fill_rate_exposure(lots, committed[:1], [], 1, 4, 70, rate)
    assert e2["pre_arrival_exposure_units"] == pytest.approx(e["pre_arrival_exposure_units"])
    assert min(e["pre_arrival_exposure_units"], e["post_arrival_from_pre_arrival_carryover_units"],
               e["post_arrival_from_window_deliveries_units"]) >= 0


def test_exposure_baseline_is_the_plan_itself():
    for p in (example_a(), example_b(), example_c()):
        e = p.fill_rate_exposure
        assert e["baseline_shortfall_units"]["pre_arrival"] == pytest.approx(p.pre_delivery_gap_units["p50"])
        assert e["baseline_shortfall_units"]["post_arrival"] == pytest.approx(p.residual_shortfall_units)
    e = example_c().fill_rate_exposure  # the routine gap before delivery is not counted again as exposure
    assert e["pre_arrival_exposure_units"] == 0
    assert e["post_arrival_exposure_units"] == pytest.approx(QC[2] - 4185)


# --------------------------------------------------------------------- p50 arrival state and expiry projections
def test_post_order_positions_share_the_p50_arrival_state():
    lots, committed = [I.Lot(236, 229, 1500)], [I.Delivery(233, 245, 600)]
    p = I.plan_order(lots, committed, 232, 3, 13, *QA, 92, 12, 2)
    at_a, _, _ = I.project_stock(lots, committed, 232, 235, QA[1])
    assert p.usable_at_arrival_units == pytest.approx(sum(x.units for x in at_a))
    new = [I.Delivery(d.arrival_day, d.expiry_day, d.ordered_units) for d in p.drops if d.ordered_units]
    for k, q in zip(("p10", "p50", "p90"), QA):
        assert p.post_order_shortfall_units[k] == pytest.approx(I.project_stock(at_a, new, 235, 242, q)[2])
    at_a_p90 = I.project_stock(lots, committed, 232, 235, QA[2])[0]
    assert sum(x.units for x in at_a_p90) < p.usable_at_arrival_units  # v1.1-style depletion at p90 would differ


def test_dairy_example_day_by_day():
    p = example_a()
    win = {r["day"]: r for r in p.days if r["phase"] == "WINDOW_PLANNING_RATE"}
    pre = {r["day"]: r for r in p.days if r["phase"] == "PRE_ARRIVAL_P50"}
    assert list(pre) == [232, 233] and all(r["planned_use_units"] == pytest.approx(QA[1] / 7) for r in pre.values())
    assert list(win) == list(range(234, 241)) and win[234]["received_units"] == 4176
    assert all(r["shortfall_units"] == pytest.approx(0) for r in win.values())
    assert win[235]["expired_end_of_day_units"] == pytest.approx(p.existing_stock_expected_expiry_units)
    assert sum(r["expired_end_of_day_units"] for r in win.values()) == pytest.approx(p.existing_stock_expected_expiry_units)
    assert win[236]["sellable_units_start"] == pytest.approx(4176)  # only the new order is sellable from Friday


def test_expected_expiry_is_explanatory_and_not_counted_as_supply_or_waste():
    p = example_a()
    # Removing exactly the units projected to expire leaves the order unchanged: they were never counted as supply.
    trimmed = I.plan_order([I.Lot(235, 227, 4214 - p.existing_stock_expected_expiry_units)], [], 232, 2, 9, *QA, 92, 12, 2)
    assert trimmed.ordered_units == p.ordered_units
    assert trimmed.existing_stock_expected_expiry_units == pytest.approx(0, abs=1e-6)
    names = set(I.OrderPlan.__dataclass_fields__) | {k for r in p.days for k in r}
    assert not any(n.startswith("sim_") or "realised" in n or "realized" in n for n in names)
    assert "not realised simulated waste" in p.projection_note
    # Realised simulated waste exists only in the accepted simulator, which does not use the calculator.
    src = inspect.getsource(RP)
    assert "decision.inventory" not in src and "import inventory" not in src and "sim_expired_units" in src


def test_exposure_outputs_are_deterministic():
    runs = [I.plan_order([I.Lot(5, 1, 25)], [I.Delivery(2, 12, 40), I.Delivery(6, 15, 30)], 1, 3, 9, 70, 70, 70, 50, 6, 2)
            for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


def test_planning_uses_ordered_quantities_not_receipts():
    params = inspect.signature(I.plan_order).parameters
    assert not {"delivered_units", "sales", "demand", "actual_units"} & set(params)
    assert set(I.Delivery.__dataclass_fields__) == {"arrival_day", "expiry_day", "units", "delivery_id"}


# ------------------------------------------------------------------------------------- leakage and determinism
def test_inputs_are_not_modified_and_results_are_deterministic():
    lots = [I.Lot(240, 228, 900, "x"), I.Lot(235, 227, 4214, "y")]
    committed = [I.Delivery(233, 241, 300, "c")]
    before = copy.deepcopy((lots, committed))
    p1 = I.plan_order(lots, committed, 232, 2, 9, *QA, 92, 12, 2)
    p2 = I.plan_order(list(reversed(lots)), committed, 232, 2, 9, *QA, 92, 12, 2)
    assert (lots, committed) == before
    assert p1 == p2 == I.plan_order(lots, committed, 232, 2, 9, *QA, 92, 12, 2)


def test_deliveries_after_the_window_do_not_change_the_decision():
    later = [I.Delivery(241 + k, 260, 10_000) for k in range(5)]
    assert I.plan_order([I.Lot(235, 227, 4214)], later, 232, 2, 9, *QA, 92, 12, 2).drops == example_a().drops


@pytest.fixture(scope="module")
def captured_states():
    """Decision-time states from the accepted simulator on the synthetic fixtures: base and future-scrambled sales."""
    panel = build_panel(forecast_raw())
    contract = FC.build_contract(fake_contract_predictions(panel), panel, "TEST")["contract"]
    v = {**A.resolve(A.load(), "SC1"), "opening_cover_multiplier": 0.05}
    orig = RP._decide

    def run(p):
        seen = {}

        def spy(k, T, D0, a, h1, h4, st, values, schedule):
            row = h1.loc[(*k, T)] if (*k, T) in h1.index else None
            seen[(k, T)] = (D0, dict(a), None if row is None else row.to_dict(),
                            [I.Lot(e, ar, q, i) for e, ar, q, i in st.lots],
                            [I.Delivery(d, dl["expiry_day"], dl["ordered_units"], dl["delivery_id"])
                             for d, dls in sorted(st.scheduled.items()) for dl in dls])
            return orig(k, T, D0, a, h1, h4, st, values, schedule)

        RP._decide = spy
        try:
            RP.simulate(contract, p, v)
        finally:
            RP._decide = orig
        return seen

    cutoff = 21
    p2 = panel.copy()
    later = p2["week_index"] > cutoff
    p2.loc[later, "Units_Sold"] = np.random.default_rng(5).permutation(p2.loc[later, "Units_Sold"].to_numpy())
    return run(panel), run(p2), cutoff, v


def _plans(states, cutoff, v):
    out = {}
    for (k, T), (D0, a, row, lots, committed) in sorted(states.items()):
        if T > cutoff or row is None:
            continue
        out[(k, T)] = I.plan_order(lots, committed, D0, a["effective_lead_time_days"], a["remaining_life_days"],
                                   row["lower_p10_units"], row["median_p50_units"], row["upper_p90_units"],
                                   v["service_target_pct"][a["Product_Category"]], v["case_size_units"][a["Product_Category"]],
                                   v["moq_cases_per_delivery"], uncertainty_available=row["uncertainty_status"] == "AVAILABLE")
    return out


def test_scrambled_future_sales_leave_earlier_plans_unchanged(captured_states):
    base, scrambled, cutoff, v = captured_states
    pb, ps = _plans(base, cutoff, v), _plans(scrambled, cutoff, v)
    assert pb and pb.keys() == ps.keys()
    assert all(pb[k] == ps[k] for k in pb)
    assert any(p.status == "SIZED" and p.ordered_units > 0 for p in pb.values())
    later = [k for k in base if k[1] > cutoff + 1]
    assert any(base[k][3] != scrambled[k][3] for k in later)  # later states did change: the test can see a difference


def test_calculator_on_simulator_states_respects_all_delivery_rules(captured_states):
    base, _, cutoff, v = captured_states
    for p in _plans(base, 99, v).values():
        if p.status != "SIZED":
            continue
        assert all(d.valid and d.arrival_day >= p.arrival_day for d in p.drops)
        assert p.residual_shortfall_units == pytest.approx(0, abs=1e-6)
