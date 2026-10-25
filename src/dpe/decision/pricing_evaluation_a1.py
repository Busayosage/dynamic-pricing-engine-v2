"""Amendment A1 evaluation: original Phase 2 cooldown rule (v7) vs A1 (v8) vs unchanged prices (SIMULATED RESEARCH).

Evaluation policy: config/evaluation/evaluation_policy_phase2_a1_v1.json (EP-PH2-A1-2026-10-24-v1), registered in
docs/CHECKSUMS.sha256 before any full A1 outcome was simulated. `pricing_evaluation.py` (the frozen original evaluation)
is imported and reused, never edited: its prerequisites, hard gates, measures and thresholds are applied to A1 unchanged.
A1-specific checks (the original reproduced, gate G8) and the preregistered preference rule are added here.
A pass is a research result only; nothing is approved, proposed for live use or executed.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v8 as V8
from dpe.decision import dynamic_pricing as DP
from dpe.decision import pricing_evaluation as PE
from dpe.decision import replay_pricing as RPP
from dpe.decision import replay_pricing_a1 as RPA1

POLICY_FILE = config.PROJECT_ROOT / "config" / "evaluation" / "evaluation_policy_phase2_a1_v1.json"
ORIGINAL_RUN = config.PROJECT_ROOT / "outputs" / "runs" / "20261023-233225_dynamic_pricing_evaluation"
REGISTERED = ("config/assumptions/assumption_set_v8.json", "src/dpe/decision/assumptions_v8.py",
              "src/dpe/decision/dynamic_pricing_a1.py", "src/dpe/decision/replay_pricing_a1.py",
              "src/dpe/decision/pricing_evaluation_a1.py", "scripts/run_dynamic_pricing_evaluation_a1.py",
              "config/evaluation/evaluation_policy_phase2_a1_v1.json", "docs/PHASE_2_AMENDMENT_A1_COOLDOWN.md")
RULES = ("ORIGINAL", "A1")
KEY = PE.KEY
TOL = PE.TOL


def load_policy() -> dict:
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def prerun_checks() -> dict:
    expected = config.load_expected_checksums()
    bad = [rel for rel, digest in expected.items() if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    policy = load_policy()
    src = config.PROJECT_ROOT / policy["source"]["document"]
    orig = config.PROJECT_ROOT / policy["source"]["original_policy"]["file"]
    v2, v8 = B.load(), V8.load()
    checks = {
        "protected_checksums_verified": not bad, "protected_checksum_count": len(expected), "failed": bad,
        "a1_files_registered": {rel: expected.get(rel) == PE._sha(config.PROJECT_ROOT / rel) for rel in REGISTERED},
        "evaluation_policy_status_frozen": policy["status"] == "FROZEN_BEFORE_COMPARISON",
        "source_document_unchanged": PE._sha(src) == policy["source"]["document_sha256"],
        "original_policy_unchanged": PE._sha(orig) == policy["source"]["original_policy"]["sha256"],
        "original_run_present": (ORIGINAL_RUN / "manifest.json").exists(),
        "replay_assumptions_match_policy": A.content_sha256(v2) == policy["scope"]["replay_assumption_set"]["content_sha256"],
        "pricing_assumptions_match_policy": A.content_sha256(v8) == policy["scope"]["pricing_assumption_set"]["content_sha256"],
    }
    checks["a1_files_all_registered"] = all(checks["a1_files_registered"].values())
    checks["all_passed"] = all(v for k, v in checks.items() if isinstance(v, bool))
    if not checks["all_passed"]:
        raise PE.IntegrityError(f"Pre-run integrity checks failed; A1 evaluation not run: {checks}")
    return checks


def g8_a1_cooldown(log: pd.DataFrame, params: dict) -> bool:
    """Every repeat markdown starts at least cooldown + 1 days after the previous window ended."""
    ev = log[log["outcome"] == DP.SELECTED].sort_values("decision_day")
    for _, g in ev.groupby(KEY):
        s, e = g["window_start_day"].to_numpy(), g["window_end_day"].to_numpy()
        if len(s) > 1 and (s[1:] < e[:-1] + params["dynamic_pricing_cooldown_days"] + 1).any():
            return False
    return True


def cooldown_blocked(log: pd.DataFrame) -> int:
    if not len(log):
        return 0
    return int(((log["outcome"] == "GUARD_BLOCKED") & log["guard_codes"].fillna("").str.contains("COOLDOWN")).sum())


def run_scenario(sc: str, contract, panel, v2doc, p7: dict, p8: dict, saved_markdown, series=None) -> dict:
    """Full evaluation of one scenario; `series` (tests only) restricts lines and skips the full-run prerequisites."""
    values = A.resolve(v2doc, sc)
    off = RPP.simulate(contract, panel, values, policy="P2", series=series, assumption_sha=A.content_sha256(v2doc),
                       contract_run=config.FORECAST_CONTRACT_RUN_ID)
    shadow = RPA1.simulate(contract, panel, values, dict(p8, dynamic_pricing_max_events_per_window=0), policy="P2",
                           pricing=True, true_response="R2_CENTRAL", fixed=off, series=series)
    pre = PE.prerequisites(sc, off, shadow, saved_markdown) if series is None else {"passed": True, "subset_only": True}
    if not pre["passed"]:  # STOP: never evaluate on a baseline that does not reproduce the protected replay
        raise PE.IntegrityError(f"{sc}: pricing-off equivalence failed; no A1 run was made: {pre}")
    base_days = RPP.price_days(off, contract, p8)
    out = {"off": off, "prerequisites": pre, "base_days": base_days, "truths": {}}
    for t in PE.TRUTHS:
        orig = RPP.simulate(contract, panel, values, p7, policy="P2", pricing=True, true_response=t, fixed=off,
                            series=series)
        saved = pd.read_csv(ORIGINAL_RUN / sc / t / "pricing_decisions.csv")
        if series is not None:
            saved = saved[saved.set_index(KEY).index.isin(series)].reset_index(drop=True)
        reproduced = PE._same(orig["pricing_log"], saved)
        orig_days = RPP.price_days(orig, contract, p7)
        a1 = RPA1.simulate(contract, panel, values, p8, policy="P2", pricing=True, true_response=t, fixed=off,
                           series=series)
        days = RPA1.price_days(a1, contract, p8)
        gates = PE.hard_gates(a1, off, base_days, days, p8)
        gates["G8_a1_cooldown_from_window_end"] = g8_a1_cooldown(a1["pricing_log"], p8)
        gates["passed"] = gates["passed"] and gates["G8_a1_cooldown_from_window_end"]
        orig_gates = PE.hard_gates(orig, off, base_days, orig_days, p7)
        out["truths"][t] = {
            "result": a1, "days": days, "gates": gates, "measures": PE.measures(days, base_days, a1["pricing_log"]),
            "cooldown_blocked": cooldown_blocked(a1["pricing_log"]),
            "original": {"reproduced": reproduced, "gates_passed": orig_gates["passed"],
                         "measures": PE.measures(orig_days, base_days, orig["pricing_log"]),
                         "cooldown_blocked": cooldown_blocked(orig["pricing_log"]), "log": orig["pricing_log"]}}
    out["thresholds"] = PE.thresholds({t: e["measures"] for t, e in out["truths"].items()})
    out["original_thresholds"] = PE.thresholds({t: e["original"]["measures"] for t, e in out["truths"].items()})
    return out


def preference(results: dict) -> dict:
    """The frozen preference rule PA-PE (evaluation_policy_phase2_a1_v1.json)."""
    adopt = PE.ADOPTION_SCENARIOS
    pa = all(r["prerequisites"]["passed"] for r in results.values()) and \
        all(e["gates"]["passed"] and e["original"]["reproduced"] for r in results.values() for e in r["truths"].values())
    pb = all(v != "FAIL" for sc in adopt for v in results[sc]["thresholds"].values())
    d = lambda sc, t, c, rule: (results[sc]["truths"][t]["measures"] if rule == "A1"  # noqa: E731
                                else results[sc]["truths"][t]["original"]["measures"])["delta"][c]
    pc = all(d(sc, t, "gross_profit", "A1") >= d(sc, t, "gross_profit", "ORIGINAL") - TOL
             for sc in adopt for t in ("R0_NO_RESPONSE", "R1_LOW"))
    gain_o = sum(d(sc, "R2_CENTRAL", "gross_profit", "ORIGINAL") for sc in adopt)
    gain_a = sum(d(sc, "R2_CENTRAL", "gross_profit", "A1") for sc in adopt)
    exp_o = -sum(d(sc, "R2_CENTRAL", "sim_expired_units", "ORIGINAL") for sc in adopt)
    exp_a = -sum(d(sc, "R2_CENTRAL", "sim_expired_units", "A1") for sc in adopt)
    pd_ = gain_a >= 0.75 * gain_o - TOL and exp_a >= 0.75 * exp_o - TOL
    pe = all(sum(d(sc, t, "sim_unmet_units_illustrative", "A1") for sc in adopt)
             <= sum(d(sc, t, "sim_unmet_units_illustrative", "ORIGINAL") for sc in adopt) + TOL for t in PE.TRUTHS)
    parts = {"PA_all_checks_and_gates": pa, "PB_original_thresholds_met": pb, "PC_no_larger_loss_weak_response": pc,
             "PD_keeps_75pct_of_central_benefit": pd_, "PE_no_more_unmet_units": pe}
    ok = all(parts.values())
    return {**parts, "central_gross_profit_gain": {"original": gain_o, "a1": gain_a,
                                                   "a1_share_of_original": None if gain_o == 0 else gain_a / gain_o},
            "central_expired_units_avoided": {"original": exp_o, "a1": exp_a,
                                              "a1_share_of_original": None if exp_o == 0 else exp_a / exp_o},
            "result": "A1_PREFERRED_RESEARCH_COOLDOWN" if ok else "ORIGINAL_RULE_RETAINED_AS_PREFERRED",
            "failed_parts": [k for k, v in parts.items() if not v],
            "statement": "Research comparison on synthetic data under assumed customer responses; exploratory because "
                         "the original results were seen first. Not commercial proof."}


def comparison_rows(results: dict) -> pd.DataFrame:
    rows = []
    for sc, r in results.items():
        for t, e in r["truths"].items():
            for rule, m, blocked, gates in (("ORIGINAL", e["original"]["measures"], e["original"]["cooldown_blocked"],
                                             e["original"]["gates_passed"]),
                                            ("A1", e["measures"], e["cooldown_blocked"], e["gates"]["passed"])):
                rows.append({"scenario_id": sc, "true_response": t, "rule": rule,
                             "source_run": ORIGINAL_RUN.name if rule == "ORIGINAL" else "this run",
                             "markdown_events": m["markdown_events"], "markdowns_blocked_by_cooldown": blocked,
                             "lines_with_markdowns": m["lines_with_markdowns"], "mandatory_reviews": m["mandatory_reviews"],
                             **{f"delta_{k}": v for k, v in m["delta"].items()},
                             **{f"baseline_{k}": v for k, v in m["baseline"].items()},
                             "lines_gross_profit_fell": m["lines_gross_profit_fell"],
                             "lines_gross_profit_rose": m["lines_gross_profit_rose"],
                             "lines_expiry_fell": m["lines_expiry_fell"], "lines_unmet_rose": m["lines_unmet_rose"],
                             "hard_gates_passed": gates})
    return pd.DataFrame(rows)


def write_run(results: dict, checks_before: dict, checks_after: dict, policy: dict, run_id=None) -> Path:
    from dpe.eda.outputs import save_json, save_table

    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_dynamic_pricing_evaluation_a1"
    run_dir = config.new_run_dir(run_id)  # never reuses or overwrites a run
    comp = comparison_rows(results)
    for sc, r in results.items():
        marked = set()
        for t, e in r["truths"].items():
            log = e["result"]["pricing_log"]
            save_table(log, run_dir / sc / t / "pricing_decisions.csv")
            save_table(e["result"]["weekly"], run_dir / sc / t / "weekly.csv")
            sel = log[log["outcome"] == DP.SELECTED]
            marked |= set(zip(sel["Store_ID"], sel["Product_ID"]))
        keep = lambda df: df[df.set_index(KEY).index.isin(marked)]  # noqa: E731
        save_table(keep(r["base_days"]), run_dir / sc / "baseline_daily_marked_lines.csv")
        for t, e in r["truths"].items():
            save_table(keep(e["days"]), run_dir / sc / t / "daily_marked_lines.csv")
            cols = ["revenue", "gross_profit", "sim_expired_units", "sim_unmet_units_illustrative"]
            per = e["days"].groupby(KEY)[cols].sum() - r["base_days"].groupby(KEY)[cols].sum()
            save_table(per.add_prefix("delta_").reset_index(), run_dir / sc / t / "line_deltas.csv")
    save_table(comp[comp.rule == "A1"].drop(columns=["rule", "source_run"]), run_dir / "comparison_table.csv")
    save_table(comp, run_dir / "comparison_original_vs_a1.csv")
    pref = preference(results)
    a1_out = {"prerequisites_passed": all(r["prerequisites"]["passed"] for r in results.values()),
              "hard_gates_passed": all(e["gates"]["passed"] for r in results.values() for e in r["truths"].values()),
              "adoption_thresholds_passed": all(v != "FAIL" for sc in PE.ADOPTION_SCENARIOS
                                                for v in results[sc]["thresholds"].values())}
    a1_out["result"] = ("MEETS_PREREGISTERED_RESEARCH_CRITERIA" if all(a1_out.values())
                        else "DOES_NOT_MEET_PREREGISTERED_RESEARCH_CRITERIA")
    a1_out["statement"] = ("Research result on synthetic data under assumed customer responses. Not commercial proof; "
                           "nothing is approved, proposed for live use or executed.")
    save_json({"evaluation_policy_id": policy["evaluation_policy_id"], "rule": "A1", "outcome": a1_out,
               "preference": pref, "original_reproduced": {f"{sc}/{t}": e["original"]["reproduced"]
                                                           for sc, r in results.items() for t, e in r["truths"].items()},
               "prerequisites": {sc: r["prerequisites"] for sc, r in results.items()},
               "hard_gates": {f"{sc}/{t}": {k: v for k, v in e["gates"].items()} for sc, r in results.items()
                              for t, e in r["truths"].items()},
               "thresholds": {sc: r["thresholds"] for sc, r in results.items()},
               "original_thresholds_recomputed": {sc: r["original_thresholds"] for sc, r in results.items()},
               "measures": {f"{sc}/{t}": e["measures"] for sc, r in results.items() for t, e in r["truths"].items()},
               "prerun_checks": checks_before, "postrun_checks": checks_after}, run_dir / "evaluation.json")
    code = config.PROJECT_ROOT / "src" / "dpe" / "decision"
    save_json({"run_id": run_id, "created_at": datetime.now().isoformat(timespec="seconds"),
               "step": "Phase 2 amendment A1 research evaluation: cooldown from the end of the previous markdown window "
                       "(SYNTHETIC; SIMULATED RESEARCH - NOT VALIDATED FOR LIVE USE)",
               "rule": "A1", "evaluation_policy": {"id": policy["evaluation_policy_id"], "sha256": PE._sha(POLICY_FILE)},
               "original_run": ORIGINAL_RUN.name, "replay_assumption_set": policy["scope"]["replay_assumption_set"],
               "pricing_assumption_set": policy["scope"]["pricing_assumption_set"],
               "protected_baseline_run": PE.PROTECTED_RUN.name, "forecast_contract_run": config.FORECAST_CONTRACT_RUN_ID,
               "simulator_version": RPA1.SIMULATOR_VERSION, "scenarios": list(results), "true_responses": list(PE.TRUTHS),
               "daily_outputs": "written only for lines with at least one A1 markdown (size); all gates ran on every daily row in memory",
               "status": "SIMULATED / HYPOTHETICAL_UNAPPROVED / NOT_EXECUTED: no order, price change, approval or integration exists",
               "code_sha256": {n: PE._sha(code / n) for n in ("replay.py", "replay_v12.py", "replay_pricing.py",
                                                              "replay_pricing_a1.py", "dynamic_pricing.py", "dynamic_pricing_a1.py",
                                                              "discount_recommendation.py", "pricing_evaluation.py",
                                                              "pricing_evaluation_a1.py", "assumptions_v8.py")}},
              run_dir / "manifest.json")
    return run_dir
