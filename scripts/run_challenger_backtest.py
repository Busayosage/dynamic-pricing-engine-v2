"""Step 4D Phase 2 entry point: the one-round challenger backtest (XGBoost, CatBoost, SES; S0; H1 and H4; six
folds) with the frozen Option A configurations. Writes a new outputs/runs/<id>_challenger_backtest folder.
Results are exploratory. Do not re-run to search for a better result: the experiment budget is one round."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.forecast.challenger_run import run_challenger_backtest  # noqa: E402

if __name__ == "__main__":
    print(f"Challenger backtest written to: {run_challenger_backtest()}")
