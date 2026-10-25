"""Step 5B-2 entry point: validate the assumption set, then run the chronological replay simulator (SYNTHETIC).

  run_replay_simulation.py worked-example   two series (store 505: White Sandwich Loaf, Semi-Skimmed Milk), SC1-SC3
  run_replay_simulation.py full             all 720 series, SC1-SC3, plus the SC1 sensitivity report

Writes a new outputs/runs/<id>_replay_* folder. No inventory, waste-risk or pricing recommendation engine; no database."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from dpe import config  # noqa: E402
from dpe.decision import assumptions as A  # noqa: E402
from dpe.decision import replay_run as RUN  # noqa: E402
from dpe.forecast.panel import load_verified_panel  # noqa: E402

WORKED_EXAMPLE = [(505, 1001), (505, 1025)]

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("worked-example", "full"):
        raise SystemExit(__doc__)
    from dpe.forecast.acceptance import _verify_run_checksums

    _verify_run_checksums(config.FORECAST_CONTRACT_RUN_ID)
    doc = A.load()
    panel, panel_info = load_verified_panel()
    contract = pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")
    series = WORKED_EXAMPLE if mode == "worked-example" else None
    t = time.perf_counter()
    results = RUN.run_scenarios(contract, panel, doc, series=series, trace=(mode == "worked-example"))
    sim_seconds = time.perf_counter() - t
    bad = {sc: r["conservation"] for sc, r in results.items()
           if not all(r["conservation"][k] for k in ("daily_balanced", "weekly_balanced", "closing_equals_next_opening",
                                                      "no_negative_values", "unmet_equals_demand_minus_sold"))}
    if bad:
        raise SystemExit(f"Integrity checks failed; nothing written: {bad}")
    approved = {sc: r["kpis"]["actions_with_approval_event"] for sc, r in results.items() if r["kpis"]["actions_with_approval_event"]}
    if approved:
        raise SystemExit(f"Simulated actions carry approval events; nothing written: {approved}")
    sens = directions = None
    if mode == "full":
        directions = RUN.directional_checks(contract, panel, doc)
        if not all(directions.values()):
            raise SystemExit(f"Directional checks failed; nothing written: {directions}")
        sens = RUN.sensitivity(contract, panel, doc)
    label = ("replay_worked_example" if mode == "worked-example" else "replay_simulation") + "_v1_1"
    run_dir = RUN.write_run(results, doc, label, sens=sens, directions=directions,
                            extra={"supersedes_for_review": config.REPLAY_WORKED_EXAMPLE_RUN_ID if mode == "worked-example"
                                   else config.REPLAY_SIMULATION_RUN_ID, "mode": mode, "series": "all" if series is None else [list(s) for s in series],
                                   "simulation_seconds_three_scenarios": round(sim_seconds, 2),
                                   "panel_verification": panel_info})
    if mode == "worked-example":
        for sc, r in results.items():
            r["result"]["sales_trace"].to_csv(run_dir / sc / "sales_trace.csv", index=False)
    print(f"Replay written to: {run_dir} ({sim_seconds:.1f} s for three scenarios)")
