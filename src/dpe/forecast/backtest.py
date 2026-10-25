"""CP3: chronological backtest folds and the training/test boundary for each fold and horizon.

Folds are non-overlapping blocks of TARGET weeks. For a fold starting at target week b and a
horizon h, the earliest test forecast is made at origin b - h. Anything used for training must
already be observed at that origin, so:

    training targets  <= b - h        (train_target_max)
    training origins  <= b - 2h       (= train_target_max - h)
    test targets       in [b, b + 3]  with origins = target - h

Both horizons are scored on the same target weeks. No model is trained in CP3; the training
selection is implemented and verified now so CP4 cannot change it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from dpe.forecast.features import MIN_HISTORY_WEEKS

FIRST_TEST_TARGET = 29
LAST_TEST_TARGET = 52
FOLD_WEEKS = 4
REFERENCE_WINDOW = (45, 52)  # the Oct 2025 holdout: targets 2024-11-04 .. 2024-12-23


@dataclass(frozen=True)
class Fold:
    fold: str
    test_start: int
    test_end: int


@dataclass(frozen=True)
class FoldPlan:
    fold: str
    horizon: int
    test_start: int
    test_end: int
    earliest_test_origin: int
    latest_test_origin: int
    train_target_min: int
    train_target_max: int
    train_origin_min: int
    train_origin_max: int


def make_folds(first_target: int = FIRST_TEST_TARGET, last_target: int = LAST_TEST_TARGET,
               fold_weeks: int = FOLD_WEEKS) -> list[Fold]:
    span = last_target - first_target + 1
    if span <= 0 or span % fold_weeks:
        raise ValueError(f"Target weeks {first_target}-{last_target} do not split into {fold_weeks}-week folds")
    return [Fold(f"F{i + 1}", s, s + fold_weeks - 1)
            for i, s in enumerate(range(first_target, last_target + 1, fold_weeks))]


def fold_plan(fold: Fold, horizon: int, min_history: int = MIN_HISTORY_WEEKS) -> FoldPlan:
    earliest_origin = fold.test_start - horizon
    plan = FoldPlan(fold.fold, horizon, fold.test_start, fold.test_end, earliest_origin, fold.test_end - horizon,
                    train_target_min=min_history + horizon, train_target_max=earliest_origin,
                    train_origin_min=min_history, train_origin_max=earliest_origin - horizon)
    if plan.train_origin_max < plan.train_origin_min:
        raise ValueError(f"{fold.fold} h={horizon}: no training origins with {min_history} weeks of history")
    return plan


def plan_table(folds: list[Fold], horizons) -> pd.DataFrame:
    return pd.DataFrame([asdict(fold_plan(f, h)) for h in horizons for f in folds])


def select_test_rows(features: pd.DataFrame, plan: FoldPlan) -> pd.DataFrame:
    """Forecast rows whose target week lies in the fold (origins = target - horizon)."""
    f = features[(features["horizon"] == plan.horizon)
                 & features["target_week"].between(plan.test_start, plan.test_end)].copy()
    f.insert(0, "fold", plan.fold)
    return f


def select_training_rows(features: pd.DataFrame, plan: FoldPlan) -> pd.DataFrame:
    """Labelled pairs observable at the fold's earliest test origin (used from CP4 onwards)."""
    f = features[(features["horizon"] == plan.horizon) & (features["target_week"] <= plan.train_target_max)
                 & (features["origin_week"] >= plan.train_origin_min)].copy()
    f.insert(0, "fold", plan.fold)
    return f


def assert_fold_boundaries(train: pd.DataFrame, test: pd.DataFrame, plan: FoldPlan) -> None:
    """Raise if any training target or origin could not have been observed at the earliest test origin."""
    if test.empty:
        raise AssertionError(f"{plan.fold} h={plan.horizon}: no test rows")
    if not test["target_week"].between(plan.test_start, plan.test_end).all():
        raise AssertionError(f"{plan.fold}: test targets outside the fold")
    if (test["origin_week"] != test["target_week"] - plan.horizon).any():
        raise AssertionError(f"{plan.fold}: test origin != target - horizon")
    if not train.empty:
        if train["target_week"].max() > plan.earliest_test_origin:
            raise AssertionError(f"{plan.fold} h={plan.horizon}: training target after the earliest test origin")
        if train["target_week"].max() >= plan.test_start:
            raise AssertionError(f"{plan.fold} h={plan.horizon}: training target inside or after the test period")
        if train["origin_week"].max() > plan.train_origin_max:
            raise AssertionError(f"{plan.fold} h={plan.horizon}: training origin too late")
        keys = ["Store_ID", "Product_ID", "target_week"]
        if not train[keys].merge(test[keys], on=keys).empty:
            raise AssertionError(f"{plan.fold} h={plan.horizon}: training and test share target rows")
