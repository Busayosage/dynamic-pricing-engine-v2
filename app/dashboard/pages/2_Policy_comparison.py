import pandas as pd
import streamlit as st

import dashboard_data as D
import theme as T
import ui

ui.page("Policy comparison", "⚖️")
scenario = ui.scenario_select()
ev = ui.load_evaluation()
t_all = ui.load_comparison().set_index(["scenario_id", "policy_id"])
scenario_name = D.SCENARIO_NAMES[scenario].split(" — ")[1]

T.md(T.head("Stage 5B-3e · protected research comparison", "Which ordering policy works best?",
            "Three ordering policies replayed on the same 720 store-product series over 20 weeks, judged against "
            "acceptance tests that were fixed before the run.",
            chips=(f"Run {D.COMPARISON_DIR.name}", "Evaluation policy EP-5B3E-2026-10-23-v1", "Assumptions v2 (DRAFT)"),
            art="chart"))
T.md(T.disclaimer())
T.md(T.banner(f"<b>Research evaluation result:</b> P2 passed every preregistered test against P1 and is the research "
              f"replay default ({ev['outcome']['research_replay_default']}). It is <b>not approved for production</b>, and "
              "the comparison is <b>exploratory</b> because some results were seen before the final run.", "ok", "✅"))


def pct(sc, col, a="P2", b="P1"):
    return 100 * (t_all.loc[(sc, a), col] / t_all.loc[(sc, b), col] - 1)


# ------------------------------------------------------------------------------------------- policy cards
T.md(T.section(f"{scenario} — {scenario_name}", ui.SCENARIO_EXPLAINED[scenario] + " " + D.SIMULATED_LABEL + "."))
names = {"P0": "Simple baseline", "P1": "Original forecast rule", "P2": "Expiry-aware plan"}
cards = []
for p in D.POLICIES:
    r = t_all.loc[(scenario, p)]
    rows = [("Units ordered", ui.fmt(r.ordered_units)), ("Customers could not buy*", ui.fmt(r.unmet_units_illustrative)),
            ("Units gone out of date", ui.fmt(r.expired_units)), ("Weekly review cases", ui.fmt(r.weekly_cases))]
    cards.append(T.policy_card(p, names[p], rows, T.POLICY_ACCENT[p],
                               badge="Research default" if p == "P2" else "", tag="Simulated"))
T.md(T.grid(cards))
st.caption("*Illustrative unmet demand in a simulated replay — not observed lost sales. P2 also has 360 one-off "
           "supplier-confirmation items (one per fresh product line), kept separate from weekly review.")

c1, c2 = st.columns(2, gap="large")
t = t_all.loc[scenario].reset_index()
c1.altair_chart(T.policy_bars(t, "ordered_units", "Units ordered"), width="stretch")
c2.altair_chart(T.policy_bars(t, "unmet_units_illustrative", "Customers could not buy (illustrative)"), width="stretch")
c3, c4 = st.columns(2, gap="large")
c3.altair_chart(T.policy_bars(t, "expired_units", "Units gone out of date"), width="stretch")
c4.altair_chart(T.policy_bars(t, "weekly_cases", "Weekly review cases"), width="stretch")

# ------------------------------------------------------------------------------------------------- trade-offs
T.md(T.section("The trade-off in plain English", "P2 compared with P1 in this scenario (green = fewer, coral = more)."))
T.md(T.grid([
    T.use_case("🛒", "Shortages", f"Customers unable to buy: {pct(scenario, 'unmet_units_illustrative'):+.2f}%. P2 stops "
               "counting stock that will go out of date mid-week, so it covers more of the week."),
    T.use_case("🗑️", "Expiry", f"Units gone out of date: {pct(scenario, 'expired_units'):+.2f}%. The extra cover can "
               "itself expire, so P2 can reduce simulated unmet demand while increasing simulated expiry."),
    T.use_case("📦", "Ordering", f"Units ordered: {pct(scenario, 'ordered_units'):+.2f}%. P2 orders slightly more in "
               "some scenarios; under supply pressure the two behave almost the same."),
    T.use_case("🧑‍💼", "Review workload", f"Weekly review cases: {pct(scenario, 'weekly_cases'):+.2f}%. This mostly "
               "reflects different review rules, not only better decisions."),
]))
st.caption("P0 is a deliberately simple baseline: it ignores the sales that use up current stock before the next delivery, "
           "so it runs short far more often. All figures come from a simulated replay; they are not measured savings.")

pct_t = ui.load_pct()
fmt = {c: "{:+.2f}%" for c in pct_t.columns[2:]}
with st.expander("Percentage differences against P1 — this scenario and all scenarios"):
    st.dataframe(pct_t[pct_t.Scenario == scenario].style.format(fmt), hide_index=True, width="stretch")
    st.dataframe(pct_t.style.format(fmt), hide_index=True, width="stretch")
    raw = t_all.reset_index()[["scenario_id", "policy_id", "ordered_units", "unmet_units_illustrative", "expired_units",
                               "weekly_cases", "standing_supplier_confirmation_cases"]]
    st.dataframe(raw, hide_index=True, width="stretch")

# -------------------------------------------------------------------------------------------- research gates
T.md(T.section("Research evaluation — acceptance tests decided before the run",
               "These are research gates for the replay, not approval for live use."))
labels = {"T_U": "Customers unable to buy", "T_E": "Stock gone out of date", "T_O": "Units ordered",
          "T_R": "Review workload", "T_S": "Shortfall left after the order"}
rows = []
for sc, th in ev["thresholds"].items():
    for k, label in labels.items():
        x = th[k]
        actual = (f"P2 ÷ P1 = {x['ratio']:.3f} (must be ≤ {x['limit']})" if "ratio" in x
                  else f"P2 {x['P2']} vs P1 {x['P1_v11_flag']} (P2 must be 0)")
        rows.append((sc, label, actual, T.chip("PASS", "ok") if x["passed"] else T.chip("FAIL", "high")))
T.md(T.table(["Scenario", "Test", "Result", "Outcome"], rows, html_cols=("Outcome",)))
gates = ev["hard_gates"]
n_pass = sum(g["passed"] for g in gates.values())
regress = all(all(v.values()) for v in ev["p1_regression_vs_protected_v11"].values())
T.md(T.grid([
    T.kpi("🛡️", "Hard safety gates", f"{n_pass} of {len(gates)}", "policy × scenario runs pass every gate", T.EMERALD,
          "Research evaluation"),
    T.kpi("🔁", "P1 reproduces protected results", "Yes" if regress else "No", "exact match with the earlier run",
          T.NAVY_3, "Research evaluation"),
    T.kpi("🧪", "Supplier stress (SF75)", "Reported", "not an adoption test", T.AMBER, "Research evaluation"),
]))
st.caption(f"Safety and integrity checks: {n_pass} of {len(gates)} runs keep stock balanced, respect case sizes and "
           "delivery timing, approve or execute nothing, and route Christmas and missing-forecast weeks to a person.")
with st.expander("Technical details — gate codes per run"):
    st.json({k: {g: {n: v for n, v in vals.items()} for g, vals in x.items() if g in ("G1", "G2", "G3")}
             for k, x in gates.items()}, expanded=False)
