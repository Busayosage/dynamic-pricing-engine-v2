# Step 5B-3 inventory engine — implementation readiness (for review)

- **Date:** 23 Oct 2026
- **Status:** the design is conditionally approved. **Nothing is implemented.**
- **Design reference:** `docs/STEP_5B3_INVENTORY_ENGINE_DESIGN.md`. Its text is unchanged. Where this register differs
  from it, the register applies, because it records your approved directions.
- **Assumption set:** AS-2026-10-22-v1 stays DRAFT and unchanged, with content hash `383d703d…6fa`. Its values are
  illustrative ASSUMED and SYNTHETIC values, not validated or production-valid business policy.

---

## 1. Decision register D1–D12

The "Design wording" column quotes the design document's section 13 exactly. "Direction" names your approved
direction, numbered 1–7 as in your readiness message.

| # | Design wording (decision / recommendation) | Direction | Proposed disposition |
|---|---|---|---|
| D1 | "Adopt time-phased, expiry-aware sizing (section 3) as the design for P2" / "Approve" | 2 | **Approved by direction 2.** Usable stock is time-phased and never counted after expiry. Each drop is validated against case size and MOQ. Rounding excess is reported per drop. |
| D2 | "Depletion rate for existing stock **before** arrival: p50 (expected) or the planning rate (cautious)" / "p50, consistent with v1.1. The planning rate is used inside the window." | none | **Open, and needed for stage 5B-3a.** Proposed: p50 before arrival, the planning rate inside the window. In Example A the order is the same either way (4,176); only the expected expiry of existing stock differs (1,396.9 against 879.2). |
| D3 | "Planning fill rate: F1 (100% plus exposure), F2 (assumed rate) or F3 (as-of observed); value of `f_low` for exposure" / "F1 default; F2 as sensitivity; F3 only with real receipts; `f_low` = 75%" | 1 | **Resolved by direction 1.** See the D3 detail below the table. |
| D4 | "Recommendation categories and precedence (section 4.1)" / "Approve" | 3 adds a trigger | **Proposed: approve, with one addition.** The feasibility escalation `SHORT_LIFE_ARRANGEMENT_FEASIBILITY` is added as a material trigger. Its rule is blocker B1. Precedence is otherwise unchanged. |
| D5 | "No remedies for pre-delivery shortages (expedite, transfer) without documented evidence" / "Approve" | none | **Proposed: approve.** Remedies appear only as "options requiring evidence" and are never sized. |
| D6 | "Whether `SHORT_LIFE_ARRANGEMENT_ASSUMED` alone requires review" / "Warning only, until a supplier arrangement is documented" | 3 | **Resolved in principle by direction 3.** The warning is kept on every short-life proposal. Outputs never call daily or weekend drops verified. An escalation is required where the assumed arrangement materially affects feasibility. **What counts as "material" is open: blocker B1.** |
| D7 | "Rounding: always round up to cases and MOQ, or allow round-down when the overage would expire unsold" / "Round up (current); report overage" | 2 | **Proposed: round up, and report.** Every drop is either 0 or a whole number of cases of at least MOQ × case. Rounding excess is reported per drop and in total. Round-down is not implemented. |
| D8 | "`Supply_Capacity`: leave unused until its unit and period are defined" / "Leave unused" | 4 | **Approved by direction 4.** It is not an operational constraint. Outputs and reports state that it is excluded and why. |
| D9 | "Christmas escalations excluded from any bulk or default approval" / "Approve" | 7, protection | **Proposed: approve.** Christmas stays a mandatory escalation. No bulk, default or automatic approval path exists. |
| D10 | "Include an illustrative cost proxy (assumed margins) in the comparison" / "Optional; label as ASSUMED" | none | **Proposed: exclude from acceptance.** If reported at all, it is labelled "ASSUMED margins, illustrative" and plays no part in any threshold. |
| D11 | "Baseline definition P0 (4-week average, expiry-blind netting) and the pre-registered thresholds in section 7.4" / "Approve before any comparison run" | 5 | **P0, P1 and P2 are retained.** Section 2 below replaces the section 7.4 thresholds. They are frozen when you approve them, and before any comparison run. |
| D12 | "New parameters go into a new assumption-set version (v2, DRAFT); AS-2026-10-22-v1 is not edited" / "Approve" | 6 | **Approved by direction 6.** v1 and its recorded hash are preserved. New parameters will be proposed in a separate DRAFT file, AS-…-v2, at stage 5B-3d. Nothing is marked approved or production-valid. |

**D3 in detail (direction 1):**
- The planning fill rate is 100%, as a default illustrative assumption.
- Orders are **not** grossed up. Option F2 is dropped from the runs.
- 75% supplier fulfilment is evaluated separately as a stress scenario: planned at 100%, realised at 75% (section 2.4).
- Expected fulfilment stays separate from realised receipts.
- `f_low` = 75% is used only for the reported fill-rate exposure.
- F3 is deferred until real receipt data exists.

---

## 2. Predeclared comparison thresholds (proposed for your approval; to be frozen before any comparison run)

### 2.1 Scope

**Policies:**
- P0: historical-sales baseline, the as-of 4-week average with expiry-blind netting
- P1: accepted v1.1 sizing
- P2: time-phased, expiry-aware sizing

**Scenarios:** SC1, SC2 and SC3 from the DRAFT assumptions, plus the fill-rate stress scenario **SF75** (section 2.4).

All policies share these, so the policy comparison is like for like:
- delivery arrangements
- case and MOQ rules
- review gates
- demand path
- planning fill rate (100%)

### 2.2 Hard gates

Each gate must hold for **every** policy × scenario, with zero tolerance. Any failure blocks the comparison result.

| Gate | Area | Requirement |
|---|---|---|
| G1 | Inventory conservation | (a) Every series-day: opening + received = sold + expired + closing. (b) Closing = next opening. (c) No negative values; all units are integers. (d) Weekly totals equal the sum of daily values. |
| G2 | Delivery feasibility | (a) No drop arrives before day 1 + lead time, or outside its coverage window and drop schedule. (b) Every drop is 0, or a whole number of cases ≥ MOQ × case. (c) No stock is counted after its expiry day, audited in the per-day tables. (d) No quantity is proposed where the arrangement is `UNSUPPORTED` or bounds are missing. (e) Every short-life proposal carries `SHORT_LIFE_ARRANGEMENT_ASSUMED`. (f) `Supply_Capacity` is used nowhere. |
| G3 | Operational safety | (a) No record has an approved, executed or authorised status, or a non-empty `approval_event_id`. (b) 100% of Christmas decision points are `MANDATORY_ESCALATION`. (c) 100% of missing-bound points are `MANDATORY_REVIEW` with a quantity of 0. (d) The leakage, scramble and mutation tests pass. (e) The banned-wording test passes on all outputs. (f) P1 reproduces the protected v1.1 run exactly. (g) Every protected checksum still verifies. |

### 2.3 Comparison thresholds: P2 against P1

P1 is the accepted policy, so these thresholds decide whether P2 may replace it **as the replay default**. P2 stays
SYNTHETIC and DRAFT either way.

| Metric | SC1 (primary) | SC2 and SC3 |
|---|---|---|
| T-U: simulated unmet units (illustrative) | P2 ≤ 1.00 × P1 | P2 ≤ 1.02 × P1 |
| T-E: simulated expired units | P2 ≤ 1.05 × P1 | P2 ≤ 1.05 × P1 |
| T-O: total ordered units | P2 ≤ 1.05 × P1 | P2 ≤ 1.10 × P1 |
| T-R: review workload (decision-point cases) | P2 ≤ 1.10 × P1; mandatory counts identical (5,040 review, 2,880 Christmas) | the same |
| T-S: residual shortfalls after the order | 0, unless each has a named structural cause; and P2 ≤ P1 (P1 is 29 in SC1, 111 in SC3) | the same |
| T-X: rounding excess (report, not a gate) | Report per drop and per category. Flag any category where it exceeds 10% of ordered units. | the same |

**Notes:**
- Arrangement-confirmation cases from B1 option A are reported separately. They are not counted in T-R.
- **Outcome rule.** P2 is recommended as the replay default only if:
  - G1–G3 pass everywhere
  - every SC1 threshold passes
  - every SC2 and SC3 threshold passes

  Otherwise P1 remains, and the report lists each failed threshold. Thresholds are not changed after results are
  seen. A later change needs a new, dated threshold version, recorded before any new run.
- **P0 (baseline):** results are reported for context, with no gate in either direction. This avoids choosing the
  baseline to make P2 look good. Wording follows section 7.3 of the design: simulated differences only, no claim of
  real waste reduction or measured lost sales.

### 2.4 Stress scenario SF75: fill-rate stress

- SC1 with realised `delivery_fill_rate_pct` = 75 and the planning fill rate kept at 100. Nothing else changes.
- Gates G1–G3 apply.
- The following are reported, with no adoption threshold:
  - unmet units
  - expiry
  - pre-delivery shortage counts
  - residual shortfall counts
  - `FILL_RATE_SHORTFALL_LAST_WEEK` counts
  - the reported fill-rate exposure at `f_low` = 75%, against what was realised
- SF75 will be proposed as a new scenario in the v2 DRAFT file at stage 5B-3d. v1 is not edited.

### 2.5 Freezing

On approval, this section is copied unchanged into a dated threshold record. Its SHA-256 is then added to
`docs/CHECKSUMS.sha256` before stage 5B-3e runs. Any later edit would fail verification.

---

## 3. Implementation stages, as proposed in design section 12 and adjusted for the directions

| Stage | Content | Output | Needs decided first |
|---|---|---|---|
| **5B-3a** | Pure time-phased calculator: stock projection, per-drop expiry-aware sizing, case and MOQ validation, rounding excess, pre-delivery gap, post-order position, fill-rate exposure (no gross-up) | new module and unit tests; no run | D1, **D2**, D7 |
| 5B-3b | Recommendation categories, the feasibility escalation (B1), approval record schema, review queue v1.2 | tests only | D4, D5, **D6/B1**, D9 |
| 5B-3c | Simulator v1.2 with pluggable sizing policies P0, P1 and P2; P1 regression against the protected v1.1 run; leakage, conservation and determinism tests | tests only | 5B-3a, 5B-3b |
| 5B-3d | Separate DRAFT assumption file AS-…-v2, holding the new parameters and SF75. v1 is untouched. | new JSON, validated, DRAFT | D12, D3 |
| 5B-3e | Worked-example run, then the full comparison: 3 policies × SC1–SC3 + SF75; protection and report | new protected runs, report, STOP | **frozen thresholds** (section 2) |

### Recommended first stage: 5B-3a, narrowed to the calculator only

**Files:**
- new `src/dpe/decision/inventory.py` (pure functions, no file input or output)
- new `tests/test_inventory_calculator.py`

**Unchanged:**
- no change to `replay.py`, `review_queue.py`, `replay_run.py`, `assumptions.py` or any config or JSON file
- no run folder
- no checksum change

**Functions:**
1. Project the lots to the arrival day. This takes on-hand lots and committed deliveries at their ordered quantities.
2. Size each drop for its own coverage window. Usable stock is checked day by day against expiry, and quantities are
   rounded up to cases and MOQ.
3. Validate each drop: 0, or a whole number of cases ≥ MOQ × case.
4. Report the rounding excess per drop.
5. Calculate the pre-delivery gap at the p10, p50 and p90 rates.
6. Calculate the post-order position and the residual shortfall.
7. Calculate the fill-rate exposure at `f_low`. This is reported only; no gross-up.

**Tests:**
- design tests T1a–c (expiry-aware stock)
- T3 (pre-delivery gap)
- T4a and T4c (delivery timing)
- T5c (exposure grows as fill falls)
- T5d (100% means no change)
- T6 (case and MOQ)
- a determinism check of the pure functions
- worked examples A (4,176), B (1,428 = 7 × 204) and C (gaps 404.4 / 1,006.7 / 1,752.1). Their inputs are frozen
  in the tests as hand-entered fixtures: lots, committed deliveries, p10, p50 and p90.

**Done when:**
- the new tests pass
- the existing 338 tests pass unchanged
- all 293 checksums verify

**Why it is independently testable:** the calculator has no dependency on the simulator, the review queue or any
assumption file.

---

## 4. Remaining blockers

1. **B1: definition of "materially affects feasibility" (D6 and direction 3).** This is needed for 5B-3b, not 5B-3a.
   - **Evidence:** in the accepted SC1 replay, all 7,200 short-life orders across 360 series depend on drops more
     often than weekly.
     - Every order with R ≤ 3 includes a weekend drop: 4,500 orders, where weekend drops carry 29–45% of the units.
     - 75% of R = 4 orders include one.
     - R = 5–6 orders do not.
     - 3,600 short-life orders are also lead-time tight.
   - **Options:**
     - **A (recommended):** one `ARRANGEMENT_CONFIRMATION_REQUIRED` case per short-life series per replay, 360 in
       total, reported separately from weekly workload. The per-decision warning stays on every proposal.
     - **B:** a per-decision escalation where R ≤ 2, meaning drops at least every 2 days. This is about 2,400
       decisions per SC1 replay.
     - **C:** a per-decision escalation wherever a weekend drop is needed. This is about 5,400 decisions per SC1
       replay: 4,500 with R ≤ 3, plus 75% of the 1,200 with R = 4.

     B and C would roughly add 20–50% to SC1's 11,397 weekly cases.
2. **B2: D2, the depletion rate before arrival.** This is needed for 5B-3a. Proposed: p50.
3. **B3: approval of the section 2 thresholds,** then freezing them by checksum before 5B-3e.
4. **B4: explicit approval of D4, D5, D7, D9 and D10 as proposed in section 1.** D7 is needed for 5B-3a. The others
   are needed for 5B-3b and 5B-3e.
5. **Not blockers, recorded for later:**
   - SF75 and the new parameters belong to the v2 DRAFT file at 5B-3d.
   - `Supply_Capacity` stays excluded until it is defined.
   - All results remain synthetic.
