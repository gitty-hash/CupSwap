"""Part B UI: the buyer agent (plan → approve → ReAct → approve purchase → memory update)."""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from cupswap import buyer_agent, memory, store
from cupswap.config import BUYER_CLOCK, BUYER_MAX_STEPS
from cupswap.llm import CacheMiss
from cupswap.scenarios import BUYER
from cupswap.trace import Trace
from ui.common import get_llm, is_cached, live_logger, recording_caption, render_plan, render_recommendation, render_trace
from ui.style import callout, hero, html, pill, progress_states, section, stepper

STEPS = ["Delegate goal", "Approve plan", "Agent executes", "Approve purchase", "Memory updated"]
PHASE_INDEX = {"idle": 0, "plan_ready": 1, "recommended": 3, "done": 5}


def _memory_card(profile: dict, title: str, tone: str) -> None:
    p = profile
    html(f'<div class="cs-eyebrow">{escape(title)}</div>'
         f'<div class="cs-line" style="font-size:1rem"><b>{escape(p["display_name"])}</b> · {escape(p["home_city"])}</div>'
         '<div class="cs-line">' + pill("⚽ " + ", ".join(p["favorite_teams"]), tone)
         + "".join(pill(c, "gray") for c in p["cities_within_reach"]) + "</div>")
    rows = [
        ("Budget", f"${p['budget_habits']['typical_max_per_ticket']}/ticket — {p['budget_habits']['notes']}"),
        ("Seats", "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in p["seat_preferences"].items())),
        ("Sellers", f"min rating {p['seller_rules']['min_seller_rating']} · avoid "
                    f"{', '.join(p['seller_rules']['avoid_sellers']) or 'none'}"),
        ("Notes", " · ".join(p.get("agent_notes", [])) or "—"),
    ]
    html('<div class="cs-kv">' + "".join(f'<div class="k">{escape(k)}</div><div class="v">{escape(v)}</div>'
                                         for k, v in rows) + "</div>")
    with st.expander(f"Past purchases ({len(p['past_purchases'])})", icon=":material/receipt_long:"):
        st.dataframe(pd.DataFrame(p["past_purchases"]), hide_index=True, width="stretch")


def page() -> None:
    hero("Part B · Chapter 5 — single agent", "Buyer Agent",
         "One fan delegates a ticket hunt. The agent plans, waits for your approval, then reasons and acts through "
         "tools in a think → act → observe loop, remembers the fan's preferences, and never buys without your click.",
         ["Plan mode + human approval", "ReAct + strict function calling", "Long-term memory",
          f"Hard cap: {BUYER_MAX_STEPS} steps", f"Demo clock {BUYER_CLOCK.replace('T', ' ')}"])
    ss = st.session_state
    b = ss.setdefault("buyer", {"phase": "idle"})
    stepper(STEPS, progress_states(len(STEPS), PHASE_INDEX[b["phase"]]))
    locked = b["phase"] not in {"idle", "done"}

    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            html('<div class="cs-eyebrow">1 · The request</div>')
            sid = st.selectbox("Fan profile — same request, different long-term memory", list(BUYER),
                               format_func=lambda k: BUYER[k]["label"], disabled=locked, key="buyer_sid")
            cfg = BUYER[sid]
            goal = st.text_area("Goal and constraints", value=cfg["goal"], height=68, disabled=is_cached() or locked,
                                help="Cached mode replays the recorded request. Switch to Live mode to type your own.")
            use_mcp = st.toggle("Call check_match_status via the MCP server (bonus)", value=cfg["use_mcp"], disabled=locked,
                                help="The agent discovers the tool with MCP list_tools and calls it over stdio.")
            if is_cached():
                recording_caption(sid)

        scenario = sid if is_cached() else f"{sid}_live"

        # ---------------- phase: idle -> draft plan ----------------
        if b["phase"] in {"idle", "done"}:
            if st.button("Draft a plan", icon=":material/map:", type="primary",
                         help="Plan mode: the agent proposes steps but may not act until you approve."):
                llm = get_llm(scenario, {"fan_id": cfg["fan_id"], "goal": goal, "use_mcp": use_mcp})
                if llm:
                    store.reset_files(["listings.json", "holds.json"])
                    before = memory.load(cfg["fan_id"])
                    trace = Trace()
                    with st.status("Agent is drafting a plan…", expanded=True) as box:
                        trace.on_event = live_logger(box)
                        try:
                            plan = buyer_agent.draft_plan(llm, before, goal, trace)
                        except CacheMiss as e:
                            st.error(str(e))
                            return
                    ss["buyer"] = {"phase": "plan_ready", "sid": sid, "scenario": scenario, "fan_id": cfg["fan_id"],
                                   "goal": goal, "use_mcp": use_mcp, "plan": plan, "plan_version": 1,
                                   "memory_before": before, "trace": trace.to_list()}
                    st.rerun()

        # ---------------- phase: plan ready -> human approval ----------------
        if b["phase"] == "plan_ready":
            with st.container(border=True):
                html(f'<div class="cs-eyebrow">2 · Your approval is required</div>'
                     f'<div class="cs-line" style="font-size:1.05rem"><b>Plan v{b["plan_version"]}</b> '
                     f'{pill("agent is waiting — no action taken yet", "orange")}</div>')
                render_plan(b["plan"])
                cA, cB, cC = st.columns([2, 3, 1])
                approve = cA.button("Approve plan & run agent", icon=":material/play_arrow:", type="primary")
                revise = False
                feedback = None
                if not is_cached():
                    feedback = cB.text_input("Request changes", placeholder="e.g. only Dallas, under $350",
                                             label_visibility="collapsed")
                    revise = cB.button("Revise plan", icon=":material/edit:", disabled=not feedback)
                else:
                    cB.caption("Plan revision is available in Live mode.")
                if cC.button("Cancel", icon=":material/close:"):
                    ss["buyer"] = {"phase": "idle"}
                    st.rerun()
            if revise and feedback:
                trace = Trace.from_list(b["trace"])
                llm = get_llm(b["scenario"])
                plan = buyer_agent.draft_plan(llm, b["memory_before"], b["goal"], trace, feedback=feedback,
                                              previous=b["plan"], version=b["plan_version"] + 1)
                b.update(plan=plan, plan_version=b["plan_version"] + 1, trace=trace.to_list())
                st.rerun()
            if approve:
                trace = Trace.from_list(b["trace"])
                llm = get_llm(b["scenario"])
                with st.status("Agent is executing the approved plan (think → act → observe)…", expanded=True) as box:
                    trace.on_event = live_logger(box)
                    try:
                        session = buyer_agent.run_react(llm, b["memory_before"], b["goal"], b["plan"], trace,
                                                        use_mcp=b["use_mcp"])
                    except CacheMiss as e:
                        st.error(str(e))
                        return
                    box.update(label="Agent finished — review its recommendation", state="complete")
                b.update(phase="recommended", session=session, trace=trace.to_list())
                st.rerun()

        # ---------------- phase: recommendation -> human purchase gate ----------------
        if b["phase"] == "recommended":
            session = b["session"]
            r = session.recommendation
            with st.container(border=True):
                html('<div class="cs-eyebrow">4 · Purchase decision — only you can buy</div>')
                if r:
                    render_recommendation(r)
                    if session.hold:
                        st.caption(f"Hold {session.hold['hold_id']} on {session.hold['listing_id']} expires "
                                   f"{session.hold['expires_at']} — reversible and monitored, not a purchase.")
                else:
                    st.warning("The agent hit its step cap without a recommendation; any hold was released.")
                can_buy = bool(r and r["status"] == "recommend")
                cA, cB = st.columns(2)
                yes = cA.button(f"Approve purchase · ${r['total_price']:,.0f} (mock)" if can_buy else "Approve purchase",
                                icon=":material/verified:", type="primary", disabled=not can_buy, width="stretch")
                no = cB.button("Decline & release hold" if can_buy else "End session", icon=":material/block:",
                               width="stretch")
            if yes or no:
                trace = Trace.from_list(b["trace"])
                llm = get_llm(b["scenario"])
                order = buyer_agent.decide_purchase(session, bool(yes), trace)
                outcome = "approved" if order else "declined"
                after = buyer_agent.end_session(llm, b["memory_before"], session, outcome, trace)
                b.update(phase="done", order=order, memory_after=after, trace=trace.to_list())
                st.rerun()

        if b["phase"] == "done":
            if b.get("order"):
                st.success(f"Mock purchase {b['order']['order_id']} executed after your approval: "
                           f"{b['order']['listing_id']} ×{b['order']['quantity']} = ${b['order']['total']:,.0f}. "
                           f"No real money moved.", icon=":material/check_circle:")
            else:
                st.info("Session ended without a purchase.")
            callout("Switch to the other fan profile and run the same request to see how long-term memory changes "
                    "the agent's search, shortlist and final choice.", "Try the comparison", "violet")

    with right:
        with st.container(border=True):
            profile_now = memory.load(cfg["fan_id"])
            _memory_card(b.get("memory_before") or profile_now, "Long-term memory — BEFORE this session", "blue")
        if b.get("memory_after"):
            with st.container(border=True):
                _memory_card(b["memory_after"], "Long-term memory — AFTER this session", "green")
                diff = memory.diff(b["memory_before"], b["memory_after"])
                if diff:
                    html('<div class="cs-eyebrow" style="margin-top:6px">What changed</div>')
                    st.dataframe(pd.DataFrame(diff), hide_index=True, width="stretch")
        callout("Plan → you approve · Search, status, price history, seller ratings → autonomous · "
                "Hold (15 min, reversible) → monitored · Purchase → you approve · Memory update → monitored",
                "Placed autonomy", "blue")

    if b.get("trace"):
        section("Agent trace", "Every think, act and observe step in order — expand observations to see exactly "
                               "what the agent saw.")
        render_trace(b["trace"], key="buyer")
