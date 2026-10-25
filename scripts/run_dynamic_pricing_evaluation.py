"""Phase 2 entry point: dynamic pricing research evaluation against unchanged prices (SYNTHETIC).

  run_dynamic_pricing_evaluation.py

1. Pre-run integrity checks: frozen evaluation policy EP-PH2-2026-10-23-v1 registered, its source document, assumption
   sets v2 and v7, every protected file. Any failure stops the script before anything is simulated.
2. Per scenario (SC1, SC2, SC3, SF75): pricing off (must reproduce the protected P2 run exactly), the fixed-order
   no-markdown check and the in-loop eligibility check. Any failure stops the script: no pricing run is made.
3. Pricing on under each true response (none, low, central, high) with orders fixed to the pricing-off pass.
4. Hard gates, preregistered thresholds, protected checksums again; then ONE new outputs/runs/<id>_dynamic_pricing_evaluation.
No database, no Airtable, no GitHub, no price change; nothing is approved or executed."""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "app" / "dashboard")]

import pandas as pd  # noqa: E402

from dpe import config  # noqa: E402
from dpe.decision import assumptions_v2 as B  # noqa: E402
from dpe.decision import assumptions_v7 as V7  # noqa: E402
from dpe.decision import pricing_evaluation as PE  # noqa: E402
from dpe.forecast.panel import load_verified_panel  # noqa: E402
import dashboard_data as D  # noqa: E402  - saved Markdown review (read-only) for the E3 check

if __name__ == "__main__":
    t0 = time.perf_counter()
    checks = PE.prerun_checks()
    print("Pre-run checks passed:", json.dumps({k: v for k, v in checks.items() if k != "failed"}))
    policy = PE.load_policy()
    panel, _ = load_verified_panel()
    contract = pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")
    v2doc, params = B.load(), V7.dynamic_pricing_values(V7.load())
    results = {}
    for sc in PE.SCENARIOS:
        t = time.perf_counter()
        results[sc] = PE.run_scenario(sc, contract, panel, v2doc, params, saved_markdown=D.markdown_review(sc, "P2"))
        print(f"{sc}: prerequisites {results[sc]['prerequisites']['passed']}, gates "
              f"{ {k: e['gates']['passed'] for k, e in results[sc]['truths'].items()} }, "
              f"thresholds {results[sc]['thresholds']} ({time.perf_counter() - t:.0f} s)")
    after = PE.prerun_checks()
    run_dir = PE.write_run(results, checks, after, policy, contract)
    print("Outcome:", PE.outcome(results))
    print(f"Evaluation written to: {run_dir} ({time.perf_counter() - t0:.0f} s)")
