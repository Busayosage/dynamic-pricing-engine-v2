"""Step 5B-3e: controlled P0/P1/P2 inventory policy comparison under the frozen evaluation policy.

Evaluation policy: config/evaluation/evaluation_policy_5B3e_v1.json (EP-5B3E-2026-10-23-v1), registered in
docs/CHECKSUMS.sha256 before the run. Pre-run checks refuse to start if the policy, its source document, the assumption
sets or any protected file has changed. Policies and thresholds are not changed after results are seen.

All results are SYNTHETIC replay values: recorded sales are illustrative demand (not verified unconstrained demand),
opening stock and supplier behaviour are assumed, and simulated unmet units are never observed lost sales. The
comparison is exploratory, because preliminary SC1 totals were seen during Stage 5B-3c.
"""
from __future__ import annotations

import hashlib
import inspect
import io
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import inventory as INV
from dpe.decision import recommendations as REC
from dpe.decision import replay as RP
from dpe.decision import replay_v12 as V

POLICY_FILE = config.PROJECT_ROOT / "config" / "evaluation" / "evaluation_policy_5B3e_v1.json"
SCENARIOS = ("SC1", "SC2", "SC3", "SF75")
ADOPTION_SCENARIOS = ("SC1", "SC2", "SC3")
ALLOWED_ACTION_STATUS = {"HYPOTHETICAL_UNAPPROVED", "REVIEW_REQUIRED_NO_ACTION"}
BANNED = ("probability of stockout", "chance of stockout", "% probability", "stockout probability:",
          "observed lost sale", "will run out on", "expires on", "stockout on", "on day ", "waste reduction of",
          "prevents lost sales", "margin improvement of")
KEY = ["store_id", "product_id", "origin_week"]


class IntegrityError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ------------------------------------------------------------------------------------------- phase 1
def prerun_checks() -> dict:
    """Integrity checks that must all pass before any comparison is executed."""
    expected = config.load_expected_checksums()
    bad = [rel for rel, digest in expected.items() if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    rel_policy = POLICY_FILE.relative_to(config.PROJECT_ROOT).as_posix()
    src = config.PROJECT_ROOT / policy["source"]["document"]
    v1 = A.load()
    v2 = B.load()
    checks = {
        "protected_checksums_verified": not bad, "protected_checksum_count": len(expected), "failed": bad,
        "evaluation_policy_registered": expected.get(rel_policy) == _sha(POLICY_FILE),
        "evaluation_policy_sha256": _sha(POLICY_FILE),
        "evaluation_policy_status_frozen": policy["status"] == "FROZEN_BEFORE_COMPARISON",
        "source_document_unchanged": _sha(src) == policy["source"]["document_sha256"],
        "source_document_registered": expected.get(policy["source"]["document"]) == _sha(src),
        "assumption_v1_unchanged_draft": A.content_sha256(v1) == B.V1_CONTENT_SHA256 and v1["approval"]["status"] == "DRAFT",
        "assumption_v2_matches_policy": A.content_sha256(v2) == policy["scope"]["assumption_set"]["content_sha256"]
        and v2["approval"]["status"] == "DRAFT" and v2["production_use"] is False,
        "protected_v11_run_present": (config.REPLAY_SIMULATION_V11_RUN_DIR / "manifest.json").exists(),
    }
    checks["all_passed"] = all(v for k, v in checks.items() if isinstance(v, bool))
    if not checks["all_passed"]:
        raise IntegrityError(f"Pre-run integrity checks failed; comparison not run: {checks}")
    return checks


# ------------------------------------------------------------------------------------------- phase 2
def run_all(contract, panel, v2doc, policies=V.POLICIES, scenarios=SCENARIOS, series=None) -> dict:
    share = V.unit_share(panel)
    out = {}
    for sc in scenarios:
        values = A.resolve(v2doc, sc)
        for p in policies:
            res = V.simulate(contract, panel, values, p, series=series, assumption_sha=A.content_sha256(v2doc),
                             contract_run=config.FORECAST_CONTRACT_RUN_ID)
            out[(p, sc)] = {"result": res, "review": V.review(res, contract, values, share, series=series), "values": values}
    return out


def _rt(df: pd.DataFrame) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(df.to_csv(index=False)))


def p1_regression(contract, panel, v1doc) -> dict:
    """P1 (v1 assumptions) against the protected v1.1 full replay, exactly (CSV round trip, as written)."""
    share = V.unit_share(panel)
    out = {}
    for sc in ADOPTION_SCENARIOS:
        v = A.resolve(v1doc, sc)
        r = V.simulate(contract, panel, v, "P1")
        prot = config.REPLAY_SIMULATION_V11_RUN_DIR / sc
        res = {}
        for name in ("decisions", "deliveries", "weekly", "daily"):
            old = pd.read_csv(prot / f"{name}.csv")
            cols = [c for c in old.columns if c != "simulator_version"]
            res[name] = bool(_rt(r[name])[cols].equals(old[cols]))
        res["review_cases"] = bool(_rt(V.review(r, contract, v, share)["cases"]).equals(pd.read_csv(prot / "review_cases.csv")))
        out[sc] = res
    return out


def p1_v2_matches_v1(results: dict, contract, panel, v1doc) -> dict:
    """P1 under assumption set v2 makes the same decisions and outcomes as under v1 (only set ids differ)."""
    out = {}
    for sc in ADOPTION_SCENARIOS:
        a = V.simulate(contract, panel, A.resolve(v1doc, sc), "P1")
        b = results[("P1", sc)]["result"]
        cols = [c for c in a["decisions"].columns if c != "assumption_set_id"]
        out[sc] = bool(a["decisions"][cols].equals(b["decisions"][cols])) and bool(
            a["weekly"].drop(columns="assumption_set_id", errors="ignore").equals(b["weekly"].drop(columns="assumption_set_id", errors="ignore")))
    return out


# --------------------------------------------------------------------------------------------- metrics
def _cases_frame(review) -> pd.DataFrame:
    c = review["cases"]
    return c.copy() if isinstance(c, pd.DataFrame) else pd.DataFrame(c)


def metrics(entry: dict) -> dict:
    r, review, v = entry["result"], entry["review"], entry["values"]
    w, d, dl = r["weekly"], r["decisions"], r["deliveries"]
    orders = dl[dl["kind"] == "ORDER"]
    excess = orders["ordered_units"] - orders["need_units_before_rounding"]
    cat = r["attributes"].drop_duplicates("Product_ID").set_index("Product_ID")["Product_Category"]
    by_cat = pd.DataFrame({"cat": orders["Product_ID"].map(cat), "ord": orders["ordered_units"], "exc": excess}).groupby("cat").sum()
    cases = _cases_frame(review)
    flags = d["flags"].fillna("")
    residual_p2 = int(flags.str.contains("SHORTAGE_REMAINING_AFTER_ORDER").sum())
    residual_v11 = int(flags.str.contains("POST_ORDER_SHORTFALL").sum())
    std = V.standard_risk_summary(r)
    dem = int(w["sim_demand_units_illustrative"].sum())
    return {
        "ordered_units": int(d["ordered_units"].sum()), "received_units": int(w["sim_received_units"].sum()),
        "demand_units_illustrative": dem, "sold_units": int(w["sim_sold_units"].sum()),
        "unmet_units_illustrative": int(w["sim_unmet_units_illustrative"].sum()),
        "expired_units": int(w["sim_expired_units"].sum()),
        "closing_units_final_week": int(w[w["week"] == w["week"].max()]["sim_closing_units"].sum()),
        "series_weeks_with_unmet": int((w["sim_unmet_units_illustrative"] > 0).sum()),
        "illustrative_fill_pct": round(100 * w["sim_sold_units"].sum() / dem, 3) if dem else None,
        "expired_share_of_received_pct": round(100 * w["sim_expired_units"].sum() / max(1, w["sim_received_units"].sum()), 3),
        "order_deliveries": int(len(orders)),
        "residual_shortfall_p2_reason": residual_p2, "residual_shortfall_v11_flag": residual_v11,
        "std_pre_delivery_shortage": std["pre_delivery_shortage"], "std_post_order_shortfall": std["post_order_shortfall"],
        "std_existing_expiry_high": std["existing_expiry_high"],
        "rounding_excess_units": round(float(excess.sum()), 1),
        "rounding_excess_pct_of_ordered": round(100 * float(excess.sum()) / max(1, int(orders["ordered_units"].sum())), 3),
        "rounding_excess_pct_by_category": {k: round(100 * row.exc / max(1, row.ord), 3) for k, row in by_cat.iterrows()},
        "weekly_cases": int(cases["case_type"].notna().sum()),
        "weekly_cases_by_type": {k: int(n) for k, n in cases["case_type"].value_counts().sort_index().items()},
        "standing_supplier_confirmation_cases": len(review["standing"]),
        "review_queue_version": review["queue_version"],
    }


# --------------------------------------------------------------------------------------------- gates
def _christmas_missing_points(contract) -> tuple[set, set]:
    c = contract.assign(_x=contract["target_week"].isin(RP.CHRISTMAS_WEEKS), _m=contract["uncertainty_status"] != "AVAILABLE")
    g = c.groupby(KEY).agg(x=("_x", "any"), m=("_m", "any"))
    return set(map(tuple, g[g["x"]].index)), set(map(tuple, g[g["m"]].index))


def hard_gates(entry: dict, contract) -> dict:
    """G1, G2 and G3 (a, b, c, e) for one policy x scenario; run-level reads for G3 d."""
    r, review, v = entry["result"], entry["review"], entry["values"]
    p = r["policy_id"]
    daily, weekly, d, dl = r["daily"], r["weekly"], r["decisions"], r["deliveries"]
    c = RP.check_conservation(daily, weekly)
    stock_cols = [x for x in daily.columns if x.startswith("sim_")]
    agg = daily.groupby(["Store_ID", "Product_ID", "week"])[["sim_received_units", "sim_sold_units", "sim_expired_units",
                                                              "sim_unmet_units_illustrative"]].sum().reset_index()
    wk = weekly.merge(agg, on=["Store_ID", "Product_ID", "week"], suffixes=("", "_d"))
    g1 = {"a_daily_balance": c["daily_balanced"], "b_closing_equals_next_opening": c["closing_equals_next_opening"],
          "c_no_negative_integer_stock": c["no_negative_values"] and all(pd.api.types.is_integer_dtype(daily[x]) for x in stock_cols),
          "d_weekly_equals_daily_sum": bool(c["weekly_balanced"] and all((wk[x] == wk[f"{x}_d"]).all() for x in
                                            ("sim_received_units", "sim_sold_units", "sim_expired_units", "sim_unmet_units_illustrative")))}
    orders = dl[dl["kind"] == "ORDER"].merge(d[["order_id", "decision_day", "effective_lead_time_days", "remaining_life_days",
                                                "product_category"]], on="order_id", how="left")
    a_day = orders["decision_day"] + orders["effective_lead_time_days"]
    case = orders["product_category"].map(v["case_size_units"])
    christmas, missing = _christmas_missing_points(contract)
    sim_keys = set(zip(d["Store_ID"], d["Product_ID"], d["origin_week"]))
    keyed = d.set_index(["Store_ID", "Product_ID", "origin_week"])
    gate_missing = [k for k in sim_keys if k in missing] if p == "P2" else \
        [k for k in sim_keys if k in set(map(tuple, contract[(contract.horizon_weeks == 1) & (contract.uncertainty_status != "AVAILABLE")][KEY].values))]
    no_qty = d["delivery_arrangement"].eq("UNSUPPORTED") | d["action_status"].eq("REVIEW_REQUIRED_NO_ACTION")
    recs = r["recommendations"]
    if p == "P2":
        sl = [x for x in recs if x["supplier_arrangement"]["arrangement"] == "SHORT_LIFE_RECURRING_DROPS" and x["proposed_order_units"] > 0]
        g2e = all("SHORT_LIFE_ARRANGEMENT_ASSUMED" in x["warnings"] for x in sl)
        g2e_note = f"{len(sl)} P2 short-life proposals checked"
    else:
        g2e, g2e_note = True, "NOT_APPLICABLE: no recommendation records for P0/P1; arrangement recorded as ASSUMED"
    sources = "".join(inspect.getsource(m) for m in (RP, V, INV, REC))
    life = dl.merge(r["attributes"][["Store_ID", "Product_ID", "remaining_life_days"]], on=["Store_ID", "Product_ID"])
    g2 = {"a_arrival_on_schedule": bool(((orders["arrival_day"] >= a_day) & (orders["arrival_day"] < a_day + 7)
                                         & ((orders["arrival_day"] - a_day) % orders["remaining_life_days"].clip(upper=7) == 0)).all()),
          "b_whole_cases_at_least_moq": bool(((orders["ordered_units"] % case == 0)
                                               & (orders["ordered_units"] >= case * v["moq_cases_per_delivery"])).all()),
          "c_expiry_day_rule": bool((life["expiry_day"] == life["arrival_day"] + life["remaining_life_days"] - 1).all()
                                    and len(life) == len(dl)),
          "d_no_quantity_when_blocked": bool((d.loc[no_qty, "ordered_units"] == 0).all()
                                             and all(keyed.loc[k, "ordered_units"] == 0 for k in gate_missing)),
          "e_short_life_assumed_label": g2e, "e_note": g2e_note,
          "f_supply_capacity_not_used": v.get("supply_capacity_used") is False and "Supply_Capacity" not in sources}
    cases = _cases_frame(review)
    ck = cases.set_index(KEY)
    unsafe_recs = 0
    for x in recs:
        try:
            REC.assert_safe(x)
        except AssertionError:
            unsafe_recs += 1
    case_list = cases.to_dict("records") + list(review["standing"])
    approval_ok = all((x.get("approval_event_id") is None or (isinstance(x.get("approval_event_id"), float) and np.isnan(x["approval_event_id"])))
                      for x in case_list)
    texts = []
    for df in (d, dl, cases):
        texts += [str(t).lower() for col in df.columns if df[col].dtype == object for t in df[col].dropna().astype(str).unique()]
    texts += [x["explanation"].lower() for x in recs]
    blob = " | ".join(texts)
    g3 = {"a_no_approval_or_execution": bool(set(d["action_status"]) <= ALLOWED_ACTION_STATUS and d["approval_event_id"].isna().all()
                                             and (dl["authorisation"] == RP.DELIVERY_AUTHORISATION).all() and unsafe_recs == 0
                                             and approval_ok and "APPROVED" not in set(cases.get("approval_status", pd.Series(dtype=object)).dropna())),
          "b_christmas_mandatory_escalation": bool(all(ck.loc[k, "case_type"] == "MANDATORY_ESCALATION" for k in christmas if k in ck.index)
                                                   and len([k for k in christmas if k in ck.index]) == len(christmas)),
          "c_missing_bounds_mandatory": bool(all(k in ck.index and ck.loc[k, "case_type"] in ("MANDATORY_REVIEW", "MANDATORY_ESCALATION")
                                                 for k in missing)),
          "d_reads_after_decision": bool(all(wk_ == dec + 1 for wk_, dec in r["demand_log"])
                                         and all(wk_ <= o for wk_, o in r["sales_reads"])),
          "e_banned_wording_absent": not [b for b in BANNED if b in blob]}
    return {"G1": g1, "G2": g2, "G3": g3,
            "passed": all(g1.values()) and all(val for k, val in g2.items() if k != "e_note") and all(g3.values())}


def thresholds(m: dict, policy: dict) -> dict:
    """Every quantitative threshold for P2 against P1, per adoption scenario, individually."""
    t = policy["comparison_thresholds_p2_vs_p1"]
    out = {}
    for sc in ADOPTION_SCENARIOS:
        p1, p2 = m[("P1", sc)], m[("P2", sc)]
        row = {}
        for code, metric in (("T_U", "unmet_units_illustrative"), ("T_E", "expired_units"), ("T_O", "ordered_units")):
            lim = t[f"{code}_" + {"T_U": "simulated_unmet_units_illustrative", "T_E": "simulated_expired_units",
                                  "T_O": "total_ordered_units"}[code]][sc]["max_ratio_to_P1"]
            ratio = p2[metric] / p1[metric] if p1[metric] else (0.0 if p2[metric] == 0 else float("inf"))
            row[code] = {"P1": p1[metric], "P2": p2[metric], "ratio": round(ratio, 4), "limit": lim, "passed": ratio <= lim}
        tr = t["T_R_review_workload"]["all"]
        ratio = p2["weekly_cases"] / p1["weekly_cases"]
        mand = {k: (p1["weekly_cases_by_type"].get(k, 0), p2["weekly_cases_by_type"].get(k, 0)) for k in tr["mandatory_counts_identical"]}
        row["T_R"] = {"P1": p1["weekly_cases"], "P2": p2["weekly_cases"], "ratio": round(ratio, 4), "limit": tr["max_ratio_to_P1"],
                      "mandatory_P1_P2": mand,
                      "mandatory_expected": tr["mandatory_counts_identical"],
                      "passed": ratio <= tr["max_ratio_to_P1"] and all(a == b == tr["mandatory_counts_identical"][k] for k, (a, b) in mand.items())}
        row["T_S"] = {"P1_v11_flag": p1["residual_shortfall_v11_flag"], "P2": p2["residual_shortfall_p2_reason"],
                      "passed": p2["residual_shortfall_p2_reason"] == 0 and p2["residual_shortfall_p2_reason"] <= p1["residual_shortfall_v11_flag"]}
        flag = t["T_X_rounding_excess"]["flag_if_category_share_of_ordered_units_above_pct"]
        row["T_X_report"] = {"P1_pct": p1["rounding_excess_pct_of_ordered"], "P2_pct": p2["rounding_excess_pct_of_ordered"],
                             "P2_categories_above_flag": [k for k, x in p2["rounding_excess_pct_by_category"].items() if x > flag],
                             "P1_categories_above_flag": [k for k, x in p1["rounding_excess_pct_by_category"].items() if x > flag]}
        row["passed"] = all(row[k]["passed"] for k in ("T_U", "T_E", "T_O", "T_R", "T_S"))
        out[sc] = row
    return out


def run_leakage_tests() -> dict:
    """G3 d: the leakage, scramble and mutation tests of the suite (subprocess, read-only)."""
    k = "leak or scrambl or future or receipts or demand_is_read or reads_happen or altering_future or truncated_history"
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-k", k, "tests"],
                          cwd=config.PROJECT_ROOT, capture_output=True, text=True)
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    return {"exit_code": proc.returncode, "passed": proc.returncode == 0, "summary": tail}


# --------------------------------------------------------------------------------------------- write
def write_run(results, gates, m, th, checks, regression, p1_same, leakage, policy, run_id=None) -> Path:
    from dpe.eda.outputs import _json_default, save_json, save_table

    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_policy_comparison"
    run_dir = config.new_run_dir(run_id)
    rows = []
    for (p, sc), e in results.items():
        r = e["result"]
        base = run_dir / sc / p
        for name in ("decisions", "deliveries", "weekly"):
            save_table(r[name], base / f"{name}.csv")
        save_table(_cases_frame(e["review"]), base / "review_cases.csv")
        if p == "P2":
            save_table(pd.DataFrame(e["review"]["standing"]), base / "standing_cases.csv")
            save_table(pd.DataFrame([{k: (json.dumps(v, default=_json_default) if isinstance(v, (dict, list)) else v) for k, v in x.items()}
                                     for x in r["recommendations"]]), base / "recommendations.csv")
        rows.append({"policy_id": p, "scenario_id": sc, **{k: (json.dumps(v, default=_json_default) if isinstance(v, dict) else v)
                                                            for k, v in m[(p, sc)].items()}})
    save_table(pd.DataFrame(rows), run_dir / "comparison_table.csv")
    adopt = all(g["passed"] for g in gates.values()) and all(th[sc]["passed"] for sc in ADOPTION_SCENARIOS) \
        and all(all(x.values()) for x in regression.values()) and leakage["passed"] and checks["all_passed"]
    save_json({"hard_gates": {f"{p}/{sc}": g for (p, sc), g in gates.items()}, "thresholds": th,
               "p1_regression_vs_protected_v11": regression, "p1_v2_equals_v1": p1_same, "leakage_tests": leakage,
               "prerun_checks": checks, "outcome": {"p2_meets_all_adoption_criteria": bool(adopt),
                                                    "research_replay_default": "P2" if adopt else "P1"}},
              run_dir / "evaluation.json")
    code = config.PROJECT_ROOT / "src" / "dpe" / "decision"
    save_json({"run_id": run_id, "created_at": datetime.now().isoformat(timespec="seconds"),
               "step": "5B-3e controlled inventory policy comparison (SYNTHETIC, exploratory)",
               "evaluation_policy": {"id": policy["evaluation_policy_id"], "sha256": _sha(POLICY_FILE)},
               "assumption_set": policy["scope"]["assumption_set"], "forecast_contract_run": config.FORECAST_CONTRACT_RUN_ID,
               "policies": V.POLICY_DESCRIPTIONS, "scenarios": list(SCENARIOS), "simulator_version": V.SIMULATOR_VERSION,
               "exploratory_note": policy["source"]["preliminary_exposure"],
               "daily_outputs": "not written (size); conservation and timing gates were evaluated on them in memory",
               "status": "HYPOTHETICAL_UNAPPROVED: no order, delivery, price change or transfer was made; nothing is approved",
               "code_sha256": {n: _sha(code / n) for n in ("replay.py", "replay_v12.py", "inventory.py", "recommendations.py",
                                                           "inventory_review.py", "review_queue.py", "assumptions.py",
                                                           "assumptions_v2.py", "policy_comparison.py")}},
              run_dir / "manifest.json")
    return run_dir
