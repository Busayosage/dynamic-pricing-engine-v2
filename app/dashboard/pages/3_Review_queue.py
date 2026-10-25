import pandas as pd
import streamlit as st

import dashboard_data as D
import labels as L
import theme as T
import ui

ui.page("Review queue", "🗂️")
scenario = ui.scenario_select()
policy = ui.policy_select()
T.md(T.head("Human review centre · read-only", "Decisions waiting for a manager",
            f"Formal policy review cases from the saved outputs of the protected comparison run, with plain reasons and "
            f"what to check. {D.SCENARIO_NAMES[scenario]} · {D.POLICY_NAMES[policy]}.",
            chips=(f"Policy {policy}", f"Scenario {scenario}", "Every case PENDING_REVIEW"), art="queue"))
T.md(T.disclaimer())
T.md(T.banner("<b>Read-only.</b> There are no approve, reject or order buttons. Every case is <b>PENDING_REVIEW</b>: no "
              "approval exists and nothing has been ordered. Christmas cases can never be approved in bulk.",
              "caution", "🔒"))

cases = ui.load_cases(scenario, policy)
names = ui.load_series()[["Store_ID", "Product_ID", "Product_Name"]]
cases = cases.merge(names, left_on=["store_id", "product_id"], right_on=["Store_ID", "Product_ID"], how="left")
cases["Review"] = cases.case_type.map(L.case_type)
cases["Why"] = cases.reasons_list.map(lambda r: "; ".join(L.reasons(r)))
counts = cases.case_type.value_counts()
standing = ui.load_standing(scenario) if policy == "P2" else None

T.md(T.section("Formal policy review cases", "Raised by the inventory policy's review rules — one per store, product and week."))
T.md(T.grid([
    T.kpi("🎄", "Must be escalated", f"{counts.get('MANDATORY_ESCALATION', 0):,}", "Christmas trading weeks", T.RED, "Pending review"),
    T.kpi("📋", "Must be reviewed", f"{counts.get('MANDATORY_REVIEW', 0):,}", "No forecast range yet — no automatic order",
          T.AMBER, "Pending review"),
    T.kpi("⚠️", "Review recommended", f"{counts.get('RISK_ESCALATION', 0):,}", "Shortage, waste or supplier risk",
          T.TEAL, "Pending review"),
    T.kpi("🚚", "Standing supplier items", f"{len(standing):,}" if standing is not None else "—",
          "Separate from policy review (see below)" if standing is not None else "Not used by this policy's queue",
          T.NAVY_3, "Operational follow-up"),
]))

# ------------------------------------------------------------------------------------------------ filters
f1, f2, f3 = st.columns(3)
types = [t for t in ("MANDATORY_ESCALATION", "MANDATORY_REVIEW", "RISK_ESCALATION") if t in counts.index]
sel = f1.multiselect("Review type", types, default=types, format_func=L.case_type, key=f"rq_type_{scenario}_{policy}")
store = f2.selectbox("Store", ["All stores"] + sorted(cases.store_id.unique()), key=f"rq_store_{scenario}_{policy}")
week = f3.selectbox("Order week", ["All weeks"] + sorted((cases.origin_week + 1).astype(int).unique()),
                    key=f"rq_week_{scenario}_{policy}")
view = cases[cases.case_type.isin(sel)]
if store != "All stores":
    view = view[view.store_id == store]
if week != "All weeks":
    view = view[(view.origin_week + 1) == week]
level = {"MANDATORY_ESCALATION": "high", "MANDATORY_REVIEW": "caution", "RISK_ESCALATION": "info"}

if len(view) == 0:
    T.md(T.banner("No cases match these filters.", "neutral", "🔍"))
else:
    shown = view.head(25)
    rows = [(r.store_id, r.Product_Name, int(r.origin_week) + 1, T.chip(r.Review, level[r.case_type]),
             T.chip("Pending review", "caution"), r.Why or "—") for r in shown.itertuples()]
    T.md(T.table(["Store", "Product", "Order week", "Review", "Status", "Why"], rows, html_cols=("Review", "Status")))
    st.caption(f"Showing the first {len(shown):,} of {len(view):,} matching cases. The full list is below.")
    with st.expander(f"All {len(view):,} matching cases"):
        table = pd.DataFrame({"Store": view.store_id, "Product": view.Product_Name, "Order week": view.origin_week + 1,
                              "Review": view.Review, "Why": view.Why, "Status": view.review_status})
        if policy == "P2":
            table.insert(4, "Proposed units (hypothetical)", view.proposed_order_units)
        st.dataframe(table, hide_index=True, width="stretch", height=360)

    # ------------------------------------------------------------------------------------------ case detail
    T.md(T.section("Case explained", "Choose a case to see what needs attention and what to check."))
    options = view.index.tolist()[:1000]
    pick = st.selectbox("Choose a case", options, key=f"rq_pick_{scenario}_{policy}",
                        format_func=lambda i: f"Store {view.loc[i, 'store_id']} · {view.loc[i, 'Product_Name']} · "
                                              f"week {int(view.loc[i, 'origin_week']) + 1} · {view.loc[i, 'Review']}")
    row = view.loc[pick]
    codes = set(row.reasons_list)
    tips = []
    if "CHRISTMAS_PERIOD" in codes:
        tips.append("Christmas demand is hard to forecast — confirm the quantity against seasonal plans.")
    if "UNCERTAINTY_UNAVAILABLE" in codes:
        tips.append("There is not yet enough history for a forecast range, so no order was proposed — decide manually.")
    if codes & {"PRE_DELIVERY_SHORTAGE", "PRE_ORDER_SHORTAGE"}:
        tips.append("Stock may run out before the delivery arrives — check shelf stock; faster delivery or a transfer is "
                    "not assumed to be available.")
    if codes & {"EXPIRY_BEFORE_COVERAGE", "WASTE_HIGH_EXISTING_STOCK"}:
        tips.append("Current stock may go out of date — check dates on the shelf.")
    if "ARRANGEMENT_FEASIBILITY_RISK" in codes:
        tips.append("The plan relies on a delivery schedule the supplier has not confirmed.")
    if "FILL_RATE_SHORTFALL_LAST_WEEK" in codes:
        tips.append("Last week's delivery arrived short — check with the supplier.")
    if "TREND_DIVERGENCE" in codes:
        tips.append("Short- and longer-range forecasts disagree — sense-check recent sales.")
    tips = tips or ["Check the proposed quantity and the reasons above."]
    qty = f"{ui.fmt(row.proposed_order_units)} units" if policy == "P2" else "See Product investigation"
    reasons = "".join(T.chip(x, "info") + " " for x in L.reasons(row.reasons_list))
    warns = "".join(T.chip(x, "neutral") + " " for x in L.reasons(row.warnings_list))
    T.md(f'<div class="ds-detail"><div class="ds-sub">Store {row.store_id} · order week {int(row.origin_week) + 1} · '
         f'policy {policy}, scenario {scenario}</div><div class="h">{T._e(row.Product_Name)}</div>'
         f'<div style="margin:.5rem 0">{T.chip(row.Review, level[row.case_type])} {T.chip("Pending review", "caution")} '
         f'{T.chip("Proposed: " + qty + " · hypothetical", "neutral")}</div>'
         f'<div class="ds-sub" style="margin-top:.6rem;font-weight:700">Why it needs attention</div><div>{reasons or "—"}</div>'
         + (f'<div class="ds-sub" style="margin-top:.6rem;font-weight:700">Also worth knowing</div><div>{warns}</div>' if warns else "")
         + '<div class="ds-panel"><div class="l">What to check</div><div class="p">'
         + "<br>".join("• " + T._e(t) for t in tips) + "</div></div></div>")
    with st.expander("Full explanation and technical details"):
        if policy == "P2" and isinstance(row.explanation, str):
            st.info(L.humanize(row.explanation))
        st.write({"case_id": row.get("case_id"), "case_type": row.case_type, "reason_codes": row.reasons_list,
                  "warnings": row.warnings_list, "status": row.review_status, "approval_event_id": None})

# ------------------------------------------------------------------------------------------- standing items
T.md(T.section("Standing supplier-confirmation items",
               "Not policy review cases: one item per fresh product line whose frequent or weekend deliveries are "
               "assumed but not confirmed. Checked once rather than every week."))
if standing is None:
    T.md(T.banner("P0 and P1 use the original review rules, which have no separate supplier-confirmation items. Select "
                  "P2 in the sidebar to see them.", "neutral", "ℹ️"))
else:
    s = standing.merge(names, left_on=["store_id", "product_id"], right_on=["Store_ID", "Product_ID"], how="left")
    head = s.head(12)
    rows = [(r.store_id, r.Product_Name, r.product_category, L.label(L.SUPPLIER_STATUS, r.arrangement_status),
             ", ".join(D.parse_list(r.weekend_drop_days)) or "None", T.chip("Pending confirmation", "caution"))
            for r in head.itertuples()]
    T.md(T.table(["Store", "Product", "Category", "Arrangement", "Weekend drops", "Status"], rows, html_cols=("Status",)))
    with st.expander(f"All {len(s):,} standing supplier items"):
        st.dataframe(pd.DataFrame({"Store": s.store_id, "Product": s.Product_Name, "Category": s.product_category,
                                   "Status": s.arrangement_status.map(lambda c: L.label(L.SUPPLIER_STATUS, c)),
                                   "Weekend drops": s.weekend_drop_days.map(lambda x: ", ".join(D.parse_list(x)) or "None"),
                                   "Review": "Pending"}), hide_index=True, width="stretch", height=300)
