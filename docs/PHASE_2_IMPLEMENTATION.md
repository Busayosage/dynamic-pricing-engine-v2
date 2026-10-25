# Phase 2 — Dynamic pricing engine: as built and evaluated

**Status:** simulated research, DRAFT, **NOT VALIDATED FOR LIVE USE**.
- Every markdown is SIMULATED / HYPOTHETICAL_UNAPPROVED / NOT_EXECUTED.
- Inside the replay a markdown is applied only "as if approved", so its effect can be measured.
- No order, price change, approval or integration exists.

The approved design is `docs/PHASE_2_DYNAMIC_PRICING_DESIGN.md` (frozen and registered). This document records what
was built, the new assumptions, the results and the limitations.

## 1. What was built

| File | Role |
|---|---|
| `src/dpe/decision/replay_pricing.py` | Simulator **v1.3**: the v1.2 chronology plus a pricing step. It imports `replay.py` / `replay_v12.py` and never edits them |
| `src/dpe/decision/dynamic_pricing.py` | Per-decision policy: state assessment → eligibility → timing guards → Phase 1 `recommend_line` → review tags |
| `src/dpe/decision/pricing_evaluation.py` | Pre-run checks, prerequisites E1–E3, hard gates G1–G7, measures, preregistered thresholds, run writer |
| `src/dpe/decision/assumptions_v7.py`, `config/assumptions/assumption_set_v7.json`, `scripts/build_assumption_set_v7.py` | DRAFT assumption set v7 |
| `config/evaluation/evaluation_policy_phase2_v1.json` | Evaluation policy EP-PH2-2026-10-23-v1, frozen before any pricing outcome was simulated |
| `scripts/run_dynamic_pricing_evaluation.py` | Writes one new run: `outputs/runs/20261023-233225_dynamic_pricing_evaluation` |
| `app/dashboard/pages/7_Dynamic_pricing_lab.py` | Dynamic Pricing Lab, which reads the saved run only |
| `tests/test_dynamic_pricing.py` | 20 tests |

**Reused unchanged:**
- the protected daily selling step `replay._simulate_week`: deliveries, oldest-first selling, expiry and unit
  conservation. It is reached through a demand wrapper.
- the v1.2 P2 ordering policy
- `standard_indicators`
- `waste_risk.classify`
- `markdown_eligibility.blockers_for` / `classify`
- `pricing_demo.options`
- `discount_recommendation.recommend_line`, with its explanations

## 2. Decision sequence (every origin week, every store-product)

1. **Order.**
   - With pricing off, the P2 policy decides exactly as in v1.2.
   - With pricing on, the order and its deliveries are copied unchanged from the pricing-off pass for the same
     scenario. Pricing can therefore never change an ordering decision (approved condition 1).
2. **State assessment.** All inputs are known at the decision:
   - the standard expiry projection on the current simulated stock
   - batches already received
   - the forecast contract row for the origin
   - Christmas in any horizon
   - the recorded promotion in the origin week
3. **Eligibility.** The unchanged Stage 7B rules apply.
4. **Timing guards (v7).** A selection is blocked if any of these hold:
   - fewer than 7 days since the previous selection
   - two selections already in the rolling 28 days
   - an earlier window still in force
5. **Choice.** The Phase 1 engine chooses with the **belief**: v6 weights of low 25%, central 50% and high 25%. It
   never sees the **true** response.
6. **Tags.**
   - Every selection is tagged `PENDING_HUMAN_REVIEW`.
   - `MANDATORY_REVIEW` is added for a markdown of 20% or more, a repeat within 28 days, or an open inventory review
     case.
7. **Simulate the week.**
   - On markdown days, demand = floor(recorded daily units × (1 + true response × points / 100) + 0.5).
   - Revenue is booked at the price in force: the reference price of the deciding origin, or the markdown price.
   - The markdown applies from the investigate-by day to the oldest batch's last sellable day, then the price
     returns to the reference.

**Event counting rule.** An event is counted on the decision day it is **selected**. Every selection is applied in the
simulation, so the selected and the hypothetically applied events are the same set. The cooldown, the rolling limit
and the overlap rule all use selection days and selected windows. The tests check that the set of applied markdown
days equals the set of selected events.

## 3. New assumptions in v7 (all ASSUMED, DRAFT)

| Parameter | Value |
|---|---|
| Cooldown between markdown selections per store-product | 7 days (approved) |
| Maximum markdown events per store-product in any rolling 28 days | 2 (approved) |
| Markdown only (never above the reference price) | true (approved) |
| Ordering interaction | orders fixed to the pricing-off pass (approved) |
| True responses simulated | R0 none, R1 low (1.0%/pt), R2 central (1.6%/pt, non-causal), R3 high (3.0%/pt) (approved) |
| Overlap rule | no selection while an earlier window is in force |
| Demand rounding on markdown days | floor(x + 0.5), integer units |
| Revenue price rule | reference price of the origin that decided the week |
| Mandatory review threshold | markdown of 20% or more, a repeat, or an open inventory case |
| Simulation convention | SIMULATED_AS_IF_APPROVED |

**Note on the cooldown.** Decisions are exactly 7 days apart, so a cooldown of 7 days between *decisions* can never
block a selection on its own. The limiting rules in practice are the 28-day limit and the no-overlap rule. If the
cooldown should be measured from the end of the previous markdown window instead, that needs a new approval and a new
assumption version.

## 4. Critical validation (pricing off), passed in all four scenarios

| Check | SC1 | SC2 | SC3 | SF75 |
|---|---|---|---|---|
| E1: pricing off equals the protected P2 run (decisions, deliveries, weekly stock flows, unmet and expiry; CSV round trip) | PASS | PASS | PASS | PASS |
| E2: fixed orders with no markdown possible equal pricing off (decisions, deliveries, daily, weekly) | PASS | PASS | PASS | PASS |
| E3: in-loop eligibility, blockers, waste class, batch dates, investigate-by day and at-risk units equal the saved Markdown review on every decision | PASS | PASS | PASS | PASS |

The evaluation policy was registered **before** any pricing outcome was simulated. The only runs made before freezing
were the SC1 pricing-off check and a no-markdown shadow run.

## 5. Results: run 20261023-233225_dynamic_pricing_evaluation (720 lines, 20 weeks)

All hard gates G1–G7 passed in all 16 priced runs:
- G1 conservation
- G2 orders unchanged
- G3 markdown only and price bounds
- G4 guards
- G5 chronology
- G6 labels
- G7 no-response demand equals baseline

Under the frozen rule the outcome is **MEETS_PREREGISTERED_RESEARCH_CRITERIA**. This is a research result only, not
commercial proof.

Changes are against unchanged prices; GP is simulated gross profit.

| Scenario | True response | Markdowns (lines) | GP change | GP change % | Expired units | Unmet units | Lines with GP down / up |
|---|---|---|---|---|---|---|---|
| SC1 | none | 41 (28) | −£15,609 | −0.1% | 0 | 0 | 28 / 0 |
| SC1 | low | 41 (28) | −£5,663 | −0.0% | −4,286 | +885 | 28 / 0 |
| SC1 | central | 41 (28) | +£290 | +0.0% | −6,861 | +1,422 | 6 / 22 |
| SC1 | high | 41 (28) | +£14,272 | +0.1% | −12,857 | +2,669 | 6 / 22 |
| SC2 | all | 0 | £0 | 0% | 0 | 0 | — (no line was eligible to price) |
| SC3 | none | 205 (74) | −£45,989 | −0.4% | 0 | 0 | 74 / 0 |
| SC3 | low | 205 (74) | −£9,389 | −0.1% | −10,594 | +158 | 74 / 0 |
| SC3 | central | 205 (74) | +£12,631 | +0.1% | −16,958 | +262 | 3 / 71 |
| SC3 | high | 205 (74) | +£62,062 | +0.6% | −31,282 | +996 | 0 / 74 |
| SF75 | none / low / central / high | 5 (5) | −£1,710 / −£313 / +£326 / +£1,241 | ≈0% | 0 / −577 / −863 / −1,346 | 0 / 0 / +65 / +393 | 5/0, 5/0, 1/4, 1/4 |

In SC1 and SC3, about 68–73% of the markdowns are tagged `MANDATORY_REVIEW`.

**How to read the results:**
- **Benefits depend on customers responding.** Gross profit rises only with a central or high response. With no
  response, every line that was marked down loses money; with a low response, every one also loses money.
- **Unmet units are a harm.** Illustrative unmet units rise whenever customers respond, because demand on markdown
  days can exceed the stock on the shelf.
- **The effects are small.** They are at most 0.6% of scenario gross profit, and the expiry reductions are under 1% of
  expired units. Only lines eligible for markdown review are ever priced.
- **The preregistered loss limits were lenient.** The limits for the low and no-response cases (10% and 25% of the
  scenario's baseline expired-stock cost) were passed by a very wide margin, because that cost is large. They are not
  changed after the results; a stricter, line-level loss test would need a new, separately preregistered evaluation.
- **SC2 adds nothing to the outcome.** It produced no markdowns, so its tests are NOT_APPLICABLE and it contributes
  nothing to the result.

## 6. Limitations

- **Customer response is an assumption.** It is not a measured elasticity; the central 1.6%/pt is a non-causal
  association.
- **Commercial inputs are proxies.** Prices are an estimated proxy and costs an assumed margin, so gross-profit
  figures are illustrative.
- **Everything else comes from the simulation.** Stock, expiry and demand are simulated or forecast, and recorded
  sales are not unconstrained demand.
- **Ordering does not react to pricing.** This is by design in Phase 2: price-aware ordering is out of scope.
- **The markdown window is simple.** It covers the oldest batch only, and one price applies to all stock on those
  days.
- **Not modelled:**
  - effects between products (cannibalisation, halo)
  - competitor prices
  - legal and commercial pricing rules
  - store operations
  - real approvers
- **The cooldown does not bind** at weekly cadence (see section 3).
- **Output size.** Daily outputs are saved only for lines with at least one markdown. The run folder is about 89 MB.

## 7. Cooldown rule decision (2026-10-24)

**A1 is the PREFERRED RESEARCH RULE — NOT PRODUCTION APPROVED.** Decision record:
`config/decisions/phase2_cooldown_rule_decision.json` (DEC-PH2-COOLDOWN-2026-10-24-v1, registered).

| | Preferred research rule | Retained comparison |
|---|---|---|
| Rule | A1: 7 complete days after the previous markdown window ends | Original: 7 days between weekly decisions (never binds) |
| Assumptions / simulator | v8 (DRAFT) / v1.4 | v7 (DRAFT) / v1.3 |
| Evaluation policy | EP-PH2-A1-2026-10-24-v1 | EP-PH2-2026-10-23-v1 |
| Run | `20261024-002535_dynamic_pricing_evaluation_a1` | `20261023-233225_dynamic_pricing_evaluation` (re-run and reproduced exactly) |

**Rationale.**
- A1 meets the pre-frozen preference criteria PA–PE.
- It reduces losses when customers respond weakly or not at all: in SC3, −£43,569 instead of −£45,989 with no
  response, and −£8,910 instead of −£9,389 with low response.
- It reduces mandatory reviews in SC3 from 150 to 134.
- It gives up some upside, which was accepted: +£11,868 instead of +£12,631 with central response, and +£58,534
  instead of +£62,062 with high response.
- SC1, SC2 and SF75 are identical under both rules.

**Limitations.**
- The evidence comes from SC3 only (74 lines).
- The data is synthetic, customer response is assumed, and prices and costs are proxies.
- The comparison is exploratory, because the original results were seen first.
- None of this is commercial proof.

**What the decision does not change.** It changes no pricing algorithm, threshold, assumption set or protected output.
The Dynamic Pricing Lab shows A1 by default and keeps the original selectable. It stays read-only, with every markdown
SIMULATED / HYPOTHETICAL_UNAPPROVED / NOT_EXECUTED.
