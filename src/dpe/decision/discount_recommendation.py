"""Phase 1: numerical discount recommendation engine (SIMULATED RESEARCH — NOT VALIDATED FOR LIVE USE).

For each line that Stage 7B marks ELIGIBLE_FOR_MARKDOWN_REVIEW, compares every permitted markdown step with keeping
the full price under explicitly ASSUMED demand-response scenarios, and returns either one illustrative top-ranked
option or NO RECOMMENDATION with the reason. Pure and deterministic: no I/O, no randomness, nothing approved,
proposed or executed. Design and worked example: docs/PHASE_1_DISCOUNT_RECOMMENDATION_ENGINE.md; parameters from
assumption set v6 (DRAFT).

Inputs per line (all labelled): base price P0 (ESTIMATED reference-price proxy), unit cost C = P0 x (1 - margin)
(ASSUMED margin), at-risk units X (SIMULATED stock x FORECAST demand: units projected to expire at full price), the
markdown window W days (investigate-by day to the oldest batch's last sellable day, SIMULATED), and the protected
1-week forecast quantiles q10/q50/q90 (FORECAST).

Model for markdown d (fraction) and response r (% more units per markdown point), baseline quantile q:
  S0     = q / 7 x W                       full-price units sold in the window anyway
  extra  = min(S0 x r x 100d / 100, X)     additional units sold, only out of the at-risk stock
  sold   = S0 + extra ; expired = X - extra
  GP(d)  = sold x P0(1 - d) - C x (S0 + X) - expired x C x disposal%     (stock in scope is already bought)
  delta  = GP(d) - GP(0)
Decision (in order): line evidence gates -> option constraints (pricing_demo.options) -> materiality of the
weighted expected delta over R1..R3 at q50 -> downside guard (delta under the downside scenario at q90 must not lose
more than the stated share of the at-risk stock cost) -> rank by expected delta, then smaller downside loss, then the
smaller markdown. R0 (no response) is a stress test reported for every option and never weighted.
"""
from __future__ import annotations

import math

import pandas as pd

from dpe.decision import pricing_demo as PD

LABEL = "SIMULATED RESEARCH RECOMMENDATION — NOT VALIDATED FOR LIVE USE"
RECOMMEND = "SIMULATED_RESEARCH_RECOMMENDATION"
KEEP = "NO_RECOMMENDATION_KEEP_FULL_PRICE"
UNCERTAIN = "NO_RECOMMENDATION_TOO_UNCERTAIN"
CONSTRAINED = "NO_RECOMMENDATION_NO_PERMITTED_OPTION"
EVIDENCE = "NO_RECOMMENDATION_INSUFFICIENT_EVIDENCE"
NOT_ELIGIBLE = "NOT_ASSESSED_NOT_ELIGIBLE"
STATUS_LABELS = {
    RECOMMEND: "Simulated research recommendation",
    KEEP: "No recommendation — keeping the full price ranks first",
    UNCERTAIN: "No recommendation — outcome too uncertain",
    CONSTRAINED: "No recommendation — every markdown step is blocked by a rule",
    EVIDENCE: "No recommendation — evidence missing or conflicting",
    NOT_ELIGIBLE: "Not assessed — not eligible for markdown review",
}
EVIDENCE_LABELS = {
    "MISSING_BASE_PRICE_OR_MARGIN": "Reference price or assumed category margin missing",
    "MISSING_FORECAST_QUANTILES": "Forecast range (p10/p50/p90) unavailable, so uncertainty cannot be assessed",
    "MISSING_AT_RISK_UNITS": "No projection of stock at risk of expiry",
    "MISSING_MARKDOWN_WINDOW": "No dated batch evidence to define the markdown window",
    "PRICE_EVIDENCE_CONFLICT": "Recorded shelf price that week conflicts with the reference price",
}
CASES = (  # (case id, response scenario, baseline quantile, role)
    ("R0@p50", "R0_NO_RESPONSE", "p50", "stress"),
    ("R1@p50", "R1_LOW", "p50", "decision"),
    ("R2@p50", "R2_CENTRAL", "p50", "decision"),
    ("R3@p50", "R3_HIGH", "p50", "decision"),
    ("R2@p10", "R2_CENTRAL", "p10", "demand band"),
    ("R2@p90", "R2_CENTRAL", "p90", "demand band"),
)
SCENARIO_LABELS = {"R0_NO_RESPONSE": "No response (stress test)", "R1_LOW": "Low response",
                   "R2_CENTRAL": "Central response (historical association — not causal)", "R3_HIGH": "High response"}
EVIDENCE_QUALITY = ("LOW — every commercial input is estimated or assumed, stock and expiry are simulated, and the "
                    "demand response is a stated scenario, not a measured elasticity")
TOL = 1e-9


def _bad(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def outcome(base_price: float, unit_cost: float, markdown_pct: float, baseline_units: float, at_risk_units: float,
            response_pct_per_point: float, disposal_pct: float = 0.0) -> dict:
    """Window outcome for one markdown step under one response scenario. Raises ValueError on unusable inputs."""
    for name, v in (("base price", base_price), ("unit cost", unit_cost), ("baseline units", baseline_units),
                    ("at-risk units", at_risk_units), ("response", response_pct_per_point)):
        if _bad(v):
            raise ValueError(f"{name} missing")
    if base_price <= 0:
        raise ValueError("base price must be positive")
    if unit_cost < 0 or unit_cost >= base_price:
        raise ValueError("unit cost must be non-negative and below the base price")
    if not 0 <= markdown_pct < 100:
        raise ValueError("markdown must be in [0, 100)")
    if baseline_units < 0 or at_risk_units < 0 or response_pct_per_point < 0:
        raise ValueError("units and response must be non-negative")
    price = base_price * (1 - markdown_pct / 100)
    extra = min(baseline_units * response_pct_per_point * markdown_pct / 100, at_risk_units)
    sold, expired = baseline_units + extra, at_risk_units - extra
    revenue = sold * price
    gp = revenue - unit_cost * (baseline_units + at_risk_units) - expired * unit_cost * disposal_pct / 100
    gp0 = baseline_units * base_price - unit_cost * (baseline_units + at_risk_units) - at_risk_units * unit_cost * disposal_pct / 100
    return {"price": price, "extra_units": extra, "units_sold": sold, "expired_units": expired, "revenue": revenue,
            "gross_profit": gp, "delta_vs_full_price": gp - gp0}


def window_days(investigate_by_day, earliest_batch_last_day):
    if _bad(investigate_by_day) or _bad(earliest_batch_last_day):
        return None
    w = int(earliest_batch_last_day) - int(investigate_by_day) + 1
    return w if w >= 1 else None


def recommend_line(base_price, gross_margin_pct, min_margin_pct, at_risk_units, window, q10, q50, q90,
                   promotion_active: bool, recorded_price, params: dict) -> tuple[dict, list[dict]]:
    """(line result, option rows) for one eligible line. Deterministic; never raises on missing evidence."""
    gaps = []
    if _bad(base_price) or (not _bad(base_price) and base_price <= 0) or _bad(gross_margin_pct) or _bad(min_margin_pct):
        gaps.append("MISSING_BASE_PRICE_OR_MARGIN")
    if any(_bad(q) for q in (q10, q50, q90)):
        gaps.append("MISSING_FORECAST_QUANTILES")
    if _bad(at_risk_units):
        gaps.append("MISSING_AT_RISK_UNITS")
    if window is None:
        gaps.append("MISSING_MARKDOWN_WINDOW")
    tol = params["price_evidence_conflict_tolerance_pct"]
    conflict_pct = None
    if not gaps and not _bad(recorded_price) and recorded_price > 0:
        conflict_pct = 100 * (float(recorded_price) / float(base_price) - 1)
        if abs(conflict_pct) > tol + TOL:
            gaps.append("PRICE_EVIDENCE_CONFLICT")
    line = {"recommendation_status": None, "recommended_markdown_pct": None, "expected_delta": None,
            "downside_delta": None, "stress_delta": None, "at_risk_stock_cost": None, "window_days": window,
            "price_difference_recorded_vs_reference_pct": conflict_pct, "evidence_gaps": "|".join(gaps),
            "evidence_quality": EVIDENCE_QUALITY, "label": LABEL, "runner_up_markdown_pct": None}
    if gaps:
        line["recommendation_status"] = EVIDENCE
        line["explanation"] = explain(line, [], params)
        return line, []

    p0 = float(base_price)
    base = PD.options(p0, gross_margin_pct, min_margin_pct, params["max_discount_pct"], params["discount_steps_pct"],
                      params["pricing_display_markdown_steps_pct"], promotion_active)
    cost = base[0]["illustrative_unit_cost"]
    x = float(at_risk_units)
    at_risk_cost = x * cost
    line["at_risk_stock_cost"] = at_risk_cost
    resp, weights = params["demand_response_scenarios_pct_per_point"], params["demand_response_decision_weights"]
    disposal = params["expiry_disposal_cost_pct_of_unit_cost"]
    quant = {"p10": float(q10), "p50": float(q50), "p90": float(q90)}
    downside_case = (params["recommendation_downside_scenario"], "p90")
    min_gain = max(params["recommendation_min_expected_benefit_gbp"],
                   at_risk_cost * params["recommendation_min_expected_benefit_pct_of_at_risk_cost"] / 100)
    max_loss = at_risk_cost * params["recommendation_max_downside_loss_pct_of_at_risk_cost"] / 100
    rows = []
    for o in base:
        d = o["markdown_pct"]
        row = {**o, "cases": {}}
        for case, scen, q, role in CASES + ((f"{downside_case[0][:2]}@p90 (downside)", downside_case[0], "p90", "downside"),):
            s0 = quant[q] / 7 * window
            row["cases"][case] = {"scenario": scen, "baseline_quantile": q, "role": role, "baseline_units": s0,
                                  **outcome(p0, cost, d, s0, x, resp[scen], disposal)}
        exp = sum(w * row["cases"][f"{k[:2]}@p50"]["delta_vs_full_price"] for k, w in weights.items())
        down = next(c for c in row["cases"].values() if c["role"] == "downside")["delta_vs_full_price"]
        row.update(expected_delta=exp, downside_delta=down, stress_delta=row["cases"]["R0@p50"]["delta_vs_full_price"],
                   permitted=o["status"] == PD.PASSES, material=exp >= min_gain - TOL,
                   within_downside_limit=-down <= max_loss + TOL, rank=None, is_recommended=False)
        rows.append(row)

    permitted = [r for r in rows if r["permitted"]]
    ranked = sorted(permitted, key=lambda r: (-round(r["expected_delta"], 9), round(-r["downside_delta"], 9),
                                              r["markdown_pct"]))
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    material = [r for r in ranked if r["material"]]
    safe = [r for r in material if r["within_downside_limit"]]
    if not permitted:
        status, chosen = CONSTRAINED, None
    elif not material:
        status, chosen = KEEP, None
    elif not safe:
        status, chosen = UNCERTAIN, material[0]
    else:
        status, chosen = RECOMMEND, safe[0]
    if status == RECOMMEND:
        chosen["is_recommended"] = True
        line["recommended_markdown_pct"] = chosen["markdown_pct"]
        others = [r for r in ranked if r is not chosen]
        line["runner_up_markdown_pct"] = others[0]["markdown_pct"] if others else None
    if chosen is not None:
        line.update(expected_delta=chosen["expected_delta"], downside_delta=chosen["downside_delta"],
                    stress_delta=chosen["stress_delta"])
    line.update(recommendation_status=status, unit_cost=cost, min_expected_benefit=min_gain, max_downside_loss=max_loss,
                considered_markdown_pct=None if chosen is None else chosen["markdown_pct"])
    line["explanation"] = explain(line, rows, params)
    return line, rows


def _gbp(x) -> str:
    return f"£{abs(x):,.2f}"


def explain(line: dict, rows: list[dict], params: dict) -> str:
    """Plain-English explanation of the decision for a retail manager."""
    s = line["recommendation_status"]
    if s == EVIDENCE:
        gaps = "; ".join(EVIDENCE_LABELS[g] for g in line["evidence_gaps"].split("|") if g)
        return f"No recommendation: the evidence needed to compare options is missing or conflicting ({gaps})."
    if s == CONSTRAINED:
        reasons = sorted({r["blocking_reasons"] for r in rows if r["markdown_pct"] > 0 and r["blocking_reasons"]})
        return "No recommendation: every markdown step is blocked by a rule — " + "; ".join(reasons) + "."
    by = {r["markdown_pct"]: r for r in rows}
    if s == KEEP:
        best = max((r for r in rows if r["permitted"]), key=lambda r: r["expected_delta"])
        return (f"No recommendation — keeping the full price ranks first. The best permitted step ({best['markdown_pct']}%) "
                f"is expected to change the result by {'+' if best['expected_delta'] >= 0 else '−'}"
                f"{_gbp(best['expected_delta'])}, below the {_gbp(line['min_expected_benefit'])} needed to count as a "
                "real benefit: the extra units it might sell do not make up for the lower price on units that would "
                "have sold anyway.")
    c = by[line["considered_markdown_pct"]]
    if s == UNCERTAIN:
        return (f"No recommendation — too uncertain. A {c['markdown_pct']}% markdown has the best expected result "
                f"(+{_gbp(c['expected_delta'])}), but if customers respond only weakly and demand is high it could lose "
                f"{_gbp(c['downside_delta'])}, more than the {params['recommendation_max_downside_loss_pct_of_at_risk_cost']}% "
                f"limit ({_gbp(line['max_downside_loss'])}) of the {_gbp(line['at_risk_stock_cost'])} of stock at stake.")
    runner = by.get(line["runner_up_markdown_pct"])
    text = (f"{LABEL}: a {c['markdown_pct']}% markdown ranks first under the stated assumptions, with an expected "
            f"+{_gbp(c['expected_delta'])} compared with keeping the full price (weighted across low, central and high "
            f"customer response) and about {c['cases']['R2@p50']['extra_units']:,.0f} fewer units going out of date in "
            "the central case.")
    if runner is not None:
        deeper = runner["markdown_pct"] > c["markdown_pct"]
        why = ("a deeper markdown gives away more on units that would have sold anyway" if deeper else
               "a smaller markdown sells fewer of the at-risk units")
        text += (f" It ranks above {runner['markdown_pct']}% (expected {'+' if runner['expected_delta'] >= 0 else '−'}"
                 f"{_gbp(runner['expected_delta'])}) because {why}.")
    text += (f" If the response is weak and demand high it would {'gain' if c['downside_delta'] >= 0 else 'lose'} "
             f"{_gbp(c['downside_delta'])} (limit {_gbp(line['max_downside_loss'])}); if customers do not respond at all "
             f"it would lose {_gbp(c['stress_delta'])}. Not validated for live use; nothing is proposed or approved.")
    return text


def assess(markdown: pd.DataFrame, reference_prices: pd.DataFrame, contract: pd.DataFrame,
           params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(lines, outcomes) for one policy and scenario. `markdown` is the Stage 7B assessment; `contract` the protected
    forecast contract. Outcomes: one row per line x markdown step x case."""
    ref = reference_prices[["Store_ID", "Product_ID", "origin_week", "reference_price_asof"]]
    h1 = contract[contract["horizon_weeks"] == 1].rename(columns={"store_id": "Store_ID", "product_id": "Product_ID"})[
        ["Store_ID", "Product_ID", "origin_week", "lower_p10_units", "median_p50_units", "upper_p90_units"]]
    m = markdown.merge(ref, on=["Store_ID", "Product_ID", "origin_week"], how="left").merge(
        h1, on=["Store_ID", "Product_ID", "origin_week"], how="left")
    lines, out = [], []
    for r in m.itertuples(index=False):
        key = {"Store_ID": r.Store_ID, "Product_ID": r.Product_ID, "origin_week": r.origin_week,
               "target_week": r.target_week}
        gm, mn = params["gross_margin_pct"].get(r.product_category), params["min_margin_pct"].get(r.product_category)
        promo = (not _bad(r.recorded_discount_pct_origin_week)) and float(r.recorded_discount_pct_origin_week) > 0
        common = {**key, "product_category": r.product_category, "eligibility": r.eligibility,
                  "base_price": None if _bad(r.reference_price_asof) else float(r.reference_price_asof),
                  "assumed_gross_margin_pct": gm, "assumed_min_margin_pct": mn,
                  "recorded_price_origin_week": r.recorded_price_origin_week, "promotion_active": promo,
                  "at_risk_units": r.projected_existing_expiry_units, "investigate_by_label": r.investigate_by_label,
                  "earliest_batch_last_day_label": r.earliest_batch_last_day_label,
                  "q10": r.lower_p10_units, "q50": r.median_p50_units, "q90": r.upper_p90_units,
                  "status": "HYPOTHETICAL_UNAPPROVED", "execution_status": "NOT_EXECUTED", "proposal_id": None,
                  "approval_event_id": None, "policy_id": r.policy_id, "scenario_id": r.scenario_id}
        if r.eligibility != "ELIGIBLE_FOR_MARKDOWN_REVIEW":
            lines.append({**common, "recommendation_status": NOT_ELIGIBLE, "recommended_markdown_pct": None,
                          "explanation": STATUS_LABELS[NOT_ELIGIBLE]})
            continue
        res, rows = recommend_line(common["base_price"], gm, mn, r.projected_existing_expiry_units,
                                   window_days(r.investigate_by_day, r.earliest_batch_last_day),
                                   r.lower_p10_units, r.median_p50_units, r.upper_p90_units, promo,
                                   r.recorded_price_origin_week, params)
        lines.append({**common, **res})
        for o in rows:
            flat = {k: v for k, v in o.items() if k != "cases"}
            for case, c in o["cases"].items():
                out.append({**key, **flat, "case": case, **c})
    lines = pd.DataFrame(lines)
    lines["recommendation_status_label"] = lines["recommendation_status"].map(STATUS_LABELS)
    return lines, pd.DataFrame(out)


def summary(lines: pd.DataFrame) -> dict:
    c = lines["recommendation_status"].value_counts()
    return {**{k: int(c.get(k, 0)) for k in STATUS_LABELS}, "assessed": int((lines["recommendation_status"] != NOT_ELIGIBLE).sum()),
            "approvals_created": 0, "proposals_created": 0, "prices_changed": 0}
