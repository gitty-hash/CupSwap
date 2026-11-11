"""Part C UI: the negotiation arena."""
from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cupswap import negotiation, store
from cupswap.config import NEGOTIATION_MAX_ROUNDS, PLATFORM_FEE_RATE, PRICE_CAP_MULTIPLIER
from cupswap.llm import CacheMiss
from cupswap.scenarios import NEGOTIATION
from cupswap.trace import Trace
from ui.common import PLOT_LAYOUT, get_llm, is_cached, live_logger, recording_caption, render_trace
from ui.style import callout, hero, html, kpis, pill, progress_states, section, stepper

STEPS = ["Platform verifies listing", "Agents negotiate", "You approve", "Platform settles"]


def _offer_chart(state: dict, reveal: bool) -> go.Figure:
    h = state["history"]
    fig = go.Figure()
    s = [x for x in h if x["role"] == "Seller agent"]
    b = [x for x in h if x["role"] == "Buyer agent"]
    fig.add_trace(go.Scatter(x=[x["round"] for x in s], y=[x["price_per_ticket"] for x in s], mode="lines+markers",
                             name="Seller ask / counter", line=dict(color="#E11D48", width=3), marker=dict(size=8)))
    fig.add_trace(go.Scatter(x=[x["round"] for x in b], y=[x["price_per_ticket"] for x in b], mode="lines+markers",
                             name="Buyer offer", line=dict(color="#2563EB", width=3), marker=dict(size=8)))
    cap = state["rules"]["price_cap_per_ticket"]
    fig.add_hline(y=cap, line_dash="dot", line_color="#94A3B8", annotation_text=f"price cap ${cap:g}",
                  annotation_font_color="#64748B")
    if reveal:
        p = state["_private"]
        fig.add_hline(y=p["seller_floor"], line_dash="dash", line_color="#E11D48",
                      annotation_text=f"seller floor ${p['seller_floor']:g} (hidden)", annotation_position="bottom right")
        fig.add_hline(y=p["buyer_ceiling"], line_dash="dash", line_color="#2563EB",
                      annotation_text=f"buyer ceiling ${p['buyer_ceiling']:g} (hidden)", annotation_position="top left")
    if state.get("deal_price_per_ticket"):
        last_round = max(x["round"] for x in h)
        fig.add_trace(go.Scatter(x=[last_round], y=[state["deal_price_per_ticket"]], mode="markers", name="Deal",
                                 marker=dict(size=18, symbol="star", color="#F59E0B", line=dict(color="#0F172A", width=1))))
    fig.update_layout(**PLOT_LAYOUT, height=330, xaxis_title="Round", yaxis_title="$ per ticket", xaxis=dict(dtick=1),
                      legend=dict(orientation="h", y=1.12, x=0))
    return fig


def _transcript(state: dict) -> str:
    out = ['<div class="cs-chat">']
    ruling = state.get("ruling") or {}
    verified = ruling.get("verified")
    opening = "opening $" + str(ruling.get("enforced_opening_price"))
    out.append('<div class="cs-msg system"><div class="cs-who">Platform agent · ruling</div>'
               + pill("ticket verified" if verified else "NOT verified", "green" if verified else "red")
               + pill(opening, "blue")
               + '<div style="margin-top:4px">' + escape(ruling.get("note", "")) + "</div></div>")
    for h in state["history"]:
        cls = "buyer" if h["role"] == "Buyer agent" else "seller"
        action_tone = {"accept": "green", "ask": "gray", "offer": "blue", "counter": "orange"}.get(h["action"], "gray")
        checks = "".join(pill(("✓ " if c["ok"] else "✗ ") + c["rule"], "green" if c["ok"] else "red") for c in h["platform_checks"])
        guards = "".join(f'<div class="cs-guard">🛡 {escape(g)}</div>' for g in h.get("guards", []))
        out.append(f'<div class="cs-msg {cls}"><div class="cs-who">{escape(h["role"])} · round {h["round"]}</div>'
                   f'<div class="cs-price">{pill(h["action"].upper(), action_tone)} ${h["price_per_ticket"]:,.2f} '
                   f'<span style="font-weight:500;color:#64748B;font-size:.8rem">per ticket</span></div>'
                   f'<div>{escape(h["message"])}</div><div style="margin-top:5px">{checks}</div>{guards}</div>')
    status = state["status"]
    end = {"no_agreement": f"Round cap ({NEGOTIATION_MAX_ROUNDS}) reached — no agreement. The protocol ended gracefully.",
           "deal_pending_approval": "Agreement reached — waiting for the human buyer to approve.",
           "settled": "Deal approved by the human buyer and settled by the platform agent.",
           "declined": "The human buyer declined the deal.", "blocked": "Trading blocked: the ticket failed verification."}
    if status in end:
        out.append(f'<div class="cs-msg system"><b>{escape(end[status])}</b></div>')
    out.append("</div>")
    return "".join(out)


def page() -> None:
    hero("Part C · Chapters 5–6 — multi-agent", "Negotiation Arena",
         "An agent-to-agent market in miniature: a buyer agent with a private ceiling, a seller agent with a hidden "
         "floor and a concession schedule tied to kickoff proximity, and a neutral platform agent that verifies the "
         "ticket, enforces the price cap and settles. Every agent reads one shared negotiation state.",
         ["3 roles · own prompts", f"Bounded: {NEGOTIATION_MAX_ROUNDS} rounds", f"Cap {PRICE_CAP_MULTIPLIER}× face value",
          f"Fee {int(PLATFORM_FEE_RATE * 100)}% (seller pays)", "Human holds the final key"])
    ss = st.session_state
    n = ss.setdefault("nego", {"phase": "idle"})
    state = n.get("state")
    status = state["status"] if state else None
    cur = {None: 0, "deal_pending_approval": 2, "settled": 4, "declined": 3, "no_agreement": 2, "blocked": 0}[status]
    fail = {"no_agreement": 1, "declined": 2, "blocked": 0}.get(status)
    states = progress_states(len(STEPS), cur, failed=fail)
    if status == "no_agreement":
        states = ["done", "fail", "todo", "todo"]
    stepper(STEPS, states)

    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            html('<div class="cs-eyebrow">Scenario</div>')
            sid = st.selectbox("Scenario", list(NEGOTIATION), format_func=lambda k: NEGOTIATION[k]["label"],
                               disabled=n["phase"] == "deal_pending", key="nego_sid", label_visibility="collapsed")
            cfg = dict(NEGOTIATION[sid])
            if not is_cached():
                with st.expander("Live mode: custom negotiation", icon=":material/tune:"):
                    active = [x["listing_id"] for x in store.listings() if x["status"] == "active"]
                    cfg["listing_id"] = st.selectbox("Listing", active, index=active.index(cfg["listing_id"]) if cfg["listing_id"] in active else 0)
                    cfg["fan_id"] = st.selectbox("Buyer (fan profile)", ["sofia", "julien"], index=["sofia", "julien"].index(cfg["fan_id"]))
                    cfg["ceiling"] = st.number_input("Buyer's private ceiling ($/ticket)", 50.0, 1000.0, float(cfg["ceiling"]), 5.0)
            else:
                recording_caption(sid)
            run = st.button("Run negotiation", icon=":material/play_arrow:", type="primary",
                            disabled=n["phase"] == "deal_pending")
    with right:
        x = store.listing(cfg["listing_id"]) or {}
        m = store.match(x.get("match_id", "")) or {}
        pills = (pill("ask $%s" % x.get("price_per_ticket"), "orange") + pill("face $%s" % x.get("face_value"), "gray")
                 + pill("seller %s" % x.get("seller_id"), "gray") + pill("buyer %s × %s" % (cfg["fan_id"], cfg["quantity"]), "blue"))
        html('<div class="cs-card"><div class="cs-eyebrow">Listing ' + escape(cfg["listing_id"]) + "</div>"
             + '<div class="h">' + escape("%s vs %s" % (m.get("home"), m.get("away"))) + "</div>"
             + '<div class="d">' + escape("%s · %s · %s §%s row %s" % (m.get("stage"), m.get("city"), x.get("category"),
                                                                       x.get("section"), x.get("row"))) + "</div>"
             + pills + '<div class="d" style="margin-top:8px">Private limits stay hidden from the counterparty — use '
             "the analyst view after the run to compare.</div></div>")

    if run:
        scenario = sid if is_cached() else f"{sid}_live"
        llm = get_llm(scenario, {k: cfg[k] for k in ["listing_id", "fan_id", "quantity", "ceiling"]})
        if llm:
            store.reset_files(["listings.json"])
            trace = Trace()
            setup = negotiation.Setup(cfg["listing_id"], cfg["fan_id"], cfg["quantity"], cfg["ceiling"], cfg["label"])
            with st.status("Agents are negotiating…", expanded=True) as box:
                trace.on_event = live_logger(box)
                try:
                    new_state = negotiation.run(llm, setup, trace)
                except CacheMiss as e:
                    st.error(str(e))
                    return
                box.update(label=f"Negotiation finished: {new_state['status'].replace('_', ' ')}", state="complete")
            ss["nego"] = {"phase": "deal_pending" if new_state["status"] == "deal_pending_approval" else "done",
                          "state": new_state, "trace": trace.to_list(), "scenario": scenario}
            st.rerun()

    if not state:
        callout("Pick a scenario and click Run. The Deal scenario has a zone of agreement; in the No-deal scenario the "
                "seller's hidden floor sits above the buyer's hidden ceiling.", "How it works", "blue")
        return

    # ---------------- human gate (top, so it is impossible to miss) ----------------
    if n["phase"] == "deal_pending":
        with st.container(border=True):
            html(f'<div class="cs-eyebrow">Your decision</div><div class="cs-line" style="font-size:1.05rem">'
                 f'The agents agreed on <b>{state["quantity"]} × ${state["deal_price_per_ticket"]:,.2f} = '
                 f'${state["quantity"] * state["deal_price_per_ticket"]:,.2f}</b> (mock). Nothing executes until you approve.</div>')
            a, d, _ = st.columns([2, 1, 3])
            if a.button("Approve purchase", icon=":material/verified:", type="primary", width="stretch"):
                trace = Trace.from_list(n["trace"])
                llm = get_llm(n["scenario"])
                negotiation.settle(llm, state, trace)
                n.update(phase="done", state=state, trace=trace.to_list())
                st.rerun()
            if d.button("Decline", icon=":material/block:", width="stretch"):
                trace = Trace.from_list(n["trace"])
                negotiation.decline(state, trace)
                n.update(phase="done", state=state, trace=trace.to_list())
                st.rerun()
    if state.get("settlement"):
        s = state["settlement"]
        st.success(f"Settled by the platform agent: buyer paid ${s['buyer_total']:,.2f}, platform fee ${s['platform_fee']:,.2f}, "
                   f"seller receives ${s['seller_proceeds']:,.2f} (mock ledger).", icon=":material/check_circle:")
    if state["status"] == "no_agreement":
        p = state["_private"]
        st.warning(f"No agreement — the protocol ended gracefully at the round cap ({NEGOTIATION_MAX_ROUNDS}). No hold, no "
                   f"payment, nothing to undo. Analyst view: seller floor ${p['seller_floor']:g} > buyer ceiling "
                   f"${p['buyer_ceiling']:g}, so no zone of possible agreement existed.", icon=":material/do_not_disturb_on:")
    if state["status"] == "blocked":
        st.error("Trading blocked by the platform agent: the ticket failed verification.")

    # ---------------- transcript + chart ----------------
    left, right = st.columns([3, 2], gap="large")
    with left:
        section("Transcript", "Labeled by role · platform rule checks shown as badges on every offer")
        with st.container(border=True, height=620):
            html(_transcript(state))
    with right:
        section("Offer history", "Concessions per round")
        reveal = st.toggle("Analyst view: reveal hidden floor & ceiling", value=False)
        st.plotly_chart(_offer_chart(state, reveal), width="stretch")
        section("Shared negotiation state", "Collective memory — every agent reads this record before moving")
        st.dataframe(pd.DataFrame([{"Round": h["round"], "Role": h["role"].replace(" agent", ""), "Action": h["action"],
                                    "$/ticket": h["price_per_ticket"],
                                    "Checks": ", ".join(("✓ " if c["ok"] else "✗ ") + c["rule"] for c in h["platform_checks"])}
                                   for h in state["history"]]), hide_index=True, width="stretch")

    if state.get("deal_price_per_ticket") is not None:
        sp = negotiation.surplus(state)
        section("Who captured the surplus", f"Zone of possible agreement: ${sp['zopa_per_ticket']:g}/ticket × "
                                            f"{sp['quantity']} = ${sp['zopa_per_ticket'] * sp['quantity']:g} of gains from trade")
        kpis([("Deal", f"${sp['deal_price']:g} × {sp['quantity']}", "agreed price per ticket", "blue"),
              ("Buyer surplus", f"${sp['buyer_surplus']:,.2f}", "(ceiling − price) × qty", "green"),
              ("Seller surplus after fee", f"${sp['seller_surplus_after_fee']:,.2f}", "(price − fee − floor) × qty",
               "red" if sp["seller_surplus_after_fee"] < 0 else "green"),
              ("Platform fee", f"${sp['platform_fee']:,.2f}", f"{int(PLATFORM_FEE_RATE * 100)}% of the sale", "violet")])

    # ---------------- leakage test ----------------
    section("Leakage test", "What did each agent reveal to a counterparty that logs everything?")
    leaks = negotiation.leakage_report(state)
    if leaks:
        st.dataframe(pd.DataFrame(leaks).rename(columns=str.capitalize), hide_index=True, width="stretch")
    else:
        st.success("No explicit or verbal leakage of the private floor or ceiling detected in this transcript.")
    st.caption("EXPLICIT = a message states the private number · SIGNAL = limit language that tells the counterparty "
               "where the wall is · BEHAVIORAL = the price path itself sits on the private limit.")

    with st.expander("Full trace — platform tool calls, guards, approvals", icon=":material/timeline:"):
        render_trace(n["trace"], key="nego")
