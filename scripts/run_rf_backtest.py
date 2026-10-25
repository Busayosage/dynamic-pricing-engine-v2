"""Step 4B CP4 entry point: train the S0 Random Forest (original configuration, no tuning) for H1 and
H4 on the six backtest folds, score it with both baselines on identical rows, and save everything to a
new outputs/runs/<id>_rf_backtest folder. Selects, deploys or promotes nothing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.forecast.rf_backtest import run_rf_backtest  # noqa: E402

if __name__ == "__main__":
    print(f"Random Forest backtest written to: {run_rf_backtest()}")
