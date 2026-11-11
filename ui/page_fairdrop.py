"""Part E UI: the Fair-Drop desk (innovation feature for tournament organizers)."""
from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cupswap import fairdrop, store
from cupswap.llm import CacheMiss
from cupswap.scenarios import FAIRDROP
from ui.common import PLOT_LAYOUT, get_llm, is_cached, pace, recording_caption
from ui.style import callout, hero, html, kpis, pill, progress_states, section, stepper

STEPS = ["Window closes", "Integrity filter", "Need assessment", "Seeded lottery", "Fairness audit", "Organizer approval"]


def _share_chart(res: dict) -> go.Figure:
    reqs = res["drop"]["requests"]
    fc = fairdrop.channel_stats(reqs, res["fcfs"])
    fd = fairdrop.channel_stats(reqs, res["winners"])
    fig = go.Figure()
    for ch, color, name in [("agent_api", "#94A3B8", "Requests via AI agents / bots"),
                            ("web_form", "#059669", "Fans without agents (web form)")]:
        fig.add_trace(go.Bar(y=["First-come-first-served", "Fair-Drop"], x=[fc[ch]["tickets"], fd[ch]["tickets"]],
                             name=name, marker_color=color, orientation="h", text=[fc[ch]["tickets"], fd[ch]["tickets"]],
                             textposition="inside", insidetextfont=dict(color="white", size=13)))
    fig.update_layout(**PLOT_LAYOUT, barmode="stack", height=230, xaxis_title="Tickets allocated",
                      legend=dict(orientation="h", y=1.25, x=0))
    return fig


def page() -> None:
    hero("Part E · innovation feature — for tournament organizers", "Fair-Drop Desk",
         "When face-value tickets are released for a marquee match, agents submit in milliseconds and first-come-first-"
         "served hands them everything. Fair-Drop batches the window, holds linked accounts for review, has an LLM "
         "assess need from verified facts only, draws a published-seed lottery within tiers, has a second agent audit "
         "the result — and lets a human organizer approve before anything is allocated.",
         ["Hybrid workflow", "Evidence-grounded LLM assessment", "Prompt-injection defense", "LLM-as-judge audit",
          "Organizer approval gate"])
    ss = st.session_state
    res = ss.get("fairdrop")
    drop = fairdrop.load_drop()
    m = store.match(drop["match_id"])
    if not res:
        states = progress_states(len(STEPS), 0)
    else:
        states = progress_states(len(STEPS), {"awaiting_organizer_approval": 5, "approved": 6}.get(res["status"], 5),
                                 failed=5 if res["status"] == "rejected" else None)
    stepper(STEPS, states)

    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            n_agent = sum(r["channel"] == "agent_api" for r in drop["requests"])
            n_web = sum(r["channel"] == "web_form" for r in drop["requests"])
            html(f'<div class="cs-eyebrow">Organizer release · {escape(drop["drop_id"])}</div>'
                 f'<div class="cs-line" style="font-size:1.05rem"><b>{escape(m["home"])} vs {escape(m["away"])}</b> · '
                 f'{escape(m["stage"])} · {escape(m["city"])}</div>'
                 f'<div class="cs-line">{pill(str(drop["tickets_released"]) + " tickets", "blue")}'
                 f'{pill("face value $" + str(drop["face_value_per_ticket"]), "gray")}'
                 f'{pill("window " + drop["window_opens"][11:16] + "–" + drop["window_closes"][11:16], "gray")}'
                 f'{pill("max " + str(drop["max_tickets_per_request"]) + " per request", "gray")}</div>'
                 f'<div class="cs-line" style="color:#475569">{len(drop["requests"])} requests: {n_agent} via agent API '
                 f'(all within 2.2 s) and {n_web} via the web form (over 10 minutes).</div>')
            if is_cached():
                recording_caption("fairdrop_r16dal")
            run = st.button("Close the window & run Fair-Drop", icon=":material/how_to_vote:", type="primary")
    with right:
        callout("Integrity filter, need assessment and lottery → automatic and fully logged · Fairness audit → a second "
                "agent · Allocation → organizer approves · Linked accounts → held for trust review, never auto-banned",
                "Placed autonomy", "blue")

    with st.expander("All incoming requests (arrival order)", icon=":material/inbox:"):
        st.dataframe(pd.DataFrame([{"Request": r["request_id"], "Channel": r["channel"], "Arrived after (s)": r["arrival_offset_s"],
                                    "Qty": r["quantity"], "Statement (untrusted)": r["statement"]}
                                   for r in sorted(drop["requests"], key=lambda r: r["arrival_offset_s"])]),
                     hide_index=True, width="stretch")

    if run:
        llm = get_llm("fairdrop_r16dal" if is_cached() else "fairdrop_r16dal_live", FAIRDROP["fairdrop_r16dal"])
        if llm:
            with st.status("Fair-Drop pipeline running…", expanded=True) as box:
                def progress(msg):
                    box.write(msg)
                    pace()
                try:
                    ss["fairdrop"] = fairdrop.run(llm, progress=progress)
                except CacheMiss as e:
                    st.error(str(e))
                    return
                box.update(label="Proposed allocation ready — awaiting organizer approval", state="complete")
            st.rerun()

    if not res:
        return

    held_ids = {h["request_id"] for h in res["held"]}
    fc_ring = sum(r["allocated"] for r in res["fcfs"] if r["request_id"] in held_ids)
    web_tix = sum(w["allocated"] for w in res["winners"] if w["channel"] == "web_form")
    injections = sum(1 for a in res["assessed"] if a["assessment"].get("injection_detected"))
    corrected = sum(1 for a in res["assessed"] if a["grounding_guards"] and not a["assessment"].get("injection_detected"))
    total = res["drop"]["tickets_released"]
    kpis([("FCFS → linked-account ring", f"{fc_ring} / {total}", "tickets a bot ring would get", "red"),
          ("Fair-Drop → fans without agents", f"{web_tix} / {total}", "web-form requests served", "green"),
          ("Held for trust review", len(res["held"]), "linked accounts (shared payment)", "orange"),
          ("Guard corrections", corrected, f"plus {injections} prompt injection(s) blocked", "violet")])

    # ---------------- organizer gate (top) ----------------
    if res["status"] == "awaiting_organizer_approval":
        with st.container(border=True):
            html(f'<div class="cs-eyebrow">Organizer decision</div><div class="cs-line" style="font-size:1.05rem">Allocate '
                 f'<b>{sum(w["allocated"] for w in res["winners"])} tickets</b> to <b>{len(res["winners"])} requests</b> and '
                 f'send {len(res["held"])} linked accounts to trust review? Nothing is allocated until you approve.</div>')
            x, y, _ = st.columns([2, 2, 3])
            if x.button("Approve allocation", icon=":material/verified:", type="primary", width="stretch"):
                fairdrop.organizer_decision(res, True)
                st.rerun()
            if y.button("Send back for revision", icon=":material/undo:", width="stretch"):
                fairdrop.organizer_decision(res, False)
                st.rerun()
    elif res["status"] == "approved":
        st.success("Allocation approved by the organizer and written to state/fairdrop_allocations.json (mock).",
                   icon=":material/check_circle:")
    else:
        st.warning("Allocation sent back for revision; nothing was allocated.")

    section("Who gets the tickets", f"First-come-first-served vs Fair-Drop · lottery seed {res['seed']} is published so "
                                    f"anyone can re-run the draw")
    with st.container(border=True):
        st.plotly_chart(_share_chart(res), width="stretch")

    a, b = st.columns([2, 3], gap="large")
    with a:
        section("Integrity filter", "Deterministic — held, never auto-banned")
        st.dataframe(pd.DataFrame([{"Request": h["request_id"], "Account": h["account"], "Qty": h["quantity"],
                                    "Held because": "; ".join(h["integrity_notes"])} for h in res["held"]]),
                     hide_index=True, width="stretch")
    with b:
        audit = res["judge"]["audit"]
        verdict = audit.get("verdict", "?")
        section("Fairness judge", "A second agent audits the proposal before the organizer sees the button")
        with st.container(border=True):
            html(f'<div class="cs-line">Verdict {pill(verdict.replace("_", " "), "green" if verdict == "approve" else "orange")}</div>'
                 + "".join(f'<div class="cs-line">{pill(f["status"], "green" if f["status"] == "pass" else "orange")}'
                           f'<b>{escape(f["check"])}</b> — {escape(f["detail"])}</div>' for f in audit.get("findings", []))
                 + f'<div class="cs-line" style="color:#475569;font-size:.84rem"><i>{escape(audit.get("recommendation", ""))}</i></div>')

    section("Need assessment", "LLM tier from verified facts only → code guard re-derives the tier from the cited evidence")
    rows = []
    for r in sorted(res["assessed"], key=lambda x: (x["tier_final"], x["request_id"])):
        asm = r["assessment"]
        f = r["verified_facts"]
        rows.append({"Request": r["request_id"], "Channel": r["channel"], "Qty": r["quantity"],
                     "Verified facts": f"supporter {f['supporter_of'] or '—'} · attended {f['attended_team_match']} · "
                                       f"accessible {f['accessibility_verified']} · home {f['home_city']}",
                     "LLM tier": asm.get("tier"), "Final tier": r["tier_final"],
                     "Evidence cited": ", ".join(asm.get("evidence", [])) or "—",
                     "Unverified claims ignored": "; ".join(asm.get("unverified_claims", [])) or "—",
                     "Injection": "detected" if asm.get("injection_detected") else "",
                     "Guards": "; ".join(r["grounding_guards"] + r["integrity_notes"]) or "—"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("Assessor rationales", icon=":material/psychology:"):
        for r in sorted(res["assessed"], key=lambda x: x["request_id"]):
            html(f'<div class="cs-line"><b>{escape(r["request_id"])}</b> {pill(r["channel"], "gray")}'
                 f'{escape(str(r["assessment"].get("rationale")))}<br><span style="color:#64748B;font-size:.8rem">'
                 f'statement: “{escape(r["statement"])}”</span></div>')

    w1, w2 = st.columns(2, gap="large")
    with w1:
        section("Proposed winners", "Tier order, random within tier")
        st.dataframe(pd.DataFrame([{"Draw": w["draw_order"], "Request": w["request_id"], "Channel": w["channel"],
                                    "Tier": w["tier_final"], "Tickets": w["allocated"],
                                    "Evidence": ", ".join(w["assessment"].get("evidence", []))} for w in res["winners"]]),
                     hide_index=True, width="stretch")
    with w2:
        section("Waitlist", "Next in line if a winner cancels")
        st.dataframe(pd.DataFrame([{"Request": w["request_id"], "Channel": w["channel"], "Tier": w["tier_final"],
                                    "Qty": w["quantity"]} for w in res["waitlist"]]), hide_index=True, width="stretch")
