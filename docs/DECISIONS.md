# Approved decisions (21 Oct 2026)

1. Price, discount and marketing are planned inputs only when known before the forecast date; otherwise use clearly labelled scenarios.
2. Evaluate forecasts with and without weather. Never use actual future weather as if it were a weather forecast.
3. No Git initialisation until .gitignore is reviewed and approved.
4. The incomplete backup venv is left untouched.
5. Original Random Forest scores are reference benchmarks; new results are not forced to match.
6. Four-week forecasts use only information available at the forecast origin.

## Step 4B CP1–CP2 (21 Oct 2026)

7. Forecasts have an explicit origin week T and target week T + h (H1: h = 1, H4: h = 4); one direct model per horizon, no recursion on predictions.
8. S0 (no plans) is the primary forecast. Target-week discount, marketing and price enter only as declared plan inputs (S1, S2); actual weather only as the non-deployable diagnostic S3. Wastage is never a model input.
9. Holiday_Flag is treated as a regional holiday calendar known in advance (assumption).
10. Origins need 8 observed weeks; missing history is excluded or raises an error, never filled with zero.
11. Store_ID and Product_ID are kept on every row and enter models only as one-hot identity columns.
12. Acceptance thresholds in STEP_4A section 10 are provisional until the backtest results are reviewed; any bootstrap comparison uses series x week-block resampling (STEP_4A section 14).

## Step 4B CP5 handoff (21 Oct 2026; evidence: outputs/runs/20261021-214104_cp5_acceptance, docs/STEP_4B_CP5_ACCEPTANCE.md)

13. H1 (one week ahead): the S0 Random Forest (300 trees, depth 12, seed 42) is the preferred research candidate (WAPE 25.92%; all nine CP5 gates PASS).
14. H4 (four weeks ahead): the four-week moving average is retained as the preferred research candidate (WAPE 29.41%); the H4 Random Forest failed gates G1, G5, G6, G7 and G8.
15. The original CP5 acceptance thresholds and verdicts are preserved as recorded; they are not revised retrospectively.
16. Numerical reproducibility tolerance: forecasts agree within 1e-6 forecast units (absolute). Bit-exact equality is not claimed for parallel (n_jobs=-1) runs.
17. Neither model is approved for production deployment.

## Step 4D challenger round (approved 21 Oct 2026; results 22 Oct 2026; evidence: docs/STEP_4D_CHALLENGER_RESULTS.md)

18. Challenger scope: XGBoost, CatBoost and per-series simple exponential smoothing; LightGBM excluded. Option A: one fixed pre-registered configuration per model, no tuning on the six folds; inner validation for sanity checks only.
19. Replacement policy: docs/STEP_4D_REPLACEMENT_POLICY.md (written before training) - separate from the CP5 gates, which are unchanged. All challenger results are exploratory; bootstrap significance on reused folds is not independent confirmation.
20. Challenger dependencies are pinned in requirements-challenger.txt (xgboost 3.2.0, catboost 1.2.10, graphviz 0.21, plotly 7.1.0, narwhals 2.27.1); core pins in requirements.txt are unchanged.
21. Outcome under the pre-registered policy: no challenger qualifies; the H1 Random Forest and the H4 four-week moving average remain the preferred research candidates (DECISIONS 13-14 unchanged). The H4 CatBoost result (+5.57% vs mean_4w; failed only CP5 gate G5 in the Christmas fold) is recorded as exploratory evidence, not adopted.
22. The challenger round is closed (one-round budget, firm stop). Any future model study needs new, untouched data and a policy agreed before results are seen.

## Step 5A design and 5B-1 forecast contract (22 Oct 2026; evidence: docs/STEP_5A_DECISION_ENGINE_DESIGN.md, docs/STEP_5B1_FORECAST_CONTRACT.md)

23. The Step 5A decision-engine design is approved; Step 5 is decision support with human approval, not automated or optimised pricing.
24. Forecast contract v1.0 (run 20261022-081926_forecast_contract) is the single forecast input for downstream modules: H1 Random Forest and H4 four-week moving average from the protected runs, no retraining; decision-time fields and replay-only fields are kept in separate files.
25. Uncertainty bounds use only errors observed by the origin (same model, horizon, category; at least 4 target weeks); otherwise they are UNAVAILABLE. This replaces the fallback proposed in Step 5A section 4.1.
26. Pending review: the assumptions listed in STEP_5B1_FORECAST_CONTRACT.md section 8 (holiday calendar, origin-week observation, reference-price definition, uncertainty settings).

## Step 5B-1 acceptance and 5B-2 design/implementation (22 Oct 2026; evidence: STEP_5B2_BUSINESS_ASSUMPTIONS_DESIGN.md v2, STEP_5B2_REPLAY_SIMULATOR_RESULTS.md)

27. Forecast contract v1.0 accepted with conditions: the 2024 holiday calendar is for historical replay only; an origin occurs after that week's sales and prices are finalised; the reference price is an estimated proxy; p10/p50/p90 bounds are provisional; forecasts without bounds require human review; weekly forecasts are never presented as daily stockout or expiry predictions.
28. Step 5B-2 design v2 approved: planning weight clip((target - 50)/40, 0, 1) between p50 and p90, capped at p90 (extrapolation disabled); coverage positions are heuristics, not probabilities; day-level simulated schedule for short-life items; arrival on day 1 + lead time only; one review case per decision point (Christmas = mandatory escalation, missing bounds = mandatory review, holiday = flag only).
29. Assumption set AS-2026-10-22-v1 (config/assumptions/assumption_set_v1.json) created as DRAFT; all ASSUMED/SYNTHETIC values are illustrative and unsupported by business data; approval does not change its content hash; an approved set is immutable and changes require a new version.
30. The chronological replay simulator (src/dpe/decision/replay.py) is the SYNTHETIC inventory engine for demonstrations; short-life multi-drop orders exist only under the explicit SHORT_LIFE_RECURRING_DROPS arrangement; recorded sales are illustrative demand and simulated unmet units are never observed lost sales.
31. Pending your decision: LIFE_LEAD_TIME_TIGHT as a material trigger (applies to 180 series in normal trading), and redefining the coverage-position trigger (inert as specified); see STEP_5B2_REPLAY_SIMULATOR_RESULTS.md section 9.

## Step 5B-2 replay correction checkpoint (23 Oct 2026; evidence: docs/STEP_5B2_REPLAY_CORRECTION_RESULTS.md)

32. LIFE_LEAD_TIME_TIGHT is an informational warning; it escalates only together with a material operational risk and is preserved in the review evidence (resolves item 31, first part).
33. Shortage pressure is assessed on pre-order coverage (stock plus committed deliveries before the new order can arrive); post-order coverage (proposed drops on their scheduled arrival days) shows whether the order addresses its window. Both are heuristic positions, not stockout probabilities or daily forecasts (resolves item 31, second part).
34. Christmas remains a mandatory escalation. No action is approved or executed without an explicit approval event; all simulated orders and outcomes are hypothetical and unauthorised.
35. Simulator v1.1 runs are the current replay evidence; the v1.0 runs are kept unchanged for comparison. Pending your review; the assumption set remains DRAFT.

## Step 5B-3a to 5B-3d (23 Oct 2026; evidence: STEP_5B3_IMPLEMENTATION_READINESS.md, STEP_5B3D_ASSUMPTION_SET_V2.md)

36. Inventory engine decisions D1-D12 approved as recorded in STEP_5B3_IMPLEMENTATION_READINESS.md section 1; stages 5B-3a (calculator), 5B-3b (recommendations, review queue v1.2) and 5B-3c (simulator v1.2) accepted.
37. P0 baseline fixed: 4-week recorded-sales average, netting stock on hand only, ignoring expiry and committed deliveries; not revised again.
38. Preliminary SC1 P0/P2 totals were seen during 5B-3c integration; the P0/P1/P2 comparison is exploratory rather than fully confirmatory; preregistered thresholds unchanged.
39. P2 blocks actionable ordering when bounds are missing in either required horizon (policy-specific safety difference); P1 keeps v1.1 behaviour.
40. Assumption set AS-2026-10-23-v2 created as DRAFT (production_use false); v1 preserved unchanged and remains the set used by the protected runs; SF75 = SC1 with realised receipts at 75% and planning at 100%, no order inflation.

## Step 5B-3e controlled policy comparison (23 Oct 2026; evidence: STEP_5B3E_POLICY_COMPARISON_RESULTS.md, run 20261023-131711_policy_comparison)

41. Evaluation policy EP-5B3E-2026-10-23-v1 (config/evaluation/evaluation_policy_5B3e_v1.json) froze the preregistered thresholds and was checksum-registered before the comparison; thresholds unchanged.
42. Comparison outcome (exploratory, synthetic): all hard gates pass for P0/P1/P2 in SC1-SC3 and SF75; P2 meets every adoption threshold against P1 in SC1-SC3. Recommended: P2 as the research replay default, P1 retained for regression. Pending your decision; no policy is approved for live use.
43. Parameter-count correction: assumption set v1 has 24 parameters (not 26); v2 has 36 = 24 carried forward + 12 added; no values changed.
