"""Step 5B-2: the versioned assumption set (config/assumptions/assumption_set_v1.json).

- content_sha256 covers everything except the approval block, so approving a file (status, approver, date) does
  not change its content hash, while any change to a value does. An APPROVED file whose content hash no longer
  matches is rejected: changes must create a new version (new assumption_set_id and version number).
- validate() implements rules V1-V8 of docs/STEP_5B2_BUSINESS_ASSUMPTIONS_DESIGN.md section 2.4.
- resolve() applies a scenario's overrides and returns one flat, validated parameter view per scenario.
All ASSUMED / SYNTHETIC values are illustrative; none is an observed business fact.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

from dpe.config import PROJECT_ROOT

ASSUMPTION_DIR = PROJECT_ROOT / "config" / "assumptions"
DEFAULT_FILE = ASSUMPTION_DIR / "assumption_set_v1.json"
CATEGORIES = ("Bakery", "Beverages", "Dairy", "Meat")
REQUIRED_FIELDS = ("key", "value", "unit", "granularity", "scope", "provenance", "evidence",
                   "supported_by_observed_business_data", "rationale", "allowed_range")
PROVENANCES = ("OBSERVED", "CALCULATED", "ASSUMED", "SYNTHETIC")
REQUIRED_STATEMENTS = ("illustrative", "discount_uplift", "demand", "uncertainty")
SCENARIOS = ("SC1", "SC2", "SC3")


class AssumptionError(ValueError):
    pass


def content_sha256(doc: dict) -> str:
    """Hash of the canonical JSON content, excluding the approval block."""
    body = {k: v for k, v in doc.items() if k != "approval"}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def load(path: Path = DEFAULT_FILE) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    validate(doc)
    return doc


def _values(v):
    return list(v.values()) if isinstance(v, dict) else (list(v) if isinstance(v, list) else [v])


def _check_range(p: dict, value, errs: list) -> None:
    r = p["allowed_range"]
    key = p["key"]
    if "set" in r:
        if value not in r["set"]:
            errs.append(f"{key}: {value!r} not in allowed set")
        return
    for x in _values(value):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            errs.append(f"{key}: non-numeric value {x!r}")
            continue
        if "min" in r and x < r["min"] or "max" in r and x > r["max"]:
            errs.append(f"{key}: {x} outside [{r.get('min')}, {r.get('max')}]")
        if r.get("integer") and int(x) != x:
            errs.append(f"{key}: {x} must be an integer")
    if "sum" in r and abs(sum(_values(value)) - r["sum"]) > 1e-9:
        errs.append(f"{key}: values must sum to {r['sum']}")
    if r.get("increasing") and isinstance(value, dict):
        vals = list(value.values())
        if any(b <= a for a, b in zip(vals, vals[1:])):
            errs.append(f"{key}: thresholds must be strictly increasing")


def validate(doc: dict) -> dict:
    """Raise AssumptionError on any V1-V8 violation; return a summary (incl. the V8 feasibility report)."""
    errs = []
    for f in ("assumption_set_id", "version", "approval", "currency", "time_granularity", "statements", "parameters",
              "delivery_arrangements", "review_rules", "scenarios"):
        if f not in doc:
            errs.append(f"missing top-level field {f}")
    if errs:
        raise AssumptionError("; ".join(errs))
    for s in REQUIRED_STATEMENTS:
        if not doc["statements"].get(s):
            errs.append(f"missing statement {s}")
    if "not a causal effect" not in doc["statements"].get("discount_uplift", ""):
        errs.append("discount_uplift statement must state that the association is not causal")
    params = {}
    for p in doc["parameters"]:
        missing = [f for f in REQUIRED_FIELDS if f not in p]
        if missing:  # V1
            errs.append(f"{p.get('key', '?')}: missing {missing}")
            continue
        if p["key"] in params:
            errs.append(f"duplicate parameter {p['key']}")
        params[p["key"]] = p
        if p["provenance"] not in PROVENANCES:
            errs.append(f"{p['key']}: unknown provenance {p['provenance']}")
        if p["provenance"] in ("ASSUMED", "SYNTHETIC") and p["supported_by_observed_business_data"] is not False:  # V4
            errs.append(f"{p['key']}: ASSUMED/SYNTHETIC values cannot be marked as supported by business data")
        if p["provenance"] in ("ASSUMED", "SYNTHETIC") and p["evidence"] == "OBSERVED_DATA":
            errs.append(f"{p['key']}: ASSUMED/SYNTHETIC values cannot claim OBSERVED_DATA evidence")
        if isinstance(p["value"], dict) and p["scope"] == "category" and set(p["value"]) != set(CATEGORIES):
            errs.append(f"{p['key']}: category values must cover {CATEGORIES}")
        _check_range(p, p["value"], errs)  # V2, V3
    g = {k: v["value"] for k, v in params.items()}
    for c in CATEGORIES:  # V2 cross-field
        mn, gm = g.get("min_margin_pct", {}), g.get("gross_margin_pct", {})
        if c in mn and c in gm and not mn[c] < gm[c]:
            errs.append(f"min_margin_pct must be below gross_margin_pct for {c}")
    if "discount_steps_pct" in g and "max_discount_pct" in g and max(g["discount_steps_pct"]) > g["max_discount_pct"]:
        errs.append("discount steps exceed max_discount_pct")
    if g.get("allow_extrapolation_above_p90") is not False:
        errs.append("allow_extrapolation_above_p90 must be false (approved design)")
    for sid in SCENARIOS:  # V5
        sc = doc["scenarios"].get(sid)
        if sc is None:
            errs.append(f"missing scenario {sid}")
            continue
        for k, v in sc["overrides"].items():
            if k not in params:
                errs.append(f"{sid}: override of unknown key {k}")
            else:
                _check_range(params[k], v, errs)
    status = doc["approval"].get("status")  # V6, V7
    if status not in ("DRAFT", "APPROVED"):
        errs.append(f"approval.status must be DRAFT or APPROVED, got {status!r}")
    if doc["approval"].get("content_sha256") != content_sha256(doc):
        errs.append("content_sha256 does not match the file content"
                    + (" - an APPROVED set cannot be edited; create a new version" if status == "APPROVED" else ""))
    if status == "APPROVED" and not (doc["approval"].get("approved_by") and doc["approval"].get("approved_at")):
        errs.append("APPROVED sets need approved_by and approved_at")
    if errs:
        raise AssumptionError("Assumption set invalid: " + "; ".join(errs))
    return {"assumption_set_id": doc["assumption_set_id"], "version": doc["version"], "status": status,
            "content_sha256": content_sha256(doc), "feasibility": feasibility(doc)}


def feasibility(doc: dict) -> dict:
    """V8: largest allowed discount step per category given the margin floor (cost = price x (1 - margin))."""
    g = {p["key"]: p["value"] for p in doc["parameters"]}
    out = {}
    for c in CATEGORIES:
        m, mn = g["gross_margin_pct"][c] / 100, g["min_margin_pct"][c] / 100
        max_by_margin = 1 - (1 - m) / (1 - mn)  # price x (1 - d) >= cost / (1 - min_margin)
        limit = min(g["max_discount_pct"] / 100, max_by_margin)
        steps = [s for s in g["discount_steps_pct"] if s / 100 <= limit + 1e-12]
        out[c] = {"max_discount_by_margin_pct": round(100 * max_by_margin, 2), "largest_allowed_step_pct": max(steps, default=0),
                  "discount_possible": bool(steps)}
    return out


def resolve(doc: dict, scenario: str) -> dict:
    """Flat parameter values for a scenario (base values with the scenario's overrides applied)."""
    if scenario not in doc["scenarios"]:
        raise AssumptionError(f"Unknown scenario {scenario}")
    values = {p["key"]: copy.deepcopy(p["value"]) for p in doc["parameters"]}
    values.update(copy.deepcopy(doc["scenarios"][scenario]["overrides"]))
    values["scenario_id"] = scenario
    values["scenario_name"] = doc["scenarios"][scenario]["name"]
    values["assumption_set_id"] = doc["assumption_set_id"]
    values["assumption_status"] = doc["approval"]["status"]
    values["assumption_content_sha256"] = content_sha256(doc)
    return values


def planning_weight(service_target_pct: float) -> tuple[float, bool]:
    """Approved heuristic: clip((target - 50) / 40, 0, 1). Returns (weight, capped_above_p90)."""
    w = (service_target_pct - 50) / 40
    return (min(max(w, 0.0), 1.0), w > 1.0)


def watermark(values: dict) -> str:
    wm = "DEMONSTRATION - ASSUMED/SYNTHETIC INPUTS"
    return wm + (" - DRAFT ASSUMPTION SET" if values.get("assumption_status") != "APPROVED" else "")


def remaining_life_days(shelf_life_days: int, transit_age_days: int) -> int:
    return max(1, int(shelf_life_days) - int(transit_age_days))


def case_round(x: float, case: int, moq_cases: int) -> int:
    """0 for x <= 0; otherwise rounded UP to whole cases and at least the MOQ."""
    if x <= 0:
        return 0
    return int(max(moq_cases, math.ceil(x / case - 1e-9)) * case)
