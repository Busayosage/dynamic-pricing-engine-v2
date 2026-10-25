"""Feature construction, chronological split and prediction output. No model training."""
import numpy as np
import pandas as pd
import pytest

from dpe import reference_baseline as rb
from conftest import N_WEEKS, SERIES_BASE


@pytest.fixture
def features(synthetic_inputs):
    return rb.build_features(*synthetic_inputs)


def test_week_labels_parse_to_mondays():
    df = pd.DataFrame({"Week_Number": [f"2024-W{w:02d}" for w in range(1, 53)]})
    out = rb._parse_week_date(df)
    assert out["WeekDate"].iloc[0] == pd.Timestamp("2024-01-01")
    assert out["WeekDate"].iloc[-1] == pd.Timestamp("2024-12-23")
    assert (out["WeekDate"].dt.dayofweek == 0).all()
    assert out["WeekDate"].is_unique


def test_ids_preserved_and_unique(features):
    for col in ("Store_ID", "Product_ID", "WeekDate"):
        assert col in features.columns
    assert not features.duplicated(subset=["Store_ID", "Product_ID", "WeekDate"]).any()


def test_rows_without_8_weeks_history_dropped(features):
    assert len(features) == len(SERIES_BASE) * (N_WEEKS - 8)


def test_lags_stay_within_each_series(features):
    for (store, product), base in SERIES_BASE.items():
        s = features[(features.Store_ID == store) & (features.Product_ID == product)]
        week = s["Units_Sold"] - base
        for lag in (1, 2, 4, 8):
            assert (s[f"lag_{lag}"] == base + week - lag).all(), (store, product, lag)


def test_rolling_features_exclude_current_week(features):
    s = features
    week_value = s["Units_Sold"]
    assert np.allclose(s["roll_mean_4"], week_value - 2.5)
    assert np.allclose(s["roll_mean_8"], week_value - 4.5)
    assert np.allclose(s["roll_std_4"], np.std([1, 2, 3, 4], ddof=1))


def test_chronological_split(features):
    train, valid = rb.temporal_split(features, n_val_weeks=2)
    assert train["WeekDate"].max() < valid["WeekDate"].min()
    assert valid["WeekDate"].nunique() == 2
    assert len(train) + len(valid) == len(features)


def test_feature_matrix_excludes_ids_target_and_leakage(features):
    X, y = rb.make_feature_matrix(features)
    for col in ("Units_Sold", "Wastage_Units", "Store_ID", "Product_ID", "WeekDate", "Region"):
        assert col not in X.columns
    assert len(X) == len(y) == len(features)


def test_prediction_frame_keeps_ids(features):
    _, valid = rb.temporal_split(features, n_val_weeks=2)
    preds = {"naive": rb.naive_last_week(valid, ["Store_ID", "Product_ID"]),
             "rf": np.zeros(len(valid))}
    out = rb.build_prediction_frame(valid, preds)
    assert list(out.columns) == ["Store_ID", "Product_ID", "WeekDate", "Units_Sold", "pred_naive", "pred_rf"]
    assert (out["pred_naive"] == valid["lag_1"].to_numpy()).all()


def test_prediction_frame_rejects_missing_ids_or_wrong_length(features):
    with pytest.raises(ValueError):
        rb.build_prediction_frame(features.drop(columns=["Store_ID"]), {"x": np.zeros(len(features))})
    with pytest.raises(ValueError):
        rb.build_prediction_frame(features, {"x": np.zeros(3)})


def test_metrics_formulas():
    y, p = np.array([10.0, 20.0]), np.array([12.0, 18.0])
    m = rb.metrics(y, p)
    assert m["MAE"] == pytest.approx(2.0) and m["RMSE"] == pytest.approx(2.0)
    e = rb.extra_metrics(y, p)
    assert e["WAPE"] == pytest.approx(4 / 30) and e["Bias"] == pytest.approx(0.0)
