# Step 5B-3d: Assumption set v2 and the SF75 stress scenario

**Date:** 23 Oct 2026. **Status: DRAFT. Not approved, not validated against business data, not for production use.**

| | v1 (preserved) | v2 (new) |
|---|---|---|
| File | `config/assumptions/assumption_set_v1.json` | `config/assumptions/assumption_set_v2.json` |
| ID / version | AS-2026-10-22-v1 / 1 | **AS-2026-10-23-v2** / 2 |
| Content hash | `383d703d…6fa` (unchanged) | `ddc95ec1…989f` |
| Status | DRAFT | DRAFT, `production_use: false` |
| Parameters | 24 | 36 (24 carried forward unchanged + 12 new) |
| Scenarios | SC1, SC2, SC3 | SC1, SC2, SC3 (unchanged) + **SF75** |

v1 is byte-identical: file SHA-256 `42116041…cd50`. The existing simulator, the protected runs and P1 keep using it.

Every ASSUMED or SYNTHETIC value in v2, as in v1, is an illustrative demonstration default. None is supported by observed
business data.

## 1. What changed, in plain English

### Carried forward unchanged

All 24 v1 parameters keep their values, provenance and allowed ranges. The v2 validator checks this on every load.

The descriptions of two existing parameters were reworded only, with their values unchanged:

| Parameter | Now described as |
|---|---|
| `delivery_fill_rate_pct` | **Realised** simulated receipts |
| `over_delivery_pct_short_life` | **Realised** simulated over-deliveries |

This makes clear that they describe simulated supplier performance on the arrival day. Planning never reads them.

### New parameters

All are ASSUMED and unsupported by business data. Each has a unit, scope, evidence label, rationale, allowed range and
sensitivity range.

| Parameter | Value | What it means operationally |
|---|---|---|
| `planning_fill_rate_pct` | 100 (fixed) | Orders are planned as if suppliers deliver everything ordered (decision D3). Any other value is rejected. |
| `stress_fill_rate_pct` | 75 (range 50–100) | Used only to *report* how exposed a proposal would be if 75% arrived. Orders are never changed. |
| `order_inflation_for_expected_shortfall` | false (fixed) | The engine never adds extra units "in case" the supplier delivers short. |
| `pre_arrival_depletion_quantile` | p50 (fixed) | Existing stock is expected to sell at the median forecast until the new order arrives (D2). |
| `coverage_assessment_quantiles` | p10, p50, p90 (fixed) | Coverage is checked at three demand levels from the same starting point. These are planning positions, not stockout probabilities. |
| `expiry_escalation_pct_of_p50` | 15 (range 0–100) | Stock projected to expire unused that exceeds 15% of a typical week's median demand is escalated for review. Smaller amounts are a warning. Provisional, the same level as the v1 high waste band. |
| `rounding_excess_warning_pct` | 10 | Warns when case or MOQ rounding adds more than 10% to the true need. This is reported, not a gate. |
| `p0_history_weeks` | 4 (fixed) | Baseline P0 averages the last 4 recorded weeks. Preregistered. |
| `p0_netting_rule` | `STOCK_ON_HAND_ONLY_EXPIRY_BLIND` (fixed) | P0 subtracts all stock on hand, ignoring expiry and deliveries already scheduled. It will not be revised again (5B-3d decision 1). |
| `missing_bounds_rule` | P0, P1: H1 only (v1.1). P2: any required horizon. | P2 will not propose an order if forecast bounds are missing for either horizon (5B-3d decision 2). P1 keeps its v1.1 behaviour. Review cases use the any-horizon gate for every policy. |
| `standing_confirmation_rule` | one case per series | A series that relies on assumed recurring, daily or weekend drops gets a single standing supplier-confirmation case. Weekly cases are not repeated for it (D6). |
| `supply_capacity_used` | false (fixed) | `Supply_Capacity` is ignored until its unit and period are verified (D8). |

### New blocks

- **`policies`:** plain descriptions of P0, P1 and P2, and which review queue each uses.
- **`review_rules.inventory_queue_v1_2`:** the P2 categories in precedence order, the case types and the standing-case rule.
- **`statements.fulfilment`:** the expected-versus-realised distinction.
- **`statements.status`:** DRAFT, not for production use; every action is hypothetical.
- **`statements.information_boundary`:** parameters are configuration only. None is derived from data after a decision date.
- **`evaluation_record`:** the preliminary-exposure record (section 3), the threshold reference and `comparison_status: NOT_RUN`.

## 2. SF75 supplier-fill stress scenario

| | SC1 | SF75 |
|---|---|---|
| Expected fulfilment used for planning | 100% | **100%** |
| Realised simulated receipts | 100% | **75%** of ordered units, rounded down |
| Order inflation | none | **none** |
| Everything else | — | identical to SC1 |
| Adoption threshold | preregistered | **none:** reported only |

**What this means:** the store plans normally, then the supplier delivers only three-quarters of each order. Decisions are
identical to SC1 until the first short delivery is received. From then on they differ only because stock on hand is
lower, and the last-week fill-shortfall flag starts to appear. Orders are never inflated to compensate.

The validator rejects an SF75 that changes anything other than the realised fill rate. It also rejects any scenario that
overrides the planning fill rate or turns on order inflation.

The tests confirm this behaviour, for all three policies on the synthetic fixtures:
- first decisions are identical to SC1
- every order delivery arrives at ⌊0.75 × ordered⌋ units
- illustrative unmet units rise

## 3. Preliminary comparison exposure (recorded, not used)

During Stage 5B-3c integration on 23 Oct 2026, SC1 aggregate totals for P0 and P2 were seen once, in a timing check.
The P0 run used an earlier netting rule that also counted committed deliveries. That rule was then corrected to the
preregistered text.

These figures were **not** used to change any rule, parameter or threshold:
- the P0 rule is fixed by 5B-3d decision 1
- the thresholds in `STEP_5B3_IMPLEMENTATION_READINESS.md` section 2 are unchanged

Because results were seen before the final comparison, **the P0/P1/P2 comparison in Stage 5B-3e is exploratory rather
than fully confirmatory**. This is recorded in `evaluation_record` in the v2 file.

## 4. Validation

v2 must pass two sets of rules:

- **v1 rules V1–V8.** These cover the required fields, ranges, ASSUMED/SYNTHETIC labelling, scenario overrides, DRAFT
  or APPROVED status and the content hash.
- **The new v2 rules W1–W10, in `src/dpe/decision/assumptions_v2.py`:**
  - W1: a new ID, version 2 and schema 2.0
  - W2: it supersedes v1, and v1 still has its recorded hash and DRAFT status
  - W3: every parameter has a sensitivity range
  - W4: every v1 parameter is carried forward unchanged
  - W5: all required v1.2 parameters are present
  - W6: every override, including SF75, is in range
  - W7: the SF75 definition
  - W8: DRAFT, with no production use
  - W9: no unsupported claims
  - W10: no new OBSERVED parameters

The current file passes. The tests also confirm that 17 kinds of invalid file are rejected, and that an edited file
without a new hash is rejected.

## 5. Operational implications

1. **Supplier performance is a risk to watch, not to plan around (yet).** Planning assumes full delivery, so short
   deliveries show up as exposure figures and as last-week flags. Planning around them would need real receipt data
   and a new decision.
2. **Expiry escalation at 15% of a week's median demand is provisional.** It may need tuning per category once real
   waste data exists.
3. **P2 is stricter than P1 when forecast bounds are missing.** In the current data, no point inside the replay window
   is affected, but this is a policy-specific safety difference.
4. **Short-life supplier arrangements remain unconfirmed.** They create standing confirmation work, one case per
   series, rather than weekly noise.
5. **Nothing here is production-ready.** v2 is DRAFT, every value is illustrative, and all simulated actions remain
   hypothetical and unapproved.

## 6. Decisions still open before Stage 5B-3e

1. Review and accept the v2 content (it stays DRAFT; approval is not requested here).
2. Freeze the preregistered thresholds (readiness section 2) by registering their checksum before the comparison runs.
3. Approve the 5B-3e run scope:
   - P0, P1 and P2 across SC1–SC3 and SF75, using v2
   - P1 also confirmed against v1
   - comparison report wording rules (design section 7.3)
