"""Forecast scenarios: which target-week inputs, beyond history and the known calendar, are allowed.

S0 is the primary (deployable) forecast and uses no target-week commercial or weather values.
S1-S3 add target-week values that would only be known if supplied as plans (S1, S2) or that are
never known in advance (S3, a diagnostic "weather oracle"). In backtests the realised values stand
in for the plans; that is an explicit assumption recorded in every run manifest.
R0 (the reference-model replica) is built from dpe.reference_baseline at CP4 and is not defined here.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    # feature name -> panel column taken at the TARGET week (supplied plan or oracle value)
    target_week_inputs: dict = field(default_factory=dict)
    deployable: bool = True
    eligible_for_acceptance: bool = True
    assumption: str = ""


SCENARIOS = {
    "S0": Scenario(
        "S0", "No plans: sales history to the origin, static attributes and the known calendar only.",
        assumption="Regional holiday calendar is known in advance."),
    "S1": Scenario(
        "S1", "Promotion plan known: S0 plus the planned target-week discount.",
        {"plan_discount": "Discount_Percent"},
        assumption="A discount plan exists for the target week; in backtests the recorded discount stands in for it."),
    "S2": Scenario(
        "S2", "Full commercial plan: S1 plus planned target-week marketing spend and price.",
        {"plan_discount": "Discount_Percent", "plan_marketing": "Marketing_Spend", "plan_price": "Price"},
        assumption="Discount, marketing and price plans exist; recorded values stand in for them in backtests."),
    "S3": Scenario(
        "S3", "Weather oracle (diagnostic): S2 plus ACTUAL target-week weather. Not deployable.",
        {"plan_discount": "Discount_Percent", "plan_marketing": "Marketing_Spend", "plan_price": "Price",
         "oracle_temperature": "Avg_Temperature", "oracle_rainfall": "Rainfall"},
        deployable=False, eligible_for_acceptance=False,
        assumption="Uses recorded actual weather as a perfect forecast; for measuring information value only."),
}


def get_scenario(name: str) -> Scenario:
    if name not in SCENARIOS:
        raise KeyError(f"Unknown scenario {name!r}; expected one of {sorted(SCENARIOS)}")
    return SCENARIOS[name]
