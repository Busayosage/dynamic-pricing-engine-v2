# Phase 3 — Waste Intervention Intelligence: as built

**Status:** advisory investigation support, read-only, DRAFT.
- Every assessment is `PENDING_HUMAN_INVESTIGATION` and `NOT_EXECUTED`, and nothing is approved.
- No order change, transfer, markdown, donation or disposal is assumed to have happened.
- No waste reduction, saving or profit is claimed.

The design is `docs/PHASE_3_WASTE_INTERVENTION_DESIGN.md` (approved 2026-10-24, registered).

## What was built

| File | Role |
|---|---|
| `src/dpe/decision/waste_interventions.py` | Deterministic advisory module: five options per at-risk line, two separate decisions, explanations, manager summary |
| `config/assumptions/assumption_set_v9.json`, `scripts/build_assumption_set_v9.py`, `src/dpe/decision/assumptions_v9.py` | DRAFT v9: v8 carried forward unchanged, plus 7 Phase 3 rule parameters (all ASSUMED) |
| `app/dashboard/dashboard_data.py` (`waste_interventions`, `intervention_params`) | Read-only, in-memory loader over the protected P2 replay; nothing is written |
| `app/dashboard/pages/8_Waste_intervention_lab.py` | Waste Intervention Lab. Future features moved to `9_` |
| `tests/test_waste_interventions.py` | 16 acceptance tests, plus 4 Lab tests in `tests/test_dashboard.py` |

**Reused unchanged:**
- the protected P2 replay
- Stage 6B waste risk and Stage 7B markdown eligibility
- the Phase 1 Discount Decision Lab ranking
- the preferred A1 Dynamic Pricing run (central response), used as context only
- the forecast contract reference price and the assumed margins
- store regions

No forecasting, inventory, pricing or A1 calculation was changed.

## How it decides (per store × product × week)

1. **Low** waste risk → `NO_INTERVENTION_NEEDED`. **Insufficient information** → `INSUFFICIENT_EVIDENCE`.
   **High / Moderate** → assess all five options.
2. **Stock already in the store:**
   - **C. Markdown.** `CANDIDATE_FOR_REVIEW` only when Stage 7B finds the line eligible **and** Phase 1 ranks a step
     (evidence level L2). It is `BLOCKED` by Stage 7B blockers, by "keeping the full price ranks first", or when
     every step is blocked. It is `INSUFFICIENT_EVIDENCE` when the price evidence conflicts or the result is too
     uncertain. The A1 run's selection is shown as context.
   - **B. Transfer.** `OPPORTUNITY_FOR_INVESTIGATION` (L1) when another store in the same region, for the same product
     and week, is projected short before its next delivery. Otherwise `NOT_APPLICABLE`. It is never higher.
   - **D. Donation or disposal.** `INVESTIGATE_ONLY` (L0) from 100 units at risk (an ASSUMED level). Otherwise
     `NOT_APPLICABLE`. It is never higher.
   - **E. No action:**
     - `NO_ACTION_SUPPORTED` when Phase 1 ranks keeping the full price first and nothing else is active
     - `INSUFFICIENT_EVIDENCE` when no option for the stock in store has usable evidence
     - otherwise `ALWAYS_AVAILABLE`
   - **Investigation order:**
     - Highest evidence level first; ties go markdown → transfer → donation (fewer outside parties first).
     - If only L0 remains, the result is **INSUFFICIENT EVIDENCE — investigate**.
     - This is the order of investigation, not a commercially optimal choice.
3. **The next order** is a separate decision.
   - **A. Replenishment review:** `CANDIDATE_FOR_REVIEW` (L1) when this week's simulated order is above typical (p50)
     demand within its shelf life and the line is not projected short.
   - It is `BLOCKED` when the line may run short, and `NOT_APPLICABLE` otherwise.
   - Its wording always says it cannot save the stock already in store. The protected P2 order is never changed.
4. **Values are illustrative.**
   - Estimated retail value = units × estimated reference price.
   - Assumed cost value = units × reference price × (1 − assumed margin).
   - Both are labelled "not a saving".

## Results (in memory, from the protected P2 replay)

| | SC1 | SC2 | SC3 | SF75 |
|---|---|---|---|---|
| Lines with stock at risk | 134 | 10 | 724 | 11 |
| Units projected to expire | 70,549 | 1,062 | 154,846 | 3,994 |
| Estimated retail value / assumed cost value | £210,389 / £151,249 | £5,926 / £4,134 | £627,639 / £434,208 | £11,159 / £7,996 |
| Stock in store: markdown first | 41 | 0 | 225 | 5 |
| Stock in store: transfer first (investigate only) | 17 | 1 | 6 | 2 |
| Stock in store: insufficient evidence (incl. "donation only — investigate") | 76 | 9 | 493 | 4 |
| Next order: review its size | 11 | 8 | 556 | 1 |
| Transfer opportunities (any rank) | 25 | 1 | 9 | 6 |

Every count matches the design inspection: at-risk lines, order buffers and transfer pairs.

## Limitations

- **The stock is simulated.** Stock, batches and expiry come from the replay, the projections assume typical demand,
  and units left per batch are unknown.
- **Transfers rest on a proxy.** Same region stands in for distance. Transport time and cost, receiving capacity
  (cold-storage units unknown) and batch dates are missing, and the receiver's shortage is itself a simulated
  indicator.
- **Donation and disposal have no data.** There are no partners, eligibility or food-safety rules, transport or
  values.
- **The order review cannot show its effect.** It flags the next order but does not simulate what a smaller order
  would change.
- **The markdown evidence keeps its Phase 1 / A1 limits:** assumed customer response, proxy prices, assumed costs.
  The A1 context comes from a run in which earlier simulated markdowns changed stock.
- **The values are illustrative and the data is synthetic.** None of this is commercial evidence.
