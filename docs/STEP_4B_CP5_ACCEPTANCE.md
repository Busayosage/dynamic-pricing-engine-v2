# Step 4B, checkpoint 5: model acceptance and bootstrap review

- **Status:** CP5 is complete. **No model was retrained, tuned, selected, deployed or promoted.** The CP3 and CP4 predictions were read, not modified. **Awaiting approval.**
- **Date:** 2026-10-21
- **Review run:** `outputs/runs/20261021-214104_cp5_acceptance/`
- **Inputs (protected, checksum-verified):**
  - CP3 baselines: `outputs/runs/20261021-175029_baseline_backtest/`
  - CP4 Random Forest: `outputs/runs/20261021-180522_rf_backtest/`

> The dataset is *apparently synthetic; provenance unconfirmed*. Every verdict below is a statement about this dataset and these backtests. **A statistical PASS is not a deployment approval.** Feature importance and segment patterns are associations, not causes.

---

## 1. Recommendation per horizon

| Horizon | Recommendation (fixed decision rule) | Statistical significance | Predictive accuracy | Bias | Operational deployment suitability |
|---|---|---|---|---|---|
| **H1** (one week ahead) | **Accept Random Forest**, as the best-performing S0 forecast *in this backtest* | **PASS.** +7.07% relative improvement, 95% CI **+5.88% to +8.29%** (series × week-block); store sensitivity +5.82% to +8.34% | **PASS** on G1, G2, G3, G6, G7: better in 6/6 folds, 15/15 stores and 4/4 categories | **PASS** on G4 and G5, but F6 bias −9.16% is close to the ±10% limit | **Not yet suitable** (section 7) |
| **H4** (four weeks ahead) | **Retain the four-week moving average** | **FAIL.** +1.96% relative improvement, 95% CI **−0.32% to +4.26%**, which includes zero; store sensitivity −0.65% to +4.62% | **FAIL** on G1 (1.96% < 3%), G6 (Meat +3.51 points) and G7 (9/15 stores). **PASS** on G2 (5/6 folds) and G3 | G4 **PASS** (pooled −0.50%); G5 **FAIL** (F6 −12.52%) | **Not suitable**, and the baseline is preferred anyway |

**Decision rule**, fixed in code before results were computed:
- **ACCEPT** if every gate passes.
- **RETAIN BASELINE** if G1 (accuracy) or G8 (significance) fails.
- **REQUIRE FURTHER VALIDATION** otherwise.

H1 passes every gate. H4 fails both G1 and G8, so the rule returns "retain baseline". "Require further validation" would have applied to H4 if it had passed G1 and G8 but failed only consistency, bias or segment gates.

---

## 2. Acceptance matrix (thresholds exactly as in STEP_4A section 10; not revised)

| Gate | Criterion | Threshold | H1 observed | H1 | H4 observed | H4 |
|---|---|---|---|---|---|---|
| G0 | Leakage and integrity tests pass | all pass | 79 passed, 0 failed | **PASS** | 79 passed, 0 failed | **PASS** |
| G1 | Relative WAPE improvement vs mean_4w | ≥ 5% (H1), ≥ 3% (H4) | 7.07% | **PASS** | 1.96% | **FAIL** |
| G2 | Folds where RF WAPE is lower | ≥ 5 of 6 | 6 of 6 | **PASS** | 5 of 6 | **PASS** |
| G3 | Worst fold, RF minus mean_4w | ≤ +1.0 points | −1.65 (F1) | **PASS** | +0.36 (F6) | **PASS** |
| G4 | Pooled RF bias | within ±5% | −1.76% | **PASS** | −0.50% | **PASS** |
| G5 | Largest per-fold RF bias | within ±10% | −9.16% (F6) | **PASS** | −12.52% (F6) | **FAIL** |
| G6 | Worst category, RF minus mean_4w | ≤ +2.0 points | −1.48 (Meat) | **PASS** | +3.51 (Meat) | **FAIL** |
| G7 | Stores where RF WAPE is lower | ≥ 13 of 15 | 15 of 15 | **PASS** | 9 of 15 | **FAIL** |
| G8 | 95% bootstrap interval excludes zero | lower bound > 0 (primary and store sensitivity) | [5.88%, 8.29%]; [5.82%, 8.34%] | **PASS** | [−0.32%, 4.26%]; [−0.65%, 4.62%] | **FAIL** |

**Status rules** (recorded in the manifest before evaluation):
- "Improved" means strictly lower WAPE; a tie counts as not improved.
- "At least" and "within" bounds are inclusive.
- **G0:** INCONCLUSIVE if the tests were not run.
- **G8:** PASS needs both intervals above 0. FAIL if the primary interval is not above 0. INCONCLUSIVE if the primary interval is above 0 and the store-sensitivity interval is not.

No gate came out INCONCLUSIVE.

**G0 evidence.** The four forecasting test files (features, panel, backtest, models) were re-run in a subprocess at CP5: 79 tests, exit code 0. They include the truncation, future-scrambling, boundary, training-cut-off, wastage and protected-file tests.

**Reproducibility.** The original design's G0 also mentioned "outputs reproducible". That is reported separately in section 6, because bit-exact reproducibility does not hold for the parallel run and the tolerance is still a proposal.

---

## 3. Independent verification (`verification.json`)

| Check | Result |
|---|---|
| Checksums of both input runs (CP3: 7 files; CP4: 19 files) | Verified before reading |
| CP3 and CP4 baseline rows (keys, forecasts, actuals) | **Identical** (outer join, 0 unmatched) |
| Identical scoring rows | All 3 models share the same rows in each of the 12 fold-horizon cells; 17,280 rows per model per horizon; no duplicates |
| Fold membership | Every target week sits in the correct fold (F1 29–32 … F6 49–52) |
| Forecast origins | origin_week = target − *h* and target_date − origin_date = *h* weeks for every row |
| Actual sales | Equal to the verified panel's units for every row |
| Baselines recomputed from the panel | last_week = units at the origin (exact); mean_4w = mean of weeks *T*−3…*T* (within 10⁻⁹) |
| RF forecasts | Finite and ≥ 0 |
| Reported metrics recomputed from rows | CP4 pooled and by-fold, CP3 pooled and by-fold: max difference **1.1 × 10⁻¹³** |

---

## 4. Bootstrap procedure and results

**Procedure** (`acceptance.two_way_bootstrap`):

| Setting | Value |
|---|---|
| Unit of analysis | Per horizon, the paired predictions of the RF and mean_4w on the same 17,280 rows |
| Cells | Absolute errors and actual units summed into **clusters × week blocks**: 720 store-product series (or 15 stores, for sensitivity) × **6 blocks of 4 consecutive target weeks** (the folds F1–F6) |
| Resampling | Each replicate draws clusters **with replacement** and, independently, the **6 week blocks with replacement**. A cell's weight is (times its cluster was drawn) × (times its block was drawn). Both models use the same weights (paired). |
| Statistic | Relative WAPE improvement = 100 × (1 − Σw·\|e_RF\| / Σw·\|e_mean_4w\|). Also the WAPE difference in points. |
| Replicates | 2,000 |
| Seed | 20261021 (NumPy `default_rng`) |
| Interval | 95% percentile interval (2.5th and 97.5th percentiles) |
| Why two-way | Errors are correlated within a series across weeks, and across series within a week. Resampling only one dimension treats the other as independent and gives intervals that are too narrow. |

**Results** (relative improvement, %):

| Horizon | Variant | Point | 95% CI | WAPE difference CI (points) | Replicates with RF better | Excludes zero? |
|---|---|---|---|---|---|---|
| H1 | **series × week-block (primary)** | 7.07 | **5.88 to 8.29** | −2.31 to −1.64 | 100% | **Yes** |
| H1 | store × week-block (sensitivity) | 7.07 | 5.82 to 8.34 | −2.33 to −1.63 | 100% | Yes |
| H1 | series only | 7.07 | 6.40 to 7.72 | −2.16 to −1.78 | 100% | Yes |
| H1 | week-block only | 7.07 | 6.38 to 7.84 | −2.18 to −1.80 | 100% | Yes |
| H4 | **series × week-block (primary)** | 1.96 | **−0.32 to 4.26** | −1.20 to +0.10 | 95.0% | **No** |
| H4 | store × week-block (sensitivity) | 1.96 | −0.65 to 4.62 | −1.30 to +0.20 | 92.6% | No |
| H4 | series only | 1.96 | 0.87 to 3.05 | −0.90 to −0.26 | 100% | Yes |
| H4 | week-block only | 1.96 | 0.17 to 3.82 | −1.08 to −0.05 | 98.4% | Yes |

**Reading.** For H4, the one-dimensional bootstraps would have suggested a significant improvement. The dependence-aware two-way interval does not. **The H4 improvement is not distinguishable from zero** once correlation across both weeks and series is respected.

**Caveat.** With only 6 week blocks, the block dimension is coarse, and percentile intervals from 6 blocks can be unstable. The H1 conclusion is robust across all four variants. The H4 conclusion depends on the two-way design, which is the pre-registered primary method.

---

## 5. Diagnostics (existing predictions only; no features or settings changed)

### 5.1 H4 Meat instability

| Evidence | H4 F1 | H4 F2 | H4 F3 | H4 F4–F6 |
|---|---|---|---|---|
| Meat RF bias (CP4) | +41.4% | +40.2% | +24.2% | −3% to +1% |
| Meat actual / origin-week sales | **0.84** | 0.90 | 1.01 | 0.99–1.29 |
| Meat RF forecast / origin-week sales | **1.19** | **1.27** | **1.26** | 0.99–1.03 |
| Meat mean_4w forecast / origin-week sales | 0.99 | 1.09 | 1.02 | 0.99–1.00 |
| Meat target/origin ratio in the model's last training month | **1.29** (June) | 0.99 (July) | 0.79 (Aug) | 0.97–1.01 |

**The level shift.** Meat sales sit about 92% of their annual mean until week 22, jump to about 120% for weeks 23–29 (3 June – 15 July), then fall back to about 92% from week 30 (`meat_weekly_level.csv`).

**What the H4 forest did.**
- The F1 model's training ends at target week 25. Its final month of training targets is June, where Meat targets were **1.29× their origin-week sales**: the step-up.
- It then forecast Meat at **1.19–1.27× the origin level** throughout F1–F3, while actual sales fell to 0.84–1.01× the origin level.
- From target week 29 to week 40, its Meat forecasts exceed actuals by 15–56% in every week. The four-week average's error shrinks once its window passes the high period.

**Month coverage.** Every H4 fold tests target months absent from its training targets. For example, F1 trains on March–June and tests July–August (`target_month_coverage.csv`). So the forest can only map new months onto the months it has seen.

**Interpretation (diagnosis, not proven).**
- The forest appears to have learned a "Meat jumps four weeks after late May/June" relationship, and kept applying it after the shift had ended.
- The persistence into F3, whose training already includes the August fall, shows that more than the last month is involved, possibly the interplay of `target_month`, level and hierarchy features.
- Isolating the cause would need retraining experiments. That is not allowed in CP5, and it should only be done with an inner validation split, never by tuning on these folds.
- This is **not leakage**: all inputs were available at the forecast origin.
- The H1 forest shows a smaller version in F1 (Meat forecast 1.14× origin against 0.94× actual).

### 5.2 Christmas weeks (51 = 16 Dec, 52 = 23 Dec)

**Actual uplift** versus the average of weeks 45–50:

| Category | Week 51 | Week 52 |
|---|---|---|
| Bakery | +66% | +79% |
| Meat | +54% | +60% |
| Dairy | +6% | +5% |
| Beverages | −12% | −12% |

**Bias by category, weeks 51 and 52:**

| Category | H1 mean_4w | H1 RF | H4 mean_4w | H4 RF |
|---|---|---|---|---|
| Bakery | −37% / −32% | −38% / −30% | −45% / −47% | −49% / −53% |
| Meat | −35% / −29% | −34% / −23% | −36% / −38% | −35% / −37% |
| Dairy | −5% / −3% | −6% / −5% | −7% / −5% | −9% / −8% |
| Beverages | +10% / +6% | +14% / +10% | +22% / +18% | +32% / +31% |

- **The Christmas pattern is category-specific.** A large rise in Bakery and Meat, a fall in Beverages.
- **No training fold contains anything like it.** The holiday weeks available to F6 training are 13, 17, 21, 35 and 48. Week 1 is never a training target, because it lacks history.
- **Every model is wrong in the same direction.** The H4 RF is the worst on Bakery and Beverages.
- **It accounts for the F6 bias** that fails G5 for H4 and nearly fails it for H1 (−9.16%).
- **No S0 model can fix it with this data.** The only Christmas in the dataset is the one being forecast.

---

## 6. Reproducibility review (`reproducibility_review.json`)

| Item | Value |
|---|---|
| Observed refit difference (CP4: H1 F1 and H4 F1) | max **9.09 × 10⁻¹³ units** |
| Median RF forecast | 1,386 units |
| Relative size | 6.6 × 10⁻¹⁶ ≈ **3.0 machine epsilons** (float64 ε = 2.2 × 10⁻¹⁶) × median forecast |
| Largest possible effect on WAPE | 5.6 × 10⁻¹⁴ percentage points (both horizons) |
| Cause | With `n_jobs=-1`, scikit-learn sums the 300 tree predictions in parallel threads. The addition order can vary between runs, and floating-point addition is not associative, so the last bits can differ. Single-threaded refits (`n_jobs=1`, tested) are bit-identical. |
| Bit-exact for the protected parallel run? | **No, and not claimed** |
| Proposed tolerance (needs your approval) | \|Δ\| ≤ **1 × 10⁻⁶ units** absolute (with `rtol` 1 × 10⁻⁹ for ratio checks) |
| Within the proposed tolerance? | Yes, by six orders of magnitude |
| Alternative | Run with `n_jobs=1` whenever bit-exact reruns are required (slower) |

The protected CP4 run was not altered.

---

## 7. Why "accept" for H1 is not a deployment approval

The following hold for **both** horizons and are independent of the gates:

1. **Data:** apparently synthetic, provenance unconfirmed, one year only.
2. **Christmas:** weeks 51–52 are under-forecast by 14–21% overall, and by up to about 50% for Bakery and Meat. No model handles them.
3. **Discounts:** discounted weeks are under-forecast by about 15% in S0. Plan-based scenarios (S1/S2) have not been run.
4. **Calendar:** no holiday calendar exists beyond 2024-12-23, so forecasts for 2025 cannot be built yet.
5. **Margin:** H1 F6 bias (−9.16%) is close to the ±10% limit. One more bad week would fail G5.
6. **Reproducibility:** holds only within a tolerance that is not yet approved.
7. **Scope:** no out-of-sample period beyond these six folds, and no operational test (data latency, all-store availability at the origin).

---

## 8. Outputs (`outputs/runs/20261021-214104_cp5_acceptance/`)

| File | Content |
|---|---|
| `acceptance_matrix.csv` | 18 rows (9 gates × 2 horizons): criterion, threshold, observed, status |
| `recommendations.json` | Recommendation per horizon; significance, accuracy, bias and deployment dimensions; decision rule |
| `verification.json` | Independent verification evidence |
| `bootstrap/bootstrap_summary.csv` | 8 rows (4 variants × 2 horizons) |
| `bootstrap/bootstrap_replicates_relative_improvement_pct.csv` | 2,000 replicate values per variant and horizon |
| `diagnostics/target_month_coverage.csv` | Training vs test target months per fold and horizon |
| `diagnostics/forecast_and_actual_relative_to_origin_week.csv` | Actual and forecast vs origin-week sales; last-training-month ratio |
| `diagnostics/meat_by_target_week.csv`, `diagnostics/meat_weekly_level.csv` | Meat error and level by week |
| `diagnostics/weeks_45_52_by_category.csv`, `diagnostics/christmas_uplift_vs_weeks_45_50.csv` | Christmas analysis |
| `diagnostics/reproducibility_review.json` | Section 6 |
| `manifest.json` | Inputs and checksums, thresholds and source, status and decision rules, bootstrap procedure, leakage test result, "nothing retrained, tuned, selected or promoted" |

---

## 9. Tests and integrity

- **New tests:** 17, in `tests/test_forecast_acceptance.py`. They cover:
  - frozen thresholds (attempting to revise one raises an error)
  - inclusive bounds; FAIL, PASS and INCONCLUSIVE logic; the decision rule
  - bootstrap correctness (degenerate cases, seeded reproducibility, pairing, cell reconciliation)
  - real-data verification, and detection of 4 kinds of corruption (baseline forecast, fold label, actual, reported metric)
  - month coverage and reproducibility review
  - new-folder-only writing; CP4 run protected
- **Full suite:** **210 passed, 0 failed** (193 earlier + 17 new).
- **Protection:**
  - CP4 run `20261021-180522_rf_backtest` added to the protected paths; its 19 files recorded in `CHECKSUMS.sha256`; writes blocked.
  - All files that existed before CP5 are byte-identical.
  - `reference_baseline.py` and every forecasting module used for CP4 (features, models, backtest, baselines) are unchanged.

**Files created or changed:**
- `src/dpe/config.py` (RF run protection)
- `docs/CHECKSUMS.sha256`
- `src/dpe/forecast/acceptance.py` (new)
- `scripts/run_cp5_acceptance.py` (new)
- `tests/test_forecast_acceptance.py` (new)
- this document
- `docs/CHANGELOG.md`

---

## 10. Decisions needed from you

1. **H1:** confirm the "accept Random Forest (S0)" recommendation as the H1 candidate, with section 7 recorded as deployment blockers.
2. **H4:** confirm "retain the four-week moving average".
3. **Reproducibility tolerance:** approve 1 × 10⁻⁶ units, or require `n_jobs=1` bit-exact runs.
4. **Gates:** the thresholds were provisional. They stand as applied here unless you decide otherwise. Any change would apply to *future* evaluations only, and would be recorded.
5. **Next steps** (not started): for example, the S1/S2 plan scenarios; a pre-agreed inner-validation experiment on `target_month`; a Christmas/event strategy; or moving to Step 5 (pricing) with the H1 forecast.
