"""Step 5B-2 chronological replay simulator: acceptance criteria S1-S17 and the specific checks requested
(no future leakage incl. a future-sales mutation test, determinism, conservation, lead times, shelf life, no sale
before delivery or after expiry, no duplicated deliveries, opening/closing stock, scenario separation, provenance,
missing-uncertainty review, Christmas escalation, no probability claims). Synthetic panel unless stated."""
import copy
import json
import math
import shutil
import uuid

import numpy as np
import pandas as pd
import pytest

from conftest import fake_contract_predictions, forecast_raw
from dpe import config
from dpe.decision import assumptions as A
from dpe.decision import forecast_contract as FC
from dpe.decision import replay as RP
from dpe.decision import replay_run as RUN
from dpe.decision import review_queue as RQ
from dpe.forecast.panel import build_panel

BANNED = ("probability of stockout", "chance of stockout", "% probability", "stockout probability:",
          "observed lost sale", "will run out on", "expires on", "stockout on", "on day ")


@pytest.fixture(scope="module")
def panel():
    return build_panel(forecast_raw())


@pytest.fixture(scope="module")
def contract(panel):
    return FC.build_contract(fake_contract_predictions(panel), panel, "TEST")["contract"]


@pytest.fixture(scope="module")
def doc():
    return A.load()


@pytest.fixture(scope="module")
def runs(contract, panel, doc):
    return RUN.run_scenarios(contract, panel, doc, trace=True)


def _sc1(runs):
    return runs["SC1"]["result"]


# S4 ------------------------------------------------------------- conservation
@pytest.mark.parametrize("sc", ["SC1", "SC2", "SC3"])
def test_daily_and_weekly_conservation(runs, sc):
    c = runs[sc]["conservation"]
    assert all(c[k] for k in ("daily_balanced", "weekly_balanced", "closing_equals_next_opening",
                              "no_negative_values", "unmet_equals_demand_minus_sold"))
    d = runs[sc]["result"]["daily"]
    assert pd.api.types.is_integer_dtype(d["sim_sold_units"]) and pd.api.types.is_integer_dtype(d["sim_closing_units"])


def test_opening_and_closing_stock(runs):
    r = _sc1(runs)
    d = r["daily"].sort_values(["Store_ID", "Product_ID", "day"])
    first = d.groupby(["Store_ID", "Product_ID"]).head(1)
    attrs = r["attributes"].set_index(["Store_ID", "Product_ID"])
    for row in first.itertuples():
        arr = attrs.loc[(row.Store_ID, row.Product_ID), "delivery_arrangement"]
        if arr == "SHORT_LIFE_RECURRING_DROPS":
            assert row.sim_opening_units == 0  # short-life items start empty
        else:
            assert row.sim_opening_units > 0  # long-life opening cover (SYNTHETIC)
    w = r["weekly"].sort_values(["Store_ID", "Product_ID", "week"])
    nxt = w.groupby(["Store_ID", "Product_ID"])["sim_opening_units"].shift(-1)
    assert ((nxt.isna()) | (nxt == w["sim_closing_units"])).all()


# S3 --------------------------------------------------------------- determinism
def test_replay_is_deterministic(contract, panel, doc, runs):
    again = RUN.run_scenarios(contract, panel, doc, scenarios=("SC2",), trace=True)["SC2"]["result"]
    for name in ("decisions", "deliveries", "daily", "weekly", "sales_trace"):
        pd.testing.assert_frame_equal(again[name], runs["SC2"]["result"][name])


# S1 + mutation test --------------------------------------------------- leakage
@pytest.mark.parametrize("cutoff", [17, 22, 26])
def test_altering_future_sales_does_not_change_earlier_decisions(contract, panel, doc, runs, cutoff):
    """Mutation test: deliberately alter all sales and contract forecasts after the cut-off week."""
    rng = np.random.default_rng(cutoff)
    p2 = panel.copy()
    later = p2["week_index"] > cutoff
    p2.loc[later, "Units_Sold"] = rng.integers(1, 5_000, int(later.sum()))
    c2 = contract.copy()
    fut = c2["origin_week"] > cutoff
    for col in ("predicted_units", "lower_p10_units", "median_p50_units", "upper_p90_units"):
        c2.loc[fut & c2[col].notna(), col] = c2.loc[fut & c2[col].notna(), col] * 3
    v = A.resolve(doc, "SC1")
    got = RP.simulate(c2, p2, v)
    base = _sc1(runs)
    keep = lambda df, col, lim: df[df[col] <= lim].reset_index(drop=True)  # noqa: E731
    pd.testing.assert_frame_equal(keep(got["decisions"], "origin_week", cutoff), keep(base["decisions"], "origin_week", cutoff))
    pd.testing.assert_frame_equal(keep(got["daily"], "week", cutoff), keep(base["daily"], "week", cutoff))
    assert not got["daily"].equals(base["daily"])  # later weeks did change: the test can see a difference


def test_truncated_history_gives_identical_earlier_decisions(contract, panel, doc, runs):
    base = _sc1(runs)
    K = 24
    origins = [o for o in base["origins"] if o <= K - 1]
    got = RP.simulate(contract[contract["origin_week"] <= K - 1], panel[panel["week_index"] <= K], A.resolve(doc, "SC1"),
                      origins=origins)
    pd.testing.assert_frame_equal(got["decisions"], base["decisions"][base["decisions"]["origin_week"] <= K - 1]
                                  .reset_index(drop=True))


# S2 ---------------------------------------------------------------- chronology
def test_demand_is_read_only_after_the_decision(runs):
    log = _sc1(runs)["demand_log"]
    assert log and all(week == decided + 1 for week, decided in log)
    guard = RP.DemandAccess({(1, 1, 5): 10}, 1.0, [1 / 7] * 7)
    with pytest.raises(RP.ChronologyError):
        guard.week_demand((1, 1), 5)  # nothing decided yet
    guard.decided_through_origin = 3
    with pytest.raises(RP.ChronologyError):
        guard.week_demand((1, 1), 5)  # week 5 needs the decision for origin 4


# S5 ---------------------------------------------------------------- daily split
def test_daily_demand_split_is_exact(runs, panel):
    for sc in ("SC1", "SC2"):
        d = runs[sc]["result"]["daily"]
        m = runs[sc]["values"]["demand_multiplier"]
        tot = d.groupby(["Store_ID", "Product_ID", "week"])["sim_demand_units_illustrative"].sum()
        rec = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"]
        assert all(tot[k] == int(round(rec[k] * m)) for k in tot.index)
    assert RP.split_week(1018, [1 / 7] * 7) == [146, 146, 146, 145, 145, 145, 145]


# S6 --------------------------------------------------------------- lead times
@pytest.mark.parametrize("sc", ["SC1", "SC2"])
def test_orders_arrive_only_on_day_one_plus_lead_time(runs, sc):
    r = runs[sc]["result"]
    dec = r["decisions"].dropna(subset=["order_id"]).set_index("order_id")
    dl = r["deliveries"][r["deliveries"]["kind"] == "ORDER"]
    first = dl.sort_values("arrival_day").groupby("order_id").head(1)
    for row in first.itertuples():
        dd = dec.loc[row.order_id]
        assert row.arrival_day == dd["decision_day"] + dd["effective_lead_time_days"]
        assert row.arrival_dow == 1 + dd["effective_lead_time_days"]  # never available from Monday
    assert (dl.merge(dec[["decision_day"]], left_on="order_id", right_index=True).eval("arrival_day > decision_day")).all()


# S7 + no sale before delivery / after expiry ------------------------ shelf life
def test_no_sale_before_delivery_or_after_expiry(runs):
    for sc in ("SC1", "SC2", "SC3"):
        t = runs[sc]["result"]["sales_trace"]
        assert (t["day"] >= t["arrival_day"]).all() and (t["day"] <= t["expiry_day"]).all()


def test_shelf_life_and_short_life_drop_schedule(runs):
    r = _sc1(runs)
    attrs = r["attributes"].set_index(["Store_ID", "Product_ID"])
    dl = r["deliveries"]
    for row in dl.itertuples():
        R = attrs.loc[(row.Store_ID, row.Product_ID), "remaining_life_days"]
        assert row.expiry_day - row.arrival_day + 1 == R
    orders = dl[dl["kind"] == "ORDER"]
    for oid, g in orders.groupby("order_id"):
        k = (g["Store_ID"].iloc[0], g["Product_ID"].iloc[0])
        R, arr = attrs.loc[k, "remaining_life_days"], attrs.loc[k, "delivery_arrangement"]
        if arr == "SHORT_LIFE_RECURRING_DROPS":
            assert len(g) <= math.ceil(7 / R) and g["days_covered"].sum() <= 7
            assert (np.diff(sorted(g["arrival_day"])) % R == 0).all()
        else:
            assert len(g) == 1 and g["days_covered"].iloc[0] == 7
    # Long-life lots carry over across weeks.
    t = r["sales_trace"]
    assert ((t["day"] - 1) // 7 > (t["arrival_day"] - 1) // 7).any()


def test_short_life_lots_carry_over_the_week_boundary(contract, panel, doc):
    """Bread with transit age 0 (R = 3) and lead time 1 + 2 = 3: drops on Thu, Sun, Wed; the Sunday lot sells on Monday."""
    v = A.resolve(doc, "SC1")
    v.update(transit_age_days=0, lead_time_adjustment_days=2)
    r = RP.simulate(contract, panel, v, series=[(500, 1000)], trace=True)
    assert r["attributes"]["remaining_life_days"].iloc[0] == 3
    t = r["sales_trace"]
    cross = t[((t["day"] - 1) // 7 > (t["arrival_day"] - 1) // 7)]
    assert len(cross) > 0 and (cross["day"] <= cross["expiry_day"]).all()
    assert RP.check_conservation(r["daily"], r["weekly"])["daily_balanced"]


def test_expired_units_leave_stock_at_end_of_last_sellable_day(runs):
    r = _sc1(runs)
    d = r["daily"]
    assert d["sim_expired_units"].sum() > 0
    dl = r["deliveries"]
    sold = r["sales_trace"].groupby("delivery_id")["units"].sum()
    received_ids = dl[dl["arrival_day"] <= d["day"].max()]
    last_day = d["day"].max()
    exp = d.groupby(["Store_ID", "Product_ID"])["sim_expired_units"].sum()
    for k, g in received_ids[received_ids["expiry_day"] <= last_day].groupby(["Store_ID", "Product_ID"]):
        unsold = (g.set_index("delivery_id")["delivered_units"] - sold.reindex(g["delivery_id"]).fillna(0).to_numpy()).sum()
        assert unsold <= exp.loc[k] + 1e-9


# no duplicated deliveries ---------------------------------------------------
def test_each_delivery_is_unique_and_received_exactly_once(runs):
    for sc in ("SC1", "SC2", "SC3"):
        r = runs[sc]["result"]
        dl = r["deliveries"]
        assert dl["delivery_id"].is_unique
        assert not dl.duplicated(subset=["Store_ID", "Product_ID", "arrival_day", "kind", "order_id"]).any()
        last = r["daily"]["day"].max()
        within = dl[dl["arrival_day"] <= last]
        assert int(within["delivered_units"].sum()) == int(r["daily"]["sim_received_units"].sum())
        # Short-life coverage windows tile without overlap: at most one ORDER drop per series and day.
        o = dl[dl["kind"] == "ORDER"]
        assert not o.duplicated(subset=["Store_ID", "Product_ID", "arrival_day"]).any()


def test_monday_order_drop_count_is_explicit(runs):
    r = _sc1(runs)
    d = r["decisions"].dropna(subset=["order_id"])
    dl = r["deliveries"][r["deliveries"]["kind"] == "ORDER"].groupby("order_id").size()
    assert (d.set_index("order_id")["n_deliveries"] == dl.reindex(d["order_id"]).fillna(0).to_numpy()).all()
    attrs = r["attributes"]
    assert set(attrs["drops_per_order"]) <= {1, 2, 3, 4, 7}
    assert (attrs.loc[attrs["delivery_arrangement"] == "LONG_LIFE_WEEKLY", "drops_per_order"] == 1).all()


# S8 ---------------------------------------------------------------- rounding
def test_orders_are_whole_cases_and_meet_moq(runs, doc):
    v = A.resolve(doc, "SC1")
    r = _sc1(runs)
    cat = r["attributes"].set_index("Product_ID")["Product_Category"].to_dict()
    dl = r["deliveries"][r["deliveries"]["ordered_units"] > 0]
    for row in dl.itertuples():
        case = v["case_size_units"][cat[row.Product_ID]]
        assert row.ordered_units % case == 0 and row.ordered_units >= v["moq_cases_per_delivery"] * case
    assert (r["decisions"]["ordered_units"] >= 0).all()


# scenario separation and S14 direction -------------------------------------
def test_scenarios_are_separate_and_reproducible(contract, panel, doc, runs):
    ids = {sc: set(runs[sc]["result"]["deliveries"]["order_id"].dropna()) for sc in runs}
    assert not (ids["SC1"] & ids["SC2"]) and not (ids["SC1"] & ids["SC3"])
    for sc in runs:
        for name in ("decisions", "daily", "weekly"):
            assert set(runs[sc]["result"][name]["scenario_id"]) == {sc}
    alone = RUN.run_scenarios(contract, panel, doc, scenarios=("SC1",), trace=True)["SC1"]["result"]
    pd.testing.assert_frame_equal(alone["weekly"], runs["SC1"]["result"]["weekly"])


def test_scenario_directions(runs):
    k = {sc: runs[sc]["kpis"] for sc in runs}
    assert k["SC2"]["unmet_units_illustrative"] > k["SC1"]["unmet_units_illustrative"]
    assert k["SC2"]["pre_order_shortage"] >= k["SC1"]["pre_order_shortage"]
    assert k["SC3"]["expired_units"] > k["SC1"]["expired_units"]
    assert k["SC3"]["waste_high_existing_stock"] >= k["SC1"]["waste_high_existing_stock"]


# S9 / S10 ------------------------------------------------- provenance, wording
def test_provenance_labels_and_watermarks(runs):
    for sc in runs:
        r = runs[sc]["result"]
        for name in ("daily", "weekly"):
            sim_cols = [c for c in r[name].columns if c not in ("Store_ID", "Product_ID", "week", "dow", "day", "scenario_id",
                                                                 "assumption_set_id", "simulator_version", "watermark", "label")]
            assert sim_cols and all(c.startswith("sim_") for c in sim_cols)
            assert r[name]["watermark"].str.contains("ASSUMED/SYNTHETIC").all()
            assert r[name]["watermark"].str.contains("DRAFT").all()  # the assumption file is still DRAFT
        assert (r["daily"]["label"] == RP.DAILY_LABEL).all()
        assert (r["decisions"]["assumption_set_id"] == "AS-2026-10-22-v1").all()
        assert any("illustrative" in c for c in r["daily"].columns if "demand" in c or "unmet" in c)


def test_no_probability_or_daily_prediction_claims(runs):
    texts = []
    for sc in runs:
        r = runs[sc]["result"]
        for name in ("decisions", "daily", "weekly", "deliveries"):
            df = r[name]
            texts += [str(x).lower() for c in df.columns if df[c].dtype == object for x in df[c].unique()]
            texts += [c.lower() for c in df.columns]
        texts += [str(x).lower() for x in runs[sc]["cases"]["reasons"].unique()]
    blob = " | ".join(texts)
    for phrase in BANNED:
        assert phrase not in blob, phrase
    assert "not a stockout probability" in RP.POSITION_NOTE


# S11 / S12 / S13 ------------------------------------------------- review queue
def test_missing_uncertainty_requires_review_and_no_automatic_order(contract, panel, doc, runs):
    cases = runs["SC1"]["cases"]
    missing_points = contract[contract["uncertainty_status"] != "AVAILABLE"][["store_id", "product_id", "origin_week"]].drop_duplicates()
    m = missing_points.merge(cases, on=["store_id", "product_id", "origin_week"])
    assert len(m) == len(missing_points) and (m["case_type"].isin(["MANDATORY_REVIEW", "MANDATORY_ESCALATION"])).all()
    # Force one simulated origin to be unavailable: no automatic order, MANDATORY_REVIEW.
    c2 = contract.copy()
    T = _sc1(runs)["origins"][3]
    hit = (c2["horizon_weeks"] == 1) & (c2["origin_week"] == T) & (c2["store_id"] == 500) & (c2["product_id"] == 1000)
    c2.loc[hit, ["lower_p10_units", "median_p50_units", "upper_p90_units"]] = np.nan
    c2.loc[hit, "uncertainty_status"] = "UNAVAILABLE_INSUFFICIENT_HISTORY"
    v = A.resolve(doc, "SC1")
    res = RP.simulate(c2, panel, v, origins=_sc1(runs)["origins"])
    row = res["decisions"].query("Store_ID == 500 and Product_ID == 1000 and origin_week == @T").iloc[0]
    assert row["ordered_units"] == 0 and row["order_basis"] == "NO_AUTOMATIC_ORDER_UNCERTAINTY_UNAVAILABLE"
    cs = RQ.build_cases(c2, res["decisions"], v).query("store_id == 500 and product_id == 1000 and origin_week == @T")
    assert cs["case_type"].iloc[0] == "MANDATORY_REVIEW" and "UNCERTAINTY_UNAVAILABLE" in cs["reasons"].iloc[0]


def test_unsupported_delivery_arrangement_requires_review(contract, panel, doc):
    v = A.resolve(doc, "SC1")
    v["lead_time_adjustment_days"] = 6  # outside the approved range on purpose: lead time >= 7 days
    res = RP.simulate(contract, panel, v)
    assert (res["decisions"]["ordered_units"] == 0).all()
    assert (res["attributes"]["delivery_arrangement"] == "UNSUPPORTED").all()
    cases = RQ.build_cases(contract, res["decisions"], v)
    sim = cases[cases["simulated_decision"]]
    assert sim["reasons"].str.contains("UNSUPPORTED_DELIVERY_ARRANGEMENT").all()


def test_one_case_per_decision_point_and_holiday_only_creates_no_case(runs):
    for sc in runs:
        cases = runs[sc]["cases"]
        assert not cases.duplicated(subset=["store_id", "product_id", "origin_week"]).any()
        assert RQ.case_summary(cases)["duplicate_cases"] == 0
        only_holiday = cases[cases["holiday_flag"] & (cases["material_trigger_count"] == 0)
                             & ~cases["reasons"].str.contains("UNCERTAINTY_UNAVAILABLE|CHRISTMAS|UNSUPPORTED")]
        assert only_holiday["case_type"].isna().all()


@pytest.fixture(scope="module")
def real_contract():
    return pd.read_csv(config.FORECAST_CONTRACT_RUN_DIR / "forecast_contract.csv")


def test_real_christmas_escalation_and_case_counts(real_contract, doc):
    v = A.resolve(doc, "SC1")
    empty = pd.DataFrame(columns=["Store_ID", "Product_ID", "origin_week", "flags"])
    cases = RQ.build_cases(real_contract, empty, v)
    xmas = real_contract[real_contract["target_week"].isin([51, 52])][["store_id", "product_id", "origin_week"]].drop_duplicates()
    m = xmas.merge(cases, on=["store_id", "product_id", "origin_week"])
    assert len(m) == 2_880 and (m["case_type"] == "MANDATORY_ESCALATION").all()
    s = RQ.case_summary(cases)
    assert s["decision_points"] == 19_440 and s["by_type"] == {"MANDATORY_REVIEW": 5_040, "MANDATORY_ESCALATION": 2_880}
    assert s["holiday_only_flagged_no_case"] > 0 and s["duplicate_cases"] == 0


# S15 / S16 --------------------------------------------------- sensitivity, safety
def test_sensitivity_directional_checks(contract, panel, doc):
    checks = RUN.directional_checks(contract, panel, doc)
    assert all(checks.values()), checks


def test_simulator_makes_no_price_or_discount_recommendations(runs):
    for sc in runs:
        cols = " ".join(runs[sc]["result"]["decisions"].columns).lower()
        assert "discount" not in cols and "price" not in cols
    f = A.feasibility(A.load())
    assert all(v["largest_allowed_step_pct"] <= 25 for v in f.values())


# real-data worked example and output safety -------------------------------------
def test_real_worked_example_reproduces_design_figures(real_contract, doc):
    from dpe.forecast.panel import load_verified_panel

    panel, _ = load_verified_panel()
    r = RP.simulate(real_contract, panel, A.resolve(doc, "SC1"), series=[(505, 1001), (505, 1025)], trace=True)
    w = r["weekly"].set_index(["Product_ID", "week"])
    assert (w.loc[(1001, 45), "sim_received_units"], w.loc[(1001, 45), "sim_expired_units"]) == (1428, 410)
    assert w.loc[(1025, 46), "sim_expired_units"] == 397
    d = r["decisions"].set_index(["Product_ID", "origin_week"])
    assert d.loc[(1001, 44), "ordered_units"] == 1428 and d.loc[(1001, 44), "n_deliveries"] == 7
    assert d.loc[(1025, 44), "ordered_units"] == 2676 and "TARGET_ABOVE_P90_CAPPED" in d.loc[(1025, 44), "flags"]
    assert r["origins"][0] == 32 and RP.check_conservation(r["daily"], r["weekly"])["daily_balanced"]


@pytest.mark.parametrize("run_id,run_dir,n_files", [
    (config.REPLAY_WORKED_EXAMPLE_RUN_ID, config.REPLAY_WORKED_EXAMPLE_RUN_DIR, 24),
    (config.REPLAY_SIMULATION_RUN_ID, config.REPLAY_SIMULATION_RUN_DIR, 22),
    (config.REPLAY_WORKED_EXAMPLE_V11_RUN_ID, config.REPLAY_WORKED_EXAMPLE_V11_RUN_DIR, 24),
    (config.REPLAY_SIMULATION_V11_RUN_ID, config.REPLAY_SIMULATION_V11_RUN_DIR, 22),
])
def test_replay_runs_are_recorded_unchanged_and_write_blocked(run_id, run_dir, n_files):
    expected = {k: v for k, v in config.load_expected_checksums().items() if k.startswith(f"outputs/runs/{run_id}/")}
    assert len(expected) == n_files
    for rel, digest in expected.items():
        assert config.sha256_file(config.PROJECT_ROOT / rel) == digest, rel
    with pytest.raises(config.UnsafeWriteError):
        config.assert_safe_output(run_dir / "manifest.json")


def test_run_writes_only_a_new_folder(runs, doc):
    existing = {p.name for p in config.OUTPUT_ROOT.iterdir()}
    run_id = f"_pytest_{uuid.uuid4().hex}_replay"
    run_dir = RUN.write_run(runs, doc, "replay", run_id=run_id)
    try:
        assert {p.name for p in config.OUTPUT_ROOT.iterdir()} - existing == {run_id}
        m = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert m["assumption_set"]["status"] == "DRAFT" and "not a causal effect" in m["statements"]["discount_uplift"]
        for sc in ("SC1", "SC2", "SC3"):
            for f in ("decisions.csv", "deliveries.csv", "daily.csv", "weekly.csv", "review_cases.csv", "scenario_summary.json"):
                assert (run_dir / sc / f).is_file()
        with pytest.raises(FileExistsError):
            RUN.write_run(runs, doc, "replay", run_id=run_id)
    finally:
        shutil.rmtree(run_dir)
