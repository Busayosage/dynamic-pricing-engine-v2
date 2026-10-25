"""Statistical helpers. Every result is descriptive or associational, never causal.

With ~37,000 rows almost any difference is 'significant', so effect sizes are reported
alongside p-values. Rows from the same store-product series are not independent; group
tests are therefore run on series-level aggregates and the regression uses clustered errors.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

ASSOCIATION_LABEL = "conditional association (not a causal effect or elasticity estimate)"


def within_group_demean(df: pd.DataFrame, cols, by) -> pd.DataFrame:
    """Subtract each group's mean, so comparisons are within (not across) groups."""
    cols = list(cols)
    return df[cols] - df.groupby(by)[cols].transform("mean")


def multiway_demean(values, groups, max_iter: int = 100, tol: float = 1e-10) -> pd.Series:
    """Remove several sets of group means at once (alternating projections).

    Used to compare a variable with units sold after taking out, e.g., series and month means.
    Converges in one pass for balanced panels; iterates otherwise.
    """
    out = pd.Series(np.asarray(values, dtype=float))
    keys = [pd.Series(np.asarray(g)) for g in groups]
    for _ in range(max_iter):
        before = out.copy()
        for k in keys:
            out = out - out.groupby(k).transform("mean")
        if float((out - before).abs().max()) < tol:
            break
    return out


def spearman_with_ci(x, y, conf: float = 0.95) -> dict:
    """Spearman rho with an approximate CI (Fisher z, Fieller-Hartley-Pearson SE)."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = int(len(x))
    if n < 4 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return {"rho": float("nan"), "ci_low": float("nan"), "ci_high": float("nan"),
                "p_value": float("nan"), "n": n}
    res = sps.spearmanr(x, y)
    rho = float(res.statistic)
    z = np.arctanh(np.clip(rho, -0.999999, 0.999999))
    se = np.sqrt(1.06 / (n - 3))
    zc = sps.norm.ppf(0.5 + conf / 2)
    return {"rho": rho, "ci_low": float(np.tanh(z - zc * se)), "ci_high": float(np.tanh(z + zc * se)),
            "p_value": float(res.pvalue), "n": n}


def kruskal_effect(values, groups) -> dict:
    """Kruskal-Wallis H with epsilon-squared effect size."""
    d = pd.DataFrame({"v": np.asarray(values, dtype=float), "g": np.asarray(groups)}).dropna()
    samples = [s.to_numpy() for _, s in d.groupby("g")["v"]]
    n = int(len(d))
    if len(samples) < 2 or n < 3:
        return {"statistic": float("nan"), "p_value": float("nan"), "effect_size": float("nan"),
                "effect_measure": "epsilon_squared", "n": n}
    h, p = sps.kruskal(*samples)
    return {"statistic": float(h), "p_value": float(p), "effect_size": float(h / (n - 1)),
            "effect_measure": "epsilon_squared", "n": n}


def mann_whitney_effect(a, b) -> dict:
    """Mann-Whitney U with rank-biserial correlation (+1 = every a above every b)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) == 0 or len(b) == 0:
        return {"statistic": float("nan"), "p_value": float("nan"), "effect_size": float("nan"),
                "effect_measure": "rank_biserial", "n": int(len(a) + len(b))}
    res = sps.mannwhitneyu(a, b, alternative="two-sided")
    r = 2 * float(res.statistic) / (len(a) * len(b)) - 1
    return {"statistic": float(res.statistic), "p_value": float(res.pvalue), "effect_size": r,
            "effect_measure": "rank_biserial", "n": int(len(a) + len(b))}


def paired_difference(diffs) -> dict:
    """Summary of within-series differences, with a Wilcoxon signed-rank test when n >= 10."""
    d = np.asarray(diffs, dtype=float)
    d = d[np.isfinite(d)]
    n = int(len(d))
    out = {"n": n, "mean": float(np.mean(d)) if n else float("nan"),
           "median": float(np.median(d)) if n else float("nan"),
           "share_positive": float(np.mean(d > 0)) if n else float("nan"), "p_value": float("nan")}
    if n >= 10 and np.any(d != 0):
        out["p_value"] = float(sps.wilcoxon(d).pvalue)
    return out


def ljung_box(series, lags=(4, 8)) -> pd.DataFrame:
    """Ljung-Box test for autocorrelation in a weekly series."""
    from statsmodels.stats.diagnostic import acorr_ljungbox

    s = np.asarray(series, dtype=float)
    s = s[np.isfinite(s)]
    usable = [lag for lag in lags if lag < len(s)]
    if not usable:
        return pd.DataFrame(columns=["lag", "lb_stat", "lb_pvalue"])
    return pd.DataFrame(acorr_ljungbox(s, lags=usable)).reset_index(names="lag")


def bh_adjust(pvals) -> np.ndarray:
    """Benjamini-Hochberg false-discovery-rate adjusted p-values (NaNs left as NaN)."""
    p = np.asarray(pvals, dtype=float)
    out = np.full(p.shape, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return out
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adj = np.empty(m)
    adj[order] = np.minimum(ranked, 1.0)
    out[ok] = adj
    return out


def associational_ols(df: pd.DataFrame):
    """log(units) on log(price), discount, log(marketing), weather and holiday, with product,
    store and week fixed effects; errors clustered by product. Labelled as association only."""
    import statsmodels.formula.api as smf

    cols = ["Units_Sold", "Price", "Discount_Percent", "Marketing_Spend", "Avg_Temperature",
            "Rainfall", "Holiday_Flag", "Product_ID", "Store_ID", "WeekDate"]
    d = df[cols].dropna().copy()
    d = d[(d.Units_Sold > 0) & (d.Price > 0) & (d.Marketing_Spend > 0)]
    d["log_units"] = np.log(d["Units_Sold"])
    d["log_price"] = np.log(d["Price"])
    d["log_marketing"] = np.log(d["Marketing_Spend"])
    d["week_label"] = d["WeekDate"].dt.strftime("%Y-%m-%d")
    formula = ("log_units ~ log_price + Discount_Percent + log_marketing + Avg_Temperature + Rainfall"
               " + Holiday_Flag + C(Product_ID) + C(Store_ID) + C(week_label)")
    groups = pd.factorize(d["Product_ID"])[0]
    fit = smf.ols(formula, data=d).fit(cov_type="cluster", cov_kwds={"groups": groups})
    terms = ["log_price", "Discount_Percent", "log_marketing", "Avg_Temperature", "Rainfall", "Holiday_Flag"]
    ci = fit.conf_int().loc[terms]
    table = pd.DataFrame({
        "term": terms,
        "coef": fit.params[terms].to_numpy(),
        "std_err_clustered": fit.bse[terms].to_numpy(),
        "ci_low": ci[0].to_numpy(),
        "ci_high": ci[1].to_numpy(),
        "p_value": fit.pvalues[terms].to_numpy(),
    })
    table["interpretation"] = ASSOCIATION_LABEL
    info = {"n": int(fit.nobs), "r_squared": float(fit.rsquared), "clusters": int(len(set(groups))),
            "fixed_effects": "product, store, week", "interpretation": ASSOCIATION_LABEL}
    return table, info
