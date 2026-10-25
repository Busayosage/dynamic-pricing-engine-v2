"""CP1 panel checks on the real V2 data, real-data leakage spot checks, and protected-run integrity.

No model is trained here.
"""
import pandas as pd
import pytest

from dpe import config
from dpe.config import FINAL_EDA_RUN_DIR, UnsafeWriteError, assert_safe_output
from dpe.forecast import features as F
from dpe.forecast.panel import (EXPECTED, KEYS, build_panel, holiday_calendar, reconcile_with_eda, validate_panel,
                                write_panel_run)


@pytest.fixture(scope="module")
def real_panel():
    return build_panel()  # checksum-verified V2 raw files


@pytest.fixture(scope="module")
def real_calendar(real_panel):
    return holiday_calendar(real_panel)


# ------------------------------------------------------------------ CP1
def test_real_panel_dimensions_and_totals(real_panel):
    s = validate_panel(real_panel, expected=EXPECTED)
    assert (s["rows"], s["products"], s["stores"], s["weeks"]) == (37_440, 48, 15, 52)
    assert (s["units"], s["wastage"]) == (61_482_249, 4_786_490)
    assert (s["first_week"], s["last_week"]) == ("2024-01-01", "2024-12-23")


def test_real_panel_keys_preserved_and_week_index(real_panel):
    assert real_panel[KEYS].notna().all().all() and not real_panel.duplicated(subset=KEYS).any()
    wk = real_panel.drop_duplicates("week_index").sort_values("week_index")
    assert list(wk["week_index"]) == list(range(1, 53))
    assert (wk["WeekDate"] == pd.Timestamp("2024-01-01") + pd.to_timedelta((wk["week_index"] - 1) * 7, "D")).all()


def test_real_panel_reconciles_with_final_eda_run(real_panel):
    r = reconcile_with_eda(real_panel)
    assert r["reconciled"], r
    assert r["eda_run"] == config.FINAL_EDA_RUN_ID and r["weeks_compared"] == 52 and r["categories_compared"] == 4


def test_validate_panel_rejects_broken_panels(real_panel):
    small = real_panel[real_panel["week_index"] <= 10]
    with pytest.raises(ValueError, match="Duplicate"):
        validate_panel(pd.concat([small, small.iloc[[0]]]))
    with pytest.raises(ValueError, match="consecutive"):
        validate_panel(small[small["week_index"] != 5])
    with pytest.raises(ValueError, match="expected"):
        validate_panel(small, expected={"rows": 37_440})


def test_real_holiday_calendar(real_calendar):
    assert len(real_calendar) == 6 * 52
    nat = real_calendar.drop_duplicates("week_index").set_index("week_index")["national_holiday_share"]
    assert set(nat[nat == 1].index) == {17, 52}
    assert int(((nat > 0) & (nat < 1)).sum()) == 8


# ------------------------------------------------ CP2 on the real data
@pytest.mark.parametrize("h,n_origins", [(1, 44), (4, 41)])
def test_real_feature_row_counts(real_panel, real_calendar, h, n_origins):
    f = F.build_features(real_panel, real_calendar, h)
    assert len(f) == 720 * n_origins  # origins 8..52-h
    assert (f["origin_week"].min(), f["target_week"].max()) == (8, 52)
    assert f[F.HISTORY_FEATURES].notna().all().all()


@pytest.mark.parametrize("h", [1, 4])
@pytest.mark.parametrize("scenario", ["S0", "S1"])
def test_real_truncation_invariance_at_boundaries(real_panel, real_calendar, h, scenario):
    full = F.build_features(real_panel, real_calendar, h, scenario, plans=real_panel)
    for T in (8, 28, 52 - h):  # first eligible origin, first backtest origin region, last labelled origin
        got = F.build_features(real_panel[real_panel["week_index"] <= T], real_calendar, h, scenario,
                               plans=real_panel, origins=[T])
        pd.testing.assert_frame_equal(got, full[full["origin_week"] == T].reset_index(drop=True), check_exact=True)


def test_write_panel_run_writes_only_a_new_folder(eda_raw):
    import json
    import shutil
    import uuid

    panel = build_panel(eda_raw)
    existing = {p.name for p in config.OUTPUT_ROOT.iterdir()}
    run_id = f"_pytest_{uuid.uuid4().hex}_forecast_panel"
    run_dir = write_panel_run(panel, None, run_id=run_id)
    try:
        assert {p.name for p in config.OUTPUT_ROOT.iterdir()} - existing == {run_id}
        assert sorted(p.name for p in run_dir.iterdir()) == ["forecast_panel.csv", "holiday_calendar.csv",
                                                              "panel_manifest.json"]
        saved = pd.read_csv(run_dir / "forecast_panel.csv")
        assert len(saved) == len(panel) and {"Store_ID", "Product_ID", "WeekDate"} <= set(saved.columns)
        manifest = json.loads((run_dir / "panel_manifest.json").read_text(encoding="utf-8"))
        assert "never a model input" in " ".join(manifest["assumptions"])
        with pytest.raises(FileExistsError):
            write_panel_run(panel, None, run_id=run_id)
    finally:
        shutil.rmtree(run_dir)


# -------------------------------------------------- protected runs
def test_final_eda_run_is_recorded_unchanged_and_write_blocked():
    expected = config.load_expected_checksums()
    hashes = {k: v for k, v in expected.items() if k.startswith(f"outputs/runs/{config.FINAL_EDA_RUN_ID}/")}
    assert len(hashes) == 60
    for rel, digest in hashes.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(FINAL_EDA_RUN_DIR / "tables" / "weekly_trend.csv")


def test_all_recorded_checksums_still_match(protected_registry):
    """Raw data, reference data, legacy copies and every protected run are byte-identical."""
    for rel, digest in protected_registry.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
