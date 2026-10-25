import pandas as pd
import streamlit as st

import dashboard_data as D
import theme as T
import ui
from dpe.decision import markdown_eligibility as M

ui.page("Markdown review", "🏷️")
scenario = ui.scenario_select()
policy = ui.policy_select()
prm = ui.load_markdown_params()
md = ui.load_markdown(scenario, policy)  # one table drives every figure below
policy_name = D.POLICY_NAMES[policy].split(" — ")[1]
scenario_name = D.SCENARIO_NAMES[scenario].split(" — ")[1]

T.md(T.head("Markdown review intelligence · eligibility only", "Markdown Opportunity Review",
            "Find products worth investigating for possible discounts before stock expires.",
            chips=(f"Policy {policy}", f"Scenario {scenario}", "No discount proposed"), art="tag"))
T.md(f'<div class="ds-sub" style="font-size:1rem;margin:-.2rem 0 .8rem 0">Showing inventory policy <b>{policy} — '
     f'{T._e(policy_name)}</b> in scenario <b>{scenario} — {T._e(scenario_name)}</b>. Change either in the left sidebar; '
     'every count and explanation on this page updates together.</div>')
T.md(T.disclaimer())
T.md(T.banner("<b>Eligibility only.</b> This page identifies lines worth a person's investigation. It does <b>not</b> "
              "calculate, propose or approve a discount, set a new price, or predict sales, margin or waste effects. "
              "There are no approval buttons.", "caution", "🏷️"))

# -------------------------------------------------------------------------------------------- executive summary
counts = md.eligibility.value_counts()
eligible = md[md.eligibility == "ELIGIBLE_FOR_MARKDOWN_REVIEW"]
held = int(counts.get("BLOCKED", 0) + counts.get("INSUFFICIENT_INFORMATION", 0))
T.md(T.section("Executive summary", f"Store × product × decision weeks for {policy} in {scenario} "
                                    "(720 series × 20 simulated weeks)."))
T.md(T.grid([
    T.kpi("🔎", "Eligible for markdown review", f"{counts.get('ELIGIBLE_FOR_MARKDOWN_REVIEW', 0):,}",
          "Worth a person's investigation", T.TEAL, "Eligibility evidence"),
    T.kpi("⛔", "Blocked", f"{counts.get('BLOCKED', 0):,}", "A blocker applies (all are listed)", T.RED, "Eligibility evidence"),
    T.kpi("⚪", "Insufficient information", f"{counts.get('INSUFFICIENT_INFORMATION', 0):,}",
          "More evidence needed to judge timing", T.AMBER, "Eligibility evidence"),
    T.kpi("▫️", "Not considered", f"{counts.get('NOT_CONSIDERED', 0):,}", "Low waste risk", "#64748B", "Eligibility evidence"),
]))
T.md(T.grid([
    T.kpi("🛒", "Products represented", f"{eligible.Product_ID.nunique():,}", "among eligible lines", T.NAVY_3,
          "From the eligible rows"),
    T.kpi("🏬", "Stores represented", f"{eligible.Store_ID.nunique():,}", "among eligible lines", T.NAVY_3,
          "From the eligible rows"),
    T.kpi("🧱", "Blocked or needing evidence", f"{held:,}", "blocked + insufficient information", T.AMBER,
          "Eligibility evidence"),
    T.kpi("🚫", "Discount status", "No discount proposed", "No percentage or price is calculated anywhere", T.CORAL,
          "Eligibility only"),
]))
considered = md[md.eligibility != "NOT_CONSIDERED"]
st.caption(f"{int(considered.warning_codes.str.len().gt(0).sum()):,} of the {len(considered):,} considered lines also have an "
           "open inventory review case — shown as a warning, never a blocker.")

# --------------------------------------------------------------------------------------------- review table
T.md(T.section("Review table", "Filter the lines, then choose one to open its investigation panel."))
f1, f2, f3, f4 = st.columns([1.6, 1, 1.4, 1])
status = f1.multiselect("Review status", [c for c in M.CLASSES if c != "NOT_CONSIDERED"],
                        default=["ELIGIBLE_FOR_MARKDOWN_REVIEW", "BLOCKED", "INSUFFICIENT_INFORMATION"],
                        format_func=lambda c: f"{ui.MARKDOWN_ICON[c]} {M.CLASS_LABELS[c]}", key=f"md_status_{scenario}_{policy}")
store = f2.selectbox("Store", ["All stores"] + sorted(md.Store_ID.unique()), key=f"md_store_{scenario}_{policy}")
pool = md if store == "All stores" else md[md.Store_ID == store]
product = f3.selectbox("Product", ["All products"] + sorted(pool.Product_Name.dropna().unique()),
                       key=f"md_product_{scenario}_{policy}")
week = f4.selectbox("Decision week", ["All weeks"] + sorted(md.target_week.unique()), key=f"md_week_{scenario}_{policy}")
view = md[md.eligibility.isin(status)]
if store != "All stores":
    view = view[view.Store_ID == store]
if product != "All products":
    view = view[view.Product_Name == product]
if week != "All weeks":
    view = view[view.target_week == week]
order = {c: i for i, c in enumerate(M.CLASSES)}
view = view.sort_values(["eligibility", "projected_expiry_pct_of_p50"], ascending=[True, False],
                        key=lambda s: s.map(order) if s.name == "eligibility" else s)
level = {"ELIGIBLE_FOR_MARKDOWN_REVIEW": "info", "BLOCKED": "high", "INSUFFICIENT_INFORMATION": "caution",
         "NOT_CONSIDERED": "neutral"}

if len(view) == 0:
    T.md(T.banner("No lines match these filters.", "neutral", "🔍"))
else:
    rows = [(T.chip(f"{ui.MARKDOWN_ICON[r.eligibility]} {M.CLASS_LABELS[r.eligibility]}", level[r.eligibility]),
             r.Store_ID, r.Product_Name, r.target_week, ui.fmt(r.projected_existing_expiry_units) + " units",
             r.investigate_by_label or "—", r.reasons or "None — eligible") for r in view.head(25).itertuples()]
    T.md(T.table(["Review status", "Store", "Product", "Decision week", "Simulated expiry exposure", "Investigate by",
                  "Missing evidence / blockers"], rows, html_cols=("Review status",)))
    st.caption(f"Showing the first {min(25, len(view)):,} of {len(view):,} matching lines. Simulated expiry exposure = "
               "stock already in store projected to go out of date (SIMULATED × FORECAST).")
    with st.expander(f"All {len(view):,} matching lines"):
        st.dataframe(pd.DataFrame({
            "Status": view.eligibility.map(lambda c: f"{ui.MARKDOWN_ICON[c]} {M.CLASS_LABELS[c]}"),
            "Store": view.Store_ID, "Product": view.Product_Name, "Week": view.target_week,
            "Expiry (units)": view.projected_existing_expiry_units,
            "Investigate by": view.investigate_by_label.fillna("—"),
            "Blockers / gaps": view.reasons.replace("", "—")}), hide_index=True, width="stretch", height=320,
            column_config={"Expiry (units)": st.column_config.NumberColumn(format="%.0f")})

    # --------------------------------------------------------------------------------------- detail panel
    T.md(T.section("Investigation detail", "Read-only. Nothing here proposes, approves or executes a discount."))
    pick = st.selectbox(f"Line ({len(view):,} match the filters)", view.index.tolist()[:1000],
                        key=f"md_pick_{scenario}_{policy}", format_func=lambda i: (
                            f"{ui.MARKDOWN_ICON[view.loc[i, 'eligibility']]} {view.loc[i, 'Product_Name']} · store "
                            f"{view.loc[i, 'Store_ID']} · decision week {view.loc[i, 'target_week']} · "
                            f"{M.CLASS_LABELS[view.loc[i, 'eligibility']]}"))
    r = view.loc[pick]
    share = f"{r.projected_expiry_pct_of_p50:.1f}% of a typical week" if pd.notna(r.projected_expiry_pct_of_p50) else "share undefined"
    days = "—" if pd.isna(r.sellable_days_after_investigate_by) else f"{int(r.sellable_days_after_investigate_by)} day(s)"
    flagged = "".join(T.chip(x, "info") + " " for x in str(r.waste_reasons).split("; ") if x and x != "nan") or "—"
    gaps = []
    if r.blocker_codes:
        gaps += [("⛔ " + M.BLOCKER_LABELS[b], "high") for b in r.blocker_codes.split("|")]
    if r.insufficient_codes:
        gaps += [("⚪ " + M.INSUFFICIENT_LABELS[b], "caution") for b in r.insufficient_codes.split("|")]
    gap_html = " ".join(T.chip(t, lv) for t, lv in gaps) or T.chip("No blockers — eligible for investigation", "ok")
    warn_html = (f'<div class="ds-sub" style="margin-top:.4rem">⚠️ {T._e(M.WARNING_LABELS["OPEN_INVENTORY_REVIEW_CASE"])}: '
                 f'{T._e(r.review_case_ref)}</div>' if r.warning_codes else "")
    missing = r.missing_data_for_numerical_discount.split("|")
    T.md(f'<div class="ds-detail"><div class="ds-sub">Store {r.Store_ID} · {T._e(r.Region)} · decision week {r.target_week} · '
         f'Policy {policy} · scenario {scenario}</div><div class="h">{T._e(r.Product_Name)}</div>'
         f'<div style="margin:.5rem 0">{T.chip(M.CLASS_LABELS[r.eligibility], level[r.eligibility])} '
         f'{T.chip("No proposal · nothing approved or executed", "neutral")}</div>'
         + T.grid([
             T.kpi("🔭", "Simulated expiry exposure", f"{ui.fmt(r.projected_existing_expiry_units)} units", share, T.RED,
                   "SIMULATED × FORECAST"),
             T.kpi("📅", "Investigation deadline", r.investigate_by_label or "—",
                   f"Oldest batch sellable until {r.earliest_batch_last_day_label}" if r.earliest_batch_last_day_label
                   else "No dated batch evidence", T.AMBER, "SIMULATED delivery dates"),
             T.kpi("⏱️", "Sellable days after the deadline", days, "provisional one-day rule", T.NAVY_3, "calculated"),
         ])
         + '<div class="ds-sub" style="font-weight:700;margin-top:.3rem">1 · Why this line was flagged</div>'
         f'<div>{flagged}</div><div style="margin-top:.45rem">{gap_html}</div>{warn_html}'
         '<div class="ds-panel"><div class="l">2 · What the manager should investigate</div>'
         f'<div class="p">{T._e(r.guidance)}</div></div>'
         '<div class="ds-sub" style="font-weight:700;margin-top:.8rem">3 · Why a numerical discount cannot be recommended yet</div>'
         '<div class="ds-sub">No discount size is proposed. This verified information does not exist yet: '
         + "; ".join(T._e(M.MISSING_DATA_LABELS[c].lower()) for c in missing) + ".</div></div>")
    with st.expander("Technical evidence — recorded price, codes and provenance"):
        price = "—" if pd.isna(r.recorded_price_origin_week) else f"{r.recorded_price_origin_week:.2f}"
        disc = "—" if pd.isna(r.recorded_discount_pct_origin_week) else f"{int(r.recorded_discount_pct_origin_week)}%"
        st.markdown(f"- Recorded shelf price in the decision week: **{price}** (RECORDED, apparently synthetic dataset; "
                    "currency assumed GBP; context only, not a recommendation)\n"
                    f"- Recorded promotion in the decision week: **{disc}** (used only for the promotion blocker)")
        st.write({"eligibility": r.eligibility, "blocker_codes": r.blocker_codes.split("|") if r.blocker_codes else [],
                  "insufficient_codes": r.insufficient_codes.split("|") if r.insufficient_codes else [],
                  "warning_codes": r.warning_codes.split("|") if r.warning_codes else [],
                  "waste_risk_category": r.waste_risk_category, "lifecycle_state": r.lifecycle_state,
                  "status": r.status, "execution_status": r.execution_status, "proposal_id": None,
                  "approval_event_id": None})
    if r.eligibility == "ELIGIBLE_FOR_MARKDOWN_REVIEW":
        ui.link_to("pages/6_Discount_decision_lab.py", label="Compare markdown options for eligible lines in the "
                   "Discount Decision Lab (simulated research — not validated for live use)", icon="🧪")

# ------------------------------------------------------------------------------- before a discount can be recommended
T.md(T.section("Before a discount can be recommended",
               "Every item below must be verified before a discount could be recommended for live use. Until then the Discount Decision Lab only ranks options as simulated research."))
T.md(T.grid([
    T.evidence_card("💷", "Verified unit purchase cost", "Missing", "Margins are assumed; no real cost per unit exists."),
    T.evidence_card("🏷️", "Verified shelf price", "Partial", "Recorded prices are noisy; the reference price is an "
                    "estimated proxy.", "caution"),
    T.evidence_card("📦", "Batch-level inventory and expiry", "Missing", "Stock by batch is simulated; units left per batch "
                    "are not saved."),
    T.evidence_card("📈", "Actual historical markdown response", "Missing", "Recorded discounts are not causal evidence of "
                    "how sales respond."),
    T.evidence_card("⚖️", "Legal and commercial pricing rules", "Missing", "Legal limits, supplier and brand agreements, "
                    "price matching."),
    T.evidence_card("🏪", "Store markdown operations", "Missing", "Markdown times, label printing and staff capacity."),
    T.evidence_card("🧑‍💼", "Authorised approvers", "Documented only", "Roles and limits are written down; nothing is built.",
                    "caution"),
    T.evidence_card("🚚", "Confirmed supplier delivery schedules", "Missing", "360 fresh lines rely on assumed schedules."),
    T.evidence_card("♻️", "Alternative actions and their costs", "Missing", "Donation, staff sale or disposal values."),
]))

T.md(T.section("How a discount would move through the process",
               "Only stage 1 exists. Approval roles and audit requirements are documented only."))
T.md(T.steps([
    ("1", "Eligible for investigation", "This page — built. Says whether a person should look at a line.", T.EMERALD),
    ("2", "Discount proposal — NOT BUILT", "A specific, bounded proposal; needs the verified evidence above.", "#94A3B8"),
    ("3", "Human authorisation — NOT BUILT", "A named, authorised person decides; never bulk or automatic, never for "
     "Christmas by default.", "#94A3B8"),
    ("4", "Store execution and audit — NOT BUILT", "Done in the store's own price system, confirmed back and kept in an "
     "append-only audit record.", "#94A3B8"),
]))

with st.expander("How eligibility is decided"):
    st.markdown(
        "Checked in this order — the first match gives the final status:\n\n"
        "1. ▫️ **Not considered** — waste risk is Low.\n"
        "2. ⚪ **Insufficient information** — waste risk cannot be judged, or there is no dated batch evidence.\n"
        "3. ⛔ **Blocked** — High or Moderate waste risk, but one or more blockers apply (all are listed): Christmas "
        "escalation week · stock may run short before the next delivery · already on a recorded promotion · product on "
        f"the exclusion list (currently **{len(prm['markdown_product_exclusions'])}** products) · fewer than "
        f"**{prm['markdown_min_sellable_days_after_investigate_by']}** sellable day left after the investigate-by day.\n"
        "4. 🔎 **Eligible for markdown review** — everything else with High or Moderate waste risk.\n\n"
        "An open inventory review case is shown as a **warning**, not a blocker.\n\n"
        f"Rules are ASSUMED and provisional — assumption set **{prm['assumption_set_id']} ({prm['assumption_status']})**.")
with st.expander("Data sources and evidence labels"):
    st.dataframe(pd.DataFrame({"Figure": list(M.PROVENANCE), "Evidence": list(M.PROVENANCE.values())}),
                 hide_index=True, width="stretch")
