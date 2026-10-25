"""Guarded writers: every path must pass config.assert_safe_output and must not already exist."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dpe.config import assert_safe_output


def _prepare(path) -> Path:
    safe = assert_safe_output(path)
    if safe.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {safe}")
    safe.parent.mkdir(parents=True, exist_ok=True)
    return safe


def _json_default(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    return str(obj)


def save_table(df: pd.DataFrame, path, index: bool = False) -> Path:
    safe = _prepare(path)
    df.to_csv(safe, index=index)
    return safe


def save_figure(fig, path, dpi: int = 150) -> Path:
    import matplotlib.pyplot as plt

    safe = _prepare(path)
    try:
        fig.savefig(safe, dpi=dpi, bbox_inches="tight")
    finally:
        plt.close(fig)
    return safe


def save_json(obj, path) -> Path:
    safe = _prepare(path)
    safe.write_text(json.dumps(obj, indent=2, default=_json_default), encoding="utf-8")
    return safe


def save_text(text: str, path) -> Path:
    safe = _prepare(path)
    safe.write_text(text, encoding="utf-8")
    return safe
