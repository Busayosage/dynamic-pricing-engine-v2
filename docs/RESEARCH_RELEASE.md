# Research release archive — `dpe-v2-research-results-1.0.0.zip`

The Git repository holds the code, configuration, documentation, tests and the five original training CSVs. The
**saved research results** that the dashboard reads, and that the tests verify, are about 933 MB of CSV and JSON.
That is too large for Git, so they are published separately as a compressed archive attached to the GitHub Release
`v1.0.0`.

The archive contains the protected outputs exactly as they were produced: the same folder structure, file names, run
IDs and bytes. Nothing in it was regenerated for publication.

## Archive facts

| Property | Value |
|---|---|
| File | `dpe-v2-research-results-1.0.0.zip` |
| Size | 68,837,929 bytes (65.6 MB) |
| SHA-256 | `b02c58d0a2dffe2d18a7c36d5abf37901dd48543587a6e9f419c66cfd4cef2f7` |
| Contents | 484 files (933.2 MB uncompressed) plus `RELEASE_MANIFEST.json` |
| Integrity | Every file is listed in `docs/CHECKSUMS.sha256` and in the manifest, with size and SHA-256 |
| Download (after publication) | `https://github.com/Busayosage/dynamic-pricing-engine-v2/releases/download/v1.0.0/dpe-v2-research-results-1.0.0.zip` |

### What it contains

| Folder | Files | Size | Purpose |
|---|---|---|---|
| `data/reference/` | 2 | 5.7 MB | Merged dataset and validation predictions from the original Colab project (reference benchmark) |
| `outputs/runs/20261021-133846_reference_rf` | 3 | 0.3 MB | Verified reproduction of the original Random Forest |
| `outputs/runs/20261021-160432_eda`, `…162605_eda` | 113 | 3.2 MB | Exploratory data analysis (reviewed and final runs) |
| `outputs/runs/20261021-171758_forecast_panel` | 3 | 3.3 MB | Verified weekly forecasting panel |
| `outputs/runs/20261021-175029_baseline_backtest` | 7 | 4.2 MB | Baseline forecast backtest |
| `outputs/runs/20261021-180522_rf_backtest` | 19 | 9.4 MB | Random Forest backtest and accuracy metrics |
| `outputs/runs/20261021-214104_cp5_acceptance` | 13 | 0.3 MB | Forecast acceptance tests |
| `outputs/runs/20261022-011204_challenger_backtest`, `…011554_challenger_evaluation` | 25 | 10.2 MB | XGBoost / CatBoost challenger comparison |
| `outputs/runs/20261022-081926_forecast_contract` | 5 | 23.5 MB | Forecast contract (p10 / p50 / p90) used by every decision engine |
| `outputs/runs/20261022-225527_…`, `…225809_…`, `20261023-081500_…`, `…081809_…` | 92 | 192.0 MB | Inventory replay worked examples and simulations (v1.0, v1.1) |
| `outputs/runs/20261023-131711_policy_comparison` | 59 | 505.4 MB | P0 / P1 / P2 inventory policy comparison (protected baseline) |
| `outputs/runs/20261023-233225_dynamic_pricing_evaluation` | 71 | 87.9 MB | Phase 2 dynamic pricing evaluation, original cooldown rule |
| `outputs/runs/20261024-002535_dynamic_pricing_evaluation_a1` | 72 | 87.8 MB | Phase 2 dynamic pricing evaluation, A1 cooldown rule (preferred research rule) |

### What it does not contain

The six legacy reference copies from the original projects (`legacy/`) are **private and not published**. They
contain machine-specific paths.

- The integrity checks and the test suite treat them as optional only when the whole `legacy/` folder is absent.
- In a public clone, three tests that need the original computer's sibling project folders are skipped, with an
  explanation. Their write-blocking check still runs.

## 1. Verify the download

Compare the SHA-256 with the value above before restoring.

```powershell
# Windows (PowerShell)
Get-FileHash .\dpe-v2-research-results-1.0.0.zip -Algorithm SHA256
```

```bash
# macOS
shasum -a 256 dpe-v2-research-results-1.0.0.zip
# Linux
sha256sum dpe-v2-research-results-1.0.0.zip
```

## 2. Restore it into the project

Run these from the project root, inside the activated Python 3.11 environment.

```bash
python scripts/restore_research_release.py path/to/dpe-v2-research-results-1.0.0.zip --dry-run   # checks only
python scripts/restore_research_release.py path/to/dpe-v2-research-results-1.0.0.zip             # restore
python scripts/restore_research_release.py --verify-only                                         # verify all
```

Expected results:
- **Restore:** `Restored dpe-v2-research-results-1.0.0: 484 file(s) written … all 484 files verified`.
- **Verify-only:** `Registry: 516 files | verified 510 | missing 0 | altered 0 | private legacy copies not present
  (optional): 6`.

### What the restore script guarantees

- **Nothing is written unless every check passes.** These all stop the restore before anything is placed:
  - a file in the archive that is not in its manifest, or a manifest entry missing from the archive
  - an absolute path, a `..` path, or a path outside `outputs/runs/`, `data/reference/` and `legacy/`
  - a file whose SHA-256 does not match `docs/CHECKSUMS.sha256` (for example, the wrong archive version)
- **Files are verified twice.** They are extracted to a temporary folder inside the project, checked (size and
  SHA-256), moved into place, then checked again.
- **Existing files are protected.** Identical files are skipped. A file that differs stops the restore unless you pass
  `--force`, which is then an explicit decision.
- **Windows path length is checked in advance.** If the project folder path is too long for Windows' 260-character
  limit, the script stops with advice, before writing anything.
- **Exit codes:** `0` success, `1` verification failure, `2` usage error or conflict.

## 3. Windows path length

The deepest restored file is 103 characters below the project folder, and several installed Python packages have
deep paths of their own. Without Windows long-path support, keep the project in a **short folder**, for example
`C:\dev\dynamic-pricing-engine-v2`. Both `pip install` and the restore were seen to fail in a deeply nested folder.
Alternatively, enable Windows long-path support (an administrator setting).

## 4. How the archive was built (maintainers)

```bash
python scripts/build_release_archive.py . release --version 1.0.0
```

The builder reads the project and writes `release/dpe-v2-research-results-1.0.0.zip`, its `.sha256` file, and a
separate private `dpe-v2-legacy-reference-1.0.0.zip`, which must **not** be uploaded.

It refuses to package a file that does not match the registry, and never overwrites an existing archive. The
`release/` folder and `dpe-v2-*.zip` files are git-ignored.

## Verification record (2026-10-24)

The archive was restored into fresh clones of the publication file set:
- Python 3.11.9
- a new virtual environment
- dependencies installed from PyPI

All 484 files were restored and verified. Without the private legacy files, the full test suite gave **711 passed, 3
skipped, 0 failed, 0 errors**. All ten dashboard pages loaded without errors.

The restore script's own safety self-test passed 14 of 14 checks:
- tampered contents
- path traversal
- files outside the allowed folders
- files not in the manifest
- the wrong archive version
- conflicting existing files, with and without `--force`
- the dry run
- re-running an identical restore
- a missing archive or registry

This verification was run on **Windows**. On Linux and macOS (Apple Silicon), only the availability of the pinned
dependencies was checked; the code was not run on those systems.
