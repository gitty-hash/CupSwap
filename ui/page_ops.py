"""Part D UI: the operations desk (postponement workflow + approval gate + human-on-the-loop monitor)."""
from __future__ import annotations

from collections import Counter
from html import escape

import pandas as pd
import streamlit as st

from cupswap import operations, store
from cupswap.config import CLASSIFIER_MIN_CONFIDENCE, OPS_CLOCK, REFUND_APPROVAL_THRESHOLD
from cupswap.llm import CacheMiss
from cupswap.scenarios import OPS
from ui.common import get_llm, is_cached, pace, recording_caption
from ui.style import callout, hero, html, kpis, pill, progress_states, section, stepper

STEPS = ["Weather feed", "Classify (LLM)", "Recovery rules", "Cite policy", "Route", "Human gate", "Monitor"]
STATUS_TEXT = {
    "auto_refunded": ("Refunded automatically", "green"), "awaiting_approval": ("Awaiting approval", "orange"),
    "refunded_after_approval": ("Refunded — human-approved", "green"), "refund_rejected": ("Refund rejected", "red"),
    "reissued_for_new_date": ("Kept — reissued for new date", "green"), "dispute_queue": ("Dispute queue", "violet"),
    "frozen_flag_pending": ("Frozen — flag awaits approval", "orange"), "account_flagged": ("Account flagged", "red"),
    "flag_dismissed": ("Flag dismissed", "gray"), "escalated": ("Escalated to human", "orange"),
}
PENDING = {"awaiting_approval", "frozen_flag_pending", "escalated"}


def _diagram(cases: dict) -> str:
    cnt = Counter()
    for c in cases.values():
        for a, b in zip(c["path"], c["path"][1:]):
            cnt[(a, b)] += 1
    nodes = {
        "trigger": ("Trigger\nmatch postponed", "#EFF6FF", "#2563EB"), "classify": ("Classify\nLLM node", "#F5F3FF", "#7C3AED"),
        "rules": ("Recovery rules\nR1 R2 R3 R5", "#FFFBEB", "#D97706"), "retrieve": ("Retrieve policy\nknowledge node", "#ECFDF5", "#059669"),
        "policy_check": ("Policy check R4\ncite or re-query", "#FFFBEB", "#D97706"), "branch": ("Conditional\nbranch", "#F1F5F9", "#475569"),
        "auto_refund": (f"Auto refund\n≤ ${REFUND_APPROVAL_THRESHOLD:,.0f} · monitored", "#ECFDF5", "#059669"),
        "gate": (f"APPROVAL GATE\n> ${REFUND_APPROVAL_THRESHOLD:,.0f}", "#FEF2F2", "#DC2626"),
        "reissue": ("Reissue for\nnew date", "#ECFDF5", "#059669"), "dispute": ("Dispute queue\ntrust agent", "#F5F3FF", "#7C3AED"),
        "freeze": ("Freeze order +\nflag approval", "#FEF2F2", "#DC2626"), "escalate": ("Human review\nescalated", "#FEF2F2", "#DC2626"),
    }
    lines = ['digraph G { rankdir=LR; bgcolor="transparent"; nodesep=0.25; ranksep=0.45;',
             'node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, penwidth=1.4, margin="0.15,0.07"];',
             'edge [color="#94A3B8", fontname="Helvetica", fontsize=9, fontcolor="#334155", arrowsize=0.7];']
    for k, (label, fill, stroke) in nodes.items():
        lab = label.replace("\n", "\\n")
        lines.append(f'{k} [label="{lab}", fillcolor="{fill}", color="{stroke}", fontcolor="#0F172A"];')
    for (a, b), n in cnt.items():
        lines.append(f'{a} -> {b} [label=" {n} ", penwidth={1 + min(n, 14) / 5:.1f}];')
    lines.append("}")
    return "\n".join(lines)


def page() -> None:
    hero("Part D · Chapter 6 — pre-defined workflow", "Operations Desk",
         "A storm postpones a group-stage match in Miami. Every affected order flows through a fixed workflow: an LLM "
         "classifies it, recovery rules check the classifier, a retrieval node cites the governing policy, and a "
         "conditional branch routes it. Large refunds wait for a human; everything else is monitored.",
         ["Conditional orchestration", "Knowledge retrieval + citation", f"Approval gate > ${REFUND_APPROVAL_THRESHOLD:,.0f}",
          "Human-on-the-loop monitor", "Failure + recovery rules"])
    ss = st.session_state
    ev = store.seed("events.json")[0]
    m = store.match(ev["match_id"])
    data = store.state("ops_cases.json", {}) or {}
    cases = data.get("cases") or {}
    pending = [c for c in cases.values() if c["status"] in PENDING]
    if not cases:
        states = progress_states(len(STEPS), 0)
    else:
        states = progress_states(len(STEPS), 5 if pending else 6)
        if not pending:
            states[-1] = "active"
    stepper(STEPS, states)

    left, right = st.columns([3, 2], gap="large")
    with left:
        with st.container(border=True):
            status_tone = "orange" if m["status"] == "postponed" else "blue"
            html(f'<div class="cs-eyebrow">Event feed · {escape(OPS_CLOCK.replace("T", " "))}</div>'
                 f'<div class="cs-line" style="font-size:1.05rem"><b>{escape(m["home"])} vs {escape(m["away"])}</b> · '
                 f'{escape(m["stage"])} · {escape(m["city"])} {pill("status: " + m["status"], status_tone)}</div>'
                 f'<div class="cs-line" style="color:#475569">{escape(ev["reason"])}</div>'
                 f'<div class="cs-line">{pill("original " + ev["original_kickoff"].replace("T", " "), "gray")} → '
                 f'{pill("new " + ev["new_kickoff"].replace("T", " "), "blue")}</div>')
            if is_cached():
                recording_caption("ops_postponement")
            run = st.button("Ingest weather feed & run the refund-or-keep workflow", icon=":material/thunderstorm:",
                            type="primary")
    with right:
        callout(f"Refunds above ${REFUND_APPROVAL_THRESHOLD:,.0f} pause for an explicit human click; refunds at or below "
                f"it pay out automatically and still appear in the monitor. Classifier confidence below "
                f"{CLASSIFIER_MIN_CONFIDENCE} escalates. Account flags always need a human.", "Placed autonomy", "orange")
        callout("R1 low confidence → human · R2 'keep' but cannot attend → refund · R3 refund but can attend → human · "
                "R4 cited policy doesn't govern this event → re-query, then human · R5 fraud signals → fraud route",
                "Recovery rules", "violet")

    if run:
        llm = get_llm("ops_postponement" if is_cached() else "ops_postponement_live", OPS["ops_postponement"])
        if llm:
            store.reset_files(["matches.json", "refunds.json", "ops_cases.json", "account_flags.json"])
            with st.status("Workflow running…", expanded=True) as box:
                def progress(msg):
                    box.write(msg)
                    pace()
                try:
                    operations.run_workflow(llm, progress=progress)
                except CacheMiss as e:
                    st.error(str(e))
                    return
                box.update(label="Workflow complete — cases are in the monitor", state="complete")
            ss.pop("ops_selected", None)
            st.rerun()

    if not cases:
        callout("Click the button to flip the match to postponed; every affected order enters the workflow.",
                "Ready", "blue")
        return

    refunded = sum(r["amount"] for r in store.state("refunds.json", []))
    recovered = sum(1 for c in cases.values() if c["rules_fired"])
    kpis([("Affected orders", len(cases), "entered the workflow", "blue"),
          ("Waiting for a human", len(pending), "approvals · flags · escalations", "orange" if pending else "green"),
          ("Refunded so far", f"${refunded:,.0f}", "mock ledger", "green"),
          ("Caught by recovery rules", recovered, "re-routed, re-queried or escalated", "violet")])

    section("Workflow", "Edge labels show how many cases took each path")
    with st.container(border=True):
        st.graphviz_chart(_diagram(cases), width="stretch")

    # ---------------- approval gate ----------------
    section(f"Approval queue ({len(pending)})", "High-stakes or ambiguous cases — nothing here moves without your click")
    if not pending:
        st.success("Nothing is waiting for a human.", icon=":material/task_alt:")
    for c in pending:
        with st.container(border=True):
            a, b = st.columns([4, 2])
            label, tone = STATUS_TEXT[c["status"]]
            with a:
                html(f'<div class="cs-line" style="font-size:1rem"><b>{escape(c["order_id"])}</b> · {escape(c["buyer"])} '
                     f'({escape(c["country"])}) · <b>${c["amount"]:,.0f}</b> {pill(label, tone)}</div>'
                     f'<div class="cs-line" style="color:#475569">“{escape(c["message"])}”</div>'
                     f'<div class="cs-line" style="font-size:.8rem;color:#64748B">{escape(c["classification"].get("summary_en", ""))} · '
                     f'cites {escape(c["policy"]["policy_id"])} §{escape(c["policy"]["section"])}</div>'
                     + "".join(pill(r.split(" → ")[0][:70], "violet") for r in c["rules_fired"]))
            with b:
                if c["status"] == "awaiting_approval":
                    if st.button(f"Approve ${c['amount']:,.0f} refund", key=f"ap-{c['order_id']}", type="primary",
                                 icon=":material/verified:", width="stretch"):
                        operations.human_action(c["order_id"], "approve_refund"); st.rerun()
                    if st.button("Reject refund", key=f"rj-{c['order_id']}", icon=":material/block:", width="stretch"):
                        operations.human_action(c["order_id"], "reject_refund"); st.rerun()
                elif c["status"] == "frozen_flag_pending":
                    if st.button("Approve account flag", key=f"fl-{c['order_id']}", type="primary", icon=":material/flag:",
                                 width="stretch"):
                        operations.human_action(c["order_id"], "approve_flag"); st.rerun()
                    if st.button("Dismiss flag & unfreeze", key=f"df-{c['order_id']}", icon=":material/lock_open:",
                                 width="stretch"):
                        operations.human_action(c["order_id"], "dismiss_flag"); st.rerun()
                elif c["status"] == "escalated":
                    if st.button("Resolve: refund", key=f"rr-{c['order_id']}", type="primary", icon=":material/payments:",
                                 width="stretch"):
                        operations.human_action(c["order_id"], "resolve_refund"); st.rerun()
                    if st.button("Resolve: keep for new date", key=f"rk-{c['order_id']}", icon=":material/event:",
                                 width="stretch"):
                        operations.human_action(c["order_id"], "resolve_keep"); st.rerun()

    # ---------------- monitor ----------------
    section("Human-on-the-loop monitor", "Every case, including the automatic ones — tick 'Escalate' to pull any case to a human")
    rows = []
    for c in cases.values():
        rows.append({"Order": c["order_id"], "Fan": f"{c['buyer']} ({c['country']})", "Amount $": c["amount"],
                     "Status": STATUS_TEXT.get(c["status"], (c["status"],))[0],
                     "Route taken": " → ".join(operations.NODE_LABELS.get(p, p) for p in c["path"][1:]),
                     "Classifier": f"{c['route_initial']} ({c['classification'].get('confidence')})",
                     "Final route": c["route_final"],
                     "Cited policy": f"{c['policy']['policy_id']} §{c['policy']['section']} — {c['policy']['heading']}",
                     "Rules fired": "; ".join(r.split(" → ")[0] for r in c["rules_fired"]) or "—",
                     "Escalate": False})
    df = pd.DataFrame(rows)
    edited = st.data_editor(df, hide_index=True, width="stretch", key="ops_monitor",
                            disabled=[col for col in df.columns if col != "Escalate"],
                            column_config={"Escalate": st.column_config.CheckboxColumn("Escalate", help="Send to a human"),
                                           "Amount $": st.column_config.NumberColumn(format="$%d")})
    to_escalate = [r["Order"] for _, r in edited.iterrows() if r["Escalate"]]
    if st.button(f"Escalate selected ({len(to_escalate)})", icon=":material/upgrade:", disabled=not to_escalate):
        for oid in to_escalate:
            operations.human_action(oid, "escalate")
        st.rerun()

    # ---------------- case inspector ----------------
    section("Case inspector", "Open any case to see its full path, the classifier's reasoning and the cited policy text")
    oid = st.selectbox("Order", list(cases), key="ops_selected", label_visibility="collapsed",
                       format_func=lambda k: f"{k} — {cases[k]['buyer']} — {cases[k]['route_final']}")
    c = cases[oid]
    a, b = st.columns([3, 2], gap="large")
    with a:
        with st.container(border=True):
            cl = c["classification"]
            html(f'<div class="cs-eyebrow">Customer message · {escape(str(cl.get("language")))}</div>'
                 f'<div class="cs-line">“{escape(c["message"])}”</div>'
                 f'<div class="cs-eyebrow" style="margin-top:8px">Classifier (LLM)</div>'
                 f'<div class="cs-line">{pill(c["route_initial"], "violet")}{pill("confidence " + str(cl.get("confidence")), "gray")}'
                 f'{pill("attends new date: " + str(cl.get("attends_new_date")), "gray")}</div>'
                 f'<div class="cs-line cs-think">{escape(str(cl.get("rationale")))}</div>'
                 '<div class="cs-eyebrow" style="margin-top:8px">Path through the workflow</div>')
            for t in c["timeline"]:
                tone = {"ok": "green", "warn": "orange"}.get(t["status"], "blue")
                html(f'<div class="cs-line">{pill(t["node"], tone)}{escape(t["text"])}</div>')
    with b:
        p = c["policy"]
        with st.container(border=True):
            html(f'<div class="cs-eyebrow">Cited policy</div><div class="cs-line"><b>{escape(p["title"])}</b> — '
                 f'§{escape(p["section"])} {escape(p["heading"].split(" ", 1)[-1])}</div>'
                 f'<div class="cs-line" style="color:#475569;font-size:.84rem">{escape(p["excerpt"])}</div>'
                 f'<div style="font-size:.74rem;color:#94A3B8">source: data/policies/{escape(p["file"])}</div>')
        if c["retrieval"]:
            html('<div class="cs-eyebrow" style="margin-top:8px">Retrieval attempts</div>')
            st.dataframe(pd.DataFrame(c["retrieval"]), hide_index=True, width="stretch")
