"""Phase 2: pricing replay simulator v1.3 (SYNTHETIC; SIMULATED RESEARCH — NOT VALIDATED FOR LIVE USE).

A new version beside the protected simulators; `replay.py` (v1.1) and `replay_v12.py` (v1.2) are imported, never
edited. v1.3 runs the v1.2 chronology with the v1.2 ordering policy and adds a pricing step:

  for each origin T:
    1 ORDER    pricing off: the policy decides (`replay_v12` policy classes, unchanged)
               pricing on:  the order and its deliveries are copied from the pricing-off pass for the same scenario,
                            so pricing can never change an ordering decision (assumption set v7)
    2 PRICE    pricing on: `dynamic_pricing.decide` on the decision-time state (belief = v6 decision weights)
    3 SIMULATE days of week T + 1 with the protected v1.1 selling step (`replay._simulate_week`: deliveries,
               oldest-first selling, expiry, conservation). On markdown days, illustrative demand is
               floor(units x (1 + true response x points / 100) + 0.5); the TRUE response is a run parameter that the
               pricing step never sees.
Revenue is booked at the price in force each day: the estimated reference price of the origin that decided the week,
or the selected markdown price on its window days. Markdowns are SIMULATED, HYPOTHETICAL_UNAPPROVED, NOT_EXECUTED.

With pricing off, v1.3 must reproduce the protected P2 outputs exactly (run 20261023-131711_policy_comparison).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from dpe.decision import dynamic_pricing as DP
from dpe.decision import inventory as INV
from dpe.decision import replay as RP
from dpe.decision import replay_v12 as V
from dpe.decision.assumptions import case_round, watermark

SIMULATOR_VERSION = "1.3"
DELIVERY_EXTRA_COLUMNS = ("scenario_id", "assumption_set_id", "watermark", "policy_id")


class PricedDemand:
    """Wraps the protected DemandAccess (chronology guard included) and applies the TRUE response on markdown days."""

    def __init__(self, inner: RP.DemandAccess, response_pct_per_point: float):
        self.inner = inner
        self.response = response_pct_per_point
        self.markdown_days: dict = {}  # (store, product) -> {day: markdown points}

    @property
    def decided_through_origin(self):
        return self.inner.decided_through_origin

    @decided_through_origin.setter
    def decided_through_origin(self, value):
        self.inner.decided_through_origin = value

    @property
    def log(self):
        return self.inner.log

    def week_demand(self, series, week: int) -> list[int]:
        base = self.inner.week_demand(series, week)
        days = self.markdown_days.get(tuple(series))
        if not days:
            return base
        out = []
        for dow, units in enumerate(base, 1):
            pts = days.get(RP.day_index(week, dow), 0)
            out.append(int(math.floor(units * (1 + self.response * pts / 100) + 0.5)) if pts else units)
        return out


def simulate(contract: pd.DataFrame, panel: pd.DataFrame, values: dict, params: dict | None = None,
             policy: str = "P2", pricing: bool = False, true_response: str | None = None, fixed: dict | None = None,
             series: list | None = None, origins: list | None = None, assumption_sha: str = "",
             contract_run: str = "") -> dict:
    """One run from a fresh state. pricing=False reproduces replay_v12.simulate; pricing=True needs `fixed` (the
    pricing-off result for the same scenario and series) and a `true_response` key of the v6 response scenarios."""
    if pricing and (fixed is None or true_response is None or params is None):
        raise ValueError("pricing runs need the pricing-off result (fixed orders), a true response and parameters")
    pol = V.get_policy(policy)
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
    inner = RP.DemandAccess(weekly, values["demand_multiplier"], values["daily_demand_profile"])
    response = 0.0 if not pricing else float(params["demand_response_scenarios_pct_per_point"][true_response])
    demand = PricedDemand(inner, response)
    attr = attrs.set_index(["Store_ID", "Product_ID"]).to_dict("index")
    states = {k: RP.SeriesState() for k in keys}
    wm = watermark(values)
    ctx = {"weekly_sales": V._AsOfSales(weekly, inner), "contract_gates": V._contract_gates(contract),
           "recommendations": [], "assumption_sha": assumption_sha, "contract_run": contract_run}
    decisions, deliveries, daily = [], [], []
    pricing_log, history = [], {k: [] for k in keys}
    if pricing:
        fixed_dec = {(r["Store_ID"], r["Product_ID"], r["origin_week"]): r
                     for r in fixed["decisions"].to_dict("records")}
        fdl = fixed["deliveries"].drop(columns=[c for c in DELIVERY_EXTRA_COLUMNS if c in fixed["deliveries"]])
        fixed_dlv = {}
        for r in fdl[fdl["kind"] == "ORDER"].to_dict("records"):
            fixed_dlv.setdefault(r["order_id"], []).append(r)
        xmas = V._contract_gates(contract)
        rec_disc = panel.set_index(["Store_ID", "Product_ID", "week_index"])[["Price", "Discount_Percent"]].to_dict("index")
        gm, mn = params["gross_margin_pct"], params["min_margin_pct"]

    def schedule(state, k, order_id, drops, R, short, tag):  # identical to replay_v12.simulate
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

    def schedule_fixed(state, order_id):
        """Copy the pricing-off pass's deliveries for this order unchanged (ids, quantities, realised receipts)."""
        for r in fixed_dlv.get(order_id, []):
            if r["delivery_id"] in state.seen_deliveries:
                raise AssertionError(f"Duplicate delivery id {r['delivery_id']}")
            state.seen_deliveries.add(r["delivery_id"])
            dl = dict(r)
            state.scheduled.setdefault(dl["arrival_day"], []).append(dl)
            deliveries.append(dl)

    # ----- synthetic initial state at the first decision (identical to replay_v12.simulate)
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

    # ----- chronological loop: order, then price, for every series; then simulate the target week
    for T in origins:
        D0 = RP.day_index(T + 1, 1)
        ctx["weekly_sales"].decided_origin = T
        for k in keys:
            st = states[k]
            lots, committed = V._state_inputs(st)
            n_before = len(deliveries)
            if pricing:
                rec = dict(fixed_dec[(*k, T)])
                if isinstance(rec.get("order_id"), str):
                    schedule_fixed(st, rec["order_id"])
            else:
                rec = pol.decide(k, T, D0, attr[k], h1, h4, st, values, schedule, ctx)
            new = [INV.Delivery(dl["arrival_day"], dl["expiry_day"], dl["ordered_units"], dl["delivery_id"])
                   for dl in deliveries[n_before:]]
            row = h1.loc[(*k, T)] if (*k, T) in h1.index else None
            std = V.standard_indicators(row, attr[k], values, D0, lots, committed, new)
            if not pricing:
                rec.update(std)
            decisions.append(rec)
            if pricing:
                h4row = h4.loc[(*k, T)] if (*k, T) in h4.index else None
                rp = rec_disc.get((*k, T), {})
                state = DP.assess_state(k[1], D0, attr[k]["delivery_arrangement"], row, h4row, std,
                                        DP.earliest_batch_last_day(st.received, D0),
                                        xmas.get((*k, T), {"christmas": False})["christmas"],
                                        rp.get("Discount_Percent"), params)
                cat = attr[k]["Product_Category"]
                ref = None if row is None else float(row["reference_price_asof"])
                promo = (not DP._missing(rp.get("Discount_Percent"))) and float(rp.get("Discount_Percent")) > 0
                p = DP.decide(k, T, D0, state, row, ref, gm.get(cat), mn.get(cat), rp.get("Price"), promo, history[k],
                              isinstance(rec.get("case_type"), str), params)
                p.update(std_existing_expiry_projection_units=std["std_existing_expiry_projection_units"],
                         product_category=cat, true_response=true_response)
                pricing_log.append(p)
                if p["outcome"] == DP.SELECTED:
                    history[k].append(p)
                    days = demand.markdown_days.setdefault(k, {})
                    for d in range(p["window_start_day"], p["window_end_day"] + 1):
                        days[d] = p["markdown_pct"]
        demand.decided_through_origin = T
        for k in keys:
            daily += RP._simulate_week(k, T + 1, attr[k], states[k], demand, None)

    dec = pd.DataFrame(decisions)
    dly = pd.DataFrame(daily)
    tag = values["scenario_id"]
    if not pricing:
        for df in (dec, dly):
            df["scenario_id"] = tag
            df["assumption_set_id"] = values["assumption_set_id"]
            df["simulator_version"] = V.SIMULATOR_VERSION  # pricing off reproduces v1.2 exactly, labels included
            df["policy_id"] = policy
            df["watermark"] = wm
        dly["label"] = RP.DAILY_LABEL
        dlv = pd.DataFrame(deliveries).assign(scenario_id=tag, assumption_set_id=values["assumption_set_id"],
                                              watermark=wm, policy_id=policy)
    else:
        dly = dly.assign(scenario_id=tag, assumption_set_id=values["assumption_set_id"], simulator_version=V.SIMULATOR_VERSION,
                         policy_id=policy, watermark=wm, label=RP.DAILY_LABEL)
        dlv = pd.DataFrame(deliveries).assign(scenario_id=tag, assumption_set_id=values["assumption_set_id"],
                                              watermark=wm, policy_id=policy)
    wk = RP.weekly_summary(dly)
    out = {"policy_id": policy, "decisions": dec, "deliveries": dlv, "daily": dly, "weekly": wk, "attributes": attrs,
           "demand_log": demand.log, "origins": origins, "recommendations": ctx["recommendations"],
           "sales_reads": ctx["weekly_sales"].log, "pricing_simulator_version": SIMULATOR_VERSION,
           "pricing": pricing, "true_response": true_response,
           "pricing_log": pd.DataFrame(pricing_log)}
    return out


def price_days(result: dict, contract: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Daily rows with the price in force, the markdown points and revenue (sold units x price)."""
    d = result["daily"][["Store_ID", "Product_ID", "week", "dow", "day", "sim_opening_units", "sim_received_units",
                         "sim_demand_units_illustrative", "sim_sold_units", "sim_unmet_units_illustrative",
                         "sim_expired_units", "sim_closing_units"]].copy()
    h1 = contract[contract["horizon_weeks"] == 1][["store_id", "product_id", "origin_week", "reference_price_asof"]].rename(
        columns={"store_id": "Store_ID", "product_id": "Product_ID"})
    d["origin_week"] = d["week"] - 1
    d = d.merge(h1, on=["Store_ID", "Product_ID", "origin_week"], how="left").rename(
        columns={"reference_price_asof": "reference_price"})
    d["markdown_pct"] = 0
    d["price"] = d["reference_price"]
    log = result.get("pricing_log")
    if log is not None and len(log):
        ev = log[log["outcome"] == DP.SELECTED]
        rows = [(r.Store_ID, r.Product_ID, day, r.markdown_pct, r.markdown_price, r.event_id)
                for r in ev.itertuples() for day in range(int(r.window_start_day), int(r.window_end_day) + 1)]
        if rows:
            m = pd.DataFrame(rows, columns=["Store_ID", "Product_ID", "day", "_pct", "_price", "event_id"])
            d = d.merge(m, on=["Store_ID", "Product_ID", "day"], how="left")
            hit = d["_pct"].notna()
            d.loc[hit, "markdown_pct"] = d.loc[hit, "_pct"].astype(int)
            d.loc[hit, "price"] = d.loc[hit, "_price"]
            d = d.drop(columns=["_pct", "_price"])
    if "event_id" not in d:
        d["event_id"] = None
    cat = result["attributes"].set_index(["Store_ID", "Product_ID"])["Product_Category"]
    gm = params["gross_margin_pct"]
    d["unit_cost"] = d["reference_price"] * (1 - d.set_index(["Store_ID", "Product_ID"]).index.map(cat).map(gm).astype(float) / 100)
    d["revenue"] = d["sim_sold_units"] * d["price"]
    d["received_cost"] = d["sim_received_units"] * d["unit_cost"]
    d["expired_cost"] = d["sim_expired_units"] * d["unit_cost"]
    d["disposal_cost"] = d["expired_cost"] * params["expiry_disposal_cost_pct_of_unit_cost"] / 100
    d["gross_profit"] = d["revenue"] - d["received_cost"] - d["disposal_cost"]
    return d.drop(columns="origin_week")
