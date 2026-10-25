"""Phase 3: waste intervention intelligence (ADVISORY INVESTIGATION SUPPORT ONLY; read-only, deterministic).

For every P2 decision (store x product x week) of the protected replay, classifies five possible courses of action from
saved, decision-time evidence and returns plain-English explanations. Nothing is ordered, moved, discounted, donated,
approved or executed; no saving, waste reduction or profit is claimed. Design: docs/PHASE_3_WASTE_INTERVENTION_DESIGN.md;
parameters from assumption set v9 (DRAFT).

Two separate decisions:
  CURRENT_STOCK  stock already in the store (it expires whatever the next order does): markdown, transfer, donation /
                 disposal, or no action
  FUTURE_ORDER   the size of the next replenishment order (it cannot save stock already approaching expiry)

Options and their highest possible status:
  A REPLENISHMENT_REVIEW   CANDIDATE_FOR_REVIEW            SIMULATED pattern (order buffer above typical demand)
  B TRANSFER               OPPORTUNITY_FOR_INVESTIGATION   SIMULATED pattern (same-region store projected short)
  C MARKDOWN               CANDIDATE_FOR_REVIEW            reuses Stage 7B eligibility + Phase 1 ranking (+ A1 context)
  D DONATION_OR_DISPOSAL   INVESTIGATE_ONLY                no evidence beyond the size of the exposure
  E NO_ACTION              NO_ACTION_SUPPORTED / INSUFFICIENT_EVIDENCE / ALWAYS_AVAILABLE
Investigation order (current stock): highest evidence level first (L2 modelled consequence > L1 simulated pattern > L0
none), ties by fewer outside parties (markdown, transfer, donation). If only L0 remains: INSUFFICIENT EVIDENCE —
investigate. The order reflects evidence quality, not financial benefit, and is not a commercially optimal choice.
"""
from __future__ import annotations

import math

import pandas as pd

from dpe.decision import discount_recommendation as R
from dpe.decision import markdown_eligibility as M

KEY = ["Store_ID", "Product_ID", "origin_week"]
CANDIDATE, OPPORTUNITY, INVESTIGATE = "CANDIDATE_FOR_REVIEW", "OPPORTUNITY_FOR_INVESTIGATION", "INVESTIGATE_ONLY"
BLOCKED, INSUFFICIENT, NA = "BLOCKED", "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE"
NO_ACTION_SUPPORTED, ALWAYS = "NO_ACTION_SUPPORTED", "ALWAYS_AVAILABLE"
ACTIVE = (CANDIDATE, OPPORTUNITY, INVESTIGATE)
STATUS_LABELS = {CANDIDATE: "Candidate for review", OPPORTUNITY: "Opportunity — investigate only",
                 INVESTIGATE: "Investigate only", BLOCKED: "Blocked", INSUFFICIENT: "Insufficient evidence",
                 NA: "Not applicable", NO_ACTION_SUPPORTED: "No action supported by the evidence",
                 ALWAYS: "Always available to a manager"}
LINE_OUTCOMES = {"NO_INTERVENTION_NEEDED": "No intervention needed — waste risk is Low",
                 "INSUFFICIENT_EVIDENCE": "Insufficient evidence — waste risk could not be judged",
                 "INVESTIGATIONS_SUGGESTED": "Stock at risk — investigations suggested"}
OPTIONS = {
    "REPLENISHMENT_REVIEW": ("A", "Review the next replenishment order", "FUTURE_ORDER", "Product investigation"),
    "TRANSFER": ("B", "Investigate a transfer to another store", "CURRENT_STOCK", None),
    "MARKDOWN": ("C", "Investigate a markdown", "CURRENT_STOCK", "Discount Decision Lab"),
    "DONATION_OR_DISPOSAL": ("D", "Investigate donation or alternative disposal", "CURRENT_STOCK", None),
    "NO_ACTION": ("E", "No intervention / further investigation", "CURRENT_STOCK", None),
}
LEVEL_LABELS = {2: "L2 — simulated, with a modelled consequence", 1: "L1 — simulated pattern only", 0: "L0 — no evidence"}
MISSING = {
    "REPLENISHMENT_REVIEW": ["Confirmed supplier order deadlines and minimums", "Real (not simulated) stock on hand",
                             "What a smaller order would change (not simulated in Phase 3)"],
    "TRANSFER": ["Distance and travel time between the stores", "Transport cost and availability",
                 "Receiving capacity and cold storage at the other store (capacity units unknown)",
                 "Batch-level stock and remaining shelf life", "Whether the other store's shortage is real"],
    "MARKDOWN": [M.MISSING_DATA_LABELS[c] for c in ("D1_PURCHASE_COST", "D2_SHELF_AND_REGULAR_PRICE",
                                                     "D4_MARKDOWN_RESPONSE_HISTORY", "D8_APPROVAL_OWNERSHIP")],
    "DONATION_OR_DISPOSAL": ["Donation partners and their availability", "Food-safety and labelling rules",
                             "Eligibility of the product for donation", "Transport and handling capacity",
                             "Disposal routes and their costs", "Any financial or tax effect"],
    "NO_ACTION": ["Real stock and expiry dates on the shelf"],
}
CHECKS = {
    "REPLENISHMENT_REVIEW": ["Buyer checks stock on hand and the next order before the supplier deadline",
                             "Confirm a smaller order would not cause a shortage before the following delivery"],
    "TRANSFER": ["Both store managers confirm surplus and shortage on the shelf", "Logistics confirms transport, time and cost",
                 "Quality checks remaining shelf life and cold chain"],
    "MARKDOWN": ["Store manager checks dates and quantity on the shelf", "Pricing owner reviews any markdown — named approver, "
                 "never automatic", "Use the Markdown review and Discount Decision Lab evidence; customer response is assumed"],
    "DONATION_OR_DISPOSAL": ["Food-safety owner confirms the product may be donated", "Confirm an eligible recipient and collection",
                             "Record any disposal through the store's waste process"],
    "NO_ACTION": ["Store manager confirms on the shelf that no action is needed, or records why"],
}
TOL = 0.5


def _missing(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _units(x) -> str:
    return f"{x:,.0f}"


def _money(x) -> str:
    return "not available" if _missing(x) else f"£{x:,.0f}"


def option_row(option: str, status: str, level: int, evidence_for: list, evidence_against: list, explanation: str) -> dict:
    letter, title, group, link = OPTIONS[option]
    return {"option": option, "letter": letter, "title": title, "decision_group": group, "status": status,
            "status_label": STATUS_LABELS[status], "evidence_level": level if status in ACTIVE else None,
            "evidence_level_label": LEVEL_LABELS[level] if status in ACTIVE else "—",
            "evidence_for": "|".join(evidence_for), "evidence_against": "|".join(evidence_against),
            "missing_information": "|".join(MISSING[option]), "human_checks": "|".join(CHECKS[option]),
            "explanation": explanation, "linked_page": link, "review_status": "PENDING_HUMAN_INVESTIGATION",
            "execution_status": "NOT_EXECUTED", "approval_event_id": None}


def assess_replenishment(r) -> dict:
    """Future order only. Never claims to save the stock already in the store."""
    if not (r.ordered_units > 0):
        return option_row("REPLENISHMENT_REVIEW", NA, 1, [], ["No simulated order was placed this week (SIMULATED)"],
                          "No order was placed this week, so there is no order size to review.")
    if r.shortage_before_delivery:
        return option_row("REPLENISHMENT_REVIEW", BLOCKED, 1, [],
                          ["Stock may run short before the next delivery (SIMULATED × FORECAST)"],
                          "Do not reduce the next order: the simulated stock may run short before the delivery arrives.")
    if _missing(r.planned_buffer_units) or r.planned_buffer_units <= TOL:
        return option_row("REPLENISHMENT_REVIEW", NA, 1, [f"Simulated order of {_units(r.ordered_units)} units (SIMULATED)"],
                          ["The order is not above typical (p50) demand within its shelf life (SIMULATED × FORECAST)"],
                          "The simulated order is not above typical demand, so there is nothing to trim.")
    return option_row(
        "REPLENISHMENT_REVIEW", CANDIDATE, 1,
        [f"Simulated order of {_units(r.ordered_units)} units this week (SIMULATED)",
         f"{_units(r.planned_buffer_units)} units above typical (p50) demand within the delivery's shelf life "
         "(SIMULATED × FORECAST)", f"{_units(r.at_risk_units)} units of existing stock projected to expire (SIMULATED × FORECAST)"],
        ["The buffer is a planning margin for uncertain demand (ASSUMED service target)", "Effect of a smaller order is not simulated"],
        f"For the next order: the simulated order puts about {_units(r.planned_buffer_units)} units above typical demand. A "
        "buyer could review whether the next order can be smaller. This would not save the stock already in the store.")


def assess_transfer(r, receivers: list) -> dict:
    if not receivers:
        return option_row("TRANSFER", NA, 1, [], ["No store in the same region is projected short of this product this week "
                                                  "(SIMULATED × FORECAST)"],
                          "No nearby store appears short of this product this week, so a transfer is not suggested.")
    names = ", ".join(f"store {s}" for s in receivers)
    return option_row(
        "TRANSFER", OPPORTUNITY, 1,
        [f"Same region ({r.Region}) and same week: {names} projected short before its next delivery (SIMULATED × FORECAST)",
         f"{_units(r.at_risk_units)} units projected to expire here (SIMULATED × FORECAST)"],
        ["Region stands in for distance; no travel time or cost exists", "Receiving capacity and batch dates are unknown",
         "The other store's shortage is itself a simulated indicator"],
        f"Possible opportunity only: {names} in {r.Region} may be short of this product. A transfer cannot be judged "
        "without transport, cost, receiving and batch information — investigate, do not assume it is feasible.")


def assess_markdown(r, a1_selected_pct) -> dict:
    elig = r.eligibility
    a1 = ("" if a1_selected_pct is None else
          f"In the preferred A1 dynamic-pricing research run (central response) a {int(a1_selected_pct)}% markdown was "
          "simulated for this week (context only)" if a1_selected_pct else
          "In the preferred A1 dynamic-pricing research run (central response) no markdown was simulated this week (context only)")
    ctx = [a1] if a1 else []
    if elig == "BLOCKED":
        why = "; ".join(M.BLOCKER_LABELS[b] for b in str(r.blocker_codes).split("|") if b)
        return option_row("MARKDOWN", BLOCKED, 2, ctx, [f"Markdown review blocked: {why} (ASSUMED rules)"],
                          f"A markdown review is not appropriate now: {why.lower()}.")
    if elig != "ELIGIBLE_FOR_MARKDOWN_REVIEW":
        return option_row("MARKDOWN", INSUFFICIENT, 2, ctx, [f"Markdown review: {M.CLASS_LABELS.get(elig, elig).lower()}"],
                          "There is not enough information to judge a markdown for this line.")
    status, pct = r.phase1_status, r.phase1_markdown_pct
    base = ["Eligible for markdown review (Stage 7B, ASSUMED rules on SIMULATED stock)"]
    if status == R.RECOMMEND:
        return option_row(
            "MARKDOWN", CANDIDATE, 2,
            base + [f"Phase 1 simulated research ranks a {int(pct)}% markdown first (ASSUMED customer response — not proven)"] + ctx,
            ["Customer response is assumed, not measured", "Prices are an estimated proxy and costs an assumed margin"],
            f"A markdown is worth reviewing: the line is eligible and the simulated research ranks {int(pct)}% first under "
            "assumed customer response. A named person must review it in the Discount Decision Lab; nothing is decided here.")
    if status in (R.KEEP, R.CONSTRAINED):
        reason = R.STATUS_LABELS[status].split(" — ", 1)[-1]
        return option_row("MARKDOWN", BLOCKED, 2, base + ctx, [f"Phase 1: {reason} (ASSUMED inputs)"],
                          f"A markdown is not supported here: {reason}.")
    reason = R.STATUS_LABELS.get(status, "no Phase 1 result").split(" — ", 1)[-1]
    return option_row("MARKDOWN", INSUFFICIENT, 2, base + ctx, [f"Phase 1: {reason}"],
                      f"The line is eligible, but the evidence is not good enough to judge a markdown: {reason}.")


def assess_donation(r, min_units: int) -> dict:
    if r.at_risk_units < min_units:
        return option_row("DONATION_OR_DISPOSAL", NA, 0, [],
                          [f"Only {_units(r.at_risk_units)} units at risk, below the {min_units}-unit investigation level (ASSUMED)"],
                          "The quantity at risk is small, so a donation or disposal investigation is not suggested.")
    return option_row(
        "DONATION_OR_DISPOSAL", INVESTIGATE, 0, [f"{_units(r.at_risk_units)} units projected to expire (SIMULATED × FORECAST)"],
        ["No information on donation partners, food safety, eligibility, transport or value"],
        "Donation or another disposal route could be investigated, but nothing is known about eligibility, food safety, "
        "recipients or transport. It is never assumed to be possible.")


def assess_no_action(current_active: list, markdown_status: str, phase1_status) -> dict:
    if not current_active:
        if markdown_status == BLOCKED and phase1_status == R.KEEP:
            return option_row("NO_ACTION", NO_ACTION_SUPPORTED, 0, ["Phase 1 ranks keeping the full price first (ASSUMED inputs)"],
                              [], "Under the stated assumptions no option is supported for the stock in store; confirm on the "
                              "shelf and record the outcome.")
        return option_row("NO_ACTION", INSUFFICIENT, 0, [], ["No option for the stock in store has usable evidence"],
                          "INSUFFICIENT EVIDENCE: the available data cannot support an action for the stock in store. "
                          "Check the shelf and decide manually.")
    return option_row("NO_ACTION", ALWAYS, 0, [], [],
                      "A manager may decide to take no action; the projected expiry would then be expected to occur.")


def _first(options: list, tie_order: list) -> dict | None:
    active = [o for o in options if o["decision_group"] == "CURRENT_STOCK" and o["status"] in ACTIVE]
    if not active:
        return None
    return sorted(active, key=lambda o: (-o["evidence_level"], tie_order.index(o["option"])))[0]


def assess(waste: pd.DataFrame, decisions: pd.DataFrame, markdown: pd.DataFrame, phase1: pd.DataFrame,
           a1_pricing: pd.DataFrame | None, reference_prices: pd.DataFrame, stores: pd.DataFrame,
           params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(lines, options) for one scenario of the P2 replay. All inputs are saved, decision-time evidence."""
    at_risk = params["waste_intervention_at_risk_categories"]
    min_units = params["waste_intervention_donation_min_units"]
    tie = params["waste_intervention_tie_order"]
    gm = params["gross_margin_pct"]
    w = waste[["Store_ID", "Product_ID", "product_category", "origin_week", "target_week", "decision_day", "category",
               "projected_existing_expiry_units", "projected_expiry_pct_of_p50", "typical_weekly_demand_p50",
               "planned_buffer_units", "recorded_wastage_pct_4w", "earliest_batch_last_day_label",
               "investigate_by_label", "review_case_type"]]
    d = decisions[KEY + ["ordered_units", "std_pre_delivery_shortage"]]
    md = markdown[KEY + ["eligibility", "blocker_codes"]]
    p1 = phase1[KEY + ["recommendation_status", "recommended_markdown_pct"]].rename(
        columns={"recommendation_status": "phase1_status", "recommended_markdown_pct": "phase1_markdown_pct"})
    m = (w.merge(d, on=KEY, how="left").merge(md, on=KEY, how="left").merge(p1, on=KEY, how="left")
         .merge(reference_prices[KEY + ["reference_price_asof"]], on=KEY, how="left")
         .merge(stores[["Store_ID", "Region"]], on="Store_ID", how="left"))
    if a1_pricing is not None:
        a1 = a1_pricing[KEY + ["outcome", "markdown_pct"]].assign(
            a1_markdown_pct=lambda x: x["markdown_pct"].where(x["outcome"] == "MARKDOWN_SELECTED", 0))[KEY + ["a1_markdown_pct"]]
        m = m.merge(a1, on=KEY, how="left")
    else:
        m["a1_markdown_pct"] = None
    m["shortage_before_delivery"] = m["std_pre_delivery_shortage"].fillna(False).astype(bool)
    short = m[m["shortage_before_delivery"]].groupby(["Product_ID", "origin_week", "Region"])["Store_ID"].apply(sorted).to_dict()

    lines, options = [], []
    for r in m.assign(at_risk_units=m["projected_existing_expiry_units"].fillna(0.0)).itertuples(index=False):
        ref = None if _missing(r.reference_price_asof) else float(r.reference_price_asof)
        retail = None if ref is None else r.at_risk_units * ref
        cost = None if ref is None or gm.get(r.product_category) is None else r.at_risk_units * ref * (1 - gm[r.product_category] / 100)
        line = {"Store_ID": r.Store_ID, "Product_ID": r.Product_ID, "origin_week": r.origin_week, "target_week": r.target_week,
                "decision_day": r.decision_day, "product_category": r.product_category, "Region": r.Region,
                "waste_risk_category": r.category, "at_risk_units": r.projected_existing_expiry_units,
                "share_of_typical_week_pct": r.projected_expiry_pct_of_p50, "earliest_batch_last_day_label": r.earliest_batch_last_day_label,
                "investigate_by_label": r.investigate_by_label, "estimated_retail_value": retail, "assumed_cost_value": cost,
                "reference_price": ref, "recorded_wastage_pct_4w": r.recorded_wastage_pct_4w,
                "open_review_case": r.review_case_type if isinstance(r.review_case_type, str) else None,
                "current_stock_first": None, "current_stock_outcome": None, "future_order_outcome": None,
                "review_status": "PENDING_HUMAN_INVESTIGATION", "execution_status": "NOT_EXECUTED", "approval_event_id": None}
        if r.category not in at_risk:
            outcome = "INSUFFICIENT_EVIDENCE" if r.category == "INSUFFICIENT_INFORMATION" else "NO_INTERVENTION_NEEDED"
            line.update(line_outcome=outcome, line_outcome_label=LINE_OUTCOMES[outcome],
                        current_stock_outcome=outcome, future_order_outcome="NO_CHANGE_SUGGESTED",
                        manager_summary=LINE_OUTCOMES[outcome] + "." + (" Check the shelf and decide manually."
                                                                       if outcome == "INSUFFICIENT_EVIDENCE" else ""))
            lines.append(line)
            continue
        receivers = [s for s in short.get((r.Product_ID, r.origin_week, r.Region), []) if s != r.Store_ID]
        a1pct = None if a1_pricing is None or _missing(r.a1_markdown_pct) else r.a1_markdown_pct
        opts = [assess_replenishment(r), assess_transfer(r, receivers), assess_markdown(r, a1pct), assess_donation(r, min_units)]
        mk = opts[2]
        current_active = [o for o in opts if o["decision_group"] == "CURRENT_STOCK" and o["status"] in ACTIVE]
        opts.append(assess_no_action(current_active, mk["status"], r.phase1_status))
        first = _first(opts, tie)
        if first is None:
            cur = opts[-1]["status"]
        elif first["evidence_level"] == 0:
            cur = "INSUFFICIENT_EVIDENCE_INVESTIGATE"
        else:
            cur = "INVESTIGATE_" + first["option"]
        ranked = sorted([o for o in opts if o["decision_group"] == "CURRENT_STOCK" and o["status"] in ACTIVE],
                        key=lambda o: (-o["evidence_level"], tie.index(o["option"])))
        for i, o in enumerate(opts):
            o["investigation_rank"] = (ranked.index(o) + 1) if o in ranked else None
            options.append({**{k: line[k] for k in ("Store_ID", "Product_ID", "origin_week", "target_week")}, **o})
        fut = "REVIEW_NEXT_ORDER" if opts[0]["status"] == CANDIDATE else "NO_CHANGE_SUGGESTED"
        line.update(line_outcome="INVESTIGATIONS_SUGGESTED", line_outcome_label=LINE_OUTCOMES["INVESTIGATIONS_SUGGESTED"],
                    current_stock_first=None if first is None else first["option"], current_stock_outcome=cur,
                    future_order_outcome=fut, manager_summary=summary(line, opts, first, cur))
        lines.append(line)
    return pd.DataFrame(lines), pd.DataFrame(options)


def summary(line: dict, opts: list, first: dict | None, cur: str) -> str:
    """Plain-English manager summary. Never claims a saving or a commercially optimal choice."""
    share = line["share_of_typical_week_pct"]
    s = (f"About {_units(line['at_risk_units'])} units already in store may go out of date by "
         f"{line['earliest_batch_last_day_label'] or 'an unknown date'}"
         + (f" (about {share:.0f}% of a typical week's sales)" if not _missing(share) else "")
         + f". Illustrative value at risk: {_money(line['estimated_retail_value'])} at the estimated shelf price, "
           f"{_money(line['assumed_cost_value'])} at assumed cost — not a saving. ")
    if cur == "INSUFFICIENT_EVIDENCE_INVESTIGATE":
        s += ("Stock in store: INSUFFICIENT EVIDENCE — only donation or another disposal route remains, and nothing is known "
              "about it; investigate manually. ")
    elif first is None:
        s += ("Stock in store: no option is supported under the stated assumptions; confirm on the shelf. "
              if cur == NO_ACTION_SUPPORTED else "Stock in store: INSUFFICIENT EVIDENCE to suggest an action; check the shelf. ")
    else:
        others = [o["title"].lower() for o in opts if o["decision_group"] == "CURRENT_STOCK" and o["status"] in ACTIVE
                  and o is not first]
        s += (f"Stock in store: investigate first — {first['title'].lower()} ({LEVEL_LABELS[first['evidence_level']].split(' — ')[1]})"
              + (f"; also possible: {', '.join(others)}" if others else "") + ". ")
    rep = opts[0]
    s += ("Next order: review its size — the simulated order is above typical demand. This cannot save the stock already "
          "in store. " if rep["status"] == CANDIDATE else f"Next order: no change suggested ({rep['explanation'].rstrip('.').lower()}). ")
    s += "The order of investigation reflects evidence quality, not financial benefit. Nothing has been done or approved."
    return s


def summarise(lines: pd.DataFrame, options: pd.DataFrame) -> dict:
    c = lines["line_outcome"].value_counts()
    out = {"decisions": int(len(lines)), **{k: int(c.get(k, 0)) for k in LINE_OUTCOMES},
           "units_at_risk": float(lines.loc[lines["line_outcome"] == "INVESTIGATIONS_SUGGESTED", "at_risk_units"].sum()),
           "estimated_retail_value": float(lines.loc[lines["line_outcome"] == "INVESTIGATIONS_SUGGESTED", "estimated_retail_value"].sum()),
           "assumed_cost_value": float(lines.loc[lines["line_outcome"] == "INVESTIGATIONS_SUGGESTED", "assumed_cost_value"].sum()),
           "actions_executed": 0, "approvals_created": 0}
    if len(options):
        for opt in OPTIONS:
            s = options[options["option"] == opt]["status"].value_counts()
            out[opt] = {k: int(v) for k, v in s.items()}
    return out
