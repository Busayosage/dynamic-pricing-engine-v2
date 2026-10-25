"""CP4: Random Forest wrapper with training-only preprocessing.

- Settings are the original reference configuration (300 trees, max depth 12, seed 42), imported
  from dpe.reference_baseline so they cannot drift; they are not tuned.
- The only learned transformation is the one-hot encoding of the identity columns. Its category
  lists are fitted on each fold's TRAINING rows and then applied unchanged to the test rows; a
  category never seen in training raises instead of being silently encoded. No imputer or scaler
  is used: eligible rows have no missing values (CP2) and trees need no scaling.
- Forecasts are clipped at zero (units cannot be negative).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from dpe.forecast.features import STATIC_CATEGORICAL, model_matrix
from dpe.reference_baseline import RF_PARAMS as _REFERENCE_RF_PARAMS

RF_PARAMS = dict(_REFERENCE_RF_PARAMS)  # {"n_estimators": 300, "max_depth": 12, "n_jobs": -1, "random_state": 42}
CP4_SCENARIOS = ("S0",)  # S1-S3 and R0 are not run in CP4


class TrainOnlyEncoder:
    """One-hot category lists learned from training rows only."""

    def __init__(self, scenario: str = "S0"):
        if scenario not in CP4_SCENARIOS:
            raise ValueError(f"Scenario {scenario} is not enabled in CP4 (only {CP4_SCENARIOS})")
        self.scenario = scenario
        self.categories: dict[str, list] | None = None
        self.columns: list[str] | None = None

    def fit(self, train: pd.DataFrame) -> "TrainOnlyEncoder":
        self.categories = {c: sorted(train[c].unique().tolist()) for c in STATIC_CATEGORICAL}
        self.columns = list(model_matrix(train.head(1), self.scenario, self.categories).columns)
        return self

    def transform(self, features: pd.DataFrame) -> pd.DataFrame:
        if self.categories is None:
            raise RuntimeError("Encoder must be fitted on training rows first")
        X = model_matrix(features, self.scenario, self.categories)
        if list(X.columns) != self.columns:
            raise AssertionError("Transformed columns differ from the fitted training columns")
        return X


def fit_rf(X: pd.DataFrame, y, params: dict | None = None):
    from sklearn.ensemble import RandomForestRegressor

    model = RandomForestRegressor(**(params or RF_PARAMS))
    model.fit(X, np.asarray(y, dtype=float))
    return model


def predict(model, X: pd.DataFrame) -> np.ndarray:
    yhat = np.clip(model.predict(X), 0.0, None)
    if not np.isfinite(yhat).all():
        raise ValueError("Non-finite forecasts")
    return yhat
