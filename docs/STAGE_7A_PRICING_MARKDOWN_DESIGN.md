# Stage 7A: Pricing and markdown intelligence design (for review)

**Date:** 23 Oct 2026. **Status: DESIGN ONLY.** No pricing engine is implemented.

This design proposes **no** discount percentage, price elasticity, extra sales, margin uplift or waste saving. Figures
below are counts of saved, SYNTHETIC replay decisions, and recorded price and discount history from the apparently
synthetic dataset. They are not business results.

---

## 1. Plain-English summary

The first stage of markdown intelligence answers one narrow question:

> "Is this product, in this store, this week, worth a person looking at for a possible markdown — and if not, why not?"

It does **not** say how big a discount should be. It doesn't predict what a discount would do, and it never changes a
price.

It builds on the accepted Waste-Risk Intelligence:
1. Only lines with **High or Moderate waste risk** are considered.
2. They must have dated evidence that stock is approaching its last sellable day.
3. Safety **blockers** stop the review where a markdown would be inappropriate or premature. These are a Christmas
   escalation week, a shortage expected before the next delivery, a line already on a recorded promotion, or an excluded
   product.

Counts from the saved outputs for P2 and normal trading (SC1) show the scale:

| Status | Decisions |
|---|---|
| Eligible for markdown review | 91 |
| Blocked | 42 |
| Insufficient information | 1 |
| Not considered (low waste risk) | 14,266 |

A specific discount recommendation needs data we do not have: real purchase costs, real shelf prices, batch-level stock
and controlled markdown history. Until that exists, the system stops at **eligibility for review**.

---

## 2. Four separate states

The system must never blur these.

| State | Who or what sets it | Exists today? | Meaning |
|---|---|---|---|
| **1. Eligible for markdown investigation** | System, from saved evidence (this design) | Designed here | "A person should look at this line." No price, no percentage. |
| **2. Specific discount proposed** | System, only once the data in section 5 exist and a numerical stage is approved | **No** | A specific, bounded discount proposal inside the safety controls in section 7, still hypothetical |
| **3. Discount approved** | A named, authorised person, recorded as an approval event | **No** | A human decision with a reason, on one specific proposal |
| **4. Discount executed** | The store's real price system, confirmed by an external record | **No** | The shelf or till price actually changed. This system never sets this state itself. |

Rules:
- A record can only move forward one state at a time.
- State 3 requires an approval event. State 4 requires an execution confirmation from outside this system.
- Today every record is at most state 1, with status **HYPOTHETICAL_UNAPPROVED** and **NOT_EXECUTED**.

---

## 3. What evidence exists today

| Evidence | Source | Label | Use in eligibility |
|---|---|---|---|
| Waste-risk category, projected expiry of stock in store, investigate-by day, reasons | Stage 6B assessment from saved outputs | SIMULATED × FORECAST, ASSUMED thresholds | **Trigger:** High or Moderate only |
| Oldest in-date batch and its last sellable day | Saved deliveries (comparison run) | SIMULATED | Sellable-days check; investigate-by |
| Shelf life and remaining life | Recorded shelf life minus assumed transit age | RECORDED and ASSUMED | Context |
| Typical demand and range (p10 / p50 / p90) | Protected forecast contract | FORECAST | Context |
| Shortage expected before the next delivery | Saved common indicator `std_pre_delivery_shortage` | SIMULATED × FORECAST | **Blocker:** never mark down when stock may run out |
| Christmas or mandatory escalation week | Saved decision flags | RECORDED calendar | **Blocker:** escalation comes first |
| Recorded shelf price and discount % for the week | Verified raw panel | RECORDED (synthetic dataset) | **Blocker** if a discount is already recorded; otherwise context. Price range: Bakery £0.75–4.00, Meat £2.28–12.00. 23.2% of recorded weeks had a 5–25% discount. |
| Reference price | Forecast contract `reference_price_asof` | ESTIMATED PROXY | Context only. It is not a real list price. |
| Gross margin, minimum margin, max discount 25%, discount steps 5–25% | Assumption sets v1–v3 | **ASSUMED** | **Not used.** They are limits for a future numerical stage only. |
| Margin feasibility check (V8) | `assumptions.feasibility` | CALCULATED from ASSUMED | Not used. Illustrative caps are Bakery 25%, Beverages 25%, Dairy 20%, Meat 20%. |
| Discount uplift of +1.6% per point | Assumption sets | **ASSUMED** non-causal association in apparently synthetic data | **Never used** for any prediction |

---

## 4. First-stage markdown eligibility rules

Each saved decision (store × product × decision week, for a chosen policy and scenario) gets exactly one status.
Statuses are checked in this order; the first match wins.

| # | Status | Rule | Plain meaning |
|---|---|---|---|
| 1 | **NOT_CONSIDERED** | Waste-risk category is Low | No unusual waste expected from current stock |
| 2 | **INSUFFICIENT_INFORMATION** | Waste-risk category is Insufficient information, **or** there is no dated batch evidence | We cannot judge timing; decide manually |
| 3 | **BLOCKED** | High or Moderate, but any blocker applies (list below) | A markdown review is not appropriate now; reasons are shown |
| 4 | **ELIGIBLE_FOR_MARKDOWN_REVIEW** | High or Moderate, dated batch evidence, at least one sellable day left on the investigate-by day, no blocker | A person should consider whether a markdown is appropriate |

### Blockers (all reported, not just the first)

| Code | Rule | Reason |
|---|---|---|
| `CHRISTMAS_ESCALATION` | Mandatory escalation week | Christmas decisions go to escalation first and are never bulk-approved |
| `SHORTAGE_BEFORE_DELIVERY` | Common indicator: shortage expected before the next delivery | A markdown would make a shortage worse |
| `ALREADY_ON_PROMOTION` | Recorded discount above 0% in the origin week | Avoid stacking discounts without review |
| `PRODUCT_EXCLUDED` | Product or category on an exclusion list | Business exclusions; none are defined yet (decision M4) |
| `TOO_LATE_TO_ACT` | Fewer than 1 sellable day after the investigate-by day | No time to act. In the saved data, 2–5 days remain at each decision, so this never fires today. |
| `INVENTORY_REVIEW_PENDING` | Optional (M6): an open mandatory inventory case on the same line | Resolve the order decision first |

### Counts from the saved outputs (P2)

| Scenario | Eligible | Blocked | Insufficient information | Not considered |
|---|---|---|---|---|
| SC1 normal trading | 91 | 42 (27 Christmas, 19 already discounted; some overlap) | 1 | 14,266 |
| SC2 pressure | 1 | 1 | 8 | 14,390 |
| SC3 excess stock | 497 | 225 (124 Christmas, 120 already discounted) | 2 | 13,676 |
| SF75 supplier stress | 8 | 2 | 1 | 14,389 |

**Observations:**
- Eligibility in SC1 is almost entirely Dairy (123 of 134 High or Moderate rows). This follows the waste-risk results.
- No shortage blocker fires for High or Moderate waste rows in SC1 or SC3. That is consistent: stock that is about to
  expire is rarely also short.

**Limitations:**
- Every input is simulated or assumed.
- Remaining units per batch are not saved, so "at least one sellable day left" relies on batch dates, not quantities.
- A recorded discount in the dataset is not the same as an active promotion in a real store.

---

## 5. Data needed before any numerical price recommendation is defensible

| # | Minimum data | Why it is needed | Status today |
|---|---|---|---|
| D1 | Purchase cost per unit, per supplier and date | The margin floor: never price below cost plus minimum margin | **Missing**: margins are ASSUMED; cost is derived from an estimated reference price |
| D2 | Current shelf price and regular (non-promotion) price per store and week | The base for any percentage | Partly: recorded price exists, but reference price is a proxy |
| D3 | Stock on hand by batch, with real expiry dates | How many units, by when | **Missing**: simulated only; daily batch export not approved |
| D4 | Markdown history with outcomes (price, timing, units sold before and after, residual waste) | A causal estimate of how sales respond. Without it, any percentage is a guess. | **Missing**: recorded discounts exist, but the +1.6% per point figure is non-causal |
| D5 | Value of the alternatives: donation, staff sale, disposal cost, recovery | Whether a markdown beats doing nothing | **Missing** |
| D6 | Pricing rules: legal limits, brand and supplier agreements, price-matching, minimum advertised prices | Hard constraints | **Missing** |
| D7 | Store markdown operations: times, label printing, staff capacity | Feasibility | **Missing** |
| D8 | Approval ownership and limits by role | Who may approve what | **Missing**: to be defined (section 7) |
| D9 | Confirmed supplier delivery schedules | Fresh-line timing; 360 series rely on unconfirmed drops | **Missing** |

**Minimum set for a defensible first numerical stage: D1, D2, D3, D4, D6 and D8.** Without D4, any recommended
percentage would be a rule of thumb and must be labelled as such. It would not be an optimised price.

---

## 6. Manager-facing output (first stage)

One row per store × product × decision week:

| Field | Content |
|---|---|
| Store and product | ID, name, region, category |
| Decision week | order week, decided-on day |
| Waste-risk category | from Stage 6B, with its icon |
| Stock and expiry evidence | Projected expiry of stock in store (units, % of a typical week). Oldest in-date batch and its last sellable day. Investigate-by day. Sellable days left. Each carries its evidence label. |
| Markdown review eligibility | Eligible / Blocked / Insufficient information / Not considered |
| Reasons | why it qualifies, in plain English |
| Blockers and missing information | every blocker, plus the standing list of missing data (D1–D9) that prevents a specific discount |
| Suggested investigation | Text only. For example: "Check dates and quantity on the shelf before Wed, week 40; consider with the store team whether a markdown, a smaller next order or another option is appropriate." |
| Recorded price context | Recorded shelf price and any recorded discount this week. Labelled RECORDED (synthetic dataset), not a recommendation. |
| Human-approval status | "No proposal — eligibility only" (today). Later: Proposed, Approved by / Rejected by, or Executed (externally confirmed). |

### Example (from saved SC1, P2 outputs; the eligibility status is computed by the rules in section 4)

> **Cottage Cheese 300g · store 504 (London) · order week 40**
> 🔴 **High waste risk:** about 2,374 units in store may go out of date (60% of a typical week).
> *[SIMULATED × FORECAST]*
> **Oldest batch** sellable until **Thu, week 40**. **Investigate by Wed, week 40.** *[SIMULATED delivery dates]*
> **Markdown review:** ✅ **Eligible for review.** There is no Christmas week, no expected shortage and no recorded
> promotion that week.
> **Recorded price context:** shelf price 2.58 in week 39, with no recorded discount. *[RECORDED, synthetic dataset;
> currency assumed GBP; not a recommendation]*
> **A specific discount cannot be proposed yet:** cost, regular price, batch quantities and markdown history are missing
> (D1–D4).
> **Approval status:** no proposal; eligibility only. Nothing has been approved or changed.

---

## 7. Safety controls for any future pricing stage

These must be in place before any numerical proposal exists.

1. **Margin floor.**
   - A proposed price must never fall below real unit cost × (1 + minimum margin).
   - With assumed margins this can only ever be shown as illustrative.
   - The existing V8 check already caps illustrative discounts per category.
2. **Maximum discount and fixed steps.**
   - Cap at a configured maximum. The draft value is 25%, and it is ASSUMED.
   - Use fixed steps only (draft 5/10/15/20/25%). Never a free number.
3. **Exclusions.**
   - A configurable list of products, categories or brands never marked down by the system.
   - Lines already on promotion are excluded, unless a person overrides with a reason.
   - Christmas and other mandatory-escalation weeks are excluded.
4. **No stacking and a cooldown.**
   - One active markdown per line.
   - A minimum gap between markdowns on the same batch.
5. **Approval ownership.**
   - Every proposal has a named approver role, such as a store manager or a fresh-food lead.
   - Approval limits by role, for example larger steps needing a second approver.
   - Approval is never bulk or automatic for Christmas, and never by the system.
6. **Audit records.**
   - An append-only record of every state change.
   - It holds: proposal id, inputs and their evidence labels, assumption-set id and hash, proposer (system version),
     approver, decision, reason, timestamps and execution confirmation reference.
   - Nothing is overwritten.
7. **Expiry of proposals.** An unapproved proposal lapses at its investigate-by day. It is never executed late.
8. **Execution separation.** This system never changes a price. Execution happens in the store's price system and is
   recorded back as a confirmation.
9. **Kill switch and read-only default.**
   - The pricing page is read-only unless a separate, approved workflow is enabled.
   - A single configuration flag disables all proposals.
10. **Monitoring.** Real outcomes are compared with any expectation after the event, only once real data exist. There are
    no "savings" claims before that.

---

## 8. Dashboard integration

1. **New page "Markdown review"**, placed after Waste risk. It uses the same sidebar (scenario, policy, store, product),
   the safety banner and the evidence labels.
   - **Tiles:** counts of Eligible / Blocked / Insufficient information / Not considered. A clear line states which
     policy and scenario they represent.
   - **"Lines to consider" table:** Eligible rows first, then Blocked with their blockers. Columns are store, product,
     week, waste risk, projected expiry, investigate-by, eligibility, and main reason or blocker.
   - **Row card:** the output in section 6, including the explicit "why a specific discount can't be proposed yet" panel
     listing D1–D9.
   - **Data-readiness panel:** each required dataset as Available / Partial / Missing.
   - **No buttons:** no approve, reject, propose or apply buttons. A note explains how approval will work later
     (section 7).
2. **Waste risk page:** a link from each High or Moderate row to its markdown-review status.
3. **Product investigation page:** one line in the decision summary, "Markdown review: Eligible / Blocked (reason)".
4. **Future features page:** remains the place for unbuilt items: numerical discounts, dynamic pricing, and waste
   interventions such as order reductions or donations.
5. **Implementation (Stage 7B, if approved):**
   - a pure module `src/dpe/decision/markdown_eligibility.py`
   - reads Stage 6B outputs and saved data only, with no simulation and no writes
   - thresholds and exclusions in a new assumption set v4 (DRAFT)
   - tests for every status and blocker, the evidence labels, no buttons, no numbers, no future data and checksums

---

## 9. Risks and limitations

1. **Synthetic foundation.** All eligibility rests on simulated stock, forecast demand and assumed thresholds. It is a
   prioritisation aid, not evidence that a markdown would help.
2. **Timing without quantities.** Without batch-level remaining units (D3), eligibility knows *when* but not *how much*
   of a batch is at risk.
3. **Recorded discounts.** These come from an apparently synthetic dataset, and the association with sales is
   non-causal. They are used only as a blocker or context.
4. **Policy dependence.** Results differ by inventory policy and scenario. The page must always say which it shows.
5. **Workload.** It is small in normal trading (91 eligible decisions over 20 weeks and 720 series). It is much larger
   with excess stock (497). Thresholds may need tuning when real data exist.
6. **Risk of anchoring.** A future numerical stage must not let a default percentage become a habit. Steps should need an
   explicit choice with a reason.

---

## 10. Decisions requiring approval

| # | Decision | Recommendation |
|---|---|---|
| M1 | Adopt the four eligibility statuses and their order (section 4) | Approve |
| M2 | Adopt the blockers: Christmas, shortage before delivery, already on promotion, product exclusion, too late to act | Approve |
| M3 | "At least one sellable day left on the investigate-by day" as the timing rule (ASSUMED) | Approve as provisional |
| M4 | Exclusion list content (none defined today) | Define later with the business; start empty and visible |
| M5 | Thresholds and exclusions held in a new assumption set v4 (DRAFT); v1–v3 unchanged | Approve |
| M6 | Whether an open mandatory inventory case should also block markdown review | Optional; recommend "show, not block" |
| M7 | No numerical discount until D1, D2, D3, D4, D6 and D8 exist | Approve |
| M8 | Approval roles, limits and audit-record schema (section 7) | Define before any numerical stage |
| M9 | Proceed to Stage 7B: implement eligibility only, read-only | Your decision |
