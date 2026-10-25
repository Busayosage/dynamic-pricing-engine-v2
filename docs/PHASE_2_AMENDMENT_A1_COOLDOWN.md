# Phase 2 — Research-rule amendment A1: cooldown from the end of the previous markdown window

**Status:** implemented as a separate version and tested. **No new evaluation has been run.** The frozen Phase 2
evaluation and its protected run are unchanged and remain the reported result.

## The approved rule

A new markdown for the same store-product may **start** only after **seven complete days** have elapsed since the
previous simulated markdown **ended**:

```
candidate window start ≥ previous window end + 7 + 1
```

For example, a window that ends on day 235 leaves days 236–242 as the seven complete days, and the earliest allowed
start is day 243.

The rolling limit (at most 2 events in any 28 days, counted at selection) and the no-overlap rule are kept unchanged.

## How markdown dates are recorded, and the weekly cadence

| Field | Meaning |
|---|---|
| `decision_day` | The weekly decision day (Monday of the target week) |
| `window_start_day` | The investigate-by day: max(decision day, oldest batch's last sellable day − 1) |
| `window_end_day` | The oldest batch's last sellable day |

In the protected run every window lasts 2 days. It starts 1–4 days after the Monday decision and ends between Tuesday
and Saturday of the same week.

The candidate window start is known at the decision, so A1 is checked at the existing weekly decision. **The cadence
is unchanged.**
- A blocked line is not rescheduled; it is reconsidered at the next weekly decision.
- In practice A1 blocks a markdown in the week straight after a markdown. A markdown two weeks later is allowed:
  for example, a start on day 247 after an end on day 235.

## Implementation (new files only; nothing frozen is edited)

| File | Role |
|---|---|
| `config/assumptions/assumption_set_v8.json`, `scripts/build_assumption_set_v8.py`, `src/dpe/decision/assumptions_v8.py` | DRAFT v8: all v7 values carried forward, plus `dynamic_pricing_cooldown_basis = END_OF_PREVIOUS_MARKDOWN_WINDOW`. Not yet registered in `docs/CHECKSUMS.sha256` |
| `src/dpe/decision/dynamic_pricing_a1.py` | The A1 guard and decision. It reuses the frozen v7 policy with its selection-day cooldown switched off; the overlap and rolling-limit checks are identical |
| `src/dpe/decision/replay_pricing_a1.py` | Simulator v1.4: the **same compiled** v1.3 loop with only the policy module rebound, so ordering, selling, expiry, demand response and revenue are identical by construction |
| `tests/test_cooldown_amendment.py` | 10 focused tests |

The tests show:
1. Starts on days 236–242 are blocked after a window ending on day 235, and day 243 is allowed.
2. An otherwise eligible repeat in the following week is blocked (`GUARD_BLOCKED`, `COOLDOWN`, no price change), and
   the same line is selected again two weeks later.
3. With no history, A1 chooses exactly what the frozen v7 policy chooses.
4. The rolling limit and the no-overlap rule still apply.
5. In an SC3 replay of 5 affected lines:
   - the frozen v1.3 still reproduces the protected run's decisions exactly
   - v1.4 blocks the repeats, while a repeat after the full interval still happens
   - every Phase 2 hard gate passes
6. v1–v7, the evaluation policy, the design document and all protected outputs are unchanged.

## Impact on previously reported results

This analysis was read from the protected run; nothing was re-run.

| Scenario | Selections in the frozen run | Would A1 block any? | Effect |
|---|---|---|---|
| SC1 | 41 | No | Prices and every figure identical. One non-selected decision would be labelled `GUARD_BLOCKED` instead of "insufficient evidence"; this is a label only |
| SC2 | 0 | — | Identical |
| SF75 | 5 | No | Identical |
| **SC3** | 205 (74 lines) | **Yes: 26 selections in 19 lines**, the same under all four true responses; all are consecutive-week repeats | **Results change.** From each blocked point, stock and later decisions differ, so the SC3 figures cannot be adjusted by hand |

The original evaluation (EP-PH2-2026-10-23-v1, run `20261023-233225_dynamic_pricing_evaluation`) is preserved as
reported. It remains the result **for the v7 rule**.

## What a separately versioned comparison would require (awaiting approval)

1. **A new evaluation policy**, `EP-PH2-A1-v1`, frozen and registered **before** running. It would say whether the
   v7 thresholds T1–T5 are kept unchanged, and it would record that the v7 results were already seen (exploratory
   exposure).
2. **Register v8**, the A1 modules and the amendment note in `docs/CHECKSUMS.sha256`.
3. **One new run directory**, for example `<timestamp>_dynamic_pricing_evaluation_a1`, made with v8 and simulator
   v1.4. It would cover all four scenarios × four true responses, with the same prerequisites E1–E3 (pricing off must
   still reproduce the protected P2 replay) and hard gates G1–G7. G4 would check the A1 cooldown.
4. **Reporting** next to the v7 result, never in place of it:
   - benefits and harms for every scenario and response
   - an explicit v7-vs-A1 difference table, showing SC1 and SF75 identical and SC3 changed
5. **Dashboard:** the Dynamic Pricing Lab gains a rule-version selector (v7 frozen / A1 amendment), with the frozen v7
   result still the default until you decide otherwise.
