"""Step 5B-3c: replay simulator v1.2 with selectable inventory planning policies (SYNTHETIC).

The chronology, initial state, delivery handling, daily selling, expiry and conservation checks are those of the
accepted simulator v1.1 (`replay.py`, unchanged and still the code of the protected v1.1 runs). v1.2 only makes the
weekly ordering decision pluggable:

  P0  historical-sales baseline: as-of 4-week average of recorded weekly sales, netting ALL stock on hand regardless
      of expiry (the preregistered expiry-blind rule, design section 7.1); v1.1 review queue
  P1  accepted v1.1 sizing, reproduced exactly by calling replay._decide; v1.1 review queue
  P2  5B-3a time-phased, expiry-aware calculator + 5B-3b recommendations; review queue v1.2 (weekly cases, standing
      supplier-confirmation cases, contract-gate cases for decision points outside the replay window)

All policies share the delivery arrangements and drop days, case/MOQ rounding, missing-bound and unsupported-arrangement
gates (no quantity), Christmas escalation, scenario definitions, initial state and demand path. Each run starts from a
fresh state: nothing is shared between policies or scenarios.

Every decision also carries STANDARDISED risk indicators (`std_*`), computed identically for every policy with the
5B-3a calculator from that policy's own decision-time state and proposed deliveries. They support a like-for-like
comparison that is separate from each policy's own review workload.

Every simulated order, delivery and outcome is hypothetical, unapproved and not executed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dpe.decision import inventory as INV
from dpe.decision import inventory_review as IRQ
from dpe.decision import recommendations as REC
from dpe.decision import replay as RP
from dpe.decision import review_queue as RQ
from dpe.decision.assumptions import case_round, planning_weight, watermark

SIMULATOR_VERSION = "1.2"
POLICIES = ("P0", "P1", "P2")
POLICY_DESCRIPTIONS = {
    "P0": "Historical-sales baseline: 4-week average of recorded sales, expiry-blind netting (preregistered)",
    "P1": "Accepted v1.1 sizing (planning weight between p50 and p90, usable-at-arrival netting)",
    "P2": "Time-phased, expiry-aware sizing (5B-3a) with recommendation classification (5B-3b)",
}
P1_ADDED_COLUMNS = ("policy_id", "simulator_version", "std_pre_delivery_gap_p50_units", "std_pre_delivery_shortage",
                    "std_post_order_shortfall_planning_units", "std_post_order_shortfall",
                    "std_existing_expiry_projection_units", "std_existing_expiry_high")


# ---------------------------------------------------------------------------------------------- helpers
def _common_flags(k, T, D0, a, row, st) -> list[str]:
    """Flags every policy records at the decision (same rules as v1.1)."""
    flags = []
    if row is not None and "HOLIDAY_TARGET_WEEK" in row["risk_flags"]:
        flags.append("HOLIDAY_TARGET_WEEK")
    if row is not None and row["target_week"] in RP.CHRISTMAS_WEEKS:
        flags.append("CHRISTMAS_PERIOD")
    if a["life_lead_time_tight"]:
        flags.append("LIFE_LEAD_TIME_TIGHT")
    if _fill_shortfall_last_week(D0, st):
        flags.append("FILL_RATE_SHORTFALL_LAST_WEEK")
    return flags


def _fill_shortfall_last_week(D0, st) -> bool:
    return any(dl["delivered_units"] < dl["ordered_units"] for d in range(D0 - 7, D0) for dl in st.received.get(d, []))


def _state_inputs(st) -> tuple[list, list]:
    """Decision-time stock (lots) and committed deliveries at their ORDERED quantity (never realised receipts)."""
    lots = [INV.Lot(e, ar, q, i) for e, ar, q, i in st.lots]
    committed = [INV.Delivery(d, dl["expiry_day"], dl["ordered_units"], dl["delivery_id"])
                 for d, dls in sorted(st.scheduled.items()) for dl in dls]
    return lots, committed


def _no_order(rec, flags, basis, flag) -> dict:
    flags.append(flag)
    rec.update(order_id=None, ordered_units=0, arrival_day=None, n_deliveries=0, order_basis=basis,
               action_status="REVIEW_REQUIRED_NO_ACTION", approval_event_id=None)
    return rec


def _base(k, T, D0, a, flags) -> dict:
    return {"Store_ID": k[0], "Product_ID": k[1], "origin_week": T, "decision_day": D0, "target_week": T + 1,
            "product_category": a["Product_Category"], "remaining_life_days": a["remaining_life_days"],
            "effective_lead_time_days": a["effective_lead_time_days"], "delivery_arrangement": a["delivery_arrangement"],
            "flags": flags, "escalation_required": "CHRISTMAS_PERIOD" in flags}


# ---------------------------------------------------------------------------------------------- policies
class P1Policy:
    policy_id = "P1"

    def decide(self, k, T, D0, a, h1, h4, st, values, schedule, ctx):
        return RP._decide(k, T, D0, a, h1, h4, st, values, schedule)


class P0Policy:
    """Preregistered baseline. Weekly quantity = mean recorded sales of weeks T-3..T (known at the decision)."""
    policy_id = "P0"

    def decide(self, k, T, D0, a, h1, h4, st, values, schedule, ctx):
        row = h1.loc[(*k, T)] if (*k, T) in h1.index else None
        flags = _common_flags(k, T, D0, a, row, st)
        rec = _base(k, T, D0, a, flags)
        if row is None or row["uncertainty_status"] != "AVAILABLE":
            return RP._finish(_no_order(rec, flags, "NO_AUTOMATIC_ORDER_UNCERTAINTY_UNAVAILABLE", "UNCERTAINTY_UNAVAILABLE"))
        if a["delivery_arrangement"] == "UNSUPPORTED":
            return RP._finish(_no_order(rec, flags, "NO_AUTOMATIC_ORDER_UNSUPPORTED_ARRANGEMENT",
                                        "UNSUPPORTED_DELIVERY_ARRANGEMENT"))
        weekly_avg = float(np.mean([ctx["weekly_sales"][(*k, w)] for w in range(T - 3, T + 1)]))
        # Preregistered netting (design 7.1): ALL stock on hand at the decision, ignoring expiry and ignoring the demand
        # that will use it before the new order arrives. Deliveries already scheduled are not netted.
        on_hand = sum(lot[2] for lot in st.lots)
        credit = float(on_hand)
        R, lt, arr = a["remaining_life_days"], a["effective_lead_time_days"], a["delivery_arrangement"]
        cat = a["Product_Category"]
        a_day = D0 + lt
        drops = []
        for d, cov in RP._drop_days(a_day, R, arr):
            need = weekly_avg / 7 * cov
            used = min(credit, need)
            credit -= used
            drops.append((d, case_round(need - used, values["case_size_units"][cat], values["moq_cases_per_delivery"]),
                          cov, need - used))
        order_id = f"{values['scenario_id']}-{k[0]}-{k[1]}-O{T}"
        schedule(st, k, order_id, drops, R, arr == "SHORT_LIFE_RECURRING_DROPS", "ORDER")
        rec.update(order_id=order_id, ordered_units=int(sum(q for _, q, _, _ in drops)), arrival_day=a_day,
                   n_deliveries=sum(1 for _, q, _, _ in drops if q > 0),
                   order_basis="P0_HISTORICAL_4_WEEK_AVERAGE_EXPIRY_BLIND", baseline_weekly_units=round(weekly_avg, 3),
                   expiry_blind_credit_units=round(on_hand, 3),
                   action_status=RP.ACTION_STATUS, approval_event_id=None)
        return RP._finish(rec)


class P2Policy:
    """Time-phased calculator + recommendation layer. Orders are scheduled only for eligible recommendations."""
    policy_id = "P2"

    def decide(self, k, T, D0, a, h1, h4, st, values, schedule, ctx):
        row = h1.loc[(*k, T)] if (*k, T) in h1.index else None
        cat = a["Product_Category"]
        gate = ctx["contract_gates"].get((*k, T), {"christmas": False, "missing": True})
        status = "AVAILABLE" if row is not None and row["uncertainty_status"] == "AVAILABLE" and not gate["missing"] \
            else "UNAVAILABLE_ANY_HORIZON"
        h4row = h4.loc[(*k, T)] if (*k, T) in h4.index else None
        c = REC.context_from_values(
            values, store_id=int(k[0]), product_id=int(k[1]), product_category=cat, origin_week=int(T),
            decision_day=D0, shelf_life_days=int(a["Shelf_Life_Days"]), lead_time_days=int(a["Lead_Time_Days"]),
            p10=None if row is None else row["lower_p10_units"], p50=None if row is None else row["median_p50_units"],
            p90=None if row is None else row["upper_p90_units"], uncertainty_status=status,
            risk_flags="" if row is None else row["risk_flags"],
            h1_point=None if row is None else float(row["predicted_units"]),
            h4_point=None if h4row is None else float(h4row["predicted_units"]),
            fill_shortfall_last_week=_fill_shortfall_last_week(D0, st),
            assumption_content_sha256=ctx["assumption_sha"] or values.get("assumption_content_sha256", ""),
            forecast_contract_run=ctx["contract_run"],
            christmas_any_horizon=gate["christmas"])
        lots, committed = _state_inputs(st)
        plan = REC.plan_for(c, lots, committed)
        r = REC.recommend(c, plan)
        REC.assert_safe(r)
        ctx["recommendations"].append(r)
        flags = list(r["reason_codes"])
        rec = _base(k, T, D0, a, flags)
        rec["escalation_required"] = r["escalation_required"]
        rec.update(recommendation_id=r["recommendation_id"], primary_category=r["primary_category"],
                   case_type=r["case_type"], supplier_arrangement_status=r["supplier_arrangement"]["status"],
                   pre_delivery_position=plan.pre_delivery_position, post_order_position=plan.post_order_position,
                   residual_shortfall_units=None if plan.residual_shortfall_units is None else round(plan.residual_shortfall_units, 3),
                   existing_stock_expected_expiry_units=None if plan.existing_stock_expected_expiry_units is None
                   else round(plan.existing_stock_expected_expiry_units, 3),
                   rounding_excess_units=round(plan.rounding_excess_units, 3))
        if not r["proposal_eligible"]:
            rec.update(order_id=None, ordered_units=0, arrival_day=plan.arrival_day, n_deliveries=0,
                       order_basis="NO_AUTOMATIC_ORDER_" + ("UNSUPPORTED_ARRANGEMENT" if plan.status ==
                                                            "NOT_SIZED_UNSUPPORTED_ARRANGEMENT" else "UNCERTAINTY_UNAVAILABLE"),
                       action_status="REVIEW_REQUIRED_NO_ACTION", approval_event_id=None)
            return RP._finish(rec)
        order_id = f"{values['scenario_id']}-{k[0]}-{k[1]}-O{T}"
        drops = [(d.arrival_day, d.ordered_units, d.days_covered, d.net_need_units) for d in plan.drops]
        schedule(st, k, order_id, drops, a["remaining_life_days"], a["delivery_arrangement"] == "SHORT_LIFE_RECURRING_DROPS",
                 "ORDER")
        rec.update(order_id=order_id, ordered_units=plan.ordered_units, arrival_day=plan.arrival_day,
                   n_deliveries=sum(1 for d in plan.drops if d.ordered_units > 0),
                   order_basis="P2_TIME_PHASED_EXPIRY_AWARE", action_status=RP.ACTION_STATUS, approval_event_id=None)
        return RP._finish(rec)


POLICY_CLASSES = {"P0": P0Policy, "P1": P1Policy, "P2": P2Policy}


def get_policy(policy_id: str):
    if policy_id not in POLICY_CLASSES:
        raise ValueError(f"Unknown policy {policy_id!r}; expected one of {POLICIES}")
    return POLICY_CLASSES[policy_id]()


# ----------------------------------------------------------------------------------- standardised indicators
def standard_indicators(row, a, values, D0, lots, committed, new_deliveries) -> dict:
    """Common risk indicators, identical for every policy: the 5B-3a calculator applied to the policy's own
    decision-time state and its proposed deliveries. None when bounds are unavailable or nothing can be sized."""
    empty = {"std_pre_delivery_gap_p50_units": None, "std_pre_delivery_shortage": None,
             "std_post_order_shortfall_planning_units": None, "std_post_order_shortfall": None,
             "std_existing_expiry_projection_units": None, "std_existing_expiry_high": None}
    if row is None or row["uncertainty_status"] != "AVAILABLE" or a["delivery_arrangement"] == "UNSUPPORTED":
        return empty
    p10, p50, p90 = float(row["lower_p10_units"]), float(row["median_p50_units"]), float(row["upper_p90_units"])
    w, _ = planning_weight(values["service_target_pct"][a["Product_Category"]])
    s_week = p50 + w * (p90 - p50)
    a_day = D0 + a["effective_lead_time_days"]
    pre = [x for x in committed if x.arrival_day < a_day]
    win = [x for x in committed if x.arrival_day >= a_day] + list(new_deliveries)
    gaps, _ = INV.pre_delivery_gap(lots, pre, D0, a_day, p10, p50, p90)
    at_a, _, _ = INV.project_stock(lots, pre, D0, a_day, p50)
    _, _, residual = INV.post_order_coverage(at_a, win, a_day, p10, p50, p90, s_week)
    expiry = INV.unsold_at_expiry(at_a, a_day, s_week) if at_a else 0.0
    return {"std_pre_delivery_gap_p50_units": round(gaps["p50"], 3), "std_pre_delivery_shortage": gaps["p50"] > INV.TOL,
            "std_post_order_shortfall_planning_units": round(residual, 3), "std_post_order_shortfall": residual > INV.TOL,
            "std_existing_expiry_projection_units": round(expiry, 3),
            "std_existing_expiry_high": REC.expiry_share_is_high(
                expiry, p50, values.get("expiry_escalation_pct_of_p50", values["waste_band_pct"]["HIGH_above"]))}


# ---------------------------------------------------------------------------------------------- simulate
def _contract_gates(contract) -> dict:
    c = contract.assign(_x=contract["target_week"].isin(RP.CHRISTMAS_WEEKS), _m=contract["uncertainty_status"] != "AVAILABLE")
    g = c.groupby(["store_id", "product_id", "origin_week"]).agg(christmas=("_x", "any"), missing=("_m", "any"))
    return {(int(s), int(p), int(o)): {"christmas": bool(x), "missing": bool(m)}
            for (s, p, o), x, m in zip(g.index, g["christmas"], g["missing"])}


def simulate(contract: pd.DataFrame, panel: pd.DataFrame, values: dict, policy: str, series: list | None = None,
             origins: list | None = None, trace: bool = False, assumption_sha: str = "", contract_run: str = "") -> dict:
    """Run one policy in one scenario from a fresh synthetic state (v1.1 chronology and conventions)."""
    pol = get_policy(policy)
    attrs = RP.series_attributes(panel, values)
    if series is not None:
        attrs = attrs[attrs.set_index(["Store_ID", "Product_ID"]).index.isin(series)].reset_index(drop=True)
    keys = list(zip(attrs["Store_ID"], attrs["Product_ID"]))
    h1 = contract[contract["horizon_weeks"] == 1].set_index(["store_id", "product_id", "origin_week"])
    h4 = contract[contract["horizon_weeks"] == 4].set_index(["store_id", "product_id", "origin_week"])
    if origins is None:
        start = RP.first_full_origin(contract, keys)
        origins = sorted(o for o in contract.loc[contract["horizon_weeks"] == 1, "origin_week"].unique() if o >= start)
    weekly = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"].to_dict()
    demand = RP.DemandAccess(weekly, values["demand_multiplier"], values["daily_demand_profile"])
    attr = attrs.set_index(["Store_ID", "Product_ID"]).to_dict("index")
    states = {k: RP.SeriesState() for k in keys}
    wm = watermark(values)
    ctx = {"weekly_sales": _AsOfSales(weekly, demand), "contract_gates": _contract_gates(contract), "recommendations": [],
           "assumption_sha": assumption_sha, "contract_run": contract_run}
    decisions, deliveries, daily, trace_rows = [], [], [], []

    def schedule(state, k, order_id, drops, R, short, tag):  # identical to replay.simulate
        for i, (d, qty, cov, need) in enumerate(drops):
            if qty <= 0:
                continue
            did = f"{order_id}-D{i + 1}"
            if did in state.seen_deliveries:
                raise AssertionError(f"Duplicate delivery id {did}")
            state.seen_deliveries.add(did)
            dl = {"delivery_id": did, "order_id": order_id, "Store_ID": k[0], "Product_ID": k[1],
                  "arrival_day": d, "arrival_week": RP.week_of(d), "arrival_dow": RP.dow_of(d), "days_covered": cov,
                  "need_units_before_rounding": round(float(need), 6), "ordered_units": int(qty),
                  "delivered_units": RP._delivered(int(qty), values, short),
                  "expiry_day": d + R - 1, "kind": tag, "authorisation": RP.DELIVERY_AUTHORISATION}
            state.scheduled.setdefault(d, []).append(dl)
            deliveries.append(dl)

    # ----- synthetic initial state at the first decision (identical to replay.simulate; data <= origin only)
    T0 = origins[0]
    D0 = RP.day_index(T0 + 1, 1)
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

    # ----- chronological loop: decide for every series, then simulate the target week
    for T in origins:
        D0 = RP.day_index(T + 1, 1)
        ctx["weekly_sales"].decided_origin = T
        for k in keys:
            st = states[k]
            lots, committed = _state_inputs(st)
            n_before = len(deliveries)
            rec = pol.decide(k, T, D0, attr[k], h1, h4, st, values, schedule, ctx)
            new = [INV.Delivery(dl["arrival_day"], dl["expiry_day"], dl["ordered_units"], dl["delivery_id"])
                   for dl in deliveries[n_before:]]
            row = h1.loc[(*k, T)] if (*k, T) in h1.index else None
            rec.update(standard_indicators(row, attr[k], values, D0, lots, committed, new))
            decisions.append(rec)
        demand.decided_through_origin = T
        for k in keys:
            daily += RP._simulate_week(k, T + 1, attr[k], states[k], demand, trace_rows if trace else None)

    dec = pd.DataFrame(decisions)
    dly = pd.DataFrame(daily)
    for df in (dec, dly):
        df["scenario_id"] = values["scenario_id"]
        df["assumption_set_id"] = values["assumption_set_id"]
        df["simulator_version"] = SIMULATOR_VERSION
        df["policy_id"] = policy
        df["watermark"] = wm
    dly["label"] = RP.DAILY_LABEL
    dlv = pd.DataFrame(deliveries).assign(scenario_id=values["scenario_id"], assumption_set_id=values["assumption_set_id"],
                                          watermark=wm, policy_id=policy)
    wk = RP.weekly_summary(dly)
    out = {"policy_id": policy, "decisions": dec, "deliveries": dlv, "daily": dly, "weekly": wk, "attributes": attrs,
           "demand_log": demand.log, "origins": origins, "recommendations": ctx["recommendations"],
           "sales_reads": ctx["weekly_sales"].log}
    if trace:
        out["sales_trace"] = pd.DataFrame(trace_rows)
    return out


class _AsOfSales:
    """Recorded weekly sales for the P0 baseline, readable only up to the current origin week (known at decision)."""

    def __init__(self, weekly: dict, demand):
        self._weekly = weekly
        self.decided_origin: int | None = None
        self.log: list[tuple[int, int]] = []

    def __getitem__(self, key):
        week = key[2]
        if self.decided_origin is None or week > self.decided_origin:
            raise RP.ChronologyError(f"Recorded sales for week {week} requested at origin {self.decided_origin}")
        self.log.append((week, self.decided_origin))
        return self._weekly[key]


# ---------------------------------------------------------------------------------------------- review queues
def unit_share(panel) -> dict:
    share = panel.groupby(["Store_ID", "Product_ID"])["Units_Sold"].sum()
    share = share / share.groupby(level=0).transform("sum")
    return {(int(s), int(p), o): float(v) for (s, p), v in share.items() for o in range(1, 53)}


def review(result: dict, contract: pd.DataFrame, values: dict, share: dict | None = None,
           series: list | None = None) -> dict:
    """Policy-specific review workload: v1.1 queue for P0 and P1, queue v1.2 for P2."""
    c = contract if series is None else contract[contract.set_index(["store_id", "product_id"]).index.isin(series)]
    if result["policy_id"] in ("P0", "P1"):
        cols = [col for col in result["decisions"].columns if col not in P1_ADDED_COLUMNS]
        cases = RQ.build_cases(c, result["decisions"][cols], values, share)
        s = RQ.case_summary(cases)
        return {"queue_version": RQ.QUEUE_VERSION, "cases": cases, "standing": [],
                "summary": {"weekly_cases": s["cases"], "weekly_by_type": dict(sorted(s["by_type"].items())),
                            "standing_supplier_confirmation_cases": 0, "duplicate_weekly_cases": s["duplicate_cases"]}}
    recs = result["recommendations"]
    simulated = {(r["store_id"], r["product_id"], r["origin_week"]) for r in recs}
    weekly = IRQ.weekly_cases(recs) + IRQ.contract_gate_cases(c, simulated, values["scenario_id"])
    standing = IRQ.standing_cases(recs)
    return {"queue_version": IRQ.QUEUE_VERSION, "cases": weekly, "standing": standing,
            "summary": IRQ.queue_summary(weekly, standing)}


def standard_risk_summary(result: dict) -> dict:
    """Standardised common risk indicators (identical rules for every policy)."""
    d = result["decisions"]
    known = d["std_pre_delivery_shortage"].notna()
    return {"decisions_assessed": int(known.sum()),
            "pre_delivery_shortage": int(d.loc[known, "std_pre_delivery_shortage"].astype(bool).sum()),
            "post_order_shortfall": int(d.loc[known, "std_post_order_shortfall"].astype(bool).sum()),
            "existing_expiry_high": int(d.loc[known, "std_existing_expiry_high"].astype(bool).sum())}


def outcome_summary(result: dict) -> dict:
    w, d = result["weekly"], result["decisions"]
    return {"ordered_units": int(d["ordered_units"].sum()), "received_units": int(w["sim_received_units"].sum()),
            "unmet_units_illustrative": int(w["sim_unmet_units_illustrative"].sum()),
            "expired_units": int(w["sim_expired_units"].sum()),
            "conservation": RP.check_conservation(result["daily"], result["weekly"])}

