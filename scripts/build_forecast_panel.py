"""Step 4B CP1 entry point: build, validate and reconcile the forecasting panel, then save it to a new
outputs/runs/<id>_forecast_panel folder. Trains no model."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.config import verify_raw_inputs  # noqa: E402
from dpe.forecast.panel import EXPECTED, build_panel, reconcile_with_eda, validate_panel, write_panel_run  # noqa: E402

if __name__ == "__main__":
    hashes = verify_raw_inputs()
    panel = build_panel()
    validate_panel(panel, expected=EXPECTED)
    rec = reconcile_with_eda(panel)
    if not rec["reconciled"]:
        raise SystemExit(f"Panel does not reconcile with the final EDA run: {rec}")
    print(f"Forecast panel written to: {write_panel_run(panel, rec, input_hashes=hashes)}")
