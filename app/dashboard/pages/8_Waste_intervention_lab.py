import altair as alt
import pandas as pd
import streamlit as st

import dashboard_data as D
import theme as T
import ui
from dpe.decision import discount_recommendation as R
from dpe.decision import markdown_eligibility as M
from dpe.decision import waste_interventions as WI

ui.page("Waste Intervention Lab", "♻️")
scenario = ui.scenario_select()
prm = ui.load_intervention_params()
lines, opts = ui.load_waste_interventions(scenario)
scenario_name = D.SCENARIO_NAMES[scenario].split(" — ")[1]
LEVEL = {"CANDIDATE_FOR_REVIEW": "info", "OPPORTUNITY_FOR_INVESTIGATION": "caution", "INVESTIGATE_ONLY": "caution",
         "BLOCKED": "high", "INSUFFICIENT_EVIDENCE": "neutral", "NOT_APPLICABLE": "neutral",
         "NO_ACTION_SUPPORTED": "ok", "ALWAYS_AVAILABLE": "neutral"}
CUR = {"INVESTIGATE_MARKDOWN": "Investigate a markdown first", "INVESTIGATE_TRANSFER": "Investigate a transfer first",
       "INSUFFICIENT_EVIDENCE_INVESTIGATE": "Insufficient evidence — investigate manually",
       "INSUFFICIENT_EVIDENCE": "Insufficient evidence", "NO_ACTION_SUPPORTED": "No action supported",
       "NO_INTERVENTION_NEEDED": "No intervention needed"}

T.md(T.head("Waste intervention intelligence · Phase 3 · advisory · read-only", "Waste Intervention Lab",
            "When stock is projected to go out of date: what is at risk, which actions could be investigated, what "
            "evidence supports or blocks each one, and who must check it.",
            chips=(f"Scenario {scenario}", "Inventory replay P2 (protected)", "Pricing context: A1 preferred research run",
                   f"Assumptions {prm['assumption_set_id']} ({prm['assumption_status']})"), art="clock"))
T.md(T.banner("<b>Advisory — investigation support only.</b> Nothing here orders, moves, discounts, donates or disposes of "
              "stock, and nothing is assumed to have happened. Stock transfer and donation or disposal are <b>INVESTIGATE "
              "ONLY</b>. The investigation order reflects evidence quality, not financial benefit, and is not a commercially "
              "optimal choice. There are no approval or execution controls.", "coral", "♻️"))
T.md(T.disclaimer())
T.md(T.grid([
    T.use_case("📒", "Recorded / forecast", "Recorded wastage history (context only) and the protected forecast range."),
    T.use_case("🧪", "Simulated", "Stock, orders, batch dates and shortages from the protected P2 replay."),
    T.use_case("📐", "Assumed", "Margins, reference prices, markdown rules, customer response and the Phase 3 rules (v9)."),
    T.use_case("❔", "Not available", "Distance, transport, receiving capacity, batch stock, donation partners, food-safety "
               "rules, real costs."),
]))

# ----------------------------------------------------------------------------------------------- scenario summary
s = WI.summarise(lines, opts)
at = lines[lines.line_outcome == "INVESTIGATIONS_SUGGESTED"]
T.md(T.section(f"{scenario} — {scenario_name}", "Store × product × week decisions of the protected P2 replay "
                                                "(720 lines × 20 weeks)."))
T.md(T.grid([
    T.kpi("⚠️", "Lines with stock at risk", f"{s['INVESTIGATIONS_SUGGESTED']:,}", f"of {s['decisions']:,} decisions",
          T.AMBER, "SIMULATED × FORECAST"),
    T.kpi("🗑️", "Units projected to expire", f"{s['units_at_risk']:,.0f}", "stock already in store", T.RED,
          "SIMULATED × FORECAST"),
    T.kpi("🏷️", "Estimated retail value at risk", ui.money(s["estimated_retail_value"], 0), "units × estimated shelf price",
          T.NAVY_3, "ESTIMATED · not a saving"),
    T.kpi("💷", "Assumed cost value at risk", ui.money(s["assumed_cost_value"], 0), "units × assumed unit cost", T.NAVY_3,
          "ASSUMED · not a saving"),
]))
cc = at.current_stock_outcome.value_counts()
T.md(T.grid([
    T.kpi("🔎", "Markdown first", f"{int(cc.get('INVESTIGATE_MARKDOWN', 0)):,}", "eligible + simulated research ranking",
          T.TEAL, "L2 evidence"),
    T.kpi("🚚", "Transfer first", f"{int(cc.get('INVESTIGATE_TRANSFER', 0)):,}", "same-region store looks short", T.AMBER,
          "L1 · investigate only"),
    T.kpi("❔", "Insufficient evidence", f"{int(cc.get('INSUFFICIENT_EVIDENCE_INVESTIGATE', 0) + cc.get('INSUFFICIENT_EVIDENCE', 0)):,}",
          "no option with usable evidence for the stock in store", "#64748B", "L0 or none"),
    T.kpi("📦", "Next-order reviews", f"{int((at.future_order_outcome == 'REVIEW_NEXT_ORDER').sum()):,}",
          "order above typical demand — separate decision", T.NAVY_3, "L1 · future order"),
]))

# ------------------------------------------------------------------------------------------------ selectors
T.md(T.section("Investigate a line", "Choose a store, product and week with stock at risk."))
if len(at) == 0:
    T.md(T.banner("No line has stock at risk in this scenario — no intervention needed.", "ok", "✅"))
else:
    f1, f2, f3 = st.columns([1, 2, 1])
    store = f1.selectbox("Store", sorted(at.Store_ID.unique()), key=f"wi_store_{scenario}")
    pool = at[at.Store_ID == store]
    prods = pool.groupby(["Product_ID", "Product_Name"]).at_risk_units.sum().sort_values(ascending=False).reset_index()
    prod = f2.selectbox("Product", prods.Product_ID.tolist(), key=f"wi_prod_{scenario}_{store}",
                        format_func=lambda p: prods.set_index("Product_ID").loc[p, "Product_Name"])
    weeks = pool[pool.Product_ID == prod].sort_values("target_week")
    week = f3.selectbox("Order week", weeks.target_week.tolist(), key=f"wi_week_{scenario}_{store}_{prod}")
    L = weeks[weeks.target_week == week].iloc[0]
    o = opts[(opts.Store_ID == store) & (opts.Product_ID == prod) & (opts.origin_week == L.origin_week)].set_index("option")

    share = "—" if pd.isna(L.share_of_typical_week_pct) else f"{L.share_of_typical_week_pct:.0f}% of a typical week"
    rec = "—" if pd.isna(L.recorded_wastage_pct_4w) else f"{L.recorded_wastage_pct_4w:.1f}% of sales"
    T.md(f'<div class="ds-detail"><div class="ds-sub">Store {store} · {T._e(L.Region)} · {T._e(L.product_category)} · '
         f'order week {week} · scenario {scenario}</div><div class="h">{T._e(L.Product_Name)}</div>'
         f'<div style="margin:.4rem 0">{T.chip(str(L.waste_risk_category).title() + " waste risk", "high" if L.waste_risk_category == "HIGH" else "caution")} '
         f'{T.chip(CUR.get(L.current_stock_outcome, L.current_stock_outcome), "info")} '
         f'{T.chip("PENDING_HUMAN_INVESTIGATION · NOT_EXECUTED", "neutral")}</div>'
         + T.grid([
             T.kpi("🗑️", "Units at risk on this line", f"{ui.fmt(L.at_risk_units)} units", share, T.RED, "SIMULATED × FORECAST"),
             T.kpi("📅", "Oldest batch last sellable", L.earliest_batch_last_day_label or "—",
                   f"investigate by {L.investigate_by_label or '—'}", T.AMBER, "SIMULATED dates"),
             T.kpi("🏷️", "Estimated retail value", ui.money(L.estimated_retail_value, 0), "not a saving", T.NAVY_3, "ESTIMATED"),
             T.kpi("💷", "Assumed cost value", ui.money(L.assumed_cost_value, 0), "not a saving", T.NAVY_3, "ASSUMED"),
             T.kpi("📒", "Recorded wastage, last 4 weeks", rec, "history, not this projection", "#64748B", "RECORDED"),
         ]) + f'<div class="ds-panel"><div class="l">Manager summary</div><div class="p">{T._e(L.manager_summary)}</div></div></div>')

    md_row = ui.load_markdown(scenario, "P2").set_index(["Store_ID", "Product_ID", "origin_week"]).loc[
        (store, prod, L.origin_week)]
    p1 = ui.load_recommendations_v6(scenario, "P2")[0].set_index(["Store_ID", "Product_ID", "origin_week"]).loc[
        (store, prod, L.origin_week)]

    def markdown_gates() -> str:
        """Step 1 eligibility vs step 2 evidence: two different questions (read from saved Stage 7B and Phase 1)."""
        elig = md_row.eligibility
        e_ok = elig == "ELIGIBLE_FOR_MARKDOWN_REVIEW"
        e_txt = {"ELIGIBLE_FOR_MARKDOWN_REVIEW": "Eligible", "BLOCKED": "Blocked",
                 "INSUFFICIENT_INFORMATION": "Insufficient information", "NOT_CONSIDERED": "Not considered"}.get(elig, elig)
        e_sub = ("Stage 7B rules allow a person to look at a markdown" if e_ok else
                 "; ".join(M.BLOCKER_LABELS[b] for b in str(md_row.blocker_codes).split("|") if b) or
                 "Stage 7B rules do not allow a markdown review now")
        if not e_ok:
            v_lvl, v_txt, v_sub = "neutral", "Not assessed", "Eligibility is the first gate; evidence is only judged after it"
        elif p1.recommendation_status == R.RECOMMEND:
            v_lvl, v_txt = "ok", "Sufficient to investigate"
            v_sub = (f"Simulated research ranks {int(p1.recommended_markdown_pct)}% first under assumed customer response; "
                     "enough to investigate, not proof that it would work")
        else:
            v_lvl, v_txt = "caution", "Not sufficient"
            v_sub = R.STATUS_LABELS.get(p1.recommendation_status, "No Phase 1 result").split(" — ", 1)[-1].capitalize()
        strong = lambda lvl: T.LEVELS[lvl][0]  # noqa: E731
        return (f'<div class="ds-gate"><div style="--strong:{strong("ok" if e_ok else "high")}"><div class="t">Step 1 · '
                f'Markdown eligibility</div><div class="v">{T._e(e_txt)}</div><div class="s">{T._e(e_sub)}</div></div>'
                f'<div style="--strong:{strong(v_lvl)}"><div class="t">Step 2 · Evidence for a markdown investigation</div>'
                f'<div class="v">{T._e(v_txt)}</div><div class="s">{T._e(v_sub)}</div></div></div>')

    def card(opt: str) -> str:
        r = o.loc[opt]
        parts = lambda s: [x for x in str(s).split("|") if x and x != "nan"]  # noqa: E731
        items = lambda s, mark: "".join(f"<li>{mark} {T._e(x)}</li>" for x in parts(s))  # noqa: E731
        lvl = "" if pd.isna(r.evidence_level) else T.chip(r.evidence_level_label, "info" if r.evidence_level == 2 else
                                                          "caution" if r.evidence_level == 1 else "neutral")
        rank = "" if pd.isna(r.investigation_rank) else T.chip(f"Investigation order {int(r.investigation_rank)}", "neutral")
        key = (parts(r.evidence_for) or parts(r.evidence_against) or [""])[0]
        n = sum(len(parts(x)) for x in (r.evidence_for, r.evidence_against, r.missing_information, r.human_checks))
        link = f'<div class="lab">Related page</div><div class="p">{T._e(r.linked_page)} (left sidebar)</div>' \
            if isinstance(r.linked_page, str) else ""
        return (f'<div class="ds-card ds-road"><div class="h">{r.letter} · {T._e(r.title)}</div>'
                f'<div style="margin:.35rem 0">{T.chip(r.status_label, LEVEL[r.status])} {lvl} {rank}</div>'
                f'<div class="p">{T._e(r.explanation)}</div>'
                + (markdown_gates() if opt == "MARKDOWN" else "")
                + (f'<div class="ds-key"><b>Key point:</b> {T._e(key)}</div>' if key else "")
                + f'<details class="ds-more"><summary>Evidence, blockers, missing information and human checks ({n})</summary>'
                + (f'<div class="lab">Evidence for</div><ul>{items(r.evidence_for, "✔")}</ul>' if r.evidence_for else "")
                + (f'<div class="lab">Limitations and blockers</div><ul>{items(r.evidence_against, "✖")}</ul>'
                   if r.evidence_against else "")
                + f'<div class="lab">Missing information</div><ul>{items(r.missing_information, "❔")}</ul>'
                f'<div class="lab">Human checks required</div><ul>{items(r.human_checks, "👤")}</ul>{link}</details></div>')

    REASON = {"MARKDOWN": "the line is eligible for markdown review and a simulated research ranking exists",
              "TRANSFER": "a store in the same region looks short of this product in the simulation",
              "DONATION_OR_DISPOSAL": "only the size of the stock at risk is known"}
    ranked = o[(o.decision_group == "CURRENT_STOCK") & o.investigation_rank.notna()].sort_values("investigation_rank")
    if isinstance(L.current_stock_first, str) and L.current_stock_outcome.startswith("INVESTIGATE_"):
        f = o.loc[L.current_stock_first]
        why = (f"<b>{T._e(f.title)}</b> comes first because it has the strongest evidence available for this line "
               f"({T._e(f.evidence_level_label)}): {REASON[L.current_stock_first]}.")
        rest = [f"{T._e(r.title.lower())} is {T._e(r.evidence_level_label.split(' — ')[0])} ({REASON[i]})"
                for i, r in ranked.iloc[1:].iterrows()]
        if rest:
            why += " Next: " + "; ".join(rest) + "."
    elif L.current_stock_outcome == "INSUFFICIENT_EVIDENCE_INVESTIGATE":
        why = ("No option for the stock in store has better than L0 evidence. Only donation or another disposal route "
               "remains, and nothing is known about it, so the honest answer is <b>insufficient evidence: investigate "
               "manually</b>.")
    else:
        why = ("No option for the stock in store has usable evidence, so nothing is ranked. "
               + ("Under the stated assumptions keeping the full price ranks first." if L.current_stock_outcome ==
                  "NO_ACTION_SUPPORTED" else "Check the shelf and decide manually."))
    blocked = [r.title.lower() for i, r in o.iterrows() if r.decision_group == "CURRENT_STOCK" and r.status in
               ("BLOCKED", "INSUFFICIENT_EVIDENCE", "NOT_APPLICABLE") and i != "NO_ACTION"]
    T.md(T.banner(f"<b>Why this investigation comes first.</b> {why}"
                  + (f" Not ranked: {T._e(', '.join(blocked))} (blocked, not applicable or not enough evidence)." if blocked else "")
                  + " This is the order of investigation by evidence quality, not a judgement that it is the best "
                    "commercial action.", "info", "🧭"))

    T.md(T.section("Stock already in the store", "It expires whatever the next order does. Options C, B, D and E; open "
                                                 "a card's details for the full evidence."))
    T.md('<div class="ds-cards2">' + card("MARKDOWN") + card("TRANSFER") + card("DONATION_OR_DISPOSAL") + card("NO_ACTION")
         + "</div>")
    T.md(T.section("The next replenishment order", "A separate decision. Changing the next order cannot save stock already "
                                                   "approaching expiry. Option A."))
    T.md('<div class="ds-cards2">' + card("REPLENISHMENT_REVIEW")
         + T.use_case("ℹ️", "Why this is separate", "The order for this week is the protected P2 decision and is never "
                      "changed here. A reviewed order would only affect stock that arrives later. What a smaller order "
                      "would change is not simulated in Phase 3.") + "</div>")

    # ---------------------------------------------------------------------------------------- weekly history
    T.md(T.section("Weekly history for this product", f"Store {store}, every simulated week (read-only)."))
    hist = lines[(lines.Store_ID == store) & (lines.Product_ID == prod)].sort_values("target_week")
    risk_names = {"HIGH": "High", "MODERATE": "Moderate", "LOW": "Low", "INSUFFICIENT_INFORMATION": "Insufficient information"}
    chart = alt.Chart(hist.assign(units=hist.at_risk_units.fillna(0), risk=hist.waste_risk_category.map(risk_names))).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
        x=alt.X("target_week:O", title="Order week", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("units:Q", title="Units projected to expire"),
        color=alt.Color("risk:N", title=None,
                        scale=alt.Scale(domain=list(risk_names.values()),
                                        range=[T.RED, T.AMBER, "#94A3B8", "#CBD5E1"]),
                        legend=alt.Legend(orient="bottom", labelFontSize=12)),
        tooltip=[alt.Tooltip("target_week:O", title="Week"), alt.Tooltip("risk:N", title="Waste risk"),
                 alt.Tooltip("units:Q", title="Units at risk", format=",.0f")])
    st.altair_chart(T.chart(chart.properties(title=alt.TitleParams("Projected expiry by week", fontSize=15, anchor="start",
                                                                   color=T.NAVY, font=T.FONT)), 320), width="stretch")
    T.md(T.table(["Order week", "Waste risk", "Units at risk", "Stock in store", "Next order"], [
        (int(h.target_week), str(h.waste_risk_category).title(), ui.fmt(h.at_risk_units),
         T.chip(CUR.get(h.current_stock_outcome, h.current_stock_outcome), "info" if str(h.current_stock_outcome).startswith(
             "INVESTIGATE_") else "neutral"),
         "Review size" if h.future_order_outcome == "REVIEW_NEXT_ORDER" else "No change suggested")
        for h in hist.itertuples()], html_cols=("Stock in store",)))

# -------------------------------------------------------------------------------------------- investigation queue
T.md(T.section("Investigation queue", "Every line with stock at risk in this scenario — read-only, "
                                      "PENDING_HUMAN_INVESTIGATION. Nothing can be assigned, approved or executed."))
if len(at):
    c1, c2, c3 = st.columns([2.2, 1, 0.8])
    choice = c1.multiselect("Show", list(CUR)[:5], default=list(CUR)[:4], format_func=CUR.get, key=f"wi_q_{scenario}")
    sort = c2.selectbox("Sort by", ("Units at risk", "Retail value (est.)", "Order week"), key=f"wi_qs_{scenario}")
    rows = c3.selectbox("Rows", (25, 50, 100), key=f"wi_qn_{scenario}")
    col = {"Units at risk": "at_risk_units", "Retail value (est.)": "estimated_retail_value", "Order week": "target_week"}[sort]
    q = at[at.current_stock_outcome.isin(choice)].sort_values(col, ascending=col == "target_week")
    risk = {"HIGH": ("High", "high"), "MODERATE": ("Moderate", "caution")}
    T.md('<div class="ds-num">' + T.table(
        ["Store", "Product", "Week", "Risk", "Units at risk", "Retail value (est.)", "Stock in store", "Next order"], [
            (f"{int(r.Store_ID)} · {r.Region}", r.Product_Name, int(r.target_week),
             T.chip(*risk.get(r.waste_risk_category, (str(r.waste_risk_category).title(), "neutral"))),
             ui.fmt(r.at_risk_units), ui.money(r.estimated_retail_value, 0),
             T.chip(CUR.get(r.current_stock_outcome, r.current_stock_outcome),
                    "info" if str(r.current_stock_outcome).startswith("INVESTIGATE_") else "neutral"),
             "Review size" if r.future_order_outcome == "REVIEW_NEXT_ORDER" else "—") for r in q.head(rows).itertuples()],
        html_cols=("Risk", "Stock in store")) + "</div>")
    st.caption(f"Showing {min(rows, len(q)):,} of {len(q):,} lines, sorted by {sort.lower()}. Values are illustrative, "
               "never savings.")
    with st.expander(f"All {len(q):,} queued lines"):
        st.dataframe(q[["Store_ID", "Product_Name", "target_week", "waste_risk_category", "at_risk_units",
                        "estimated_retail_value", "assumed_cost_value", "current_stock_outcome", "future_order_outcome",
                        "review_status", "execution_status"]], hide_index=True, width="stretch", height=300)

with st.expander("Technical details — rules, evidence levels, parameters and sources"):
    st.markdown(
        "- **At risk:** Stage 6B waste-risk class High or Moderate on the protected P2 replay (decision-time evidence only).\n"
        "- **Evidence levels:** L2 simulated with a modelled consequence (markdown: Stage 7B eligibility + Phase 1 ranking); "
        "L1 simulated pattern only (transfer pairing, order buffer); L0 no evidence (donation or disposal).\n"
        "- **Investigation order (stock in store):** highest level first; ties markdown → transfer → donation (fewer outside "
        "parties first). Only L0 left → INSUFFICIENT EVIDENCE — investigate.\n"
        "- **Transfer pairing:** same product, same region, same decision week, another store projected short before its "
        "next delivery. Region stands in for distance. Always INVESTIGATE ONLY.\n"
        f"- **Donation or disposal:** suggested for investigation from {prm['waste_intervention_donation_min_units']} units "
        "at risk. Always INVESTIGATE ONLY.\n"
        "- **Next order:** a candidate for review when the simulated order is above typical (p50) demand within its shelf "
        "life and the line is not projected short; blocked when it may run short.\n"
        "- **Values:** units × estimated reference price, and × assumed cost (reference price × (1 − assumed margin)).\n"
        f"- **Sources:** protected P2 replay {D.COMPARISON_DIR.name}; pricing context {D.DYNAMIC_PRICING_A1_RUN_ID} (A1, "
        f"central response); assumption set {prm['assumption_set_id']} ({prm['assumption_status']}).")
    st.json({k: v for k, v in prm.items() if k.startswith("waste_intervention")}, expanded=False)
