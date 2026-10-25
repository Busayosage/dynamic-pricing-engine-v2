"""Shared Streamlit helpers: cached read-only loaders, sidebar selections, page styling and safety banners."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import dashboard_data as D
import labels as L

load_series = st.cache_data(show_spinner=False)(D.series_list)
load_forecast_metrics = st.cache_data(show_spinner=False)(D.forecast_metrics)
load_forecast_by_category = st.cache_data(show_spinner=False)(D.forecast_metrics_by_category)
load_acceptance = st.cache_data(show_spinner=False)(D.acceptance_matrix)
load_contract = st.cache_data(show_spinner="Loading forecast contract…")(D.contract)
load_sales = st.cache_data(show_spinner=False)(D.sales_history)
load_comparison = st.cache_data(show_spinner=False)(D.comparison_table)
load_pct = st.cache_data(show_spinner=False)(D.pct_change_table)
load_evaluation = st.cache_data(show_spinner=False)(D.evaluation)
load_decisions = st.cache_data(show_spinner="Loading decisions…")(D.decisions)
load_weekly = st.cache_data(show_spinner=False)(D.weekly)
load_deliveries = st.cache_data(show_spinner="Loading deliveries…")(D.deliveries)
load_cases = st.cache_data(show_spinner="Loading review cases…")(D.review_cases)
load_standing = st.cache_data(show_spinner=False)(D.standing_cases)
load_recommendations = st.cache_data(show_spinner="Loading recommendations…")(D.recommendations)

SCENARIO_EXPLAINED = {
    "SC1": "Normal trading: typical opening stock, demand equal to recorded sales and suppliers delivering in full.",
    "SC2": "Pressure: low opening stock, demand 15% above recorded sales, suppliers delivering 75% and arriving a day later.",
    "SC3": "Excess stock: double opening stock, demand 15% below recorded sales and extra fresh deliveries — expiry pressure.",
    "SF75": "Stress test: like normal trading, but suppliers deliver only 75% of each order while planning still expects 100%.",
}
POLICY_EXPLAINED = {
    "P0": "Orders the average of the last four weeks of recorded sales, minus all stock on the shelf — even stock about to "
          "go out of date. A deliberately simple baseline.",
    "P1": "The original forecast-based rule: orders between the typical and high-demand forecast, counting all stock that "
          "is still in date when the delivery arrives.",
    "P2": "The improved rule: plans day by day and only counts stock on the days it can still be sold, so stock that "
          "expires mid-week is not double-counted. The research default — not approved for production.",
}

CSS = """
<style>
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px;}
h1 {font-size: 2.1rem !important; margin-bottom: 0.2rem;}
h2 {font-size: 1.45rem !important; margin-top: 1.6rem !important;}
h3 {font-size: 1.15rem !important;}
p, li {font-size: 1.0rem; line-height: 1.55;}
[data-testid="stMetricLabel"] p {font-size: 0.9rem !important;}
[data-testid="stMetricValue"] {font-size: 1.6rem !important;}
.dpe-kicker {text-transform: uppercase; letter-spacing: .06em; font-size: .78rem; opacity: .7; margin-bottom: .1rem;}
.dpe-pill {display:inline-block; padding: .15rem .6rem; border-radius: 999px; font-size: .85rem; margin: .1rem .25rem .1rem 0;
           border: 1px solid rgba(128,128,128,.35);}
.dpe-big {font-size: 1.35rem; font-weight: 600; line-height: 1.3;}
.dpe-muted {opacity: .75; font-size: .92rem;}
@media (max-width: 640px) { h1 {font-size: 1.6rem !important;} [data-testid="stMetricValue"] {font-size: 1.3rem !important;} }
</style>
"""


def page(title: str, icon: str = "📦") -> None:
    st.set_page_config(page_title=f"{title} · Dynamic Pricing Engine V2", page_icon=icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    import theme  # design system shared by every page (presentation only)

    theme.apply_all()
    st.sidebar.markdown("### Dynamic Pricing Engine V2")
    st.sidebar.caption("Research demonstration · read-only · synthetic data")


def scenario_select(key: str = "scenario") -> str:
    if key not in st.session_state:
        st.session_state[key] = "SC1"
    return st.sidebar.selectbox("Scenario", D.SCENARIOS, format_func=D.SCENARIO_NAMES.get, key=key)


def policy_select(key: str = "policy") -> str:
    if key not in st.session_state:
        st.session_state[key] = "P2"
    return st.sidebar.selectbox("Inventory policy", D.POLICIES, format_func=D.POLICY_NAMES.get, key=key)


def safety_banner() -> None:
    st.info("**Research demonstration on synthetic data.** Stock, orders and waste are simulated; recorded sales are not "
            "verified true demand. Every order shown is **HYPOTHETICAL_UNAPPROVED · NOT_EXECUTED** — nothing has been "
            "approved, ordered, priced or transferred. No policy is approved for production.", icon="ℹ️")


def fmt(n) -> str:
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return "—"


def pills(items) -> None:
    if not items:
        st.markdown('<span class="dpe-muted">None</span>', unsafe_allow_html=True)
        return
    st.markdown(" ".join(f'<span class="dpe-pill">{x}</span>' for x in items), unsafe_allow_html=True)


def kicker(text: str) -> None:
    st.markdown(f'<div class="dpe-kicker">{text}</div>', unsafe_allow_html=True)


def big(text: str) -> None:
    st.markdown(f'<div class="dpe-big">{text}</div>', unsafe_allow_html=True)


def style_chart(chart: alt.Chart, height: int = 300) -> alt.Chart:
    return (chart.properties(height=height)
            .configure_axis(labelFontSize=13, titleFontSize=14, titlePadding=10, grid=True, gridOpacity=0.35)
            .configure_legend(labelFontSize=13, titleFontSize=13, orient="top", symbolSize=120)
            .configure_view(strokeWidth=0))


def policy_bar(df: pd.DataFrame, value: str, title: str) -> alt.Chart:
    """Bar per policy in fixed identity colours, with direct value labels (palette relief rule)."""
    df = df.assign(policy_label=df["policy_id"].map({"P0": "P0 baseline", "P1": "P1 original", "P2": "P2 improved"}))
    order = ["P0 baseline", "P1 original", "P2 improved"]
    base = alt.Chart(df).encode(
        x=alt.X("policy_label:N", title=None, sort=order, axis=alt.Axis(labelAngle=0)),
        y=alt.Y(f"{value}:Q", title=None, axis=alt.Axis(format="~s")),
        color=alt.Color("policy_label:N", scale=alt.Scale(domain=order, range=[D.POLICY_COLORS[p] for p in D.POLICIES]),
                        legend=None),
        tooltip=[alt.Tooltip("policy_label:N", title="Policy"), alt.Tooltip(f"{value}:Q", title=title, format=",")])
    bars = base.mark_bar(size=46, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
    text = base.mark_text(dy=-9, fontSize=13, color="#52514e").encode(text=alt.Text(f"{value}:Q", format=","))
    return style_chart((bars + text).properties(title=alt.TitleParams(title, fontSize=15, anchor="start")), 270)

load_waste_risk = st.cache_data(show_spinner="Assessing waste risk from saved outputs…")(D.waste_risk)
load_waste_comparison = st.cache_data(show_spinner=False)(D.waste_category_comparison)
load_waste_params = st.cache_data(show_spinner=False)(D.waste_risk_params)
WASTE_ICON = {"HIGH": "🔴", "MODERATE": "🟠", "LOW": "🟢", "INSUFFICIENT_INFORMATION": "⚪"}


def evidence(label: str, value: str, kind: str) -> None:
    """A value with its evidence label (RECORDED / FORECAST / SIMULATED / ASSUMED / MISSING)."""
    st.markdown(f'<div class="dpe-kicker">{label}</div><div class="dpe-big">{value}</div>'
                f'<span class="dpe-pill">{kind}</span>', unsafe_allow_html=True)

load_markdown = st.cache_data(show_spinner="Assessing markdown review eligibility…")(D.markdown_review)
load_markdown_params = st.cache_data(show_spinner=False)(D.markdown_params)
MARKDOWN_ICON = {"ELIGIBLE_FOR_MARKDOWN_REVIEW": "🔎", "BLOCKED": "⛔", "INSUFFICIENT_INFORMATION": "⚪", "NOT_CONSIDERED": "▫️"}


def link_to(page_path: str, label: str, icon: str = "➡️") -> None:
    """Link to another dashboard page; falls back to a text pointer when the page runs on its own (e.g. in tests)."""
    try:
        st.page_link(page_path, label=label, icon=icon)
    except Exception:  # noqa: BLE001 - st.page_link needs the multipage app context
        st.markdown(f"{icon} {label} — use the left sidebar.")

load_pricing = st.cache_data(show_spinner="Preparing illustrative pricing options…")(D.pricing_demo)
load_pricing_params = st.cache_data(show_spinner=False)(D.pricing_params)
load_recommendations_v6 = st.cache_data(show_spinner="Ranking markdown options under the stated scenarios…")(D.discount_recommendations)
load_recommendation_params = st.cache_data(show_spinner=False)(D.recommendation_params)
load_dp_evaluation = st.cache_data(show_spinner=False)(D.dp_evaluation)
load_dp_manifest = st.cache_data(show_spinner=False)(D.dp_manifest)
load_dp_comparison = st.cache_data(show_spinner=False)(D.dp_comparison)
load_dp_decisions = st.cache_data(show_spinner="Loading simulated pricing decisions…")(D.dp_decisions)
load_dp_daily = st.cache_data(show_spinner="Loading price and stock timelines…")(D.dp_daily)
load_dp_line_deltas = st.cache_data(show_spinner=False)(D.dp_line_deltas)
load_dp_rule_comparison = st.cache_data(show_spinner=False)(D.dp_rule_comparison)
load_dp_rule_decision = st.cache_data(show_spinner=False)(D.dp_rule_decision)
load_intervention_params = st.cache_data(show_spinner=False)(D.intervention_params)
load_waste_interventions = st.cache_data(show_spinner="Assessing possible interventions…")(D.waste_interventions)


def money(x, decimals: int = 2) -> str:
    """Display-only rounding; calculations stay at full precision."""
    try:
        return f"{float(x):,.{decimals}f}"
    except (TypeError, ValueError):
        return "—"
