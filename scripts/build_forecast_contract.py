"""Step 5B-1 entry point: build the forecast contract (H1 Random Forest, H4 four-week moving average) from the protected
out-of-sample predictions, validate it, and save it to a new outputs/runs/<id>_forecast_contract folder.
Retrains nothing; writes no database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.decision.forecast_contract import run_forecast_contract  # noqa: E402

if __name__ == "__main__":
    print(f"Forecast contract written to: {run_forecast_contract()}")
