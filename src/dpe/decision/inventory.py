"""Step 5B-3a: time-phased, expiry-aware inventory calculator (pure, deterministic functions; no I/O).

Design: docs/STEP_5B3_INVENTORY_ENGINE_DESIGN.md section 3, with the approved decisions in
docs/STEP_5B3_IMPLEMENTATION_READINESS.md (D1-D3, D5, D7, D8). Not yet wired into the replay simulator; no
recommendation categories, approval records or review queue here (stage 5B-3b).

Conventions (identical to the accepted replay simulator v1.1):
  * days are integers; day_index(week, dow) = (week - 1) * 7 + dow, Monday = dow 1
  * a lot is sellable on day x only if arrival_day <= x <= expiry_day; it expires at the END of expiry_day
  * a delivery arriving on day d is sellable from day d; it expires at the end of d + R - 1 (R = remaining life)
  * stock is used oldest expiry first (then oldest arrival)
  * the decision is taken on day D0 (day 1 of the target week); the new order first arrives on day a = D0 + LT
  * coverage window a .. a + 6; drops: one on day a (LONG_LIFE_WEEKLY, R >= 7) or one every R days from a
    (SHORT_LIFE_RECURRING_DROPS, R < 7); UNSUPPORTED when LT >= 7 or R < 1 (nothing is sized)

Approved rules:
  * D2: expected depletion before the new order arrives uses the p50 rate; the shortage gap before delivery is
    assessed separately at the p10, p50 and p90 rates
  * after arrival, coverage is assessed separately at p10, p50 and p90 from the SAME p50-projected arrival state
    (5B-3a acceptance, decision 1). These are conditional planning positions, not calibrated stockout probabilities.
    The accepted v1.1 calculation (replay.coverage_position) is unchanged and remains policy P1.
  * inside the window, need is measured at the planning rate (p50 + w(p90 - p50), capped at p90)
  * D3: scheduled deliveries are planned at their ORDERED quantity (100% expected fulfilment); realised receipts are
    never an input. Fill-rate exposure at the 75% illustrative stress is reported in two non-overlapping periods
    (pre-arrival, post-arrival); orders are never inflated for it.
  * expected expiry is an explanatory projection only: it is never supply, never demand and never realised waste
    (realised simulated waste exists only in the replay simulator's sim_expired_units)
  * D7: each delivery is rounded up independently to whole cases and at least MOQ cases; rounding excess is reported
  * D8: supplier capacity is not an input

Daily rates are a weekly quantity split by the daily profile: a coverage convention, not a daily demand forecast.
Shortage gaps and coverage positions are heuristics, not stockout probabilities.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from dpe.decision.assumptions import case_round, planning_weight

UNIFORM_PROFILE = (1 / 7,) * 7
RATE_LABELS = (("p90", "COVERS_P90_RATE"), ("p50", "COVERS_P50_RATE"), ("p10", "COVERS_P10_RATE_ONLY"))
SHORTAGE_POSITIONS = ("COVERS_P10_RATE_ONLY", "BELOW_P10_RATE")
TOL = 1e-6


@dataclass(frozen=True)
class Lot:
    """Stock on hand: one batch with one arrival and one expiry day."""
    expiry_day: int
    arrival_day: int
    units: float
    lot_id: str = ""


@dataclass(frozen=True)
class Delivery:
    """A scheduled delivery at its ORDERED quantity (what the decision-maker expects; never the realised receipt)."""
    arrival_day: int
    expiry_day: int
    units: int
    delivery_id: str = ""


@dataclass(frozen=True)
class DropSizing:
    drop: int
    arrival_day: int
    days_covered: int
    expiry_day: int
    net_need_units: float
    ordered_units: int
    case_rounding_excess_units: float
    moq_excess_units: float
    rounding_excess_units: float
    valid: bool


@dataclass
class OrderPlan:
    status: str                       # SIZED | NOT_SIZED_UNSUPPORTED_ARRANGEMENT | NOT_SIZED_UNCERTAINTY_UNAVAILABLE
    decision_day: int
    arrival_day: int | None
    arrangement: str
    planning_weight: float | None = None
    weekly_planning_target_units: float | None = None
    target_capped_at_p90: bool = False
    usable_at_arrival_units: float | None = None
    existing_stock_expected_expiry_units: float | None = None   # explanatory projection; not realised waste
    drops: list = field(default_factory=list)
    ordered_units: int = 0
    rounding_excess_units: float = 0.0
    pre_delivery_gap_units: dict | None = None
    pre_delivery_position: str | None = None
    post_order_shortfall_units: dict | None = None
    post_order_position: str | None = None
    residual_shortfall_units: float | None = None
    fill_rate_exposure: dict | None = None
    days: list = field(default_factory=list)
    projection_note: str = ("planning projection: expected expiry and shortfalls are heuristic, conditional on the "
                            "p50-projected arrival state; not realised simulated waste and not stockout probabilities")


# ----------------------------------------------------------------------------------------- calendar helpers
def dow_of(day: int) -> int:
    return (day - 1) % 7 + 1


def delivery_arrangement(remaining_life: int, lead_time: int) -> str:
    if lead_time >= 7 or remaining_life < 1:
        return "UNSUPPORTED"
    return "LONG_LIFE_WEEKLY" if remaining_life >= 7 else "SHORT_LIFE_RECURRING_DROPS"


def drop_schedule(arrival_day: int, remaining_life: int, arrangement: str) -> list[tuple[int, int]]:
    """(arrival_day, days covered) for each drop of the 7-day window starting on arrival_day."""
    if arrangement == "UNSUPPORTED":
        return []
    if arrangement == "LONG_LIFE_WEEKLY":
        return [(arrival_day, 7)]
    days = range(arrival_day, arrival_day + 7, remaining_life)
    return [(d, min(remaining_life, arrival_day + 7 - d)) for d in days]


def daily_units(weekly_units: float, day: int, profile=UNIFORM_PROFILE) -> float:
    return weekly_units * profile[dow_of(day) - 1]


# ------------------------------------------------------------------------------------- depletion and projection
def _as_rows(lots) -> list[list]:
    # Canonical order, so results do not depend on the order in which lots are supplied.
    return sorted([lot.expiry_day, lot.arrival_day, float(lot.units)] for lot in lots)


def _by_day(deliveries) -> dict[int, list[Delivery]]:
    out: dict[int, list[Delivery]] = {}
    for dl in deliveries:
        out.setdefault(dl.arrival_day, []).append(dl)
    return out


def deplete_day(rows: list[list], day: int, demand: float) -> tuple[list[list], float, float, float]:
    """Serve one day's demand oldest expiry first from lots sellable on `day`, then expire lots whose last sellable
    day is `day`. Returns (remaining rows, served, shortfall, expired). Does not modify `rows`."""
    rows = [list(r) for r in rows]
    need = demand
    for r in sorted(rows, key=lambda x: (x[0], x[1])):
        if need <= 1e-12:
            break
        if r[1] > day or r[0] < day:
            continue  # not yet arrived, or already expired: never counted
        take = min(r[2], need)
        r[2] -= take
        need -= take
    shortfall = max(0.0, need)
    expired = sum(r[2] for r in rows if r[0] == day and r[1] <= day)
    rows = [r for r in rows if r[2] > 1e-9 and r[0] > day]
    return rows, demand - shortfall, shortfall, expired


def project_stock(lots, deliveries, start_day: int, end_day: int, weekly_rate: float, profile=UNIFORM_PROFILE,
                  count_from: int | None = None) -> tuple[list[Lot], list[dict], float]:
    """Walk days start_day .. end_day - 1: receive deliveries on their arrival day, deplete at weekly_rate split by
    profile, expire at end of day. Returns (lots remaining at the start of end_day, per-day table, total shortfall on
    days >= count_from)."""
    rows = _as_rows(lots)
    arrivals = _by_day(deliveries)
    count_from = start_day if count_from is None else count_from
    table, short = [], 0.0
    for d in range(start_day, end_day):
        received = 0.0
        for dl in arrivals.get(d, []):
            if dl.units > 0:
                rows.append([dl.expiry_day, d, float(dl.units)])
                received += dl.units
        sellable = sum(r[2] for r in rows if r[1] <= d <= r[0])
        demand = daily_units(weekly_rate, d, profile)
        rows, served, shortfall, expired = deplete_day(rows, d, demand)
        if d >= count_from:
            short += shortfall
        table.append({"day": d, "dow": dow_of(d), "received_units": received, "sellable_units_start": sellable,
                      "planned_use_units": demand, "served_units": served, "shortfall_units": shortfall,
                      "expired_end_of_day_units": expired})
    return [Lot(r[0], r[1], r[2]) for r in rows], table, short


def unsold_at_expiry(lots, start_day: int, weekly_rate: float, profile=UNIFORM_PROFILE) -> float:
    """Units of current lots expected to expire unsold if depleted at weekly_rate with no new deliveries."""
    if not lots:
        return 0.0
    _, table, _ = project_stock(lots, [], start_day, max(lot.expiry_day for lot in lots) + 1, weekly_rate, profile)
    return sum(r["expired_end_of_day_units"] for r in table)


# ------------------------------------------------------------------------------------------ rounding and checks
def validate_delivery(units, case: int, moq_cases: int) -> list[str]:
    """Violations of the delivery rules; an empty list means the delivery is valid (0, or whole cases >= MOQ)."""
    problems = []
    if not float(units).is_integer():
        problems.append("NOT_WHOLE_UNITS")
    if units < 0:
        problems.append("NEGATIVE")
    if units > 0 and units % case:
        problems.append("NOT_WHOLE_CASES")
    if 0 < units < moq_cases * case:
        problems.append("BELOW_MOQ")
    return problems


def rounding_excess(net_need: float, ordered: int, case: int) -> tuple[float, float, float]:
    """(case-rounding excess, MOQ excess, total) for one delivery. Zero when nothing is ordered."""
    if ordered <= 0:
        return 0.0, 0.0, 0.0
    whole_cases = math.ceil(net_need / case - 1e-9) * case
    return whole_cases - net_need, ordered - whole_cases, ordered - net_need


def size_drop(net_need: float, case: int, moq_cases: int) -> int:
    """Round one delivery up to whole cases and at least MOQ cases; 0 when there is no positive need."""
    return case_round(net_need, case, moq_cases)


# -------------------------------------------------------------------------------------- coverage and shortage
def _position(shortfalls: dict) -> str:
    for key, label in RATE_LABELS:
        if shortfalls[key] <= TOL:
            return label
    return "BELOW_P10_RATE"


def pre_delivery_gap(lots, committed, decision_day: int, arrival_day: int, p10: float, p50: float, p90: float,
                     profile=UNIFORM_PROFILE) -> tuple[dict, str]:
    """Heuristic shortage gap on days decision_day .. arrival_day - 1 (before the new order can arrive), at the p10,
    p50 and p90 weekly rates. Uses stock on hand and deliveries committed BEFORE this decision only."""
    gaps = {k: project_stock(lots, committed, decision_day, arrival_day, q, profile)[2]
            for k, q in (("p10", p10), ("p50", p50), ("p90", p90))}
    return gaps, _position(gaps)


def size_deliveries(lots_at_arrival, committed, schedule, remaining_life: int, planning_weekly: float, case: int,
                    moq_cases: int, profile=UNIFORM_PROFILE) -> tuple[list[DropSizing], list[Delivery]]:
    """Size each drop in date order to the shortfall on the days it covers, after usable stock, committed deliveries
    and earlier drops; stock is counted only while sellable. Returns the sizings and the new deliveries."""
    sizings, new = [], []
    for i, (d, cov) in enumerate(schedule):
        start = schedule[0][0]
        _, _, need = project_stock(lots_at_arrival, list(committed) + new, start, d + cov, planning_weekly, profile,
                                   count_from=d)
        q = size_drop(need, case, moq_cases)
        ce, me, te = rounding_excess(need, q, case)
        exp = d + remaining_life - 1
        sizings.append(DropSizing(i + 1, d, cov, exp, need, q, ce, me, te, not validate_delivery(q, case, moq_cases)))
        if q > 0:
            new.append(Delivery(d, exp, q, f"NEW-D{i + 1}"))
    return sizings, new


def post_order_coverage(lots_at_arrival, deliveries, arrival_day: int, p10: float, p50: float, p90: float,
                        planning_weekly: float, profile=UNIFORM_PROFILE) -> tuple[dict, str, float]:
    """Shortfall over the window arrival_day .. arrival_day + 6 at the p10/p50/p90 and planning rates, with every
    delivery counted only from its scheduled arrival day. `lots_at_arrival` is the p50-projected arrival state, the
    same for every rate: the positions are conditional planning positions, not stockout probabilities.
    Returns (shortfalls, position, residual at planning rate)."""
    end = arrival_day + 7
    short = {k: project_stock(lots_at_arrival, deliveries, arrival_day, end, q, profile)[2]
             for k, q in (("p10", p10), ("p50", p50), ("p90", p90))}
    residual = project_stock(lots_at_arrival, deliveries, arrival_day, end, planning_weekly, profile)[2]
    return short, _position(short), residual


def _delivered_at(deliveries, fill_pct: float) -> list[Delivery]:
    """Deliveries arriving at fill_pct of the ordered quantity, rounded down as in the simulator."""
    return [Delivery(x.arrival_day, x.expiry_day, int(math.floor(x.units * fill_pct / 100 + 1e-9)), x.delivery_id)
            for x in deliveries]


def _two_period_walk(lots, pre_dl, win_dl, decision_day: int, arrival_day: int, p50: float, planning_weekly: float,
                     profile) -> tuple[float, float]:
    """One continuous walk: days decision_day .. arrival_day - 1 at p50 (D2), then the window at the planning rate,
    the window starting from the state the first period leaves. Returns (pre-arrival, post-arrival) shortfall."""
    at_a, _, pre = project_stock(lots, pre_dl, decision_day, arrival_day, p50, profile)
    post = project_stock(at_a, win_dl, arrival_day, arrival_day + 7, planning_weekly, profile)[2]
    return pre, post


def fill_rate_exposure(lots, committed, new, decision_day: int, arrival_day: int, p50: float, planning_weekly: float,
                       fill_pct: float = 75.0, profile=UNIFORM_PROFILE) -> dict:
    """Illustrative stress: extra shortfall if deliveries arrive at fill_pct instead of the 100% routine planning
    assumption. Reported only: proposed orders are NOT changed.

    Both cases use the same continuous walk as planning (p50 before arrival, planning rate in the window), so the
    baseline equals the plan's own pre-delivery gap at p50 and its residual shortfall. Each day belongs to exactly one
    period, so the two exposures add up to the total without double counting:
      A  pre-arrival exposure   extra shortfall on days decision_day .. arrival_day - 1 (committed deliveries short)
      B  post-arrival exposure  extra shortfall on window days, split sequentially (B1 + B2 = B) into
           B1 carry-over        committed pre-arrival deliveries short, so less stock enters the window
           B2 window deliveries the new order and committed in-window deliveries short as well
    """
    pre_dl = [x for x in committed if x.arrival_day < arrival_day]
    win_dl = [x for x in committed if x.arrival_day >= arrival_day] + list(new)
    walk = lambda pre, win: _two_period_walk(lots, pre, win, decision_day, arrival_day, p50, planning_weekly, profile)  # noqa: E731
    base_pre, base_post = walk(pre_dl, win_dl)
    stress_pre, carry_post = walk(_delivered_at(pre_dl, fill_pct), win_dl)
    _, stress_post = walk(_delivered_at(pre_dl, fill_pct), _delivered_at(win_dl, fill_pct))
    short_units = lambda dls: int(sum(x.units for x in dls) - sum(x.units for x in _delivered_at(dls, fill_pct)))  # noqa: E731
    a, b1, b2 = stress_pre - base_pre, carry_post - base_post, stress_post - carry_post
    return {"routine_fill_pct": 100.0, "stress_fill_pct": fill_pct, "orders_adjusted": False,
            "rates": "pre-arrival p50; window planning rate",
            "baseline_shortfall_units": {"pre_arrival": base_pre, "post_arrival": base_post},
            "stress_shortfall_units": {"pre_arrival": stress_pre, "post_arrival": stress_post},
            "pre_arrival_exposure_units": a,
            "post_arrival_exposure_units": b1 + b2,
            "post_arrival_from_pre_arrival_carryover_units": b1,
            "post_arrival_from_window_deliveries_units": b2,
            "total_exposure_units": a + b1 + b2,
            "undelivered_units": {"committed_pre_arrival": short_units(pre_dl),
                                  "committed_in_window": short_units([x for x in committed if x.arrival_day >= arrival_day]),
                                  "new_order": short_units(new)}}


# ------------------------------------------------------------------------------------------------ one decision
def plan_order(lots, committed, decision_day: int, lead_time: int, remaining_life: int, p10, p50, p90,
               service_target_pct: float, case: int, moq_cases: int, profile=UNIFORM_PROFILE,
               fill_low_pct: float = 75.0, uncertainty_available: bool = True) -> OrderPlan:
    """Size one weekly order. `committed` are deliveries scheduled before this decision at ORDERED quantities."""
    lots, committed = tuple(lots), tuple(committed)
    arr = delivery_arrangement(remaining_life, lead_time)
    if arr == "UNSUPPORTED":
        return OrderPlan("NOT_SIZED_UNSUPPORTED_ARRANGEMENT", decision_day, None, arr)
    a = decision_day + lead_time
    if not uncertainty_available or any(x is None or (isinstance(x, float) and math.isnan(x)) for x in (p10, p50, p90)):
        return OrderPlan("NOT_SIZED_UNCERTAINTY_UNAVAILABLE", decision_day, a, arr)
    w, capped = planning_weight(service_target_pct)
    s_week = p50 + w * (p90 - p50)
    pre_dl = [x for x in committed if x.arrival_day < a]
    win_dl = [x for x in committed if x.arrival_day >= a]
    gaps, pre_pos = pre_delivery_gap(lots, pre_dl, decision_day, a, p10, p50, p90, profile)
    at_a, pre_days, _ = project_stock(lots, pre_dl, decision_day, a, p50, profile)          # D2: p50 before arrival
    usable = sum(lot.units for lot in at_a)
    schedule = drop_schedule(a, remaining_life, arr)
    sizings, new = size_deliveries(at_a, win_dl, schedule, remaining_life, s_week, case, moq_cases, profile)
    _, win_days, _ = project_stock(at_a, list(win_dl) + new, a, a + 7, s_week, profile)
    short, post_pos, residual = post_order_coverage(at_a, list(win_dl) + new, a, p10, p50, p90, s_week, profile)
    existing_expiry = unsold_at_expiry(at_a, a, s_week, profile) if at_a else 0.0
    plan = OrderPlan("SIZED", decision_day, a, arr, planning_weight=w, weekly_planning_target_units=s_week,
                     target_capped_at_p90=capped, usable_at_arrival_units=usable,
                     existing_stock_expected_expiry_units=existing_expiry, drops=sizings,
                     ordered_units=int(sum(s.ordered_units for s in sizings)),
                     rounding_excess_units=sum(s.rounding_excess_units for s in sizings),
                     pre_delivery_gap_units=gaps, pre_delivery_position=pre_pos, post_order_shortfall_units=short,
                     post_order_position=post_pos, residual_shortfall_units=residual,
                     fill_rate_exposure=fill_rate_exposure(lots, committed, new, decision_day, a, p50, s_week,
                                                           fill_low_pct, profile),
                     days=[dict(r, phase="PRE_ARRIVAL_P50") for r in pre_days]
                     + [dict(r, phase="WINDOW_PLANNING_RATE") for r in win_days])
    return plan
