import altair as alt
import pandas as pd
import streamlit as st

import dashboard_data as D
import theme as T
import ui
from dpe.decision import dynamic_pricing as DP
from dpe.decision import waste_risk as W

ui.page("Dynamic Pricing Lab", "📈")
scenario = ui.scenario_select()
scenario_name = D.SCENARIO_NAMES[scenario].split(" — ")[1]
SHORT = {"R0_NO_RESPONSE": "No response", "R1_LOW": "Low response", "R2_CENTRAL": "Central response",
         "R3_HIGH": "High response"}
LABEL = "SIMULATED RESEARCH — NOT VALIDATED FOR LIVE USE"

T.md(T.head("Dynamic pricing · Phase 2 · simulated research · read-only", "Dynamic Pricing Lab",
            "Weekly markdown decisions simulated inside the inventory replay over 20 weeks, compared with an otherwise "
            "identical replay where prices never change.",
            chips=(f"Scenario {scenario}", "Ordering policy P2 (unchanged)", "Original rule and A1 amendment"),
            art="chart"))
T.md(T.banner(f"<b>{LABEL}.</b> Every markdown here is SIMULATED · HYPOTHETICAL_UNAPPROVED · NOT_EXECUTED. It is applied "
              "inside the simulation only as if approved, so its consequences can be measured. No price, order or "
              "approval exists, and there are no approval or execution controls.", "coral", "🧪"))
T.md(T.disclaimer())
T.md(T.grid([
    T.use_case("📒", "Recorded / forecast", "Recorded weekly sales (illustrative demand, apparently synthetic) and the "
               "protected 1-week forecast range. Not verified business data."),
    T.use_case("🧪", "Simulation outputs", "Stock, deliveries, sales, expiry and unmet units from the replay — with and "
               "without pricing."),
    T.use_case("📐", "Assumptions", "Reference price, assumed cost, rules, the customer response used to choose a "
               "markdown, and the 'true' response used to simulate it — assumption sets v6 / v7 (original) and v8 (A1), DRAFT."),
    T.use_case("🗂️", "Hypothetical decisions", "Every markdown and its explanation. PENDING_HUMAN_REVIEW; nothing is "
               "proposed for live use."),
]))

RULES = {"A1": "A1 cooldown rule (preferred research rule)", "ORIGINAL": "Original Phase 2 rule (comparison)"}
decision = ui.load_dp_rule_decision()
if "dp_rule" not in st.session_state:
    st.session_state["dp_rule"] = D.PREFERRED_RULE
rule = st.radio("Cooldown rule shown on this page", tuple(RULES), horizontal=True, format_func=RULES.get, key="dp_rule")
T.md(T.banner(f"<b>A1 is the PREFERRED RESEARCH RULE — NOT PRODUCTION APPROVED</b> ({T._e(decision['decision_id'])}, "
              f"{T._e(decision['recorded_at'])}). The original Phase 2 rule stays available as a reproducible comparison. "
              "No rule is approved for live use, and every markdown remains hypothetical, unapproved and not executed.",
              "caution", "🏷️"))
ev, man, comp = ui.load_dp_evaluation(rule), ui.load_dp_manifest(rule), ui.load_dp_comparison(rule)
T.md(T.banner(f"<b>{T._e(D.RULE_NAMES[rule])}.</b> Results on this page come from research run <b>{T._e(man['run_id'])}</b> "
              f"under evaluation policy <b>{T._e(ev['evaluation_policy_id'])}</b>"
              + (" (the frozen original evaluation)." if rule == "ORIGINAL" else
                 " (a separately versioned amendment; the original run is unchanged)."), "info", "🗂️"))
truth = st.radio("Customer response that actually happens in the simulation (the “true” response)", D.TRUE_RESPONSES,
                 index=2, horizontal=True, format_func=SHORT.get, key=f"dp_truth_{scenario}")
st.caption("Markdowns are always chosen with the same assumed belief (low 25% · central 50% · high 25%). The selector "
           "changes only how customers respond in the simulation — use “No response” to see the stress case.")
row = comp[(comp.scenario_id == scenario) & (comp.true_response == truth)].iloc[0]
th = ev["thresholds"][scenario]
m = ev["measures"][f"{scenario}/{truth}"]


def signed_money(x, d=0):
    return f"+{ui.money(x, d)}" if x >= 0 else f"−{ui.money(-x, d)}"


def signed(x):
    return f"{x:+,.0f}"


# ---------------------------------------------------------------------------------------- executive summary
T.md(T.section(f"Executive summary — {scenario} {scenario_name}, {SHORT[truth].lower()}",
               "Totals over all 720 lines and 20 simulated weeks, compared with unchanged prices."))
T.md(T.grid([
    T.kpi("💷", "Gross profit vs unchanged prices", signed_money(row.delta_gross_profit),
          f"baseline {ui.money(row.baseline_gross_profit, 0)}", T.EMERALD if row.delta_gross_profit >= 0 else T.RED,
          "SIMULATED × ASSUMED"),
    T.kpi("🗑️", "Units going out of date", signed(row.delta_sim_expired_units),
          f"baseline {row.baseline_sim_expired_units:,.0f} units", T.EMERALD if row.delta_sim_expired_units <= 0 else T.RED,
          "SIMULATED"),
    T.kpi("🛒", "Customers could not buy*", signed(row.delta_sim_unmet_units_illustrative),
          f"baseline {row.baseline_sim_unmet_units_illustrative:,.0f} units",
          T.EMERALD if row.delta_sim_unmet_units_illustrative <= 0 else T.AMBER, "ILLUSTRATIVE"),
    T.kpi("🏷️", "Hypothetical markdowns", f"{int(row.markdown_events):,}",
          f"{int(row.lines_with_markdowns):,} lines · {int(row.mandatory_reviews):,} mandatory reviews", T.TEAL,
          "PENDING_HUMAN_REVIEW"),
]))
st.caption("*Illustrative unmet demand in a simulated replay — not observed lost sales. A markdown raises demand on its "
           "days, which can exceed the stock on the shelf.")
gp_share = 100 * row.delta_gross_profit / row.baseline_gross_profit if row.baseline_gross_profit else 0.0
ex_share = 100 * row.delta_sim_expired_units / row.baseline_sim_expired_units if row.baseline_sim_expired_units else 0.0
T.md(T.banner(f"<b>Scale:</b> the gross-profit change is {gp_share:+.3f}% of the scenario's baseline gross profit and the "
              f"expiry change is {ex_share:+.3f}% of its baseline expired units. Markdowns reach only eligible lines in a "
              "few weeks, so the simulated effects are small, and they depend entirely on the assumed customer response.",
              "info", "📏"))
c1, c2 = st.columns(2, gap="large")
with c1:
    T.md(T.banner(f"<b>Simulated benefits</b><br>Gross-profit gain: {ui.money(m['benefits']['gross_profit_gain'], 0)}<br>"
                  f"Units kept from going out of date: {m['benefits']['expired_units_avoided']:,.0f}<br>"
                  f"Lines where gross profit rose: {int(row.lines_gross_profit_rose):,}", "ok", "✅"))
with c2:
    T.md(T.banner(f"<b>Simulated harms</b><br>Gross-profit loss: {ui.money(m['harms']['gross_profit_loss'], 0)}<br>"
                  f"Extra units customers could not buy: {m['harms']['extra_unmet_units']:,.0f}<br>"
                  f"Lines where gross profit fell: {int(row.lines_gross_profit_fell):,} · markdowns needing review: "
                  f"{int(row.markdown_events):,}", "high", "⚠️"))

# ------------------------------------------------------------------------------ assumed vs true response matrix
T.md(T.section("Assumed versus actual simulated customer response",
               "The engine always assumes the same mix of responses; each row shows what happens if customers actually "
               "respond that way."))
tmap = {"R0_NO_RESPONSE": "T4_R0_NO_RESPONSE", "R1_LOW": "T3_R1_LOW", "R2_CENTRAL": "T1_R2_CENTRAL", "R3_HIGH": "T2_R3_HIGH"}
lvl = {"PASS": "ok", "FAIL": "high", "NOT_APPLICABLE": "neutral"}
rows = []
for t in D.TRUE_RESPONSES:
    r = comp[(comp.scenario_id == scenario) & (comp.true_response == t)].iloc[0]
    res, unmet = th[tmap[t]], th[f"T5_UNMET_{t}"]
    rows.append((SHORT[t] + (" (stress test)" if t == "R0_NO_RESPONSE" else ""), "Low 25% · central 50% · high 25%",
                 signed_money(r.delta_gross_profit), signed(r.delta_sim_expired_units),
                 signed(r.delta_sim_unmet_units_illustrative), f"{int(r.lines_gross_profit_fell):,}",
                 T.chip(res.replace("_", " "), lvl[res]) + " " + T.chip("unmet " + unmet.replace("_", " ").lower(), lvl[unmet])))
T.md(T.table(["True response (simulated)", "Assumed when choosing", "Gross profit", "Expired units", "Unmet units*",
              "Lines where profit fell", "Preregistered test"], rows, html_cols=("Preregistered test",)))
grid = comp.pivot(index="true_response", columns="scenario_id", values="delta_gross_profit").reindex(list(D.TRUE_RESPONSES))
with st.expander("Gross-profit change for every market scenario × true response"):
    st.dataframe(grid.rename(index=SHORT).style.format("£{:+,.0f}"), width="stretch")
    st.dataframe(comp, hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------ original rule vs A1
rc = ui.load_dp_rule_comparison()
pref = ui.load_dp_evaluation("A1")["preference"]
a1_run = ui.load_dp_manifest("A1")["run_id"]
T.md(T.section("Original Phase 2 rule versus A1 cooldown rule",
               f"{scenario}, every true response. Original figures come from run {D.DYNAMIC_PRICING_RUN_ID} (re-run and "
               f"reproduced exactly inside run {a1_run}); A1 figures come from run {a1_run}."))
crow = []
for t in D.TRUE_RESPONSES:
    o = rc.query("scenario_id == @scenario and true_response == @t and rule == 'ORIGINAL'").iloc[0]
    a = rc.query("scenario_id == @scenario and true_response == @t and rule == 'A1'").iloc[0]
    crow.append((SHORT[t], f"{signed_money(o.delta_gross_profit)} → {signed_money(a.delta_gross_profit)}",
                 f"{signed(o.delta_sim_expired_units)} → {signed(a.delta_sim_expired_units)}",
                 f"{signed(o.delta_sim_unmet_units_illustrative)} → {signed(a.delta_sim_unmet_units_illustrative)}",
                 f"{int(o.markdown_events)} → {int(a.markdown_events)}", f"{int(a.markdowns_blocked_by_cooldown)}",
                 f"{int(o.lines_gross_profit_rose)}/{int(o.lines_gross_profit_fell)} → "
                 f"{int(a.lines_gross_profit_rose)}/{int(a.lines_gross_profit_fell)}",
                 f"{int(o.mandatory_reviews)} → {int(a.mandatory_reviews)}"))
T.md(T.table(["True response", "Gross profit (orig → A1)", "Expired units", "Unmet units*", "Markdowns",
              "Decisions blocked by A1 cooldown", "Lines profit up/down", "Mandatory reviews"], crow))
st.caption("Decisions blocked by the A1 cooldown include weeks that would not have produced a markdown anyway (for "
           "example, evidence was insufficient), so they exceed the change in markdowns. A1 trades a little upside for a "
           "little downside protection: fewer markdowns lose less when customers barely respond and gain less when they "
           "respond strongly. Differences appear only where repeat markdowns in consecutive weeks occurred.")
parts = {"PA_all_checks_and_gates": "All checks and safety gates pass",
         "PB_original_thresholds_met": "Meets the original Phase 2 thresholds",
         "PC_no_larger_loss_weak_response": "Loses no more than the original with no or low response",
         "PD_keeps_75pct_of_central_benefit": "Keeps at least 75% of the original's central-response benefit",
         "PE_no_more_unmet_units": "No more unmet units than the original"}
T.md(T.table(["Preregistered A1 preference test (SC1–SC3)", "Result"],
             [(lab, T.chip("PASS" if pref[k] else "FAIL", "ok" if pref[k] else "high")) for k, lab in parts.items()],
             html_cols=("Result",)))
prefers = pref["result"] == "A1_PREFERRED_RESEARCH_COOLDOWN"
T.md(T.banner(f"<b>{'A1 meets the preregistered preference rule' if prefers else 'The original rule is retained as preferred'}.</b> "
              f"Central response, SC1–SC3: A1 gross-profit gain {ui.money(pref['central_gross_profit_gain']['a1'], 0)} vs "
              f"original {ui.money(pref['central_gross_profit_gain']['original'], 0)}; expired units avoided "
              f"{pref['central_expired_units_avoided']['a1']:,.0f} vs {pref['central_expired_units_avoided']['original']:,.0f}. "
              f"{T._e(pref['statement'])}", "ok" if prefers else "caution", "⚖️"))

# -------------------------------------------------------------------------------------------- evaluation results
out = ev["outcome"]
T.md(T.section("Evaluation results", f"Frozen and registered before any pricing outcome was simulated "
                                     f"({ev['evaluation_policy_id']})."))
ok = out["result"] == "MEETS_PREREGISTERED_RESEARCH_CRITERIA"
T.md(T.banner(f"<b>{'Meets' if ok else 'Does not meet'} the preregistered research criteria.</b> "
              f"{T._e(out['statement'])}", "ok" if ok else "caution", "🧾"))
pre = ev["prerequisites"][scenario]
gates = {k: v for k, v in ev["hard_gates"][f"{scenario}/{truth}"].items() if k.startswith("G")}
T.md(T.grid([
    T.kpi("🟰", "Pricing off reproduces the protected replay", "PASS" if all(pre["E1_pricing_off_equals_protected_P2"].values())
          else "FAIL", "orders, deliveries, stock, unmet and expiry identical", T.EMERALD, "Prerequisite E1"),
    T.kpi("🔁", "Orders fixed when pricing is on", "PASS" if all(pre["E2_fixed_orders_no_markdown_equal_pricing_off"].values())
          else "FAIL", "pricing never changes an order", T.EMERALD, "Prerequisite E2"),
    T.kpi("🔎", "Eligibility matches Markdown review", "PASS" if pre["E3_in_loop_eligibility_equals_saved_markdown_review"]["passed"]
          else "FAIL", "every decision, decision-time data only", T.EMERALD, "Prerequisite E3"),
    T.kpi("🛡️", "Hard safety gates (this run)", f"{sum(gates.values())} of {len(gates)}", "conservation, bounds, guards, "
          "chronology, labels", T.EMERALD if all(gates.values()) else T.RED, "Hard gates"),
]))
gate_names = {"G1_conservation": "Units balance every day", "G2_ordering_unchanged": "Ordering unchanged",
              "G3_markdown_only_and_price_bounds": "Markdown only, within floor and maximum",
              "G4_eligibility_and_timing_guards": "Eligible, 7-day cooldown, ≤2 in 28 days, no overlap",
              "G5_chronology": "No look-ahead; markdown days inside windows",
              "G6_labels_unapproved_not_executed": "Unapproved and not executed",
              "G7_no_response_demand_equals_baseline": "No-response demand equals baseline",
              "G8_a1_cooldown_from_window_end": "A1: 7 complete days after the previous markdown ends"}
T.md(T.table(["Gate", "Result"], [(gate_names.get(k, k), T.chip("PASS" if v else "FAIL", "ok" if v else "high"))
                                  for k, v in gates.items()], html_cols=("Result",)))
T.md(T.banner("<b>Evidence quality: LOW.</b> Customer response is assumed, not measured; prices are an estimated proxy and "
              "costs an assumed margin; stock, expiry and demand are simulated or forecast. The loss limits for low and no response "
              "are measured against the whole scenario's expired-stock cost, which is large, so they are lenient tests. "
              + ("Under the original rule the 7-day cooldown cannot bind on its own with weekly decisions — the 28-day "
                 "limit and the no-overlap rule do the limiting. " if rule == "ORIGINAL" else
                 "Under A1 a new markdown may start only after 7 complete days without one, so a markdown in the week "
                 "straight after another is blocked. ")
              + "Effects between products, competitor prices and store operations are not modelled.", "caution", "⚠️"))

# -------------------------------------------------------------------------------------- line timelines and history
dec = ui.load_dp_decisions(scenario, truth, rule)
sel = dec[dec.outcome == DP.SELECTED]
T.md(T.section("Store and product timelines", "Lines with at least one simulated markdown in this scenario and response."))
if len(sel) == 0:
    T.md(T.banner("No markdown was selected in this scenario and response, so prices never changed.", "neutral", "ℹ️"))
else:
    lines = sel.groupby(["Store_ID", "Product_ID", "Product_Name"]).size().reset_index(name="n")
    f1, f2 = st.columns([1, 2])
    store = f1.selectbox("Store", sorted(lines.Store_ID.unique()), key=f"dp_store_{scenario}_{truth}_{rule}")
    pool = lines[lines.Store_ID == store].sort_values("n", ascending=False)
    prod = f2.selectbox("Product", pool.Product_ID.tolist(), key=f"dp_prod_{scenario}_{truth}_{rule}",
                        format_func=lambda p: f"{pool.set_index('Product_ID').loc[p, 'Product_Name']} · "
                                              f"{pool.set_index('Product_ID').loc[p, 'n']} markdown(s)")
    k = (store, prod)
    pr = ui.load_dp_daily(scenario, truth, rule)
    bs = ui.load_dp_daily(scenario, None, rule)
    pr = pr[(pr.Store_ID == store) & (pr.Product_ID == prod)].assign(run="With simulated pricing")
    bs = bs[(bs.Store_ID == store) & (bs.Product_ID == prod)].assign(run="Unchanged prices")
    both = pd.concat([bs, pr])
    runs = ["Unchanged prices", "With simulated pricing"]
    colour = alt.Scale(domain=runs, range=["#94A3B8", T.TEAL])
    legend = alt.Legend(orient="bottom", labelFontSize=12)

    def line(y, title, fmt, step=False):
        base = alt.Chart(both).encode(
            x=alt.X("day:Q", title="Simulated day"), y=alt.Y(f"{y}:Q", title=None, scale=alt.Scale(zero=not step)),
            color=alt.Color("run:N", title=None, scale=colour, legend=legend),
            tooltip=[alt.Tooltip("run:N", title="Run"), alt.Tooltip("week:Q", title="Week"), alt.Tooltip("day:Q", title="Day"),
                     alt.Tooltip(f"{y}:Q", title=title, format=fmt)])
        mark = base.mark_line(strokeWidth=2.2, interpolate="step-after") if step else base.mark_line(strokeWidth=2.2)
        return T.chart(mark.properties(title=alt.TitleParams(title, fontSize=15, anchor="start", color=T.NAVY, font=T.FONT)), 240)

    st.altair_chart(line("price", "Price in force (£)", ".2f", step=True), width="stretch")
    g1, g2 = st.columns(2, gap="large")
    g1.altair_chart(line("sim_closing_units", "Stock at end of day (units)", ",.0f"), width="stretch")
    wk = both.groupby(["run", "week"], as_index=False)["sim_expired_units"].sum()
    bars = alt.Chart(wk).encode(
        x=alt.X("week:O", title="Simulated week", axis=alt.Axis(labelAngle=0)), xOffset=alt.XOffset("run:N", sort=runs),
        y=alt.Y("sim_expired_units:Q", title=None), color=alt.Color("run:N", title=None, scale=colour, legend=legend),
        tooltip=[alt.Tooltip("run:N", title="Run"), alt.Tooltip("week:O", title="Week"),
                 alt.Tooltip("sim_expired_units:Q", title="Units expired", format=",.0f")])
    g2.altair_chart(T.chart(bars.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).properties(
        title=alt.TitleParams("Units going out of date per week", fontSize=15, anchor="start", color=T.NAVY, font=T.FONT)),
        240), width="stretch")
    dlt = pr[["revenue", "sim_expired_units", "sim_unmet_units_illustrative"]].sum() - \
        bs[["revenue", "sim_expired_units", "sim_unmet_units_illustrative"]].sum()
    st.caption(f"This line vs unchanged prices: gross profit {signed_money(dlt['revenue'], 2)} · expired units "
               f"{signed(dlt['sim_expired_units'])} · unmet units {signed(dlt['sim_unmet_units_illustrative'])} "
               "(simulated; receipts and costs are identical in both runs).")

    T.md(T.section("Decision history", "Every weekly pricing decision for this line — read-only."))
    hist = dec[(dec.Store_ID == store) & (dec.Product_ID == prod)].sort_values("origin_week")
    lab = lambda o: DP.OUTCOME_LABELS.get(o, o)  # noqa: E731
    shown = hist[hist.outcome != "NOT_ELIGIBLE"]
    T.md(T.table(["Order week", "Outcome", "Markdown", "Window", "Review"], [
        (int(h.target_week), T.chip(lab(h.outcome), "info" if h.outcome == DP.SELECTED else "neutral"),
         f"{int(h.markdown_pct)}%" if h.markdown_pct else "—",
         f"{W.day_label(h.window_start_day)} → {W.day_label(h.window_end_day)}" if h.outcome == DP.SELECTED else "—",
         str(h.review_tags).replace("|", " · ") if isinstance(h.review_tags, str) else "—") for h in shown.itertuples()],
        html_cols=("Outcome",)))
    st.caption(f"{len(hist) - len(shown)} other weekly decisions for this line were not eligible for markdown review, so the "
               "price stayed at the reference. Every record is SIMULATED · HYPOTHETICAL_UNAPPROVED · NOT_EXECUTED.")
    with st.expander(f"All {len(hist)} weekly pricing decisions for this line"):
        st.dataframe(hist[["target_week", "eligibility", "waste_risk_category", "outcome", "guard_codes", "markdown_pct",
                           "status", "approval_status", "execution_status"]], hide_index=True, width="stretch")
    choices = hist[hist.outcome == DP.SELECTED]
    pick = st.selectbox("Explain a hypothetical markdown", choices.index.tolist(), key=f"dp_pick_{scenario}_{truth}_{k}_{rule}",
                        format_func=lambda i: f"Order week {int(choices.loc[i, 'target_week'])} · "
                                              f"{int(choices.loc[i, 'markdown_pct'])}% markdown")
    h = choices.loc[pick]
    T.md(f'<div class="ds-detail"><div class="ds-sub">{T._e(h.Product_Name)} · store {store} · decision day '
         f'{T._e(W.day_label(h.decision_day))} · scenario {scenario}</div>'
         f'<div class="h">{int(h.markdown_pct)}% markdown — {T._e(W.day_label(h.window_start_day))} to '
         f'{T._e(W.day_label(h.window_end_day))}</div>'
         f'<div style="margin:.4rem 0">{T.chip("SIMULATED_AS_IF_APPROVED", "info")} '
         f'{T.chip("HYPOTHETICAL_UNAPPROVED · NOT_EXECUTED", "neutral")} '
         + " ".join(T.chip(t, "caution") for t in str(h.review_tags).split("|")) + '</div>'
         f'<div class="ds-panel"><div class="l">Why it was chosen (assumed response, at the decision)</div>'
         f'<div class="p">{T._e(h.explanation)}</div></div>'
         f'<div class="ds-sub" style="margin-top:.5rem">Reference price {ui.money(h.reference_price, 2)} → simulated price '
         f'{ui.money(h.markdown_price, 2)} · {ui.fmt(h.at_risk_units)} units at risk · expected change at the decision '
         f'{signed_money(h.expected_delta_belief, 2)}. What actually happened depends on the true response selected above.'
         '</div></div>')

with st.expander("Technical details — method, parameters and provenance"):
    st.markdown(
        "- **Sequence each week:** the P2 order is decided first (pricing off) and copied unchanged into every priced run → "
        "waste risk and markdown eligibility from the decision-time state → timing guards → the Phase 1 engine picks a "
        "step under the assumed belief → the week is simulated with the protected selling step.\n"
        "- **Demand on markdown days:** floor(recorded daily units × (1 + true response × points ÷ 100) + 0.5).\n"
        "- **Gross profit:** revenue at the price in force − assumed cost of units received − disposal (0%); receipts are "
        "identical in paired runs, so differences come from revenue.\n"
        "- **Events are counted when selected** (decision day); every selection is applied, so selected = applied.\n"
        f"- Assumption sets: replay {man['replay_assumption_set']['assumption_set_id']}, pricing "
        f"{man['pricing_assumption_set']['assumption_set_id']} (DRAFT). Protected baseline run "
        f"{man['protected_baseline_run']}; simulator {man['simulator_version']}.")
    st.json({"outcome": out, "thresholds": th, "prerequisites": pre, "code_sha256": man["code_sha256"]}, expanded=False)
    st.dataframe(sel[["Store_ID", "Product_Name", "target_week", "markdown_pct", "window_start_day", "window_end_day",
                      "review_tags", "phase1_status", "status", "approval_status", "execution_status"]],
                 hide_index=True, width="stretch", height=280)
st.caption("Each decision reuses the Phase 1 discount engine unchanged. Order quantities remain HYPOTHETICAL_UNAPPROVED "
           "and NOT_EXECUTED.")
