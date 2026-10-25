# Phase 2 — Dynamic Pricing Engine: design proposal (NOT IMPLEMENTED)

**Status:** proposal awaiting approval. Nothing in this document is built. Every output it describes would be
SIMULATED, HYPOTHETICAL_UNAPPROVED and NOT_EXECUTED, with no live price changes, approval buttons or integrations.

## 1. What Phase 1 and earlier stages provide (reused unchanged)

| Component | File | Reused for |
|---|---|---|
| Replay chronology, initial state, deliveries, oldest-first selling, expiry, conservation checks | `replay.py` (v1.1) | The same daily mechanics; called through its helpers and never edited |
| Pluggable ordering policies P0/P1/P2, standard risk indicators | `replay_v12.py` (v1.2) | Ordering stays P2 by default; `pol.decide(...)` is called unchanged |
| Time-phased stock projection | `inventory.py` | Units at risk and their dates at each decision |
| Waste-risk classification | `waste_risk.py` (`classify`) | High / Moderate / Low per decision |
| Markdown eligibility rules | `markdown_eligibility.py` | Which lines may be considered |
| Rule checks (promotion, steps, maximum markdown, margin floor) | `pricing_demo.options` | Mandatory option constraints |
| Single-line ranking, evidence gates, materiality, downside guard, explanations | `discount_recommendation.recommend_line` | The per-decision pricing choice |
| Forecast contract p10 / p50 / p90 | protected run `20261022-081926_forecast_contract` | Decision-time demand and uncertainty |
| Assumption sets v1–v6 (DRAFT) | `config/assumptions/` | Carried forward unchanged into a new v7 |
| Evaluation pattern: preregistered thresholds, hard gates, P1 regression | `policy_comparison.py`, EP-5B3E | The template for the Phase 2 evaluation policy |

## 2. Why dynamic pricing is different from Phase 1

| Phase 1 (single line) | Phase 2 (over time) |
|---|---|
| One decision for one line, evaluated in isolation | A price decision every week for every eligible line, inside the chronological replay |
| The effect of a markdown is calculated once, from a frozen stock snapshot | A markdown changes sales, which changes stock, expiry, the next waste-risk class, the next eligibility and the next pricing decision |
| The order is ignored | The order for the same week is decided first; committed deliveries change what is at risk |
| No memory | Needs memory: cooldown between markdowns, a limit on consecutive markdown weeks, and a return to the reference price after the window |
| Result = an expected £ change from assumed responses | Result = a paired simulation against **prices unchanged**, run under each "true" customer response, with outcomes measured inside the simulation |

The central design choice is to keep the engine's **belief** separate from the simulated **world**. The engine
decides using its weighted scenarios (R1/R2/R3, as in Phase 1). Each replay is then run with one fixed "true"
response (R0, R1, R2 or R3). This shows how the policy behaves when its belief is wrong, including when customers do
not respond at all.

## 3. Proposed decision sequence (per origin week T, per series)

1. **Inventory decision.** The P2 order is decided with the existing code and the decision-time state only. The
   pricing step cannot change the order.
2. **State assessment.** Compute from the same state:
   - the existing-stock expiry projection
   - the waste-risk class
   - the oldest batch's last sellable day
   - the investigate-by day
   - the shortage-before-delivery check
3. **Eligibility.** Apply the Stage 7B rules unchanged, including the Christmas, shortage and recorded-promotion
   blockers. Ineligible lines stay at the reference price.
4. **Temporal guards (new, all ASSUMED in v7).** A line that fails any guard is not marked down:
   - a cooldown since the last simulated markdown (a value must be stated explicitly; v5 currently says NOT_DEFINED)
   - a maximum number of markdown weeks in any 4 weeks
   - no markdown on stock that arrived in the same week
   - markdown only: no price above the reference price, and no surge pricing
5. **Pricing choice.** Call the Phase 1 `recommend_line` with:
   - decision-time inputs only
   - the window from the investigate-by day to the last sellable day
   - the evidence gates, materiality and downside guard from v6

   Results other than a recommendation leave the price unchanged.
6. **Review classification.** Every simulated markdown is a hypothetical proposal tagged `PENDING_HUMAN_REVIEW`.
   - Inside the replay it is applied only as `SIMULATED_AS_IF_APPROVED`, so its consequences can be measured.
   - Markdowns of 20% or more, repeat markdowns, and lines with an open inventory review case are also tagged
     `MANDATORY_REVIEW`.
7. **Simulate the week.** Daily selling uses the price in force that day. On markdown days, demand is recorded
   demand × scenario multiplier × (1 + r_true × points / 100). Revenue is booked at the price actually charged. The
   price returns to the reference after the window.
8. **Record and check.** Record price, sold, expired, unmet and revenue per day. Then check:
   - conservation of units
   - price within the floor and the maximum markdown
   - no markdown on a blocked day
   - zero approvals and zero executions

**Safeguards:**
- A chronology guard: demand for week T+1 cannot be read before decision T. This is the existing `DemandAccess`
  guard, extended to prices.
- Pricing never feeds the ordering logic in Phase 2. Price-aware ordering is a later, separate decision.
- Pricing off must reproduce the protected P2 results exactly.

## 4. Data limitations — what must stay assumed

| Input | Status in Phase 2 |
|---|---|
| Customer response to price | **ASSUMED** scenarios (R0–R3). No causal elasticity exists; the 1.6%/point figure stays non-causal |
| Purchase cost | **ASSUMED** margin on the reference-price proxy |
| Shelf / regular price | **ESTIMATED** proxy; recorded prices are noisy (±70%), so the conflict gate remains |
| Batch stock and expiry | **SIMULATED** by the replay, not observed |
| Demand | Recorded sales × scenario multiplier: illustrative, not unconstrained demand |
| Cooldown, markdown-frequency limits, review thresholds | **ASSUMED**, new in v7, explicitly stated |
| Cross-product effects (cannibalisation, halo), competitor prices, store operations, legal rules | **Not modelled**; listed as limitations |
| Approvals | **None exist.** "As if approved" is a simulation convention only |

## 5. How the engine would be tested against keeping prices unchanged

1. **Regression gate.** With pricing off, the new simulator must reproduce the protected P2 outputs exactly:
   - run `20261023-131711_policy_comparison`
   - all scenarios, every daily row
2. **Paired comparison.** Run the same series, scenario, ordering policy and demand path with and without pricing.
   Every difference is then caused by pricing alone. The grid is:
   - "true" response: R0, R1, R2, R3
   - market scenario: SC1, SC2, SC3, SF75
3. **Measures, each against prices unchanged:**
   - simulated gross profit (revenue at the price charged − assumed cost of delivered units − disposal)
   - simulated expired units
   - illustrative unmet units
   - number of markdowns and review workload
   - the depth and frequency of discounts
4. **Preregistered evaluation policy.** A frozen JSON is registered in `docs/CHECKSUMS.sha256` **before** the run, as
   for EP-5B3E. Proposed thresholds:
   - **R2 true:** expiry must fall and gross profit must not fall.
   - **R0 true:** the total loss may not exceed a stated share of the at-risk stock cost.
   - **R1 true:** the loss must be bounded.
   - **Every run:** the hard gates (conservation, price bounds, blockers respected, zero approvals and executions,
     chronology) must pass 100%.
5. **Sensitivity checks.** Vary each of these and report the results; none is used for adoption:
   - margins ±10 points
   - disposal cost 0% or 20%
   - cooldown values
   - decision weights
6. **Unit tests**, as in Phase 1, for:
   - the temporal guards
   - the return to the reference price
   - determinism
   - the chronology guard
   - "no markdown" lines matching the baseline exactly

## 6. The proposed dashboard page: Dynamic Pricing Lab

The page would keep the existing navy and teal design and contain, in order:

1. **Header and labels.** The page carries "SIMULATED RESEARCH — NOT VALIDATED FOR LIVE USE", the research
   disclaimer, and the evidence key (recorded / simulated / assumed / hypothetical).
2. **Portfolio summary against prices unchanged.** Gross-profit change, expiry change, markdown count and review
   cases, for the selected market scenario. A selector chooses the **true** response scenario, with R0 always one
   click away.
3. **Belief vs truth matrix.** A small table of gross-profit and expiry changes for each true response × market
   scenario, with pass/fail chips from the preregistered thresholds.
4. **Series timeline (one store and product).**
   - Price path as a step line: reference price vs simulated markdowns.
   - Stock and expiry, with pricing vs unchanged, as two separate single-axis charts.
   - Markers where a markdown was considered and why it was or was not applied.
5. **Hypothetical price-change log.** Each simulated markdown with its date, depth, window, explanation, review tag
   (`PENDING_HUMAN_REVIEW` / `MANDATORY_REVIEW`) and `SIMULATED_AS_IF_APPROVED`. The log is read-only, with no
   buttons.
6. **Evaluation gates.** Preregistered thresholds and hard gates with PASS/FAIL, plus the regression result.
7. **Expanders.** Formulas, v7 parameters, provenance, and run IDs with checksums.

## 7. Files proposed

**Create:**
- `config/assumptions/assumption_set_v7.json` and `scripts/build_assumption_set_v7.py`. This is a DRAFT that carries
  v6 forward, plus:
  - the cooldown
  - the markdown-frequency limit
  - the true-response grid
  - the review thresholds
  - markdown only
- `src/dpe/decision/assumptions_v7.py`: the v7 validator, rules X1–X7.
- `src/dpe/decision/dynamic_pricing.py`: the per-decision pricing policy. It covers state assessment → eligibility →
  temporal guards → Phase 1 `recommend_line` → review tags.
- `src/dpe/decision/replay_pricing.py`: simulator v1.3. It composes the v1.2 ordering and v1.1 mechanics with a
  price-aware selling step, and with pricing off it reproduces v1.2 exactly.
- `src/dpe/decision/pricing_evaluation.py`: the paired runs, metrics, hard gates and preregistered thresholds.
- `docs/PHASE_2_EVALUATION_POLICY.json`: frozen and registered before any run.
- `scripts/run_dynamic_pricing_evaluation.py`: writes one new run directory under `outputs/runs/`, only when you
  approve the run.
- `tests/test_dynamic_pricing.py` and `tests/test_replay_pricing.py`.
- `app/dashboard/pages/7_Dynamic_pricing_lab.py`: reads the saved run only.

**Modify (append-only or additive):**
- `app/dashboard/dashboard_data.py` and `ui.py`: read-only loaders for the new run.
- `Home.py`: a navigation card.
- `pages/7_Future_features.py`, renamed to `8_Future_features.py`.
- `tests/test_dashboard.py`.
- `docs/CHANGELOG.md`.
- `docs/CHECKSUMS.sha256`: new entries appended only.

**Not modified:**
- `replay.py`, `replay_v12.py`, `inventory.py`, `waste_risk.py`, `markdown_eligibility.py`, `pricing_demo.py` and
  `discount_recommendation.py`. Any needed change would become a new versioned module.
- Assumption sets v1–v6.
- Every protected run and historical output.

## 8. Approval needed before implementation

- The decision sequence: order first, then price; pricing never feeds ordering in Phase 2.
- The markdown-only scope (no price increases).
- That stating a cooldown value and a markdown-frequency limit as new **assumptions** is acceptable.
- The evaluation design: paired against prices unchanged, true responses R0–R3, and thresholds frozen before the run.
- That one new run directory may be written for the evaluation.
