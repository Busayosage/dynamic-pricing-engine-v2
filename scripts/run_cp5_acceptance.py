"""Step 4B CP5 entry point: verify the protected CP3/CP4 runs, run the leakage tests, bootstrap the relative WAPE
improvement, evaluate the provisional gates and write everything to a new outputs/runs/<id>_cp5_acceptance folder.
Retrains, tunes, selects, deploys or promotes nothing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.forecast.acceptance import run_acceptance  # noqa: E402

if __name__ == "__main__":
    print(f"CP5 acceptance review written to: {run_acceptance()}")
