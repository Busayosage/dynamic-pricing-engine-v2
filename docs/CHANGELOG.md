# Changelog

## 2026-10-21 — Step 3a
- Created V2 folder structure.
- Copied 5 raw CSVs, reference merged dataset, reference validation predictions,
  3 original modelling scripts and 2 legacy v1 pricing scripts (SHA-256 verified).
- run_pricing_to_airtable.py deliberately NOT copied (contains a hard-coded credential).
- Added original notebook as reference copy: legacy/perishable_project/notebooks/ (SHA-256 verified).

## 2026-10-21 — Step 3b (preparation only; nothing executed)
- requirements.txt pinned (7 packages); requirements-dev.txt added (3 packages).
- Added src/dpe/config.py (V2-only paths, checksum verification, write guard).
- Added src/dpe/reference_baseline.py (faithful port of baseline_model.py with ID preservation).
- Added scripts/reproduce_reference_baseline.py, pytest.ini and tests/ (no model training in tests).
- Added docs/STEP_3B_REPRODUCTION.md.

## 2026-10-21 — Milestone: Random Forest recovery verified (run 20261021-133846_reference_rf)
- Reproduced the Oct 2025 baseline inside V2 from checksum-verified raw data.
- Random Forest: MAE 487.237, RMSE 714.034, R2 0.635, WAPE 27.939%.
- Naive baseline: MAE 597.105, RMSE 878.517, R2 0.448, WAPE 34.239%.
- Validation 2024-11-04 to 2024-12-23, 5,760 rows; predictions match the Oct 2025 reference (RF max diff 2.7e-12).
- Run files preserved unchanged; SHA-256 recorded in docs/STEP_3B_REPRODUCTION.md.

## 2026-10-21 — Step 3C-C1: EDA development (code only; nothing executed)
- config.py: verified run 20261021-133846_reference_rf added to protected paths; its 3 files added to CHECKSUMS.sha256.
- .gitignore: credential variants (.env.*, keeping .env.example), test/coverage caches, extra SQLite files.
- Added src/dpe/eda/ (data, quality, stats, analysis, plots, report, outputs, pipeline) and scripts/run_eda.py.
- Added notebooks/01_eda.ipynb (read-only; outputs cleared).
- Added tests: test_eda_quality, test_eda_analysis, test_eda_stats, test_eda_outputs, test_notebook; conftest eda_raw fixture.

## 2026-10-21 — Step 3C-C2/C3: test fix and first full EDA run (20261021-160432_eda)
- tests/test_eda_quality.py: corrected expected wastage_exceeds_units_sold (2, not 1) and asserted the full range_checks result; range_checks() unchanged.
- Full EDA run 20261021-160432_eda: 31 tables, 19 charts; totals reconciled (61,482,249 units, 4,786,490 wastage units).

## 2026-10-21 — Step 3C-C4: EDA visual review (docs/STEP_3C_C4_REVIEW.md)
- Reviewed all charts, tables and findings; identified corrections P1–P10. No code or outputs changed.

## 2026-10-21 — Milestone: Step 3C-C5 EDA corrections and final findings (run 20261021-162605_eda)
- P1 plots: chart 09 region legend built from explicit colour patches (colours now match bars).
- P4 analysis/plots: chart 03 indexed to each category's average week instead of week 1 (a holiday week).
- P2/P3/P6 report/plots: price section separates unadjusted, undiscounted-only and adjusted results; the unsupported
  "lower recorded prices may coincide with higher sales" hypothesis removed; chart 13 adds an undiscounted-rows line
  and states the adjusted coefficient; discount section reports timing checks and the product-mix explanation of
  waste by discount level.
- P5 analysis: new diagnostic tables diagnostic_price_by_discount_level, diagnostic_waste_generation_rule,
  diagnostic_discount_mix; manifest "diagnostics" block (price/waste generation, discount timing).
- P7 analysis/stats: month-adjusted temperature and rainfall correlations (multiway_demean helper); chart 16 caption.
- P8/P9: Pareto wording "top 10 of 48 (20.8%)", "1 store", truncated-axis note, category notes on charts 06/10/11/17,
  adjusted holiday coefficient and national-vs-regional holiday weeks in the report; p-values below 0.001 shown as "p<0.001".
- Chart notes now wrap to the figure width; binned-chart y-label shortened (it was clipped in earlier runs).
- config.py: reviewed EDA run 20261021-160432_eda added to protected paths; its 53 files added to CHECKSUMS.sha256.
- P10 tests: 16 new tests (legend colours, index base, price/waste rule detection, mix/timing, month adjustment,
  chart wording/labels, note and axis-label overflow, protected reviewed run). Full suite: 114 passed.
- New runs: 20261021-162605_eda (final, 38 tables, 19 charts). Intermediate runs 20261021-162317_eda and
  20261021-162452_eda superseded (chart-layout defects only; findings text identical) and kept unchanged.
- Added docs/EDA_FINDINGS.md. Random Forest model, forecasting and pricing code, raw data and prior runs unchanged.

## 2026-10-21 — Step 4A: forecasting design and leakage audit (design only)
- Added docs/STEP_4A_FORECAST_DESIGN.md. No code changed, no model trained.

## 2026-10-21 — Step 4B CP1–CP2: forecasting panel and leakage-safe features (no model training)
- config.py: final EDA run 20261021-162605_eda added to protected paths; its 60 files added to CHECKSUMS.sha256.
- Added src/dpe/forecast/ (panel, scenarios, features) and scripts/build_forecast_panel.py.
- Panel run 20261021-171758_forecast_panel: 37,440 rows (48 products x 15 stores x 52 weeks); units 61,482,249 and
  wastage 4,786,490 reconciled week by week and by category with the final EDA run.
- As-of features for H1 and H4 with explicit origin/target weeks, scenarios S0–S3, explicit feature list,
  one-hot identifiers, no zero-filled history.
- 43 new tests (truncation invariance, future scrambling, wastage never read, alignment, boundaries, no zero-fill,
  feature whitelist, protected runs). Full suite: 157 passed.
- Docs: STEP_4B_CP1_CP2_IMPLEMENTATION.md; STEP_4A section 14 amendments; DECISIONS 7–12.

## 2026-10-21 — Step 4B CP3: baseline forecasts and backtest folds (no model training)
- config.py: forecast panel run 20261021-171758_forecast_panel added to protected paths; its 3 files added to CHECKSUMS.sha256.
- Added src/dpe/forecast/ backtest, baselines, evaluate, reference_check, pipeline; panel.load_verified_panel();
  scripts/run_baseline_backtest.py.
- Six non-overlapping 4-week folds (target weeks 29–52); training targets <= earliest test origin, enforced by assertions.
- Baselines last_week and mean_4w for H1 and H4 on identical rows (17,280 per horizon). Pooled WAPE:
  H1 34.08% / 27.89%, H4 34.99% / 29.41% (last_week / mean_4w). Best baseline: mean_4w in every fold.
- H1 last_week equals the original naive benchmark row by row for targets 45–52 (5,760 rows, max diff 0);
  H4 and mean_4w have no original equivalent and are not compared.
- Run 20261021-175029_baseline_backtest. 20 new tests; full suite 177 passed. Docs: STEP_4B_CP3_BASELINES.md.

## 2026-10-21 — Step 4B CP4: Random Forest backtest, S0 (no tuning, no selection, no acceptance verdict)
- config.py: baseline run 20261021-175029_baseline_backtest added to protected paths; its 7 files added to CHECKSUMS.sha256.
- Added src/dpe/forecast/models.py (original RF settings, training-only one-hot encoder, clipping) and
  rf_backtest.py; scripts/run_rf_backtest.py. features.py: `fold` allowed as a metadata column.
- 12 fits (H1/H4 x F1–F6) on identical rows with both baselines. Pooled WAPE: H1 RF 25.92% vs mean_4w 27.89%
  (6/6 folds, 15/15 stores); H4 RF 28.84% vs 29.41% (5/6 folds, 9/15 stores; Meat +3.5 points, early-fold
  over-forecast linked to unseen target months). Weeks 51–52 under-forecast by 14–21% for every model.
- Run 20261021-180522_rf_backtest. 16 new tests; full suite 193 passed. Docs: STEP_4B_CP4_RF_RESULTS.md.

## 2026-10-21 — Step 4B CP5: acceptance and bootstrap review (no retraining, tuning, selection or deployment)
- config.py: CP4 run 20261021-180522_rf_backtest added to protected paths; its 19 files added to CHECKSUMS.sha256.
- Added src/dpe/forecast/acceptance.py and scripts/run_cp5_acceptance.py: independent verification (rows, folds,
  origins, actuals, baselines and metrics recomputed), two-way series x week-block bootstrap (2,000 replicates,
  seed 20261021, percentile CI), frozen STEP_4A gates, fixed decision rule, Meat/Christmas/reproducibility diagnostics.
- H1: all 9 gates PASS; +7.07% relative WAPE improvement, 95% CI +5.88% to +8.29% -> ACCEPT_RANDOM_FOREST (not a
  deployment approval). H4: G1, G5, G6, G7, G8 FAIL; +1.96%, 95% CI -0.32% to +4.26% -> RETAIN_FOUR_WEEK_AVERAGE.
- Reproducibility: max refit difference 9.1e-13 units (~3 machine epsilons, parallel summation); bit-exact not
  claimed; tolerance 1e-6 units proposed.
- Run 20261021-214104_cp5_acceptance. 17 new tests; full suite 210 passed. Docs: STEP_4B_CP5_ACCEPTANCE.md.

## 2026-10-21 — Step 4B CP5 handoff: decisions recorded and CP5 run protected (no rerun, no model changes)
- DECISIONS 13–17: H1 Random Forest and H4 four-week moving average are the preferred research candidates;
  CP5 thresholds and verdicts preserved; reproducibility tolerance 1e-6 forecast units approved; no production deployment.
- config.py: CP5 run 20261021-214104_cp5_acceptance added to protected paths; its 13 files added to CHECKSUMS.sha256.
- tests: CP5 run checksum and write-protection test added.

## 2026-10-21 — Step 4D-A: challenger design (design only)
- Added docs/STEP_4D_CHALLENGER_DESIGN.md.

## 2026-10-22 — Step 4D-B: one-round challenger study (exploratory; round closed)
- Added requirements-challenger.txt (dry-run verified against requirements.txt) and installed xgboost 3.2.0,
  catboost 1.2.10, graphviz 0.21, plotly 7.1.0, narwhals 2.27.1; no core pin changed.
- Added docs/STEP_4D_REPLACEMENT_POLICY.md (pre-registered), src/dpe/forecast/challengers.py, challenger_run.py,
  challenger_eval.py, scripts/run_challenger_backtest.py, scripts/run_challenger_evaluation.py.
- Runs 20261022-011204_challenger_backtest (87 min; CatBoost ~285 s per fit) and 20261022-011554_challenger_evaluation;
  both protected in config.py and CHECKSUMS.sha256.
- Pooled WAPE H1: RF 25.92 / CatBoost 25.77 / XGBoost 26.00 / SES 27.78. H4: mean_4w 29.41 / CatBoost 27.78 /
  XGBoost 28.27 / SES 29.76. No challenger meets the replacement policy; both incumbents retained. H4 CatBoost passed
  every rule except CP5 G5 (Christmas-fold bias -13.0%; incumbent -12.1%).
- 33 new tests; docs: STEP_4D_CHALLENGER_RESULTS.md; DECISIONS 18-22.

## 2026-10-22 — Step 5A: decision engine design (design only)
- Added docs/STEP_5A_DECISION_ENGINE_DESIGN.md.

## 2026-10-22 — Step 5B-1: forecast contract v1.0 (no retraining, no database)
- Added src/dpe/decision/ (forecast_contract.py) and scripts/build_forecast_contract.py.
- Contract run 20261022-081926_forecast_contract: 34,560 rows (17,280 H1 Random Forest, 17,280 H4 mean_4w), exact
  match to the protected predictions; decision-time contract and replay-only evaluation in separate files.
- As-of uncertainty bounds (p10/p50/p90 ratio quantiles, >= 4 error weeks, by model/horizon/category); unavailable for
  2,880 H1 and 5,040 H4 rows; replay p10-p90 coverage 78.2% (H1) and 73.4% (H4), Christmas weeks 66.8% / 56.2%.
- Run protected in config.py and CHECKSUMS.sha256. Superseded first build 20261022-081829_forecast_contract kept
  (long text per row; replaced by codes and a manifest code dictionary).
- 25 new tests; docs: STEP_5B1_FORECAST_CONTRACT.md; DECISIONS 23-26.

## 2026-10-22 — Step 5B-2: business assumptions design (v1, then v2 amended) — design only
- Added docs/STEP_5B2_BUSINESS_ASSUMPTIONS_DESIGN.md (v2 replaces v1: planning weights, coverage positions, day-level
  short-life schedule, lead-time timing, de-duplicated review queue, recalculated examples, acceptance criteria).

## 2026-10-22 — Step 5B-2: assumption set and chronological replay simulator (SYNTHETIC; no recommendation engines)
- Added config/assumptions/assumption_set_v1.json (AS-2026-10-22-v1, DRAFT, content sha256 744404c8...).
- Added src/dpe/decision/assumptions.py, replay.py, review_queue.py, replay_run.py; scripts/run_replay_simulation.py.
- Runs 20261022-225527_replay_worked_example and 20261022-225809_replay_simulation (720 series x weeks 33-52 x SC1-SC3,
  100,800 simulated store-product-days per scenario, 19.2 s); conservation, chronology, uniqueness and directional checks
  all pass; both runs protected in config.py and CHECKSUMS.sha256. Superseded worked example 20261022-225236 kept.
- Review cases (SC1): 5,040 mandatory review, 2,880 mandatory escalation, 4,684 risk escalation; 0 duplicates.
- tests: test_assumptions.py (AF1-AF6) and test_replay_simulator.py (S1-S17, future-sales mutation test);
  fake_contract_predictions moved to conftest.py. Docs: STEP_5B2_REPLAY_SIMULATOR_RESULTS.md; DECISIONS 27-31.

## 2026-10-23 — Step 5B-2 replay simulator correction checkpoint (v1.1)
- replay.py v1.1: separate pre-order coverage (stock + committed deliveries before the new order can arrive;
  PRE_ORDER_SHORTAGE) and post-order coverage (proposed drops on their scheduled arrival days; POST_ORDER_SHORTFALL);
  coverage_position/COVERAGE_* removed; every simulated order HYPOTHETICAL_UNAPPROVED, every delivery
  HYPOTHETICAL_UNAPPROVED_SIMULATED, Christmas escalation_required, approval_event_id always empty; simulator_version column.
- review_queue.py v1.1: LIFE_LEAD_TIME_TIGHT is a warning (warnings column; LIFE_LEAD_TIME_TIGHT_WARNING reason when a
  case exists); material triggers per assumption review_rules; cases PENDING_REVIEW.
- replay_run.py: new KPIs (pre-order shortage, post-order shortfall, approval counts); manifest records simulator,
  queue version and approval note; lead-time sensitivity now re-enables the v1.0 rule. Script refuses to write if an
  approval event appears; new runs labelled _v1_1.
- Assumption set AS-2026-10-22-v1 (still DRAFT): life_lead_time_tight_is_material_trigger false; review_rules gain
  material_triggers, warnings, coverage and approval. Content hash 744404c8…09e5 -> 383d703d…6fa.
- New runs 20261023-081500_replay_worked_example_v1_1 and 20261023-081809_replay_simulation_v1_1 (protected,
  46 checksums added); v1.0 runs unchanged and kept for comparison.
- Added tests/test_replay_corrections.py (16 tests); docs/STEP_5B2_REPLAY_CORRECTION_RESULTS.md.

## 2026-10-23 — Step 5B-3 inventory engine design (design only)
- Replay simulator v1.1 correction checkpoint accepted (run 20261023-081809_replay_simulation_v1_1).
- Added docs/STEP_5B3_INVENTORY_ENGINE_DESIGN.md: time-phased expiry-aware sizing, recommendation categories,
  planning vs realised fill rate, policy comparison (P0/P1/P2), tests T1-T12, stages 5B-3a-e, decisions D1-D12.
- No code, runs or assumption files changed.

## 2026-10-23 — Step 5B-3 implementation readiness (no implementation)
- Design conditionally approved. Added docs/STEP_5B3_IMPLEMENTATION_READINESS.md: D1-D12 register with dispositions
  under the approved directions, predeclared comparison gates and thresholds (proposed, not yet frozen), fill-rate
  stress scenario SF75, stages 5B-3a-e, recommended first stage, blockers B1-B4.
- No code, runs, assumption files or checksums changed.

## 2026-10-23 — Stage 5B-3a inventory calculator (pure functions only)
- Added src/dpe/decision/inventory.py: time-phased stock projection, expiry-aware FIFO depletion, per-drop sizing,
  case/MOQ validation, rounding excess (case and MOQ parts), pre-delivery gap at p10/p50/p90, post-order coverage and
  residual shortfall, fill-rate exposure (reported only; orders never adjusted). p50 depletion before arrival (D2);
  100% expected fulfilment (D3); supplier capacity not an input (D8).
- Added tests/test_inventory.py (41 tests): worked examples A 4,176, B 1,428, C gaps 404.4/1,006.7/1,752.1; expiry,
  timing, rounding, MOQ, unsupported/missing bounds, zero stock, no negative orders, leakage, determinism.
- Not wired into the simulator; no categories, approval records, review queue, runs or assumption changes.

## 2026-10-23 — Stage 5B-3a acceptance clarifications
- inventory.py: post-order coverage positions documented as conditional planning positions from the same
  p50-projected arrival state (v1.1 calculation unchanged as P1). Fill-rate exposure split into pre-arrival (A) and
  post-arrival (B = carry-over B1 + window deliveries B2) from one continuous walk against the plan's own baseline
  (100% routine, 75% stress); orders unchanged. Expected expiry labelled as an explanatory projection.
- tests/test_inventory.py: 10 new tests (51 total).

## 2026-10-23 — Stage 5B-3b inventory recommendations and review queue v1.2
- Added src/dpe/decision/recommendations.py: five primary categories with deterministic precedence, stable reason
  codes (BLOCK / MANDATORY / MATERIAL / WARNING / STANDING), supplier-arrangement status (never "confirmed"),
  provenance-grouped evidence, plain-English explanations, assert_safe guard. All records HYPOTHETICAL_UNAPPROVED,
  NOT_EXECUTED, no approval events.
- Added src/dpe/decision/inventory_review.py: review queue v1.2 with one weekly case per decision point (reasons
  combined, conflicting duplicates rejected) and one standing supplier-confirmation case per short-life or
  weekend-delivery series, kept apart from weekly cases. review_queue.py (v1.1, policy P1) unchanged.
- Added tests/test_recommendations.py (28 tests). Calculator, simulator, runs and assumptions unchanged.

## 2026-10-23 — Stage 5B-3c simulator v1.2 integration (no comparison run)
- Added src/dpe/decision/replay_v12.py: simulator v1.2 with selectable policies P0 (preregistered 4-week average,
  expiry-blind netting of stock on hand), P1 (calls replay._decide; v1.1 queue) and P2 (5B-3a calculator + 5B-3b
  recommendations; queue v1.2). v1.1 chronology, initial state, delivery handling and conservation reused; fresh
  state per run; standardised std_* risk indicators computed identically for every policy; P0 recorded-sales reads
  guarded to weeks <= origin.
- recommendations.py: Christmas gate across both horizons (christmas_any_horizon, v1.1 queue rule); provisional
  expiry trigger >15% of weekly p50 with safe handling of zero/unavailable p50 (expiry_share_is_high).
- inventory_review.py: contract_gate_cases for decision points outside the replay window (same gates as v1.1).
- Added tests/test_replay_v12.py (23 tests), including exact P1 regression against the protected v1.1 full replay
  (SC1-SC3: decisions, deliveries, weekly, daily, review cases) and worked example (incl. sales trace).
- replay.py, review_queue.py, inventory.py, protected runs and the DRAFT assumption set unchanged; no runs written.

## 2026-10-23 — Stage 5B-3d assumption set v2 and SF75 (no comparison run)
- Added config/assumptions/assumption_set_v2.json (AS-2026-10-23-v2, DRAFT, content hash ddc95ec1…989f): 26 v1
  parameters carried forward unchanged, 12 new ASSUMED parameters, policies block, review queue v1.2 rules, SF75
  scenario, evaluation record of the preliminary exposure. v1 file byte-identical.
- Added src/dpe/decision/assumptions_v2.py (validation rules W1-W10 on top of v1 rules V1-V8).
- recommendations.py / replay_v12.py read v2 parameters when present (expiry escalation level, stress fill rate) and
  reject expected fulfilment below 100% or order inflation; v1 behaviour unchanged.
- Added tests/test_assumptions_v2.py (32 tests); docs/STEP_5B3D_ASSUMPTION_SET_V2.md; DECISIONS 36-40.

## 2026-10-23 — Stage 5B-3e controlled policy comparison
- Correction: assumption set v1 has 24 parameters, so v2 = 24 carried forward + 12 added = 36 (the 5B-3d entry above
  and STEP_5B3D_ASSUMPTION_SET_V2.md said 26; documentation corrected, no values changed).
- Added config/evaluation/evaluation_policy_5B3e_v1.json (frozen thresholds from the readiness document section 2);
  registered with its source document and assumption_set_v2.json in docs/CHECKSUMS.sha256 before the run.
- Added src/dpe/decision/policy_comparison.py (pre-run integrity checks, runs, metrics, hard gates, thresholds,
  writing), scripts/run_policy_comparison.py and tests/test_policy_comparison.py (8 tests).
- First attempt failed while writing (numpy int64 not JSON serialisable); partial folder
  20261023-125852_policy_comparison marked INCOMPLETE_RUN_NOT_VALID and not registered; fix was serialisation only.
- New protected run 20261023-131711_policy_comparison (59 checksums; config.POLICY_COMPARISON_RUN_ID).
- Added docs/STEP_5B3E_POLICY_COMPARISON_RESULTS.md; DECISIONS 41-43.

## 2026-10-23 — Interactive dashboard MVP (read-only)
- Added app/dashboard (Streamlit): Home.py (overview), pages/1_Product_investigation.py, 2_Policy_comparison.py,
  3_Review_queue.py, 4_Future_features.py; dashboard_data.py (read-only loaders over the verified panel, forecast
  contract, RF backtest metrics, CP5 matrix and the protected 5B-3e comparison run); ui.py; .streamlit/config.toml
  (localhost:8501, usage stats off, deploy toolbar hidden).
- Added run_dashboard.cmd (Windows start command), requirements-dashboard.txt (streamlit 1.66.1 and dependencies,
  installed with the core pins as constraints; no existing package version changed), .claude/launch.json.
- Added tests/test_dashboard.py (15 smoke tests: every page renders, overview figures match saved outputs, review
  queue has no action buttons, saved cases never approved, dashboard code has no write/simulate calls, protected
  checksums unchanged after rendering).
- Known data gap: day-level stock is not saved in the protected comparison run (weekly totals and per-delivery
  arrival/expiry days are shown); a read-only daily export would need approval.
- No algorithm, assumption, protected run or database changed; waste-risk and pricing engines are placeholders only.

## 2026-10-23 — Dashboard usability and presentation upgrade (UI only)
- Added app/dashboard/labels.py: plain-English labels for every stored reason code, recommendation category, review
  type, coverage position, delivery arrangement, supplier status and action status; explanation text humanised for
  display (saved outputs unchanged; original codes kept in "Technical details" expanders).
- ui.py: page styling (headings, spacing, metric sizes, small-screen rules), readable chart styling (larger axis and
  legend fonts, compact number format, direct value labels), scenario and policy explanations, pills/kicker helpers.
- Home: explains the selected scenario and policy; plain-English forecast-accuracy note; technical table in expander.
- Product investigation: decision summary ABOVE the tables (store, product, decision week, proposed quantity,
  recommendation in plain English, shortage/expiry risk from the saved common indicators, review requirement,
  supplier-confirmation status, explanation); selected week marked on both charts; weekly table, deliveries and data
  sources moved into expanders.
- Policy comparison: plain-English summary (fewer simulated shortages, slightly more expiry and ordering) computed
  from the saved comparison table; tests shown with plain names; gate codes in an expander.
- Review queue: manager-friendly case card (what, review needed, proposed quantity, why, what to check), readable
  table, supplier schedules to confirm; still no action buttons.
- tests/test_dashboard.py: 17 tests (label coverage for every saved code, summary above the tables, humanised text).
- No algorithm, simulation result, assumption, protected run or external connection changed.

## 2026-10-23 — Stage 6A waste-risk intelligence design (design only)
- Added docs/STAGE_6A_WASTE_RISK_DESIGN.md: evidence review (recorded / forecast / simulated / assumed / missing),
  indicators W1-W9, provisional classification (High >= 25%, Moderate >= 10% of weekly p50 on the stock-on-hand expiry
  projection; Insufficient information), review of the 15% inventory trigger (keep unchanged and separate),
  manager-facing output with two worked examples from saved outputs, dashboard integration plan, data needed for
  future pricing, implementation stages 6B-a..c, unresolved decisions U1-U7.
- Key findings recorded: the existing-stock projection covers about 3% of simulated expiry; most simulated expiry is
  the planned service buffer on fresh lines (~32-34% of typical weekly sales, about twice recorded historical wastage).
- No code, algorithm, simulation, assumption or protected run changed.

## 2026-10-23 — Stage 6B waste-risk intelligence (advisory, read-only)
- Added config/assumptions/assumption_set_v3.json (AS-2026-10-23-v3, DRAFT, production_use false, content hash
  cb46de1b…63d9): 36 v2 parameters carried forward unchanged (incl. the 15% inventory warning) + 9 waste-risk
  parameters (High 25%, Moderate 10% of weekly p50; zero-p50 rule; existing-stock projection as the only driver;
  4-week as-of windows; max 3 reasons; advisory only; discounts disabled). v1 and v2 byte-identical.
- Added src/dpe/decision/assumptions_v3.py (rules X1-X8) and src/dpe/decision/waste_risk.py: deterministic advisory
  classification from saved outputs only (projection, planned buffer and low-sales buffer as context, as-of recorded
  wastage, recent simulated expiry, investigate-by day from saved delivery dates, links to existing review cases,
  evidence labels, category comparison of recorded wastage vs simulated expiry as separate measures).
- Dashboard: new page 4_Waste_risk.py (Future features moved to 5_); waste-risk summary in the Product investigation
  decision summary; waste-risk loaders in dashboard_data.py / ui.py; waste reason labels in labels.py.
- Tests: tests/test_waste_risk.py (32) and 3 new dashboard tests (20 in total).
- SC1 / P2: High 37, Moderate 97, Low 14,266, Insufficient 0; no review case, approval, discount or price created.
- No P0/P1/P2 logic, forecast, simulation, protected run or original assumption changed.

## 2026-10-23 — Stage 7A pricing and markdown intelligence design (design only) + presentation corrections
- Added docs/STAGE_7A_PRICING_MARKDOWN_DESIGN.md: four separated states (eligible for investigation / discount proposed
  / approved / executed), first-stage markdown eligibility rules (Not considered, Insufficient information, Blocked,
  Eligible for markdown review) with blockers (Christmas escalation, shortage before delivery, already on promotion,
  product exclusion, too late to act), counts from saved outputs (SC1 / P2: 91 eligible, 42 blocked, 1 insufficient),
  minimum data before any numerical price (D1-D9), manager-facing output, safety controls, dashboard plan, risks,
  decisions M1-M9. No discount percentages, elasticities, uplifts or savings proposed.
- Dashboard presentation corrections (no calculation or threshold changed): Waste risk page states which inventory
  policy and scenario the results represent (banner, caption, Policy/Scenario columns; product-page waste line too);
  Future features separates completed Waste-Risk Intelligence from unbuilt waste interventions, markdown/discount
  recommendations and dynamic pricing (no discount sizes implied).
- Registered assumption set v3 (AS-2026-10-23-v3, content cb46de1b…63d9, file 2b600cbe…7ad) in docs/CHECKSUMS.sha256
  as DRAFT after verifying content, validation and v1/v2 integrity: integrity freeze only, not an approval.
- Tests: 2 new dashboard tests, 1 new v3 registration test.

## 2026-10-23 — Stage 7B markdown review intelligence (eligibility only, read-only)
- Added config/assumptions/assumption_set_v4.json (AS-2026-10-23-v4, DRAFT, production_use false, content hash
  bde13a20…a1a5): 45 v3 parameters carried forward unchanged + 8 markdown parameters (eligible waste categories,
  one-sellable-day rule, blocker order, empty exclusion list, open inventory case = warning only, numerical discounts
  and approval functionality disabled, required data D1-D9) + documented-only approval/audit requirements.
  v1-v3 byte-identical.
- Added src/dpe/decision/assumptions_v4.py (rules Y1-Y8) and src/dpe/decision/markdown_eligibility.py: deterministic
  state-1 eligibility (Not considered, Insufficient information, Blocked, Eligible for markdown review) from saved
  evidence only; every applicable blocker retained in documented order; open inventory cases as warnings; no
  discount sizes, prices, uplifts, savings, proposals, approvals or execution.
- Dashboard: new page 5_Markdown_review.py (Future features moved to 6_); Markdown review column and link on Waste
  risk; markdown line and link in the Product investigation decision summary; Future features lists Markdown review
  eligibility as completed and numerical discounts, dynamic pricing and waste interventions as unbuilt; ui.link_to
  helper.
- SC1 / P2: 91 eligible, 42 blocked (27 Christmas, 19 already on promotion), 1 insufficient, 14,266 not considered;
  TOO_LATE_TO_ACT fires once in SC2 (the Stage 7A design said it never fired; corrected here).
- Tests: tests/test_markdown_eligibility.py (32) and 2 new dashboard tests.

## 2026-10-23 — Markdown Review page presentation check (UI only)
- pages/5_Markdown_review.py re-laid out: larger title and figures; eligibility summary (Eligible, Blocked,
  Insufficient information, Not considered) at the top for the selected policy and scenario; selected-line card as
  the main focus with three separated sections (1 why flagged, 2 what to investigate, 3 why no numerical discount
  yet); full table below; rules, data readiness and provenance in expandable reference sections; widget keys tied to
  the selected policy and scenario so every count and explanation updates together; wrapping metric labels.
- tests/test_dashboard.py: consistency test across SC1/P2, SC3/P2, SC1/P1 and SF75/P0 (counts equal the module's
  output; card shows the same policy and scenario; disclaimers and no buttons).
- No calculation, assumption set or protected output changed.

## 2026-10-23 — Stage 8A pricing intelligence design (design only)
- Added docs/STAGE_8A_PRICING_INTELLIGENCE_DESIGN.md: separate labelled demonstration mode (illustrative base price =
  reference-price proxy, illustrative cost = base x (1 - assumed gross margin)), margin-floor / maximum-markdown /
  overlap rules and option-level blockers, path from 7B eligibility to demonstration options (state 1b) and future
  proposal / approval / execution states, what can and cannot be claimed, dashboard page design, worked example
  (Cottage Cheese 300g, store 504, week 40: 5-20% allowed in demonstration, 25% blocked by the 8% floor), risks,
  missing data D1-D9, decisions P1-P10.
- Finding recorded: recorded non-discount shelf prices are too noisy to use as a base (median CV 39%, max/min ~4x).
- No code, assumption set, protected output or algorithm changed.

## 2026-10-23 — Stage 8B pricing intelligence demonstration (illustrative, read-only)
- Added config/assumptions/assumption_set_v5.json (AS-2026-10-23-v5, DRAFT, production_use false, content hash
  21180c90…706a): 53 v4 parameters carried forward unchanged + 10 pricing-demonstration parameters (demo mode,
  reference-price base rule, cost rule, displayed steps 0-25%, display decimals, cooldown NOT_DEFINED and not
  enforced, recommendations / proposals disabled, at-risk stock cost shown separately). v1-v4 byte-identical.
- Added src/dpe/decision/assumptions_v5.py (rules Z1-Z7) and src/dpe/decision/pricing_demo.py: full-precision
  illustrative arithmetic (price, cost, gross profit per unit, margin %, units to preserve gross profit — arithmetic,
  not a forecast), option blockers (overlapping promotion, permitted steps, maximum markdown, margin floor, no profit)
  with plain-English reasons, options only for Stage 7B eligible lines, illustrative at-risk stock cost, no
  recommendation, proposal, approval or execution.
- Dashboard: new page 6_Pricing_demo.py (Future features moved to 7_), linked from Markdown review; Future features
  lists the pricing demonstration as completed and numerical discount recommendations as unbuilt; ui.money display
  helper (rounding for display only).
- SC1 / P2: 91 lines with options, 366 passing options, 89 blocked (all below the margin floor at 25%).
- Tests: tests/test_pricing_demo.py (31) and 5 new dashboard tests.

## 2026-10-23 — Premium retail UI redesign, phase 1 (Home and Product investigation only; UI only)
- Added app/dashboard/theme.py: reusable design system (navy #10243A, teal #0D9488, emerald #16A34A, background
  #F1F5F9, amber caution, red high/blocked), page CSS (navy sidebar with teal accents and readable selectors, soft
  blue-grey background, typography), components (hero header with an original inline SVG retail illustration,
  compact research disclaimer, section titles, KPI cards, use-case cards, policy cards, risk indicators, executive
  decision card with Manager's takeaway) and an Altair chart theme. No photographs or external assets.
- Home redesigned: branded hero, "What this system helps a retail manager decide", KPI cards, plain-English
  forecasting summary, simulated policy cards with the research default marked, selected policy and scenario
  explained; disclaimers and simulated-vs-observed labels kept.
- Product investigation redesigned: hero, executive decision card (store, product, order week, hypothetical order,
  human review), distinct shortage / expiry / supplier-confirmation indicators, Manager's takeaway, full explanation
  and codes in expanders, restyled charts and KPI cards.
- Other pages unchanged (they do not call theme.apply()). tests/test_dashboard.py updated for the new layout plus
  decision-card and palette tests. No calculation, assumption set, saved result or protected file changed.

## 2026-10-23 — Consolidated premium dashboard design and clarity upgrade (frontend only)
- theme.py extended: coral level, page headers with local SVG art, banners, chips, readable HTML tables, process
  steps, evidence cards, roadmap cards, coloured deltas and single-measure policy bar charts. ui.page() now applies
  the design system to every page.
- Home: "Where to go next" navigation cards added. Product investigation: formal policy review shown separately
  from operational follow-up ("Formal policy review: Not triggered" when no review code exists); the saved review
  flag is unchanged.
- Policy comparison, Review queue, Waste risk, Markdown review ("Markdown Opportunity Review"), Pricing
  demonstration and Future features rewritten with the shared components. Markdown review adds executive summary
  cards, a review table, a read-only investigation panel, nine "Before a discount can be recommended" evidence
  cards and a four-stage process diagram (stages 2–4 NOT BUILT). Pricing demonstration adds an unverified-elasticity
  warning (the +1.6% figure is a non-causal association) and separate price and margin charts. Future features is a
  roadmap of three NOT BUILT cards.
- tests/test_dashboard.py: KPI checks read the HTML cards; new tests for the Markdown process stages and for the
  Review queue's formal vs standing items. No calculation, assumption set, saved result or protected file changed.

## 2026-10-23 — Phase 1: numerical discount recommendation engine (simulated research)
- Added src/dpe/decision/discount_recommendation.py. It is a deterministic engine that ranks permitted markdown
  steps against the full price under stated customer-response scenarios (R0 stress, R1 low, R2 central = non-causal
  1.6%/pt association, R3 high). It applies evidence gates, the Stage 8B rule checks (reused unchanged), a
  materiality threshold, a downside guard (low response, p90 demand) and ranking. It returns
  SIMULATED_RESEARCH_RECOMMENDATION or one of four NO_RECOMMENDATION reasons, each with a plain-English explanation.
  Results are computed in memory; nothing is written.
- Added assumption set v6 (DRAFT, AS-2026-10-23-v6): v5 is carried forward unchanged, plus 13 recommendation
  parameters. It also adds src/dpe/decision/assumptions_v6.py (rules Y1–Y7) and scripts/build_assumption_set_v6.py.
  v1–v5 are unchanged.
- Dashboard: the Pricing demonstration page is replaced by the Discount Decision Lab (pages/6_Discount_decision_lab.py).
  The Lab includes:
  - an evidence key that separates recorded, simulated, assumed and hypothetical information
  - scenario counts and customer-response scenario cards
  - line selectors and the result card with its plain-English explanation
  - evidence-quality and uncertainty warnings
  - an option comparison table and two single-axis charts
  - technical calculations
  Home, Markdown review and Future features are updated to match (numerical discount recommendations are now
  "Completed — Phase 1 · simulated research").
- Tests: tests/test_discount_recommendation.py (34 tests); the Lab tests in tests/test_dashboard.py replace the pricing
  demonstration page tests.
- Documentation: docs/PHASE_1_DISCOUNT_RECOMMENDATION_ENGINE.md (assumptions, scenarios, method, worked example,
  limitations). Dynamic pricing and waste interventions are not started.

## 2026-10-23 — Phase 1 closed out; Phase 2 design proposed (not implemented)
- Final Phase 1 verification:
  - the complete suite passed (647 of 647) on the final code, including the two Discount Decision Lab display fixes
  - all 356 previously registered checksums matched
- Registered DRAFT assumption set v6 (AS-2026-10-23-v6) in docs/CHECKSUMS.sha256:
  - file SHA-256 2d7bc7fe…d1e2; content hash 024fb42d…3c34
  - this is an integrity freeze only, not an approval
  - the manifest now has 357 entries, 0 mismatches
  - test_v6_is_a_valid_draft… now also asserts the registration
  - v1–v5 and every protected output are unchanged
- Phase 1 status: complete as simulated research, not validated for live use. Nothing is proposed, approved or
  executed.
- Added docs/PHASE_2_DYNAMIC_PRICING_DESIGN.md (design only, awaiting approval). No Phase 2 code was written.

## 2026-10-23 — Phase 2: dynamic pricing engine (simulated research, approved design with conditions)
- New simulator v1.3, src/dpe/decision/replay_pricing.py.
  - It runs the v1.2 chronology with a pricing step.
  - It reuses the protected daily selling step, the P2 ordering policy and the standard indicators unchanged;
    replay.py and replay_v12.py are not modified.
  - Orders are fixed to the pricing-off pass; prices are markdown-only.
  - The belief (v6 weights) is kept separate from the simulated true response (none / low / central / high).
- New src/dpe/decision/dynamic_pricing.py: the per-decision policy.
  - Waste-risk and eligibility rules are applied to the decision-time state.
  - Timing guards: 7-day cooldown, at most 2 events in 28 days, no overlapping windows.
  - The Phase 1 recommend_line makes the choice.
  - Review tags; every record is SIMULATED / HYPOTHETICAL_UNAPPROVED / NOT_EXECUTED.
  - Events are counted at selection.
- New src/dpe/decision/pricing_evaluation.py and scripts/run_dynamic_pricing_evaluation.py.
- DRAFT assumption set v7 (AS-2026-10-23-v7): v6 is carried forward, plus 13 parameters. It comes with
  assumptions_v7.py (rules X1–X7) and scripts/build_assumption_set_v7.py. v1–v6 are unchanged.
- Evaluation policy EP-PH2-2026-10-23-v1 (config/evaluation/evaluation_policy_phase2_v1.json) was frozen and
  registered in docs/CHECKSUMS.sha256, together with v7 and the design document, before any pricing outcome was
  simulated.
- Critical validation: pricing off reproduced the protected P2 replay exactly in SC1, SC2, SC3 and SF75. The checks
  were decisions, deliveries and weekly stock flows / unmet / expiry; fixed orders with no markdown; and the in-loop
  eligibility against the saved Markdown review.
- New run outputs/runs/20261023-233225_dynamic_pricing_evaluation (71 files, registered in docs/CHECKSUMS.sha256).
  - All hard gates passed in all 16 priced runs, and the outcome is MEETS_PREREGISTERED_RESEARCH_CRITERIA (research
    only).
  - Gross profit rises only under central or high response. Under no or low response every line that was marked down
    loses gross profit.
  - Illustrative unmet units rise when customers respond.
  - The effects are small (at most 0.6% of scenario gross profit), and SC2 had no markdowns.
- Dashboard:
  - new pages/7_Dynamic_pricing_lab.py
  - Future features moved to pages/8_Future_features.py (dynamic pricing now "Completed — Phase 2 · simulated
    research"; waste interventions NOT BUILT)
  - a Home navigation card
  - read-only loaders in dashboard_data.py / ui.py
- Tests: tests/test_dynamic_pricing.py (20); the Lab and run tests are in tests/test_dashboard.py.
- Documentation: docs/PHASE_2_IMPLEMENTATION.md (assumptions, counting rule, validation, results, limitations).
- Phase 3 (waste interventions) is not started. Nothing was pushed.

## 2026-10-23 — Phase 2 amendment A1: cooldown from the end of the previous markdown window (no new evaluation run)
- Implemented as a separate version:
  - DRAFT assumption set v8 (v7 carried forward unchanged, plus dynamic_pricing_cooldown_basis)
  - src/dpe/decision/assumptions_v8.py, dynamic_pricing_a1.py and replay_pricing_a1.py (simulator v1.4, which reuses
    the compiled v1.3 loop with only the policy rebound)
  - scripts/build_assumption_set_v8.py
  - tests/test_cooldown_amendment.py (10 tests)
- Nothing frozen was modified:
  - dynamic_pricing.py, replay_pricing.py, assumption sets v1–v7 and evaluation policy EP-PH2-2026-10-23-v1
  - protected run 20261023-233225_dynamic_pricing_evaluation, which stays the reported result for the v7 rule
- Impact, read from the protected run:
  - SC1, SC2 and SF75: unchanged (SC1 has one label-only change)
  - SC3: 26 consecutive-week repeat selections in 19 lines would be blocked, so SC3 results would change
- A separately versioned comparison (new frozen policy, v8 registration, one new run) awaits approval:
  docs/PHASE_2_AMENDMENT_A1_COOLDOWN.md.

## 2026-10-24 — Amendment A1 evaluated (cooldown from the end of the previous markdown)
- Evaluation policy EP-PH2-A1-2026-10-24-v1 (config/evaluation/evaluation_policy_phase2_a1_v1.json): the original
  criteria are unchanged, plus the A1 gate G8, a check that the original reproduces, and a preregistered preference
  rule (PA–PE). It was frozen and registered, together with v8, the A1 modules, src/dpe/decision/pricing_evaluation_a1.py
  and scripts/run_dynamic_pricing_evaluation_a1.py, before the full A1 run.
- New run outputs/runs/20261024-002535_dynamic_pricing_evaluation_a1 (registered).
  - Pricing off still reproduces the protected P2 replay.
  - The frozen original reproduces exactly in all 16 runs.
  - Every A1 gate, including G8, passes.
- Results:
  - SC1, SC2 and SF75 are identical to the original.
  - In SC3, A1 makes 190 markdowns instead of 205 and 134 mandatory reviews instead of 150.
  - SC3 gross profit is better with no response (−£43,569 vs −£45,989) and with low response, and worse with central
    (+£11,868 vs +£12,631) and high response. Expired units avoided are slightly fewer; unmet units are unchanged.
  - Preference rule outcome: A1_PREFERRED_RESEARCH_COOLDOWN (research only).
- Dynamic Pricing Lab: an Original Phase 2 / A1 rule selector, a source-run banner, and an original-vs-A1 comparison
  with the preference tests. It stays read-only.
- Tests: tests/test_a1_evaluation.py, plus rule-selector tests in tests/test_dashboard.py.
- Documentation: docs/PHASE_2_A1_EVALUATION_RESULTS.md. Phase 3 is not started; nothing was pushed.

## 2026-10-24 — A1 adopted as the preferred research cooldown rule (administrative closeout)
- Decision DEC-PH2-COOLDOWN-2026-10-24-v1 (config/decisions/phase2_cooldown_rule_decision.json, registered in
  docs/CHECKSUMS.sha256): A1 is the PREFERRED RESEARCH RULE, NOT PRODUCTION APPROVED. The original Phase 2 rule and
  evaluation are retained as a reproducible comparison.
- Dynamic Pricing Lab: A1 is now the default selection, with the original rule selectable and a status banner. It stays
  read-only, and every markdown remains hypothetical, unapproved and not executed.
- Docs: PHASE_2_IMPLEMENTATION.md section 7 and PHASE_2_A1_EVALUATION_RESULTS.md record the decision, rationale,
  comparison and limitations.
- Tests: Lab default and decision record (tests/test_dashboard.py).
- No pricing algorithm, threshold, assumption set or protected output changed. Phase 3 is not started; nothing was
  pushed.

## 2026-10-24 — Phase 3: waste intervention intelligence (advisory, read-only)
- New src/dpe/decision/waste_interventions.py: a deterministic advisory module over the protected P2 replay.
  - For each at-risk store × product × week it assesses: A next-order review, B transfer (investigate only),
    C markdown (reusing Stage 7B, Phase 1 and the A1 context), D donation or disposal (investigate only), and
    E no action / insufficient evidence.
  - Two separate decisions: stock in store and the next order.
  - The investigation order is by evidence quality, not financial benefit.
  - Values are illustrative (estimated retail and assumed cost), never savings.
  - Every assessment is PENDING_HUMAN_INVESTIGATION / NOT_EXECUTED.
- DRAFT assumption set v9 (AS-2026-10-24-v9): v8 carried forward, plus 7 parameters. It comes with assumptions_v9.py
  and scripts/build_assumption_set_v9.py. Registered with the module and the design in docs/CHECKSUMS.sha256 (an
  integrity freeze, not an approval).
- Dashboard: new pages/8_Waste_intervention_lab.py. It shows scenario KPIs, store / product / week selectors,
  exposure, value at risk, a manager summary, separate stock-in-store and next-order panels, five option cards, the
  investigation queue, weekly history, evidence levels and technical details. It has no buttons.
  - Future features moved to pages/9_Future_features.py (Phase 3 completed; executable interventions NOT BUILT).
  - Home has a navigation card.
- Tests: tests/test_waste_interventions.py (16), plus Lab tests in tests/test_dashboard.py.
- Documentation: docs/PHASE_3_IMPLEMENTATION.md.
- No forecasting, inventory, pricing or A1 calculation, assumption set v1–v8 or protected output changed. Nothing was
  pushed.

## 2026-10-24 — Phase 3 presentation polish (presentation only)
- theme.py:
  - wider desktop content (max 1480 px, larger side padding; 1 rem on phones)
  - roomier, striped tables
  - new styles for collapsible card details, key points and the two-step markdown gate
- Waste Intervention Lab:
  - intervention cards show status, evidence level, explanation and one key point; the full evidence, blockers,
    missing information and human checks are kept in a collapsible section
  - a "Why this investigation comes first" explanation, built from the existing ranks and evidence levels
  - the markdown card separates Step 1 (eligibility, Stage 7B) from Step 2 (evidence sufficient to investigate,
    Phase 1)
  - the investigation queue gains sort and row-count controls, a region column, a risk chip and aligned numbers
- Checked at 1600 px and 375 px wide: no page-level horizontal overflow; tables scroll inside their frame.
- No algorithm, assumption, threshold or protected output changed; waste_interventions.py is unchanged and still
  registered. No approval or execution controls were added.

## 2026-10-24 — GitHub publication preparation (Stages 1–4; nothing committed or published)
- `.gitignore`: publishes exactly the five original AMDARI training CSVs in `data/raw/` (byte-identical to the public
  copies in Busayosage/predicting_demand_for_perishable_goods). It still excludes:
  - `data/reference/`, `outputs/runs/` and the private `legacy/` copies
  - environments, caches and local tool settings
  - release archives
- Absolute path removed from `scripts/build_assumption_set_v6.py`.
- Tests made portable (13 files, tests only):
  - Registry checks leave out the six private legacy copies only when the whole `legacy/` folder is absent.
  - Original-machine folder checks skip their existence check but keep the write-blocking check.
  - A guard test pins this scope.
- Release tooling:
  - `scripts/build_release_archive.py` builds `dpe-v2-research-results-1.0.0.zip` (484 files, 65.6 MB, SHA-256
    b02c58d0…f2f7) without changing any file.
  - `scripts/restore_research_release.py` restores it with manifest, registry and double-verification, conflict
    protection and a Windows path-length guard. Its safety self-test passes 14 of 14 checks.
- Fresh-clone verification on Windows (Python 3.11.9, new environment, archive restored, no legacy): 711 passed, 3
  skipped; all 10 dashboard pages load. Original environment: 714 passed. All 516 protected checksums unchanged.
- New `README.md` (portfolio README) and `docs/RESEARCH_RELEASE.md` (archive contents, SHA-256 verification,
  restore, path-length guidance).

## 2026-10-25 — GitHub portfolio preparation (documentation only; nothing published)
- `README.md` rewritten for analyst recruiters: business questions, forecast evaluation and limitations, technologies,
  skills mapped to Data / BI / Performance / Operations Analyst roles, and what can run without the research archive.
- New `NOTICE.md`: authorship (original 2025 code written personally during the AMDARI mentorship; V2 developed with
  AI-assisted development and testing), AMDARI dataset not claimed, and no licence granted.
- New `docs/images/`: eight real screenshots of the running dashboard (light theme, 1440 px wide).
- `docs/GITHUB_PUBLICATION_READINESS.md` is kept local and excluded by `.gitignore`.
- Fresh clone without the research archive: 556 passed, 155 failed or errored (saved results absent), 3 skipped.
- No engine code, assumptions, decisions, protected outputs or CSVs changed; all 516 protected checksums unchanged.
