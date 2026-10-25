"""Step 5B-2: deterministic, chronological replay simulator (SYNTHETIC inventory; weekly decisions, daily steps).

Inputs: the protected forecast contract v1.0 (decision-time fields only), the verified panel (recorded weekly sales
used as ILLUSTRATIVE demand, static attributes, supplier lead times) and one resolved assumption-set scenario.

Chronology (docs/STEP_5B2_BUSINESS_ASSUMPTIONS_DESIGN.md sections 4-6):
  for each origin T (ascending):
    1. decide for every series using the contract row for origin T and the current simulated state only
    2. then simulate days 1..7 of week T + 1: receive deliveries arriving that day, sell oldest-first,
       expire lots at the end of their last sellable day, carry the rest over (across days and weeks)
Week T + 1 demand is read only through DemandAccess, which refuses any read before the decisions for origin T.

Delivery arrangements (explicit, one order per series per decision; every delivery has a unique id):
  LONG_LIFE_WEEKLY            R >= 7:  one delivery on day 1 + LT
  SHORT_LIFE_RECURRING_DROPS  R < 7:   ceil(7 / R) drops, one every R days from day 1 + LT, inside the 7-day window
  UNSUPPORTED                 LT >= 7: no simulated order; mandatory review
Units are integers. Conservation per series-day: opening + received = sold + expired + closing.
Demand, unmet units and stockouts are ILLUSTRATIVE (recorded sales are not verified unconstrained demand);
simulated unmet units are never observed lost sales. Coverage positions are heuristics, not probabilities.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from dpe.decision.assumptions import case_round, planning_weight, remaining_life_days, watermark

SIMULATOR_VERSION = "1.1"
# 1.0 (run 20261022-225809): coverage measured on planned supply after the order (could not show shortage).
# 1.1: separate pre-order and post-order coverage; lead-time mismatch is a warning; every simulated action is
#      labelled hypothetical and unapproved (no approval events exist in a replay).
DAILY_LABEL = "SIMULATED_DAILY_NOT_A_PREDICTION"
POSITION_NOTE = ("heuristic coverage position: whether supply would cover expected demand at the forecast's p90, "
                 "p50 or p10 weekly rate; not a stockout probability and not a daily demand forecast")
ACTION_STATUS = "HYPOTHETICAL_UNAPPROVED"
DELIVERY_AUTHORISATION = "HYPOTHETICAL_UNAPPROVED_SIMULATED"
COVERAGE_POSITIONS = ("COVERS_P90_RATE", "COVERS_P50_RATE", "COVERS_P10_RATE_ONLY", "BELOW_P10_RATE")
SHORTAGE_POSITIONS = ("COVERS_P10_RATE_ONLY", "BELOW_P10_RATE")
CHRISTMAS_WEEKS = (51, 52)


class ChronologyError(RuntimeError):
    pass


class ConservationError(AssertionError):
    pass


def day_index(week: int, dow: int) -> int:
    return (week - 1) * 7 + dow


def week_of(day: int) -> int:
    return (day - 1) // 7 + 1


def dow_of(day: int) -> int:
    return (day - 1) % 7 + 1


def split_week(total: int, profile) -> list[int]:
    """Integer daily split by largest remainder; the seven values sum exactly to the weekly total."""
    raw = [total * p for p in profile]
    base = [math.floor(x) for x in raw]
    rest = total - sum(base)
    order = sorted(range(7), key=lambda i: (-(raw[i] - base[i]), i))
    for i in order[:rest]:
        base[i] += 1
    return base


class DemandAccess:
    """Illustrative daily demand from recorded weekly sales x scenario multiplier, with a chronology guard."""

    def __init__(self, weekly_sales: dict, multiplier: float, profile):
        self._weekly = weekly_sales
        self.multiplier = multiplier
        self.profile = profile
        self.decided_through_origin: int | None = None
        self.log: list[tuple[int, int]] = []  # (week read, latest decided origin at the time)

    def week_demand(self, series, week: int) -> list[int]:
        if self.decided_through_origin is None or week > self.decided_through_origin + 1:
            raise ChronologyError(f"Demand for week {week} requested before the decision for origin {week - 1}")
        self.log.append((week, self.decided_through_origin))
        total = int(round(self._weekly[(*series, week)] * self.multiplier))
        return split_week(total, self.profile)


@dataclass
class SeriesState:
    lots: list = field(default_factory=list)       # [expiry_day, arrival_day, qty, delivery_id]
    scheduled: dict = field(default_factory=dict)   # arrival_day -> list of delivery dicts (not yet received)
    received: dict = field(default_factory=dict)    # arrival_day -> list of delivery dicts (received)
    seen_deliveries: set = field(default_factory=set)


def _arrangement(R: int, lt: int) -> str:
    if lt >= 7 or R < 1:
        return "UNSUPPORTED"
    return "LONG_LIFE_WEEKLY" if R >= 7 else "SHORT_LIFE_RECURRING_DROPS"


def _drop_days(a: int, R: int, arrangement: str) -> list[tuple[int, int]]:
    """(arrival_day, days covered) for the 7-day coverage window starting at day a."""
    if arrangement == "LONG_LIFE_WEEKLY":
        return [(a, 7)]
    days = list(range(a, a + 7, R))
    return [(d, min(R, a + 7 - d)) for d in days]


def _delivered(ordered: int, values: dict, short_life: bool) -> int:
    q = ordered * values["delivery_fill_rate_pct"] / 100
    if short_life:
        q *= 1 + values["over_delivery_pct_short_life"] / 100
    return int(math.floor(q + 1e-9))


def _project(lots, scheduled, start_day: int, end_day: int, daily: float) -> list:
    """Expected-demand FIFO projection from start_day to end_day - 1 (float units); returns surviving lots."""
    proj = [[e, a, float(q), i] for e, a, q, i in lots]
    for d in range(start_day, end_day):
        for dl in scheduled.get(d, []):
            # The decision-maker expects ORDERED quantities; actual supplier shortfalls are not known in advance.
            proj.append([dl["expiry_day"], d, float(dl["ordered_units"]), dl["delivery_id"]])
        need = daily
        for lot in sorted(proj, key=lambda x: (x[0], x[1])):
            take = min(lot[2], need)
            lot[2] -= take
            need -= take
            if need <= 0:
                break
        proj = [lot for lot in proj if lot[2] > 1e-9 and lot[0] > d]
    return proj


def _existing_surplus(lots, start_day: int, daily: float) -> float:
    """Expected units of current stock that expire unsold under expected demand (no new orders)."""
    proj = [[e, a, float(q)] for e, a, q, _ in lots]
    expired, d = 0.0, start_day
    while proj:
        need = daily
        for lot in sorted(proj, key=lambda x: (x[0], x[1])):
            take = min(lot[2], need)
            lot[2] -= take
            need -= take
            if need <= 0:
                break
        expired += sum(lot[2] for lot in proj if lot[0] == d)
        proj = [lot for lot in proj if lot[2] > 1e-9 and lot[0] > d]
        d += 1
    return expired


def expected_shortfall(lots, deliveries: dict, start: int, end: int, count_from: int, daily: float) -> float:
    """Expected unmet units on days [count_from, end) when demand runs at `daily` units per day from `start`,
    selling oldest expiry first. `deliveries`: arrival_day -> [(expiry_day, units)]. Units arriving on a day are
    sellable from that day only; lots are sellable until the end of their expiry day."""
    proj = [[e, a, float(q)] for e, a, q, _ in lots]
    short = 0.0
    for d in range(start, end):
        for e, q in deliveries.get(d, []):
            proj.append([e, d, float(q)])
        need = daily
        for lot in sorted(proj, key=lambda x: (x[0], x[1])):
            take = min(lot[2], need)
            lot[2] -= take
            need -= take
            if need <= 1e-12:
                break
        if d >= count_from:
            short += max(0.0, need)
        proj = [lot for lot in proj if lot[2] > 1e-9 and lot[0] > d]
    return short


def coverage_position(lots, deliveries: dict, start: int, end: int, count_from: int,
                      p10: float, p50: float, p90: float, tol: float = 1e-6) -> str:
    """Heuristic position: the highest forecast weekly rate (p90, p50, p10) at which supply covers demand on days
    [count_from, end). Not a stockout probability."""
    for rate, label in ((p90, "COVERS_P90_RATE"), (p50, "COVERS_P50_RATE"), (p10, "COVERS_P10_RATE_ONLY")):
        if expected_shortfall(lots, deliveries, start, end, count_from, rate / 7) <= tol:
            return label
    return "BELOW_P10_RATE"


def _band(pct: float, values: dict) -> str:
    b = values["waste_band_pct"]
    return "LOW" if pct < b["LOW_below"] else ("HIGH" if pct > b["HIGH_above"] else "MEDIUM")


def series_attributes(panel: pd.DataFrame, values: dict) -> pd.DataFrame:
    a = panel.drop_duplicates(["Store_ID", "Product_ID"])[
        ["Store_ID", "Product_ID", "Product_Category", "Shelf_Life_Days", "Lead_Time_Days"]].copy()
    a["remaining_life_days"] = [remaining_life_days(s, values["transit_age_days"]) for s in a["Shelf_Life_Days"]]
    a["effective_lead_time_days"] = a["Lead_Time_Days"] + values["lead_time_adjustment_days"]
    a["delivery_arrangement"] = [_arrangement(R, lt) for R, lt in zip(a["remaining_life_days"], a["effective_lead_time_days"])]
    a["drops_per_order"] = [0 if arr == "UNSUPPORTED" else len(_drop_days(1, R, arr))
                            for R, arr in zip(a["remaining_life_days"], a["delivery_arrangement"])]
    a["drop_interval_days"] = [7 if arr == "LONG_LIFE_WEEKLY" else (R if arr != "UNSUPPORTED" else None)
                               for R, arr in zip(a["remaining_life_days"], a["delivery_arrangement"])]
    a["life_lead_time_tight"] = a["effective_lead_time_days"] >= a["remaining_life_days"]
    return a.reset_index(drop=True)


def first_full_origin(contract: pd.DataFrame, series: list) -> int:
    """First H1 origin from which every selected series has AVAILABLE bounds at every later origin."""
    h1 = contract[contract["horizon_weeks"] == 1]
    h1 = h1[h1.set_index(["store_id", "product_id"]).index.isin(series)]
    bad = h1[h1["uncertainty_status"] != "AVAILABLE"]["origin_week"]
    return int(bad.max() + 1) if len(bad) else int(h1["origin_week"].min())


def simulate(contract: pd.DataFrame, panel: pd.DataFrame, values: dict, series: list | None = None,
             origins: list | None = None, trace: bool = False) -> dict:
    """Run one scenario. Returns DataFrames: decisions, deliveries, daily, weekly (+ sales trace if requested)."""
    attrs = series_attributes(panel, values)
    if series is not None:
        attrs = attrs[attrs.set_index(["Store_ID", "Product_ID"]).index.isin(series)].reset_index(drop=True)
    keys = list(zip(attrs["Store_ID"], attrs["Product_ID"]))
    h1 = contract[contract["horizon_weeks"] == 1].set_index(["store_id", "product_id", "origin_week"])
    h4 = contract[contract["horizon_weeks"] == 4].set_index(["store_id", "product_id", "origin_week"])
    if origins is None:
        start = first_full_origin(contract, keys)
        origins = sorted(o for o in contract.loc[contract["horizon_weeks"] == 1, "origin_week"].unique() if o >= start)
    weekly = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"].to_dict()
    demand = DemandAccess(weekly, values["demand_multiplier"], values["daily_demand_profile"])
    attr = attrs.set_index(["Store_ID", "Product_ID"]).to_dict("index")
    states = {k: SeriesState() for k in keys}
    wm = watermark(values)
    decisions, deliveries, daily, trace_rows = [], [], [], []

    def schedule(state, k, order_id, drops, R, short, tag):
        for i, (d, qty, cov, need) in enumerate(drops):
            if qty <= 0:
                continue
            did = f"{order_id}-D{i + 1}"
            if did in state.seen_deliveries:
                raise AssertionError(f"Duplicate delivery id {did}")
            state.seen_deliveries.add(did)
            dl = {"delivery_id": did, "order_id": order_id, "Store_ID": k[0], "Product_ID": k[1],
                  "arrival_day": d, "arrival_week": week_of(d), "arrival_dow": dow_of(d), "days_covered": cov,
                  "need_units_before_rounding": round(float(need), 6), "ordered_units": int(qty), "delivered_units": _delivered(int(qty), values, short),
                  "expiry_day": d + R - 1, "kind": tag, "authorisation": DELIVERY_AUTHORISATION}
            state.scheduled.setdefault(d, []).append(dl)
            deliveries.append(dl)

    # ----- synthetic initial state at the first decision (data <= origin only)
    T0 = origins[0]
    D0 = day_index(T0 + 1, 1)
    for k in keys:
        a = attr[k]
        R, lt, arr = a["remaining_life_days"], a["effective_lead_time_days"], a["delivery_arrangement"]
        avg4 = np.mean([weekly[(*k, w)] for w in range(T0 - 3, T0 + 1)])
        st = states[k]
        if arr == "LONG_LIFE_WEEKLY":
            q = int(round(values["opening_cover_weeks"][a["Product_Category"]] * values["opening_cover_multiplier"] * avg4))
            if q > 0:
                st.lots.append([D0 + R - 1, D0, q, f"{values['scenario_id']}-INIT-{k[0]}-{k[1]}-OPENING"])
        elif arr == "SHORT_LIFE_RECURRING_DROPS":
            first_arrival = D0 + lt
            drops = [(d, case_round(avg4 / 7 * min(R, first_arrival - d), values["case_size_units"][a["Product_Category"]],
                                    values["moq_cases_per_delivery"]), min(R, first_arrival - d), avg4 / 7 * min(R, first_arrival - d))
                     for d in range(D0, first_arrival, R)]
            schedule(st, k, f"{values['scenario_id']}-INIT-{k[0]}-{k[1]}", drops, R, True, "INITIAL_SCHEDULE")

    # ----- chronological loop
    for T in origins:
        D0 = day_index(T + 1, 1)
        for k in keys:
            decisions.append(_decide(k, T, D0, attr[k], h1, h4, states[k], values, schedule))
        demand.decided_through_origin = T
        for k in keys:
            daily += _simulate_week(k, T + 1, attr[k], states[k], demand, trace_rows if trace else None)

    dec = pd.DataFrame(decisions)
    dly = pd.DataFrame(daily)
    for df in (dec, dly):
        df["scenario_id"] = values["scenario_id"]
        df["assumption_set_id"] = values["assumption_set_id"]
        df["simulator_version"] = SIMULATOR_VERSION
        df["watermark"] = wm
    dly["label"] = DAILY_LABEL
    dlv = pd.DataFrame(deliveries).assign(scenario_id=values["scenario_id"], assumption_set_id=values["assumption_set_id"],
                                          watermark=wm)
    wk = weekly_summary(dly)
    out = {"decisions": dec, "deliveries": dlv, "daily": dly, "weekly": wk, "attributes": attrs,
           "demand_log": demand.log, "origins": origins}
    if trace:
        out["sales_trace"] = pd.DataFrame(trace_rows)
    return out


def _decide(k, T, D0, a, h1, h4, st, values, schedule) -> dict:
    cat, R, lt, arr = a["Product_Category"], a["remaining_life_days"], a["effective_lead_time_days"], a["delivery_arrangement"]
    row = h1.loc[(*k, T)] if (*k, T) in h1.index else None
    rec = {"Store_ID": k[0], "Product_ID": k[1], "origin_week": T, "decision_day": D0, "target_week": T + 1,
           "product_category": cat, "remaining_life_days": R, "effective_lead_time_days": lt,
           "delivery_arrangement": arr, "flags": [], "position_note": POSITION_NOTE}
    flags = rec["flags"]
    if row is not None and "HOLIDAY_TARGET_WEEK" in row["risk_flags"]:
        flags.append("HOLIDAY_TARGET_WEEK")
    if row is not None and row["target_week"] in CHRISTMAS_WEEKS:
        flags.append("CHRISTMAS_PERIOD")
    if a["life_lead_time_tight"]:
        flags.append("LIFE_LEAD_TIME_TIGHT")
    recent = [dl for d in range(D0 - 7, D0) for dl in st.received.get(d, [])]
    if any(dl["delivered_units"] < dl["ordered_units"] for dl in recent):
        flags.append("FILL_RATE_SHORTFALL_LAST_WEEK")
    christmas = "CHRISTMAS_PERIOD" in flags
    base = {"order_id": None, "ordered_units": 0, "planned_supply_units": None,
            "pre_order_coverage": None, "post_order_coverage": None, "pre_arrival_days": None,
            "order_addresses_window": None, "planning_weight": None, "weekly_planning_target_units": None,
            "usable_at_arrival_units": None, "existing_stock_surplus_units": None, "existing_stock_waste_band": None,
            "planned_exposure_pct": None, "arrival_day": None, "n_deliveries": 0, "order_basis": None,
            "action_status": "NO_ACTION_PROPOSED", "escalation_required": christmas, "approval_event_id": None}
    if row is None or row["uncertainty_status"] != "AVAILABLE":
        flags.append("UNCERTAINTY_UNAVAILABLE")
        rec.update(base, order_basis="NO_AUTOMATIC_ORDER_UNCERTAINTY_UNAVAILABLE", action_status="REVIEW_REQUIRED_NO_ACTION")
        return _finish(rec)
    if arr == "UNSUPPORTED":
        flags.append("UNSUPPORTED_DELIVERY_ARRANGEMENT")
        rec.update(base, order_basis="NO_AUTOMATIC_ORDER_UNSUPPORTED_ARRANGEMENT", action_status="REVIEW_REQUIRED_NO_ACTION")
        return _finish(rec)
    p10, p50, p90 = float(row["lower_p10_units"]), float(row["median_p50_units"]), float(row["upper_p90_units"])
    w, capped = planning_weight(values["service_target_pct"][cat])
    if capped:
        flags.append("TARGET_ABOVE_P90_CAPPED")
    s_week = p50 + w * (p90 - p50)
    rate = s_week / 7
    a_day = D0 + lt
    # Pre-order coverage: current stock + deliveries committed BEFORE this decision, over the days before the new
    # order can arrive (identifies shortage pressure that this order cannot fix).
    committed = {d: [(dl["expiry_day"], dl["ordered_units"]) for dl in dls] for d, dls in st.scheduled.items()}
    pre = coverage_position(st.lots, committed, D0, a_day, D0, p10, p50, p90)
    survivors = _project(st.lots, st.scheduled, D0, a_day, p50 / 7)
    usable = sum(lot[2] for lot in survivors if lot[0] >= a_day)
    surplus = _existing_surplus(st.lots, D0, p50 / 7)
    case, moq = values["case_size_units"][cat], values["moq_cases_per_delivery"]
    drops = []
    for i, (d, cov) in enumerate(_drop_days(a_day, R, arr)):
        need = rate * cov - (usable if i == 0 else 0.0)
        drops.append((d, case_round(need, case, moq), cov, need))
    # Post-order coverage: the same plus the proposed drops on their scheduled arrival days, over the 7-day window.
    with_order = {d: list(v) for d, v in committed.items()}
    for d, q, _, _ in drops:
        if q > 0:
            with_order.setdefault(d, []).append((d + R - 1, q))
    post = coverage_position(st.lots, with_order, D0, a_day + 7, a_day, p10, p50, p90)
    order_id = f"{values['scenario_id']}-{k[0]}-{k[1]}-O{T}"
    schedule(st, k, order_id, drops, R, arr == "SHORT_LIFE_RECURRING_DROPS", "ORDER")
    ordered = int(sum(q for _, q, _, _ in drops))
    supply = usable + ordered
    h4row = h4.loc[(*k, T)] if (*k, T) in h4.index else None
    if h4row is not None and abs(float(h4row["predicted_units"]) / float(row["predicted_units"]) - 1) * 100 \
            > values["trend_divergence_threshold_pct"]:
        flags.append("TREND_DIVERGENCE")
    rec.update(base, order_id=order_id, ordered_units=ordered, planned_supply_units=round(supply, 3),
               pre_order_coverage=pre, post_order_coverage=post, pre_arrival_days=lt,
               order_addresses_window=post not in SHORTAGE_POSITIONS, planning_weight=round(w, 6),
               weekly_planning_target_units=round(s_week, 3), usable_at_arrival_units=round(usable, 3),
               existing_stock_surplus_units=round(surplus, 3),
               existing_stock_waste_band=_band(100 * surplus / p50, values),
               planned_exposure_pct=round(100 * (supply - p50) / p50, 3), arrival_day=a_day,
               n_deliveries=sum(1 for _, q, _, _ in drops if q > 0), order_basis="PLANNING_WEIGHT_P50_P90_HEURISTIC",
               action_status=ACTION_STATUS)
    if pre in SHORTAGE_POSITIONS:
        flags.append("PRE_ORDER_SHORTAGE")
    if post in SHORTAGE_POSITIONS:
        flags.append("POST_ORDER_SHORTFALL")
    if rec["existing_stock_waste_band"] == "HIGH":
        flags.append("WASTE_HIGH_EXISTING_STOCK")
    return _finish(rec)


def _finish(rec: dict) -> dict:
    rec["flags"] = "|".join(dict.fromkeys(rec["flags"]))
    return rec


def _simulate_week(k, week, a, st, demand: DemandAccess, trace) -> list[dict]:
    rows = []
    dem = demand.week_demand(k, week)
    R = a["remaining_life_days"]
    for dow in range(1, 8):
        d = day_index(week, dow)
        opening = sum(lot[2] for lot in st.lots)
        received = 0
        for dl in st.scheduled.pop(d, []):
            if dl["delivered_units"] > 0:
                st.lots.append([dl["expiry_day"], d, dl["delivered_units"], dl["delivery_id"]])
            received += dl["delivered_units"]
            st.received.setdefault(d, []).append(dl)
        want, sold = dem[dow - 1], 0
        for lot in sorted(st.lots, key=lambda x: (x[0], x[1])):
            if sold >= want:
                break
            if lot[1] > d or lot[0] < d:
                raise AssertionError("Stock sold outside its arrival-expiry window")
            take = min(lot[2], want - sold)
            if take and trace is not None:
                trace.append({"Store_ID": k[0], "Product_ID": k[1], "day": d, "delivery_id": lot[3],
                              "arrival_day": lot[1], "expiry_day": lot[0], "units": take})
            lot[2] -= take
            sold += take
        expired = sum(lot[2] for lot in st.lots if lot[0] == d)
        st.lots = [lot for lot in st.lots if lot[2] > 0 and lot[0] > d]
        closing = sum(lot[2] for lot in st.lots)
        if opening + received != sold + expired + closing or min(opening, received, sold, expired, closing) < 0:
            raise ConservationError(f"Conservation failed for {k} on day {d}")
        rows.append({"Store_ID": k[0], "Product_ID": k[1], "week": week, "dow": dow, "day": d,
                     "sim_opening_units": opening, "sim_received_units": received,
                     "sim_demand_units_illustrative": want, "sim_sold_units": sold,
                     "sim_unmet_units_illustrative": want - sold, "sim_expired_units": expired,
                     "sim_closing_units": closing})
    return rows


def weekly_summary(daily: pd.DataFrame) -> pd.DataFrame:
    g = daily.sort_values("day").groupby(["Store_ID", "Product_ID", "week"])
    w = g.agg(sim_opening_units=("sim_opening_units", "first"), sim_received_units=("sim_received_units", "sum"),
              sim_demand_units_illustrative=("sim_demand_units_illustrative", "sum"),
              sim_sold_units=("sim_sold_units", "sum"),
              sim_unmet_units_illustrative=("sim_unmet_units_illustrative", "sum"),
              sim_expired_units=("sim_expired_units", "sum"), sim_closing_units=("sim_closing_units", "last"),
              sim_days_with_unmet_illustrative=("sim_unmet_units_illustrative", lambda s: int((s > 0).sum()))).reset_index()
    for c in ("scenario_id", "assumption_set_id", "watermark"):
        w[c] = daily[c].iloc[0] if len(daily) else None
    return w


def check_conservation(daily: pd.DataFrame, weekly: pd.DataFrame) -> dict:
    d = daily
    lhs, rhs = d["sim_opening_units"] + d["sim_received_units"], d["sim_sold_units"] + d["sim_expired_units"] + d["sim_closing_units"]
    nxt = d.sort_values("day").groupby(["Store_ID", "Product_ID"])["sim_opening_units"].shift(-1)
    cur = d.sort_values("day")["sim_closing_units"]
    carry_ok = bool(((nxt.isna()) | (nxt == cur)).all())
    w = weekly
    wl = w["sim_opening_units"] + w["sim_received_units"]
    wr = w["sim_sold_units"] + w["sim_expired_units"] + w["sim_closing_units"]
    num = d.select_dtypes("number")
    return {"daily_rows": int(len(d)), "daily_balanced": bool((lhs == rhs).all()),
            "weekly_rows": int(len(w)), "weekly_balanced": bool((wl == wr).all()),
            "closing_equals_next_opening": carry_ok,
            "no_negative_values": bool((num[[c for c in num.columns if c.startswith("sim_")]] >= 0).all().all()),
            "unmet_equals_demand_minus_sold": bool((d["sim_unmet_units_illustrative"]
                                                    == d["sim_demand_units_illustrative"] - d["sim_sold_units"]).all())}
