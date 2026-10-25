"""Output safety, chart labelling, wording rules and an end-to-end run on synthetic data."""
import shutil
import uuid

import pandas as pd
import pytest

from dpe import config
from dpe.config import (EXTERNAL_PROTECTED_ROOTS, LEGACY_DIR, OUTPUT_ROOT, RAW_DIR, REFERENCE_DIR,
                        REVIEWED_EDA_RUN_DIR, VERIFIED_RUN_DIR, UnsafeWriteError, assert_safe_output)
from dpe.eda import outputs as O
from dpe.eda import plots as P
from dpe.eda.pipeline import compute_all, result_tables, run_eda
from dpe.eda.report import build_findings, render_markdown


def _verified_run_hashes():
    expected = config.load_expected_checksums()
    return {k: v for k, v in expected.items() if k.startswith("outputs/runs/20261021-133846_reference_rf/")}


@pytest.fixture
def results(eda_raw):
    return compute_all(eda_raw)


# --------------------------------------------------------------- write safety
def test_verified_run_is_recorded_and_unchanged():
    hashes = _verified_run_hashes()
    assert len(hashes) == 3
    for rel, digest in hashes.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel


def test_reviewed_eda_run_is_recorded_unchanged_and_write_blocked():
    expected = config.load_expected_checksums()
    hashes = {k: v for k, v in expected.items() if k.startswith("outputs/runs/20261021-160432_eda/")}
    assert len(hashes) == 53
    for rel, digest in hashes.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(REVIEWED_EDA_RUN_DIR / "findings_draft.md")


@pytest.mark.parametrize("root", [VERIFIED_RUN_DIR, REVIEWED_EDA_RUN_DIR, RAW_DIR, REFERENCE_DIR, LEGACY_DIR,
                                  *EXTERNAL_PROTECTED_ROOTS])
def test_writers_refuse_protected_locations(root):
    target = root / f"_should_not_exist_{uuid.uuid4().hex}.csv"
    with pytest.raises(UnsafeWriteError):
        O.save_table(pd.DataFrame({"a": [1]}), target)
    with pytest.raises(UnsafeWriteError):
        O.save_text("x", target.with_suffix(".md"))
    assert not target.exists() and not target.with_suffix(".md").exists()


def test_verified_run_folder_is_write_blocked():
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(VERIFIED_RUN_DIR / "metrics.json")


def test_writers_never_overwrite():
    run_dir = config.new_run_dir(f"_pytest_{uuid.uuid4().hex}")
    try:
        O.save_text("first", run_dir / "a.md")
        with pytest.raises(FileExistsError):
            O.save_text("second", run_dir / "a.md")
        assert (run_dir / "a.md").read_text(encoding="utf-8") == "first"
    finally:
        shutil.rmtree(run_dir)


# --------------------------------------------------------------------- charts
@pytest.mark.parametrize("name", sorted(P.CHARTS))
def test_every_chart_has_title_labels_and_note(results, name):
    import matplotlib.pyplot as plt

    fig = P.CHARTS[name](results)
    try:
        ax = fig.axes[0]
        assert ax.get_title().strip(), "missing title"
        assert ax.get_xlabel().strip(), "missing x-axis label"
        assert ax.get_ylabel().strip(), "missing y-axis label"
        notes = " ".join(t.get_text() for t in fig.texts)
        assert "Note:" in notes and "provenance unconfirmed" in notes
        # Notes must fit inside the figure, or the saved image widens and squashes the plot.
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        for t in fig.texts:
            assert t.get_window_extent(renderer).x1 <= fig.bbox.x1 + 1, "note wider than figure"
        for label in (ax.xaxis.label, ax.yaxis.label):
            box = label.get_window_extent(renderer)
            assert box.x0 >= -1 and box.y0 >= -1 and box.x1 <= fig.bbox.x1 + 1 and box.y1 <= fig.bbox.y1 + 1, \
                f"axis label clipped: {label.get_text()}"
    finally:
        plt.close(fig)


def test_store_chart_legend_colours_match_bars(results):
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_rgba

    fig = P.CHARTS["09_store_units_per_sqft"](results)
    try:
        ax = fig.axes[0]
        stores = results["stores"].sort_values("units_per_1000_sqft", ascending=False)
        bar_colour = {}
        for patch, region in zip(ax.patches, stores["Region"]):
            bar_colour.setdefault(region, to_rgba(patch.get_facecolor()))
        legend = {t.get_text(): to_rgba(h.get_facecolor())
                  for t, h in zip(ax.get_legend().get_texts(), ax.get_legend().legend_handles)}
        assert set(legend) == set(bar_colour)
        assert all(legend[r] == bar_colour[r] for r in legend)
        assert len(set(legend.values())) == len(legend)  # distinct colour per region
    finally:
        plt.close(fig)


def test_price_chart_separates_unadjusted_and_undiscounted_and_states_adjusted_result(results):
    import matplotlib.pyplot as plt

    fig = P.CHARTS["13_price_relationship"](results)
    try:
        labels = [line.get_label() for line in fig.axes[0].get_lines() if not line.get_label().startswith("_")]
        assert labels == ["All rows (unadjusted)", "Undiscounted rows only"]
        note = " ".join(t.get_text() for t in fig.texts)
        assert "Adjusted for discount" in note and "log-price coefficient" in note
    finally:
        plt.close(fig)


def test_region_chart_uses_singular_store(results):
    import matplotlib.pyplot as plt

    fig = P.CHARTS["10_region_comparison"](results)
    try:
        labels = [t.get_text() for t in fig.axes[0].texts]
        assert any(label.startswith("1 store\n") for label in labels)
        assert not any("1 stores" in label for label in labels)
    finally:
        plt.close(fig)


# -------------------------------------------------------------- wording rules
def test_price_wording_distinguishes_unadjusted_from_adjusted(results):
    findings = build_findings(results)
    price = next(s for s in findings["sections"] if s["title"].startswith("Price"))
    text = " ".join(price["shows"] + price["hypotheses"] + price["cannot_conclude"]).lower()
    assert "lower recorded prices may coincide with higher sales" not in text
    assert "unadjusted" in text and "fixed effects" in text
    lp = results["ols_table"].set_index("term").loc["log_price"]
    if lp["ci_low"] <= 0 <= lp["ci_high"]:
        assert "no detectable association" in text
    assert "no price elasticity is estimated" in text


def test_wastage_and_discount_wording_avoid_real_world_and_causal_claims(results):
    findings = build_findings(results)
    waste = next(s for s in findings["sections"] if s["title"] == "Wastage")
    assert any("do not represent real-world waste behaviour" in x for x in waste["cannot_conclude"])
    discount = next(s for s in findings["sections"] if s["title"].startswith("Discounts"))
    claims = " ".join(discount["shows"] + discount["hypotheses"]).lower()
    for banned in ("discounts cause", "discounts increase", "drive sales", "elasticity"):
        assert banned not in claims
    weekly = next(s for s in findings["sections"] if s["title"].startswith("Weekly"))
    assert any("holiday coefficient" in x for x in weekly["shows"])


def test_manifest_and_tables_include_diagnostics(results):
    tables = result_tables(results)
    for name in ("diagnostic_price_by_discount_level", "diagnostic_waste_generation_rule", "diagnostic_discount_mix",
                 "temperature_correlations_month_adjusted", "rainfall_correlations_month_adjusted",
                 "price_undiscounted_binned", "price_undiscounted_correlations"):
        assert name in tables, name
    assert "consistent_with_post_discount_price" in results["price_rule"]["summary"]
    assert "share_rows_floor_rule" in results["waste_rule"]["summary"]
def test_findings_wording_rules(results):
    findings = build_findings(results)
    md = render_markdown(findings, "test").lower()
    assert "apparently synthetic" in md and "provenance unconfirmed" in md
    assert "before or after any discount" in md
    for s in findings["sections"]:
        claims = " ".join(s["shows"] + s["hypotheses"]).lower()
        for banned in ("recurring", "every year", "annual seasonality", " causes ", "caused by", "proves"):
            assert banned not in claims, (s["title"], banned)
    discount = next(s for s in findings["sections"] if s["title"].startswith("Discounts"))
    text = " ".join(discount["shows"] + discount["hypotheses"] + discount["cannot_conclude"] + [discount["title"]]).lower()
    assert "elasticity" not in text
    assert "descriptive discount lift" in discount["title"].lower()


# ------------------------------------------------------------ end-to-end run
def test_pipeline_writes_only_inside_its_new_run_folder(eda_raw):
    before = {rel: config.sha256_file(config.PROJECT_ROOT / rel) for rel in _verified_run_hashes()}
    existing_runs = set(p.name for p in OUTPUT_ROOT.iterdir())
    run_id = f"_pytest_{uuid.uuid4().hex}_eda"
    run_dir = run_eda(run_id=run_id, raw=eda_raw)
    try:
        assert run_dir.parent == OUTPUT_ROOT.resolve()
        new_entries = set(p.name for p in OUTPUT_ROOT.iterdir()) - existing_runs
        assert new_entries == {run_id}
        for f in run_dir.rglob("*"):
            if f.is_file():
                f.resolve().relative_to(run_dir)
        charts = sorted((run_dir / "charts").glob("*.png"))
        assert len(charts) == len(P.CHARTS) and all(c.stat().st_size > 0 for c in charts)
        tables = sorted((run_dir / "tables").glob("*.csv"))
        assert len(tables) == len(result_tables(compute_all(eda_raw)))
        for name in ("findings.json", "findings_draft.md", "eda_manifest.json"):
            assert (run_dir / name).is_file()
        with pytest.raises(FileExistsError):
            run_eda(run_id=run_id, raw=eda_raw)
    finally:
        shutil.rmtree(run_dir)
    after = {rel: config.sha256_file(config.PROJECT_ROOT / rel) for rel in before}
    assert before == after
