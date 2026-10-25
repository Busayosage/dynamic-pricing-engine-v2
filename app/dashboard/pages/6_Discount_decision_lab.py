import altair as alt
import pandas as pd
import streamlit as st

import dashboard_data as D
import theme as T
import ui
from dpe.decision import discount_recommendation as R
from dpe.decision import pricing_demo as PD

ui.page("Discount Decision Lab", "🧪")
scenario = ui.scenario_select()
policy = ui.policy_select()
prm = ui.load_recommendation_params()
dp = prm["pricing_display_decimals"]
policy_name = D.POLICY_NAMES[policy].split(" — ")[1]
scenario_name = D.SCENARIO_NAMES[scenario].split(" — ")[1]

T.md(T.head("Numerical discount recommendations · Phase 1 · simulated research · read-only", "Discount Decision Lab",
            "Compares every permitted markdown with keeping the full price, under stated customer-response scenarios, "
            "and either ranks one option or says why there is no recommendation.",
            chips=(f"Policy {policy}", f"Scenario {scenario}", "Not validated for live use",
                   f"Parameters {prm['assumption_set_id']} ({prm['assumption_status']})"), art="coin"))
T.md(T.banner(f"<b>{R.LABEL}.</b> Every ranking here comes from estimated prices, assumed costs, simulated stock and "
              "stated customer-response scenarios. Nothing is proposed, approved, published or executed, and no price "
              "changes. There are no approval buttons.", "coral", "🧪"))
T.md(f'<div class="ds-sub" style="font-size:1rem;margin:.2rem 0 .6rem 0">Lines from inventory policy {policy} — '
     f'{T._e(policy_name)}, scenario {scenario} — {T._e(scenario_name)}. Only lines that Markdown review marks eligible '
     'are assessed. Change either in the left sidebar.</div>')
T.md(T.disclaimer())

T.md(T.section("What each number is based on", "Four kinds of information, kept apart on every screen."))
T.md(T.grid([
    T.use_case("📒", "Recorded / forecast", "Recorded shelf price that week (noisy, apparently synthetic data) and the "
               "protected 1-week sales forecast range (p10 / p50 / p90). Nothing here is verified business data."),
    T.use_case("🧪", "Simulation outputs", "Stock already in store projected to go out of date, and the dates of the "
               "oldest batch — from the protected inventory replay."),
    T.use_case("📐", "Assumptions", "Reference price (estimated proxy), unit cost (assumed margin), margin floor, maximum "
               "markdown, steps, customer-response scenarios and decision limits — assumption set "
               f"{prm['assumption_set_id']}, DRAFT."),
    T.use_case("🗂️", "Hypothetical decisions", "The ranking and its explanation. HYPOTHETICAL_UNAPPROVED and "
               "NOT_EXECUTED — a research output for discussion only."),
]))

lines, outcomes = ui.load_recommendations_v6(scenario, policy)
s = R.summary(lines)
T.md(T.section("This scenario at a glance", "Results of the engine for every eligible line in the selected policy and "
                                            "scenario."))
T.md(T.grid([
    T.kpi("🔎", "Lines assessed", f"{s['assessed']:,}", "eligible for markdown review", T.NAVY_3, "Eligibility evidence"),
    T.kpi("🧪", "Simulated research recommendations", f"{s[R.RECOMMEND]:,}", "an option ranks first — not validated",
          T.TEAL, "Hypothetical"),
    T.kpi("⚪", "No recommendation — evidence", f"{s[R.EVIDENCE]:,}", "missing or conflicting evidence", T.AMBER,
          "Evidence gate"),
    T.kpi("⚖️", "No recommendation — other", f"{s[R.KEEP] + s[R.UNCERTAIN] + s[R.CONSTRAINED]:,}",
          f"keep full price {s[R.KEEP]} · too uncertain {s[R.UNCERTAIN]} · all blocked {s[R.CONSTRAINED]}", "#64748B",
          "Decision rules"),
]))

T.md(T.section("Customer-response scenarios used", "Stated research scenarios — not measured elasticities."))
resp, weights = prm["demand_response_scenarios_pct_per_point"], prm["demand_response_decision_weights"]
T.md(T.grid([
    T.kpi("🧊", R.SCENARIO_LABELS[k], f"+{v:g}% per point", ("weight " + f"{weights[k]:.0%}") if k in weights
          else "stress test only — not weighted", {"R0_NO_RESPONSE": "#94A3B8", "R1_LOW": "#2563EB",
                                                   "R2_CENTRAL": T.TEAL, "R3_HIGH": T.NAVY}[k], "ASSUMED")
    for k, v in resp.items()]))
T.md(T.banner("<b>Unverified customer response.</b> “+1.6% per point” is a non-causal association seen in apparently "
              "synthetic historical data; it is used only as the central scenario. A markdown is not shown to increase "
              "sales, reduce waste or improve profit — each figure says what would follow <i>if</i> customers responded "
              "as stated.", "caution", "⚠️"))

assessed = lines[lines.recommendation_status != R.NOT_ELIGIBLE].copy()
T.md(T.section("Selected line", "Choose an eligible line to see how its options compare."))
if len(assessed) == 0:
    T.md(T.banner("No line is eligible for a markdown review under this policy and scenario, so nothing is assessed.",
                  "neutral", "ℹ️"))
else:
    order = {k: i for i, k in enumerate((R.RECOMMEND, R.UNCERTAIN, R.KEEP, R.CONSTRAINED, R.EVIDENCE))}
    assessed = assessed.assign(_o=assessed.recommendation_status.map(order)).sort_values(
        ["_o", "at_risk_units"], ascending=[True, False])
    f1, f2, f3 = st.columns([1, 1.6, 2.4])
    store = f1.selectbox("Store", ["All stores"] + sorted(assessed.Store_ID.unique()), key=f"dl_store_{scenario}_{policy}")
    pool = assessed if store == "All stores" else assessed[assessed.Store_ID == store]
    product = f2.selectbox("Product", ["All products"] + sorted(pool.Product_Name.dropna().unique()),
                           key=f"dl_product_{scenario}_{policy}")
    pool = pool if product == "All products" else pool[pool.Product_Name == product]
    pick = f3.selectbox(f"Line ({len(pool):,})", pool.index.tolist(), key=f"dl_pick_{scenario}_{policy}",
                        format_func=lambda i: f"{pool.loc[i, 'Product_Name']} · store {pool.loc[i, 'Store_ID']} · "
                                              f"order week {pool.loc[i, 'target_week']} · "
                                              f"{R.STATUS_LABELS[pool.loc[i, 'recommendation_status']]}")
    L = pool.loc[pick]
    o = outcomes[(outcomes.Store_ID == L.Store_ID) & (outcomes.Product_ID == L.Product_ID) &
                 (outcomes.origin_week == L.origin_week)]
    money = lambda x, d=dp: "—" if pd.isna(x) else ui.money(x, d)  # noqa: E731
    rec_price = money(L.recorded_price_origin_week)
    T.md(f'<div class="ds-detail"><div class="ds-sub">Store {L.Store_ID} · {T._e(L.Region)} · {T._e(L.product_category)} · '
         f'order week {L.target_week} · policy {L.policy_id}, scenario {L.scenario_id}</div>'
         f'<div class="h">{T._e(L.Product_Name)}</div>'
         + T.grid([
             T.kpi("🏷️", "Current price (reference)", money(L.base_price), "estimated reference-price proxy", T.NAVY_3,
                   "ESTIMATED"),
             T.kpi("💷", "Unit cost", money(L.get("unit_cost")),
                   f"{L.assumed_gross_margin_pct:g}% assumed margin" if pd.notna(L.assumed_gross_margin_pct) else "—",
                   T.AMBER, "ASSUMED"),
             T.kpi("🧾", "Recorded shelf price that week", rec_price, "cross-check only", "#64748B", "RECORDED · noisy"),
             T.kpi("🗑️", "Simulated expiry exposure", f"{ui.fmt(L.at_risk_units)} units",
                   f"stock at stake ≈ {money(L.get('at_risk_stock_cost'), 0)} at assumed cost", T.RED,
                   "SIMULATED × FORECAST"),
             T.kpi("📅", "Markdown window", f"{int(L.window_days)} day(s)" if pd.notna(L.window_days) else "—",
                   f"{L.investigate_by_label or '—'} → {L.earliest_batch_last_day_label or '—'}", T.TEAL, "SIMULATED dates"),
         ]) + "</div>")

    # ------------------------------------------------------------------------------------------- the result
    st_ = L.recommendation_status
    if st_ == R.RECOMMEND:
        headline, level, icon = f"{int(L.recommended_markdown_pct)}% markdown ranks first", "info", "🧪"
    else:
        headline, level, icon = "NO RECOMMENDATION", "neutral" if st_ == R.KEEP else "caution", "⚪"
    T.md(T.section("Result", R.STATUS_LABELS[st_]))
    T.md(f'<div class="ds-card" style="border-left:6px solid {T.TEAL if st_ == R.RECOMMEND else T.AMBER};padding:1.1rem 1.3rem">'
         f'<div class="ds-sub" style="font-weight:700;letter-spacing:.04em">{T._e(R.LABEL if st_ == R.RECOMMEND else "ENGINE RESULT — READ-ONLY")}</div>'
         f'<div style="font-size:2rem;font-weight:800;color:{T.NAVY};margin:.2rem 0">{icon} {T._e(headline)}</div>'
         f'<div style="margin:.3rem 0 .6rem 0">{T.chip(R.STATUS_LABELS[st_], level)} '
         f'{T.chip("HYPOTHETICAL_UNAPPROVED · NOT_EXECUTED", "neutral")}</div>'
         f'<div class="ds-panel"><div class="l">In plain English</div><div class="p">{T._e(L.explanation)}</div></div></div>')
    gaps = [g for g in str(L.evidence_gaps or "").split("|") if g and g != "nan"]
    warn = [f"<b>Evidence quality:</b> {T._e(R.EVIDENCE_QUALITY)}."]
    if pd.notna(L.get("price_difference_recorded_vs_reference_pct")):
        warn.append(f"Recorded shelf price differs from the reference price by "
                    f"{L.price_difference_recorded_vs_reference_pct:+.1f}% (limit ±{prm['price_evidence_conflict_tolerance_pct']}%).")
    warn += [f"⛔ {T._e(R.EVIDENCE_LABELS[g])}." for g in gaps]
    warn.append("Cooldown between markdowns is not implemented; real costs, batch stock and approvers do not exist.")
    T.md(T.banner("<br>".join(warn), "caution", "⚠️"))

    if len(o) == 0:
        T.md(T.banner("Options are not compared for this line because the evidence gate failed.", "neutral", "ℹ️"))
    else:
        opt = o.drop_duplicates("markdown_pct").set_index("markdown_pct")
        case = lambda c: o[o.case == c].set_index("markdown_pct")["delta_vs_full_price"]  # noqa: E731
        down_case = next(c for c in o.case.unique() if c.endswith("(downside)"))
        signed = lambda x: "—" if pd.isna(x) else (f"+{ui.money(x, dp)}" if x >= 0 else f"−{ui.money(-x, dp)}")  # noqa: E731
        central_saved = o[o.case == "R2@p50"].set_index("markdown_pct")["extra_units"]
        result = []
        for d, r in opt.iterrows():
            if d == 0:
                result.append("Reference")
            elif not r.permitted:
                result.append("⛔ Blocked")
            elif r.is_recommended:
                result.append("🧪 Ranks first (simulated)")
            elif not r.material:
                result.append("Below benefit threshold")
            elif not r.within_downside_limit:
                result.append("Downside too large")
            else:
                result.append("Permitted")
        table = pd.DataFrame({
            "Markdown": [("0% (full price)" if d == 0 else f"{d}%") for d in opt.index],
            "Selling price": opt.illustrative_price.map(lambda x: ui.money(x, dp)).values,
            "Margin %": opt.gross_margin_pct.map(lambda x: f"{x:.1f}%").values,
            "Rules check": opt.status.map({PD.FULL_PRICE: "— (reference)", PD.PASSES: "✅ Passes", PD.BLOCKED: "⛔ Blocked"}).values,
            "Expected change vs full price*": [signed(r.expected_delta) if r.permitted else "—" for _, r in opt.iterrows()],
            "If no response": case("R0@p50").map(signed).values,
            "If low response": case("R1@p50").map(signed).values,
            "If central response": case("R2@p50").map(signed).values,
            "If high response": case("R3@p50").map(signed).values,
            "Weak response, high demand": case(down_case).map(signed).values,
            "Fewer units expiring (central)": central_saved.map(lambda x: f"{x:,.0f}").values,
            "Rank": [("—" if pd.isna(x) else f"{int(x)}") for x in opt["rank"]],
            "Result": result,
            "Why blocked": opt.blocking_reasons.replace("", "—").values})
        T.md(T.section("Markdown options compared", "Change in window gross profit compared with keeping the full price, "
                                                    "by customer-response scenario."))
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption(f"*Weighted across low ({weights['R1_LOW']:.0%}), central ({weights['R2_CENTRAL']:.0%}) and high "
                   f"({weights['R3_HIGH']:.0%}) response at typical (p50) demand — research weights, not probabilities. "
                   f"An option needs at least {ui.money(L.min_expected_benefit, dp)} expected benefit and may not lose more "
                   f"than {ui.money(L.max_downside_loss, dp)} ({prm['recommendation_max_downside_loss_pct_of_at_risk_cost']}% "
                   "of the stock at stake) with weak response and high (p90) demand. Gross profit counts the assumed cost "
                   "of all stock in the window, so it is not a saving and not a forecast.")

        short = {"R0_NO_RESPONSE": "No response", "R1_LOW": "Low", "R2_CENTRAL": "Central (not causal)", "R3_HIGH": "High"}
        cd = o[o.case.isin(["R0@p50", "R1@p50", "R2@p50", "R3@p50"]) & (o.permitted | (o.markdown_pct == 0))].assign(
            scenario_label=lambda x: x.scenario.map(short), step=lambda x: x.markdown_pct.map(lambda d: f"{d}%"))
        dom = list(short.values())
        steps_order = [f"{d}%" for d in sorted(cd.markdown_pct.unique())]
        base = alt.Chart(cd).encode(
            x=alt.X("step:N", title="Markdown step", sort=steps_order, axis=alt.Axis(labelAngle=0, labelFontSize=13)),
            y=alt.Y("delta_vs_full_price:Q", title="Change vs full price (£)"),
            color=alt.Color("scenario_label:N", title=None, sort=dom,
                            scale=alt.Scale(domain=dom, range=["#94A3B8", "#2563EB", T.TEAL, T.NAVY]),
                            legend=alt.Legend(orient="bottom", labelFontSize=12)),
            tooltip=[alt.Tooltip("step:N", title="Markdown"), alt.Tooltip("scenario_label:N", title="Scenario"),
                     alt.Tooltip("delta_vs_full_price:Q", title="Change vs full price (£)", format=",.2f"),
                     alt.Tooltip("extra_units:Q", title="Extra units sold", format=",.0f")])
        zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=T.INK, strokeWidth=1).encode(y="y:Q")
        c1 = (base.mark_line(strokeWidth=2.5) + base.mark_point(filled=True, size=90) + zero).properties(
            title=alt.TitleParams("Gross-profit change by scenario", fontSize=15, anchor="start", color=T.NAVY, font=T.FONT))
        ex = o[(o.case == "R2@p50") & (o.permitted | (o.markdown_pct == 0))].assign(
            step=lambda x: x.markdown_pct.map(lambda d: f"{d}%"),
            pick=lambda x: x.is_recommended.map({True: "Ranks first (simulated)", False: "Other permitted step"}))
        bars = alt.Chart(ex).encode(
            x=alt.X("step:N", title="Markdown step", sort=steps_order, axis=alt.Axis(labelAngle=0, labelFontSize=13)),
            y=alt.Y("expired_units:Q", title="Units going out of date"),
            color=alt.Color("pick:N", title=None, scale=alt.Scale(domain=["Ranks first (simulated)", "Other permitted step"],
                                                                  range=[T.TEAL, "#94A3B8"]),
                            legend=alt.Legend(orient="bottom", labelFontSize=12)),
            tooltip=[alt.Tooltip("step:N", title="Markdown"), alt.Tooltip("expired_units:Q", title="Units expiring", format=",.0f")])
        c2 = (bars.mark_bar(size=40, cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
              + bars.mark_text(dy=-9, fontSize=12, fontWeight="bold", color=T.INK).encode(text=alt.Text("expired_units:Q", format=",.0f"))
              ).properties(title=alt.TitleParams("Simulated units going out of date (central response)", fontSize=15,
                                                 anchor="start", color=T.NAVY, font=T.FONT))
        g1, g2 = st.columns(2, gap="large")
        g1.altair_chart(T.chart(c1, 300), width="stretch")
        g2.altair_chart(T.chart(c2, 300), width="stretch")
        st.caption("Blocked steps are left out of the charts. Each line shows what would follow if customers responded as "
                   "that scenario states; none is a forecast.")

        with st.expander("Technical calculations — formulas, every case at full precision, parameters"):
            st.markdown(
                "- **Baseline units in the window** S0 = forecast weekly quantile ÷ 7 × window days (p50 for the "
                "scenarios; p10 / p90 for the demand band; p90 for the downside check)\n"
                "- **Extra units** = min(S0 × response % per point × markdown points ÷ 100, units at risk)\n"
                "- **Window gross profit** = units sold × price − unit cost × (S0 + units at risk) − expired units × unit "
                "cost × disposal %\n"
                "- **Change vs full price** = gross profit at the markdown − gross profit at full price\n"
                "- **Decision**: evidence gates → rule checks → expected change ≥ benefit threshold → downside within the "
                "limit → rank by expected change, then smaller downside, then the smaller markdown")
            st.dataframe(o[["markdown_pct", "case", "scenario", "baseline_quantile", "baseline_units", "price", "extra_units",
                            "units_sold", "expired_units", "revenue", "gross_profit", "delta_vs_full_price",
                            "expected_delta", "downside_delta", "permitted", "material", "within_downside_limit", "rank",
                            "is_recommended", "blocker_codes"]], hide_index=True, width="stretch", height=320)
            st.write({"recommendation_status": st_, "recommended_markdown_pct": None if pd.isna(L.recommended_markdown_pct)
                      else int(L.recommended_markdown_pct), "status": L.status, "execution_status": L.execution_status,
                      "proposal_id": None, "approval_event_id": None, "assumption_set_id": prm["assumption_set_id"],
                      "assumption_content_sha256": prm["assumption_content_sha256"],
                      "disposal_cost_pct_of_unit_cost": prm["expiry_disposal_cost_pct_of_unit_cost"]})

    with st.expander(f"All {len(assessed):,} assessed lines in this scenario"):
        st.dataframe(pd.DataFrame({
            "Store": assessed.Store_ID, "Product": assessed.Product_Name, "Order week": assessed.target_week,
            "Result": assessed.recommendation_status.map(R.STATUS_LABELS),
            "Markdown ranked first (simulated)": assessed.recommended_markdown_pct.map(
                lambda x: "—" if pd.isna(x) else f"{int(x)}%"),
            "Expected change": assessed.expected_delta, "Units at risk": assessed.at_risk_units}),
            hide_index=True, width="stretch", height=320,
            column_config={"Expected change": st.column_config.NumberColumn(format="£%.2f"),
                           "Units at risk": st.column_config.NumberColumn(format="%.0f")})

T.md(T.section("What stays human", "The engine ranks options for research; people decide."))
T.md(T.steps([
    ("1", "Eligible", "Markdown review — built.", T.EMERALD),
    ("1b", "Simulated ranking", "This page — research engine, not validated.", T.TEAL),
    ("2", "Proposal — NOT BUILT", "A bounded proposal on verified evidence.", "#94A3B8"),
    ("3", "Approval — NOT BUILT", "A named, authorised person decides.", "#94A3B8"),
    ("4", "Execution — NOT BUILT", "In the store's own price system, audited.", "#94A3B8"),
]))
ui.link_to("pages/5_Markdown_review.py", label="Back to Markdown review", icon="🏷️")
