"""Landing page: what CupSwap is, how to use the control room, and where autonomy is placed."""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from cupswap import store
from cupswap.config import REFUND_APPROVAL_THRESHOLD
from ui.style import hero, html, kpis, pill, section

FEATURES = [
    ("buyer", "🛒", "#EFF6FF", "Buyer Agent", "Part B · Chapter 5",
     "One fan, one agent. Plan mode with approval, a think-act-observe loop over six tools, long-term memory, and a "
     "human purchase gate. Same request, two fans, two different answers."),
    ("negotiation", "🤝", "#FFF1F2", "Negotiation Arena", "Part C · Chapters 5–6",
     "Buyer, seller and platform agents negotiate under a price cap and fee. Watch concessions, test for leaked limits "
     "and see who captured the surplus."),
    ("operations", "🌩️", "#FFFBEB", "Operations Desk", "Part D · Chapter 6",
     "A storm postpones a match. A fixed workflow classifies, cites policy and routes 14 orders; large refunds wait "
     "for you; recovery rules catch mistakes."),
    ("fairdrop", "⚖️", "#ECFDF5", "Fair-Drop Desk", "Part E · innovation",
     "Organizer releases without the bot race: verified-need tiers, injection defense, a published-seed lottery, an "
     "AI fairness audit and organizer approval."),
]

AUTONOMY = [
    ("Buyer agent", "Draft a plan", "LLM-generated, human-imposed goal", ("Human approves", "red")),
    ("Buyer agent", "Search, match status, price history, seller rating", "Read-only", ("Autonomous, traced", "blue")),
    ("Buyer agent", "Place a hold (15 min)", "Reversible", ("Monitored", "green")),
    ("Buyer agent", "Purchase", "Irreversible money", ("Human approves", "red")),
    ("Buyer agent", "Update long-term memory", "Visible diff", ("Monitored", "green")),
    ("Platform agent", "Verify ticket, apply price cap, publish ruling", "Rule enforcement", ("Autonomous + code guard", "blue")),
    ("Buyer & seller agents", "Offers and counter-offers", "Bounded, 5 rounds", ("Monitored + code guards", "green")),
    ("Platform agent", "Record settlement / execute purchase", "Irreversible money", ("Only after human approval", "red")),
    ("Ops workflow", f"Refund ≤ ${REFUND_APPROVAL_THRESHOLD:,.0f}", "Irreversible, small", ("Automatic + monitor", "green")),
    ("Ops workflow", f"Refund > ${REFUND_APPROVAL_THRESHOLD:,.0f}", "Irreversible, large", ("Human approves", "red")),
    ("Ops workflow", "Reissue for new date · freeze order · dispute queue", "Reversible", ("Monitored", "green")),
    ("Ops workflow", "Flag an account", "Reputational", ("Human approves", "red")),
    ("Fair-Drop", "Allocate released tickets", "Irreversible, fairness-critical", ("Organizer approves", "red")),
    ("Fair-Drop", "Hold linked accounts for review", "Reversible", ("Monitored — never auto-ban", "green")),
]


def page() -> None:
    hero("MIS 552 · Homework 3 · fictional platform, mock tools, synthetic data",
         "CupSwap — an agent-to-agent marketplace for World Cup 2026",
         "A control room for agents, not a chat window. Watch a buyer agent plan and act, three agents negotiate under "
         "marketplace rules, a workflow handle a storm postponement, and a fair allocation desk keep organizer releases "
         "honest — with every step traced and every irreversible action behind a human click.",
         ["Auditability: every step leaves a readable trace", "Placed autonomy: humans gate irreversible actions",
          "Runs without an API key (cached demo)"])

    from ui.common import PAGES
    cols = st.columns(4, gap="medium")
    for col, (path, icon, bg, title, tag, desc) in zip(cols, FEATURES):
        with col:
            html(f'<div class="cs-card feature"><div class="ic" style="background:{bg}">{icon}</div>'
                 f'<div class="cs-eyebrow">{escape(tag)}</div><div class="h">{escape(title)}</div>'
                 f'<div class="d">{escape(desc)}</div></div>')
            if path in PAGES:
                st.page_link(PAGES[path], label=f"Open {title}", icon=":material/arrow_forward:")

    section("How to run the demo", "Cached mode replays recorded LLM calls; tools, guards and approvals run for real")
    steps = [
        ("Buyer Agent", "Pick a fan → Draft a plan → approve → watch the trace → approve or decline the purchase → "
                        "compare memory before/after. Repeat with the other fan."),
        ("Negotiation Arena", "Run the Deal scenario and approve; run the No-deal scenario. Toggle the analyst view and "
                              "read the leakage test."),
        ("Operations Desk", "Ingest the weather feed; work the approval queue; inspect O-1010 and O-1014 to see "
                            "recovery rules catch failures."),
        ("Fair-Drop Desk", "Close the window, compare first-come-first-served with Fair-Drop, read the judge, approve."),
        ("Audit Log", "Every state change, who made it, and whether a human approved it."),
    ]
    html("".join(f'<div class="cs-line"><span class="cs-num">{i}</span> <b>{escape(t)}</b> — '
                 f'<span style="color:#475569">{escape(d)}</span></div>' for i, (t, d) in enumerate(steps, 1)))

    section("Where autonomy is placed", "Chapter 6: high-stakes, irreversible actions keep an explicit human approval "
                                        "gate; routine actions are monitored")
    rows = "".join(f"<tr><td><b>{escape(a)}</b></td><td>{escape(act)}</td><td style='color:#64748B'>{escape(nat)}</td>"
                   f"<td>{pill(ctl, tone)}</td></tr>" for a, act, nat, (ctl, tone) in AUTONOMY)
    html('<table class="cs-autonomy"><thead><tr><th>Agent / workflow</th><th>Action</th><th>Nature</th><th>Control</th>'
         f"</tr></thead><tbody>{rows}</tbody></table>")

    section("The bundled mock market", "Invented bracket and results — they need not match the real tournament")
    m, lst = store.matches(), store.listings()
    kpis([("Matches", len(m), "group stage → quarter-finals", "blue"),
          ("Host cities", len({x["city"] for x in m}), "US · Canada · Mexico", "violet"),
          ("Listings", len(lst), f"{len({x['seller_id'] for x in lst})} sellers", "green"),
          ("Postponement orders", len(store.seed("orders.json")), "4 languages", "orange"),
          ("Policy documents", 3, "weather · relocation · fraud", "gray")])
    a, b = st.columns(2, gap="large")
    with a:
        with st.expander("Matches", icon=":material/stadium:"):
            st.dataframe(pd.DataFrame([{"Match": x["match_id"], "Stage": x["stage"], "Teams": f"{x['home']} vs {x['away']}",
                                        "City": x["city"], "Kickoff": x["kickoff"].replace("T", " "), "Status": x["status"],
                                        "Result": x.get("result") or ""} for x in m]), hide_index=True, width="stretch")
    with b:
        with st.expander("Listings", icon=":material/confirmation_number:"):
            st.dataframe(pd.DataFrame([{"Listing": x["listing_id"], "Match": x["match_id"], "Seller": x["seller_id"],
                                        "Cat": x["category"], "Section": x["section"], "Qty": x["quantity"],
                                        "Together": x["seats_adjacent"], "$/ticket": x["price_per_ticket"],
                                        "Face $": x["face_value"], "Status": x["status"]} for x in lst]),
                         hide_index=True, width="stretch")
