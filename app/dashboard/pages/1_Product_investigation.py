import altair as alt
import pandas as pd
import streamlit as st

import dashboard_data as D
import labels as L
import theme as T
import ui

ui.page("Product investigation", "🔎")
scenario = ui.scenario_select()
policy = ui.policy_select()
series = ui.load_series()
store = st.sidebar.selectbox("Store", sorted(series.Store_ID.unique()),
                             format_func=lambda s: f"{s} — {series[series.Store_ID == s].Region.iloc[0]}")
prods = series[series.Store_ID == store]
product = st.sidebar.selectbox("Product", prods.Product_ID.tolist(),
                               format_func=lambda p: f"{prods[prods.Product_ID == p].Product_Name.iloc[0]} ({p})")
info = prods[prods.Product_ID == product].iloc[0]


icon = T.CATEGORY_ICON.get(info.Product_Category, "🛒")
T.md(T.hero(f"Product investigation · store {store} · {info.Region}", f"{icon} {info.Product_Name}",
            f"{info.Product_Category} · {D.SCENARIO_NAMES[scenario]} · {D.POLICY_NAMES[policy]}",
            chips=(f"Policy {policy}", f"Scenario {scenario}", "Hypothetical · not ordered"), art=False))
T.md(T.disclaimer())

dec = ui.load_decisions(scenario, policy)
dec = dec[(dec.Store_ID == store) & (dec.Product_ID == product)].sort_values("origin_week").reset_index(drop=True)
wk = ui.load_weekly(scenario, policy)
wk = wk[(wk.Store_ID == store) & (wk.Product_ID == product)].sort_values("week")
dl_all = ui.load_deliveries(scenario, policy)
dl_all = dl_all[(dl_all.Store_ID == store) & (dl_all.Product_ID == product)]

# ------------------------------------------------------------------------------------------- decision summary
st.header("Decision summary")
target = st.select_slider("Choose the week the order is for", options=dec.target_week.tolist(),
                          value=int(dec.target_week.iloc[0]), format_func=lambda w: f"Week {w}")
d = dec[dec.target_week == target].iloc[0]
orders = dl_all[dl_all.order_id == d.order_id] if isinstance(d.order_id, str) else dl_all.iloc[0:0]

if policy == "P2":
    rec = ui.load_recommendations(scenario)
    rec = rec[(rec.store_id == store) & (rec.product_id == product) & (rec.origin_week == d.origin_week)].iloc[0]
    category = L.label(L.CATEGORIES, d.primary_category)
    review_code = d.case_type if isinstance(d.case_type, str) else None
    reason_codes, warning_codes = D.parse_list(rec.reason_codes), D.parse_list(rec.warnings)
    material = [c for c in reason_codes if c not in warning_codes]
    supplier = L.label(L.SUPPLIER_STATUS, d.supplier_arrangement_status)
    why = L.humanize(rec.explanation)
else:
    cases = ui.load_cases(scenario, policy)
    case = cases[(cases.store_id == store) & (cases.product_id == product) & (cases.origin_week == d.origin_week)]
    review_code = case.case_type.iloc[0] if len(case) else None
    material = case.reasons_list.iloc[0] if len(case) else []
    warning_codes = case.warnings_list.iloc[0] if len(case) else []
    reason_codes = D.parse_list(d["flags"])
    category = "Order proposed" if d.ordered_units > 0 else "No order proposed"
    weekend = bool((orders.arrival_dow >= 6).any()) if len(orders) else False
    supplier = (L.SUPPLIER_STATUS["ASSUMED_UNCONFIRMED_REQUIRES_SUPPLIER_CONFIRMATION"]
                if d.delivery_arrangement == "SHORT_LIFE_RECURRING_DROPS" or weekend
                else L.SUPPLIER_STATUS["ASSUMED_STANDARD_WEEKLY_UNCONFIRMED"])
    first = L.day_label(d.arrival_day)
    if policy == "P0":
        why = (f"P0 orders the average of the last four weeks of recorded sales ({ui.fmt(d.baseline_weekly_units)} units a week) "
               f"minus all stock on hand ({ui.fmt(d.expiry_blind_credit_units)} units, counted even if it will go out of date). ")
    else:
        why = (f"P1 plans for {ui.fmt(d.weekly_planning_target_units)} units this week (between the typical and the "
               f"high-demand forecast) and counts {ui.fmt(d.usable_at_arrival_units)} units of stock that is still in date "
               "when the delivery arrives. ")
    why += (f"It proposes {ui.fmt(d.ordered_units)} units in {int(d.n_deliveries)} "
            f"deliver{'y' if d.n_deliveries == 1 else 'ies'}, first arriving {first}. ")
    if material:
        why += "Review is required because: " + "; ".join(r.lower() for r in L.reasons(material)) + ". "
    why += "This is a hypothetical proposal: nothing has been approved or ordered."

# planning-risk indicators (identical rules for every policy, from the saved outputs)
pre_gap, post_gap = d.std_pre_delivery_gap_p50_units, d.std_post_order_shortfall_planning_units
wr = ui.load_waste_risk(scenario, policy)
w = wr[(wr.Store_ID == store) & (wr.Product_ID == product) & (wr.target_week == target)]
w = w.iloc[0] if len(w) else None
mdr = ui.load_markdown(scenario, policy)
mdr = mdr[(mdr.Store_ID == store) & (mdr.Product_ID == product) & (mdr.target_week == target)]
mdr = mdr.iloc[0] if len(mdr) else None
first = L.day_label(d.arrival_day)
deliveries = f"{int(d.n_deliveries)} deliver{'y' if d.n_deliveries == 1 else 'ies'}"

if d.std_post_order_shortfall:
    shortage = T.indicator("Shortage risk", f"Still about {ui.fmt(post_gap)} units short",
                           "Even after this order the week is not fully covered at planned demand.", "high", "📉")
    short_text = f"it would still leave about {ui.fmt(post_gap)} units short"
elif d.std_pre_delivery_shortage:
    shortage = T.indicator("Shortage risk", "May run short before the delivery",
                           f"About {ui.fmt(pre_gap)} units at typical demand before the order arrives ({first}).",
                           "caution", "📉")
    short_text = f"stock may run short by about {ui.fmt(pre_gap)} units before it arrives"
else:
    shortage = T.indicator("Shortage risk", "No shortage expected",
                           "Stock covers typical demand before the delivery, and the order covers its week.", "ok", "📉")
    short_text = "no shortage is expected"

level = {"HIGH": "high", "MODERATE": "caution", "LOW": "ok", "INSUFFICIENT_INFORMATION": "neutral"}
if w is not None:
    share = f" ({w.projected_expiry_pct_of_p50:.1f}% of a typical week)" if pd.notna(w.projected_expiry_pct_of_p50) else ""
    by = f" Check the shelf by {w.investigate_by_label}." if w.investigate_by_label else ""
    expiry = T.indicator("Expiry risk", L.WASTE_CATEGORIES[w.category],
                         f"{ui.fmt(w.projected_existing_expiry_units)} units already in store may go out of date{share}.{by}",
                         level[w.category], "⏳")
    if w.category in ("HIGH", "MODERATE"):
        exp_text = (f"about {ui.fmt(w.projected_existing_expiry_units)} units already in store may go out of date"
                    + (f" (check the shelf by {w.investigate_by_label})" if w.investigate_by_label else ""))
    else:
        exp_text = "little current stock is expected to go out of date"
else:
    expiry = T.indicator("Expiry risk", "Not assessed", "No waste-risk row for this week.", "neutral", "⏳")
    exp_text = "expiry risk was not assessed"

sup_level = "caution" if "confirmation" in supplier.lower() else ("high" if "not supported" in supplier.lower() else "info")
sup_head = {"caution": "Needs confirming", "high": "Not supported", "info": "Standard weekly delivery"}[sup_level]
supplier_ind = T.indicator("Supplier delivery schedule", sup_head,
                           supplier + ". Assumed, not confirmed by the supplier.", sup_level, "🚚")
formal = L.case_type(review_code) if review_code else "Not triggered"  # the saved review flag, unchanged
# Operational follow-ups are derived from the same saved indicators; they are display notes, never review cases.
followups = []
if sup_level == "caution":
    followups.append(("Supplier delivery confirmation needed", "caution"))
if d.std_pre_delivery_shortage or d.std_post_order_shortfall:
    followups.append(("Check stock levels before the delivery arrives", "caution"))
if w is not None and w.category in ("HIGH", "MODERATE"):
    followups.append((f"Check shelf dates{' by ' + w.investigate_by_label if w.investigate_by_label else ''}", "caution"))
follow_text = ("; operational follow-up: " + ", ".join(t.lower() for t, _ in followups)) if followups else ""
takeaway = (f"A hypothetical order of {ui.fmt(d.ordered_units)} units ({deliveries}, first {first}); {short_text}, and "
            f"{exp_text}. Formal policy review: {formal.lower()}{follow_text}. Nothing has been ordered or approved.")
tags = [f"Recommendation: {category}", L.label(L.ACTION_STATUS, d.action_status)]
if mdr is not None:
    tags.append(f"Markdown review: {mdr.eligibility_label}")

T.md(T.decision_card(
    [("Store · product", f"Store {store} · {info.Product_Name}", f"{info.Region} · {info.Product_Category}"),
     ("Order week", f"Week {target}", f"Decided {L.day_label(d.decision_day)}"),
     ("Hypothetical order", f"{ui.fmt(d.ordered_units)} units", f"{deliveries} · first {first}"),
     ("Human review · formal policy review", formal,
      "Pending review — no approval exists" if review_code else "No formal review case for this week")],
    [shortage, expiry, supplier_ind], takeaway, tags, followups))
if not review_code and followups:
    st.caption("“Not triggered” means the policy's review rules raised no formal case this week. The operational "
               "follow-ups above are practical checks shown for information; they do not change the review flag.")

with st.expander("Why this recommendation — full explanation and reasons"):
    st.info(why)
    st.markdown("**Reasons for review:** " + ("; ".join(L.reasons(material)) or "no review triggers"))
    if warning_codes:
        st.caption("Warnings (information only, no review on their own): " + "; ".join(L.reasons(warning_codes)))
    if w is not None:
        st.caption(f"Waste risk (advisory) · policy {policy}, scenario {scenario}: {L.WASTE_CATEGORIES[w.category]}; "
                   f"planned buffer (context only) {ui.fmt(w.planned_buffer_units)} units. SIMULATED stock × FORECAST "
                   "demand, ASSUMED thresholds (v3 DRAFT).")
    if mdr is not None:
        st.caption(f"Markdown review (eligibility only) · policy {policy}, scenario {scenario}: {mdr.eligibility_label}"
                   + (f" — {mdr.reasons}" if mdr.reasons else "") + ". No discount size is proposed.")
with st.expander("Technical details — original codes"):
    st.write({"reason_codes": reason_codes, "warnings": warning_codes, "case_type": review_code,
              "action_status": d.action_status, "order_id": d.order_id, "order_basis": d.order_basis,
              "delivery_arrangement": d.delivery_arrangement,
              **({"pre_delivery_position": d.pre_delivery_position, "post_order_position": d.post_order_position}
                 if policy == "P2" else {})})
ui.link_to("pages/5_Markdown_review.py", label="Open Markdown review", icon="🏷️")

# --------------------------------------------------------------------------------------------- sales and forecasts
st.header("Sales and demand forecast")
st.caption("Recorded weekly sales beside the forecast and its likely range. Forecasts are made before each week; recorded sales are known only afterwards.")
sales = ui.load_sales(int(store), int(product))
con = ui.load_contract()
horizon = st.radio("Forecast made", [1, 4], format_func=lambda h: "1 week ahead" if h == 1 else "4 weeks ahead", horizontal=True)
f = con[(con.store_id == store) & (con.product_id == product) & (con.horizon_weeks == horizon)].copy()
f["week"] = f["target_week"]
hist = sales.rename(columns={"week_index": "week"})
x = alt.X("week:Q", title="Week of 2024", scale=alt.Scale(domain=[1, 52]))
band = alt.Chart(f.dropna(subset=["lower_p10_units"])).mark_area(opacity=0.18, color=T.TEAL).encode(
    x=x, y=alt.Y("lower_p10_units:Q", title="Units per week", axis=alt.Axis(format="~s")), y2="upper_p90_units:Q",
    tooltip=[alt.Tooltip("week:Q", title="Week"), alt.Tooltip("lower_p10_units:Q", title="Low (p10)", format=",.0f"),
             alt.Tooltip("median_p50_units:Q", title="Typical (p50)", format=",.0f"),
             alt.Tooltip("upper_p90_units:Q", title="High (p90)", format=",.0f")])
fc = alt.Chart(f).mark_line(strokeWidth=2.6, color=T.TEAL).encode(
    x=x, y="predicted_units:Q", tooltip=[alt.Tooltip("week:Q", title="Week"),
                                         alt.Tooltip("predicted_units:Q", title="Forecast", format=",.0f")])
sold = alt.Chart(hist).mark_line(strokeWidth=2, color=T.NAVY, strokeDash=[5, 3]).encode(
    x=x, y="Units_Sold:Q", tooltip=[alt.Tooltip("week:Q", title="Week"), alt.Tooltip("WeekDate:N", title="Week starting"),
                                    alt.Tooltip("Units_Sold:Q", title="Recorded sales", format=",")])
rule = alt.Chart(pd.DataFrame({"week": [target]})).mark_rule(color=T.AMBER, strokeWidth=2, strokeDash=[2, 2]).encode(x="week:Q")
st.altair_chart(T.chart(band + fc + sold + rule, 330), width="stretch")
st.markdown("**Teal line** forecast · **teal band** likely range (low to high) · **dashed navy** recorded sales · "
            "**amber line** selected week")
missing = int((f.uncertainty_status != "AVAILABLE").sum())
if missing:
    st.caption(f"{missing} of {len(f)} early forecasts have no likely range yet (too little history). Those weeks fall "
               "before the simulated period and always require a manager's review.")

# -------------------------------------------------------------------------------------------- stock over time
st.header("Simulated stock flow")
st.caption(D.SIMULATED_LABEL)
T.md(T.grid([
    T.kpi("📦", "Units ordered", ui.fmt(dec.ordered_units.sum()), "Hypothetical orders, 20 weeks", T.NAVY_3, "Simulated"),
    T.kpi("🛍️", "Units sold", ui.fmt(wk.sim_sold_units.sum()), "In the replay", T.EMERALD, "Simulated"),
    T.kpi("🚫", "Units customers could not buy", ui.fmt(wk.sim_unmet_units_illustrative.sum()),
          "Illustrative, not observed lost sales", T.AMBER, "Simulated"),
    T.kpi("🗑️", "Units gone out of date", ui.fmt(wk.sim_expired_units.sum()), "In the replay", T.RED, "Simulated"),
]))
names = {"sim_received_units": "Delivered", "sim_sold_units": "Sold", "sim_expired_units": "Out of date",
         "sim_unmet_units_illustrative": "Could not buy"}
long = wk.melt(id_vars="week", value_vars=list(names), var_name="measure", value_name="units")
long["measure"] = long["measure"].map(names)
order = list(names.values())
lines = alt.Chart(long).mark_line(strokeWidth=2.5, point=alt.OverlayMarkDef(size=45)).encode(
    x=alt.X("week:Q", title="Simulated week"), y=alt.Y("units:Q", title="Units", axis=alt.Axis(format="~s")),
    color=alt.Color("measure:N", sort=order, title=None,
                    scale=alt.Scale(domain=order, range=[T.NAVY_3, T.EMERALD, T.RED, T.AMBER])),
    tooltip=[alt.Tooltip("week:Q", title="Week"), alt.Tooltip("measure:N", title="Measure"), alt.Tooltip("units:Q", format=",")])
st.altair_chart(T.chart(lines + rule, 300), width="stretch")

with st.expander("Weekly decisions table"):
    show = pd.DataFrame({
        "Order for week": dec.target_week, "Proposed units": dec.ordered_units, "Deliveries": dec.n_deliveries,
        "First arrival": dec.arrival_day.map(L.day_label), "Status": dec.action_status.map(lambda s: L.label(L.ACTION_STATUS, s)),
        "Reasons": dec["flags"].map(lambda f: "; ".join(L.reasons(D.parse_list(f))))})
    if policy == "P2":
        show.insert(1, "Recommendation", dec.primary_category.map(lambda c: L.label(L.CATEGORIES, c)))
        show.insert(2, "Review", dec.case_type.map(L.case_type))
    show = show.merge(wk[["week", "sim_opening_units", "sim_expired_units", "sim_closing_units"]].rename(columns={
        "week": "Order for week", "sim_opening_units": "Opening stock", "sim_expired_units": "Out of date",
        "sim_closing_units": "Closing stock"}), on="Order for week", how="left")
    st.dataframe(show, hide_index=True, width="stretch")
with st.expander("Every scheduled delivery"):
    st.dataframe(pd.DataFrame({
        "Delivery": dl_all.delivery_id, "Type": dl_all.kind.map({"ORDER": "Order", "INITIAL_SCHEDULE": "Starting stock plan"}),
        "Arrives": dl_all.arrival_day.map(L.day_label), "Last day it can be sold": dl_all.expiry_day.map(L.day_label),
        "Ordered units": dl_all.ordered_units, "Delivered units (simulated)": dl_all.delivered_units,
        "Need before case rounding": dl_all.need_units_before_rounding.round(1), "Authorisation": dl_all.authorisation}),
        hide_index=True, width="stretch")
with st.expander("Data sources and limits"):
    st.markdown(f"- Forecasts: protected forecast contract `{D.CONTRACT_FILE.parent.name}`.\n"
                f"- Simulated stock and recommendations: protected comparison run `{D.COMPARISON_DIR.name}`.\n"
                "- Recorded sales: verified raw panel (illustrative demand, not verified unconstrained demand).\n"
                f"- {D.DAILY_GAP}")
