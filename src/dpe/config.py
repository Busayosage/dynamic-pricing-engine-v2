"""Central paths and write-safety guard for V2.

Every input is read from this project's data/raw folder, and every output must pass
assert_safe_output(), which refuses any location outside V2 or inside a protected
folder (the original projects, the recovery backups, and V2's own reference copies).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
LEGACY_DIR = PROJECT_ROOT / "legacy"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "runs"
CHECKSUM_FILE = PROJECT_ROOT / "docs" / "CHECKSUMS.sha256"

RAW_FILES = (
    "weekly_sales.csv",
    "product_details.csv",
    "store_info.csv",
    "supplier_info.csv",
    "weather_data.csv",
)

_HUB_DIR = PROJECT_ROOT.parent
_DESKTOP_DIR = _HUB_DIR.parent

# Folders that must never be written to by V2 code.
EXTERNAL_PROTECTED_ROOTS = (
    _DESKTOP_DIR / "perishable_project",
    _HUB_DIR / "dynamic-pricing-engine",
    _HUB_DIR / "Dynamic_Pricing_Recovery_2026-10-21",
)
# Verified Random Forest reproduction (Step 3b). Its files must never be changed.
VERIFIED_RUN_ID = "20261021-133846_reference_rf"
VERIFIED_RUN_DIR = OUTPUT_ROOT / VERIFIED_RUN_ID
# First full EDA run, reviewed in Step 3C-C4. Kept unchanged as the review baseline.
REVIEWED_EDA_RUN_ID = "20261021-160432_eda"
REVIEWED_EDA_RUN_DIR = OUTPUT_ROOT / REVIEWED_EDA_RUN_ID
# Final corrected EDA run (Step 3C-C5); the basis of docs/EDA_FINDINGS.md and the forecast panel reconciliation.
FINAL_EDA_RUN_ID = "20261021-162605_eda"
FINAL_EDA_RUN_DIR = OUTPUT_ROOT / FINAL_EDA_RUN_ID
# Verified forecasting panel (Step 4B CP1); the input to every backtest.
FORECAST_PANEL_RUN_ID = "20261021-171758_forecast_panel"
FORECAST_PANEL_RUN_DIR = OUTPUT_ROOT / FORECAST_PANEL_RUN_ID
# Verified baseline backtest (Step 4B CP3); the benchmark every model is compared against.
BASELINE_RUN_ID = "20261021-175029_baseline_backtest"
BASELINE_RUN_DIR = OUTPUT_ROOT / BASELINE_RUN_ID
# Verified Random Forest backtest (Step 4B CP4); reviewed in CP5, never re-run in place.
RF_BACKTEST_RUN_ID = "20261021-180522_rf_backtest"
RF_BACKTEST_RUN_DIR = OUTPUT_ROOT / RF_BACKTEST_RUN_ID
# CP5 acceptance review (Step 4B CP5); the record behind the approved research-candidate decisions.
CP5_ACCEPTANCE_RUN_ID = "20261021-214104_cp5_acceptance"
CP5_ACCEPTANCE_RUN_DIR = OUTPUT_ROOT / CP5_ACCEPTANCE_RUN_ID
# Step 4D one-round challenger backtest and its evaluation (exploratory; the round is closed).
CHALLENGER_RUN_ID = "20261022-011204_challenger_backtest"
CHALLENGER_RUN_DIR = OUTPUT_ROOT / CHALLENGER_RUN_ID
CHALLENGER_EVAL_RUN_ID = "20261022-011554_challenger_evaluation"
CHALLENGER_EVAL_RUN_DIR = OUTPUT_ROOT / CHALLENGER_EVAL_RUN_ID
# Step 5B-1 forecast contract v1.0 (the input to every downstream decision module).
FORECAST_CONTRACT_RUN_ID = "20261022-081926_forecast_contract"
FORECAST_CONTRACT_RUN_DIR = OUTPUT_ROOT / FORECAST_CONTRACT_RUN_ID
# Step 5B-2 replay simulator runs (SYNTHETIC; DRAFT assumption set AS-2026-10-22-v1).
REPLAY_WORKED_EXAMPLE_RUN_ID = "20261022-225527_replay_worked_example"
REPLAY_WORKED_EXAMPLE_RUN_DIR = OUTPUT_ROOT / REPLAY_WORKED_EXAMPLE_RUN_ID
REPLAY_SIMULATION_RUN_ID = "20261022-225809_replay_simulation"
REPLAY_SIMULATION_RUN_DIR = OUTPUT_ROOT / REPLAY_SIMULATION_RUN_ID
# Replay simulator v1.1 correction runs (23 Oct 2026; the v1.0 runs above are kept for comparison).
REPLAY_WORKED_EXAMPLE_V11_RUN_ID = "20261023-081500_replay_worked_example_v1_1"
REPLAY_WORKED_EXAMPLE_V11_RUN_DIR = OUTPUT_ROOT / REPLAY_WORKED_EXAMPLE_V11_RUN_ID
REPLAY_SIMULATION_V11_RUN_ID = "20261023-081809_replay_simulation_v1_1"
REPLAY_SIMULATION_V11_RUN_DIR = OUTPUT_ROOT / REPLAY_SIMULATION_V11_RUN_ID
# Step 5B-3e controlled P0/P1/P2 policy comparison (SYNTHETIC, exploratory; assumption set v2 DRAFT).
POLICY_COMPARISON_RUN_ID = "20261023-131711_policy_comparison"
POLICY_COMPARISON_RUN_DIR = OUTPUT_ROOT / POLICY_COMPARISON_RUN_ID

INTERNAL_PROTECTED_ROOTS = (RAW_DIR, REFERENCE_DIR, LEGACY_DIR, VERIFIED_RUN_DIR, REVIEWED_EDA_RUN_DIR,
                            FINAL_EDA_RUN_DIR, FORECAST_PANEL_RUN_DIR, BASELINE_RUN_DIR, RF_BACKTEST_RUN_DIR,
                            CP5_ACCEPTANCE_RUN_DIR, CHALLENGER_RUN_DIR, CHALLENGER_EVAL_RUN_DIR,
                            FORECAST_CONTRACT_RUN_DIR, REPLAY_WORKED_EXAMPLE_RUN_DIR, REPLAY_SIMULATION_RUN_DIR,
                            REPLAY_WORKED_EXAMPLE_V11_RUN_DIR, REPLAY_SIMULATION_V11_RUN_DIR, POLICY_COMPARISON_RUN_DIR)
PROTECTED_ROOTS = EXTERNAL_PROTECTED_ROOTS + INTERNAL_PROTECTED_ROOTS


class UnsafeWriteError(RuntimeError):
    """Raised when code attempts to write outside the permitted V2 output area."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def assert_safe_output(path: str | Path) -> Path:
    """Return the resolved path if it is a permitted V2 output location, else raise."""
    resolved = Path(path).resolve()
    if not _is_within(resolved, PROJECT_ROOT.resolve()):
        raise UnsafeWriteError(f"Refusing to write outside V2: {resolved}")
    for root in PROTECTED_ROOTS:
        if _is_within(resolved, root.resolve()):
            raise UnsafeWriteError(f"Refusing to write inside protected folder {root}: {resolved}")
    return resolved


def raw_path(name: str) -> Path:
    """Path of an approved raw dataset inside V2 data/raw (no fallback locations)."""
    if name not in RAW_FILES:
        raise KeyError(f"Not an approved raw dataset: {name}")
    path = RAW_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Required raw dataset missing: {path}")
    return path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_expected_checksums() -> dict[str, str]:
    """Parse docs/CHECKSUMS.sha256 into {relative_path: sha256}."""
    expected: dict[str, str] = {}
    for line in CHECKSUM_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, rel = line.split(maxsplit=1)
        expected[rel.lstrip("*").strip()] = digest
    return expected


def verify_raw_inputs() -> dict[str, str]:
    """Check every raw dataset against the recorded checksum; raise on any mismatch."""
    expected = load_expected_checksums()
    verified: dict[str, str] = {}
    for name in RAW_FILES:
        rel = f"data/raw/{name}"
        actual = sha256_file(raw_path(name))
        if expected.get(rel) != actual:
            raise ValueError(f"Checksum mismatch or missing record for {rel}")
        verified[rel] = actual
    return verified


def new_run_dir(run_id: str, output_root: Path = OUTPUT_ROOT) -> Path:
    """Create a brand-new run folder; never reuses or overwrites an existing one."""
    if not run_id or any(sep in run_id for sep in ("/", "\\", "..")):
        raise ValueError(f"Invalid run_id: {run_id!r}")
    run_dir = assert_safe_output(Path(output_root) / run_id)
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir
