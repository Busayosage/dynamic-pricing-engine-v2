"""Static notebook validation (the notebook is not executed by the test suite)."""
import ast
import json
import re

import pytest

from dpe.config import PROJECT_ROOT

NB_PATH = PROJECT_ROOT / "notebooks" / "01_eda.ipynb"


@pytest.fixture(scope="module")
def nb():
    return json.loads(NB_PATH.read_text(encoding="utf-8"))


def _code(nb):
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def test_notebook_structure_and_kernel(nb):
    assert nb["nbformat"] == 4
    assert nb["metadata"]["kernelspec"]["language"] == "python"
    assert len(_code(nb)) >= 20


def test_code_cells_are_valid_python(nb):
    for src in _code(nb):
        ast.parse(src)


def test_outputs_cleared(nb):
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            assert c["outputs"] == [] and c["execution_count"] is None


def test_uses_shared_functions_and_v2_data(nb):
    code = "\n".join(_code(nb))
    assert "from dpe.eda" in code and "data.load_raw()" in code
    assert "read_csv" not in code  # data is only loaded through the checksum-verified loader


def test_notebook_writes_no_files(nb):
    code = "\n".join(_code(nb))
    for forbidden in ("to_csv", "savefig", "write_text", "to_excel", "run_eda(", "open("):
        assert forbidden not in code, forbidden


def test_no_absolute_paths_or_credentials():
    text = NB_PATH.read_text(encoding="utf-8")
    assert not re.search(r"\b[A-Za-z]:[\\/]", text)
    assert "Users/Admin" not in text and "Users\\\\Admin" not in text
    assert not re.search(r"pat[A-Za-z0-9]{14}\.[a-f0-9]{20,}", text)
    assert not re.search(r"(?i)(api[_-]?key|airtable_token|bearer)", text)


def test_required_labels_present(nb):
    md = " ".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown").lower()
    for phrase in ("apparently synthetic", "provenance unconfirmed", "descriptive discount lift",
                   "before or after discounts", "one year", "ratio of sums"):
        assert phrase in md, phrase
