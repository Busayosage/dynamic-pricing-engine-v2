# Step 5B-2 replay simulator correction checkpoint (v1.1), 23 Oct 2026

Status: for your review. The assumption set **AS-2026-10-22-v1 is still DRAFT**. No inventory, waste-risk or pricing
recommendation engine has been started. No SQLite tables, no Airtable, no GitHub.

| | v1.0 (kept for comparison) | v1.1 (new) |
|---|---|---|
| Worked example run | `20261022-225527_replay_worked_example` | `20261023-081500_replay_worked_example_v1_1` |
| Full replay run | `20261022-225809_replay_simulation` | `20261023-081809_replay_simulation_v1_1` |
| Simulator / review queue | 1.0 / 1.0 | 1.1 / 1.1 |
| Assumption content hash | `744404c8…09e5` | `383d703d…6fa` (DRAFT; lead-time switch and review rules changed) |

The v1.0 runs and every other protected run are unchanged and still checksum-verified. All results are
SYNTHETIC; recorded sales are used as illustrative demand.

## 1. What changed

1. **Lead-time warning.** `LIFE_LEAD_TIME_TIGHT` (effective lead time ≥ remaining life) is still calculated. It is now
   an informational warning, not a material trigger (`life_lead_time_tight_is_material_trigger = false`).
   - On its own it creates no review case. It is kept in the new `warnings` column of every decision point.
   - It escalates only when the same decision point also has a material operational risk:
     - pre-order shortage
     - post-order shortfall
     - high existing-stock waste exposure
     - a fill-rate shortfall
     - trend divergence
     - an unsupported delivery arrangement (mandatory review)
     - Christmas (mandatory escalation)
   - When a case exists, the reasons carry `LIFE_LEAD_TIME_TIGHT_WARNING` as evidence.
   - The v1.0 rule is available only as an explicit sensitivity switch.
2. **Shortage detection: separate pre-order and post-order coverage.**
   - *Pre-order coverage* uses stock on hand plus deliveries committed **before** the decision, at their ordered
     quantities, because supplier shortfalls are not known in advance. It covers the days before the new order can
     arrive: decision day to decision day + lead time − 1. A position of `COVERS_P10_RATE_ONLY` or `BELOW_P10_RATE`
     raises `PRE_ORDER_SHORTAGE`. The new order cannot hide this, because the order is not in the calculation.
   - *Post-order coverage* is the same, plus the proposed drops on their **actual scheduled arrival days**, each
     sellable until its own expiry. It covers the 7-day window from the first arrival. A shortfall raises
     `POST_ORDER_SHORTFALL`. `order_addresses_window` records whether the order covers its window.
   - Positions are calculated by an expected-demand FIFO walk at the forecast's p90, p50 and p10 weekly rate ÷ 7:
     `COVERS_P90_RATE`, `COVERS_P50_RATE`, `COVERS_P10_RATE_ONLY` or `BELOW_P10_RATE`. They are heuristic positions,
     not stockout probabilities. Dividing the weekly rate by 7 is a coverage convention, not a daily demand forecast.
3. **Christmas and approval safety.**
   - Christmas remains `MANDATORY_ESCALATION`, and the decision carries `escalation_required = true`.
   - Every simulated order has `action_status = HYPOTHETICAL_UNAPPROVED`. Points with no order are
     `REVIEW_REQUIRED_NO_ACTION`.
   - Every delivery has `authorisation = HYPOTHETICAL_UNAPPROVED_SIMULATED`.
   - Every case is `PENDING_REVIEW` with an empty `approval_event_id`.
   - The run script refuses to write if any simulated action carries an approval event. The manifest states that
     outcomes are simulated, not authorised business actions.
4. **Order sizing is unchanged.**

## 2. Results (full replay, origins 32–51, 720 series, 14,400 series-weeks per scenario)

### Review cases, old versus new

| | SC1 old | SC1 new | SC2 old | SC2 new | SC3 old | SC3 new |
|---|---|---|---|---|---|---|
| Mandatory escalation (Christmas) | 2,880 | 2,880 | 2,880 | 2,880 | 2,880 | 2,880 |
| Mandatory review | 5,040 | 5,040 | 5,040 | 5,040 | 5,040 | 5,040 |
| Risk escalation | 4,684 | 3,477 | 11,064 | 11,189 | 5,660 | 4,760 |
| **Total cases** | **12,604** | **11,397** | **18,984** | **19,109** | **13,580** | **12,680** |
| Cases removed: lead-time warning only | | 1,786 | | 185 | | 1,057 |
| Cases added: pre-order shortage | | 579 | | 310 | | 157 |
| Lead-time warning kept inside a case | | 1,814 | | 4,615 | | 2,543 |
| Approved cases / actions with an approval event | | 0 / 0 | | 0 / 0 | | 0 / 0 |

Every case that moved changed for one of exactly two reasons:
- **Removed:** the only trigger was the lead-time warning.
- **Added:** the only new trigger was `PRE_ORDER_SHORTAGE`.

No mandatory case changed.

### Shortage detection

| | SC1 | SC2 | SC3 |
|---|---|---|---|
| Decisions with a pre-order shortage (v1.0 coverage trigger: 0) | 957 | 5,281 | 277 |
| … covering only the p10 rate / below the p10 rate | 489 / 468 | 2,537 / 2,744 | 187 / 90 |
| … of which the proposed order covers its own window | 957 | 5,281 | 277 |
| Decisions with a post-order shortfall | 29 | 0 | 111 |
| Share of flagged pre-arrival windows with simulated unmet units | 86.3% | 91.7% | 62.5% |
| Share of unflagged pre-arrival windows with simulated unmet units | 12.6% | 51.5% | 2.1% |
| Share of all pre-arrival simulated unmet units in flagged windows | 58.3% | 68.3% | 60.9% |

The last three rows are supporting evidence that the flag points at real pressure in the simulation. They are
**not** a calibration and not a probability. The high unflagged rate in SC2 comes from its 75% fill rate. Supplier
shortfalls are deliberately not known at decision time, so pre-order coverage counts committed deliveries at their
ordered quantity.

The previous coverage trigger never fired: 0 in every scenario. The v1.1 pre-order check detects 957 shortages in
SC1, 5,281 in SC2 and 277 in SC3. These are **newly detected**, because v1.0 could not see any of them. In SC1, 579
of them create new cases. The other 378 are already in a case for another reason; in those cases
`PRE_ORDER_SHORTAGE` now appears among the reasons.

### Effect on simulated orders, unmet units and expiry: none (identical to v1.0, verified file by file)

| | SC1 | SC2 | SC3 |
|---|---|---|---|
| Ordered units | 25,466,832 | 30,073,668 | 23,179,602 |
| Unmet units (illustrative) | 834,870 | 5,147,154 | 139,453 |
| Expired units | 2,763,370 | 415,087 | 5,713,748 |

These checks match v1.0 exactly for every decision and series-week:
- `ordered_units`, `n_deliveries` and `arrival_day`
- every `sim_*` column of the weekly outputs

The correction changes what is detected and escalated, not what is ordered.

### Directional consistency of the three scenarios: holds

- **SC2 (constrained supply)** has more unmet units, more pre-order shortages and more cases than SC1.
- **SC3 (overstock)** has more expiry and more high-waste exposure (5,216 vs 2,881) than SC1, and fewer pre-order
  shortages.
- All five directional checks pass:
  - planning weight
  - same-need case rounding
  - fill rate → unmet units
  - demand → expiry
  - margin → maximum discount
- **Sensitivity (SC1):**
  - Pre-order shortages rise when the service target falls (50%: 7,345), the fill rate falls (60%: 8,594) or demand
    rises (×1.15: 1,886).
  - They fall when demand falls (×0.85: 406).
  - Re-enabling the v1.0 lead-time rule gives 13,183 cases with identical orders.

## 3. Tests and checksums

- **New file `tests/test_replay_corrections.py`: 16 tests.** They cover:
  - lead-time warning alone → no case (unit and full run)
  - lead-time warning combined with a pre-order shortage, high waste or an unsupported arrangement → escalation, with
    the warning preserved
  - the legacy switch
  - pre-order shortage detection (unit), and that the order cannot hide it (simulation)
  - post-order coverage depends on arrival day and drop expiry (unit and simulator)
  - Christmas decisions and cases stay unapproved (real contract)
  - conservation
  - future sales scrambled at three cut-offs leave earlier decisions unchanged
  - coverage never reads actual supplier deliveries
- **Leak mutation check:** the coverage calculation was deliberately altered to read delivered rather than ordered
  units. The new test failed, so it can detect that leak.
- **Existing tests:**
  - `tests/test_replay_simulator.py` was updated to the new KPI name and simulator column.
  - New protection tests cover the two v1.1 runs.
  - The original future-sales mutation and truncated-history tests still pass with the v1.1 code.
- **Full suite:** 338 passed, 0 failed, 0 skipped. That is 320 before this checkpoint, plus the 16 new tests and 2
  new protection tests.
- **Checksums:** all 293 registered checksums verify. The registry has grown from 247 to 293 entries: 24 + 22 files
  for the two new runs. All 400 run files snapshotted before the checkpoint are byte-identical afterwards.

## 4. Remaining operational contradictions (not fixed: order sizing is outside this checkpoint)

1. **Order sizing credits stock that expires inside the window.**
   - SC1 has 29 post-order shortfalls, all Dairy, long-life weekly, R = 9, LT = 2. SC3 has 111: Dairy, Bakery and
     Meat.
   - Sizing subtracts all stock still usable on the arrival day. Some of that stock expires before the window ends.
   - The post-order check now shows the resulting gap; the sizing rule does not. This needs a decision when the
     inventory recommendation engine is designed.
2. **A pre-order shortage cannot be fixed by the routine order.**
   - In every flagged case the proposed order covers its own window, but nothing reaches the store before it arrives.
   - The only remedies are outside the simulator: an expedited delivery, a transfer or accepting the gap. The case
     reports the pressure; it does not recommend a remedy.
3. **Supplier shortfalls are invisible at decision time.**
   - In SC2, 51.5% of unflagged pre-arrival windows still have simulated unmet units, because deliveries arrive
     short.
   - `FILL_RATE_SHORTFALL_LAST_WEEK` reacts only after the event.
   - Whether to plan on an expected fill rate is a business assumption for you to decide.
4. **The lead-time warning remains very common.**
   - 3,600 SC1 decision points carry it: 1,786 without a case and 1,814 inside one.
   - It now adds no workload on its own, but the underlying assumption still needs business confirmation: shelf life
     minus one day of transit age, against lead time.
