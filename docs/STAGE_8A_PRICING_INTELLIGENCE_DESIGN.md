# Stage 8A: Pricing intelligence design (for review)

**Date:** 23 Oct 2026. **Status: DESIGN ONLY.** No numerical pricing is implemented.

Nothing is changed: no protected file, assumption set (v1–v4 stay DRAFT), algorithm or output. Every price, cost and
rule below is labelled **ILLUSTRATIVE**. No elasticity, sales uplift, waste saving or profit improvement is estimated or
implied.

---

## 1. Plain-English summary

The goal is a pricing component that could one day suggest **safe, explainable** price interventions for perishable
lines.

What we can credibly build now is a **demonstration mode**. For a line that Stage 7B already found *eligible for a
markdown review*, the page would show:
- an illustrative original price and an illustrative cost
- the standard markdown steps (5 / 10 / 15 / 20 / 25%)
- for each step, the resulting price and margin per unit
- whether a business rule blocks that step, such as a margin floor, the maximum markdown limit or an overlapping
  promotion, and why

That is **arithmetic and rule-checking only**:
- It can show that a 25% markdown would breach the margin floor.
- It can show how much margin each unit gives up.
- It cannot say whether any markdown would sell more units, reduce waste or make more money. That needs real evidence of
  how customers respond to price, and we have none.

So the demonstration never picks a "best" option and never proposes a price for approval.

### Two findings from reviewing the data

1. **Recorded shelf prices are not a usable "original price".** In weeks with no discount, a typical product's recorded
   price varies by about 39% (median coefficient of variation). Its highest price is about four times its lowest
   (median ratio 3.99). The worked-example line was priced anywhere from £1.16 to £3.53 in such weeks. Back-calculated
   list prices differ from the forecast contract's reference price by a median of 33%. The prices behave like noise in an
   apparently synthetic dataset. The design therefore uses the contract's **reference-price proxy** as the illustrative
   base, clearly labelled, and never the week's recorded price.
2. **The existing margin feasibility check already gives the limits.** With the DRAFT assumed margins it caps markdowns
   at 25% for Bakery and Beverages and 20% for Dairy and Meat, because 25% would breach the 8% minimum margin. The
   demonstration makes that visible per line.

---

## 2. What already exists and what pricing would use

| Component | Output used by pricing | Evidence label |
|---|---|---|
| Forecasting (contract v1.0) | p10 / p50 / p90 demand; `reference_price_asof` (median of price ÷ (1 − discount) over weeks up to the decision) | FORECAST; reference price is an ESTIMATED PROXY |
| Inventory (P2, research default) | Stock and deliveries in the replay | SIMULATED |
| Waste-Risk Intelligence (6B) | Category, projected expiry of stock in store, oldest batch's last sellable day, investigate-by day | SIMULATED × FORECAST, ASSUMED thresholds |
| Markdown eligibility (7B) | Eligible / Blocked / Insufficient / Not considered, and blockers | ASSUMED rules (v4 DRAFT) |
| Assumption sets v1–v4 | Gross margin %, minimum margin %, max markdown 25%, steps 5–25%, feasibility check (V8) | **ASSUMED**, illustrative |
| Recorded panel | Weekly price and discount % | RECORDED (apparently synthetic; noisy, see section 1) |

---

## 3. Demonstration mode

A separate, explicitly labelled mode. It is never mixed with research outputs and is never presented as business data.

1. **Banner on every view:** "DEMONSTRATION — ILLUSTRATIVE PRICES, COSTS AND RULES. Not real prices. No sales
   response is modelled."
2. **Its own DRAFT parameter block** in a future assumption set **v5**, carrying v4 unchanged. It would hold:
   - `demo_mode = true`
   - price base rule: the reference-price proxy
   - cost rule: illustrative cost = base × (1 − assumed gross margin)
   - minimum margin, maximum markdown, markdown steps and a price-rounding rule
   - a no-overlap rule and a cooldown

   All are ASSUMED; v1–v4 are untouched.
3. **Inputs:** only lines that Stage 7B marks **Eligible for markdown review**. Blocked and Insufficient lines show only
   their blocker or gap, with no options.
4. **Outputs:** an options table per line. Every step appears with its arithmetic and either *Allowed in demonstration*
   or *Blocked (reason)*.
   - No option is marked "recommended".
   - Nothing becomes a proposal.
   - There is no button.

---

## 4. How a future pricing engine would calculate and enforce the rules

All values per unit, for one line and one decision week.

| Quantity | Definition |
|---|---|
| Original (base) price `P0` | Demo: reference-price proxy. Real use: verified regular shelf price (data D2). |
| Unit cost `C` | Demo: `P0 × (1 − gross_margin%)`. Real use: verified purchase cost (D1). |
| Markdown step `d` | One of the allowed steps; never a free number |
| Marked-down price `P(d)` | `P0 × (1 − d)`, then the price-rounding rule (decision P3) |
| Margin per unit `M(d)` | `P(d) − C` |
| Gross margin % `GM(d)` | `M(d) ÷ P(d)` |
| **Margin floor** | Allowed only if `GM(d) ≥ min_margin%`; equivalently `P(d) ≥ C ÷ (1 − min_margin%)`. This is the same rule as the existing V8 feasibility check. |
| **Maximum markdown** | Allowed only if `d ≤ max_markdown%` (DRAFT 25%) |
| **Never below cost** | `M(d) > 0`, implied by the floor |
| Break-even multiplier (optional, P5) | `M(0) ÷ M(d)`: how many times more units must sell at price `P(d)` to earn the same total margin as at `P0`. Pure arithmetic, **not a forecast** of what will sell. |

### Option-level blockers

Every applicable blocker is reported, in this order:

| Code | Rule |
|---|---|
| `LINE_NOT_ELIGIBLE` | The 7B status is not Eligible. The 7B blockers are shown instead. |
| `OVERLAPPING_PROMOTION` | A promotion is already recorded for this line and week, or an earlier markdown on the same batch is within the cooldown |
| `EXCEEDS_MAX_MARKDOWN` | `d > max_markdown%` |
| `BELOW_MARGIN_FLOOR` | `GM(d) < min_margin%` |
| `NOT_AN_ALLOWED_STEP` | `d` is not in the configured steps; defensive |
| `PRICE_ROUNDING_BREACH` | Rounding would push the price below the floor; defensive |

**Overlapping promotions are avoided three ways:**
- a line already on a recorded promotion is blocked (inherited from 7B)
- only one active markdown is allowed per batch
- there is a cooldown between markdowns on the same line (decision P6)

---

## 5. From eligibility to a proposal to human approval

The four states from Stage 7A are kept, and a record moves forward one state at a time.

| State | Name | What happens | Built? |
|---|---|---|---|
| 1 | Eligible for investigation | Stage 7B status | **Yes** |
| 1b | Demonstration options | Arithmetic and rule checks for illustrative steps, as designed here. Never a proposal. | **Design only** |
| 2 | Hypothetical numerical proposal | **One** specific step for one line, chosen by a person or a validated method. Needs verified data D1–D4, D6 and D8, a defined proposal expiry and a full evidence record. | **No** |
| 3 | Approved / rejected | Approval event by a named, authorised role within its limits, with a reason. No bulk or automatic approval, and never for Christmas by default. | **No** |
| 4 | Executed | Done in the store's own price system and confirmed back to this system. This system never changes a price. | **No** |

**Audit record (future), append-only:**
- proposal id
- line, week and batch
- inputs with evidence labels
- assumption-set id and hash
- system version
- the options shown and their blockers
- chosen step and who chose it
- approver, decision, reason and timestamps
- execution confirmation reference

---

## 6. What can and cannot be demonstrated

**Can be demonstrated with illustrative data (clearly labelled):**
- how margin per unit and margin % change with each markdown step
- that the margin floor and maximum markdown block specific steps, and why
- that overlapping promotions, Christmas and ineligible lines are blocked
- break-even arithmetic, if approved (P5): how many more units a markdown would need to sell to keep the same total
  margin
- the illustrative cost of stock at risk: projected expiry units × illustrative cost. This is arithmetic, not a saving.
- the approval and audit workflow, as a design

**Cannot be claimed without genuine sales-response evidence:**
- that any markdown would sell more units, or how many
- that any markdown would reduce waste, or by how much
- which option is "best", "optimal" or "recommended"
- any change in revenue, profit or margin for the line or the store
- any price elasticity. The +1.6% per discount point figure is a non-causal association in apparently synthetic data and
  must never be used.

---

## 7. Worked example

The line: **Cottage Cheese 300g, store 504 (London), order week 40** (P2, SC1).

**Evidence from earlier stages:**
- **Stage 6B:** High waste risk. About 2,374 units in store may go out of date (60% of a typical week).
- **Batch timing:** the oldest batch is sellable until Thu, week 40. Investigate by Wed, week 40.
- **Stage 7B:** **Eligible for markdown review.** There are no blockers. An open inventory case is a warning only.

**Illustrative inputs** (DEMONSTRATION, all ASSUMED except where noted):

| Input | Value | Label |
|---|---|---|
| Original (base) price `P0` | **2.64** | Reference-price proxy from the forecast contract; ESTIMATED. Currency assumed GBP. |
| Recorded shelf price that week | 2.58, no recorded discount | RECORDED, apparently synthetic. Context only; not used as the base, see section 1. |
| Gross margin (Dairy) | 28% | ASSUMED |
| Illustrative unit cost `C` | 2.64 × 0.72 = **1.90** | CALCULATED from ASSUMED |
| Minimum margin (Dairy) | 8%, giving a floor price of 1.90 ÷ 0.92 = **2.07** | ASSUMED |
| Maximum markdown | 25% | ASSUMED |

**Illustrative options** (prices before any rounding rule):

| Markdown | Illustrative price | Margin per unit | Gross margin % | Break-even multiplier* | Status |
|---|---|---|---|---|---|
| none | 2.64 | 0.74 | 28.0% | 1.00 | full price |
| 5% | 2.51 | 0.61 | 24.2% | 1.22 | Allowed in demonstration |
| 10% | 2.38 | 0.48 | 20.0% | 1.56 | Allowed in demonstration |
| 15% | 2.24 | 0.34 | 15.3% | 2.15 | Allowed in demonstration |
| 20% | 2.11 | 0.21 | 10.0% | 3.50 | Allowed in demonstration |
| 25% | 1.98 | 0.08 | 4.0% | 9.33 | ⛔ **Blocked: below the 8% margin floor** |

\*To earn the same total margin as at full price, about this many times as many units would have to sell. **This is
arithmetic, not a forecast.** Nothing says that many would sell.

**What a manager would read:**

> "This line is eligible for a markdown review. In the demonstration, markdowns of 5–20% stay above the assumed 8% margin
> floor; 25% does not. A 20% markdown would leave 0.21 margin per unit — it would need 3.5 times the units to earn the
> same margin as full price. Whether any markdown would actually help is unknown: there is no evidence yet of how sales
> respond to price. No option is recommended and nothing has been proposed or approved."

**Illustrative cost of stock at risk:** 2,374 units × 1.9008 ≈ **4,512**. This is the illustrative cost of the units that
may go out of date. It is not a saving and not a prediction.

---

## 8. Pricing Intelligence dashboard page (design)

New page "Pricing intelligence (demonstration)", placed after Markdown review, using the same sidebar (scenario, policy,
store, product):

1. **Top banner:** DEMONSTRATION — ILLUSTRATIVE PRICES, COSTS AND RULES. It also says which policy and scenario the
   lines come from.
2. **Line picker:** only Stage 7B *Eligible* lines. Blocked or Insufficient lines show their reasons and no options.
3. **Price panel:**
   - the original illustrative price, with its source label
   - the recorded shelf price that week, as context, with a note on its volatility
   - the illustrative cost and margin at full price
   - the margin floor price
4. **Options table:** one row per step, with illustrative price, margin per unit, gross margin %, break-even multiplier
   (if approved) and status. Blocked steps are shown with a ⛔ and the reason. No row is highlighted as "best".
5. **"Why no option is recommended" panel:** lists the missing evidence (D1–D4, D6, D8 from Stage 7A).
6. **Lifecycle strip:** state 1 ✅ → 1b (this demonstration) → 2 / 3 / 4 not built.
7. **Technical details expander:** formulas, assumption-set id and hash, codes.
8. **No buttons:** nothing to approve, propose, apply or export as a price.

Read-only and computed from saved outputs plus the v5 DRAFT demonstration block. Tests would cover:
- the arithmetic, at each margin-floor and maximum-markdown boundary
- overlap and ineligible lines
- no "recommended" label
- no buttons
- labels on every figure
- no future data
- protected checksums

---

## 9. Risks

1. **Anchoring on illustrative numbers.** People may treat demonstration prices and costs as real. Mitigations: banners,
   labels on every figure, separate parameters and no export.
2. **False precision.** Margin % to one decimal can look authoritative. The inputs are assumed.
3. **Break-even misread as a forecast.** It must always carry "not a forecast" (P5).
4. **Recorded price noise.** Using the recorded price as the base would give unstable, misleading options, so it is
   avoided.
5. **Policy dependence.** Eligible lines differ by policy and scenario, so the page must always say which it shows.
6. **Scope creep towards optimisation.** Choosing an option automatically, or ranking options by expected profit, would
   require response evidence we lack. It is out of scope.
7. **Approval by omission.** A future workflow must make "no action" an explicit, recorded choice, and must let
   proposals lapse.

---

## 10. Missing data (unchanged from Stage 7A; all required before state 2)

| | Needed | Today |
|---|---|---|
| D1 | Purchase cost per unit | Missing: margins assumed |
| D2 | Verified shelf and regular price | Partial: recorded prices are noisy; reference price is a proxy |
| D3 | Stock by batch with real expiry dates | Missing: simulated only |
| D4 | Markdown response history (causal) | Missing: recorded discounts are not causal evidence |
| D5 | Value of alternatives (donation, staff sale, disposal) | Missing |
| D6 | Pricing rules (legal, supplier, brand, price-matching) | Missing |
| D7 | Store markdown operations | Missing |
| D8 | Approval ownership and limits | Missing: documented requirements only |
| D9 | Confirmed supplier schedules | Missing: 360 series assumed |

---

## 11. Decisions requiring approval

| # | Decision | Recommendation |
|---|---|---|
| P1 | Build a separate, labelled demonstration mode (section 3) | Approve |
| P2 | Use the reference-price proxy, not the recorded weekly price, as the illustrative base | Approve (recorded prices are too noisy) |
| P3 | Price-rounding rule: to 0.01, or to a retail ending such as .x9; the floor is checked after rounding | 0.01 for the demonstration |
| P4 | Show options only for 7B-Eligible lines | Approve |
| P5 | Show the break-even multiplier, labelled "arithmetic, not a forecast" | Approve, with the label |
| P6 | Overlap rules: block recorded promotions, one active markdown per batch, cooldown length | Approve the first two; set the cooldown later |
| P7 | Show the illustrative cost of stock at risk (units × illustrative cost) | Optional; if shown, label it as not a saving |
| P8 | Hold the demonstration parameters in a new assumption set v5 (DRAFT), v4 unchanged | Approve |
| P9 | Never mark an option "recommended", and no state 2 until D1–D4, D6 and D8 exist | Approve |
| P10 | Proceed to Stage 8B: implement the demonstration page, read-only | Your decision |
