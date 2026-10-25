"""Step 5B-2: run the replay simulator for scenarios SC1-SC3, build review cases, sensitivity checks and write a new
run folder. Reads the protected forecast contract and verified panel; writes nothing else. All simulated values are
SYNTHETIC and illustrative; no inventory, waste-risk or pricing recommendation engine is implemented here."""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import replay as RP
from dpe.decision import review_queue as RQ

SCENARIOS = ("SC1", "SC2", "SC3")
SENSITIVITY = (  # one at a time, on SC1
    ("service_target_pct", "all=50", {"service_target_pct": dict.fromkeys(A.CATEGORIES, 50)}),
    ("service_target_pct", "all=70", {"service_target_pct": dict.fromkeys(A.CATEGORIES, 70)}),
    ("service_target_pct", "all=90", {"service_target_pct": dict.fromkeys(A.CATEGORIES, 90)}),
    ("case_size_units", "x0.5", "case_half"),
    ("case_size_units", "x2", "case_double"),
    ("moq_cases_per_delivery", "4", {"moq_cases_per_delivery": 4}),
    ("delivery_fill_rate_pct", "60", {"delivery_fill_rate_pct": 60}),
    ("demand_multiplier", "0.85", {"demand_multiplier": 0.85}),
    ("demand_multiplier", "1.15", {"demand_multiplier": 1.15}),
    ("transit_age_days", "0", {"transit_age_days": 0}),
    ("transit_age_days", "2", {"transit_age_days": 2}),
    ("opening_cover_multiplier", "3.0", {"opening_cover_multiplier": 3.0}),
    ("daily_demand_profile", "weekend-heavy", {"daily_demand_profile": [0.12, 0.12, 0.13, 0.14, 0.16, 0.18, 0.15]}),
    ("life_lead_time_tight_is_material_trigger", "true (v1.0 rule)", {"life_lead_time_tight_is_material_trigger": True}),
)


def _override(values: dict, change) -> dict:
    v = copy.deepcopy(values)
    if change == "case_half":
        v["case_size_units"] = {k: max(1, x // 2) for k, x in v["case_size_units"].items()}
    elif change == "case_double":
        v["case_size_units"] = {k: x * 2 for k, x in v["case_size_units"].items()}
    else:
        v.update(change)
    return v


def kpis(res: dict, cases: pd.DataFrame) -> dict:
    w, d = res["weekly"], res["decisions"]
    s = RQ.case_summary(cases)
    dem = int(w["sim_demand_units_illustrative"].sum())
    rec = int(w["sim_received_units"].sum())
    return {"series_weeks": int(len(w)), "decisions": int(len(d)), "ordered_units": int(d["ordered_units"].sum()),
            "received_units": rec, "demand_units_illustrative": dem, "sold_units": int(w["sim_sold_units"].sum()),
            "unmet_units_illustrative": int(w["sim_unmet_units_illustrative"].sum()),
            "expired_units": int(w["sim_expired_units"].sum()), "closing_units_final_week": int(
                w[w["week"] == w["week"].max()]["sim_closing_units"].sum()),
            "illustrative_sell_through_pct": round(100 * w["sim_sold_units"].sum() / dem, 3) if dem else None,
            "expired_share_of_received_pct": round(100 * w["sim_expired_units"].sum() / rec, 3) if rec else None,
            "series_weeks_with_unmet_illustrative": int((w["sim_unmet_units_illustrative"] > 0).sum()),
            "pre_order_shortage": int(d["flags"].str.contains("PRE_ORDER_SHORTAGE").sum()),
            "post_order_shortfall": int(d["flags"].str.contains("POST_ORDER_SHORTFALL").sum()),
            "pre_order_shortage_addressed_by_order": int((d["flags"].str.contains("PRE_ORDER_SHORTAGE")
                                                          & (d["order_addresses_window"] == True)).sum()),  # noqa: E712
            "lead_time_warning_only_no_case": s["lead_time_warning_only_no_case"],
            "proposed_actions_hypothetical_unapproved": int((d["action_status"] == RP.ACTION_STATUS).sum()),
            "actions_with_approval_event": int(d["approval_event_id"].notna().sum()),
            "waste_high_existing_stock": int((d["existing_stock_waste_band"] == "HIGH").sum()),
            "cases_total": s["cases"], **{f"cases_{k}": v for k, v in s["by_type"].items()}}


def run_scenarios(contract, panel, doc, series=None, scenarios=SCENARIOS, trace=False) -> dict:
    share = panel.groupby(["Store_ID", "Product_ID"])["Units_Sold"].sum()
    share = share / share.groupby(level=0).transform("sum")
    unit_share = {(int(s), int(p), o): float(v) for (s, p), v in share.items() for o in range(1, 53)}
    out = {}
    for sc in scenarios:
        v = A.resolve(doc, sc)
        res = RP.simulate(contract, panel, v, series=series, trace=trace)
        c = contract if series is None else contract[contract.set_index(["store_id", "product_id"]).index.isin(series)]
        cases = RQ.build_cases(c, res["decisions"], v, unit_share)
        out[sc] = {"values": v, "result": res, "cases": cases,
                   "conservation": RP.check_conservation(res["daily"], res["weekly"]), "kpis": kpis(res, cases)}
    return out


def sensitivity(contract, panel, doc, series=None) -> pd.DataFrame:
    base_v = A.resolve(doc, "SC1")
    base = RP.simulate(contract, panel, base_v, series=series)
    c = contract if series is None else contract[contract.set_index(["store_id", "product_id"]).index.isin(series)]
    base_cases = RQ.build_cases(c, base["decisions"], base_v)
    rows = [{"parameter": "BASE", "setting": "SC1", **kpis(base, base_cases), "decisions_with_changed_order_pct": 0.0}]
    for param, label, change in SENSITIVITY:
        v = _override(base_v, change)
        res = RP.simulate(contract, panel, v, series=series)
        cases = RQ.build_cases(c, res["decisions"], v)
        changed = (res["decisions"]["ordered_units"].to_numpy() != base["decisions"]["ordered_units"].to_numpy()).mean()
        rows.append({"parameter": param, "setting": label, **kpis(res, cases),
                     "decisions_with_changed_order_pct": round(100 * float(changed), 3)})
    return pd.DataFrame(rows)


def first_decision_orders(contract, panel, values, series=None) -> pd.Series:
    """Orders at the first decision only (no feedback), for the directional checks."""
    res = RP.simulate(contract, panel, values, series=series)
    o = res["origins"][0]
    d = res["decisions"]
    return d[d["origin_week"] == o].set_index(["Store_ID", "Product_ID"])["ordered_units"]


def directional_checks(contract, panel, doc, series=None) -> dict:
    v = A.resolve(doc, "SC1")
    o = {t: first_decision_orders(contract, panel, _override(v, {"service_target_pct": dict.fromkeys(A.CATEGORIES, t)}), series)
         for t in (50, 70, 90)}
    # Case size is checked at the rounding step for the SAME pre-rounding need. A whole-system comparison is not
    # monotone: the synthetic initial schedule is also rounded up, so larger cases carry more stock into the first
    # decision (reported in the sensitivity table, not hidden).
    base = RP.simulate(contract, panel, v, series=series)
    cat = base["attributes"].set_index("Product_ID")["Product_Category"].to_dict()
    dl = base["deliveries"]
    small_v, big_v = _override(v, "case_half"), _override(v, "case_double")
    case_ok = all(A.case_round(n, big_v["case_size_units"][cat[p]], v["moq_cases_per_delivery"])
                  >= A.case_round(n, small_v["case_size_units"][cat[p]], v["moq_cases_per_delivery"])
                  for n, p in zip(dl["need_units_before_rounding"], dl["Product_ID"]))
    lo = RP.simulate(contract, panel, _override(v, {"delivery_fill_rate_pct": 60}), series=series)["weekly"]
    hi = RP.simulate(contract, panel, v, series=series)["weekly"]
    dm = RP.simulate(contract, panel, _override(v, {"demand_multiplier": 0.85}), series=series)["weekly"]
    feas_lo = A.feasibility({**doc, "parameters": [dict(p, value=dict.fromkeys(A.CATEGORIES, 5)) if p["key"] == "min_margin_pct" else p
                                                     for p in doc["parameters"]]})
    feas_hi = A.feasibility({**doc, "parameters": [dict(p, value=dict.fromkeys(A.CATEGORIES, 15)) if p["key"] == "min_margin_pct" else p
                                                     for p in doc["parameters"]]})
    return {
        "higher_planning_weight_orders_not_lower": bool((o[50] <= o[70]).all() and (o[70] <= o[90]).all()),
        "larger_case_size_not_lower_for_same_need": bool(case_ok),
        "lower_fill_rate_unmet_not_lower": bool(lo["sim_unmet_units_illustrative"].sum() >= hi["sim_unmet_units_illustrative"].sum()),
        "lower_demand_expired_not_lower": bool(dm["sim_expired_units"].sum() >= hi["sim_expired_units"].sum()),
        "higher_min_margin_max_discount_not_higher": all(
            feas_hi[c]["max_discount_by_margin_pct"] <= feas_lo[c]["max_discount_by_margin_pct"] for c in A.CATEGORIES),
    }


def write_run(results: dict, doc: dict, label: str, run_id: str | None = None, sens: pd.DataFrame | None = None,
              directions: dict | None = None, extra: dict | None = None) -> Path:
    from dpe.eda.outputs import save_json, save_table

    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + f"_{label}"
    run_dir = config.new_run_dir(run_id)
    comparison = []
    for sc, r in results.items():
        res = r["result"]
        for name in ("decisions", "deliveries", "daily", "weekly"):
            save_table(res[name], run_dir / sc / f"{name}.csv")
        save_table(r["cases"], run_dir / sc / "review_cases.csv")
        save_json({"conservation": r["conservation"], "kpis": r["kpis"], "case_summary": RQ.case_summary(r["cases"]),
                   "resolved_parameters": r["values"], "chronology_reads": len(res["demand_log"]),
                   "origins": [int(x) for x in res["origins"]]}, run_dir / sc / "scenario_summary.json")
        comparison.append({"scenario_id": sc, "scenario_name": r["values"]["scenario_name"], **r["kpis"]})
    first = next(iter(results.values()))["result"]
    save_table(first["attributes"], run_dir / "delivery_arrangements.csv")
    save_table(pd.DataFrame(comparison), run_dir / "scenario_comparison.csv")
    if sens is not None:
        save_table(sens, run_dir / "sensitivity_SC1.csv")
    code = Path(__file__).resolve().parent
    save_json({
        "run_id": run_id, "created_at": datetime.now().isoformat(timespec="seconds"),
        "step": "5B-2 assumption set and chronological replay simulator (SYNTHETIC; no recommendation engines)",
        "assumption_set": {"id": doc["assumption_set_id"], "version": doc["version"], "status": doc["approval"]["status"],
                           "content_sha256": A.content_sha256(doc)},
        "forecast_contract_run": config.FORECAST_CONTRACT_RUN_ID,
        "simulator_version": RP.SIMULATOR_VERSION, "review_queue_version": RQ.QUEUE_VERSION,
        "action_status": RP.ACTION_STATUS,
        "approval_note": "No approval events exist in a replay: every simulated order, delivery and outcome is "
                         "hypothetical and unauthorised; every review case is PENDING_REVIEW.",
        "scenarios": list(results), "watermark": A.watermark(next(iter(results.values()))["values"]),
        "statements": doc["statements"], "daily_label": RP.DAILY_LABEL, "position_note": RP.POSITION_NOTE,
        "directional_checks": directions,
        "code_sha256": {n: hashlib.sha256((code / n).read_bytes()).hexdigest()
                        for n in ("assumptions.py", "replay.py", "review_queue.py", "replay_run.py")},
        **(extra or {}),
    }, run_dir / "manifest.json")
    return run_dir
