"""CP2 leakage tests on a small synthetic panel with known values (no model training).

eda_raw: 3 products x 3 stores x 16 weeks; Units = 100*(product index + 1) + 10*store index + week.
"""
import numpy as np
import pandas as pd
import pytest

from conftest import EDA_PRODUCTS, EDA_STORES, EDA_WEEKS
from dpe.forecast import features as F
from dpe.forecast.panel import build_panel, holiday_calendar
from dpe.forecast.scenarios import SCENARIOS

N_SERIES = len(EDA_PRODUCTS) * len(EDA_STORES)
SCRAMBLED = ["Units_Sold", "Wastage_Units", "Price", "Discount_Percent", "Marketing_Spend", "Avg_Temperature",
             "Rainfall"]


@pytest.fixture
def panel(eda_raw):
    return build_panel(eda_raw)


@pytest.fixture
def calendar(panel):
    return holiday_calendar(panel)


def _build(panel, calendar, h, scenario="S0", history=None, plans=None, origins=None):
    plans = panel if (plans is None and scenario != "S0") else plans
    return F.build_features(panel if history is None else history, calendar, h, scenario, plans=plans,
                            origins=origins)


def _scramble_after(panel, origin, seed=0):
    """Replace every weekly value after `origin` with random numbers (keys and statics untouched)."""
    rng = np.random.default_rng(seed)
    out = panel.copy()
    later = out["week_index"] > origin
    for c in SCRAMBLED:
        out.loc[later, c] = rng.integers(1, 10_000, int(later.sum())).astype(out[c].dtype)
    return out


# ------------------------------------------------------------- feature lists
def test_feature_lists_are_explicit_and_s0_has_no_target_week_values():
    s0 = F.feature_columns("S0")
    assert len(s0) == len(set(s0))
    for scen in SCENARIOS.values():
        cols = F.feature_columns(scen.name)
        assert cols[:len(s0)] == s0 and set(cols) - set(s0) == set(scen.target_week_inputs)
    assert not [c for c in s0 if c.startswith(("plan_", "oracle_"))]
    lowered = " ".join(s0).lower()
    for banned in ("wastage", "waste", "week_number", "week_of_year", "weekofyear", "supplier_id", "price",
                   "marketing", "temperature", "rainfall"):
        assert banned not in lowered, banned
    assert not SCENARIOS["S3"].deployable and not SCENARIOS["S3"].eligible_for_acceptance


# ------------------------------------------------------- origins and alignment
@pytest.mark.parametrize("h", [1, 4])
def test_origin_target_alignment_and_lags(panel, calendar, h):
    f = _build(panel, calendar, h)
    assert (f["target_week"] == f["origin_week"] + h).all()
    assert (f["target_date"] == f["origin_date"] + pd.Timedelta(weeks=h)).all()
    assert (f["horizon"] == h).all() and (f["scenario"] == "S0").all()
    store_idx = {s: i for i, s in enumerate(EDA_STORES)}
    prod_idx = {p: i for i, p in enumerate(EDA_PRODUCTS)}
    base = 100 * (f["Product_ID"].map(prod_idx) + 1) + 10 * f["Store_ID"].map(store_idx)
    T = f["origin_week"]
    # History is anchored at the ORIGIN for both horizons (y_t0 = sales in week T, never week T + h - 1).
    assert (f["y_t0"] == base + T).all()
    for k in (1, 2, 3, 7):
        assert (f[f"y_tm{k}"] == base + T - k).all()
    assert np.allclose(f["mean_4"], base + T - 1.5) and np.allclose(f["mean_8"], base + T - 3.5)
    assert np.allclose(f["min_8"], base + T - 7) and np.allclose(f["max_8"], base + T)
    assert np.allclose(f["trend_4v4"], 4.0)
    assert np.allclose(f["expanding_mean"], base + (T + 1) / 2)


@pytest.mark.parametrize("h", [1, 4])
def test_boundary_origins_and_targets(panel, calendar, h):
    f = _build(panel, calendar, h)
    assert f["origin_week"].min() == F.MIN_HISTORY_WEEKS  # 8 observed weeks: 1..8
    assert f["target_week"].min() == F.MIN_HISTORY_WEEKS + h  # H1 -> week 9, H4 -> week 12
    assert f["origin_week"].max() == EDA_WEEKS - h  # last target is the last calendar week
    assert f["target_week"].max() == EDA_WEEKS
    n_origins = EDA_WEEKS - h - F.MIN_HISTORY_WEEKS + 1
    assert len(f) == N_SERIES * n_origins
    # Origin 7 has only 7 observed weeks: excluded, not padded.
    assert _build(panel, calendar, h, origins=[F.MIN_HISTORY_WEEKS - 1]).empty
    # An origin whose target is beyond the known calendar produces no row.
    assert _build(panel, calendar, h, origins=[EDA_WEEKS - h + 1]).empty


def test_identifiers_preserved_and_unique(panel, calendar):
    for h in (1, 4):
        f = _build(panel, calendar, h)
        assert f[["Store_ID", "Product_ID", "origin_week"]].notna().all().all()
        assert not f.duplicated(subset=["Store_ID", "Product_ID", "origin_week"]).any()
        assert set(f["Store_ID"]) == set(EDA_STORES) and set(f["Product_ID"]) == set(EDA_PRODUCTS)


# ------------------------------------------------------------- leakage tests
@pytest.mark.parametrize("h", [1, 4])
@pytest.mark.parametrize("scenario", ["S0", "S1", "S2", "S3"])
def test_truncation_invariance(panel, calendar, h, scenario):
    """Features at origin T are identical whether or not any week after T exists in the history."""
    full = _build(panel, calendar, h, scenario)
    for T in range(F.MIN_HISTORY_WEEKS, EDA_WEEKS - h + 1):
        truncated = panel[panel["week_index"] <= T]
        got = _build(panel, calendar, h, scenario, history=truncated, plans=panel, origins=[T])
        want = full[full["origin_week"] == T].reset_index(drop=True)
        pd.testing.assert_frame_equal(got, want, check_exact=True)


@pytest.mark.parametrize("h", [1, 4])
def test_future_scrambling_does_not_change_s0(panel, calendar, h):
    full = _build(panel, calendar, h)
    for T in range(F.MIN_HISTORY_WEEKS, EDA_WEEKS - h + 1):
        scrambled = _scramble_after(panel, T, seed=T)
        got = _build(scrambled, calendar, h, origins=[T])
        pd.testing.assert_frame_equal(got, full[full["origin_week"] == T].reset_index(drop=True), check_exact=True)


@pytest.mark.parametrize("h", [1, 4])
def test_future_scrambling_changes_only_declared_plan_inputs(panel, calendar, h):
    T = F.MIN_HISTORY_WEEKS
    base = _build(panel, calendar, h, "S2", origins=[T])
    scrambled = _scramble_after(panel, T, seed=99)
    got = _build(panel, calendar, h, "S2", history=scrambled, plans=scrambled, origins=[T])
    plan_cols = list(SCENARIOS["S2"].target_week_inputs)
    other = [c for c in base.columns if c not in plan_cols]
    pd.testing.assert_frame_equal(got[other], base[other], check_exact=True)
    assert not got[plan_cols].equals(base[plan_cols])  # the test can see a change when one is allowed


def test_wastage_is_never_read(panel, calendar):
    changed = panel.assign(Wastage_Units=panel["Wastage_Units"] * 7 + 3)
    for h in (1, 4):
        pd.testing.assert_frame_equal(_build(changed, calendar, h, "S3", plans=changed),
                                      _build(panel, calendar, h, "S3"), check_exact=True)


def test_target_week_values_do_not_reach_s0(panel, calendar):
    """Changing only target-week commercial/weather values (not history) leaves S0 unchanged."""
    h, T = 4, 10
    f = _build(panel, calendar, h, origins=[T])
    p = panel.copy()
    tgt = p["week_index"] == T + h
    p.loc[tgt, ["Price", "Discount_Percent", "Marketing_Spend", "Avg_Temperature", "Rainfall"]] = 9_999
    pd.testing.assert_frame_equal(_build(p, calendar, h, origins=[T]), f, check_exact=True)


def test_hierarchy_features_use_origin_week_only(panel, calendar):
    f = _build(panel, calendar, 1)
    row = f[(f["origin_week"] == 10)].iloc[0]
    wk = panel[(panel["week_index"] == 10) & (panel["Product_ID"] == row["Product_ID"])]
    assert row["prod_total_t0"] == wk["Units_Sold"].sum()
    w8 = panel[(panel["week_index"].between(3, 10))]
    series = w8[(w8.Store_ID == row["Store_ID"]) & (w8.Product_ID == row["Product_ID"])]["Units_Sold"].sum()
    product = w8[w8.Product_ID == row["Product_ID"]]["Units_Sold"].sum()
    assert row["series_share_8"] == pytest.approx(series / product)


def test_undiscounted_mean_uses_only_undiscounted_weeks_with_real_fallback(panel, calendar):
    f = _build(panel, calendar, 1)
    row = f.iloc[0]
    w = panel[(panel.Store_ID == row.Store_ID) & (panel.Product_ID == row.Product_ID)
              & panel.week_index.between(row.origin_week - 7, row.origin_week)]
    expected = w.loc[w.Discount_Percent == 0, "Units_Sold"].mean()
    assert row["undisc_mean_8"] == pytest.approx(expected)
    all_disc = panel.assign(Discount_Percent=10)
    g = _build(all_disc, calendar, 1)
    assert np.allclose(g["undisc_mean_8"], g["mean_8"])  # fallback is the observed 8-week mean


# ------------------------------------------------------ no fabricated history
def test_missing_week_raises_instead_of_zero_fill(panel, calendar):
    gap = panel.drop(index=panel.index[(panel.Store_ID == 500) & (panel.Product_ID == 1000)
                                       & (panel.week_index == 5)])
    with pytest.raises(ValueError, match="Incomplete grid"):
        _build(gap, calendar, 1)
    nan_units = panel.copy()
    nan_units.loc[nan_units.index[3], "Units_Sold"] = np.nan
    with pytest.raises(ValueError, match="missing values"):
        _build(nan_units, calendar, 1)


def test_no_missing_history_on_eligible_rows(panel, calendar):
    for h in (1, 4):
        f = _build(panel, calendar, h)
        assert f[F.HISTORY_FEATURES].notna().all().all()


# -------------------------------------------------- frame checks and matrix
def test_scenario_inputs_require_plans(panel, calendar):
    with pytest.raises(ValueError, match="needs target-week plans"):
        F.build_features(panel, calendar, 1, "S1", plans=None)


def test_check_rejects_forbidden_or_undeclared_columns(panel, calendar):
    f = _build(panel, calendar, 1)
    for col in ("Wastage_Units", "Discount_Percent", "Week_Number_wx_2024-W10", "Supplier_ID", "mystery"):
        with pytest.raises(ValueError):
            F.check_feature_frame(f.assign(**{col: 1}), "S0")
    with pytest.raises(ValueError, match="target_week"):
        F.check_feature_frame(f.assign(target_week=f["target_week"] + 1), "S0")


def test_model_matrix_uses_identifiers_only_as_one_hot(panel, calendar):
    cats = F.static_categories(panel)
    f = _build(panel, calendar, 4, "S1")
    X = F.model_matrix(f, "S1", cats)
    assert "Store_ID" not in X.columns and "Product_ID" not in X.columns
    assert {f"Store_ID={s}" for s in EDA_STORES} <= set(X.columns)
    assert {f"Product_ID={p}" for p in EDA_PRODUCTS} <= set(X.columns)
    assert X.filter(like="Store_ID=").sum(axis=1).eq(1).all()
    # Same columns, same order, for any subset of rows (fixed category lists).
    sub = F.model_matrix(f[f["Store_ID"] == 500], "S1", cats)
    assert list(sub.columns) == list(X.columns)
    assert "plan_discount" in X.columns and "plan_discount" not in F.model_matrix(_build(panel, calendar, 4), "S0", cats)
    unknown = f.copy()
    unknown.loc[unknown.index[0], "Store_ID"] = 999
    with pytest.raises(ValueError, match="Unknown"):
        F.model_matrix(unknown, "S1", cats)


def test_attach_target_is_label_only(panel, calendar):
    f = F.attach_target(_build(panel, calendar, 4), panel)
    t = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"]
    assert (f["target_units"].to_numpy() == t.loc[list(zip(f.Store_ID, f.Product_ID, f.target_week))].to_numpy()).all()
    assert "target_units" not in F.feature_columns("S3")
    with pytest.raises(ValueError, match="no observed target"):
        F.attach_target(_build(panel, calendar, 4), panel[panel.week_index < EDA_WEEKS])


def test_invalid_horizon_rejected(panel, calendar):
    for bad in (0, -1, 1.5):
        with pytest.raises(ValueError):
            F.build_features(panel, calendar, bad)
