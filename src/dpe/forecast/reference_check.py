"""CP3: row-by-row check of the H1 last-week baseline against the original naive benchmark.

Only H1 targets in weeks 45-52 are comparable: the original naive forecast for target week t is
lag_1 = units sold in week t-1 of the same series, i.e. the same origin (t-1), the same target and
the same definition as the H1 last-week baseline. H4 has no equivalent original benchmark.

Two historical files are read (never written):
- outputs/runs/20261021-133846_reference_rf/validation_predictions.csv  (V2 reproduction; has IDs)
- data/reference/validation_predictions.csv                              (Oct 2025 original; no IDs)
The original has no Store_ID/Product_ID, so it is compared by row position with the reproduction,
which Step 3B verified to be aligned with it row by row.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from dpe.config import PROJECT_ROOT, REFERENCE_DIR, VERIFIED_RUN_DIR
from dpe.forecast.backtest import REFERENCE_WINDOW

REPRODUCED_FILE = VERIFIED_RUN_DIR / "validation_predictions.csv"
ORIGINAL_FILE = REFERENCE_DIR / "validation_predictions.csv"


def _rel(path) -> str:
    try:
        return Path(path).resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def reference_naive_check(predictions: pd.DataFrame, reproduced_file: Path = REPRODUCED_FILE,
                          original_file: Path = ORIGINAL_FILE) -> dict:
    lo, hi = REFERENCE_WINDOW
    ours = predictions[(predictions["model"] == "last_week") & (predictions["horizon"] == 1)
                       & predictions["target_week"].between(lo, hi)]
    rep = pd.read_csv(reproduced_file, parse_dates=["WeekDate"])
    m = ours.merge(rep, left_on=["Store_ID", "Product_ID", "target_date"],
                   right_on=["Store_ID", "Product_ID", "WeekDate"], how="outer", indicator=True)
    both = m[m["_merge"] == "both"]
    diff = (both["forecast"] - both["pred_naive"]).abs()
    keyed = {
        "file": _rel(reproduced_file),
        "rows_ours": int(len(ours)), "rows_reference": int(len(rep)),
        "rows_matched_on_store_product_target_date": int(len(both)),
        "rows_only_ours": int((m["_merge"] == "left_only").sum()),
        "rows_only_reference": int((m["_merge"] == "right_only").sum()),
        "actuals_equal": bool((both["actual"] == both["Units_Sold"]).all()),
        "origin_is_target_minus_1_week": bool(((both["target_week"] - both["origin_week"]) == 1).all()
                                              and ((both["target_date"] - both["origin_date"])
                                                   == pd.Timedelta(weeks=1)).all()),
        "forecast_rows_equal": int((diff == 0).sum()),
        "forecast_rows_different": int((diff != 0).sum()),
        "max_abs_forecast_difference": float(diff.max()) if len(diff) else float("nan"),
    }
    keyed["equivalent"] = bool(keyed["rows_only_ours"] == 0 and keyed["rows_only_reference"] == 0
                               and keyed["actuals_equal"] and keyed["origin_is_target_minus_1_week"]
                               and keyed["forecast_rows_different"] == 0)

    orig = pd.read_csv(original_file, parse_dates=["WeekDate"])
    same_len = len(orig) == len(rep)
    positional = {
        "file": _rel(original_file),
        "has_store_product_ids": bool({"Store_ID", "Product_ID"} <= set(orig.columns)),
        "rows": int(len(orig)),
        "same_row_count_as_reproduction": bool(same_len),
        "dates_equal_by_position": bool(same_len and (orig["WeekDate"].to_numpy() == rep["WeekDate"].to_numpy()).all()),
        "actuals_equal_by_position": bool(same_len and (orig["Units_Sold"].to_numpy() == rep["Units_Sold"].to_numpy()).all()),
        "naive_max_abs_difference_by_position": float(np.max(np.abs(orig["pred_naive"].to_numpy()
                                                                    - rep["pred_naive"].to_numpy())))
        if same_len else float("nan"),
    }
    positional["equivalent_to_reproduction"] = bool(
        positional["dates_equal_by_position"] and positional["actuals_equal_by_position"]
        and positional["naive_max_abs_difference_by_position"] == 0)

    return {
        "scope": f"H1 last_week baseline, target weeks {lo}-{hi} (2024-11-04 to 2024-12-23)",
        "definition_match": "original naive = lag_1 = units in week t-1 of the same series = H1 last_week "
                            "(origin t-1, target t)",
        "keyed_vs_v2_reproduction": keyed,
        "positional_vs_oct_2025_original": positional,
        "equivalent": bool(keyed["equivalent"] and positional["equivalent_to_reproduction"]),
        "not_compared": {
            "H4": "No original 4-week-ahead benchmark exists; the original naive is a one-week-ahead forecast.",
            "mean_4w": "The original project had no four-week-average baseline.",
            "folds_F1_F4": "The original holdout covered target weeks 45-52 only.",
        },
    }
