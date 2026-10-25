"""Read-only data layer for the Dynamic Pricing Engine V2 dashboard MVP.

Every function READS existing protected outputs (forecast contract, forecasting backtest metrics, the Stage 5B-3e
policy comparison run) and the verified raw panel. Nothing here writes a file, runs a simulation, retrains a model or
creates a database. All inventory figures are SYNTHETIC replay values; recorded sales are illustrative demand, not
verified unconstrained demand; every proposal is HYPOTHETICAL_UNAPPROVED and NOT_EXECUTED.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from dpe import config  # noqa: E402

COMPARISON_DIR = config.POLICY_COMPARISON_RUN_DIR
CONTRACT_FILE = config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv"
FORECAST_METRICS_FILE = config.RF_BACKTEST_RUN_DIR / "metrics" / "pooled.csv"
FORECAST_CATEGORY_FILE = config.RF_BACKTEST_RUN_DIR / "metrics" / "by_Product_Category.csv"
CP5_MATRIX_FILE = config.CP5_ACCEPTANCE_RUN_DIR / "acceptance_matrix.csv"
PRODUCTS_FILE = config.RAW_DIR / "product_details.csv"
STORES_FILE = config.RAW_DIR / "store_info.csv"

POLICIES = ("P0", "P1", "P2")
SCENARIOS = ("SC1", "SC2", "SC3", "SF75")
SCENARIO_NAMES = {"SC1": "SC1 — Normal trading", "SC2": "SC2 — Demand / supply pressure",
                  "SC3": "SC3 — Excess stock / expiry pressure",
                  "SF75": "SF75 — 75% realised supplier fulfilment (stress test)"}
POLICY_NAMES = {"P0": "P0 — Historical-sales baseline", "P1": "P1 — Original forecast-informed (v1.1)",
                "P2": "P2 — Time-phased, expiry-aware (research default)"}
POLICY_COLORS = {"P0": "#2a78d6", "P1": "#eb6834", "P2": "#1baf7a"}  # reference palette slots 1-3, fixed order
SIMULATED_LABEL = "SIMULATED (synthetic replay) — not observed results"
STATUS_LABEL = "HYPOTHETICAL_UNAPPROVED · NOT_EXECUTED"
DAILY_GAP = ("Day-level stock is not saved in the protected comparison run (only weekly totals and every delivery with "
             "its arrival and expiry day). A safe read-only export would replay the protected configuration and write "
             "daily rows to a NEW run folder; it needs your approval and is not done here.")


def _run_file(scenario: str, policy: str, name: str) -> Path:
    if scenario not in SCENARIOS or policy not in POLICIES:
        raise ValueError(f"Unknown scenario/policy {scenario}/{policy}")
    return COMPARISON_DIR / scenario / policy / name


def parse_list(x) -> list:
    """Lists saved as text in the CSV outputs ("['A', 'B']" or "A|B")."""
    if isinstance(x, list):
        return x
    if not isinstance(x, str) or not x.strip():
        return []
    s = x.strip()
    if s.startswith("["):
        try:
            return list(ast.literal_eval(s))
        except (ValueError, SyntaxError):
            return [s]
    return [p for p in s.split("|") if p]


# ------------------------------------------------------------------------------------------- lookups
def products() -> pd.DataFrame:
    return pd.read_csv(PRODUCTS_FILE)


def stores() -> pd.DataFrame:
    return pd.read_csv(STORES_FILE)


def series_list() -> pd.DataFrame:
    """Store x product pairs present in the comparison run, with names."""
    w = pd.read_csv(_run_file("SC1", "P2", "weekly.csv"), usecols=["Store_ID", "Product_ID"]).drop_duplicates()
    return (w.merge(products()[["Product_ID", "Product_Name", "Product_Category"]], on="Product_ID")
             .merge(stores()[["Store_ID", "Region"]], on="Store_ID").sort_values(["Store_ID", "Product_ID"])
             .reset_index(drop=True))


# ---------------------------------------------------------------------------------------- forecasting
def forecast_metrics() -> pd.DataFrame:
    return pd.read_csv(FORECAST_METRICS_FILE)


def forecast_metrics_by_category() -> pd.DataFrame:
    return pd.read_csv(FORECAST_CATEGORY_FILE)


def acceptance_matrix() -> pd.DataFrame:
    return pd.read_csv(CP5_MATRIX_FILE)


def contract() -> pd.DataFrame:
    cols = ["horizon_weeks", "model_name", "store_id", "product_id", "origin_week", "origin_date", "target_week",
            "target_date", "predicted_units", "lower_p10_units", "median_p50_units", "upper_p90_units",
            "uncertainty_status", "risk_flags"]
    return pd.read_csv(CONTRACT_FILE, usecols=cols)


def sales_history(store_id: int, product_id: int) -> pd.DataFrame:
    """Recorded weekly sales for one series from the verified raw panel (illustrative demand)."""
    from dpe.forecast.panel import load_verified_panel

    panel, _ = load_verified_panel()
    s = panel[(panel["Store_ID"] == store_id) & (panel["Product_ID"] == product_id)]
    return s[["week_index", "WeekDate", "Units_Sold", "Wastage_Units", "Price", "Discount_Percent"]].reset_index(drop=True)


# ----------------------------------------------------------------------------------------- comparison
def comparison_table() -> pd.DataFrame:
    return pd.read_csv(COMPARISON_DIR / "comparison_table.csv")


def evaluation() -> dict:
    return json.loads((COMPARISON_DIR / "evaluation.json").read_text(encoding="utf-8"))


def manifest() -> dict:
    return json.loads((COMPARISON_DIR / "manifest.json").read_text(encoding="utf-8"))


def pct_change_table() -> pd.DataFrame:
    """P2 versus P1 (and P0 versus P1) percentage differences per scenario, from the saved comparison table."""
    t = comparison_table().set_index(["scenario_id", "policy_id"])
    rows = []
    for sc in SCENARIOS:
        base = t.loc[(sc, "P1")]
        for p in ("P0", "P2"):
            row = {"Scenario": sc, "Policy vs P1": p}
            for col, label in (("ordered_units", "Ordered"), ("unmet_units_illustrative", "Unmet (illustrative)"),
                               ("expired_units", "Expired"), ("weekly_cases", "Weekly review cases")):
                row[label] = round(100 * (t.loc[(sc, p), col] / base[col] - 1), 2)
            rows.append(row)
    return pd.DataFrame(rows)


def decisions(scenario: str, policy: str) -> pd.DataFrame:
    return pd.read_csv(_run_file(scenario, policy, "decisions.csv"))


def weekly(scenario: str, policy: str) -> pd.DataFrame:
    return pd.read_csv(_run_file(scenario, policy, "weekly.csv"))


def deliveries(scenario: str, policy: str) -> pd.DataFrame:
    return pd.read_csv(_run_file(scenario, policy, "deliveries.csv"))


def review_cases(scenario: str, policy: str) -> pd.DataFrame:
    """Saved review cases. P0/P1 use the v1.1 queue (one row per decision point, case_type may be empty);
    P2 uses queue v1.2 (only points that need review)."""
    c = pd.read_csv(_run_file(scenario, policy, "review_cases.csv"))
    if policy == "P2":
        c["reasons_list"] = c["reason_codes"].map(parse_list)
        c["warnings_list"] = c["warnings"].map(parse_list)
        c["review_status"] = c["status"]
    else:
        c = c[c["case_type"].notna()].copy()
        c["reasons_list"] = c["reasons"].map(parse_list)
        c["warnings_list"] = c["warnings"].map(parse_list)
        c["review_status"] = c["approval_status"]
        c["explanation"] = None
    return c.reset_index(drop=True)


def standing_cases(scenario: str) -> pd.DataFrame:
    return pd.read_csv(_run_file(scenario, "P2", "standing_cases.csv"))


def recommendations(scenario: str) -> pd.DataFrame:
    cols = ["recommendation_id", "store_id", "product_id", "origin_week", "target_week", "decision_date",
            "primary_category", "reason_codes", "warnings", "case_type", "proposed_order_units", "status",
            "execution_status", "approval_event_id", "explanation"]
    return pd.read_csv(_run_file(scenario, "P2", "recommendations.csv"), usecols=cols)


def scenario_totals(scenario: str) -> pd.DataFrame:
    t = comparison_table()
    return t[t["scenario_id"] == scenario].set_index("policy_id").loc[list(POLICIES)]


# -------------------------------------------------------------------------------------------- waste risk
def waste_risk_params() -> dict:
    from dpe.decision import assumptions_v3

    doc = assumptions_v3.load()
    return {**assumptions_v3.waste_risk_values(doc), "assumption_set_id": doc["assumption_set_id"],
            "assumption_status": doc["approval"]["status"]}


def recorded_panel() -> pd.DataFrame:
    from dpe.forecast.panel import load_verified_panel

    panel, _ = load_verified_panel()
    return panel[["Store_ID", "Product_ID", "week_index", "Units_Sold", "Wastage_Units", "Product_Category"]]


def waste_risk(scenario: str, policy: str) -> pd.DataFrame:
    """Advisory waste-risk assessment computed from saved outputs only (nothing is written)."""
    from dpe.decision import waste_risk as W

    a = W.assess(decisions(scenario, policy), deliveries(scenario, policy), weekly(scenario, policy), contract(),
                 recorded_panel(), review_cases(scenario, policy), waste_risk_params())
    names = series_list()[["Store_ID", "Product_ID", "Product_Name", "Region"]]
    wk = weekly(scenario, policy)[["Store_ID", "Product_ID", "week", "sim_expired_units"]].rename(
        columns={"week": "target_week", "sim_expired_units": "replay_expired_units_in_week"})
    return a.merge(names, on=["Store_ID", "Product_ID"], how="left").merge(wk, on=["Store_ID", "Product_ID", "target_week"], how="left")


def waste_category_comparison(scenario: str, policy: str) -> pd.DataFrame:
    from dpe.decision import waste_risk as W

    return W.category_comparison(recorded_panel(), weekly(scenario, policy), series_list().rename(
        columns={"Product_Category": "Product_Category"}))


# ----------------------------------------------------------------------------------------- markdown review
def markdown_params() -> dict:
    from dpe.decision import assumptions_v4

    doc = assumptions_v4.load()
    return {**assumptions_v4.markdown_values(doc), "assumption_set_id": doc["assumption_set_id"],
            "assumption_status": doc["approval"]["status"]}


def recorded_prices() -> pd.DataFrame:
    from dpe.forecast.panel import load_verified_panel

    panel, _ = load_verified_panel()
    return panel[["Store_ID", "Product_ID", "week_index", "Price", "Discount_Percent"]]


def markdown_review(scenario: str, policy: str) -> pd.DataFrame:
    """Read-only markdown review eligibility (state 1 only) from saved evidence; nothing is written."""
    from dpe.decision import markdown_eligibility as M

    a = M.assess(waste_risk(scenario, policy), decisions(scenario, policy), contract(), recorded_prices(), markdown_params())
    names = series_list()[["Store_ID", "Product_ID", "Product_Name", "Region"]]
    return a.merge(names, on=["Store_ID", "Product_ID"], how="left")


# ------------------------------------------------------------------------------------ pricing demonstration
def pricing_params() -> dict:
    from dpe.decision import assumptions_v5

    doc = assumptions_v5.load()
    return {**assumptions_v5.pricing_values(doc), "assumption_set_id": doc["assumption_set_id"],
            "assumption_status": doc["approval"]["status"], "assumption_content_sha256": assumptions_v5.A.content_sha256(doc)}


def reference_prices() -> pd.DataFrame:
    """Forecast-contract reference-price proxy (H1 rows), read-only."""
    c = pd.read_csv(CONTRACT_FILE, usecols=["store_id", "product_id", "origin_week", "horizon_weeks", "reference_price_asof"])
    c = c[c["horizon_weeks"] == 1].drop(columns="horizon_weeks")
    return c.rename(columns={"store_id": "Store_ID", "product_id": "Product_ID"})


def pricing_demo(scenario: str, policy: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    from dpe.decision import pricing_demo as PD

    md = markdown_review(scenario, policy)
    lines, opts = PD.assess(md, reference_prices(), pricing_params())
    names = series_list()[["Store_ID", "Product_ID", "Product_Name", "Region"]]
    return lines.merge(names, on=["Store_ID", "Product_ID"], how="left"), opts


# ----------------------------------------------------------------- discount recommendation (Phase 1, research)
def recommendation_params() -> dict:
    from dpe.decision import assumptions_v6

    doc = assumptions_v6.load()
    return {**assumptions_v6.recommendation_values(doc), "assumption_set_id": doc["assumption_set_id"],
            "assumption_status": doc["approval"]["status"],
            "assumption_content_sha256": assumptions_v6.A.content_sha256(doc)}


def discount_recommendations(scenario: str, policy: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """SIMULATED research ranking of markdown steps for eligible lines, computed in memory (nothing is written)."""
    from dpe.decision import discount_recommendation as R

    lines, outcomes = R.assess(markdown_review(scenario, policy), reference_prices(), contract(), recommendation_params())
    names = series_list()[["Store_ID", "Product_ID", "Product_Name", "Region"]]
    return lines.merge(names, on=["Store_ID", "Product_ID"], how="left"), outcomes


# ------------------------------------------------------------- dynamic pricing evaluation (Phase 2, research)
DYNAMIC_PRICING_RUN_ID = "20261023-233225_dynamic_pricing_evaluation"  # original Phase 2 rule (v7), frozen
DYNAMIC_PRICING_A1_RUN_ID = "20261024-002535_dynamic_pricing_evaluation_a1"  # amendment A1: cooldown from the end of the previous window (v8)
DYNAMIC_PRICING_RUNS = {"ORIGINAL": DYNAMIC_PRICING_RUN_ID, "A1": DYNAMIC_PRICING_A1_RUN_ID}
DYNAMIC_PRICING_DIR = config.PROJECT_ROOT / "outputs" / "runs" / DYNAMIC_PRICING_RUN_ID
TRUE_RESPONSES = ("R0_NO_RESPONSE", "R1_LOW", "R2_CENTRAL", "R3_HIGH")
RULE_DECISION_FILE = config.PROJECT_ROOT / "config" / "decisions" / "phase2_cooldown_rule_decision.json"
PREFERRED_RULE = "A1"  # DEC-PH2-COOLDOWN-2026-10-24-v1: preferred RESEARCH rule, NOT production approved
RULE_NAMES = {"ORIGINAL": "Original Phase 2 rule (v7) — cooldown counted between weekly decisions",
              "A1": "A1 cooldown rule (v8) — 7 complete days after the previous markdown ends"}


def _dp_dir(rule: str = "ORIGINAL") -> Path:
    return config.PROJECT_ROOT / "outputs" / "runs" / DYNAMIC_PRICING_RUNS[rule]


def dp_evaluation(rule: str = "ORIGINAL") -> dict:
    return json.loads((_dp_dir(rule) / "evaluation.json").read_text(encoding="utf-8"))


def dp_manifest(rule: str = "ORIGINAL") -> dict:
    return json.loads((_dp_dir(rule) / "manifest.json").read_text(encoding="utf-8"))


def dp_comparison(rule: str = "ORIGINAL") -> pd.DataFrame:
    return pd.read_csv(_dp_dir(rule) / "comparison_table.csv")


def dp_rule_comparison() -> pd.DataFrame:
    """Original vs A1, side by side, from the A1 run (the original rows reproduce the frozen original run)."""
    return pd.read_csv(_dp_dir("A1") / "comparison_original_vs_a1.csv")


def dp_decisions(scenario: str, truth: str, rule: str = "ORIGINAL") -> pd.DataFrame:
    d = pd.read_csv(_dp_dir(rule) / scenario / truth / "pricing_decisions.csv")
    names = series_list()[["Store_ID", "Product_ID", "Product_Name", "Region"]]
    return d.merge(names, on=["Store_ID", "Product_ID"], how="left")


def dp_daily(scenario: str, truth: str | None, rule: str = "ORIGINAL") -> pd.DataFrame:
    """Daily rows for lines with at least one simulated markdown; truth None = unchanged prices (baseline)."""
    f = _dp_dir(rule) / scenario / ("baseline_daily_marked_lines.csv" if truth is None else f"{truth}/daily_marked_lines.csv")
    return pd.read_csv(f)


def dp_line_deltas(scenario: str, truth: str, rule: str = "ORIGINAL") -> pd.DataFrame:
    return pd.read_csv(_dp_dir(rule) / scenario / truth / "line_deltas.csv")


def dp_rule_decision() -> dict:
    return json.loads(RULE_DECISION_FILE.read_text(encoding="utf-8"))


# ------------------------------------------------------------- waste interventions (Phase 3, advisory only)
def intervention_params() -> dict:
    from dpe.decision import assumptions_v9

    doc = assumptions_v9.load()
    return {**assumptions_v9.intervention_values(doc), "assumption_set_id": doc["assumption_set_id"],
            "assumption_status": doc["approval"]["status"], "assumption_content_sha256": assumptions_v9.A.content_sha256(doc)}


def waste_interventions(scenario: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Advisory intervention assessment for the protected P2 replay, computed in memory (nothing is written)."""
    from dpe.decision import waste_interventions as WI

    phase1, _ = discount_recommendations(scenario, "P2")
    stores = pd.read_csv(STORES_FILE)
    lines, options = WI.assess(waste_risk(scenario, "P2"), decisions(scenario, "P2"), markdown_review(scenario, "P2"),
                               phase1, dp_decisions(scenario, "R2_CENTRAL", "A1"), reference_prices(), stores,
                               intervention_params())
    names = series_list()[["Store_ID", "Product_ID", "Product_Name"]]
    return lines.merge(names, on=["Store_ID", "Product_ID"], how="left"), options
