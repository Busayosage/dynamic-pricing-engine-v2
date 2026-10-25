# Step 4D: challenger results (one round, exploratory)

- **Status:** the one-round challenger study is **complete and closed** under the firm stopping rule. **Both incumbents are retained.** Nothing is selected, deployed or promoted.
- **Date:** 2026-10-22
- **Policy:** [STEP_4D_REPLACEMENT_POLICY.md](STEP_4D_REPLACEMENT_POLICY.md), written before any challenger was trained.
- **Design:** [STEP_4D_CHALLENGER_DESIGN.md](STEP_4D_CHALLENGER_DESIGN.md)
- **Runs** (both protected):
  - `outputs/runs/20261022-011204_challenger_backtest/`: predictions, training metadata, integrity checks, manifest with code hashes
  - `outputs/runs/20261022-011554_challenger_evaluation/`: replacement matrix, incumbent bootstrap, diagnostics, decisions

> **EXPLORATORY.** The six folds (target weeks 29–52) were already examined in CP3–CP5. The bootstrap intervals below are conservative **within-sample** statements on **reused folds**, not independent confirmation. The data is *apparently synthetic; provenance unconfirmed*. Nothing here describes real shopper behaviour.

---

## 1. Outcome

| Horizon | Incumbent | Outcome (pre-registered policy) | Strongest challenger | Why the incumbent is retained |
|---|---|---|---|---|
| **H1** | Random Forest, 25.92% WAPE | **RETAIN_INCUMBENT** | CatBoost 25.77% (+0.58% relative) | Every challenger fails R3a (≥ 2% better than the RF) and R3b (interval above 0), plus CP5 G5 (F6 bias beyond ±10%). The RF itself passed G5 at −9.16%. |
| **H4** | Four-week moving average, 29.41% WAPE | **RETAIN_INCUMBENT** | CatBoost 27.78% (+5.57% relative) | **CatBoost passes every rule except CP5 gate G5** (F6 bias −13.03% vs ±10%). XGBoost also fails R3d (Meat +1.67 points); SES fails most rules. |

**The H4 CatBoost result, stated exactly:**
- It meets R1 integrity, eight of the nine CP5 gates, all four incumbent-relative rules (R3a–R3d) and both bias rules (R4a, R4b).
- Its 99.17% two-way bootstrap interval of improvement over the four-week average is **+2.08% to +8.72%** (store sensitivity +2.27% to +8.81%). It is better in **6 of 6** folds and **15 of 15** stores, with no category worse.
- It fails G5 only in the Christmas fold. **The incumbent fails that same gate in that fold (−12.13%), and so does every model at H4.**
- The policy requires all nine CP5 gates to pass, so the outcome is **retain the incumbent**.
- Per DECISION 15 the thresholds are not revised after seeing results. Whether G5 should apply relative to the incumbent in *future* studies is a policy question for you (section 8). It is not a change to this result.

---

## 2. Pooled results (17,280 rows per horizon; identical rows for every model)

| Model | H1 WAPE | H1 Bias | H1 MAE | H1 RMSE | H4 WAPE | H4 Bias | H4 MAE | H4 RMSE |
|---|---|---|---|---|---|---|---|---|
| last_week | 34.08% | −1.29% | 550.1 | 802.5 | 34.99% | −2.63% | 564.8 | 822.9 |
| mean_4w (**H4 incumbent**) | 27.89% | −2.17% | 450.2 | 654.5 | **29.41%** | −2.85% | 474.7 | 686.6 |
| Random Forest (**H1 incumbent**) | **25.92%** | −1.76% | 418.3 | 607.2 | 28.84% | −0.50% | 465.4 | 665.2 |
| XGBoost | 26.00% | −2.35% | 419.7 | 614.1 | 28.27% | −1.01% | 456.3 | 658.5 |
| CatBoost | 25.77% | −2.50% | 415.9 | 606.6 | 27.78% | −2.44% | 448.3 | 651.2 |
| SES | 27.78% | −0.47% | 448.3 | 645.4 | 29.76% | −0.33% | 480.3 | 688.2 |

**Improvement over the incumbent** (relative WAPE; Bonferroni-adjusted 99.17% two-way series × week-block bootstrap; 5,000 replicates; seed 20261022):

| Horizon | Challenger vs incumbent | Point | 99.17% CI (primary) | 99.17% CI (store) | Replicates better |
|---|---|---|---|---|---|
| H1 | XGBoost vs RF | −0.32% | −1.46% to +0.86% | −1.50% to +0.84% | 22% |
| H1 | CatBoost vs RF | +0.58% | −0.58% to +1.74% | −0.61% to +1.82% | 90% |
| H1 | SES vs RF | −7.16% | −12.70% to −2.79% | −12.51% to −2.99% | 0% |
| H4 | XGBoost vs mean_4w | +3.89% | +0.40% to +6.96% | +0.49% to +7.08% | 99.9% |
| H4 | **CatBoost vs mean_4w** | **+5.57%** | **+2.08% to +8.72%** | **+2.27% to +8.81%** | 100% |
| H4 | SES vs mean_4w | −1.17% | −8.24% to +4.44% | −8.19% to +4.59% | 35% |

---

## 3. Replacement matrix (status per rule)

| Rule | H1 XGB | H1 CatB | H1 SES | H4 XGB | H4 CatB | H4 SES |
|---|---|---|---|---|---|---|
| R1.1–R1.4 integrity (tests 110/110, rows, finite, refit identical) | PASS | PASS | PASS | PASS | PASS | PASS |
| R1.5 negative control / R1.6 inner sanity | PASS / PASS | PASS / PASS | n/a | PASS / PASS | PASS / PASS | n/a |
| R2 CP5 G0–G4 | PASS | PASS | G1–G3 FAIL | PASS | PASS | G1–G3 FAIL |
| R2 CP5 **G5** per-fold bias ±10% | **FAIL** (−10.08%, F6) | **FAIL** (−10.35%) | FAIL (−11.83%) | **FAIL** (−11.41%) | **FAIL** (−13.03%) | FAIL (−13.44%) |
| R2 CP5 G6–G8 | PASS | PASS | FAIL | PASS | PASS | FAIL |
| R3a ≥ 2% vs incumbent | FAIL (−0.32%) | FAIL (+0.58%) | FAIL | PASS (+3.89%) | **PASS (+5.57%)** | FAIL |
| R3b 99.17% CI > 0 | FAIL | FAIL | FAIL | PASS | **PASS** | FAIL |
| R3c ≥ 5/6 folds better | FAIL (2/6) | FAIL (4/6) | FAIL (0/6) | PASS (5/6) | **PASS (6/6)** | FAIL (3/6) |
| R3d category ≤ +1 point | PASS | PASS | FAIL (Bakery +4.35) | **FAIL (Meat +1.67)** | **PASS** | FAIL |
| R4a pooled \|bias\| ≤ incumbent + 1 | PASS | PASS | PASS | PASS | PASS | PASS |
| R4b folds beyond ±10% ≤ incumbent's | FAIL (1 vs 0) | FAIL (1 vs 0) | FAIL | PASS | PASS | PASS |
| **Outcome** | Retain | Retain | Retain | Retain | **Retain (G5 only)** | Retain |

The full matrix, with thresholds and observed values, is in `replacement_matrix.csv`.

---

## 4. Folds (WAPE %)

| Fold | H1 RF | H1 XGB | H1 CatB | H1 SES | H4 mean_4w | H4 XGB | H4 CatB | H4 SES |
|---|---|---|---|---|---|---|---|---|
| F1 (29–32) | 26.32 | 26.20 | 25.89 | 30.30 | 30.74 | 29.70 | **28.42** | 34.07 |
| F2 (33–36) | 26.04 | 25.78 | 25.63 | 29.09 | 30.11 | 28.51 | **27.93** | 32.41 |
| F3 (37–40) | 24.47 | 24.61 | 24.41 | 26.03 | 27.09 | 25.19 | **24.81** | 27.54 |
| F4 (41–44) | 24.78 | 24.90 | 24.83 | 25.33 | 26.72 | 25.60 | **25.34** | 25.47 |
| F5 (45–48) | 25.52 | 25.67 | 25.27 | 26.24 | 28.15 | 26.60 | **26.50** | 26.67 |
| F6 (49–52) | 28.05 | 28.44 | 28.18 | 29.56 | 33.14 | 33.24 | 32.84 | **32.33** |

**F6 bias:**

| Model | H1 | H4 |
|---|---|---|
| RF | −9.16% | −12.52% |
| mean_4w | −9.56% | −12.13% |
| XGBoost | −10.08% | −11.41% |
| CatBoost | −10.35% | −13.03% |
| SES | −11.83% | −13.44% |

**Every model exceeds ±10% at H4 in F6.**

---

## 5. Segments

**Categories** (WAPE %):

| Category | H1 RF | H1 CatB | H1 XGB | H1 SES | H4 mean_4w | H4 CatB | H4 XGB | H4 SES |
|---|---|---|---|---|---|---|---|---|
| Bakery | 27.48 | 27.43 | 27.62 | 31.82 | 32.70 | 31.11 | 31.33 | 36.62 |
| Beverages | 24.82 | 24.40 | 24.71 | 26.59 | 28.21 | 26.35 | 26.79 | 28.96 |
| Dairy | 24.87 | 24.85 | 25.17 | 25.73 | 27.33 | 25.34 | 25.68 | 26.08 |
| Meat | 28.71 | 28.53 | 28.36 | 28.94 | 32.36 | 32.34 | 34.03 | **29.74** |

**Stores** (number of 15 better than the incumbent):

| Horizon | XGBoost | CatBoost | SES |
|---|---|---|---|
| H1 (vs RF) | 6 | 10 | 0 |
| H4 (vs mean_4w) | 14 | 15 | 4 |

**Discounted target weeks** (analysis only; never an input):

| Horizon | Bias range across all models | Notes |
|---|---|---|
| H1 | −14.2% to −16.4% | Undiscounted weeks +2.4% to +4.3% |
| H4 | −13.7% to −16.6% | No challenger reduces the S0 discount gap, as expected without plans |

**Holiday target weeks.** Bias −6.2% to −9.9% for every model. There is no meaningful separation between models.

---

## 6. Focused diagnostics

### 6.1 Christmas (weeks 51–52)

| Model | H1 WAPE / bias | H4 WAPE / bias |
|---|---|---|
| RF | 30.2% / −15.4% | 37.6% / −20.0% |
| mean_4w | 32.0% / −16.2% | 36.0% / −19.6% |
| XGBoost | 30.9% / −16.8% | 37.0% / −19.0% |
| CatBoost | 30.8% / −17.0% | 36.9% / −20.6% |
| SES | 32.3% / −18.7% | 35.8% / −20.9% |

- **Same pattern for every model.** Bakery −30% to −53%, Meat −23% to −39%, Beverages +6% to +32% (Beverages fall at Christmas).
- **No challenger handles Christmas.** As before, the run-up never appears in training.

**Excluding weeks 51–52:**

| Model | H1 WAPE | H4 WAPE |
|---|---|---|
| CatBoost | 25.18% | 26.71% |
| RF | 25.41% | — |
| mean_4w | — | 28.64% |

### 6.2 Meat (H4, folds F1–F3)

**Meat bias:**

| Model | F1 | F2 | F3 |
|---|---|---|---|
| RF | +41.4% | +40.2% | +24.2% |
| XGBoost | +39.1% | +35.7% | +14.8% |
| CatBoost | +25.7% | +34.8% | +16.2% |
| mean_4w | +17.4% | +20.9% | +0.8% |
| SES | **+3.9%** | +16.3% | +8.7% |

**Forecast relative to origin-week sales**, against actual 0.84 / 0.90 / 1.01:

| Model | F1 | F2 | F3 |
|---|---|---|---|
| RF | 1.19 | 1.27 | 1.26 |
| XGBoost | 1.17 | 1.23 | 1.16 |
| CatBoost | 1.06 | 1.22 | 1.18 |

**Conclusion.** The June step-up over-forecast is **shared by all three tree models**, so it is not RF-specific. It is consistent with the trees learning the early-summer jump from too few months of training targets. SES, with a low smoothing level (median α 0.05 in F1), reacts least.

### 6.3 Integrity checks

| Check | Result |
|---|---|
| Leakage and integrity tests (re-run at evaluation) | 110 passed, 0 failed (features, panel, backtest, models, challengers) |
| Rows | Every challenger has 17,280 rows per horizon, identical keys, origins, targets and actuals to CP4 |
| Reproducibility | F1 refits for all models and both horizons: **bit-identical** (difference 0) |
| Negative control (permuted training targets, F3) | WAPE 0.99–1.04× a constant predictor. No feature-label leakage. |
| Inner sanity (F3, last 4 training weeks; selects nothing) | All boosted models beat last_week on the inner block |
| SES | Median α 0.05 (F1) to 0.17 (later folds); 1–10 convergence warnings per fold (of 720 series), recorded in `training_metadata.csv` |

---

## 7. Budget and environment

- **Fits:** exactly as budgeted: 24 boosted plus 4 reproducibility, 4 negative-control and 4 inner-sanity fits, plus SES.
- **Run time exceeded the estimate:** 87 minutes for the backtest, against the "under 30 minutes" design estimate.
  - CatBoost took about 285 s per fit (1,000 iterations with native categoricals, 4 threads).
  - XGBoost and SES took about 2–3 s per fold.
  - Evaluation took 3 minutes.
- **Packages installed** from `requirements-challenger.txt` after a dry-run compatibility check: xgboost 3.2.0, catboost 1.2.10, graphviz 0.21, plotly 7.1.0, narwhals 2.27.1.
- **The environment diff shows only these five additions.** Every core pin in `requirements.txt` is unchanged, and this is tested.

---

## 8. Interpretation, limits and open questions

1. **H1.** The RF is not improved upon. Its lead over CatBoost and XGBoost is within noise, and SES is clearly worse. The RF remains the H1 research candidate.
2. **H4.** CatBoost gives the strongest signal of the round. It is the only challenger that clears the incumbent-relative bar, and it does so in every fold and store.
   - Under the pre-registered policy it **does not** replace the four-week average, because it fails the absolute Christmas-fold bias gate. Every H4 model fails that gate, the incumbent included.
   - This is a **genuine policy tension**: the absolute G5 gate cannot be met by any model at H4 with this data. It is recorded here for your decision **for future studies only**. Changing it now would be the retroactive revision the policy forbids.
3. **Not independent evidence.** The intervals are on reused folds. Even the H4 CatBoost interval is not confirmation. Confirmation would need untouched data, such as the first 8–12 weeks of 2025.
4. **Shared weaknesses** are unchanged by any model: Christmas weeks 51–52, the bias on discounted weeks, and the Meat step-up. They are properties of the data and the S0 information set.
5. **The firm stop applies.** No further models, tuning, features or Christmas/target-month work is started. The next step is decision support (Step 5), subject to your approval.
