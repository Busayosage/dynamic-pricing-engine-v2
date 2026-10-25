"""Amendment A1 evaluation run: preregistration, preserved original, safety gates and the original-vs-A1 comparison."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from dpe import config
from dpe.decision import pricing_evaluation_a1 as PA

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dashboard"))
import dashboard_data as D  # noqa: E402

A1_RUN = config.PROJECT_ROOT / "outputs" / "runs" / D.DYNAMIC_PRICING_A1_RUN_ID
ORIGINAL_RUN = config.PROJECT_ROOT / "outputs" / "runs" / D.DYNAMIC_PRICING_RUN_ID


@pytest.fixture(scope="module")
def ev():
    return json.loads((A1_RUN / "evaluation.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def comp():
    return pd.read_csv(A1_RUN / "comparison_original_vs_a1.csv")


def test_a1_policy_was_frozen_and_registered_and_the_original_is_preserved(registry_scope):
    policy = PA.load_policy()
    assert policy["status"] == "FROZEN_BEFORE_COMPARISON"
    assert policy["original_criteria"]["thresholds_per_adoption_scenario"] == json.loads(
        (config.PROJECT_ROOT / "config/evaluation/evaluation_policy_phase2_v1.json").read_text(encoding="utf-8"))[
        "thresholds_per_adoption_scenario"]  # the original criteria, unchanged
    checks = PA.prerun_checks()
    assert checks["all_passed"] and checks["a1_files_all_registered"] and checks["original_policy_unchanged"]
    expected = config.load_expected_checksums()
    for f in sorted(A1_RUN.rglob("*")) + sorted(ORIGINAL_RUN.rglob("*")):
        if f.is_file():
            rel = f.relative_to(config.PROJECT_ROOT).as_posix()
            assert expected[rel] == config.sha256_file(f), rel  # both runs registered and unchanged


def test_a1_run_is_new_and_versioned():
    man = json.loads((A1_RUN / "manifest.json").read_text(encoding="utf-8"))
    assert man["run_id"].endswith("_dynamic_pricing_evaluation_a1") and man["rule"] == "A1"
    assert man["simulator_version"] == "1.4" and man["original_run"] == ORIGINAL_RUN.name
    assert man["pricing_assumption_set"]["assumption_set_id"] == "AS-2026-10-23-v8" and "NOT_EXECUTED" in man["status"]


def test_baseline_original_and_safety_controls_all_verified(ev):
    assert all(p["passed"] for p in ev["prerequisites"].values())  # pricing off == protected P2; orders fixed; eligibility
    assert all(ev["original_reproduced"].values()) and len(ev["original_reproduced"]) == 16
    for run, g in ev["hard_gates"].items():
        for gate in ("G1_conservation", "G2_ordering_unchanged", "G3_markdown_only_and_price_bounds",
                     "G4_eligibility_and_timing_guards", "G5_chronology", "G6_labels_unapproved_not_executed",
                     "G8_a1_cooldown_from_window_end"):
            assert g[gate], (run, gate)
    assert ev["original_thresholds_recomputed"] == json.loads(
        (ORIGINAL_RUN / "evaluation.json").read_text(encoding="utf-8"))["thresholds"]


def test_original_rows_equal_the_frozen_original_run(comp):
    orig = pd.read_csv(ORIGINAL_RUN / "comparison_table.csv")
    o = comp[comp.rule == "ORIGINAL"].drop(columns=["rule", "source_run", "markdowns_blocked_by_cooldown"])
    pd.testing.assert_frame_equal(o.reset_index(drop=True)[orig.columns], orig, check_dtype=False)
    assert (comp[comp.rule == "ORIGINAL"]["markdowns_blocked_by_cooldown"] == 0).all()  # v7 cooldown never bound


def test_a1_changes_only_where_the_impact_analysis_said(comp):
    cols = ["markdown_events", "delta_gross_profit", "delta_sim_expired_units", "delta_sim_unmet_units_illustrative"]
    for sc in ("SC1", "SC2", "SF75"):  # no original selection is blocked by A1 there
        o = comp.query("scenario_id == @sc and rule == 'ORIGINAL'")[cols].reset_index(drop=True)
        a = comp.query("scenario_id == @sc and rule == 'A1'")[cols].reset_index(drop=True)
        pd.testing.assert_frame_equal(o, a)
    sc3 = comp.query("scenario_id == 'SC3' and rule == 'A1'")
    assert (sc3["markdowns_blocked_by_cooldown"] > 0).all()


def test_preference_outcome_follows_the_frozen_rule(ev):
    pref = ev["preference"]
    parts = [k for k in pref if k.startswith("P")]
    assert parts == ["PA_all_checks_and_gates", "PB_original_thresholds_met", "PC_no_larger_loss_weak_response",
                     "PD_keeps_75pct_of_central_benefit", "PE_no_more_unmet_units"]
    expected = "A1_PREFERRED_RESEARCH_COOLDOWN" if all(pref[k] for k in parts) else "ORIGINAL_RULE_RETAINED_AS_PREFERRED"
    assert pref["result"] == expected and pref["failed_parts"] == [k for k in parts if not pref[k]]
