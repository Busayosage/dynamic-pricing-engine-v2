"""Stage 5B-3e: comparison machinery on the synthetic fixtures (no real comparison is run by the tests)."""
from __future__ import annotations

import copy
import json

import pytest

from conftest import fake_contract_predictions, forecast_raw
from dpe import config
from dpe.decision import assumptions_v2 as B
from dpe.decision import forecast_contract as FC
from dpe.decision import policy_comparison as PC
from dpe.forecast.panel import build_panel


@pytest.fixture(scope="module")
def setup():
    panel = build_panel(forecast_raw())
    contract = FC.build_contract(fake_contract_predictions(panel), panel, "TEST")["contract"]
    results = PC.run_all(contract, panel, B.load())
    return contract, panel, results


@pytest.fixture(scope="module")
def policy():
    return json.loads(PC.POLICY_FILE.read_text(encoding="utf-8"))


def test_evaluation_policy_is_frozen_and_registered(policy):
    expected = config.load_expected_checksums()
    rel = PC.POLICY_FILE.relative_to(config.PROJECT_ROOT).as_posix()
    assert expected[rel] == PC._sha(PC.POLICY_FILE)
    assert expected[policy["source"]["document"]] == policy["source"]["document_sha256"]
    assert policy["status"] == "FROZEN_BEFORE_COMPARISON" and "exploratory" in policy["source"]["preliminary_exposure"]
    t = policy["comparison_thresholds_p2_vs_p1"]
    assert [t["T_U_simulated_unmet_units_illustrative"][s]["max_ratio_to_P1"] for s in ("SC1", "SC2", "SC3")] == [1.00, 1.02, 1.02]
    assert [t["T_E_simulated_expired_units"][s]["max_ratio_to_P1"] for s in ("SC1", "SC2", "SC3")] == [1.05, 1.05, 1.05]
    assert [t["T_O_total_ordered_units"][s]["max_ratio_to_P1"] for s in ("SC1", "SC2", "SC3")] == [1.05, 1.10, 1.10]
    assert t["T_R_review_workload"]["all"]["max_ratio_to_P1"] == 1.10
    assert policy["scope"]["stress_scenarios"] == ["SF75"]


def test_prerun_checks_pass_and_fail_closed(monkeypatch, registry_scope):
    assert PC.prerun_checks()["all_passed"]
    real = PC._sha
    monkeypatch.setattr(PC, "_sha", lambda p: "0" * 64 if p == PC.POLICY_FILE else real(p))
    with pytest.raises(PC.IntegrityError):
        PC.prerun_checks()


def test_every_run_is_independent_and_complete(setup):
    _, _, results = setup
    assert set(results) == {(p, s) for p in ("P0", "P1", "P2") for s in PC.SCENARIOS}
    ids = [id(e["result"]["decisions"]) for e in results.values()]
    assert len(set(ids)) == len(ids)
    for (p, sc), e in results.items():
        assert set(e["result"]["decisions"]["policy_id"]) == {p} and set(e["result"]["decisions"]["scenario_id"]) == {sc}


def test_hard_gates_pass_on_the_synthetic_fixtures(setup):
    contract, _, results = setup
    for k, e in results.items():
        g = PC.hard_gates(e, contract)
        assert g["passed"], (k, g)


def test_gates_detect_violations(setup):
    contract, _, results = setup
    e = copy.deepcopy(results[("P2", "SC1")])
    e["result"]["decisions"].loc[0, "action_status"] = "APPROVED"
    assert not PC.hard_gates(e, contract)["G3"]["a_no_approval_or_execution"]
    e = copy.deepcopy(results[("P1", "SC1")])
    first = e["result"]["deliveries"].query("kind == 'ORDER'").index[0]
    e["result"]["deliveries"].loc[first, "ordered_units"] += 1
    assert not PC.hard_gates(e, contract)["G2"]["b_whole_cases_at_least_moq"]
    e = copy.deepcopy(results[("P0", "SC2")])
    e["result"]["daily"].loc[0, "sim_closing_units"] += 1
    assert not PC.hard_gates(e, contract)["passed"]


def test_metrics_and_thresholds_are_computed_individually(setup, policy):
    _, _, results = setup
    m = {k: PC.metrics(e) for k, e in results.items()}
    th = PC.thresholds(m, policy)
    for sc in ("SC1", "SC2", "SC3"):
        assert set(th[sc]) == {"T_U", "T_E", "T_O", "T_R", "T_S", "T_X_report", "passed"}
        assert th[sc]["passed"] == all(th[sc][k]["passed"] for k in ("T_U", "T_E", "T_O", "T_R", "T_S"))
        for k in ("T_U", "T_E", "T_O"):
            assert th[sc][k]["limit"] in (1.0, 1.02, 1.05, 1.1)
    assert "SF75" not in th  # stress assessment only
    for k, x in m.items():
        assert x["ordered_units"] >= 0 and x["rounding_excess_units"] >= 0


def test_write_run_serialises_everything(setup, policy):
    import shutil
    import uuid

    contract, _, results = setup
    gates = {k: PC.hard_gates(e, contract) for k, e in results.items()}
    m = {k: PC.metrics(e) for k, e in results.items()}
    th = PC.thresholds(m, policy)
    run_id = f"_pytest_{uuid.uuid4().hex}_policy_comparison"
    run_dir = PC.write_run(results, gates, m, th, {"all_passed": True}, {"SC1": {"decisions": True}}, {"SC1": True},
                           {"passed": True}, policy, run_id=run_id)
    try:
        ev = json.loads((run_dir / "evaluation.json").read_text(encoding="utf-8"))
        assert set(ev) == {"hard_gates", "thresholds", "p1_regression_vs_protected_v11", "p1_v2_equals_v1", "leakage_tests",
                           "prerun_checks", "outcome"}
        assert (run_dir / "SF75" / "P2" / "recommendations.csv").exists() and (run_dir / "manifest.json").exists()
    finally:
        shutil.rmtree(run_dir)


def test_comparison_run_is_recorded_unchanged_and_write_blocked():
    expected = {k: v for k, v in config.load_expected_checksums().items()
                if k.startswith(f"outputs/runs/{config.POLICY_COMPARISON_RUN_ID}/")}
    assert len(expected) == 59
    for rel, digest in expected.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(config.UnsafeWriteError):
        config.assert_safe_output(config.POLICY_COMPARISON_RUN_DIR / "manifest.json")
    ev = json.loads((config.POLICY_COMPARISON_RUN_DIR / "evaluation.json").read_text(encoding="utf-8"))
    assert ev["prerun_checks"]["all_passed"] and ev["leakage_tests"]["passed"]
    assert all(all(x.values()) for x in ev["p1_regression_vs_protected_v11"].values())
    assert all(g["passed"] for g in ev["hard_gates"].values())
