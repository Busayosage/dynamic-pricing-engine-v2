"""Amendment A1 entry point: original Phase 2 cooldown rule vs A1 vs unchanged prices (SYNTHETIC).

  run_dynamic_pricing_evaluation_a1.py

1. Pre-run integrity checks: frozen policy EP-PH2-A1-2026-10-24-v1, its source document, the unchanged original
   policy and run, assumption sets v2 and v8, the registered A1 files, every protected file. Any failure stops here.
2. Per scenario: pricing off must reproduce the protected P2 replay; fixed orders and in-loop eligibility checks.
   Any failure stops the script: no pricing run is made.
3. Per true response: the frozen original (v1.3, v7) is re-run and must reproduce the protected original decisions;
   A1 (v1.4, v8) is run with the same fixed orders.
4. Original gates and thresholds applied to A1 unchanged, gate G8, the preregistered preference rule, protected
   checksums again; then ONE new outputs/runs/<id>_dynamic_pricing_evaluation_a1.
Nothing is approved, priced live or executed; no database, Airtable or GitHub."""
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
from dpe.decision import assumptions_v8 as V8  # noqa: E402
from dpe.decision import pricing_evaluation as PE  # noqa: E402
from dpe.decision import pricing_evaluation_a1 as PA  # noqa: E402
from dpe.forecast.panel import load_verified_panel  # noqa: E402
import dashboard_data as D  # noqa: E402  - saved Markdown review (read-only) for the E3 check

if __name__ == "__main__":
    t0 = time.perf_counter()
    checks = PA.prerun_checks()
    print("Pre-run checks passed:", json.dumps({k: v for k, v in checks.items() if k not in ("failed", "a1_files_registered")}))
    policy = PA.load_policy()
    panel, _ = load_verified_panel()
    contract = pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")
    v2doc = B.load()
    p7, p8 = V7.dynamic_pricing_values(V7.load()), V8.dynamic_pricing_values(V8.load())
    results = {}
    for sc in PE.SCENARIOS:
        t = time.perf_counter()
        results[sc] = PA.run_scenario(sc, contract, panel, v2doc, p7, p8, D.markdown_review(sc, "P2"))
        r = results[sc]
        print(f"{sc}: prerequisites {r['prerequisites']['passed']}, original reproduced "
              f"{ {k: e['original']['reproduced'] for k, e in r['truths'].items()} }, A1 gates "
              f"{ {k: e['gates']['passed'] for k, e in r['truths'].items()} }, A1 thresholds {r['thresholds']} "
              f"({time.perf_counter() - t:.0f} s)")
    after = PA.prerun_checks()
    run_dir = PA.write_run(results, checks, after, policy)
    print("Preference:", json.dumps(PA.preference(results), default=float))
    print(f"A1 evaluation written to: {run_dir} ({time.perf_counter() - t0:.0f} s)")
