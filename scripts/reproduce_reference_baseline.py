r"""Step 3b entry point: reproduce the Oct 2025 Random Forest baseline inside V2.

Do not run until Step 3b execution is approved.
Usage (from the V2 folder):  .\.venv\Scripts\python.exe scripts\reproduce_reference_baseline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dpe.reference_baseline import run  # noqa: E402

if __name__ == "__main__":
    run()
