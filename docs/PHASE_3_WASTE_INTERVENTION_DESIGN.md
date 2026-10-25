# Phase 3 — Waste Intervention Intelligence: design proposal (NOT IMPLEMENTED)

**Status:** design and inspection only, awaiting review. No Phase 3 code, data or dashboard exists yet.
- Every output described here would be advisory: SIMULATED or ASSUMED, `PENDING_HUMAN_INVESTIGATION`, NOT_EXECUTED.
- No transfer, donation, order change or price change is assumed to have happened.
- The A1 cooldown rule remains the preferred Phase 2 research rule.

## 1. What already exists (reused, not rebuilt)

| Capability | Where | What Phase 3 takes from it |
|---|---|---|
| Forecast p10 / p50 / p90 | protected forecast contract | Typical demand and uncertainty per line and week |
| P2 inventory replay (protected) | run `20261023-131711_policy_comparison` | Simulated stock, orders, deliveries, expiry and the standard shortage and expiry indicators |
| Waste risk (Stage 6B) | `waste_risk.py` / Waste risk page | Risk class, at-risk units, oldest batch date, investigate-by day, planned order buffer, recorded wastage (context) |
| Markdown eligibility (Stage 7B) | `markdown_eligibility.py` / Markdown review | Eligible / blocked / insufficient, with its blockers |
| Discount Decision Lab (Phase 1) | `discount_recommendation.py` | Single-line ranking or NO RECOMMENDATION, with the reason |
| Dynamic Pricing Lab, A1 preferred | run `20261024-002535_dynamic_pricing_evaluation_a1` | Whether a simulated markdown was selected for the line and week |
| Review queue | P2 review cases and standing supplier items | Open human-review cases, shown as context |
| Store attributes | `data/raw/store_info.csv` | Region, store size, cold-storage capacity (units unknown) |

What the inspection found does **not** exist anywhere in the project:
- distances or transport times between stores
- transfer or disposal costs
- receiving capacity, beyond an unlabelled cold-storage number
- batch-level stock on hand (units left per batch)
- donation partners, eligibility or food-safety rules
- real purchase costs
- any record of an intervention actually taken

## 2. What the evidence can support today

The counts below come from the protected P2 outputs, using decisions where waste risk is High or Moderate.

| | SC1 normal | SC2 pressure | SC3 excess stock |
|---|---|---|---|
| At-risk decisions | 134 (37 High, 97 Moderate) | 10 (Moderate) | 724 (51 High, 673 Moderate) |
| Units projected to expire | 70,549 | 1,062 | 154,846 |
| Markdown-eligible / blocked / insufficient | 91 / 42 / 1 | 1 / 1 / 8 | 497 / 225 / 2 |
| New order in the same week with a planned buffer above typical demand | 11 | 9 | 556 |
| Same product and region: another store short before its next delivery | 25 | 1 | 9 |

| Intervention | Supported now? | Basis | Classification |
|---|---|---|---|
| **A. Replenishment review** | Yes, as a flag | The same-week order plus planned buffer above p50 (Stage 6B) | `CANDIDATE_FOR_REVIEW`. It flags the **next** order for a person to review. It never changes the P2 order and claims no saving. A versioned "what-if smaller order" simulation is possible later, but is not proposed now |
| **B. Stock transfer** | Partly | A same-product, same-region store that is projected short (`std_pre_delivery_shortage`) in the same week | `OPPORTUNITY_FOR_INVESTIGATION` at most. Distance, time, cost, receiving capacity and batch dates are missing, so it is never a recommendation |
| **C. Markdown consideration** | Yes, by reuse | Stage 7B eligibility, the Phase 1 result and the A1 Dynamic Pricing selection | Links to the existing labs and shows their result. No new discount logic; customer response stays labelled as assumed |
| **D. Donation / alternative disposal** | No evidence | Only the size of the at-risk stock | `INVESTIGATE_ONLY`, with every missing item listed. Eligibility, safety, recipient, transport and value are never assumed |
| **E. No intervention / insufficient evidence** | Yes | Waste risk Low, or Insufficient information | `NO_INTERVENTION_NEEDED` or `INSUFFICIENT_EVIDENCE` |

## 3. Smallest practical Phase 3

Build one **read-only advisory layer** over saved outputs. It needs no new simulation, no change to any engine, and no
new run unless you approve one.

1. **Rules module:** `src/dpe/decision/waste_interventions.py`, pure and deterministic. For each P2 decision with
   waste risk High or Moderate, it assesses the five options A–E. Each option gets:
   - a status: `CANDIDATE_FOR_REVIEW`, `OPPORTUNITY_FOR_INVESTIGATION`, `INVESTIGATE_ONLY`, `BLOCKED`,
     `INSUFFICIENT_EVIDENCE` or `NOT_APPLICABLE`
   - the evidence for it and against it, with an evidence label (RECORDED / FORECAST / SIMULATED / ASSUMED)
   - the missing information
   - the human approval needed
2. **Two separate questions**, because they act on different stock:
   - *Stock already in the store* (it expires whatever the next order does): markdown, transfer, donation / disposal.
   - *The next order*: replenishment review.
3. **"Investigate first" rule.** This is deterministic, transparent and claims no benefit. Within each question, the
   option with the strongest evidence comes first:
   1. **Level 2:** simulated with a modelled consequence. Example: a markdown eligible, with a Phase 1 or A1 research
      result.
   2. **Level 1:** a simulated pattern only. Examples: a transfer pair, or the order buffer.
   3. **Level 0:** no evidence. Example: donation.

   Ties go to the option that depends least on outside parties: internal before transfer, and transfer before
   donation. If only level 0 remains, the answer is **INSUFFICIENT EVIDENCE — investigate**.
4. **Value at risk**, shown as two labelled figures and never as a saving:
   - **cost value** = at-risk units × assumed unit cost (v5 margin)
   - **retail value** = at-risk units × estimated reference price

   Recorded historical wastage is shown separately as context.
5. **Assumption set v9 (DRAFT).** It carries v8 forward and adds only Phase 3 rule parameters:
   - the transfer pairing rule: same product, same region, same week, receiver projected short
   - the minimum at-risk units before a donation investigation is suggested
   - the evidence-level order
   - the value labels

   Every new value is ASSUMED.
6. **Data loader and page.** Results are computed in memory from the protected runs. Optionally, one versioned saved
   run can be written as a frozen record, only with your approval.

## 4. The Waste Intervention Lab (new page; Future features moves to `9_`)

It uses the existing navy and teal design, with these sections:

1. **Header and labels.** "Advisory — investigation support only", the research disclaimer, and the evidence key:
   recorded / forecast / simulated / assumed / not available.
2. **Selectors.** Scenario (sidebar), store, product and decision week. The P2 inventory replay is fixed, and the
   pricing context comes from the A1 preferred research run.
3. **Exposure panel.**
   - Risk class, units projected to expire, and the share of a typical week.
   - Investigate-by day and the oldest batch's last day.
   - Cost value and retail value at risk, both labelled assumed / estimated.
   - Recorded wastage, labelled as history.
4. **Manager summary**, in plain English. For example: "About 2,374 units already in store may go out of date by
   Thursday. Investigate first: markdown consideration (eligible; simulated research ranks 20%). For the next order:
   review the order size (planned buffer of 1,100 units above typical demand). Transfer and donation cannot be judged
   without transport and recipient information."
5. **Option cards A–E.** Each shows its status chip, evidence for (✔) and against (✖) with labels, missing
   information, the human approval needed, and a link to the existing page where one exists.
6. **Investigation queue.** All at-risk lines for the scenario, filterable, showing the suggested first investigation
   and statuses. It is read-only (`PENDING_HUMAN_INVESTIGATION`), with nothing to approve, assign or execute.
7. **Line history.** Every week for the selected line, showing risk class, options and what the simulation recorded,
   so a reader can see recurring problems.
8. **Expanders.** Rules, parameters, provenance and source run IDs.

**Not on the page:** any button, approval, order or price control, and any claim of waste reduction or profit.

## 5. Assumptions and data limitations

- **The stock is simulated.** Stock, batches and expiry come from the replay; real units left per batch are unknown.
  The waste-risk projection assumes typical (p50) demand.
- **Transfer opportunities are unverifiable.** "Same region" stands in for distance. Cold-storage capacity has no unit,
  so it is displayed as context only. Transport time, cost and receiving rules are missing, and the receiving store's
  shortage is itself a simulated forecast indicator.
- **Donation and disposal have no data at all.** There are no partners, eligibility or safety rules, transport, or
  values.
- **The replenishment flag cannot show its effect.** It points to the next order but cannot show what a smaller order
  would change. That needs a separately versioned what-if simulation, and is not proposed now.
- **The markdown context inherits its assumptions.** It carries the Phase 1 / A1 limitations: assumed customer
  response, proxy prices, assumed costs.
- **The values are illustrative.** They use the assumed margin and the estimated reference price, and are never
  savings.
- **The data is synthetic.** Recorded sales and wastage are apparently synthetic.

## 6. Acceptance tests

1. **Read-only:** no writes, no buttons, no approval or execution fields set, and every option `NOT_EXECUTED`.
2. **No invented answers:** with Insufficient waste risk, missing batch dates or missing bounds → `INSUFFICIENT_EVIDENCE`.
   A line with only donation available → `INSUFFICIENT EVIDENCE — investigate`, never a recommendation.
3. **Correct classification:** Low risk → `NO_INTERVENTION_NEEDED`. Transfer is never above
   `OPPORTUNITY_FOR_INVESTIGATION`, and donation is never above `INVESTIGATE_ONLY`.
4. **Reuse is faithful:** the markdown option exactly matches the saved Stage 7B eligibility and the A1 run's
   selection for the same line and week. Nothing is re-ranked.
5. **Transfer pairing:** same product, same region, same week, a different store, and the receiver projected short.
   The test also checks the counts in section 2 (25 / 1 / 9 pairs).
6. **No look-ahead:** every input is known at the decision (the same as the Stage 6B / 7B rules).
7. **Value labels:** cost and retail values are recalculated from units × assumed cost or reference price and labelled
   ASSUMED / ESTIMATED. No "saving", "reduction" or "profit" wording appears.
8. **Determinism and integrity:** repeat runs are identical, and every protected checksum is unchanged.
9. **Dashboard:** every scenario renders, the manager summary and the option cards appear, and the evidence key is
   present.

## 7. Implementation sequence (after approval)

1. Assumption set v9, its builder and its validator; register v9.
2. `waste_interventions.py`, with unit tests 1–8.
3. Read-only loader; cross-check against the section 2 counts.
4. Waste Intervention Lab page and dashboard tests; Home and Future features updates.
5. Full test suite, checksums, `docs/PHASE_3_IMPLEMENTATION.md`, changelog; then stop for review.

Optional, only if approved: one saved, registered run of the intervention assessments.

## Plain-English summary

**What can be built immediately**, from data the project already has:
- the at-risk stock and its labelled value
- the manager summary
- a markdown option that reuses the existing labs
- a "review the next order" flag
- a "no action needed" or "insufficient evidence" answer when the data says so

**What must remain investigative:**
- **Stock transfers.** The system can spot a nearby store of the same product that looks short, but cannot judge
  travel, cost or receiving.
- **Donation or other disposal.** There is no information at all.

**What requires real business data** before any of these could become recommendations:
- distances and transport costs
- receiving capacity
- batch-level stock
- donation partners and food-safety rules
- real costs and how customers actually respond to markdowns
