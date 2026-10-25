# Stage 6A: Waste-Risk Intelligence design (for review)

**Date:** 23 Oct 2026. **Status: DESIGN ONLY.** Nothing is implemented.

**Unchanged by this design:**
- P0, P1 and P2
- forecasts and simulations
- protected runs
- assumption sets: v1 and v2 stay DRAFT

**Scope:** no discounts or pricing are designed, no external systems are involved, and no new modelling experiment is
proposed.

All figures below come from the protected comparison run `20261023-131711_policy_comparison`, the protected forecast
contract and the verified raw panel. Inventory figures are SYNTHETIC replay values.

---

## 1. Plain-English summary

Waste-Risk Intelligence will answer five questions for a supermarket manager, for each store, product and decision week:

1. Which products are most at risk of going out of date before they sell?
2. How many units?
3. Why?
4. When should I look?
5. What would I need to know before any discount could safely be suggested?

The review of existing evidence produced three findings that shape the design.

**Finding A: today's 15% expiry trigger captures only a small part of simulated waste.** It measures only stock already
on the shelf. In SC1 it projects 92,643 units, but 2,781,470 units go out of date in the simulation, so it covers about
3%. The correlation with weekly simulated expiry is only 0.22.

**Finding B: most simulated waste is planned.** P2 deliberately orders above typical (p50) demand to meet its service
targets:
- The draft service targets put the planning weight at 0.875 for Bakery and 0.95 for Meat. Dairy and Beverages sit at the
  p90 cap.
- For fresh lines with a short shelf life, that buffer is about **32% of a typical week's sales for Bakery and 34% for
  Meat** (medians). If sales are typical, that buffer cannot sell before it expires.
- Order headroom above typical demand tracks weekly simulated expiry far better than the existing-stock projection, with
  correlations of 0.41 in SC1 and 0.63 in SC3. (This was measured on a close variant of the planned buffer W2.)

A rule that alerted on the combined figure would mark **84% of Bakery and 63% of Meat decisions "High"** (SC1): the
policy working as designed, not an exception.

**Finding C: the dataset records historical wastage (`Wastage_Units`)** for every store, product and week. This is
recorded historical data, never used by any model so far:

| Category | Recorded wastage as % of units sold |
|---|---|
| Bakery | 14.7% |
| Meat | 9.5% |
| Dairy | 4.9% |
| Beverages | 2.5% |

So the planned buffer for fresh lines is about twice what these lines historically wasted. That is a policy question for
you (decision U3), not a weekly alert.

**The design therefore separates three things:**
- **Exceptional waste risk**, which a manager should investigate this week. This is stock already on the shelf that is
  projected to go out of date. It is classified **High / Moderate / Low / Insufficient information**.
- **Planned buffer exposure**, shown as context with every row. It follows from the service target. Changing it is a
  policy decision, not a weekly task.
- **Evidence labels** on every figure: recorded, forecast, simulated, assumed or missing.

Every output stays hypothetical and subject to human review. Nothing proposes or applies a discount.

---

## 2. What evidence exists today

| Layer | What we have | Source | Can be used for |
|---|---|---|---|
| **Recorded historical data** | Weekly units sold, **wastage units**, price, discount %, marketing, weather, holiday flag, shelf life, supplier lead time | verified raw panel (2024, 52 weeks, 720 series; apparently synthetic, provenance unconfirmed) | Historical wastage rate as of each decision; price and discount context |
| **Forecasts** | p10 / p50 / p90 for 1 and 4 weeks ahead, uncertainty status, risk flags | protected forecast contract v1.0 | Typical and low-demand reference levels; forecast agreement |
| **Simulated outcomes** | Per decision: proposed units, deliveries, projected existing-stock expiry (W1), common risk indicators. Per delivery: arrival and last sellable day, ordered and delivered units. Per week: opening, received, sold, expired, closing, unmet units. | protected comparison run (P0/P1/P2 × SC1–SF75) | Planned buffer; batch expiry dates; persistence of simulated expiry; context only |
| **Illustrative assumptions** | Case size, MOQ, service targets, transit age, delivery arrangements, opening stock, fill rates, margins, 15% trigger | assumption sets v1 and v2 (DRAFT) | Inputs and thresholds; every one labelled ASSUMED or SYNTHETIC |
| **Missing real-world information** | Actual stock on hand by batch; real expiry dates; real deliveries and receipts; purchase costs; real shrink and markdown history; shelf space; whether stock was really discounted or donated | — | Must be obtained before any real-world use (section 8) |

**Known data gap:** the comparison run saves weekly stock and per-delivery dates, but not how many units of each batch
remain on each day. Exact batch-level "X units expire on Thursday" therefore needs a read-only daily export: replaying
the protected configuration into a NEW folder. This needs your approval (decision U5). Without it, the design uses the
saved projection plus batch expiry days.

---

## 3. Proposed indicators

Each indicator is calculated from existing evidence, with no new model.

| # | Indicator | Plain meaning | Calculation | Evidence label | Available now? |
|---|---|---|---|---|---|
| **W1** | Stock-on-hand expiry projection | Units already in store expected to go out of date before they sell | Saved P2 field `existing_stock_expected_expiry_units`. It is the 5B-3a calculator: p50 depletion to arrival, then planning-rate depletion. Also given as % of weekly p50 and as days of typical sales. | SIMULATED stock × FORECAST demand: a planning projection | Yes, saved for every P2 decision |
| **W2** | Planned buffer exposure | Units of the new order above typical demand within their own shelf life | For each proposed delivery: max(0, ordered − p50 ÷ 7 × sellable days), summed over the order | SIMULATED order × FORECAST p50 × ASSUMED service target | Yes, from saved deliveries and the contract |
| **W3** | Low-sales exposure | The extra units that could expire if sales come in at the low end (p10) | As W2, but with p10. Shown as "if sales are low…". | as W2 | Yes |
| **W4** | Shelf-life pressure | How little time the product has to sell | Remaining life R in days, delivery frequency, lead time ≥ R | RECORDED shelf life and lead time; ASSUMED transit age | Yes |
| **W5** | Information quality | Whether the forecast range exists and the arrangement is supported | uncertainty_status; arrangement | FORECAST / ASSUMED | Yes |
| **W6** | Recorded wastage rate | How much this line historically wasted | Wastage ÷ units sold over the last 4 recorded weeks up to the origin week (never later weeks) | RECORDED (synthetic dataset) | Yes |
| **W7** | Recent simulated expiry | Whether the replay has repeatedly wasted this line | Expired ÷ received over the previous 4 simulated weeks | SIMULATED: context, never evidence of real waste | Yes |
| **W8** | Demand signals | Reasons demand may fall short | Trend divergence (H4 vs H1), holiday or Christmas flag, last-week fill shortfall | FORECAST / RECORDED calendar / SIMULATED | Yes |
| **W9** | Investigate-by day | When to look | The day before the earliest last-sellable day among batches received before the decision and not yet expired | SIMULATED deliveries | Yes. Remaining units per batch need the daily export (U5). |

**Why W1 is the classification driver:**
- W1 is the only indicator that describes something unexpected the manager can still act on in store, such as checking
  dates or rotating stock. W2 is expected by design, and W3 is a what-if.
- W2, W3, W6 and W7 explain the classification and feed the future pricing stage, but do not raise the class on their
  own. Decision U2 asks whether any of them should.

---

## 4. Risk classification rules (provisional; every threshold documented)

| Class | Rule (first match wins) | Plain meaning |
|---|---|---|
| **Insufficient information** | Forecast bounds unavailable; arrangement UNSUPPORTED; p50 ≤ 0 or missing; or no simulated decision for that week | "We can't judge waste risk reliably — decide manually." |
| **High** | W1 ≥ **25%** of weekly p50 | "More than a quarter of a typical week's sales, already on the shelf, is expected to go out of date." |
| **Moderate** | 10% ≤ W1 < 25% of weekly p50 | "A noticeable amount of current stock may go out of date." |
| **Low** | W1 < 10% of weekly p50, including zero | "No unusual waste expected from current stock." The planned buffer is still shown. |

### Why these numbers

Both thresholds are **ASSUMED, illustrative and unsupported by business data**:
- **25%** is a quarter of a typical week, about 1¾ days of sales. That is enough stock that checking dates or adjusting
  the next order is plausibly worthwhile.
- **10%** is about ¾ of a day of sales. Below that, the expected waste is within ordinary noise, given forecast error of
  about 26% (WAPE).
- Both sit either side of the existing 15% inventory trigger, so the two layers stay comparable.

If adopted, they would go into a new **assumption set v3 (DRAFT)** with sensitivity ranges: High 20–35%, Moderate
5–15%. v1 and v2 are not edited.

### Expected workload (P2, counted from the saved outputs; decisions across 720 series × 20 weeks)

| Scenario | High (≥ 25%) | Moderate (10–25%) | Low, with some projected expiry | Insufficient information in the simulated window |
|---|---|---|---|---|
| SC1 normal trading | 37 | 97 | 417 | 0 |
| SC2 pressure | 0 | 10 | 299 | 0 |
| SC3 excess stock | 51 | 673 | 446 | 0 |
| SF75 supplier stress | 0 | 11 | 81 | 0 |

SC1 High cases are almost all Dairy: 93 of the 94 decisions above 15% are Dairy. In this replay, Dairy is where stock
expires mid-week.

### Limitations of the classification

1. W1 is a projection at assumed demand rates. It is not a forecast of actual waste.
2. W1 ignores interaction with the new order; this follows the accepted 5B-3a definition.
3. Classes describe simulated stock, not real shelves.
4. The thresholds are not calibrated against real waste. The data to do so do not exist (section 8).
5. **Insufficient information** never appears inside the simulated window, because every simulated week has forecast
   bounds. It will matter for earlier weeks and for real data.

---

## 5. Review of the provisional 15% expiry escalation

**What it is:** a 5B-3c decision, carried into assumption set v2 as `expiry_escalation_pct_of_p50` and into
recommendation reason `EXPIRY_BEFORE_COVERAGE`. It makes a P2 **inventory** recommendation a risk escalation when W1
exceeds 15% of weekly p50.

**Recommendation: keep it unchanged as an inventory warning, and keep it separate from the waste-risk class.**

1. **It is part of an accepted, protected result.** P2 passed the frozen 5B-3e gates with this rule in place. Changing it
   would change P2's review queue and reopen that evaluation.
2. **It answers a different question.** The 15% trigger asks whether this order decision needs a person. The waste-risk
   class asks how much current stock is at risk and when to look. Both use W1, so they never contradict:
   - every High case (≥ 25%) is already an inventory escalation
   - Moderate cases from 15% to 25% are escalations too
   - Moderate cases from 10% to 15% carry only the inventory warning `EXPIRY_BEFORE_COVERAGE_MINOR`
3. **Waste-risk is advisory at first.** It adds no new review cases. A waste-risk row links to the existing inventory case
   when there is one. Whether High waste risk should later create its own review case is decision U4.
4. **Replacing it later is possible but needs a new decision and a new evaluation.** One option is a single threshold
   shared by both layers. Neither the 15% trigger nor its replacement is calibrated (Finding A).

---

## 6. Manager-facing output

### One row per store × product × decision week

| Field | Content |
|---|---|
| Store and product | ID, name, region, category |
| Decision week | the week the order is for, and the decision day (Monday) |
| Projected expiry units | W1, in units, % of a typical week and days of typical sales. Planned buffer W2 shown alongside, with the low-sales figure W3. |
| Risk category | High / Moderate / Low / Insufficient information |
| Main reasons | Up to three plain-English reasons, ranked by contribution. Examples: stock on hand older than the next delivery; short shelf life; sales forecast range wide; trend falling; repeated recent waste. |
| Recommended investigation | A fixed, plain action (table below). Never a discount, transfer or order change. |
| Investigate by | W9 |
| Evidence and assumption labels | each figure tagged RECORDED, FORECAST, SIMULATED, ASSUMED or MISSING |
| Human-review status | "Pending review" if an inventory case exists, otherwise "Advisory — no review case"; always "Hypothetical, not actioned" |

| Class | Recommended investigation (text only) |
|---|---|
| High | "Check dates on the shelf before the investigate-by day. Consider with the store team whether the next order should be smaller. Possible candidate for a future markdown review (not available yet)." |
| Moderate | "Check stock rotation at the next delivery." |
| Low | "No action needed beyond routine checks." |
| Insufficient information | "The forecast range is missing or the delivery arrangement is unsupported — judge this line manually." |

### Example 1: High risk (from saved SC1, P2 outputs)

> **Cottage Cheese 300g · store 504 (London) · order for week 40** (decided Mon, week 40)
> **High waste risk:** about **2,374 units** of current stock may go out of date before they sell. That is 60% of a
> typical week (p50 3,955), about 4.2 days of typical sales. *[SIMULATED stock × FORECAST demand — planning projection]*
> **Why:**
> - a batch of 7,092 units delivered Wed, week 39 can be sold only until **Thu, week 40**
> - the next delivery arrives Wed, week 40
> - planned buffer for the new order: 0 (Dairy weekly delivery with 9 sellable days)
>
> **Investigate by:** Wed, week 40. Check dates on the shelf, and consider with the team whether the next order should be
> smaller.
> **Review:** an inventory review case exists (Review recommended: current stock may go out of date). It is pending
> review. Nothing has been ordered or discounted.
> *What happened in the replay (simulated, not a prediction):* 3,892 units expired in week 40.

### Example 2: Low risk, with a planned buffer shown

> **White Sandwich Loaf · store 505 · order for week 45**
> **Low waste risk from current stock** (0 units projected).
> **Planned buffer:** 7 daily drops of 204 units against a typical 142.5 per day, so about **431 units** would go out of
> date if sales are typical. This follows the Bakery service target (85%), not a weekly problem. *[SIMULATED order ×
> FORECAST p50 × ASSUMED service target]*
> **If sales come in low (p10):** more of the buffer would expire (W3).
> **Review:** none for waste. The standing supplier-confirmation case applies (daily and weekend drops assumed).
> *Replay:* 410 units expired in week 45.

The two examples show why the classes separate exceptional risk from planned buffer. Example 2's waste is real in the
simulation, but it is a service-target choice. It should be visible at category level (U3), not raised every week for
every loaf.

---

## 7. Dashboard integration plan

1. **New page `5_Waste_risk.py`.** It sits between Review queue and Future features, using the same sidebar (scenario,
   policy, store and product), safety banner and label conventions.
   - **Top tiles:** counts by class for the selected scenario, plus total W1 and total planned buffer, each tagged
     SIMULATED.
   - **"Investigate this week" table:** High and Moderate rows, sorted by W1 share. Columns are store, product, week,
     class, W1 units, days of sales, investigate-by and main reason.
   - **Row detail card:** the same layout as the product decision summary, with the reasons, evidence labels, review
     status and the "what happened in the replay" line kept visually separate.
   - **Category panel:** planned buffer versus recorded historical wastage per category. This is policy context for U3.
   - **Technical details expander:** the raw indicators and their codes.
2. **Product investigation page.** Add a waste-risk line to the decision summary, using the same class and reasons, and
   a link to the waste-risk page.
3. **Policy comparison page.** Unchanged.
4. **Data layer.** New read-only functions in `dashboard_data.py`, plus a pure, tested module
   `src/dpe/decision/waste_risk.py`. The module computes W1–W9 from saved outputs only: no simulation, no writes.
   Results are cached in the app. An optional protected export would only follow a later approval.
5. **Tests.** These cover:
   - class rules at each boundary (9.99 / 10 / 24.99 / 25%)
   - Insufficient information
   - no future data: W6 and W7 use only weeks up to the origin
   - every displayed code has a label
   - no buttons
   - outputs never claim approval
   - protected checksums unchanged

---

## 8. Data needed for future dynamic pricing and discounts

| Need | Why | Have today? |
|---|---|---|
| Stock on hand by batch, with real expiry dates | Know exactly what will expire and when | **No:** simulated only |
| Current shelf price and reference (non-promo) price | The discount base | Partly: recorded price and an estimated reference proxy (synthetic) |
| Purchase cost per unit | Margin floor: never sell below cost plus minimum margin | **No:** margins are ASSUMED |
| Markdown history with outcomes (sales lift, sell-through, residual waste) | Estimate the effect of a discount causally | **No.** Discount % exists, but the +1.6% per point figure is a non-causal association in apparently synthetic data. |
| Waste disposal, donation and recovery values | The value of acting versus not acting | **No** |
| Real deliveries, receipts and supplier schedules | Confirm the assumed fresh-drop arrangements | **No:** 360 series rely on unconfirmed arrangements |
| Competitor and price-policy constraints, legal limits on promotions | Safety limits | **No** |
| Store-level operational rules (markdown times, label printing, staffing) | Feasibility | **No** |
| Approval workflow ownership | Who can approve a markdown | **No:** to be defined |

Until these exist, a discount stage can at most show **which rows would qualify for a markdown review**, with the
reasons. It must not show a proposed discount size or a predicted sales effect.

---

## 9. Implementation scope (proposed, for a later approval)

| Stage | Content | Output |
|---|---|---|
| 6B-a | `src/dpe/decision/waste_risk.py`: pure functions for W1–W9 and the classification from saved outputs, plus unit tests. Rules come from a new assumption set v3 (DRAFT). | Code and tests; no run |
| 6B-b | Read-only waste-risk table for all P2 scenarios, written to a NEW protected run with checksums, plus a short results note with counts by class. | New protected run |
| 6B-c | Dashboard page 5, the product-page waste line, and the tests from section 7 | Dashboard update |
| Optional, needs U5 | Read-only daily batch export: replay of the protected P2 configuration into a new folder, verified identical in weekly totals | Exact batch-level expiry |

Out of scope throughout: changing P0/P1/P2, forecasts, the 15% trigger or protected runs; discounts and pricing; external
systems.

---

## 10. Unresolved decisions

| # | Decision | Recommendation |
|---|---|---|
| U1 | Adopt the High ≥ 25% and Moderate ≥ 10% rules on W1, as ASSUMED values in assumption set v3 (DRAFT) | Approve as provisional |
| U2 | Should W2 (planned buffer), W3 (low-sales exposure) or W7 (repeated simulated waste) ever raise the class? | No for now: show them as explanations, to avoid flagging most fresh decisions (84% of Bakery, 63% of Meat) |
| U3 | The fresh-line planned buffer (about 32–34% of typical sales) is roughly twice the recorded historical wastage (Bakery 14.7%, Meat 9.5%). Review the service targets? | Record as a policy question. Any change is a new inventory evaluation, not part of waste-risk. |
| U4 | Should High waste risk create its own review case, or stay advisory and link to existing inventory cases? | Advisory first. All High cases already have an inventory escalation. |
| U5 | Approve a read-only daily batch export (new folder) for exact units per batch | Optional. Useful before any markdown work. |
| U6 | Use recorded `Wastage_Units` (W6) as context, given the apparently synthetic dataset | Yes, as labelled RECORDED context only, never as a model input |
| U7 | The 15% inventory trigger | Keep unchanged and separate (section 5). Revisit only with a new evaluation. |
