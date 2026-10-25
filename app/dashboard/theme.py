"""Dashboard design system (presentation only): colour tokens, page styling and reusable HTML components.

Apply with `theme.apply()` on a page. Components return HTML strings rendered with st.markdown(..., unsafe_allow_html=True)
via the `show_*` helpers. Nothing here reads or changes data; every figure passed in comes from the existing read-only
data layer. Colours: navy #10243A, teal #0D9488, emerald #16A34A, background #F1F5F9, amber = caution, red = blocked/high.
"""
from __future__ import annotations

import html

import altair as alt
import streamlit as st

NAVY, NAVY_2, NAVY_3 = "#10243A", "#17324F", "#22476E"
TEAL, TEAL_SOFT = "#0D9488", "#CCFBF1"
EMERALD, EMERALD_SOFT = "#16A34A", "#DCFCE7"
AMBER, AMBER_SOFT = "#B45309", "#FEF3C7"
RED, RED_SOFT = "#DC2626", "#FEE2E2"
BG, CARD, BORDER = "#F1F5F9", "#FFFFFF", "#E2E8F0"
INK, MUTED = "#0F172A", "#475569"
LEVELS = {"ok": (EMERALD, EMERALD_SOFT), "caution": (AMBER, AMBER_SOFT), "high": (RED, RED_SOFT),
          "info": (TEAL, TEAL_SOFT), "neutral": (MUTED, "#F1F5F9")}
CATEGORY_ICON = {"Bakery": "🥖", "Beverages": "🥤", "Dairy": "🥛", "Meat": "🥩"}
POLICY_ACCENT = {"P0": "#64748B", "P1": "#2563EB", "P2": TEAL}
FONT = "'Segoe UI', 'Inter', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif"

CSS = f"""
<style>
.stApp {{background: linear-gradient(180deg, {BG} 0%, #E9EEF5 100%); color: {INK}; font-family: {FONT};}}
[data-testid="stHeader"] {{background: transparent;}}
.block-container {{padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1480px; padding-left: 2.2rem; padding-right: 2.2rem;}}
@media (max-width: 640px) {{ .block-container {{padding-left: 1rem; padding-right: 1rem;}} }}
h1, h2, h3 {{color: {NAVY} !important; font-family: {FONT}; letter-spacing: -0.01em;}}
h2 {{font-size: 1.4rem !important; margin-top: 1.8rem !important;}}
p, li, label {{font-size: 1rem; line-height: 1.55;}}
[data-testid="stCaptionContainer"] p {{color: {MUTED}; font-size: .9rem;}}
/* sidebar */
[data-testid="stSidebar"] {{background: linear-gradient(180deg, {NAVY} 0%, {NAVY_2} 100%);}}
[data-testid="stSidebar"] * {{color: #E2E8F0;}}
[data-testid="stSidebar"] h3 {{color: #FFFFFF !important;}}
[data-testid="stSidebarNav"] a {{border-radius: 8px; margin: 2px 6px;}}
[data-testid="stSidebarNav"] a[aria-current="page"] {{background: rgba(13,148,136,.28); border-left: 3px solid {TEAL};}}
[data-testid="stSidebarNav"] a:hover {{background: rgba(255,255,255,.08);}}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"],
[data-testid="stSidebar"] div[data-baseweb="select"] > div {{background-color: {NAVY_3} !important;
    border: 1px solid rgba(94,234,212,.45) !important; border-radius: 8px;}}
[data-testid="stSidebar"] [data-testid="stSelectbox"] input,
[data-testid="stSidebar"] [data-testid="stSelectbox"] button,
[data-testid="stSidebar"] div[data-baseweb="select"] * {{color: #FFFFFF !important; fill: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;}}
[data-testid="stSidebar"] label p {{color: #CBD5E1 !important; font-weight: 600; font-size: .85rem;
    text-transform: uppercase; letter-spacing: .05em;}}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {{color: #94A3B8;}}
/* native widgets on the main canvas */
[data-testid="stExpander"] {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px;}}
[data-testid="stVerticalBlockBorderWrapper"] {{border-radius: 14px;}}
[data-testid="stMetricValue"] {{color: {NAVY};}}
/* components */
.ds-hero {{position: relative; overflow: hidden; border-radius: 18px; padding: 1.6rem 1.8rem; margin-bottom: 1rem;
          background: linear-gradient(120deg, {NAVY} 0%, {NAVY_2} 55%, #1D4E63 100%); color: #FFFFFF;
          box-shadow: 0 10px 30px rgba(16,36,58,.18);}}
.ds-hero .k {{text-transform: uppercase; letter-spacing: .12em; font-size: .78rem; color: #5EEAD4; font-weight: 700;}}
.ds-hero .t {{font-size: 2.1rem; font-weight: 750; line-height: 1.15; margin: .35rem 0 .45rem 0; max-width: 62%;}}
.ds-hero .s {{font-size: 1.05rem; color: #CBD5E1; max-width: 60%; line-height: 1.5;}}
.ds-hero .chips {{margin-top: .9rem;}}
.ds-hero .chip {{display: inline-block; padding: .25rem .7rem; border-radius: 999px; margin: 0 .4rem .4rem 0;
                background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18); font-size: .85rem;}}
.ds-hero svg {{position: absolute; right: 1.2rem; bottom: 0; height: 88%; max-width: 36%; opacity: .95;}}
.ds-note {{display: flex; gap: .7rem; align-items: flex-start; background: #FFFFFF; border: 1px solid {BORDER};
          border-left: 4px solid {TEAL}; border-radius: 10px; padding: .7rem .9rem; margin: .2rem 0 1rem 0;
          font-size: .92rem; color: {MUTED}; line-height: 1.5;}}
.ds-note b {{color: {INK};}}
.ds-grid {{display: grid; gap: .9rem; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin: .3rem 0 .6rem 0;}}
.ds-card {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; padding: 1rem 1.1rem;
          box-shadow: 0 1px 2px rgba(15,23,42,.04);}}
.ds-kpi {{border-top: 4px solid var(--accent);}}
.ds-kpi .i {{font-size: 1.35rem;}}
.ds-kpi .l {{font-size: .82rem; text-transform: uppercase; letter-spacing: .06em; color: {MUTED}; font-weight: 650; margin-top: .3rem;}}
.ds-kpi .v {{font-size: 1.9rem; font-weight: 750; color: {NAVY}; line-height: 1.15; margin-top: .15rem;}}
.ds-kpi .sub {{font-size: .88rem; color: {MUTED}; margin-top: .25rem; line-height: 1.4;}}
.ds-tag {{display: inline-block; font-size: .72rem; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
         padding: .12rem .5rem; border-radius: 6px; margin-top: .45rem; background: #EEF2F7; color: {MUTED};}}
.ds-section {{margin: 1.7rem 0 .5rem 0;}}
.ds-section .t {{font-size: 1.35rem; font-weight: 750; color: {NAVY};}}
.ds-section .s {{font-size: .95rem; color: {MUTED}; margin-top: .15rem;}}
.ds-use {{display: flex; gap: .8rem; align-items: flex-start;}}
.ds-use .i {{font-size: 1.6rem; line-height: 1; background: {TEAL_SOFT}; border-radius: 10px; padding: .45rem .5rem;}}
.ds-use .h {{font-weight: 700; color: {NAVY}; font-size: 1.02rem;}}
.ds-use .p {{color: {MUTED}; font-size: .92rem; line-height: 1.45; margin-top: .15rem;}}
.ds-policy {{border-left: 5px solid var(--accent);}}
.ds-policy .h {{font-weight: 750; color: {NAVY}; font-size: 1.05rem;}}
.ds-policy .badge {{display: inline-block; font-size: .72rem; font-weight: 700; padding: .12rem .5rem; border-radius: 6px;
                   background: {TEAL_SOFT}; color: #115E59; margin-left: .4rem; vertical-align: middle;}}
.ds-policy .row {{display: flex; justify-content: space-between; border-top: 1px dashed {BORDER}; padding: .4rem 0; font-size: .95rem;}}
.ds-policy .row span:last-child {{font-weight: 700; color: {NAVY};}}
.ds-decision {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 18px; overflow: hidden;
              box-shadow: 0 8px 24px rgba(16,36,58,.08); margin: .4rem 0 1rem 0;}}
.ds-decision .top {{background: linear-gradient(120deg, {NAVY} 0%, {NAVY_2} 100%); color: #FFFFFF; padding: 1.1rem 1.4rem;
                   display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));}}
.ds-decision .top .l {{font-size: .74rem; text-transform: uppercase; letter-spacing: .08em; color: #99F6E4; font-weight: 700;}}
.ds-decision .top .v {{font-size: 1.35rem; font-weight: 750; line-height: 1.25; margin-top: .2rem;}}
.ds-decision .top .sub {{font-size: .86rem; color: #CBD5E1; margin-top: .2rem;}}
.ds-decision .body {{padding: 1.1rem 1.4rem 1.2rem 1.4rem;}}
.ds-ind {{border-radius: 12px; padding: .8rem .9rem; background: var(--soft); border: 1px solid rgba(15,23,42,.06);}}
.ds-ind .l {{font-size: .78rem; text-transform: uppercase; letter-spacing: .07em; font-weight: 750; color: var(--strong);}}
.ds-ind .h {{font-size: 1.08rem; font-weight: 750; color: {INK}; margin-top: .25rem;}}
.ds-ind .p {{font-size: .9rem; color: {MUTED}; margin-top: .25rem; line-height: 1.45;}}
.ds-takeaway {{margin-top: 1rem; border-radius: 12px; padding: .9rem 1rem; background: #F0FDFA; border: 1px solid #99F6E4;}}
.ds-takeaway .l {{font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 750; color: #115E59;}}
.ds-takeaway .p {{font-size: 1.02rem; color: {INK}; margin-top: .3rem; line-height: 1.55;}}
.ds-pill {{display: inline-block; padding: .2rem .65rem; border-radius: 999px; margin: .15rem .3rem .15rem 0; font-size: .85rem;
          background: #EEF2F7; color: {INK}; border: 1px solid {BORDER};}}
@media (max-width: 760px) {{
  .ds-hero .t {{font-size: 1.55rem; max-width: 100%;}} .ds-hero .s {{max-width: 100%;}} .ds-hero svg {{display: none;}}
  .ds-kpi .v {{font-size: 1.5rem;}}
}}
</style>
"""

# Simple, original retail illustration (shelves, products and a basket) drawn in-line; no photographs or external files.
RETAIL_ART = """
<svg viewBox="0 0 360 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <g opacity=".9">
    <rect x="40" y="18" width="250" height="170" rx="10" fill="rgba(255,255,255,.05)" stroke="rgba(255,255,255,.18)"/>
    <rect x="52" y="70" width="226" height="5" rx="2" fill="rgba(255,255,255,.35)"/>
    <rect x="52" y="122" width="226" height="5" rx="2" fill="rgba(255,255,255,.35)"/>
    <rect x="52" y="174" width="226" height="5" rx="2" fill="rgba(255,255,255,.35)"/>
    <rect x="62" y="38" width="26" height="32" rx="4" fill="#5EEAD4"/><rect x="94" y="30" width="22" height="40" rx="4" fill="#99F6E4"/>
    <rect x="122" y="44" width="30" height="26" rx="4" fill="#2DD4BF"/><rect x="158" y="34" width="20" height="36" rx="4" fill="#FDE68A"/>
    <rect x="184" y="42" width="28" height="28" rx="4" fill="#5EEAD4"/><rect x="218" y="32" width="22" height="38" rx="4" fill="#A7F3D0"/>
    <rect x="246" y="46" width="24" height="24" rx="4" fill="#FCA5A5"/>
    <circle cx="74" cy="108" r="13" fill="#FDE68A"/><circle cx="102" cy="110" r="11" fill="#FCD34D"/>
    <rect x="122" y="90" width="34" height="32" rx="6" fill="#E0F2FE"/><rect x="162" y="96" width="30" height="26" rx="6" fill="#BAE6FD"/>
    <rect x="198" y="86" width="22" height="36" rx="5" fill="#99F6E4"/><rect x="226" y="92" width="40" height="30" rx="6" fill="#FECACA"/>
    <rect x="64" y="146" width="40" height="28" rx="6" fill="#A7F3D0"/><rect x="110" y="140" width="26" height="34" rx="5" fill="#5EEAD4"/>
    <rect x="142" y="150" width="44" height="24" rx="6" fill="#FDE68A"/><rect x="192" y="142" width="24" height="32" rx="5" fill="#BAE6FD"/>
    <rect x="222" y="148" width="46" height="26" rx="6" fill="#99F6E4"/>
  </g>
  <g transform="translate(262,104)">
    <path d="M6 18 L86 18 L76 70 Q74 78 66 78 L26 78 Q18 78 16 70 Z" fill="#0D9488" stroke="#5EEAD4" stroke-width="2.5"/>
    <path d="M24 18 Q46 -14 68 18" fill="none" stroke="#5EEAD4" stroke-width="4" stroke-linecap="round"/>
    <rect x="22" y="2" width="16" height="22" rx="3" fill="#FDE68A"/><rect x="42" y="-2" width="14" height="26" rx="3" fill="#FFFFFF"/>
    <circle cx="66" cy="12" r="9" fill="#FCA5A5"/>
    <line x1="30" y1="34" x2="30" y2="66" stroke="rgba(255,255,255,.35)" stroke-width="3"/>
    <line x1="46" y1="34" x2="46" y2="66" stroke="rgba(255,255,255,.35)" stroke-width="3"/>
    <line x1="62" y1="34" x2="62" y2="66" stroke="rgba(255,255,255,.35)" stroke-width="3"/>
  </g>
</svg>
"""


RETAIL_ART = "".join(line.strip() for line in RETAIL_ART.splitlines())  # one line: safe inside markdown HTML blocks


def apply() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _e(x) -> str:
    return html.escape(str(x))


def md(raw_html: str) -> None:
    st.markdown(raw_html, unsafe_allow_html=True)


def hero(kicker: str, title: str, subtitle: str, chips=(), art: bool = True) -> str:
    chip_html = "".join(f'<span class="chip">{_e(c)}</span>' for c in chips)
    return (f'<div class="ds-hero"><div class="k">{_e(kicker)}</div><div class="t">{_e(title)}</div>'
            f'<div class="s">{_e(subtitle)}</div><div class="chips">{chip_html}</div>{RETAIL_ART if art else ""}</div>')


def disclaimer() -> str:
    """Compact research disclaimer (same wording as ui.safety_banner)."""
    return ('<div class="ds-note"><span>ℹ️</span><div><b>Research demonstration on synthetic data.</b> Stock, orders and '
            'waste are simulated; recorded sales are not verified true demand. Every order shown is '
            '<b>HYPOTHETICAL_UNAPPROVED · NOT_EXECUTED</b> — nothing has been approved, ordered, priced or transferred. '
            'No policy is approved for production.</div></div>')


def section(title: str, subtitle: str = "") -> str:
    sub = f'<div class="s">{_e(subtitle)}</div>' if subtitle else ""
    return f'<div class="ds-section"><div class="t">{_e(title)}</div>{sub}</div>'


def kpi(icon: str, label: str, value: str, sub: str = "", accent: str = TEAL, tag: str = "") -> str:
    tag_html = f'<div class="ds-tag">{_e(tag)}</div>' if tag else ""
    sub_html = f'<div class="sub">{_e(sub)}</div>' if sub else ""
    return (f'<div class="ds-card ds-kpi" style="--accent:{accent}"><div class="i">{icon}</div><div class="l">{_e(label)}</div>'
            f'<div class="v">{_e(value)}</div>{sub_html}{tag_html}</div>')


def grid(cards) -> str:
    return '<div class="ds-grid">' + "".join(cards) + "</div>"


def use_case(icon: str, heading: str, text: str) -> str:
    return (f'<div class="ds-card ds-use"><div class="i">{icon}</div><div><div class="h">{_e(heading)}</div>'
            f'<div class="p">{_e(text)}</div></div></div>')


def policy_card(code: str, name: str, rows, accent: str, badge: str = "", tag: str = "") -> str:
    badge_html = f'<span class="badge">{_e(badge)}</span>' if badge else ""
    rows_html = "".join(f'<div class="row"><span>{_e(k)}</span><span>{_e(v)}</span></div>' for k, v in rows)
    tag_html = f'<div class="ds-tag">{_e(tag)}</div>' if tag else ""
    return (f'<div class="ds-card ds-policy" style="--accent:{accent}"><div class="h">{_e(code)} · {_e(name)}{badge_html}</div>'
            f'<div style="margin-top:.5rem">{rows_html}</div>{tag_html}</div>')


def indicator(label: str, headline: str, detail: str, level: str, icon: str) -> str:
    strong, soft = LEVELS[level]
    return (f'<div class="ds-ind" style="--strong:{strong};--soft:{soft}"><div class="l">{icon} {_e(label)}</div>'
            f'<div class="h">{_e(headline)}</div><div class="p">{_e(detail)}</div></div>')


def decision_card(top_items, indicators, takeaway: str, tags=(), followups=()) -> str:
    """top_items: [(label, value, sub)], indicators: [indicator html], followups: [(text, level)]."""
    top = "".join(f'<div><div class="l">{_e(l)}</div><div class="v">{_e(v)}</div><div class="sub">{_e(s)}</div></div>'
                  for l, v, s in top_items)
    tags_html = "".join(f'<span class="ds-pill">{_e(t)}</span>' for t in tags)
    follow_html = ""
    if followups:
        follow_html = ('<div class="ds-banner" style="--strong:#B45309;--soft:#FFFBEB;margin-top:.9rem"><span>📋</span><div>'
                       '<b>Operational follow-up</b> (separate from the formal policy review; creates no review case): '
                       + " · ".join(_e(t) for t, _ in followups) + "</div></div>")
    return (f'<div class="ds-decision"><div class="top">{top}</div><div class="body">'
            f'<div class="ds-grid">{"".join(indicators)}</div>{follow_html}'
            f'<div class="ds-takeaway"><div class="l">Manager\'s takeaway</div><div class="p">{_e(takeaway)}</div></div>'
            f'<div style="margin-top:.7rem">{tags_html}</div></div></div>')


def chart(c: alt.Chart, height: int = 300) -> alt.Chart:
    return (c.properties(height=height, background="#FFFFFF", padding={"left": 8, "right": 12, "top": 12, "bottom": 6})
            .configure_axis(labelFontSize=13, titleFontSize=13, titleColor=MUTED, labelColor=MUTED, gridColor="#E2E8F0",
                            domainColor="#CBD5E1", tickColor="#CBD5E1", titlePadding=10, labelFont=FONT, titleFont=FONT)
            .configure_legend(labelFontSize=13, titleFontSize=13, orient="top", labelColor=INK, labelFont=FONT, symbolSize=140)
            .configure_view(strokeWidth=0))


# ------------------------------------------------------------------------------------- additional components
CORAL, CORAL_SOFT = "#E25C4B", "#FDE7E3"
LEVELS["coral"] = (CORAL, CORAL_SOFT)

EXTRA_CSS = f"""
<style>
.ds-head {{position: relative; overflow: hidden; border-radius: 16px; padding: 1.3rem 1.6rem; margin-bottom: .9rem;
          background: linear-gradient(120deg, {NAVY} 0%, {NAVY_2} 60%, #1D4E63 100%); color: #FFFFFF;
          box-shadow: 0 8px 24px rgba(16,36,58,.16);}}
.ds-head .k {{text-transform: uppercase; letter-spacing: .12em; font-size: .76rem; color: #5EEAD4; font-weight: 700;}}
.ds-head .t {{font-size: 1.85rem; font-weight: 750; line-height: 1.15; margin: .3rem 0 .35rem 0; max-width: 70%;}}
.ds-head .s {{font-size: 1rem; color: #CBD5E1; max-width: 68%; line-height: 1.5;}}
.ds-head .chips {{margin-top: .7rem;}}
.ds-head .chip {{display: inline-block; padding: .22rem .65rem; border-radius: 999px; margin: 0 .35rem .35rem 0;
                background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18); font-size: .82rem;}}
.ds-head svg {{position: absolute; right: 1.4rem; top: 50%; transform: translateY(-50%); height: 78%; max-width: 24%;}}
.ds-banner {{display: flex; gap: .7rem; align-items: flex-start; border-radius: 12px; padding: .8rem 1rem; margin: .3rem 0 1rem 0;
            background: var(--soft); border: 1px solid var(--strong); color: {INK}; font-size: .95rem; line-height: 1.5;}}
.ds-banner b {{color: {INK};}}
.ds-chip {{display: inline-block; padding: .16rem .6rem; border-radius: 999px; font-size: .8rem; font-weight: 700;
          background: var(--soft); color: var(--strong); border: 1px solid var(--strong); white-space: nowrap;}}
.ds-table {{width: 100%; border-collapse: separate; border-spacing: 0; background: {CARD}; border: 1px solid {BORDER};
           border-radius: 12px; overflow: hidden; font-size: .93rem;}}
.ds-table th {{background: #F8FAFC; color: {MUTED}; text-align: left; font-weight: 700; font-size: .78rem; text-transform: uppercase;
              letter-spacing: .05em; padding: .7rem .9rem; border-bottom: 1px solid {BORDER}; white-space: nowrap;}}
.ds-table td {{padding: .7rem .9rem; border-bottom: 1px solid #F1F5F9; color: {INK}; vertical-align: top; line-height: 1.45;}}
.ds-table tr:nth-child(even) td {{background: #FBFCFE;}}
.ds-table tr:last-child td {{border-bottom: none;}}
.ds-table tr:hover td {{background: #F8FAFC;}}
.ds-wrap {{overflow-x: auto;}}
.ds-cards2 {{display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); margin: .3rem 0 .8rem 0;}}
@media (max-width: 640px) {{ .ds-cards2 {{grid-template-columns: 1fr;}} }}
.ds-more {{margin-top: .7rem; border-top: 1px solid #F1F5F9; padding-top: .5rem;}}
.ds-more summary {{cursor: pointer; font-weight: 700; color: {TEAL}; font-size: .9rem; list-style: none;}}
.ds-more summary::-webkit-details-marker {{display: none;}}
.ds-more summary::before {{content: '▸ ';}}
.ds-more[open] summary::before {{content: '▾ ';}}
.ds-key {{margin-top: .5rem; padding: .5rem .7rem; background: #F8FAFC; border-radius: 10px; font-size: .9rem; color: {INK};}}
.ds-gate {{display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; margin-top: .6rem;}}
@media (max-width: 640px) {{ .ds-gate {{grid-template-columns: 1fr;}} }}
.ds-gate > div {{border: 1px solid {BORDER}; border-radius: 10px; padding: .5rem .65rem; border-left: 4px solid var(--strong);}}
.ds-gate .t {{font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; font-weight: 750; color: {MUTED};}}
.ds-gate .v {{font-weight: 750; color: {NAVY}; font-size: .95rem; margin-top: .15rem;}}
.ds-gate .s {{color: {MUTED}; font-size: .84rem; margin-top: .1rem; line-height: 1.4;}}
.ds-num td:nth-child(n+4) {{font-variant-numeric: tabular-nums;}}
.ds-steps {{display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: .7rem; margin: .4rem 0 .8rem 0;}}
.ds-step {{position: relative; background: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; padding: .9rem 1rem;
          border-top: 4px solid var(--accent);}}
.ds-step .n {{display: inline-block; width: 1.8rem; height: 1.8rem; line-height: 1.8rem; text-align: center; border-radius: 50%;
             background: var(--accent); color: #FFFFFF; font-weight: 800; font-size: .95rem;}}
.ds-step .h {{font-weight: 750; color: {NAVY}; margin-top: .45rem; font-size: 1rem;}}
.ds-step .p {{color: {MUTED}; font-size: .88rem; margin-top: .2rem; line-height: 1.45;}}
.ds-evid {{border-left: 4px solid var(--strong);}}
.ds-evid .h {{font-weight: 700; color: {NAVY}; font-size: .98rem;}}
.ds-evid .p {{color: {MUTED}; font-size: .88rem; margin-top: .3rem; line-height: 1.45;}}
.ds-road .h {{font-weight: 750; color: {NAVY}; font-size: 1.15rem; margin: .3rem 0 .5rem 0;}}
.ds-road .lab {{font-size: .74rem; text-transform: uppercase; letter-spacing: .07em; font-weight: 750; color: {MUTED}; margin-top: .7rem;}}
.ds-road .p {{color: {INK}; font-size: .92rem; line-height: 1.5; margin-top: .15rem;}}
.ds-road ul {{margin: .2rem 0 0 1.1rem; padding: 0; color: {INK}; font-size: .9rem;}}
.ds-detail {{background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px; padding: 1.1rem 1.3rem;
            box-shadow: 0 6px 20px rgba(16,36,58,.07);}}
.ds-detail .h {{font-size: 1.35rem; font-weight: 750; color: {NAVY};}}
.ds-sub {{font-size: .86rem; color: {MUTED};}}
.ds-panel {{border-radius: 12px; padding: .85rem 1rem; margin-top: .7rem; background: #F0FDFA; border: 1px solid #99F6E4;}}
.ds-panel .l {{font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; font-weight: 750; color: #115E59;}}
.ds-panel .p {{font-size: 1rem; color: {INK}; margin-top: .3rem; line-height: 1.55;}}
.ds-delta-good {{color: {EMERALD}; font-weight: 700;}} .ds-delta-bad {{color: {CORAL}; font-weight: 700;}}
.ds-delta-neutral {{color: {MUTED}; font-weight: 700;}}
@media (max-width: 760px) {{ .ds-head .t {{font-size: 1.45rem; max-width: 100%;}} .ds-head .s {{max-width: 100%;}}
                            .ds-head svg {{display: none;}} }}
</style>
"""


def _svg(body: str) -> str:
    return '<svg viewBox="0 0 120 120" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' + body + "</svg>"


ART = {
    "chart": _svg('<rect x="10" y="10" width="100" height="100" rx="18" fill="rgba(255,255,255,.07)"/>'
                  '<rect x="26" y="62" width="14" height="32" rx="3" fill="#94A3B8"/>'
                  '<rect x="48" y="44" width="14" height="50" rx="3" fill="#60A5FA"/>'
                  '<rect x="70" y="30" width="14" height="64" rx="3" fill="#2DD4BF"/>'
                  '<path d="M24 48 L52 34 L76 22 L96 14" stroke="#FDE68A" stroke-width="3" fill="none" stroke-linecap="round"/>'),
    "queue": _svg('<rect x="22" y="14" width="76" height="92" rx="10" fill="rgba(255,255,255,.08)" stroke="#5EEAD4" stroke-width="2"/>'
                  '<rect x="44" y="8" width="32" height="14" rx="5" fill="#2DD4BF"/>'
                  '<circle cx="38" cy="44" r="5" fill="#FDE68A"/><rect x="50" y="40" width="36" height="7" rx="3" fill="#CBD5E1"/>'
                  '<circle cx="38" cy="64" r="5" fill="#FCA5A5"/><rect x="50" y="60" width="36" height="7" rx="3" fill="#CBD5E1"/>'
                  '<circle cx="38" cy="84" r="5" fill="#5EEAD4"/><rect x="50" y="80" width="36" height="7" rx="3" fill="#CBD5E1"/>'),
    "clock": _svg('<circle cx="60" cy="60" r="44" fill="rgba(255,255,255,.07)" stroke="#5EEAD4" stroke-width="3"/>'
                  '<path d="M60 30 L60 60 L80 72" stroke="#FDE68A" stroke-width="5" fill="none" stroke-linecap="round"/>'
                  '<rect x="78" y="78" width="30" height="24" rx="5" fill="#FCA5A5"/>'
                  '<rect x="84" y="84" width="18" height="4" rx="2" fill="#FFFFFF"/>'),
    "tag": _svg('<path d="M18 58 L58 18 L100 18 L100 60 L60 100 Z" fill="rgba(45,212,191,.85)" stroke="#5EEAD4" stroke-width="2"/>'
                '<circle cx="84" cy="34" r="8" fill="#10243A"/>'
                '<path d="M44 70 L70 44" stroke="#FFFFFF" stroke-width="5" stroke-linecap="round"/>'
                '<circle cx="46" cy="50" r="6" fill="#FFFFFF"/><circle cx="68" cy="66" r="6" fill="#FFFFFF"/>'),
    "coin": _svg('<ellipse cx="60" cy="88" rx="38" ry="12" fill="#B45309"/><ellipse cx="60" cy="80" rx="38" ry="12" fill="#FBBF24"/>'
                 '<ellipse cx="60" cy="62" rx="38" ry="12" fill="#B45309"/><ellipse cx="60" cy="54" rx="38" ry="12" fill="#FDE68A"/>'
                 '<path d="M20 36 L44 24 L68 30 L100 14" stroke="#5EEAD4" stroke-width="4" fill="none" stroke-linecap="round"/>'),
    "road": _svg('<path d="M20 100 C 40 70, 80 80, 100 20" stroke="#5EEAD4" stroke-width="5" fill="none" stroke-dasharray="6 6"/>'
                 '<circle cx="20" cy="100" r="9" fill="#16A34A"/><circle cx="58" cy="76" r="9" fill="#FBBF24"/>'
                 '<circle cx="100" cy="20" r="9" fill="#94A3B8"/>'),
}


def apply_all() -> None:
    st.markdown(CSS + EXTRA_CSS, unsafe_allow_html=True)


def head(kicker: str, title: str, subtitle: str, chips=(), art: str = "") -> str:
    chip_html = "".join(f'<span class="chip">{_e(c)}</span>' for c in chips)
    return (f'<div class="ds-head"><div class="k">{_e(kicker)}</div><div class="t">{_e(title)}</div>'
            f'<div class="s">{_e(subtitle)}</div><div class="chips">{chip_html}</div>{ART.get(art, "")}</div>')


def banner(text_html: str, level: str = "info", icon: str = "ℹ️") -> str:
    """Notice strip; `text_html` may contain <b> markup and must already be safe."""
    strong, soft = LEVELS[level]
    return f'<div class="ds-banner" style="--strong:{strong};--soft:{soft}"><span>{icon}</span><div>{text_html}</div></div>'


def chip(text: str, level: str = "neutral") -> str:
    strong, soft = LEVELS[level]
    return f'<span class="ds-chip" style="--strong:{strong};--soft:{soft}">{_e(text)}</span>'


def table(columns, rows, html_cols=()) -> str:
    """Readable HTML table. Cells are escaped unless their column is listed in `html_cols` (pre-built chips)."""
    head_html = "".join(f"<th>{_e(c)}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{v if c in html_cols else _e(v)}</td>" for c, v in zip(columns, r)) + "</tr>"
                   for r in rows)
    return f'<div class="ds-wrap"><table class="ds-table"><thead><tr>{head_html}</tr></thead><tbody>{body}</tbody></table></div>'


def steps(items) -> str:
    """items: [(number, heading, text, accent)]"""
    return '<div class="ds-steps">' + "".join(
        f'<div class="ds-step" style="--accent:{a}"><span class="n">{_e(n)}</span><div class="h">{_e(h)}</div>'
        f'<div class="p">{_e(p)}</div></div>' for n, h, p, a in items) + "</div>"


def evidence_card(icon: str, heading: str, status: str, text: str, level: str = "coral") -> str:
    strong, _ = LEVELS[level]
    return (f'<div class="ds-card ds-evid" style="--strong:{strong}"><div class="h">{icon} {_e(heading)}</div>'
            f'<div style="margin-top:.35rem">{chip(status, level)}</div><div class="p">{_e(text)}</div></div>')


def roadmap_card(icon: str, heading: str, status: str, capability: str, missing, approval: str) -> str:
    items = "".join(f"<li>{_e(m)}</li>" for m in missing)
    return (f'<div class="ds-card ds-road"><div style="font-size:1.6rem">{icon}</div><div class="h">{_e(heading)}</div>'
            f'{chip(status, "coral")}<div class="lab">Intended capability</div><div class="p">{_e(capability)}</div>'
            f'<div class="lab">Current status</div><div class="p">{_e(status)} — nothing on this card is functional.</div>'
            f'<div class="lab">Missing requirements</div><ul>{items}</ul>'
            f'<div class="lab">Human approval requirements</div><div class="p">{_e(approval)}</div></div>')


def delta(pct: float, good_when_lower) -> str:
    """Coloured percentage difference; `good_when_lower=None` keeps it neutral (e.g. ordering volume)."""
    if good_when_lower is None or abs(pct) < 0.005:
        cls = "ds-delta-neutral"
    else:
        cls = "ds-delta-good" if (pct < 0) == good_when_lower else "ds-delta-bad"
    return f'<span class="{cls}">{pct:+.2f}%</span>'


def policy_bars(df, value: str, title: str) -> alt.Chart:
    """One measure per chart; bar per policy in fixed identity colours with direct value labels."""
    order = ["P0 baseline", "P1 original", "P2 expiry-aware"]
    df = df.assign(policy_label=df["policy_id"].map(dict(zip(["P0", "P1", "P2"], order))))
    base = alt.Chart(df).encode(
        x=alt.X("policy_label:N", title=None, sort=order, axis=alt.Axis(labelAngle=0, labelFontSize=13)),
        y=alt.Y(f"{value}:Q", title=None, axis=alt.Axis(format="~s")),
        color=alt.Color("policy_label:N", scale=alt.Scale(domain=order, range=[POLICY_ACCENT[p] for p in ("P0", "P1", "P2")]),
                        legend=None),
        tooltip=[alt.Tooltip("policy_label:N", title="Policy"), alt.Tooltip(f"{value}:Q", title=title, format=",")])
    bars = base.mark_bar(size=52, cornerRadiusTopLeft=6, cornerRadiusTopRight=6)
    text = base.mark_text(dy=-10, fontSize=13, fontWeight="bold", color=INK).encode(text=alt.Text(f"{value}:Q", format=","))
    return chart((bars + text).properties(title=alt.TitleParams(title, fontSize=15, anchor="start", color=NAVY, font=FONT)), 260)
