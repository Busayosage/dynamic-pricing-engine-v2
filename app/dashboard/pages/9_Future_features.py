import streamlit as st

import theme as T
import ui

ui.page("Future features", "🚧")
T.md(T.head("Roadmap", "What is built, and what is not yet",
            "Six research capabilities are built and read-only. The remaining decision capabilities are not built, and "
            "each would need verified evidence and a person's authorisation.",
            chips=("6 built · read-only", "1 not built", "Nothing approved or executed"), art="road"))

T.md(T.section("Built", "Each one informs a person; none changes an order, a price or stock."))
T.md(T.grid([
    T.use_case("✅", "Waste-Risk Intelligence", "Completed — Stage 6B · Advisory only. Flags which products may go out of "
               "date before they sell, how many units, why and when to look — see the Waste risk page. It does not "
               "reduce orders, mark down prices, donate stock or create review cases."),
    T.use_case("✅", "Markdown review eligibility", "Completed — Stage 7B · Eligibility only · Read-only. Says whether a "
               "person should look at a line for a possible markdown, and why not when it is blocked."),
    T.use_case("✅", "Pricing intelligence demonstration", "Completed — Stage 8B · Illustrative only. The price, margin "
               "and rule-check arithmetic, now part of the Discount Decision Lab."),
    T.use_case("🧪", "Numerical discount recommendations", "Completed — Phase 1 · Simulated research · Read-only. Ranks "
               "permitted markdown steps against keeping the full price under stated customer-response scenarios, or "
               "returns NO RECOMMENDATION with the reason — see the Discount Decision Lab. Not validated for live use."),
    T.use_case("📈", "Dynamic pricing", "Completed — Phase 2 · Simulated research · Read-only. Weekly markdown decisions "
               "simulated inside the inventory replay, with orders unchanged, compared with unchanged prices under four "
               "customer responses including none — see the Dynamic Pricing Lab. Not validated for live use."),
    T.use_case("♻️", "Waste intervention intelligence", "Completed — Phase 3 · Advisory · Read-only. For stock at risk of "
               "expiring, classifies a next-order review, transfer, markdown, donation or disposal, and no action — with "
               "evidence, blockers, missing information and human checks. Transfers and donations are investigate only; "
               "nothing is executed — see the Waste Intervention Lab."),
]))

T.md(T.section("Not yet built", "Placeholders only. Nothing below calculates, recommends or changes anything."))
T.md(T.banner("<b>NOT BUILT.</b> These cards describe intended capabilities and what they would require. None exists "
              "in this system.", "coral", "🚧"))
T.md(T.grid([
    T.roadmap_card("⚙️", "Executable waste interventions", "NOT BUILT",
                   "Carry out an intervention: change an order, move stock, mark down, donate or dispose. None is built; "
                   "the Waste Intervention Lab only supports investigation, and a person decides what to do.",
                   ["Distances, transport times and costs", "Receiving capacity and batch-level stock",
                    "Donation partners and food-safety rules", "Real costs and verified prices", "Named approvers"],
                   "A store manager or buyer authorises each action; nothing is triggered automatically."),
]))
T.md(T.banner("<b>Before numerical discount recommendations could be used live:</b> verified purchase costs and shelf "
              "prices, batch-level stock and expiry, causal evidence of how sales respond to markdowns, legal and "
              "commercial pricing rules, and named approvers. Every proposal would be approved individually by a "
              "person — never in bulk or automatically.", "caution", "⚠️"))
st.caption("Order quantities everywhere remain HYPOTHETICAL_UNAPPROVED and NOT_EXECUTED.")
