"""Statistical helpers on data with known answers."""
import numpy as np
import pandas as pd
import pytest

from dpe.eda import stats as S


def test_within_group_demean_gives_zero_group_means():
    df = pd.DataFrame({"g": [1, 1, 2, 2], "x": [1.0, 3.0, 10.0, 20.0]})
    out = S.within_group_demean(df, ["x"], "g")
    assert out.groupby(df["g"])["x"].mean().abs().max() == pytest.approx(0.0)


def test_spearman_known_cases_and_ci():
    x = np.arange(50)
    perfect = S.spearman_with_ci(x, x * 2)
    assert perfect["rho"] == pytest.approx(1.0)
    rng = np.random.default_rng(0)
    y = x + rng.normal(0, 10, size=50)
    r = S.spearman_with_ci(x, y)
    assert 0 < r["rho"] < 1 and r["ci_low"] < r["rho"] < r["ci_high"]
    big = S.spearman_with_ci(np.arange(500), np.arange(500) + rng.normal(0, 100, size=500))
    assert (big["ci_high"] - big["ci_low"]) < (r["ci_high"] - r["ci_low"])
    assert np.isnan(S.spearman_with_ci([1, 1, 1, 1, 1], [1, 2, 3, 4, 5])["rho"])


def test_kruskal_and_mann_whitney_effects():
    k = S.kruskal_effect(list(range(20)) + list(range(100, 120)), ["a"] * 20 + ["b"] * 20)
    assert k["p_value"] < 0.001 and 0 < k["effect_size"] <= 1
    mw = S.mann_whitney_effect([10, 11, 12], [1, 2, 3])
    assert mw["effect_size"] == pytest.approx(1.0)


def test_paired_difference():
    out = S.paired_difference(np.arange(1, 13))
    assert out["share_positive"] == 1.0 and out["p_value"] < 0.01
    assert np.isnan(S.paired_difference([1, 2])["p_value"])  # too few for a test
    assert S.paired_difference([])["n"] == 0


def test_bh_adjust_known_values():
    adj = S.bh_adjust([0.01, 0.04, 0.03, 0.005])
    assert np.allclose(adj, [0.02, 0.04, 0.04, 0.02])
    with_nan = S.bh_adjust([0.01, np.nan])
    assert np.isnan(with_nan[1]) and with_nan[0] == pytest.approx(0.01)


def test_ljung_box_detects_autocorrelation():
    trend = np.sin(np.arange(52) / 3)
    lb = S.ljung_box(trend, lags=(4, 8))
    assert list(lb["lag"]) == [4, 8] and (lb["lb_pvalue"] < 0.05).all()


def test_associational_ols_is_labelled_not_causal(eda_raw):
    from dpe.eda.data import build_analysis_frame

    table, info = S.associational_ols(build_analysis_frame(eda_raw))
    assert "log_price" in set(table["term"])
    assert (table["interpretation"] == S.ASSOCIATION_LABEL).all()
    assert "not a causal effect" in S.ASSOCIATION_LABEL
    assert info["fixed_effects"] == "product, store, week"
