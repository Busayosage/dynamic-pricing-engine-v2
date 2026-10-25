import altair as alt
import pandas as pd
import streamlit as st

import dashboard_data as D
import labels as L
import theme as T
import ui
from dpe.decision import markdown_eligibility as M

ui.page("Waste risk", "🗑️")
scenario = ui.scenario_select()
policy = ui.policy_select()
prm = ui.load_waste_params()
wr = ui.load_waste_risk(scenario, policy)
policy_name = D.POLICY_NAMES[policy].split(" — ")[1]
scenario_name = D.SCENARIO_NAMES[scenario].split(" — ")[1]

T.md(T.head("Waste-risk intelligence · advisory", "Which products may go out of date?",
            "Stock already in store that is projected to go out of date before it sells, when to check it, and why — "
            "computed from saved outputs only.",
            chips=(f"Policy {policy}", f"Scenario {scenario}", "Advisory only"), art="clock"))
T.md(T.banner(f"<b>Results shown for inventory policy {policy} — {policy_name}</b>, in {scenario_name.lower()}. Every "
              "figure on this page reflects the stock that policy would hold; other policies give different results. "
              "Change the policy or scenario in the left sidebar.", "info", "🔀"))
T.md(T.disclaimer())
T.md(T.banner("<b>Advisory only.</b> This page suggests what to check; it does not create review cases, discounts, orders "
              "or approvals. No prices, costs or margins are used.", "caution", "🧭"))

# -------------------------------------------------------------------------------------------- severity cards
counts = wr.category.value_counts()
T.md(T.section("Projected expiry risk", f"Store × product × decision weeks (720 series × 20 simulated weeks) under "
                                        f"policy {policy}, scenario {scenario}."))
T.md(T.grid([
    T.kpi("🔴", "High expiry risk", f"{counts.get('HIGH', 0):,}", f"≥ {prm['waste_risk_high_pct_of_p50']}% of a typical week",
          T.RED, "Forecast-based projection"),
    T.kpi("🟠", "Moderate expiry risk", f"{counts.get('MODERATE', 0):,}",
          f"{prm['waste_risk_moderate_pct_of_p50']}–{prm['waste_risk_high_pct_of_p50']}% of a typical week", T.AMBER,
          "Forecast-based projection"),
    T.kpi("🟢", "Low expiry risk", f"{counts.get('LOW', 0):,}", f"below {prm['waste_risk_moderate_pct_of_p50']}%",
          T.EMERALD, "Forecast-based projection"),
    T.kpi("⚪", "Insufficient information", f"{counts.get('INSUFFICIENT_INFORMATION', 0):,}",
          "no forecast range, zero demand or unsupported supplier", "#64748B", "Forecast-based projection"),
]))

# ----------------------------------------------------------------------------------- three separate measures
comp = ui.load_waste_comparison(scenario, policy)
wk = ui.load_weekly(scenario, policy)
T.md(T.section("Three different measures — not interchangeable",
               "Each answers a different question and comes from a different source."))
T.md(T.grid([
    T.kpi("📒", "Historical recorded wastage", f"{comp.recorded_wastage_pct_of_sold_full_year.min():.1f}–"
          f"{comp.recorded_wastage_pct_of_sold_full_year.max():.1f}% of sold",
          "Range across categories in the 2024 dataset — what the records say was wasted", T.NAVY_3,
          "RECORDED history · synthetic dataset"),
    T.kpi("🧪", "Simulated expiry outcome", f"{ui.fmt(wk.sim_expired_units.sum())} units",
          f"Went out of date in the replay under {policy} ({scenario}) over 20 weeks", T.AMBER,
          "SIMULATED replay outcome"),
    T.kpi("🔭", "Projected expiry exposure", f"{ui.fmt(wr.projected_existing_expiry_units.fillna(0).sum())} units",
          "Stock already in store projected to expire before it sells, summed over decisions", T.RED,
          "SIMULATED × FORECAST projection"),
    T.kpi("🧺", "Planned buffer (context only)", f"{ui.fmt(wr.planned_buffer_units.sum())} units",
          "Extra units the policy buys above typical demand; never raises the category", "#64748B", "context only"),
]))

with st.expander("How the categories work"):
    st.markdown(
        f"The category looks only at **stock already in store** that is projected to go out of date before it sells, "
        f"compared with a typical week's sales (the p50 forecast): 🔴 **High** at least "
        f"**{prm['waste_risk_high_pct_of_p50']}%**, 🟠 **Moderate** at least **{prm['waste_risk_moderate_pct_of_p50']}%**, "
        f"🟢 **Low** below that, ⚪ **Insufficient information** when there is no forecast range, an unsupported supplier "
        "arrangement, or a zero-demand forecast with nothing projected to expire.\n\n"
        f"Thresholds are illustrative assumptions from **{prm['assumption_set_id']} ({prm['assumption_status']})**, not "
        "calibrated against real waste. Batch-level remaining units are not saved, so projections are planning estimates.")

# ------------------------------------------------------------------------------------------------ breakdowns
risky = wr[wr.category.isin(["HIGH", "MODERATE"])]
T.md(T.section("Where the risk sits", "High and moderate rows by category and by store."))
b1, b2 = st.columns(2, gap="large")
with b1:
    by_cat = risky.groupby("product_category").agg(rows=("category", "size"),
                                                   units=("projected_existing_expiry_units", "sum")).reset_index()
    if len(by_cat):
        rows = [(f"{T.CATEGORY_ICON.get(r.product_category, '🛒')} {r.product_category}", f"{r.rows:,}", ui.fmt(r.units))
                for r in by_cat.sort_values("rows", ascending=False).itertuples()]
        T.md(T.table(["Category", "High + moderate rows", "Projected expiry (units)"], rows))
    else:
        T.md(T.banner("No high or moderate rows under this policy and scenario.", "ok", "✅"))
with b2:
    by_store = risky.groupby(["Store_ID", "Region"]).agg(rows=("category", "size"),
                                                         units=("projected_existing_expiry_units", "sum")).reset_index()
    if len(by_store):
        rows = [(f"Store {r.Store_ID} · {r.Region}", f"{r.rows:,}", ui.fmt(r.units))
                for r in by_store.sort_values("rows", ascending=False).head(8).itertuples()]
        T.md(T.table(["Store (top 8)", "High + moderate rows", "Projected expiry (units)"], rows))

# ---------------------------------------------------------------------------------------------- investigate
T.md(T.section("Products requiring investigation", "Filter, then choose a row to see the suggested investigation."))
md = ui.load_markdown(scenario, policy)[["Store_ID", "Product_ID", "origin_week", "eligibility"]]
wr = wr.merge(md, on=["Store_ID", "Product_ID", "origin_week"], how="left")
names = ui.load_series()
f1, f2, f3 = st.columns([1.4, 1, 1.4])
cats = f1.multiselect("Category", list(L.WASTE_CATEGORIES), default=["HIGH", "MODERATE"],
                      format_func=lambda x: f"{ui.WASTE_ICON[x]} {L.WASTE_CATEGORIES[x]}", key=f"wr_cat_{scenario}_{policy}")
store = f2.selectbox("Store", ["All stores"] + sorted(wr.Store_ID.unique()), key=f"wr_store_{scenario}_{policy}")
prod_opts = names if store == "All stores" else names[names.Store_ID == store]
product = f3.selectbox("Product", ["All products"] + sorted(prod_opts.Product_Name.unique()), key=f"wr_prod_{scenario}_{policy}")
view = wr[wr.category.isin(cats)]
if store != "All stores":
    view = view[view.Store_ID == store]
if product != "All products":
    view = view[view.Product_Name == product]
rank = {"HIGH": 0, "MODERATE": 1, "INSUFFICIENT_INFORMATION": 2, "LOW": 3}
view = view.sort_values(["category", "projected_expiry_pct_of_p50"], ascending=[True, False],
                        key=lambda s: s.map(rank) if s.name == "category" else s)
level = {"HIGH": "high", "MODERATE": "caution", "LOW": "ok", "INSUFFICIENT_INFORMATION": "neutral"}

if len(view) == 0:
    T.md(T.banner("No rows match these filters.", "neutral", "🔍"))
else:
    rows = [(T.chip(L.WASTE_CATEGORIES[r.category], level[r.category]), r.Store_ID, r.Product_Name, r.target_week,
             ui.fmt(r.projected_existing_expiry_units),
             "—" if pd.isna(r.projected_expiry_pct_of_p50) else f"{r.projected_expiry_pct_of_p50:.1f}%",
             r.investigate_by_label or "—", r.main_reasons or "—") for r in view.head(25).itertuples()]
    T.md(T.table(["Risk", "Store", "Product", "Order week", "Projected expiry", "% of a typical week", "Investigate by",
                  "Main reasons"], rows, html_cols=("Risk",)))
    st.caption(f"Showing the first {min(25, len(view)):,} of {len(view):,} rows for policy {policy}, scenario {scenario}.")
    with st.expander(f"All {len(view):,} matching rows"):
        st.dataframe(pd.DataFrame({
            "Policy": view.policy_id, "Scenario": view.scenario_id,
            "Risk": view.category.map(lambda x: f"{ui.WASTE_ICON[x]} {L.WASTE_CATEGORIES[x]}"),
            "Store": view.Store_ID, "Product": view.Product_Name, "Order week": view.target_week,
            "Projected expiry (units)": view.projected_existing_expiry_units,
            "% of a typical week": view.projected_expiry_pct_of_p50,
            "Investigate by": view.investigate_by_label.fillna("—"), "Main reasons": view.main_reasons,
            "Review case": view.review_case_ref.fillna("— advisory only —"),
            "Markdown review": view.eligibility.map(lambda c: f"{ui.MARKDOWN_ICON[c]} {M.CLASS_LABELS[c]}"
                                                    if isinstance(c, str) else "—")}),
            hide_index=True, width="stretch", height=360,
            column_config={"% of a typical week": st.column_config.NumberColumn(format="%.1f%%"),
                           "Projected expiry (units)": st.column_config.NumberColumn(format="%.0f")})

    pick = st.selectbox("Choose a row", view.index.tolist()[:1000], key=f"wr_pick_{scenario}_{policy}",
                        format_func=lambda i: (f"{ui.WASTE_ICON[view.loc[i, 'category']]} {view.loc[i, 'Product_Name']} "
                                               f"· store {view.loc[i, 'Store_ID']} · week {view.loc[i, 'target_week']}"))
    r = view.loc[pick]
    share = f"{r.projected_expiry_pct_of_p50:.1f}% of a typical week" if pd.notna(r.projected_expiry_pct_of_p50) else "share undefined"
    rec = "—" if pd.isna(r.recorded_wastage_pct_4w) else f"{r.recorded_wastage_pct_4w:.1f}% of sales"
    review = (T.chip("Pending review (existing case)", "caution") + f' <span class="ds-sub">{T._e(r.review_case_ref)}</span>'
              if isinstance(r.review_case_type, str) else T.chip("Advisory — no review case", "neutral"))
    reasons = "".join(T.chip(x, "info") + " " for x in str(r.main_reasons).split("; ") if x and x != "nan")
    typical = ui.fmt(r.typical_weekly_demand_p50) if pd.notna(r.typical_weekly_demand_p50) else "not available"
    T.md(f'<div class="ds-detail"><div class="ds-sub">Store {r.Store_ID} · {T._e(r.Region)} · order week {r.target_week} · '
         f'decided {T._e(r.decision_label)} · policy {policy}, scenario {scenario}</div>'
         f'<div class="h">{T._e(r.Product_Name)}</div>'
         f'<div style="margin:.5rem 0">{T.chip(L.WASTE_CATEGORIES[r.category], level[r.category])} {review}</div>'
         + T.grid([
             T.kpi("🔭", "Stock in store projected to expire", f"{ui.fmt(r.projected_existing_expiry_units)} units", share,
                   T.RED, "SIMULATED × FORECAST · projection"),
             T.kpi("📅", "Investigate by", r.investigate_by_label or "—",
                   f"Oldest in-date batch sellable until {r.earliest_batch_last_day_label}" if r.earliest_batch_last_day_label
                   else "No dated batch evidence", T.AMBER, "SIMULATED delivery dates"),
             T.kpi("📒", "Recorded wastage, last 4 weeks", rec, "Historical record for this line", T.NAVY_3,
                   "RECORDED history"),
             T.kpi("🧺", "Planned buffer (context only)", f"{ui.fmt(r.planned_buffer_units)} units",
                   "Never raises the category", "#64748B", "SIMULATED order × ASSUMED target"),
         ])
         + f'<div class="ds-sub" style="font-weight:700;margin-top:.4rem">Main reasons</div><div>{reasons or "—"}</div>'
         f'<div class="ds-panel"><div class="l">Suggested investigation</div><div class="p">{T._e(r.suggested_investigation)}'
         f'</div></div>'
         f'<div class="ds-sub" style="margin-top:.7rem">What happened in the replay (simulated outcome, not a prediction): '
         f'{ui.fmt(r.replay_expired_units_in_week)} units went out of date in week {r.target_week}. Typical demand '
         f'{typical} units a week (forecast p50). Units left per batch are not saved, so this is a planning estimate.</div>'
         '</div>')
    with st.expander("Technical details — codes and provenance"):
        st.write({"category": r.category, "reason_codes": r.all_reason_codes.split("|") if r.all_reason_codes else [],
                  "status": r.status, "creates_review_case": bool(r.creates_review_case), "approval_event_id": None,
                  "low_sales_buffer_units": r.low_sales_buffer_units,
                  "recent_simulated_expiry_pct_4w": r.recent_simulated_expiry_pct_4w,
                  "remaining_life_days": int(r.remaining_life_days)})
ui.link_to("pages/5_Markdown_review.py", label="Open Markdown review — which of these lines are worth a markdown review",
           icon="🏷️")

# ------------------------------------------------------------------------------------------- category view
T.md(T.section("Historical wastage and simulated expiry by category"))
T.md(T.banner("<b>These are different measures and are not directly comparable.</b> Recorded wastage is a historical "
              "record from the dataset (share of units sold). Simulated expiry is an outcome of the replay under assumed "
              "stock and supply (share of units delivered). They are shown side by side for context only.",
              "caution", "⚖️"))
st.dataframe(comp.rename(columns={"category": "Category",
                                  "recorded_wastage_pct_of_sold_full_year": "RECORDED wastage, % of units sold (2024)",
                                  "recorded_wastage_pct_of_sold_same_weeks": "RECORDED wastage, % of units sold (same weeks)",
                                  "simulated_expired_pct_of_received": f"SIMULATED expiry, % of units delivered ({policy}, {scenario})"}),
             hide_index=True, width="stretch")
g1, g2 = st.columns(2, gap="large")


def bar(col, title, color):
    return T.chart(alt.Chart(comp).mark_bar(size=40, color=color, cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
                   .encode(x=alt.X("category:N", title=None, axis=alt.Axis(labelAngle=0)),
                           y=alt.Y(f"{col}:Q", title="%"),
                           tooltip=[alt.Tooltip("category:N"), alt.Tooltip(f"{col}:Q", format=".1f")])
                   .properties(title=alt.TitleParams(title, fontSize=15, anchor="start", color=T.NAVY)), 240)


g1.altair_chart(bar("recorded_wastage_pct_of_sold_full_year", "RECORDED wastage — % of units sold (history)", T.NAVY_3),
                width="stretch")
g2.altair_chart(bar("simulated_expired_pct_of_received", "SIMULATED expiry — % of units delivered (replay)", T.TEAL),
                width="stretch")

with st.expander("Data sources and evidence labels"):
    from dpe.decision import waste_risk as W

    st.dataframe(pd.DataFrame({"Figure": list(W.PROVENANCE), "Evidence": list(W.PROVENANCE.values())}),
                 hide_index=True, width="stretch")
    st.markdown(f"- Saved outputs: protected comparison run `{D.COMPARISON_DIR.name}`; forecast contract; verified raw panel.\n"
                f"- {D.DAILY_GAP}")
