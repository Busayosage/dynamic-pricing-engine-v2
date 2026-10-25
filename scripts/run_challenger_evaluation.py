"""Step 4D Phase 3 entry point: evaluate the challenger run against the incumbents (H1 Random Forest, H4 four-week
moving average) under docs/STEP_4D_REPLACEMENT_POLICY.md. Writes a new outputs/runs/<id>_challenger_evaluation
folder. Retrains, tunes, selects, deploys or promotes nothing.

Usage: run_challenger_evaluation.py <challenger run folder name>"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.config import OUTPUT_ROOT  # noqa: E402
from dpe.forecast.challenger_eval import run_challenger_evaluation  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: run_challenger_evaluation.py <challenger run folder name>")
    print(f"Challenger evaluation written to: {run_challenger_evaluation(OUTPUT_ROOT / sys.argv[1])}")
