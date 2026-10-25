"""Step 3C entry point: run the full EDA and write outputs to a new outputs/runs/<id>_eda folder.

Do not run until Step 3C-C3 is approved.
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.eda.pipeline import run_eda  # noqa: E402

if __name__ == "__main__":
    print(f"EDA outputs written to: {run_eda()}")
