"""Stage 7B: markdown review eligibility (read-only, state 1 of 4) and assumption set v4 (DRAFT)."""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v3 as C
from dpe.decision import assumptions_v4 as V
from dpe.decision import markdown_eligibility as M

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dashboard"))
import dashboard_data as D  # noqa: E402

ORDER = ["CHRISTMAS_ESCALATION", "SHORTAGE_BEFORE_DELIVERY", "ALREADY_ON_PROMOTION", "PRODUCT_EXCLUDED", "TOO_LATE_TO_ACT"]
V4_CONTENT_SHA256 = "bde13a20df120ea4e452bfb36f45ee6bb24581efa191216b403f46a2c076a1a5"


@pytest.fixture(scope="module")
def params():
    return V.markdown_values(V.load())


@pytest.fixture(scope="module")
def saved():
    keep = lambda df, s="Store_ID": df[df[s].isin([504, 505, 510])].reset_index(drop=True)  # noqa: E731
    return {"waste": keep(D.waste_risk("SC1", "P2")), "decisions": keep(D.decisions("SC1", "P2")),
            "contract": keep(D.contract(), "store_id"), "panel": keep(D.recorded_prices())}


@pytest.fixture(scope="module")
def assessed(saved, params):
    return M.assess(saved["waste"], saved["decisions"], saved["contract"], saved["panel"], params)


# ----------------------------------------------------------------------------------------------- v4
def test_v4_is_a_valid_draft_and_v1_v3_are_unchanged():
    doc = V.load()
    s = V.validate(doc, C.load())
    assert s["assumption_set_id"] == "AS-2026-10-23-v4" and s["status"] == "DRAFT" and s["parameters"] == 53
    assert A.content_sha256(doc) == V4_CONTENT_SHA256 and doc["production_use"] is False
    expected = config.load_expected_checksums()
    assert hashlib.sha256(A.DEFAULT_FILE.read_bytes()).hexdigest() == "42116041ee61d265fc2756726de61b57b271513d9d095d914116208b4d2ccd50"
    for f in ("assumption_set_v2.json", "assumption_set_v3.json"):  # registered in docs/CHECKSUMS.sha256
        p = A.ASSUMPTION_DIR / f
        assert expected[f"config/assumptions/{f}"] == hashlib.sha256(p.read_bytes()).hexdigest()
    v3 = {p["key"]: p["value"] for p in C.load()["parameters"]}
    v4 = {p["key"]: p["value"] for p in doc["parameters"]}
    assert all(v4[k] == v for k, v in v3.items())
    g = V.markdown_values(doc)
    assert g["markdown_product_exclusions"] == [] and g["markdown_blocker_order"] == ORDER
    assert g["markdown_numerical_discounts_enabled"] is False and g["markdown_approval_functionality_enabled"] is False
    assert g["markdown_open_inventory_case_effect"] == "WARNING_ONLY"
    assert "not implemented" in doc["approval_and_audit_requirements"]["status"]


@pytest.mark.parametrize("mutate,message", [
    (lambda d: _p(d, "markdown_numerical_discounts_enabled").update(value=True), "allowed set"),
    (lambda d: _p(d, "markdown_approval_functionality_enabled").update(value=True), "allowed set"),
    (lambda d: _p(d, "markdown_open_inventory_case_effect").update(value="BLOCKER"), "allowed set"),
    (lambda d: _p(d, "waste_risk_high_pct_of_p50").update(value=30), "changed"),
    (lambda d: d.update(production_use=True), "production_use"),
    (lambda d: d["approval_and_audit_requirements"].update(status="IMPLEMENTED"), "not implemented"),
])
def test_invalid_v4_files_are_rejected(mutate, message):
    bad = copy.deepcopy(V.load())
    mutate(bad)
    bad["approval"]["content_sha256"] = A.content_sha256(bad)
    with pytest.raises(A.AssumptionError, match=message):
        A.validate(bad)
        V.validate(bad, C.load())


def _p(doc, key):
    return next(p for p in doc["parameters"] if p["key"] == key)


# ------------------------------------------------------------------------------------------- precedence
@pytest.mark.parametrize("cat,batch,blockers,expected", [
    ("LOW", True, [], "NOT_CONSIDERED"),
    ("LOW", True, ["CHRISTMAS_ESCALATION"], "NOT_CONSIDERED"),
    ("INSUFFICIENT_INFORMATION", True, [], "INSUFFICIENT_INFORMATION"),
    ("HIGH", False, ["CHRISTMAS_ESCALATION"], "INSUFFICIENT_INFORMATION"),
    ("HIGH", True, ["ALREADY_ON_PROMOTION"], "BLOCKED"),
    ("MODERATE", True, [], "ELIGIBLE_FOR_MARKDOWN_REVIEW"),
    ("HIGH", True, [], "ELIGIBLE_FOR_MARKDOWN_REVIEW"),
])
def test_rule_precedence(cat, batch, blockers, expected):
    assert M.classify(cat, batch, blockers, ["HIGH", "MODERATE"]) == expected


def test_overlapping_blockers_are_all_kept_in_documented_order():
    got = M.blockers_for(True, True, 10, 1001, [1001], 0, 1, ORDER)
    assert got == ORDER
    assert M.blockers_for(False, False, 0, 1001, [], 1, 1, ORDER) == []
    assert M.blockers_for(True, False, 15, 1001, [], 3, 1, ORDER) == ["CHRISTMAS_ESCALATION", "ALREADY_ON_PROMOTION"]


@pytest.mark.parametrize("days,blocked", [(0, True), (1, False), (2, False), (None, False)])
def test_one_sellable_day_boundary(days, blocked):
    assert ("TOO_LATE_TO_ACT" in M.blockers_for(False, False, 0, 1, [], days, 1, ORDER)) is blocked


@pytest.mark.parametrize("pct,blocked", [(0, False), (5, True), (25, True), (float("nan"), False), (None, False)])
def test_existing_promotion(pct, blocked):
    assert ("ALREADY_ON_PROMOTION" in M.blockers_for(False, False, pct, 1, [], 1, 1, ORDER)) is blocked


def test_empty_exclusions_block_nothing(assessed):
    assert not assessed.blocker_codes.str.contains("PRODUCT_EXCLUDED").any()
    assert M.blockers_for(False, False, 0, 1030, [], 1, 1, ORDER) == []
    assert M.blockers_for(False, False, 0, 1030, [1030], 1, 1, ORDER) == ["PRODUCT_EXCLUDED"]


# ------------------------------------------------------------------------------------------- assessment
def test_worked_example(assessed):
    r = assessed[(assessed.Store_ID == 504) & (assessed.Product_ID == 1030) & (assessed.target_week == 40)].iloc[0]
    assert r.eligibility == "ELIGIBLE_FOR_MARKDOWN_REVIEW" and r.blocker_codes == ""
    assert r.sellable_days_after_investigate_by == 1 and r.recorded_price_origin_week == pytest.approx(2.58)
    assert r.warning_codes == "OPEN_INVENTORY_REVIEW_CASE" and r.review_case_ref == "CASE-W-SC1-504-1030-O39"
    assert "Wed, week 40" in r.guidance and "No discount size is proposed" in r.guidance


def test_christmas_escalations_are_blocked(assessed):
    x = assessed[assessed.christmas_any_horizon & assessed.waste_risk_category.isin(["HIGH", "MODERATE"])]
    assert len(x) > 0 and (x.eligibility.isin(["BLOCKED", "INSUFFICIENT_INFORMATION"])).all()
    assert x[x.eligibility == "BLOCKED"].blocker_codes.str.startswith("CHRISTMAS_ESCALATION").all()


def test_shortage_blocker(saved, params):
    d = saved["decisions"].copy()
    w = saved["waste"]
    key = w[w.category.isin(["HIGH", "MODERATE"]) & w.earliest_batch_last_day.notna()].iloc[0]
    hit = (d.Store_ID == key.Store_ID) & (d.Product_ID == key.Product_ID) & (d.origin_week == key.origin_week)
    d.loc[hit, "std_pre_delivery_shortage"] = True
    a = M.assess(w, d, saved["contract"], saved["panel"], params)
    r = a[(a.Store_ID == key.Store_ID) & (a.Product_ID == key.Product_ID) & (a.origin_week == key.origin_week)].iloc[0]
    assert r.eligibility == "BLOCKED" and "SHORTAGE_BEFORE_DELIVERY" in r.blocker_codes.split("|")


def test_missing_batch_dates_give_insufficient_information(saved, params):
    w = saved["waste"].copy()
    key = w[w.category.isin(["HIGH", "MODERATE"]) & w.earliest_batch_last_day.notna()].index[0]
    w.loc[key, ["earliest_batch_last_day", "investigate_by_day"]] = np.nan
    a = M.assess(w, saved["decisions"], saved["contract"], saved["panel"], params)
    r = a.iloc[key]
    assert r.eligibility == "INSUFFICIENT_INFORMATION" and r.insufficient_codes == "MISSING_BATCH_DATE"
    assert r.sellable_days_after_investigate_by is None or pd.isna(r.sellable_days_after_investigate_by)


def test_open_inventory_cases_are_warnings_not_blockers(assessed):
    warned = assessed[assessed.warning_codes == "OPEN_INVENTORY_REVIEW_CASE"]
    assert len(warned) > 0 and (warned.eligibility == "ELIGIBLE_FOR_MARKDOWN_REVIEW").any()
    assert not assessed.blocker_codes.str.contains("INVENTORY").any()
    assert (assessed[assessed.eligibility == "NOT_CONSIDERED"].warning_codes == "").all()


def test_full_counts_match_the_design(params):
    a = M.assess(D.waste_risk("SC1", "P2"), D.decisions("SC1", "P2"), D.contract(), D.recorded_prices(), params)
    s = M.summary(a)
    assert (s["ELIGIBLE_FOR_MARKDOWN_REVIEW"], s["BLOCKED"], s["INSUFFICIENT_INFORMATION"], s["NOT_CONSIDERED"]) == (91, 42, 1, 14266)
    assert s["blocked_by_reason"] == {"CHRISTMAS_ESCALATION": 27, "ALREADY_ON_PROMOTION": 19}
    assert s["proposals_created"] == 0 and s["approvals_created"] == 0


def test_no_numbers_no_approvals_no_execution(assessed):
    assert set(assessed.lifecycle_state) == {"STATE_1_ELIGIBILITY_ONLY"}
    assert set(assessed.status) == {"HYPOTHETICAL_UNAPPROVED"} and set(assessed.execution_status) == {"NOT_EXECUTED"}
    assert assessed.approval_event_id.isna().all() and assessed.proposal_id.isna().all()
    for col in assessed.columns:
        assert not any(w in col for w in ("proposed_discount", "new_price", "uplift", "saving", "margin", "elasticity"))
    src = Path(M.__file__).read_text(encoding="utf-8")
    for forbidden in ("to_csv", "write_text", "open(", "simulate(", "sqlite", "requests", "discount_uplift"):
        assert forbidden not in src, forbidden


def test_determinism(saved, params, assessed):
    pd.testing.assert_frame_equal(M.assess(saved["waste"], saved["decisions"], saved["contract"], saved["panel"], params),
                                  assessed)


def test_no_future_data_leakage(saved, params, assessed):
    """Recorded prices and discounts after a cut-off must not change earlier eligibility."""
    cutoff = 42
    panel = saved["panel"].copy()
    later = panel.week_index > cutoff
    panel.loc[later, "Discount_Percent"] = 25
    panel.loc[later, "Price"] = 99.0
    a = M.assess(saved["waste"], saved["decisions"], saved["contract"], panel, params)
    early = lambda df: df[df.origin_week <= cutoff].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(early(a), early(assessed))
    assert not a[a.origin_week > cutoff].equals(assessed[assessed.origin_week > cutoff])


def test_protected_files_unchanged(protected_registry):
    bad = [rel for rel, digest in protected_registry.items()
           if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    assert not bad
