"""Phase 2: preregistered evaluation of the dynamic pricing simulation against unchanged prices (SIMULATED RESEARCH).

Evaluation policy: config/evaluation/evaluation_policy_phase2_v1.json (EP-PH2-2026-10-23-v1), registered in
docs/CHECKSUMS.sha256 before any pricing outcome was simulated. `prerun_checks` refuses to start if the policy, its
source document, assumption sets v2 / v7 or any protected file has changed. Thresholds are never changed after results
are seen. A pass is a research result only; nothing here is commercial proof, and nothing is approved or executed.
"""
from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v7 as V7
from dpe.decision import dynamic_pricing as DP
from dpe.decision import replay as RP
from dpe.decision import replay_pricing as RPP

POLICY_FILE = config.PROJECT_ROOT / "config" / "evaluation" / "evaluation_policy_phase2_v1.json"
PROTECTED_RUN = config.PROJECT_ROOT / "outputs" / "runs" / "20261023-131711_policy_comparison"
SCENARIOS = ("SC1", "SC2", "SC3", "SF75")
ADOPTION_SCENARIOS = ("SC1", "SC2", "SC3")
TRUTHS = ("R0_NO_RESPONSE", "R1_LOW", "R2_CENTRAL", "R3_HIGH")
KEY = ["Store_ID", "Product_ID"]
TOL = 1e-9


class IntegrityError(RuntimeError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rt(df: pd.DataFrame) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(df.to_csv(index=False)))


def _same(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    try:
        pd.testing.assert_frame_equal(_rt(a), _rt(b))
        return True
    except AssertionError:
        return False


def load_policy() -> dict:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def prerun_checks() -> dict:
    expected = config.load_expected_checksums()
    bad = [rel for rel, digest in expected.items() if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    policy = load_policy()
    rel = POLICY_FILE.relative_to(config.PROJECT_ROOT).as_posix()
    src = config.PROJECT_ROOT / policy["source"]["document"]
    v2, v7 = B.load(), V7.load()
    checks = {
        "protected_checksums_verified": not bad, "protected_checksum_count": len(expected), "failed": bad,
        "evaluation_policy_registered": expected.get(rel) == _sha(POLICY_FILE),
        "evaluation_policy_status_frozen": policy["status"] == "FROZEN_BEFORE_COMPARISON",
        "source_document_unchanged": _sha(src) == policy["source"]["document_sha256"],
        "source_document_registered": expected.get(policy["source"]["document"]) == _sha(src),
        "replay_assumptions_match_policy": A.content_sha256(v2) == policy["scope"]["replay_assumption_set"]["content_sha256"],
        "pricing_assumptions_match_policy": A.content_sha256(v7) == policy["scope"]["pricing_assumption_set"]["content_sha256"],
        "assumption_v7_registered": expected.get("config/assumptions/assumption_set_v7.json") == _sha(V7.V7_FILE),
        "protected_baseline_present": (PROTECTED_RUN / "manifest.json").exists(),
    }
    checks["all_passed"] = all(v for k, v in checks.items() if isinstance(v, bool))
    if not checks["all_passed"]:
        raise IntegrityError(f"Pre-run integrity checks failed; evaluation not run: {checks}")
    return checks


# ------------------------------------------------------------------------------------------------ prerequisites
def prerequisites(sc: str, off: dict, shadow: dict, saved_markdown: pd.DataFrame | None) -> dict:
    """E1 pricing off == protected P2; E2 fixed orders without markdowns == pricing off; E3 eligibility == saved."""
    base = PROTECTED_RUN / sc / "P2"
    e1 = {n: _same(off[n], pd.read_csv(base / f"{n}.csv")) for n in ("decisions", "deliveries", "weekly")}
    e2 = {n: _same(shadow[n], off[n]) for n in ("decisions", "deliveries", "daily", "weekly")}
    out = {"E1_pricing_off_equals_protected_P2": e1, "E2_fixed_orders_no_markdown_equal_pricing_off": e2}
    if saved_markdown is not None:
        log = shadow["pricing_log"]
        m = saved_markdown.merge(log, on=KEY + ["origin_week"], suffixes=("_saved", "_loop"))
        def eq(a, b):
            x, y = m[a], m[b]
            return int((~((x == y) | (x.isna() & y.isna()))).sum())
        out["E3_in_loop_eligibility_equals_saved_markdown_review"] = {
            "rows_saved": int(len(saved_markdown)), "rows_loop": int(len(log)), "rows_matched": int(len(m)),
            "eligibility_mismatches": eq("eligibility_saved", "eligibility_loop"),
            "blocker_mismatches": int((m["blocker_codes_saved"].fillna("") != m["blocker_codes_loop"].fillna("")).sum()),
            "waste_class_mismatches": int((m["waste_risk_category_saved"] != m["waste_risk_category_loop"]).sum()),
            "investigate_by_mismatches": eq("investigate_by_day_saved", "investigate_by_day_loop"),
            "batch_day_mismatches": eq("earliest_batch_last_day_saved", "earliest_batch_last_day_loop"),
            "at_risk_mismatches": int(((m["projected_existing_expiry_units"] - m["at_risk_units"]).abs() > TOL).sum()
                                      + (m["projected_existing_expiry_units"].isna() != m["at_risk_units"].isna()).sum())}
        e3 = out["E3_in_loop_eligibility_equals_saved_markdown_review"]
        e3["passed"] = e3["rows_saved"] == e3["rows_loop"] == e3["rows_matched"] and \
            all(v == 0 for k, v in e3.items() if k.endswith("mismatches"))
    out["passed"] = all(e1.values()) and all(e2.values()) and \
        out.get("E3_in_loop_eligibility_equals_saved_markdown_review", {"passed": True})["passed"]
    return out


# ---------------------------------------------------------------------------------------------------- hard gates
def hard_gates(priced: dict, off: dict, off_days: pd.DataFrame, days: pd.DataFrame, params: dict) -> dict:
    log = priced["pricing_log"]
    ev = log[log["outcome"] == DP.SELECTED] if len(log) else log
    cons = RP.check_conservation(priced["daily"], priced["weekly"])
    g = {"G1_conservation": all(v for k, v in cons.items() if isinstance(v, bool)),
         "G2_ordering_unchanged": _same(priced["decisions"], off["decisions"]) and _same(priced["deliveries"], off["deliveries"])}
    steps = set(params["discount_steps_pct"])
    floor_ok = True
    if len(ev):
        cost = ev["reference_price"] * (1 - ev["product_category"].map(params["gross_margin_pct"]) / 100)
        margin = (ev["markdown_price"] - cost) / ev["markdown_price"]
        floor_ok = bool((margin >= ev["product_category"].map(params["min_margin_pct"]) / 100 - TOL).all())
    g["G3_markdown_only_and_price_bounds"] = bool((days["price"] <= days["reference_price"] + TOL).all()) and \
        bool(ev["markdown_pct"].isin(steps).all()) and bool((ev["markdown_pct"] <= params["max_discount_pct"]).all()) and floor_ok
    guards_ok = bool((ev["eligibility"] == "ELIGIBLE_FOR_MARKDOWN_REVIEW").all()) and \
        bool((ev["window_start_day"] >= ev["decision_day"]).all()) if len(ev) else True
    for _, e in (ev.sort_values("decision_day").groupby(KEY) if len(ev) else []):
        dd, ends = e["decision_day"].to_numpy(), e["window_end_day"].to_numpy()
        starts = e["window_start_day"].to_numpy()
        if len(dd) > 1 and (np.diff(dd) < params["dynamic_pricing_cooldown_days"]).any():
            guards_ok = False
        if any(((dd > x - params["dynamic_pricing_event_window_days"]) & (dd <= x)).sum()
               > params["dynamic_pricing_max_events_per_window"] for x in dd):
            guards_ok = False
        if len(dd) > 1 and (starts[1:] <= ends[:-1]).any():
            guards_ok = False
    g["G4_eligibility_and_timing_guards"] = guards_ok
    reads_ok = all(week <= decided + 1 for week, decided in priced["demand_log"])
    marked = days[days["markdown_pct"] > 0]
    inside = True
    if len(marked):
        w = marked.merge(ev[["event_id", "window_start_day", "window_end_day"]], on="event_id", how="left")
        inside = bool(((w["day"] >= w["window_start_day"]) & (w["day"] <= w["window_end_day"])).all())
    g["G5_chronology"] = reads_ok and inside
    labels = len(log) == 0 or (bool((log["status"] == DP.STATUS).all()) and bool((log["approval_status"] == DP.APPROVAL_STATUS).all())
                               and bool((log["execution_status"] == DP.EXECUTION_STATUS).all())
                               and bool(log["approval_event_id"].isna().all()) and bool(log["proposal_id"].isna().all()))
    if len(ev):
        labels = labels and bool((ev["application"] == DP.APPLICATION).all()) and \
            bool(ev["review_tags"].str.contains("PENDING_HUMAN_REVIEW").all())
    g["G6_labels_unapproved_not_executed"] = labels
    if priced["true_response"] == "R0_NO_RESPONSE":
        g["G7_no_response_demand_equals_baseline"] = bool(
            (priced["daily"]["sim_demand_units_illustrative"].to_numpy() == off["daily"]["sim_demand_units_illustrative"].to_numpy()).all())
    g["passed"] = all(v for v in g.values() if isinstance(v, bool))
    g["conservation_detail"] = cons
    return g


# ------------------------------------------------------------------------------------------------------ measures
def measures(days: pd.DataFrame, base_days: pd.DataFrame, log: pd.DataFrame) -> dict:
    ev = log[log["outcome"] == DP.SELECTED] if len(log) else log
    s = lambda df, c: float(df[c].sum())  # noqa: E731
    m = {"markdown_events": int(len(ev)),
         "lines_with_markdowns": int(ev.groupby(KEY).ngroups) if len(ev) else 0,
         "mandatory_reviews": int(ev["review_tags"].str.contains("MANDATORY_REVIEW").sum()) if len(ev) else 0,
         "markdown_days": int((days["markdown_pct"] > 0).sum()),
         "baseline": {c: s(base_days, c) for c in ("revenue", "gross_profit", "sim_sold_units", "sim_expired_units",
                                                     "sim_unmet_units_illustrative", "expired_cost")},
         "priced": {c: s(days, c) for c in ("revenue", "gross_profit", "sim_sold_units", "sim_expired_units",
                                             "sim_unmet_units_illustrative", "expired_cost")}}
    m["delta"] = {c: m["priced"][c] - m["baseline"][c] for c in m["baseline"]}
    per = (days.groupby(KEY)[["gross_profit", "sim_expired_units", "sim_unmet_units_illustrative"]].sum()
           - base_days.groupby(KEY)[["gross_profit", "sim_expired_units", "sim_unmet_units_illustrative"]].sum())
    m["lines_gross_profit_fell"] = int((per["gross_profit"] < -TOL).sum())
    m["lines_gross_profit_rose"] = int((per["gross_profit"] > TOL).sum())
    m["lines_expiry_fell"] = int((per["sim_expired_units"] < 0).sum())
    m["lines_unmet_rose"] = int((per["sim_unmet_units_illustrative"] > 0).sum())
    d = m["delta"]
    m["benefits"] = {"gross_profit_gain": max(d["gross_profit"], 0.0), "expired_units_avoided": max(-d["sim_expired_units"], 0.0)}
    m["harms"] = {"gross_profit_loss": max(-d["gross_profit"], 0.0), "extra_unmet_units": max(d["sim_unmet_units_illustrative"], 0.0),
                  "extra_expired_units": max(d["sim_expired_units"], 0.0), "lines_gross_profit_fell": m["lines_gross_profit_fell"],
                  "markdown_events_needing_review": m["markdown_events"], "mandatory_reviews": m["mandatory_reviews"]}
    return m


def thresholds(m_by_truth: dict) -> dict:
    """Preregistered thresholds T1-T5 for one scenario; NOT_APPLICABLE when no markdown was selected."""
    out = {}
    def res(truth, ok):
        if m_by_truth[truth]["markdown_events"] == 0:
            return "NOT_APPLICABLE"
        return "PASS" if ok else "FAIL"
    for truth, m in m_by_truth.items():
        d, b = m["delta"], m["baseline"]
        if truth == "R2_CENTRAL":
            out["T1_R2_CENTRAL"] = res(truth, d["sim_expired_units"] < 0 and d["gross_profit"] >= -TOL)
        if truth == "R3_HIGH":
            out["T2_R3_HIGH"] = res(truth, d["gross_profit"] >= -TOL)
        if truth == "R1_LOW":
            out["T3_R1_LOW"] = res(truth, d["gross_profit"] >= -0.10 * b["expired_cost"] - TOL)
        if truth == "R0_NO_RESPONSE":
            out["T4_R0_NO_RESPONSE"] = res(truth, d["gross_profit"] >= -0.25 * b["expired_cost"] - TOL)
        out[f"T5_UNMET_{truth}"] = res(truth, d["sim_unmet_units_illustrative"] <= 0.005 * b["sim_sold_units"] + TOL)
    return out


# ---------------------------------------------------------------------------------------------------- the grid
def run_scenario(sc: str, contract, panel, v2doc, params, saved_markdown=None, series=None) -> dict:
    values = A.resolve(v2doc, sc)
    sha = A.content_sha256(v2doc)
    off = RPP.simulate(contract, panel, values, policy="P2", series=series, assumption_sha=sha,
                       contract_run=config.FORECAST_CONTRACT_RUN_ID)
    shadow = RPP.simulate(contract, panel, values, dict(params, dynamic_pricing_max_events_per_window=0), policy="P2",
                          pricing=True, true_response="R2_CENTRAL", fixed=off, series=series)
    pre = prerequisites(sc, off, shadow, saved_markdown) if series is None else None
    if pre is not None and not pre["passed"]:  # STOP: never evaluate pricing on a baseline that does not reproduce
        raise IntegrityError(f"{sc}: pricing-off equivalence failed; no pricing run was made: {pre}")
    base_days = RPP.price_days(off, contract, params)
    out = {"off": off, "prerequisites": pre, "base_days": base_days, "truths": {}}
    for t in TRUTHS:
        priced = RPP.simulate(contract, panel, values, params, policy="P2", pricing=True, true_response=t, fixed=off,
                              series=series)
        days = RPP.price_days(priced, contract, params)
        out["truths"][t] = {"result": priced, "days": days, "gates": hard_gates(priced, off, base_days, days, params),
                            "measures": measures(days, base_days, priced["pricing_log"])}
    out["thresholds"] = thresholds({t: e["measures"] for t, e in out["truths"].items()})
    return out


def outcome(results: dict) -> dict:
    pre_ok = all(r["prerequisites"]["passed"] for r in results.values())
    gates_ok = all(e["gates"]["passed"] for r in results.values() for e in r["truths"].values())
    th_ok = all(v != "FAIL" for sc in ADOPTION_SCENARIOS for v in results[sc]["thresholds"].values())
    meets = pre_ok and gates_ok and th_ok
    return {"prerequisites_passed": pre_ok, "hard_gates_passed": gates_ok, "adoption_thresholds_passed": th_ok,
            "result": "MEETS_PREREGISTERED_RESEARCH_CRITERIA" if meets else "DOES_NOT_MEET_PREREGISTERED_RESEARCH_CRITERIA",
            "statement": "Research result on synthetic data under assumed customer responses. Not commercial proof; "
                         "nothing is approved, proposed for live use or executed."}


def write_run(results: dict, checks_before: dict, checks_after: dict, policy: dict, contract, run_id=None) -> Path:
    from dpe.eda.outputs import save_json, save_table

    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_dynamic_pricing_evaluation"
    run_dir = config.new_run_dir(run_id)  # never reuses or overwrites a run
    rows, ev_all = [], []
    for sc, r in results.items():
        marked = set()
        for t, e in r["truths"].items():
            log = e["result"]["pricing_log"]
            save_table(log, run_dir / sc / t / "pricing_decisions.csv")
            save_table(e["result"]["weekly"], run_dir / sc / t / "weekly.csv")
            sel = log[log["outcome"] == DP.SELECTED]
            marked |= set(zip(sel["Store_ID"], sel["Product_ID"]))
            m = e["measures"]
            rows.append({"scenario_id": sc, "true_response": t, "markdown_events": m["markdown_events"],
                         "lines_with_markdowns": m["lines_with_markdowns"], "mandatory_reviews": m["mandatory_reviews"],
                         **{f"delta_{k}": v for k, v in m["delta"].items()},
                         **{f"baseline_{k}": v for k, v in m["baseline"].items()},
                         "lines_gross_profit_fell": m["lines_gross_profit_fell"], "lines_gross_profit_rose": m["lines_gross_profit_rose"],
                         "lines_expiry_fell": m["lines_expiry_fell"], "lines_unmet_rose": m["lines_unmet_rose"],
                         "hard_gates_passed": e["gates"]["passed"]})
        keep = lambda df: df[df.set_index(KEY).index.isin(marked)]  # noqa: E731 - daily rows only for lines with markdowns
        save_table(keep(r["base_days"]), run_dir / sc / "baseline_daily_marked_lines.csv")
        for t, e in r["truths"].items():
            save_table(keep(e["days"]), run_dir / sc / t / "daily_marked_lines.csv")
            per = (e["days"].groupby(KEY)[["revenue", "gross_profit", "sim_expired_units", "sim_unmet_units_illustrative"]].sum()
                   - r["base_days"].groupby(KEY)[["revenue", "gross_profit", "sim_expired_units", "sim_unmet_units_illustrative"]].sum())
            save_table(per.add_prefix("delta_").reset_index(), run_dir / sc / t / "line_deltas.csv")
    save_table(pd.DataFrame(rows), run_dir / "comparison_table.csv")
    out = outcome(results)
    save_json({"evaluation_policy_id": policy["evaluation_policy_id"], "outcome": out,
               "prerequisites": {sc: r["prerequisites"] for sc, r in results.items()},
               "hard_gates": {f"{sc}/{t}": {k: v for k, v in e["gates"].items()} for sc, r in results.items()
                              for t, e in r["truths"].items()},
               "thresholds": {sc: r["thresholds"] for sc, r in results.items()},
               "measures": {f"{sc}/{t}": e["measures"] for sc, r in results.items() for t, e in r["truths"].items()},
               "prerun_checks": checks_before, "postrun_checks": checks_after}, run_dir / "evaluation.json")
    code = config.PROJECT_ROOT / "src" / "dpe" / "decision"
    save_json({"run_id": run_id, "created_at": datetime.now().isoformat(timespec="seconds"),
               "step": "Phase 2 dynamic pricing research evaluation (SYNTHETIC; SIMULATED RESEARCH - NOT VALIDATED FOR LIVE USE)",
               "evaluation_policy": {"id": policy["evaluation_policy_id"], "sha256": _sha(POLICY_FILE)},
               "replay_assumption_set": policy["scope"]["replay_assumption_set"],
               "pricing_assumption_set": policy["scope"]["pricing_assumption_set"],
               "protected_baseline_run": PROTECTED_RUN.name, "forecast_contract_run": config.FORECAST_CONTRACT_RUN_ID,
               "simulator_version": RPP.SIMULATOR_VERSION, "scenarios": list(results), "true_responses": list(TRUTHS),
               "daily_outputs": "written only for lines with at least one simulated markdown (size); all gates ran on every daily row in memory",
               "status": "SIMULATED / HYPOTHETICAL_UNAPPROVED / NOT_EXECUTED: no order, price change, approval or integration exists",
               "code_sha256": {n: _sha(code / n) for n in ("replay.py", "replay_v12.py", "replay_pricing.py", "dynamic_pricing.py",
                                                           "discount_recommendation.py", "pricing_demo.py", "waste_risk.py",
                                                           "markdown_eligibility.py", "pricing_evaluation.py",
                                                           "assumptions_v7.py")}},
              run_dir / "manifest.json")
    return run_dir
