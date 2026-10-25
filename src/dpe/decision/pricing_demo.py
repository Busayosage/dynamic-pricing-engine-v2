"""Stage 8B: pricing intelligence DEMONSTRATION (read-only arithmetic and rule checks; state 1b only).

For lines that Stage 7B marks ELIGIBLE_FOR_MARKDOWN_REVIEW, shows what each markdown step would do to an ILLUSTRATIVE
price and margin, and which documented rules block it. It never recommends, ranks or proposes an option, never models a
sales response, elasticity, waste reduction or profit change, and never approves, executes or changes a price.
Design: docs/STAGE_8A_PRICING_INTELLIGENCE_DESIGN.md; parameters from assumption set v5 (DRAFT).

  base price  P0   forecast contract reference_price_asof (ESTIMATED PROXY), never the noisy recorded weekly price
  unit cost   C    P0 x (1 - gross_margin%)                         (ASSUMED margin)
  price       P(d) P0 x (1 - d)                                     full precision; rounded only for display
  profit      M(d) P(d) - C                                         per unit
  margin %    GM(d) M(d) / P(d)
  units to preserve original gross profit   M(0) / M(d)            ARITHMETIC, NOT A FORECAST
Option blockers, all reported in this order: OVERLAPPING_PROMOTION, NOT_AN_ALLOWED_STEP, EXCEEDS_MAX_MARKDOWN,
BELOW_MARGIN_FLOOR (GM(d) < min_margin%). Cooldown enforcement is NOT implemented (no duration is defined).
"""
from __future__ import annotations

import math

import pandas as pd

TOL = 1e-12
FULL_PRICE = "FULL_PRICE_REFERENCE"
PASSES = "PASSES_DEMONSTRATION_CONSTRAINTS"
BLOCKED = "BLOCKED"
STATUS_LABELS = {FULL_PRICE: "Full price (reference)", PASSES: "Passes the demonstration constraints", BLOCKED: "Blocked"}
BLOCKER_LABELS = {
    "OVERLAPPING_PROMOTION": "A promotion is already recorded for this line this week — no second markdown",
    "NOT_AN_ALLOWED_STEP": "Not one of the permitted markdown steps",
    "EXCEEDS_MAX_MARKDOWN": "Deeper than the maximum markdown allowed",
    "BELOW_MARGIN_FLOOR": "Gross margin would fall below the minimum margin floor",
    "NO_PROFIT_PER_UNIT": "The price would not cover the illustrative unit cost",
}
LINE_STATUS_LABELS = {
    "OPTIONS_SHOWN": "Illustrative options shown",
    "NOT_ELIGIBLE": "No options — the line is not eligible for a markdown review (Stage 7B)",
    "MISSING_INPUT": "No options — a required input is missing",
}
COOLDOWN_STATUS = "NOT_IMPLEMENTED — no cooldown duration is defined, so repeated markdowns are not checked"
LABELS = {
    "base_price": "ESTIMATED — forecast contract reference-price proxy (illustrative base; currency assumed GBP)",
    "unit_cost": "ILLUSTRATIVE — base price × (1 − ASSUMED gross margin)",
    "price": "ILLUSTRATIVE — derived from the estimated reference price",
    "gross_profit_per_unit": "ILLUSTRATIVE — derived from the estimated reference price and ASSUMED margin",
    "gross_margin_pct": "ILLUSTRATIVE — derived",
    "units_to_preserve_gross_profit": "ARITHMETIC, NOT A FORECAST — nothing says this many would sell",
    "at_risk_stock_cost": "ILLUSTRATIVE — projected at-risk units × illustrative cost; not a saving, not a prediction",
}
STATE = "STATE_1B_DEMONSTRATION_ONLY"


def _bad(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def options(base_price: float, gross_margin_pct: float, min_margin_pct: float, max_markdown_pct: float,
            allowed_steps, display_steps, promotion_active: bool) -> list[dict]:
    """One row per displayed markdown step, at full precision. Raises ValueError on unusable inputs."""
    if _bad(base_price) or float(base_price) <= 0:
        raise ValueError("base price missing or not positive")
    if _bad(gross_margin_pct) or _bad(min_margin_pct) or _bad(max_markdown_pct):
        raise ValueError("margin or markdown limit missing")
    p0 = float(base_price)
    cost = p0 * (1 - float(gross_margin_pct) / 100)
    gp0 = p0 - cost
    rows = []
    for d in display_steps:
        price = p0 * (1 - d / 100)
        gp = price - cost
        gm = gp / price if price > 0 else float("-inf")
        blockers = []
        if d > 0:
            if promotion_active:
                blockers.append("OVERLAPPING_PROMOTION")
            if d not in allowed_steps:
                blockers.append("NOT_AN_ALLOWED_STEP")
            if d > max_markdown_pct + TOL:
                blockers.append("EXCEEDS_MAX_MARKDOWN")
        if gm < float(min_margin_pct) / 100 - TOL:
            blockers.append("BELOW_MARGIN_FLOOR")
        if gp <= TOL and d > 0:
            blockers.append("NO_PROFIT_PER_UNIT")
        status = BLOCKED if blockers else (FULL_PRICE if d == 0 else PASSES)
        rows.append({"markdown_pct": d, "illustrative_price": price, "illustrative_unit_cost": cost,
                     "illustrative_gross_profit_per_unit": gp, "gross_margin_pct": 100 * gm,
                     "units_to_preserve_gross_profit": (gp0 / gp) if gp > TOL else None,
                     "status": status, "status_label": STATUS_LABELS[status],
                     "blocker_codes": "|".join(blockers),
                     "blocking_reasons": "; ".join(BLOCKER_LABELS[b] for b in blockers)})
    return rows


def floor_price(base_price: float, gross_margin_pct: float, min_margin_pct: float) -> float:
    """Lowest price that keeps the minimum margin: cost / (1 - min_margin%)."""
    cost = float(base_price) * (1 - float(gross_margin_pct) / 100)
    return cost / (1 - float(min_margin_pct) / 100)


def assess(markdown: pd.DataFrame, reference_prices: pd.DataFrame, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(lines, options). `markdown` is the Stage 7B assessment for one policy and scenario; `reference_prices` has
    Store_ID, Product_ID, origin_week, reference_price_asof (H1 contract rows). Options exist only for eligible lines."""
    ref = reference_prices[["Store_ID", "Product_ID", "origin_week", "reference_price_asof"]]
    m = markdown.merge(ref, on=["Store_ID", "Product_ID", "origin_week"], how="left")
    gmargin, minmargin = params["gross_margin_pct"], params["min_margin_pct"]
    lines, opts = [], []
    for r in m.itertuples(index=False):
        cat = r.product_category
        gm, mn = gmargin.get(cat), minmargin.get(cat)
        base = r.reference_price_asof
        promo = (not _bad(r.recorded_discount_pct_origin_week)) and float(r.recorded_discount_pct_origin_week) > 0
        missing = []
        if _bad(base) or (not _bad(base) and float(base) <= 0):
            missing.append("reference price")
        if gm is None or mn is None:
            missing.append("assumed margin for the category")
        if r.eligibility != "ELIGIBLE_FOR_MARKDOWN_REVIEW":
            status = "NOT_ELIGIBLE"
        elif missing:
            status = "MISSING_INPUT"
        else:
            status = "OPTIONS_SHOWN"
        line = {"Store_ID": r.Store_ID, "Product_ID": r.Product_ID, "product_category": cat, "origin_week": r.origin_week,
                "target_week": r.target_week, "eligibility": r.eligibility, "markdown_blockers": r.blocker_codes,
                "line_status": status, "line_status_label": LINE_STATUS_LABELS[status],
                "missing_inputs": "; ".join(missing),
                "illustrative_base_price": None if _bad(base) else float(base),
                "recorded_price_origin_week": r.recorded_price_origin_week,
                "recorded_discount_pct_origin_week": r.recorded_discount_pct_origin_week,
                "assumed_gross_margin_pct": gm, "assumed_min_margin_pct": mn,
                "max_markdown_pct": params["max_discount_pct"],
                "illustrative_unit_cost": None, "illustrative_floor_price": None,
                "projected_existing_expiry_units": r.projected_existing_expiry_units,
                "illustrative_at_risk_stock_cost": None, "promotion_active": promo,
                "cooldown_status": COOLDOWN_STATUS, "state": STATE, "recommended_option": None,
                "proposal_id": None, "approval_event_id": None, "execution_status": "NOT_EXECUTED",
                "policy_id": r.policy_id, "scenario_id": r.scenario_id}
        if status == "OPTIONS_SHOWN":
            rows = options(base, gm, mn, params["max_discount_pct"], params["discount_steps_pct"],
                           params["pricing_display_markdown_steps_pct"], promo)
            cost = rows[0]["illustrative_unit_cost"]
            line["illustrative_unit_cost"] = cost
            line["illustrative_floor_price"] = floor_price(base, gm, mn)
            units = r.projected_existing_expiry_units
            if params.get("pricing_show_at_risk_stock_cost") and not _bad(units):
                line["illustrative_at_risk_stock_cost"] = float(units) * cost
            for o in rows:
                opts.append({"Store_ID": r.Store_ID, "Product_ID": r.Product_ID, "origin_week": r.origin_week,
                             "target_week": r.target_week, **o, "policy_id": r.policy_id, "scenario_id": r.scenario_id})
        lines.append(line)
    return pd.DataFrame(lines), pd.DataFrame(opts)


def summary(lines: pd.DataFrame, opts: pd.DataFrame) -> dict:
    c = lines["line_status"].value_counts()
    s = opts["status"].value_counts() if len(opts) else pd.Series(dtype=int)
    return {"lines": int(len(lines)), **{k: int(c.get(k, 0)) for k in LINE_STATUS_LABELS},
            "options": int(len(opts)), **{k: int(s.get(k, 0)) for k in (FULL_PRICE, PASSES, BLOCKED)},
            "recommended_options": 0, "proposals_created": 0, "approvals_created": 0}
