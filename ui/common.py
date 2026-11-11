"""Shared UI pieces: sidebar controls, LLM factory, trace timeline, plan & recommendation cards."""
from __future__ import annotations

import time
from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cupswap import store
from cupswap.config import (BUYER_MAX_STEPS, MODEL, NEGOTIATION_MAX_ROUNDS, PLATFORM_MAX_STEPS,
                            REFUND_APPROVAL_THRESHOLD, live_available)
from cupswap.llm import CacheMiss, LLMClient, cost_usd, recording_meta
from cupswap.trace import TraceEvent
from ui.style import callout, html, inject_css, kpis, pill

PAGES: dict = {}  # filled by app.py: url_path -> st.Page (used for in-app links)

STATUS_TONE = {"ok": "green", "warn": "orange", "fail": "red", "info": "blue"}
PLOT_LAYOUT = dict(template="plotly_white", font=dict(family="Inter, sans-serif", size=12, color="#334155"),
                   margin=dict(l=10, r=10, t=36, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FFFFFF")


# ---- sidebar ------------------------------------------------------------------------------------
def sidebar() -> None:
    inject_css()
    ss = st.session_state
    ss.setdefault("usage", {"prompt": 0, "completion": 0, "calls": 0, "replayed": 0})
    ss.setdefault("mode", "cached")
    with st.sidebar:
        html('<div class="cs-brand"><div class="n">⚽ CupSwap</div>'
             '<div class="s">Agent control room · World Cup 2026 resale</div></div>')
        html('<div class="cs-side-label">Run mode</div>')
        choice = st.segmented_control("Run mode", ["Cached demo", "Live API"], label_visibility="collapsed",
                                      default="Live API" if ss["mode"] == "live" else "Cached demo", key="mode_seg")
        if choice == "Live API" and not live_available():
            st.warning("Live mode needs the OPENAI_API_KEY environment variable.")
            choice = "Cached demo"
        ss["mode"] = "live" if choice == "Live API" else "cached"
        html(f'<div class="cs-modebox"><b style="color:#F8FAFC">{MODEL}</b><br>'
             + ("Replays recorded LLM responses. Tools, guards, rules and state changes run for real — no API key needed."
                if ss["mode"] == "cached" else "Calls the OpenAI API. Each run is saved under recordings/live/.")
             + "</div>")
        if ss["mode"] == "cached":
            ss["replay_delay"] = st.slider("Replay speed (seconds per step)", 0.0, 1.0, ss.get("replay_delay", 0.25), 0.05)
        u = ss["usage"]
        html('<div class="cs-side-label">This session</div>'
             f'<div class="cs-stats"><div class="cs-stat"><div class="v">{u["calls"]}</div><div class="l">live calls</div></div>'
             f'<div class="cs-stat"><div class="v">{u["replayed"]}</div><div class="l">replayed calls</div></div>'
             f'<div class="cs-stat"><div class="v">{(u["prompt"] + u["completion"]):,}</div><div class="l">tokens</div></div>'
             f'<div class="cs-stat"><div class="v">${cost_usd(u["prompt"], u["completion"]):.3f}</div><div class="l">est. cost</div></div></div>')
        html('<div class="cs-side-label">Safety rails</div>'
             '<div class="cs-rail">• Mock tools on local files — no real money, tickets, emails or scraping</div>'
             '<div class="cs-rail">• Agents run only when you click Run</div>'
             f'<div class="cs-rail">• Hard caps: ReAct {BUYER_MAX_STEPS} steps · {NEGOTIATION_MAX_ROUNDS} rounds · '
             f'platform {PLATFORM_MAX_STEPS} steps</div>'
             f'<div class="cs-rail">• Human gates: purchases, refunds &gt; ${REFUND_APPROVAL_THRESHOLD:,.0f}, account flags, allocations</div>')
        st.write("")
        if st.button("Reset demo data", icon=":material/restart_alt:", width="stretch",
                     help="Restore listings, matches, fan memory and all mock ledgers to the bundled seed data."):
            store.reset_state()
            for k in list(ss.keys()):
                if k not in {"mode", "mode_seg", "usage", "replay_delay"}:
                    del ss[k]
            st.toast("Demo data reset to the bundled seed.", icon=":material/check_circle:")
            st.rerun()


def _make_usage_sink(us: dict):
    # Bound to the dict itself (not st.session_state) so worker threads in parallel LLM nodes can report usage.
    def sink(u: dict) -> None:
        if u.get("replayed"):
            us["replayed"] += 1
        else:
            us["calls"] += 1
            us["prompt"] += u.get("prompt_tokens", 0)
            us["completion"] += u.get("completion_tokens", 0)
    return sink


def get_llm(scenario: str, inputs: dict | None = None) -> LLMClient | None:
    mode = st.session_state.get("mode", "cached")
    usage = st.session_state.setdefault("usage", {"prompt": 0, "completion": 0, "calls": 0, "replayed": 0})
    try:
        return LLMClient(mode, scenario, inputs=inputs, usage_sink=_make_usage_sink(usage))
    except CacheMiss as e:
        st.error(f"{e}")
        return None


def is_cached() -> bool:
    return st.session_state.get("mode", "cached") == "cached"


def recording_caption(scenario: str) -> None:
    meta = recording_meta(scenario)
    if meta:
        html(f'<div style="font-size:.78rem;color:#64748B;margin:2px 0 6px">{pill("recorded live run", "violet")} '
             f'{escape(str(meta["recorded_at"]).replace("T", " "))} · {escape(str(meta["model"]))} · {meta["calls"]} LLM calls · '
             f'{meta["prompt_tokens"] + meta["completion_tokens"]:,} tokens · ${meta["cost_usd"]:.4f}</div>')
    else:
        st.warning("No recording for this scenario yet — run `python scripts/record_all.py` with an API key.")


def pace() -> None:
    if is_cached():
        time.sleep(st.session_state.get("replay_delay", 0.25))


def badge(text: str, color: str = "blue") -> str:
    """Native Streamlit markdown badge (used inside st.markdown without HTML)."""
    return f":{color}-badge[{text}]"


# ---- live progress (while an agent is running) ---------------------------------------------------
def live_logger(container):
    def on_event(ev: TraceEvent):
        tone = STATUS_TONE.get(ev.status, "blue")
        detail = f" — {escape(ev.detail[:150])}" if ev.detail else ""
        container.markdown(f'<div class="cs-line">{pill(ev.agent, tone)}<b>{escape(ev.title)}</b>'
                           f'<span style="color:#64748B">{detail}</span></div>', unsafe_allow_html=True)
        if ev.kind in {"act", "offer", "observe", "plan"}:
            pace()
    return on_event


# ---- trace timeline ---------------------------------------------------------------------------------
KIND_LABEL = {"think": "Think", "act": "Act", "observe": "Observe", "guard": "Guard", "human": "Human", "memory": "Memory",
              "plan": "Plan", "final": "Result", "user": "Request", "platform": "Platform", "offer": "Offer",
              "system": "System", "mcp": "MCP", "error": "Error"}


def render_trace(events: list[dict], key: str) -> None:
    """Each step is one card: think → act → observe (+ guards), readable without opening the code."""
    if not events:
        st.info("No trace yet.")
        return
    steps: dict[int, list[dict]] = {}
    for e in events:
        steps.setdefault(e["step"], []).append(e)
    for step, evs in steps.items():
        with st.container(border=True):
            kinds = {e["kind"] for e in evs}
            label = "think → act → observe" if {"think", "act", "observe"} <= kinds else KIND_LABEL.get(evs[0]["kind"], "")
            html(f'<div class="cs-step-head"><span class="cs-num">STEP {step}</span>'
                 f'<span class="cs-eyebrow">{escape(label)}</span><span class="cs-time">{escape(evs[0]["at"])}</span></div>')
            for i, e in enumerate(evs):
                _render_event(e, f"{key}-{step}-{i}")


def _line(kind_cls: str, label: str, body_html: str) -> None:
    html(f'<div class="cs-line"><span class="cs-k {kind_cls}">{escape(label)}</span>{body_html}</div>')


def _render_event(e: dict, key: str) -> None:
    tone = STATUS_TONE.get(e["status"], "blue")
    k = e["kind"]
    if k == "think":
        _line("think", "Think", f'<span class="cs-think">{escape(e["detail"])}</span>')
        return
    if k == "act":
        data = e.get("data") or {}
        args = data.get("args") or {}
        tool = data.get("tool") or e["title"].split("(")[0]
        chips = "".join(f'<span class="cs-code">{escape(f"{a}={v}")}</span>' for a, v in args.items() if v is not None)
        via = data.get("via")
        _line("act", "Act", pill(tool, "blue") + (pill("via MCP server", "violet") if via and via != "local" else "")
              + (f"<div style='margin:4px 0 0 70px'>{chips}</div>" if chips else ""))
        return
    if k == "observe":
        _line("observe", "Observe", pill({"ok": "ok", "warn": "check", "fail": "refused"}.get(e["status"], e["status"]), tone)
              + escape(e["detail"]))
        data = e.get("data") or {}
        if data.get("table"):
            with st.expander(f"Results the agent saw ({len(data['table'])} rows)", icon=":material/table_rows:"):
                st.dataframe(pd.DataFrame(data["table"]), hide_index=True, width="stretch")
        if data.get("chart"):
            df = pd.DataFrame(data["chart"])
            fig = go.Figure(go.Scatter(x=df["date"], y=df["median_price"], mode="lines+markers",
                                       line=dict(color="#2563EB", width=2), fill="tozeroy", fillcolor="rgba(37,99,235,.08)"))
            fig.update_layout(**{**PLOT_LAYOUT, "margin": dict(l=10, r=10, t=10, b=10)}, height=170, yaxis_title="median $")
            st.plotly_chart(fig, width="stretch", key=f"{key}-chart")
        return
    if k == "plan":
        _line("act", "Plan", f"<b>{escape(e['title'])}</b>")
        render_plan(e.get("data") or {})
        return
    if k == "final":
        _line("observe", "Result", f"<b>{escape(e['title'])}</b>")
        render_recommendation(e.get("data") or {})
        return
    if k == "memory":
        _line("think", "Memory", f"<b>{escape(e['title'])}</b> — {escape(e['detail'])}")
        data = e.get("data")
        if isinstance(data, str):
            with st.expander("What was injected into the agent's context", icon=":material/psychology:"):
                st.code(data, language=None)
        elif isinstance(data, list) and data:
            st.dataframe(pd.DataFrame(data), hide_index=True, width="stretch")
        return
    cls = {"guard": "guard", "human": "human"}.get(k, "act")
    _line(cls, KIND_LABEL.get(k, k), pill(e["agent"], tone) + f"<b>{escape(e['title'])}</b>"
          + (f" — {escape(e['detail'])}" if e["detail"] else ""))


def render_plan(plan: dict) -> None:
    if not plan:
        return
    c = plan.get("constraints", {})
    html(f'<div class="cs-line"><b>Goal:</b> {escape(plan.get("goal_summary", ""))}</div>'
         '<div class="cs-line"><span class="cs-eyebrow">Constraints</span><br>'
         + "".join(pill(f"{k.replace('_', ' ')}: {v}", "blue") for k, v in c.items() if v not in (None, "", False)) + "</div>")
    rows = [{"#": s["step"], "Action": s["action"], "Tool": s["tool"], "Why": s["why"]} for s in plan.get("steps", [])]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if plan.get("memory_applied"):
        html('<div class="cs-line"><span class="cs-eyebrow">Memory applied</span><br>'
             + "".join(pill(m, "violet") for m in plan["memory_applied"]) + "</div>")
    if plan.get("assumptions"):
        st.caption("Assumptions: " + "; ".join(plan["assumptions"]))


def render_recommendation(r: dict) -> None:
    if not r:
        return
    if r.get("status") != "recommend":
        st.warning("The agent found no listing that satisfies the hard constraints.")
        return
    kpis([("Chosen listing", r["listing_id"], "held for 15 min", "blue"),
          ("Tickets", r["quantity"], "seats together", "violet"),
          ("Total", f"${r['total_price']:,.0f}", f"${r['price_per_ticket']:,.0f} per ticket", "green")])
    callout(r["why_this_listing"], "Why this listing", "green")
    if r.get("alternatives_rejected"):
        html('<div class="cs-eyebrow" style="margin-top:6px">Why not the others</div>')
        st.dataframe(pd.DataFrame(r["alternatives_rejected"]).rename(columns={"listing_id": "Listing", "reason": "Reason"}),
                     hide_index=True, width="stretch")
    if r.get("memory_factors"):
        html('<div class="cs-line"><span class="cs-eyebrow">Memory that shaped the choice</span><br>'
             + "".join(pill(m, "violet") for m in r["memory_factors"]) + "</div>")
