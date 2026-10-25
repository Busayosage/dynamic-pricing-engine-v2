"""Step 5B-3e entry point: controlled P0/P1/P2 inventory policy comparison (SYNTHETIC, exploratory).

  run_policy_comparison.py

1. Pre-run integrity checks (frozen evaluation policy registered, source document, assumption sets, protected files).
   Any failure stops the script before anything is simulated.
2. Leakage, scramble and mutation tests of the suite (gate G3 d).
3. P1 regression against the protected v1.1 run (gate G3 f).
4. P0, P1 and P2 under SC1, SC2, SC3 and SF75 with assumption set v2 (DRAFT), each from a fresh state.
5. Hard gates, thresholds, protected checksums again (G3 g); then a new outputs/runs/<id>_policy_comparison folder.
No database, no Airtable, no GitHub; nothing is approved or executed."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from dpe import config  # noqa: E402
from dpe.decision import assumptions as A  # noqa: E402
from dpe.decision import assumptions_v2 as B  # noqa: E402
from dpe.decision import policy_comparison as PC  # noqa: E402
from dpe.forecast.panel import load_verified_panel  # noqa: E402

if __name__ == "__main__":
    t0 = time.perf_counter()
    checks = PC.prerun_checks()  # raises IntegrityError: nothing is run
    print("Pre-run checks passed:", json.dumps({k: v for k, v in checks.items() if k != "failed"}))
    policy = json.loads(PC.POLICY_FILE.read_text(encoding="utf-8"))
    leakage = PC.run_leakage_tests()
    print("Leakage tests:", leakage)
    panel, _ = load_verified_panel()
    contract = pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")
    v1doc, v2doc = A.load(), B.load()
    regression = PC.p1_regression(contract, panel, v1doc)
    print("P1 regression vs protected v1.1:", regression)
    results = PC.run_all(contract, panel, v2doc)
    p1_same = PC.p1_v2_matches_v1(results, contract, panel, v1doc)
    gates = {k: PC.hard_gates(e, contract) for k, e in results.items()}
    m = {k: PC.metrics(e) for k, e in results.items()}
    th = PC.thresholds(m, policy)
    after = PC.prerun_checks()  # G3 g: protected checksums still verify after the comparison
    run_dir = PC.write_run(results, gates, m, th, after, regression, p1_same, leakage, policy)
    print(f"Comparison written to: {run_dir} ({time.perf_counter() - t0:.0f} s)")
