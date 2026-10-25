"""Data must be read from V2, and outputs must never land in the originals or backups."""
import re
import uuid

import pandas as pd
import pytest

from dpe import config, reference_baseline as rb
from dpe.config import (
    EXTERNAL_PROTECTED_ROOTS, OUTPUT_ROOT, PROJECT_ROOT, RAW_DIR, RAW_FILES,
    UnsafeWriteError, assert_safe_output, new_run_dir, raw_path,
)


def test_project_root_is_v2():
    assert PROJECT_ROOT.name == "dynamic-pricing-engine-v2"
    assert RAW_DIR == PROJECT_ROOT / "data" / "raw"


@pytest.mark.parametrize("name", RAW_FILES)
def test_raw_files_resolve_inside_v2(name):
    path = raw_path(name)
    assert path.is_file()
    assert path.resolve().parent == RAW_DIR.resolve()


def test_unknown_raw_file_rejected():
    with pytest.raises(KeyError):
        raw_path("merged_dataset.csv")


def test_raw_inputs_match_recorded_checksums():
    verified = config.verify_raw_inputs()
    assert set(verified) == {f"data/raw/{n}" for n in RAW_FILES}


def test_all_recorded_reference_copies_unchanged(protected_registry):
    """Covers data/raw, data/reference and the legacy scripts and notebook."""
    expected = protected_registry
    assert len(expected) >= 13
    for rel, digest in expected.items():
        assert config.sha256_file(PROJECT_ROOT / rel) == digest, rel


def test_loader_reads_only_from_v2_raw(monkeypatch):
    seen = []
    real_read_csv = pd.read_csv

    def spy(path, *args, **kwargs):
        seen.append(str(path))
        return real_read_csv(path, *args, **kwargs)

    monkeypatch.setattr(rb.pd, "read_csv", spy)
    for name in ("weekly_sales.csv", "product_details.csv", "store_info.csv", "weather_data.csv"):
        rb._load_csv(name)
    assert len(seen) == 4
    for p in seen:
        assert pd.io.common.stringify_path(p).startswith(str(RAW_DIR))


def test_source_code_has_no_hardcoded_machine_paths():
    for f in (PROJECT_ROOT / "src" / "dpe").rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"\b[A-Za-z]:[\\/]", text), f"absolute Windows path in {f.name}"
        assert "Users\\Admin" not in text and "Users/Admin" not in text, f.name


def test_output_allowed_inside_v2_runs():
    assert assert_safe_output(OUTPUT_ROOT / "some_run" / "x.csv")


def test_integrity_scope_leaves_out_only_an_absent_legacy_folder(protected_registry):
    full = config.load_expected_checksums()
    legacy = {rel for rel in full if rel.startswith("legacy/")}
    dropped = set(full) - set(protected_registry)
    if (PROJECT_ROOT / "legacy").exists():
        assert not dropped  # legacy present: every registered file is verified
    else:
        assert dropped == legacy and len(legacy) == 6  # public clone: only the private legacy copies are left out
    assert all(protected_registry[rel] == full[rel] for rel in protected_registry)


@pytest.mark.parametrize("root", EXTERNAL_PROTECTED_ROOTS)
def test_external_protected_folders_exist_and_are_blocked(root):
    with pytest.raises(UnsafeWriteError):  # portable: writes into the original projects are always refused
        assert_safe_output(root / "outputs" / "x.csv")
    if not root.exists():
        pytest.skip(f"original-machine folder '{root.name}' is not part of a public clone; write blocking was verified")
    assert root.exists(), f"expected protected folder not found: {root}"


@pytest.mark.parametrize("sub", ["data/raw/x.csv", "data/reference/x.csv", "legacy/x.py"])
def test_v2_reference_folders_are_blocked(sub):
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(PROJECT_ROOT / sub)


def test_paths_outside_v2_and_traversal_are_blocked():
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(PROJECT_ROOT.parent / "x.csv")
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(OUTPUT_ROOT / ".." / ".." / ".." / "dynamic-pricing-engine" / "x.csv")


def test_sibling_v1_folder_not_confused_with_v2():
    """'dynamic-pricing-engine' must be blocked even though V2's name starts the same way."""
    with pytest.raises(UnsafeWriteError):
        assert_safe_output(PROJECT_ROOT.parent / "dynamic-pricing-engine" / "outputs" / "x.csv")


def test_writers_refuse_protected_paths_and_create_nothing():
    target = EXTERNAL_PROTECTED_ROOTS[0] / f"_should_not_exist_{uuid.uuid4().hex}.json"
    with pytest.raises(UnsafeWriteError):
        rb._write_json({"a": 1}, target)
    with pytest.raises(UnsafeWriteError):
        rb._write_csv(pd.DataFrame({"a": [1]}), target.with_suffix(".csv"))
    assert not target.exists() and not target.with_suffix(".csv").exists()


def test_run_dir_never_reused_and_ids_validated():
    run_id = f"_pytest_{uuid.uuid4().hex}"
    run_dir = new_run_dir(run_id)
    try:
        assert run_dir.parent == OUTPUT_ROOT.resolve()
        with pytest.raises(FileExistsError):
            new_run_dir(run_id)
    finally:
        run_dir.rmdir()
    for bad in ("", "../escape", "a/b", "a\\b"):
        with pytest.raises(ValueError):
            new_run_dir(bad)
