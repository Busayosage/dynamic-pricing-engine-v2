# Phase 2 amendment A1 — evaluation results (SIMULATED RESEARCH, NOT VALIDATED FOR LIVE USE)

| Item | Value |
|---|---|
| Rule | A1: a new markdown may start only after 7 complete days since the previous markdown ended |
| Evaluation policy | EP-PH2-A1-2026-10-24-v1, frozen and registered before the full A1 run |
| A1 run | `outputs/runs/20261024-002535_dynamic_pricing_evaluation_a1`: assumption set v8, simulator v1.4, registered |
| Original run | `outputs/runs/20261023-233225_dynamic_pricing_evaluation`: v7, simulator v1.3, unchanged |

The original evaluation, assumptions, policies, code and protected outputs are unchanged. The comparison is
exploratory, because the original results and the impact analysis had been seen before the policy was frozen.

## Verification

All of these passed:
- **Pricing off still reproduces the protected P2 replay** in SC1, SC2, SC3 and SF75 (E1).
- **Orders are fixed** (E2), and the in-loop eligibility matches the saved Markdown review (E3).
- **The original is reproduced.** The frozen original was re-run in all 16 scenario × response combinations and
  reproduced the protected original decisions exactly. Its thresholds also matched the original evaluation.
- **All A1 safety gates pass** in all 16 runs:
  - G1 conservation
  - G2 orders unchanged
  - G3 markdown only and price bounds
  - G4 guards
  - G5 chronology
  - G6 labels
  - G7 no-response demand equals baseline
  - G8 the A1 cooldown
- **A1 meets the original thresholds T1–T5** in SC1 and SC3. SC2 is not applicable, because it had no markdowns.
- **Every protected checksum** still matches after the run.

Stock, expiry, demand and every later decision were recalculated in the simulation. Nothing was patched onto the 26
originally affected events.

## Results

Changes are against unchanged prices.

| Scenario | True response | Gross profit (original → A1) | Expired units | Unmet units | Markdowns | Decisions blocked by A1 | Lines with profit up/down | Mandatory reviews |
|---|---|---|---|---|---|---|---|---|
| SC1 | all four | identical | identical | identical | 41 → 41 | 1 (no markdown affected) | identical | 28 → 28 |
| SC2 | all four | 0 → 0 | 0 | 0 | 0 → 0 | 0 | — | 0 |
| SF75 | all four | identical | identical | identical | 5 → 5 | 0 | identical | 5 → 5 |
| SC3 | none | −£45,989 → **−£43,569** | 0 → 0 | 0 → 0 | 205 → 190 | 69 | 0/74 → 0/74 | 150 → 134 |
| SC3 | low | −£9,389 → **−£8,910** | −10,594 → −10,144 | +158 → +158 | 205 → 190 | 69 | 0/74 → 0/74 | 150 → 134 |
| SC3 | central | +£12,631 → **+£11,868** | −16,958 → −16,226 | +262 → +262 | 205 → 190 | 69 | 71/3 → 71/3 | 150 → 134 |
| SC3 | high | +£62,062 → **+£58,534** | −31,282 → −29,913 | +996 → +996 | 205 → 190 | 69 | 74/0 → 74/0 | 150 → 134 |

How to read the table:
- **The blocked count includes weeks that would not have produced a markdown.** "Decisions blocked by A1" also counts
  weeks the cooldown now labels as blocked that had no markdown under the original (for example, insufficient
  evidence). The net change is 15 fewer markdowns in SC3, not 69.
- **A1 is a trade-off, not a uniform improvement:**
  - It loses **less** when customers respond weakly or not at all: +£2,420 better with no response, +£479 with low.
  - It gains **less** when they respond: −£762 with central, −£3,528 with high response.
  - It avoids slightly fewer expired units.
- **What A1 leaves unchanged:** unmet units and the number of profitable and loss-making lines stay the same.
- **Review workload falls:** mandatory reviews go from 150 to 134 in SC3.
- **The differences are small** relative to the totals: under 0.1% of SC3 gross profit.

## Preregistered preference rule (SC1–SC3)

| Test | Result |
|---|---|
| PA: all checks and gates pass | PASS |
| PB: meets the original thresholds | PASS |
| PC: loses no more than the original with no or low response | PASS |
| PD: keeps at least 75% of the original's central benefit | PASS: 94.1% of gross-profit gain (£12,158 vs £12,921); 96.9% of expired units avoided (23,087 vs 23,819) |
| PE: no more unmet units than the original | PASS (equal) |

Outcome under the frozen rule: **A1_PREFERRED_RESEARCH_COOLDOWN**. This is a research preference only, not commercial
proof.

## Recommendation

**Adopt A1 as the preferred research cooldown rule, as a risk-control choice rather than a performance gain.**
- **It does what the rule intends.** It stops consecutive-week repeat markdowns, reduces review workload and limits
  losses if customer response is weak.
- **It costs some upside.** It gives up about 6% of the simulated gain in the central case and about 6% in the high
  case.
- **The original remains valid.** The original rule's results remain valid and preserved for the v7 rule.

## Limitations

- Every limitation of Phase 2 applies: the customer response is assumed, the pricing and cost inputs are proxies,
  stock and expiry are simulated, and the data is synthetic.
- **The evidence comes from one scenario.** Only SC3 differs between the rules, so it rests on 74 lines in one
  scenario.
- **The preference thresholds are judgement calls.** The 75% retention level and the other preference thresholds were
  set before the run, but they are value judgements.

## Decision (2026-10-24)

The project owner approved A1 as the **PREFERRED RESEARCH RULE — NOT PRODUCTION APPROVED**.
- Decision record: DEC-PH2-COOLDOWN-2026-10-24-v1, in `config/decisions/phase2_cooldown_rule_decision.json`.
- The original rule and its evaluation are preserved as a reproducible comparison.
