# Step 5B-3e: Controlled inventory policy comparison (P0 / P1 / P2)

**Date:** 23 Oct 2026.

**Status:** SYNTHETIC and EXPLORATORY, for review.

**Run:** `outputs/runs/20261023-131711_policy_comparison`, protected with 59 checksums.

**Evaluation policy:** `config/evaluation/evaluation_policy_5B3e_v1.json` (EP-5B3E-2026-10-23-v1).
- SHA-256 `430d17bf…a79b`.
- Frozen and registered at 12:38, before the comparison started at 12:59.

**Assumption set:** AS-2026-10-23-v2, which remains DRAFT with `production_use: false`.

**Read this first:**
- **This comparison is exploratory, not confirmatory.** Preliminary SC1 totals for P0 and P2 were seen during Stage 5B-3c,
  before this run.
- **Operational inputs are partly synthetic.** Opening stock, supplier arrangements, case sizes, MOQ and fill rates are
  ASSUMED or SYNTHETIC.
- **Historical sales are not verified unconstrained demand.** Simulated unmet units are illustrative, never observed lost
  sales.
- **No real-world result is established.** No waste reduction, lost-sales prevention or margin improvement has been shown.
- **No inventory policy is approved for live deployment.** Every simulated order is hypothetical, unapproved and not
  executed.

## 1. Pre-run verification

| Check | Result |
|---|---|
| Parameter count | **36 = 24 carried forward from v1 + 12 added.** The "26" in the 5B-3d report was a documentation error, because v1 has 24 parameters. Business values are unchanged. The 5B-3d document and changelog are corrected. |
| Thresholds located | `docs/STEP_5B3_IMPLEMENTATION_READINESS.md` section 2, SHA-256 `12cc2676…cd7c` |
| Frozen policy record | Dated and versioned. Every value was cross-checked against the source table. |
| Checksum registered before the run | Yes, with the source document and the v2 file: 293 → 296 entries at 12:38 |
| Policy not changed after the preliminary results | The source document was last modified at 08:51, before the 11:03 timing check that exposed SC1 totals. The frozen values equal the source values. |
| Preliminary exposure preserved | Recorded in the policy file, in the v2 `evaluation_record` and here |
| v1 and protected runs unchanged | All 296 checksums verified before and after the run. The v1 file hash and its DRAFT status were confirmed. |

**Run log:** the first attempt (12:41) failed while writing the results. A numpy integer could not be serialised to
JSON. Only partial SC1 tables had been written, and no results were displayed. The fix was to serialisation only; no
policy, metric or threshold changed. The partial folder `20261023-125852_policy_comparison` is marked
`INCOMPLETE_RUN_NOT_VALID`, is not registered, and must not be used.

## 2. Results by scenario

All units are simulated. Unmet units are illustrative.

| Scenario | Policy | Ordered | Unmet (illustr.) | Expired | Fill % (illustr.) | Expired % of received | Residual shortfall after order | Weekly cases | Standing cases | Rounding excess % |
|---|---|---|---|---|---|---|---|---|---|---|
| SC1 | P0 | 18,227,094 | 5,523,260 | 724,493 | 76.5 | 4.0 | – | 7,920 | 0 | 0.99 |
| SC1 | P1 | 25,466,832 | 834,870 | 2,763,370 | 96.4 | 10.9 | 29 (v1.1 flag) | 11,397 | 0 | 0.73 |
| SC1 | **P2** | 25,509,570 | **812,838** | 2,781,470 | 96.5 | 10.9 | **0** | **9,171** | 360 | 0.72 |
| SC2 | P0 | 20,654,616 | 11,539,466 | 103,642 | 57.3 | 0.7 | – | 18,720 | 0 | 0.89 |
| SC2 | P1 | 30,073,668 | 5,147,154 | 415,087 | 80.9 | 1.8 | 0 | 19,109 | 0 | 0.62 |
| SC2 | **P2** | 30,081,270 | 5,142,554 | 416,192 | 81.0 | 1.9 | 0 | 19,109 | 360 | 0.62 |
| SC3 | P0 | 16,406,166 | 3,202,766 | 1,920,011 | 84.0 | 10.8 | – | 7,920 | 0 | 1.07 |
| SC3 | P1 | 23,179,602 | 139,453 | 5,713,748 | 99.3 | 22.8 | 111 (v1.1 flag) | 12,680 | 0 | 0.78 |
| SC3 | **P2** | 23,302,074 | **119,352** | 5,829,033 | 99.4 | 23.1 | **0** | **8,936** | 360 | 0.78 |
| SF75 | P0 | 20,247,780 | 7,924,866 | 180,626 | 66.2 | 1.2 | – | 18,532 | 0 | 0.90 |
| SF75 | P1 | 28,710,390 | 2,564,488 | 829,602 | 89.1 | 3.9 | 0 | 18,805 | 0 | 0.64 |
| SF75 | **P2** | 28,716,426 | 2,560,941 | 830,411 | 89.1 | 3.9 | 0 | 18,805 | 360 | 0.64 |

### Common risk indicators

These indicators use identical rules for every policy. They come from each policy's own decision-time state and
proposed deliveries, measured with the 5B-3a calculator.

| Scenario | Shortage before delivery (P0 / P1 / P2) | Shortfall after the proposed order (P0 / P1 / P2) | Existing-stock expiry above 15% of p50 (P0 / P1 / P2) |
|---|---|---|---|
| SC1 | 7,852 / 957 / 924 | 14,239 / 528 / **0** | 2 / 112 / 94 |
| SC2 | 10,702 / 5,281 / 5,279 | 14,138 / 299 / **0** | 2 / 3 / 3 |
| SC3 | 6,111 / 277 / 242 | 13,956 / 1,137 / **0** | 32 / 409 / 379 |
| SF75 | 10,899 / 4,213 / 4,209 | 14,193 / 90 / **0** | 0 / 7 / 7 |

**Safety violations:** zero, in every policy and scenario.

## 3. Acceptance gates, evaluated individually

### Hard gates

These apply to all 12 policy × scenario runs. **All pass.**

| Gate | Result |
|---|---|
| G1 a–d: conservation, carry-over, integer non-negative stock, weekly totals equal the sum of daily values | PASS, 12 of 12 |
| G2 a: arrival on schedule | PASS, 12 of 12 |
| G2 b: whole cases, at least MOQ | PASS, 12 of 12 |
| G2 c: expiry-day rule | PASS, 12 of 12 |
| G2 d: no quantity when blocked | PASS, 12 of 12 |
| G2 e: short-life label | PASS for P2: 7,200 short-life proposals checked in each scenario. **Not applicable** to P0 and P1, as predeclared in the frozen policy: they produce no recommendation records. |
| G2 f: Supply_Capacity unused | PASS, 12 of 12 |
| G3 a: no approval, execution or authorisation | PASS, 12 of 12 |
| G3 b: Christmas = MANDATORY_ESCALATION (2,880 points) | PASS, 12 of 12 |
| G3 c: missing bounds = mandatory review (5,040 points) | PASS, 12 of 12 |
| G3 d: leakage, scramble and mutation tests; reads only after the decision | PASS. 37 tests ran in a subprocess, and run-level reads were checked. |
| G3 e: banned wording absent | PASS, 12 of 12 |
| G3 f: P1 reproduces protected v1.1 exactly | PASS. SC1–SC3 decisions, deliveries, weekly, daily and review cases are all identical. P1 under v2 also equals P1 under v1. |
| G3 g: protected checksums | PASS before and after the run |

### Quantitative thresholds, P2 against P1

| Threshold | SC1 | SC2 | SC3 |
|---|---|---|---|
| T-U unmet | 0.974 (limit 1.00): **PASS** | 0.999 (limit 1.02): **PASS** | 0.856 (limit 1.02): **PASS** |
| T-E expired | 1.007 (limit 1.05): **PASS** | 1.003 (limit 1.05): **PASS** | 1.020 (limit 1.05): **PASS** |
| T-O ordered | 1.002 (limit 1.05): **PASS** | 1.000 (limit 1.10): **PASS** | 1.005 (limit 1.10): **PASS** |
| T-R workload | 0.805 (limit 1.10); mandatory 5,040 / 2,880 identical: **PASS** | 1.000; identical: **PASS** | 0.705; identical: **PASS** |
| T-S residual shortfall | P2 0 vs P1 29: **PASS** | 0 vs 0: **PASS** | 0 vs 111: **PASS** |
| T-X rounding (report only) | 0.72% vs 0.73%; no category above 10% | 0.62% vs 0.62% | 0.78% vs 0.78% |

**SF75 (stress assessment, not an adoption gate):** hard gates pass. Results are reported above.

**Outcome under the frozen rule:** P2 meets every adoption criterion in SC1, SC2 and SC3. Nothing was waived.

## 4. Scientific interpretation

### Where P2 improves on P1

- **Unmet units:** fewer, by 2.6% in SC1 and 14.4% in SC3. The difference comes from a minority of series:
  - SC1: 84 of 720 series improve, none get worse, and 636 are unchanged.
  - SC3: 67 improve and none get worse.
- **Where the gains are:** mostly in Dairy and Meat. These are the categories where existing stock expires inside the
  coverage window, the case v1.1 over-credits.
- **Unaffected:** Beverages (long life) are unaffected.
- **Decisions changed:** only 744 of 14,400 decisions in SC1, and 1,432 in SC3.
- **Shortfall after the order:** eliminated by construction. It falls from 528 in SC1 and 1,137 in SC3 (P1, common
  indicator) to 0.

### Where P2 is worse

- **Expiry:** slightly higher, by 0.65% in SC1 and 2.0% in SC3 (+115,285 units). For expiry, 86 series in SC1 and 90 in
  SC3 are worse, against 1 better in each.
- **Ordered units:** slightly higher, by 0.17% in SC1 and 0.53% in SC3.

### Do the improvements cost extra expiry or orders?

Yes, modestly. P2 orders to cover days that existing stock can no longer reach. Some of those units then expire in turn,
under the illustrative demand path.

In SC3, P2 cuts unmet units by 20,101 and adds 115,285 expired units. Whether that trade-off is worthwhile is a business
question. It cannot be settled with assumed margins (D10).

### Review-workload changes are mostly rule differences, not better decisions

**SC1 risk cases fall from 3,477 to 1,251.** The main reason is how each queue judges expiry risk:
- The P1 (v1.1) queue raises WASTE_HIGH_EXISTING_STOCK 2,379 times. That flag is measured at p50 with no new orders.
- The P2 (v1.2) queue measures existing-stock expiry at the planning rate after p50 depletion to arrival. It raises
  EXPIRY_BEFORE_COVERAGE only 75 times.
- In P2, lead-time warnings no longer appear in case reasons, and supplier confirmation moves to 360 separate standing
  cases.

**SC2 and SF75 workloads are identical (19,109 and 18,805).** In both scenarios, the last-week fill-shortfall trigger fires
at almost every decision (10,800 times), so both queues escalate the same points.

The lower P2 workload in SC1 and SC3 should therefore not be read as evidence that P2 makes better decisions. It also
means the provisional 15% expiry trigger flags fewer points than the v1.1 waste band did. That trigger may need
recalibrating (section 6).

### Sensitivity to assumed stock, demand and supplier arrangements

- **Stock (SC3, excess opening stock and lower demand):** the P2–P1 difference is largest here. With high opening stock,
  more stock expires mid-window. P2's advantage depends on the synthetic opening stock and batch-expiry structure.
- **Demand and supply pressure (SC2):** P1 and P2 are almost identical, with unmet units within 0.1%. There is little
  usable stock to mis-credit, so the policies diverge only when stock is plentiful but short-dated.
- **Supplier fulfilment (SF75):** P1 and P2 respond the same way, with unmet units of 2.56M against 0.83M at 100%
  fulfilment. Neither policy plans for short delivery, by design (D3). The common indicators show the exposure.
- **Supplier arrangements:** the assumed recurring and weekend short-life drops are common to all policies and were not
  varied. All 360 short-life series rely on them, so every short-life result is conditional on that unverified
  arrangement.
- **No intervals:** confidence intervals and bootstraps were not computed; the frozen policy did not require them. The
  differences are point comparisons on one illustrative demand path.

### P0 baseline (context only, no gate)

The preregistered expiry-blind baseline orders far less (18.2M in SC1) and leaves about 6.6 times as many illustrative
unmet units as P1. It has much less expiry.

Its rule nets all stock on hand against next week's window. It ignores the demand that uses that stock before the order
arrives. That rule is simple by design and makes P0 a weak reference. P2's margin over P0 says little about P2's absolute
quality.

## 5. Recommendation

Under the frozen evaluation policy, **P2 meets every adoption criterion**. The recommendation is to adopt P2 as the
**research replay default** for later development stages, with P1 kept for regression and comparison.

This is a research-default choice inside a synthetic, exploratory replay. It is **not** approval of any inventory policy
for live use. The assumption sets remain DRAFT.

## 6. Remaining blockers before waste-risk and pricing development

1. **Your decision on this recommendation:** P2 as the research replay default, or retain P1.
2. **The provisional expiry trigger** (15% of weekly p50, measured at the planning rate) flags far fewer points than the
   v1.1 waste band. It needs a decision before the waste-risk engine relies on it.
3. **The expiry/availability trade-off in SC3** needs a business framing. The cost proxies are assumed and excluded (D10).
4. **The short-life supplier arrangement remains unconfirmed** for all 360 series. Any waste-risk or markdown logic on
   short-life lines inherits this.
5. **No real stock, expiry, receipt or cost data exist.** Any real-world claim needs that data and a confirmatory study
   with untouched data.
6. **The assumption sets v1 and v2 are DRAFT** and not for production. Approval, if ever, needs your explicit decision.
7. **Run size:** the protected run is about 506 MB, mostly decision tables. It is worth considering before any
   repository work.
