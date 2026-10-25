"""Dashboard MVP smoke tests: every page renders without exceptions on the protected outputs, the data layer is
read-only, and nothing on screen claims approval or execution."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "dashboard"
sys.path.insert(0, str(APP))

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import dashboard_data as D  # noqa: E402
import labels as L  # noqa: E402
from dpe import config  # noqa: E402

PAGES = ["Home.py", "pages/1_Product_investigation.py", "pages/2_Policy_comparison.py", "pages/3_Review_queue.py",
         "pages/4_Waste_risk.py", "pages/5_Markdown_review.py", "pages/6_Discount_decision_lab.py",
         "pages/7_Dynamic_pricing_lab.py", "pages/8_Waste_intervention_lab.py", "pages/9_Future_features.py"]


def _run(page, **state):
    at = AppTest.from_file(str(APP / page), default_timeout=240)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _text(at) -> str:
    parts = [m.value for m in at.markdown] + [m.value for m in at.info] + [m.value for m in at.warning] + \
            [m.value for m in at.success] + [m.value for m in at.caption] + [m.value for m in at.title] +             [m.value for m in at.subheader] + [m.value for m in at.header]
    return " ".join(str(p) for p in parts)


def _kpis(at) -> dict:
    """Label -> value of the design-system KPI cards (HTML, not st.metric)."""
    import html
    import re

    text = " ".join(str(m.value) for m in at.markdown)
    return {html.unescape(l): html.unescape(v) for l, v in
            re.findall(r'<div class="l">(.*?)</div><div class="v">(.*?)</div>', text)}


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders(page):
    at = _run(page)
    text = _text(at)
    if page != "pages/9_Future_features.py":
        assert "HYPOTHETICAL_UNAPPROVED" in text and "No policy is approved for production" in text


def test_overview_shows_counts_forecasts_and_policy_totals():
    at = _run("Home.py")
    text = _text(at)
    for label, value in (("Stores", "15"), ("Products", "48"), ("Store × product series", "720"),
                         ("Product categories", "4")):
        assert f'<div class="l">{label}</div><div class="v">{value}</div>' in text
    assert "25.92% WAPE" in text and "29.41% WAPE" in text and "1.97 points better" in text
    t = D.comparison_table().set_index(["scenario_id", "policy_id"])
    for p in D.POLICIES:
        assert f"<span>Units ordered</span><span>{int(t.loc[('SC1', p), 'ordered_units']):,}</span>" in text
    assert "What this system helps a retail manager decide" in text
    assert "SIMULATED results (synthetic replay) — not observed results" in text
    assert "not approved for production" in text and len(at.button) == 0


@pytest.mark.parametrize("scenario,policy", [("SC1", "P2"), ("SC3", "P1"), ("SF75", "P0")])
def test_product_page_for_each_policy(scenario, policy):
    at = _run("pages/1_Product_investigation.py", scenario=scenario, policy=policy)
    assert "Units gone out of date" in _text(at)
    headers = [h.value for h in at.header]
    assert headers.index("Decision summary") < headers.index("Simulated stock flow")  # summary above the technical tables
    text = _text(at)
    assert any(e.label.startswith("Why this recommendation") for e in at.expander)
    assert "Human review" in text and "Supplier delivery schedule" in text
    assert "Hypothetical proposal — not approved, not ordered" in text
    assert len(at.button) == 0


def test_policy_comparison_reports_frozen_outcome():
    at = _run("pages/2_Policy_comparison.py")
    text = _text(at)
    assert "not approved for production" in text and "exploratory" in text
    assert "12 of 12" in text


@pytest.mark.parametrize("policy", ["P1", "P2"])
def test_review_queue_is_read_only(policy):
    at = _run("pages/3_Review_queue.py", policy=policy)
    assert len(at.button) == 0  # no approve / reject / order actions exist
    assert "PENDING_REVIEW" in _text(at)


def test_saved_cases_and_recommendations_are_never_approved():
    for sc in D.SCENARIOS:
        c = D.review_cases(sc, "P2")
        assert set(c.review_status) == {"PENDING_REVIEW"} and c.approval_event_id.isna().all()
        r = D.recommendations(sc)
        assert set(r.status) == {"HYPOTHETICAL_UNAPPROVED"} and set(r.execution_status) == {"NOT_EXECUTED"}
        assert r.approval_event_id.isna().all()


def test_dashboard_code_is_read_only():
    sources = " ".join(p.read_text(encoding="utf-8") for p in APP.rglob("*.py"))
    for forbidden in ("to_csv", "write_text", "open(", "sqlite", "airtable", "requests.", "save_table", "save_json",
                      "simulate(", "new_run_dir", "st.button"):
        assert forbidden not in sources, forbidden
    assert str(D.COMPARISON_DIR).endswith(config.POLICY_COMPARISON_RUN_ID)


def test_protected_outputs_unchanged_after_rendering(protected_registry):
    for page in PAGES:
        _run(page)
    bad = [rel for rel, digest in protected_registry.items()
           if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    assert not bad


def test_every_code_in_the_saved_outputs_has_a_plain_english_label():
    sys.path.insert(0, str(ROOT / "src"))
    from dpe.decision import recommendations as REC

    codes = set(REC.REASONS) | set(REC.CATEGORIES)
    for sc in D.SCENARIOS:
        for p in D.POLICIES:
            d = D.decisions(sc, p)
            for f in d["flags"].dropna():
                codes.update(D.parse_list(f))
            c = D.review_cases(sc, p)
            for col in ("reasons_list", "warnings_list"):
                for x in c[col]:
                    codes.update(x)
            if p == "P2":
                codes.update(d.supplier_arrangement_status.dropna())
                codes.update(d.pre_delivery_position.dropna())
            codes.update(d.action_status.dropna())
    missing = sorted(x for x in codes if x not in L.ALL_CODES)
    assert not missing, missing


def test_explanations_are_humanised_without_losing_the_codes():
    r = D.recommendations("SC1")
    text = r.explanation.iloc[0]
    human = L.humanize(text)
    assert not any(code in human for code in L.REASONS if code in text)
    assert text == r.explanation.iloc[0]  # the saved output itself is untouched
    assert L.day_label(232) == "Mon, week 34" and L.day_label(234) == "Wed, week 34"


def test_waste_risk_page_is_advisory_and_labelled():
    at = _run("pages/4_Waste_risk.py", scenario="SC1", policy="P2")
    metrics = _kpis(at)
    assert metrics["High expiry risk"] == "37" and metrics["Moderate expiry risk"] == "97"
    assert metrics["Insufficient information"] == "0"
    text = _text(at)
    assert "Advisory only" in text and "not directly comparable" in text
    assert "RECORDED" in text and "SIMULATED" in text and "context only" in text
    assert len(at.button) == 0
    for word in ("Approve", "Apply discount", "Place order"):
        assert word not in text


def test_product_page_shows_waste_risk_summary():
    at = _run("pages/1_Product_investigation.py", scenario="SC1", policy="P2")
    assert "Waste risk (advisory)" in _text(at)


def test_waste_risk_page_states_which_policy_it_shows():
    for policy in ("P1", "P2"):
        at = _run("pages/4_Waste_risk.py", scenario="SC3", policy=policy)
        text = _text(at)
        assert f"Results shown for inventory policy {policy}" in text and "other policies give different results" in text


def test_future_features_separates_completed_from_unbuilt():
    at = _run("pages/9_Future_features.py")
    text = _text(at)
    assert "Waste-Risk Intelligence" in text and "Completed — Stage 6B" in text
    assert "Executable waste interventions" in text and "None is built" in text and "Completed — Phase 3" in text
    assert "5–25%" not in text  # no discount sizes are implied
    assert text.count("NOT BUILT") >= 1 and "Completed — Phase 1" in text and "Completed — Phase 2" in text


def test_markdown_review_page_is_read_only_eligibility():
    at = _run("pages/5_Markdown_review.py", scenario="SC1", policy="P2")
    m = _kpis(at)
    assert (m["Eligible for markdown review"], m["Blocked"], m["Insufficient information"]) == ("91", "42", "1")
    assert m["Discount status"] == "No discount proposed"
    text = _text(at)
    assert "Showing inventory policy <b>P2" in text and "Eligibility only" in text
    assert "No discount size is proposed" in text and "documented only" in text
    assert len(at.button) == 0
    import re
    assert not re.search(r"\b\d{1,2}% (off|discount)\b", text)  # no discount sizes anywhere
    for word in ("Approve", "Apply discount", "New price:"):
        assert word not in text


def test_markdown_links_and_future_features():
    at = _run("pages/4_Waste_risk.py", scenario="SC1", policy="P2")
    assert "Open Markdown review" in _text(at)
    at = _run("pages/1_Product_investigation.py", scenario="SC1", policy="P2")
    assert "Markdown review (eligibility only)" in _text(at)
    at = _run("pages/9_Future_features.py")
    text = _text(at)
    assert "Markdown review eligibility" in text and "Completed — Stage 7B" in text
    assert "Numerical discount recommendations" in text and "Dynamic pricing" in text


@pytest.mark.parametrize("scenario,policy", [("SC1", "P2"), ("SC3", "P2"), ("SC1", "P1"), ("SF75", "P0")])
def test_markdown_page_counts_and_explanation_follow_the_selection(scenario, policy):
    from dpe.decision import markdown_eligibility as M

    at = _run("pages/5_Markdown_review.py", scenario=scenario, policy=policy)
    expected = D.markdown_review(scenario, policy).eligibility.value_counts()
    shown = _kpis(at)
    for cls in M.CLASSES:
        assert shown[M.CLASS_LABELS[cls]] == f"{expected.get(cls, 0):,}"
    text = _text(at)
    assert f"Showing inventory policy <b>{policy}" in text and f"scenario <b>{scenario}" in text
    if expected.drop("NOT_CONSIDERED", errors="ignore").sum():
        assert f"Policy {policy} · scenario {scenario}" in text  # the selected-line card uses the same selection
        for heading in ("Why this line was flagged", "What the manager should investigate",
                        "Why a numerical discount cannot be recommended yet"):
            assert heading in text
    assert "HYPOTHETICAL_UNAPPROVED" in text and "No policy is approved for production" in text
    assert len(at.button) == 0


@pytest.mark.parametrize("scenario,policy", [("SC1", "P2"), ("SC3", "P1"), ("SC2", "P0")])
def test_discount_decision_lab_is_labelled_and_read_only(scenario, policy):
    from dpe.decision import discount_recommendation as R

    at = _run("pages/6_Discount_decision_lab.py", scenario=scenario, policy=policy)
    s = R.summary(D.discount_recommendations(scenario, policy)[0])
    m = _kpis(at)
    assert m["Lines assessed"] == f"{s['assessed']:,}" and m["Simulated research recommendations"] == f"{s[R.RECOMMEND]:,}"
    assert m["No recommendation — evidence"] == f"{s[R.EVIDENCE]:,}"
    text = _text(at)
    assert R.LABEL in text and f"inventory policy {policy}" in text and "non-causal association" in text
    assert "HYPOTHETICAL_UNAPPROVED" in text and "No policy is approved for production" in text
    assert "Nothing is proposed, approved, published or executed" in text and len(at.button) == 0
    for word in ("Recommended:", "optimal", "best option", "uplift", "Approve", "will increase sales"):
        assert word not in text


def test_discount_decision_lab_shows_the_ranked_option_and_its_evidence():
    from dpe.decision import discount_recommendation as R

    at = _run("pages/6_Discount_decision_lab.py", scenario="SC1", policy="P2")
    lines, _ = D.discount_recommendations("SC1", "P2")
    first = lines[lines.recommendation_status == R.RECOMMEND].sort_values("at_risk_units", ascending=False).iloc[0]
    df = at.dataframe[0].value
    assert list(df.columns[:5]) == ["Markdown", "Selling price", "Margin %", "Rules check", "Expected change vs full price*"]
    ranked = df[df["Result"] == "🧪 Ranks first (simulated)"]
    assert list(ranked["Markdown"]) == [f"{int(first.recommended_markdown_pct)}%"]
    text = _text(at)
    assert first.Product_Name in text and f"{int(first.recommended_markdown_pct)}% markdown ranks first" in text
    for label in ("Recorded / forecast", "Simulation outputs", "Assumptions", "Hypothetical decisions",
                  "Evidence quality", "In plain English", "Simulated expiry exposure"):
        assert label in text, label
    assert any(e.label.startswith("Technical calculations") for e in at.expander)


def test_markdown_review_links_to_pricing_demo():
    at = _run("pages/5_Markdown_review.py", scenario="SC1", policy="P2")
    text = _text(at)
    assert "Discount Decision Lab" in text and "Markdown Opportunity Review" in text
    for stage in ("Eligible for investigation", "Discount proposal — NOT BUILT", "Human authorisation — NOT BUILT",
                  "Store execution and audit — NOT BUILT", "Before a discount can be recommended"):
        assert stage in text, stage


def test_review_queue_separates_formal_cases_from_standing_items():
    at = _run("pages/3_Review_queue.py", scenario="SC1", policy="P2")
    m = _kpis(at)
    c = D.review_cases("SC1", "P2").case_type.value_counts()
    assert m["Must be escalated"] == f"{c.get('MANDATORY_ESCALATION', 0):,}"
    assert m["Standing supplier items"] == f"{len(D.standing_cases('SC1')):,}"
    assert "Standing supplier-confirmation items" in _text(at)



@pytest.mark.parametrize("scenario,policy", [("SC1", "P2"), ("SC3", "P1")])
def test_product_decision_card_matches_saved_decision(scenario, policy):
    at = _run("pages/1_Product_investigation.py", scenario=scenario, policy=policy)
    text = _text(at)
    d = D.decisions(scenario, policy)
    first = d[(d.Store_ID == 500) & (d.Product_ID == 1000)].sort_values("origin_week").iloc[0]
    assert f"{int(first.ordered_units):,} units" in text and f"Week {first.target_week}" in text
    for label in ("Hypothetical order", "Human review", "Shortage risk", "Expiry risk", "Supplier delivery schedule",
                  "Manager's takeaway"):
        assert label in text, label
    assert "Nothing has been ordered or approved" in text and "Assumed, not confirmed by the supplier" in text
    assert f"Policy {policy}" in text and f"Scenario {scenario}" in text and len(at.button) == 0


def test_design_system_uses_the_approved_palette():
    import theme as T

    assert (T.NAVY, T.TEAL, T.EMERALD, T.BG) == ("#10243A", "#0D9488", "#16A34A", "#F1F5F9")
    assert "<img" not in T.RETAIL_ART and "http" not in T.RETAIL_ART.replace("http://www.w3.org/2000/svg", "")


@pytest.mark.parametrize("scenario,truth", [("SC1", "R2_CENTRAL"), ("SC3", "R0_NO_RESPONSE"), ("SC2", "R3_HIGH")])
def test_dynamic_pricing_lab_reports_the_saved_evaluation(scenario, truth):
    at = _run("pages/7_Dynamic_pricing_lab.py", scenario=scenario, **{f"dp_truth_{scenario}": truth})
    row = D.dp_comparison(D.PREFERRED_RULE).query("scenario_id == @scenario and true_response == @truth").iloc[0]
    m = _kpis(at)
    assert m["Hypothetical markdowns"] == f"{int(row.markdown_events):,}"
    text = _text(at)
    for label in ("SIMULATED RESEARCH — NOT VALIDATED FOR LIVE USE", "Assumed versus actual simulated customer response",
                  "Simulated benefits", "Simulated harms", "Evaluation results", "Evidence quality: LOW",
                  "No response (stress test)", "HYPOTHETICAL_UNAPPROVED", "No policy is approved for production"):
        assert label in text, label
    assert len(at.button) == 0
    for word in ("Approve", "Execute", "Publish", "proven", "guarantee"):
        assert word not in text, word
    if int(row.markdown_events):
        assert "Decision history" in text and "SIMULATED_AS_IF_APPROVED" in text


def test_dynamic_pricing_run_is_new_and_versioned():
    man = D.dp_manifest()
    assert man["run_id"] == D.DYNAMIC_PRICING_RUN_ID and man["run_id"].endswith("_dynamic_pricing_evaluation")
    assert man["simulator_version"] == "1.3" and man["protected_baseline_run"] == "20261023-131711_policy_comparison"
    assert "NOT_EXECUTED" in man["status"]


@pytest.mark.parametrize("rule", ["ORIGINAL", "A1"])
def test_dynamic_pricing_lab_rule_selector_names_the_source_run(rule):
    at = _run("pages/7_Dynamic_pricing_lab.py", scenario="SC3", dp_rule=rule, dp_truth_SC3="R2_CENTRAL")
    text = _text(at)
    run_id = D.DYNAMIC_PRICING_RUNS[rule]
    assert f"Results on this page come from research run <b>{run_id}</b>" in text
    row = D.dp_comparison(rule).query("scenario_id == 'SC3' and true_response == 'R2_CENTRAL'").iloc[0]
    assert _kpis(at)["Hypothetical markdowns"] == f"{int(row.markdown_events):,}"
    assert "Original Phase 2 rule versus A1 cooldown rule" in text and D.DYNAMIC_PRICING_RUN_ID in text
    assert D.DYNAMIC_PRICING_A1_RUN_ID in text and "Preregistered A1 preference test" in text
    assert len(at.button) == 0 and "Approve" not in text


def test_dynamic_pricing_lab_defaults_to_the_preferred_research_rule():
    at = _run("pages/7_Dynamic_pricing_lab.py", scenario="SC3")
    assert at.radio(key="dp_rule").value == "A1" and D.PREFERRED_RULE == "A1"
    text = _text(at)
    assert "A1 is the PREFERRED RESEARCH RULE — NOT PRODUCTION APPROVED" in text
    assert f"Results on this page come from research run <b>{D.DYNAMIC_PRICING_A1_RUN_ID}</b>" in text
    assert "ORIGINAL" in at.radio(key="dp_rule").options or "Original Phase 2 rule (comparison)" in at.radio(key="dp_rule").options
    dec = D.dp_rule_decision()
    assert dec["status"] == "PREFERRED_RESEARCH_RULE_NOT_PRODUCTION_APPROVED" and dec["preferred_rule"]["id"] == "A1"
    assert dec["retained_comparison"]["run"] == D.DYNAMIC_PRICING_RUN_ID and "production use" in dec["not_approved"]
    log = D.dp_decisions("SC3", "R2_CENTRAL", "A1")
    assert set(log["approval_status"]) == {"HYPOTHETICAL_UNAPPROVED"} and set(log["execution_status"]) == {"NOT_EXECUTED"}
    assert log["approval_event_id"].isna().all() and len(at.button) == 0


@pytest.mark.parametrize("scenario", ["SC1", "SC2", "SC3", "SF75"])
def test_waste_intervention_lab_is_advisory_and_complete(scenario):
    from dpe.decision import waste_interventions as WI

    at = _run("pages/8_Waste_intervention_lab.py", scenario=scenario)
    lines, opts = D.waste_interventions(scenario)
    s = WI.summarise(lines, opts)
    m = _kpis(at)
    assert m["Lines with stock at risk"] == f"{s['INVESTIGATIONS_SUGGESTED']:,}"
    assert m["Units projected to expire"] == f"{s['units_at_risk']:,.0f}"
    text = _text(at)
    for label in ("Advisory — investigation support only", "INVESTIGATE ONLY", "Manager summary", "Stock already in the store",
                  "The next replenishment order", "Changing the next order cannot save stock already approaching expiry",
                  "Investigation queue", "Weekly history for this product", "Evidence for", "Missing information",
                  "Human checks required", "not a saving", "HYPOTHETICAL_UNAPPROVED", "No policy is approved for production"):
        assert label in text, label
    for card in ("A · Review the next replenishment order", "B · Investigate a transfer to another store",
                 "C · Investigate a markdown", "D · Investigate donation or alternative disposal",
                 "E · No intervention / further investigation"):
        assert card in text, card
    assert len(at.button) == 0
    for word in ("Approve", "Execute", "Place order", "Transfer now", "Donate now", "will save", "optimal intervention"):
        assert word not in text, word


def test_waste_intervention_lab_explains_priority_and_separates_eligibility_from_evidence():
    at = _run("pages/8_Waste_intervention_lab.py", scenario="SC1")
    text = _text(at)
    for label in ("Why this investigation comes first", "not a judgement that it is the best commercial action",
                  "Step 1 · Markdown eligibility", "Step 2 · Evidence for a markdown investigation", "Key point:",
                  "<details class=\"ds-more\">", "Sort by"):
        assert label in text or label in str([s.label for s in at.selectbox]), label
    assert len(at.button) == 0
