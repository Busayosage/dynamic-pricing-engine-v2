import os

os.environ.setdefault("MPLBACKEND", "Agg")  # charts render without a display in tests

import numpy as np
import pandas as pd
import pytest

SERIES_BASE = {(500, 1000): 1000, (500, 1001): 2000, (501, 1000): 3000, (501, 1001): 4000}
N_WEEKS = 12


@pytest.fixture
def synthetic_inputs():
    """Tiny, fully known dataset: 2 stores x 2 products x 12 weeks.

    Units_Sold = series base + week number, so every lag and rolling value is predictable
    and any mixing between series would be obvious.
    """
    rows = []
    for (store, product), base in SERIES_BASE.items():
        for w in range(1, N_WEEKS + 1):
            rows.append({
                "Week_Number": f"2024-W{w:02d}", "Product_ID": product, "Store_ID": store,
                "Units_Sold": base + w, "Marketing_Spend": 100.0 + w, "Discount_Percent": 0,
                "Wastage_Units": 5, "Price": 2.5,
            })
    sales = pd.DataFrame(rows)
    product = pd.DataFrame({
        "Product_ID": [1000, 1001], "Product_Name": ["Bread", "Milk"],
        "Product_Category": ["Bakery", "Dairy"], "Shelf_Life_Days": [4, 10], "Supplier_ID": [1, 2],
    })
    store = pd.DataFrame({
        "Store_ID": [500, 501], "Region": ["London", "Midlands"],
        "Store_Size": [12000, 5000], "Cold_Storage_Capacity": [3788, 1086],
    })
    weather = pd.DataFrame([
        {"Week_Number": f"2024-W{w:02d}", "Region": r, "Avg_Temperature": 10.0,
         "Rainfall": 20.0, "Holiday_Flag": 0}
        for w in range(1, N_WEEKS + 1) for r in ("London", "Midlands")
    ])
    return sales, product, store, weather


def forecast_raw(n_weeks=30, seed=0):
    """Raw tables for forecasting tests: 3 products x 3 stores x n_weeks with noisy units (so models and
    baselines differ), varied discounts and a London holiday in weeks 1 and 20."""
    rng = np.random.default_rng(seed)
    products = {1000: ("Bread", "Bakery", 3, 1), 1001: ("Milk", "Dairy", 10, 2), 1002: ("Yoghurt", "Dairy", 14, 1)}
    stores = {500: ("London", 10000, 2000), 501: ("London", 5000, 1000), 502: ("Midlands", 4000, 800)}
    sales = [{"Week_Number": f"2024-W{w:02d}", "Product_ID": p, "Store_ID": s,
              "Units_Sold": int(100 * (pi + 1) + 10 * si + w + rng.integers(0, 40)),
              "Marketing_Spend": float(100 + rng.integers(0, 50)), "Discount_Percent": int(rng.choice([0, 0, 10])),
              "Wastage_Units": 5, "Price": float(2 + rng.random())}
             for pi, p in enumerate(products) for si, s in enumerate(stores) for w in range(1, n_weeks + 1)]
    weather = [{"Week_Number": f"2024-W{w:02d}", "Region": r, "Avg_Temperature": 5.0 + w, "Rainfall": 10.0,
                "Holiday_Flag": int(r == "London" and w in (1, 20))}
               for w in range(1, n_weeks + 1) for r in ("London", "Midlands")]
    return {"weekly_sales": pd.DataFrame(sales),
            "product_details": pd.DataFrame([{"Product_ID": k, "Product_Name": v[0], "Product_Category": v[1],
                                              "Shelf_Life_Days": v[2], "Supplier_ID": v[3]} for k, v in products.items()]),
            "store_info": pd.DataFrame([{"Store_ID": k, "Region": v[0], "Store_Size": v[1],
                                         "Cold_Storage_Capacity": v[2]} for k, v in stores.items()]),
            "supplier_info": pd.DataFrame({"Supplier_ID": [1, 2], "Supplier_Name": ["A", "B"],
                                           "Lead_Time_Days": [1, 3], "Supply_Capacity": [1000, 2000]}),
            "weather_data": pd.DataFrame(weather)}


FAKE_FIRST_ORIGIN, FAKE_LAST_TARGET = 10, 30


def fake_contract_predictions(panel, seed=0):
    """Out-of-sample-style predictions on a synthetic panel (H1 'random_forest', H4 'mean_4w'):
    forecast = mean of weeks T-3..T x noise. Used to build synthetic forecast contracts in tests."""
    rng = np.random.default_rng(seed)
    u = panel.set_index(["Store_ID", "Product_ID", "week_index"])["Units_Sold"]
    dates = panel.drop_duplicates("week_index").set_index("week_index")["WeekDate"]
    rows = []
    for h, m in ((1, "random_forest"), (4, "mean_4w")):
        for (s, p) in panel[["Store_ID", "Product_ID"]].drop_duplicates().itertuples(index=False):
            for t in range(FAKE_FIRST_ORIGIN + h, FAKE_LAST_TARGET + 1):
                o = t - h
                fc = np.mean([u[(s, p, w)] for w in range(o - 3, o + 1)]) * rng.uniform(0.9, 1.1)
                rows.append({"Store_ID": s, "Product_ID": p, "origin_week": o, "origin_date": dates[o], "target_week": t,
                             "target_date": dates[t], "horizon": h, "model": m, "actual": u[(s, p, t)], "forecast": fc})
    return pd.DataFrame(rows)


EDA_WEEKS = 16
EDA_PRODUCTS = {1000: ("Bread", "Bakery", 3, 1), 1001: ("Milk", "Dairy", 10, 2), 1002: ("Yoghurt", "Dairy", 14, 1)}
EDA_STORES = {500: ("London", 10000, 2000), 501: ("London", 5000, 1000), 502: ("Midlands", 4000, 800)}


@pytest.fixture
def eda_raw():
    """Synthetic raw tables (3 products x 3 stores x 16 weeks) with known totals.

    Units = 100*(product index + 1) + 10*store index + week; wastage = 5 + product index.
    Weather includes an extra region (Wales) with no stores, like the real data.
    """
    sales = []
    for pi, pid in enumerate(EDA_PRODUCTS):
        for si, sid in enumerate(EDA_STORES):
            for w in range(1, EDA_WEEKS + 1):
                sales.append({
                    "Week_Number": f"2024-W{w:02d}", "Product_ID": pid, "Store_ID": sid,
                    "Units_Sold": 100 * (pi + 1) + 10 * si + w,
                    "Marketing_Spend": 100.0 + 5 * w * (si + 1),
                    "Discount_Percent": 10 if (w + si) % 4 == 0 else 0,
                    "Wastage_Units": 5 + pi,
                    "Price": round(2.0 + 0.1 * ((w + pi + si) % 5), 2),
                })
    product = pd.DataFrame([{"Product_ID": k, "Product_Name": v[0], "Product_Category": v[1],
                             "Shelf_Life_Days": v[2], "Supplier_ID": v[3]} for k, v in EDA_PRODUCTS.items()])
    store = pd.DataFrame([{"Store_ID": k, "Region": v[0], "Store_Size": v[1], "Cold_Storage_Capacity": v[2]}
                          for k, v in EDA_STORES.items()])
    supplier = pd.DataFrame({"Supplier_ID": [1, 2], "Supplier_Name": ["Alpha Foods", "Beta Dairy"],
                             "Lead_Time_Days": [1, 3], "Supply_Capacity": [1000, 2000]})
    weather = []
    for w in range(1, EDA_WEEKS + 1):
        weather.append({"Week_Number": f"2024-W{w:02d}", "Region": "London", "Avg_Temperature": 5.0 + w,
                        "Rainfall": 10.0 + (w % 3), "Holiday_Flag": 1 if w in (1, 10) else 0})
        weather.append({"Week_Number": f"2024-W{w:02d}", "Region": "Midlands", "Avg_Temperature": 3.0 + 0.5 * w,
                        "Rainfall": 10.0 + 2 * (w % 3), "Holiday_Flag": 0})
        weather.append({"Week_Number": f"2024-W{w:02d}", "Region": "Wales", "Avg_Temperature": 6.0,
                        "Rainfall": 30.0, "Holiday_Flag": 0})
    return {"weekly_sales": pd.DataFrame(sales), "product_details": product, "store_info": store,
            "supplier_info": supplier, "weather_data": pd.DataFrame(weather)}


# --- Integrity scope for public clones (approved 2026-10-24) ------------------------------------------------------
# The six registered legacy reference copies are private and not published. They are left out of an integrity check
# ONLY when the whole legacy/ folder is absent. If legacy/ exists, every registered legacy file is required and
# verified exactly as before. Raw data, reference data, config and every research run are never left out.
LEGACY_PREFIX = "legacy/"


def _legacy_absent() -> bool:
    from dpe import config

    return not (config.PROJECT_ROOT / LEGACY_PREFIX.rstrip("/")).exists()


def _scoped(registry: dict[str, str]) -> dict[str, str]:
    if _legacy_absent():
        return {rel: digest for rel, digest in registry.items() if not rel.startswith(LEGACY_PREFIX)}
    return registry


@pytest.fixture
def protected_registry() -> dict[str, str]:
    """Registered checksums to verify in this checkout (docs/CHECKSUMS.sha256, legacy scope as above)."""
    from dpe import config

    return _scoped(config.load_expected_checksums())


@pytest.fixture
def registry_scope(monkeypatch):
    """Apply the same legacy scope to production pre-run checks, for this test only; nothing is patched when
    legacy/ is present."""
    from dpe import config

    if _legacy_absent():
        original = config.load_expected_checksums
        monkeypatch.setattr(config, "load_expected_checksums", lambda: _scoped(original()))
