"""Stage 6B: waste-risk intelligence module and assumption set v3 (advisory, read-only)."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import assumptions_v2 as B
from dpe.decision import assumptions_v3 as C
from dpe.decision import waste_risk as W

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "dashboard"))
import dashboard_data as D  # noqa: E402

V3_CONTENT_SHA256 = "cb46de1bb2acfba85e8aa763138436a9bfb5cfd0b8d42820da5bebc2be4f63d9"


@pytest.fixture(scope="module")
def params():
    return C.waste_risk_values(C.load())


@pytest.fixture(scope="module")
def saved():
    """Saved SC1 / P2 tables for two stores (keeps the tests quick)."""
    keep = lambda df, s="Store_ID": df[df[s].isin([504, 505])].reset_index(drop=True)  # noqa: E731
    return {"decisions": keep(D.decisions("SC1", "P2")), "deliveries": keep(D.deliveries("SC1", "P2")),
            "weekly": keep(D.weekly("SC1", "P2")), "contract": keep(D.contract(), "store_id"),
            "panel": keep(D.recorded_panel()), "cases": keep(D.review_cases("SC1", "P2"), "store_id")}


@pytest.fixture(scope="module")
def assessed(saved, params):
    return W.assess(saved["decisions"], saved["deliveries"], saved["weekly"], saved["contract"], saved["panel"],
                    saved["cases"], params)


# ---------------------------------------------------------------------------------------------- v3
def test_v3_is_a_valid_draft_and_v1_v2_are_unchanged():
    doc = C.load()
    s = C.validate(doc, B.load())
    assert s["assumption_set_id"] == "AS-2026-10-23-v3" and s["status"] == "DRAFT" and s["parameters"] == 45
    assert A.content_sha256(doc) == V3_CONTENT_SHA256 and doc["production_use"] is False
    assert hashlib.sha256(A.DEFAULT_FILE.read_bytes()).hexdigest() == "42116041ee61d265fc2756726de61b57b271513d9d095d914116208b4d2ccd50"
    assert hashlib.sha256(B.V2_FILE.read_bytes()).hexdigest() == "2119a2d4d2ae2b26b42d073f94c382b2e6d17a513aa5a6e9f00ee6df3910269f"
    assert len(s["added_parameters"]) == 9
    v2 = {p["key"]: p["value"] for p in B.load()["parameters"]}
    v3 = {p["key"]: p["value"] for p in doc["parameters"]}
    assert all(v3[k] == v for k, v in v2.items())
    assert v3["expiry_escalation_pct_of_p50"] == 15  # the 15% inventory warning is preserved unchanged


@pytest.mark.parametrize("mutate,message", [
    (lambda d: _p(d, "waste_risk_high_pct_of_p50").update(value=5), "below"),
    (lambda d: _p(d, "waste_risk_advisory_only").update(value=False), "allowed set"),
    (lambda d: _p(d, "waste_risk_discounts_enabled").update(value=True), "allowed set"),
    (lambda d: _p(d, "service_target_pct").update(value={"Bakery": 60, "Meat": 88, "Dairy": 92, "Beverages": 95}), "changed"),
    (lambda d: _p(d, "waste_risk_moderate_pct_of_p50").pop("sensitivity_range"), "missing"),
    (lambda d: d.update(production_use=True), "production_use"),
    (lambda d: d["approval"].update(status="APPROVED", approved_by="x", approved_at="2026-10-23"), "DRAFT"),
])
def test_invalid_v3_files_are_rejected(mutate, message):
    bad = copy.deepcopy(C.load())
    mutate(bad)
    bad["approval"]["content_sha256"] = A.content_sha256(bad)
    with pytest.raises(A.AssumptionError, match=message):
        A.validate(bad)
        C.validate(bad, B.load())


def _p(doc, key):
    return next(p for p in doc["parameters"] if p["key"] == key)


# ------------------------------------------------------------------------------------- classification
@pytest.mark.parametrize("units,p50,expected", [
    (25.0, 100, "HIGH"), (24.99, 100, "MODERATE"), (10.0, 100, "MODERATE"), (9.99, 100, "LOW"), (0, 100, "LOW"),
    (60, 100, "HIGH"),
])
def test_category_boundaries(units, p50, expected, params):
    cat, share = W.classify(units, p50, params["waste_risk_high_pct_of_p50"], params["waste_risk_moderate_pct_of_p50"])
    assert cat == expected and share == pytest.approx(units)


@pytest.mark.parametrize("units,p50,bounds,supported", [
    (50, 100, False, True), (50, 100, True, False), (None, 100, True, True), (float("nan"), 100, True, True),
    (10, None, True, True), (10, float("nan"), True, True),
])
def test_missing_information(units, p50, bounds, supported, params):
    cat, share = W.classify(units, p50, 25, 10, bounds, supported)
    assert cat == "INSUFFICIENT_INFORMATION" and share is None


def test_zero_p50_is_never_low_and_never_divides_by_zero():
    assert W.classify(5, 0, 25, 10) == ("HIGH", None)
    assert W.classify(0, 0, 25, 10) == ("INSUFFICIENT_INFORMATION", None)
    assert W.classify(0.2, 0.0, 25, 10) == ("INSUFFICIENT_INFORMATION", None)  # below half a unit counts as zero
    assert W.classify(3, -1, 25, 10) == ("HIGH", None)


def test_zero_p50_row_in_an_assessment(saved, params):
    c = saved["contract"].copy()
    hit = (c.horizon_weeks == 1) & (c.store_id == 504) & (c.product_id == 1030) & (c.origin_week == 39)
    c.loc[hit, "median_p50_units"] = 0.0
    a = W.assess(saved["decisions"], saved["deliveries"], saved["weekly"], c, saved["panel"], saved["cases"], params)
    row = a[(a.Store_ID == 504) & (a.Product_ID == 1030) & (a.origin_week == 39)].iloc[0]
    assert row.category == "HIGH" and row.projected_expiry_pct_of_p50 is None or pd.isna(row.projected_expiry_pct_of_p50)
    assert "ZERO_TYPICAL_DEMAND" in row.all_reason_codes


# ------------------------------------------------------------------------------------- assessment
def test_design_example_reproduced(assessed):
    r = assessed[(assessed.Store_ID == 504) & (assessed.Product_ID == 1030) & (assessed.target_week == 40)].iloc[0]
    assert r.category == "HIGH" and r.projected_existing_expiry_units == pytest.approx(2373.6)
    assert r.projected_expiry_pct_of_p50 == pytest.approx(60.02) and r.projected_expiry_days_of_sales == pytest.approx(4.2)
    assert r.earliest_batch_last_day_label == "Thu, week 40" and r.investigate_by_label == "Wed, week 40"
    assert r.review_case_ref == "CASE-W-SC1-504-1030-O39" and r.review_status.startswith("PENDING_REVIEW")
    b = assessed[(assessed.Store_ID == 505) & (assessed.Product_ID == 1001) & (assessed.target_week == 45)].iloc[0]
    assert b.category == "LOW" and b.planned_buffer_units == pytest.approx(430.7) and b.investigate_by_label is None


def test_planned_buffer_never_changes_the_category(saved, params, assessed):
    d = saved["decisions"].copy()
    dl = saved["deliveries"].copy()
    dl.loc[dl.kind == "ORDER", "ordered_units"] *= 10  # a much larger planned buffer
    a = W.assess(d, dl, saved["weekly"], saved["contract"], saved["panel"], saved["cases"], params)
    assert (a.category.values == assessed.category.values).all()
    assert a.planned_buffer_units.sum() > assessed.planned_buffer_units.sum()
    big = assessed[assessed.planned_buffer_units > 0.3 * assessed.typical_weekly_demand_p50]
    assert len(big) > 0 and (big.category == "LOW").any()  # large planned buffers stay Low when current stock is fine


def test_full_scenario_counts_match_the_design(params):
    a = W.assess(D.decisions("SC1", "P2"), D.deliveries("SC1", "P2"), D.weekly("SC1", "P2"), D.contract(),
                 D.recorded_panel(), D.review_cases("SC1", "P2"), params)
    s = W.summary(a)
    assert (s["HIGH"], s["MODERATE"], s["INSUFFICIENT_INFORMATION"]) == (37, 97, 0) and s["review_cases_created"] == 0
    high = a[a.category == "HIGH"]
    assert high.review_case_type.notna().all()  # every High row already has an inventory review case
    assert (a.product_category.eq("Beverages") <= a.category.eq("LOW")).all()


def test_advisory_only_no_review_or_approval_records(saved, assessed):
    before = saved["cases"].copy()
    assert (assessed.creates_review_case == False).all() and assessed.approval_event_id.isna().all()  # noqa: E712
    assert set(assessed.status) == {"ADVISORY_HYPOTHETICAL"}
    pd.testing.assert_frame_equal(saved["cases"], before)
    for col in ("discount", "price", "margin", "cost"):
        assert not any(col in c.lower() for c in assessed.columns)


def test_provenance_labels_separate_recorded_forecast_simulated_assumed():
    p = W.PROVENANCE
    assert "RECORDED" in p["recorded_wastage_pct_4w"] and "SIMULATED" not in p["recorded_wastage_pct_4w"]
    assert "SIMULATED" in p["recent_simulated_expiry_pct_4w"] and "RECORDED" not in p["recent_simulated_expiry_pct_4w"]
    assert "FORECAST" in p["typical_weekly_demand_p50"] and "ASSUMED" in p["category"]
    assert "context only" in p["planned_buffer_units"] and "projection" in p["projected_existing_expiry_units"]


def test_category_comparison_keeps_measures_separate(saved):
    attrs = D.series_list()
    comp = W.category_comparison(saved["panel"], saved["weekly"], attrs)
    assert list(comp.columns) == ["category", "recorded_wastage_pct_of_sold_full_year",
                                  "recorded_wastage_pct_of_sold_same_weeks", "simulated_expired_pct_of_received"]
    assert "DIFFERENT MEASURES" in W.category_comparison.__doc__


def test_determinism(saved, params, assessed):
    again = W.assess(saved["decisions"], saved["deliveries"], saved["weekly"], saved["contract"], saved["panel"],
                     saved["cases"], params)
    pd.testing.assert_frame_equal(again, assessed)


def test_no_future_data_leakage(saved, params, assessed):
    """Recorded wastage and simulated history after a cut-off must not change earlier assessments."""
    cutoff = 42
    panel, weekly = saved["panel"].copy(), saved["weekly"].copy()
    rng = np.random.default_rng(1)
    later = panel.week_index > cutoff
    panel.loc[later, "Wastage_Units"] = rng.integers(0, 50_000, int(later.sum()))
    wl = weekly.week > cutoff
    weekly.loc[wl, "sim_expired_units"] = rng.integers(0, 50_000, int(wl.sum()))
    a = W.assess(saved["decisions"], saved["deliveries"], weekly, saved["contract"], panel, saved["cases"], params)
    early = lambda df: df[df.origin_week <= cutoff].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(early(a), early(assessed))
    assert not a[a.origin_week > cutoff].equals(assessed[assessed.origin_week > cutoff])


def test_reads_only_saved_outputs():
    src = Path(W.__file__).read_text(encoding="utf-8")
    for forbidden in ("to_csv", "write_text", "open(", "simulate(", "new_run_dir", "sqlite", "requests"):
        assert forbidden not in src, forbidden


def test_protected_files_unchanged(protected_registry):
    bad = [rel for rel, digest in protected_registry.items()
           if config.sha256_file(config.PROJECT_ROOT / rel) != digest]
    assert not bad


def test_v3_is_registered_as_draft():
    expected = config.load_expected_checksums()
    assert expected["config/assumptions/assumption_set_v3.json"] == hashlib.sha256(C.V3_FILE.read_bytes()).hexdigest()
    assert C.load()["approval"]["status"] == "DRAFT"
