"""Overview page. Run from the project root:  run_dashboard.cmd   (or: streamlit run app/dashboard/Home.py)"""
import streamlit as st

import dashboard_data as D
import theme as T
import ui

ui.page("Overview", "📊")

scenario = ui.scenario_select()
policy = ui.policy_select()

series = ui.load_series()
fm = ui.load_forecast_metrics()
rf1 = fm[(fm.horizon == 1) & (fm.model == "random_forest")].iloc[0]
ma1 = fm[(fm.horizon == 1) & (fm.model == "mean_4w")].iloc[0]
ma4 = fm[(fm.horizon == 4) & (fm.model == "mean_4w")].iloc[0]
tot = ui.load_comparison()
tot = tot[tot.scenario_id == scenario].set_index("policy_id")
scenario_name = D.SCENARIO_NAMES[scenario].split(" — ")[1]
policy_name = D.POLICY_NAMES[policy].split(" — ")[1]

T.md(T.hero(
    "Retail decision support · research build",
    "Dynamic Pricing Engine V2",
    "Forecasts weekly demand for every store and product, plans how much fresh stock to order, and flags lines at risk "
    "of going out of date — so a manager can decide with the evidence in front of them.",
    chips=(f"{series['Store_ID'].nunique()} stores", f"{series['Product_ID'].nunique()} products",
           f"{len(series):,} store × product series", "Human review on every decision")))
T.md(T.disclaimer())

# --------------------------------------------------------------------------------------- what it helps decide
T.md(T.section("What this system helps a retail manager decide",
               "Each answer comes with its evidence and waits for a person — nothing is ordered, priced or approved."))
T.md(T.grid([
    T.use_case("📦", "How much to order", "A hypothetical weekly order for each store and product, sized day by day so "
               "stock that will go out of date is not counted twice."),
    T.use_case("⏳", "What may go to waste", "Which lines hold stock likely to go out of date before it sells, how much, "
               "and by when to check the shelf."),
    T.use_case("🧑‍💼", "What needs a person", "Christmas weeks, missing forecast ranges and supply risks are routed to a "
               "review queue — read-only, with no approval buttons."),
    T.use_case("🏷️", "Which lines deserve a markdown review", "Eligibility only, with blocking reasons. No discount size "
               "is proposed: that needs real costs, prices and sales-response evidence."),
]))

# -------------------------------------------------------------------------------------------- where to go next
T.md(T.section("Where to go next", "A suggested route through the dashboard."))
nav = st.columns(3, gap="medium")
for col, (path, label, icon, text) in zip(nav * 3, (
    ("pages/1_Product_investigation.py", "Product investigation", "🔎",
     "One store and product, week by week: the hypothetical order, shortage and expiry risk, and why."),
    ("pages/2_Policy_comparison.py", "Policy comparison", "⚖️",
     "How the three ordering policies compare on shortages, waste and ordering in each scenario."),
    ("pages/3_Review_queue.py", "Review queue", "🗂️",
     "Decisions waiting for a manager, with plain reasons and what to check."),
    ("pages/4_Waste_risk.py", "Waste risk", "⏳",
     "Lines where stock already in store may go out of date, and when to look."),
    ("pages/5_Markdown_review.py", "Markdown review", "🏷️",
     "Lines worth investigating for a possible markdown — no discount is proposed."),
    ("pages/6_Discount_decision_lab.py", "Discount Decision Lab", "🧪",
     "Markdown options ranked under stated scenarios — simulated research, not validated for live use."),
    ("pages/7_Dynamic_pricing_lab.py", "Dynamic Pricing Lab", "📈",
     "Weekly markdowns simulated over time against unchanged prices — simulated research, not validated."),
    ("pages/8_Waste_intervention_lab.py", "Waste Intervention Lab", "♻️",
     "What could be investigated when stock may expire — evidence, blockers and human checks; advisory only."),
)):
    with col.container(border=True):
        ui.link_to(path, label=label, icon=icon)
        st.caption(text)

# ------------------------------------------------------------------------------------------------ the data
T.md(T.section("The data", "One year of weekly sales (2024) from an apparently synthetic dataset; provenance unconfirmed."))
T.md(T.grid([
    T.kpi("🏬", "Stores", f"{series['Store_ID'].nunique()}", "UK regions in the dataset", T.NAVY_3, "Recorded"),
    T.kpi("🛒", "Products", f"{series['Product_ID'].nunique()}", "Bakery · Beverages · Dairy · Meat", T.TEAL, "Recorded"),
    T.kpi("🔗", "Store × product series", f"{len(series):,}", "Each forecast and planned separately", T.EMERALD, "Recorded"),
    T.kpi("🥖", "Product categories", f"{series['Product_Category'].nunique()}",
          " ".join(T.CATEGORY_ICON.values()), T.AMBER, "Recorded"),
]))

# --------------------------------------------------------------------------------------------- forecasting
T.md(T.section("How accurate are the forecasts?",
               "Measured on six held-out periods. WAPE = average forecast error as a share of actual sales; lower is better."))
T.md(T.grid([
    T.kpi("🎯", "1 week ahead · Random Forest", f"{rf1.WAPE_pct:.2f}% WAPE",
          f"{ma1.WAPE_pct - rf1.WAPE_pct:.2f} points better than a simple 4-week average ({ma1.WAPE_pct:.2f}%)",
          T.TEAL, "Backtest result"),
    T.kpi("📅", "4 weeks ahead · 4-week average", f"{ma4.WAPE_pct:.2f}% WAPE",
          "Kept because the 4-week Random Forest did not pass its acceptance gates", T.NAVY_3, "Backtest result"),
    T.kpi("🧭", "What that means", "≈ ¼ of weekly sales",
          "On average a one-week forecast is off by about a quarter of that week's sales.", T.AMBER,
          "Research only — not approved for live use"),
]))
with st.expander("Technical details — every forecasting model"):
    show = fm.assign(horizon=fm.horizon.map({1: "1 week", 4: "4 weeks"}))[["horizon", "model", "WAPE_pct", "Bias_pct", "MAE", "RMSE"]]
    st.dataframe(show.round(2), hide_index=True, width="stretch")

# ------------------------------------------------------------------------------------------------ policies
T.md(T.section(f"Inventory policies — {scenario_name.lower()}",
               f"{ui.SCENARIO_EXPLAINED[scenario]} Totals over 20 simulated weeks for all 720 series."))
T.md('<div class="ds-note"><span>🧪</span><div><b>SIMULATED results (synthetic replay) — not observed results.</b> '
     '“Could not buy” is illustrative unmet demand, never observed lost sales.</div></div>')
names = {"P0": "Simple baseline", "P1": "Original forecast rule", "P2": "Expiry-aware plan"}
cards = []
for p in D.POLICIES:
    r = tot.loc[p]
    cards.append(T.policy_card(
        p, names[p],
        [("Units ordered", ui.fmt(r.ordered_units)), ("Customers could not buy", ui.fmt(r.unmet_units_illustrative)),
         ("Units gone out of date", ui.fmt(r.expired_units))],
        T.POLICY_ACCENT[p], badge="Research default" if p == "P2" else ("Selected" if p == policy else ""),
        tag="Simulated"))
T.md(T.grid(cards))
T.md(T.grid([
    T.use_case("🧩", f"Selected policy: {policy} — {policy_name}", ui.POLICY_EXPLAINED[policy]),
    T.use_case("🌦️", f"Selected scenario: {scenario} — {scenario_name}", ui.SCENARIO_EXPLAINED[scenario]),
]))
st.caption("Change the policy or scenario in the left sidebar; the choice carries over to the other pages. P2 passed every "
           "preregistered research test and is the research default — it is not approved for production.")
