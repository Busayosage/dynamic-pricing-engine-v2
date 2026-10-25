"""Compute every EDA result (no writes) and, separately, write them to a new run folder."""
from __future__ import annotations

import platform
from datetime import datetime
from pathlib import Path

import pandas as pd

from dpe.config import new_run_dir, verify_raw_inputs
from dpe.eda import analysis as A
from dpe.eda import quality as Q
from dpe.eda import stats as S
from dpe.eda.data import DATASET_LABEL, PRICE_NOTE, build_analysis_frame, load_raw, waste_rate_of


def _group_tests(df: pd.DataFrame, r: dict) -> pd.DataFrame:
    series = A.series_summary(df)
    rows = [
        {"test": "Kruskal-Wallis: series units by category", **S.kruskal_effect(series["units"], series["Product_Category"])},
        {"test": "Kruskal-Wallis: series waste rate by category", **S.kruskal_effect(series["waste_rate"], series["Product_Category"])},
        {"test": "Kruskal-Wallis: series units by region", **S.kruskal_effect(series["units"], series["Region"])},
    ]
    hol = r["holiday"]["summary"]
    rows.append({"test": "Wilcoxon: holiday vs non-holiday % difference within series", "statistic": float("nan"),
                 "p_value": hol["p_value"], "effect_size": hol["median"], "effect_measure": "median % difference",
                 "n": hol["n"]})
    for key, label in [("price", "Spearman: price vs units within products"),
                       ("marketing", "Spearman: marketing vs units within products"),
                       ("temperature", "Spearman: temperature vs units within products"),
                       ("rainfall", "Spearman: rainfall vs units within products")]:
        c = r[key]["correlations"]
        c = c[c["scope"] == "All products"].iloc[0]
        rows.append({"test": label, "statistic": c["rho"], "p_value": c["p_value"], "effect_size": c["rho"],
                     "effect_measure": "spearman_rho", "n": c["n"]})
    out = pd.DataFrame(rows)
    out["p_value_bh"] = S.bh_adjust(out["p_value"])
    return out


def compute_all(raw: dict) -> dict:
    """Pure computation: returns tables, dicts and the analysis frame. Writes nothing."""
    df = build_analysis_frame(raw)
    r = {"df": df, "quality": Q.run_quality(raw, df)}
    r["weekly"] = A.weekly_trend(df)
    r["category_index"] = A.category_weekly_index(df)
    r["months"] = A.month_profile(df)
    r["holiday"] = A.holiday_comparison(df)
    r["ljung_box"] = S.ljung_box(r["weekly"]["units"])
    r["categories"] = A.category_summary(df)
    r["products"] = A.product_ranking(df)
    r["stores"] = A.store_summary(df)
    r["regions"] = A.region_summary(df)
    r["overall_waste_rate"] = waste_rate_of(df["Units_Sold"], df["Wastage_Units"])
    r["waste_category_month"] = A.waste_by_category_month(df)
    r["discount"] = A.discount_summary(df)
    r["price"] = A.within_product_relationship(df, "Price", log_x=True)
    # Undiscounted rows only: recorded price is not mixed with discount weeks here.
    r["price_undiscounted"] = A.within_product_relationship(df[df["Discount_Percent"] == 0], "Price",
                                                            log_x=True, by_category=False)
    r["marketing"] = A.within_product_relationship(df, "Marketing_Spend", log_x=True)
    r["temperature"] = A.within_product_relationship(df, "Avg_Temperature", log_x=False, n_bins=8)
    r["rainfall"] = A.within_product_relationship(df, "Rainfall", log_x=False, n_bins=8)
    r["temperature_month_adjusted"] = A.month_adjusted_correlations(df, "Avg_Temperature")
    r["rainfall_month_adjusted"] = A.month_adjusted_correlations(df, "Rainfall")
    r["price_rule"] = A.price_generation_check(df)
    r["waste_rule"] = A.waste_generation_check(df)
    r["discount_mix"] = A.discount_mix_check(df)
    r["discount_timing"] = A.discount_timing(df)
    r["operations"] = A.operations_summary(df)
    flags = A.outlier_flags(df)
    r["outlier_flags"] = flags
    r["outliers"] = A.outlier_summary(flags)
    r["ols_table"], r["ols_info"] = S.associational_ols(df)
    r["group_tests"] = _group_tests(df, r)
    return r


def result_tables(r: dict) -> dict[str, pd.DataFrame]:
    q = r["quality"]
    return {
        "quality_profile": q["profile"], "quality_duplicates": q["duplicates"],
        "quality_referential": q["referential"],
        "quality_completeness_matrix": q["completeness_matrix"].reset_index(),
        "weekly_trend": r["weekly"], "category_weekly_index": r["category_index"].reset_index(),
        "month_profile": r["months"], "holiday_by_series": r["holiday"]["table"],
        "ljung_box": r["ljung_box"], "category_summary": r["categories"], "product_ranking": r["products"],
        "store_summary": r["stores"], "region_summary": r["regions"],
        "waste_category_month": r["waste_category_month"].reset_index(),
        "discount_summary": r["discount"],
        "price_binned": r["price"]["binned"], "price_correlations": r["price"]["correlations"],
        "marketing_binned": r["marketing"]["binned"], "marketing_correlations": r["marketing"]["correlations"],
        "temperature_binned": r["temperature"]["binned"], "temperature_correlations": r["temperature"]["correlations"],
        "rainfall_correlations": r["rainfall"]["correlations"],
        "price_undiscounted_binned": r["price_undiscounted"]["binned"],
        "price_undiscounted_correlations": r["price_undiscounted"]["correlations"],
        "temperature_correlations_month_adjusted": r["temperature_month_adjusted"],
        "rainfall_correlations_month_adjusted": r["rainfall_month_adjusted"],
        "diagnostic_price_by_discount_level": r["price_rule"]["by_level"],
        "diagnostic_waste_generation_rule": r["waste_rule"]["products"],
        "diagnostic_discount_mix": r["discount_mix"],
        "operations_products": r["operations"]["products"], "operations_suppliers": r["operations"]["suppliers"],
        "operations_chilled_stores": r["operations"]["chilled_stores"],
        "operations_correlations": r["operations"]["correlations"],
        "outlier_flags": r["outlier_flags"].loc[r["outlier_flags"]["is_outlier"]],
        "outliers_by_week": r["outliers"]["by_week"], "outliers_by_category": r["outliers"]["by_category"],
        "associational_regression": r["ols_table"], "group_tests": r["group_tests"],
    }


def _versions() -> dict:
    import matplotlib
    import numpy
    import scipy
    import statsmodels

    return {"python": platform.python_version(), "pandas": pd.__version__, "numpy": numpy.__version__,
            "scipy": scipy.__version__, "statsmodels": statsmodels.__version__, "matplotlib": matplotlib.__version__}


def run_eda(run_id: str | None = None, raw: dict | None = None) -> Path:
    """Compute everything and write it to a brand-new outputs/runs/<run_id>/ folder."""
    from dpe.eda import outputs as O
    from dpe.eda import plots as P
    from dpe.eda.report import build_findings, render_markdown

    input_hashes = verify_raw_inputs() if raw is None else {"note": "injected data (tests)"}
    raw = raw if raw is not None else load_raw(verify=False)
    run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "_eda"
    run_dir = new_run_dir(run_id)

    r = compute_all(raw)
    tables = result_tables(r)
    for name, table in tables.items():
        O.save_table(table, run_dir / "tables" / f"{name}.csv")
    for name, make in P.CHARTS.items():
        O.save_figure(make(r), run_dir / "charts" / f"{name}.png")

    findings = build_findings(r)
    O.save_json(findings, run_dir / "findings.json")
    O.save_text(render_markdown(findings, run_id), run_dir / "findings_draft.md")
    q = r["quality"]
    O.save_json({
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dataset_label": DATASET_LABEL,
        "price_note": PRICE_NOTE,
        "inputs_sha256": input_hashes,
        "versions": _versions(),
        "completeness": q["completeness"], "ranges": q["ranges"], "waste_cap": q["waste_cap"],
        "price_variation": q["price_variation"], "ols_info": r["ols_info"],
        "diagnostics": {"price_generation": r["price_rule"]["summary"],
                        "waste_generation": r["waste_rule"]["summary"],
                        "discount_timing": r["discount_timing"]},
        "tables": sorted(tables), "charts": sorted(P.CHARTS),
    }, run_dir / "eda_manifest.json")
    return run_dir
