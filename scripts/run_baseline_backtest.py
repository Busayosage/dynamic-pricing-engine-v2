"""Step 4B CP3 entry point: score the last-week and 4-week-average baselines for H1 and H4 on the six
backtest folds, check the original naive benchmark, and save everything to a new
outputs/runs/<id>_baseline_backtest folder. Trains no model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.forecast.pipeline import run_baseline_backtest  # noqa: E402

if __name__ == "__main__":
    print(f"Baseline backtest written to: {run_baseline_backtest()}")
