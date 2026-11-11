"""Part D: the operations desk - match-postponement workflow (pre-defined, placed autonomy).

  TRIGGER (weather feed flips match to postponed)
    -> for every affected order:
       CLASSIFY (LLM node, structured output)
       -> RECOVERY RULES R1-R3, R5 (deterministic guards; may re-route or escalate)
       -> RETRIEVE POLICY (knowledge-retrieval node, BM25 over policy sections) + cite it
       -> RECOVERY RULE R4 (cited policy must govern this event/route, else re-query or escalate)
       -> CONDITIONAL BRANCH on the final route
            full_refund  <= threshold -> auto refund (monitored)
            full_refund  >  threshold -> APPROVAL GATE (human click)
            keep_for_new_date         -> tickets reissued for the new date (monitored)
            disputed                  -> dispute queue, escrow frozen (human trust agent)
            suspected_fraud           -> order frozen (auto) + account flag waits for APPROVAL GATE
            escalated                 -> human review
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import prompts, store
from .config import CLASSIFIER_MIN_CONFIDENCE, DATA, REFUND_APPROVAL_THRESHOLD
from .llm import LLMClient, json_schema_format, parse_json

ROUTES = ["full_refund", "keep_for_new_date", "disputed", "suspected_fraud"]
CLASSIFY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["route", "confidence", "attends_new_date", "language", "summary_en", "rationale"],
    "properties": {"route": {"type": "string", "enum": ROUTES}, "confidence": {"type": "number"},
                   "attends_new_date": {"type": "string", "enum": ["yes", "no", "unclear"]},
                   "language": {"type": "string"}, "summary_en": {"type": "string"},
                   "rationale": {"type": "string"}},
}
# Which policy scopes may govern a case on each route of a *weather* postponement.
ROUTE_SCOPES = {"full_refund": {"weather_postponement"}, "keep_for_new_date": {"weather_postponement"},
                "disputed": {"dispute", "all"}, "suspected_fraud": {"suspected_fraud", "all"}}
ROUTE_QUERY = {"full_refund": "refund cannot attend rescheduled new date original payment",
               "keep_for_new_date": "tickets valid rescheduled new date same seat reissued",
               "disputed": "dispute seller never transferred tickets escrow",
               "suspected_fraud": "fraud different card new account chargeback refund review"}

NODE_LABELS = {"trigger": "Trigger", "classify": "Classify (LLM)", "rules": "Recovery rules",
               "retrieve": "Retrieve policy", "policy_check": "Policy check (R4)", "branch": "Branch",
               "auto_refund": "Auto refund", "gate": "Approval gate", "reissue": "Reissue for new date",
               "dispute": "Dispute queue", "freeze": "Freeze + flag review", "escalate": "Human review"}


# ---- trigger ---------------------------------------------------------------------------------
def ingest_weather_feed() -> dict:
    ev = store.seed("events.json")[0]
    rows = store.matches()
    for m in rows:
        if m["match_id"] == ev["match_id"]:
            m["status"] = ev["new_status"]
            m["new_kickoff"] = ev["new_kickoff"]
            m["postponement_reason"] = ev["reason"]
    store.write_state("matches.json", rows)
    store.audit("weather_feed", "postpone_match", ev["match_id"], f"new kickoff {ev['new_kickoff']}", gated=False)
    return ev


def affected_orders(match_id: str) -> list[dict]:
    return [o for o in store.seed("orders.json") if o["match_id"] == match_id]


# ---- knowledge retrieval node (BM25 over policy sections) -------------------------------------
_STOP = set("the a an and or of to for in on at is are be it this that with by as if not no any from was were "
            "will can their they them our your you i we my me has have had do does did".split())


def _tok(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2 and w not in _STOP]


def policy_sections() -> list[dict]:
    out = []
    for path in sorted((DATA / "policies").glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        fm, body = raw.split("---", 2)[1], raw.split("---", 2)[2]
        meta = dict(line.split(":", 1) for line in fm.strip().splitlines())
        meta = {k.strip(): v.strip() for k, v in meta.items()}
        scopes = {s.strip() for s in meta["applies_to"].split(",")}
        for chunk in body.split("\n## ")[1:]:
            heading, _, text = chunk.partition("\n")
            sec_id = heading.split()[0]
            out.append({"policy_id": meta["policy_id"], "policy_title": meta["title"], "file": path.name,
                        "scopes": scopes, "section_id": sec_id, "heading": heading.strip(), "text": text.strip()})
    return out


def retrieve(query: str, sections: list[dict], k1: float = 1.4, b: float = 0.75) -> list[tuple[float, dict]]:
    docs = [_tok(s["heading"] + " " + s["text"]) for s in sections]
    avg = sum(map(len, docs)) / max(1, len(docs))
    df = Counter(t for d in docs for t in set(d))
    n = len(docs)
    q = _tok(query)
    scored = []
    for s, d in zip(sections, docs):
        tf = Counter(d)
        score = 0.0
        for t in q:
            if tf[t]:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / avg))
        scored.append((round(score, 3), s))
    return sorted(scored, key=lambda x: -x[0])


# ---- the workflow -----------------------------------------------------------------------------
def classify_all(llm: LLMClient, event: dict, orders: list[dict]) -> dict[str, dict]:
    m = store.match(event["match_id"])
    ev_text = (f"{m['home']} vs {m['away']} in {m['city']}, originally {event['original_kickoff']}, "
               f"rescheduled to {event['new_kickoff']} at the same venue. Reason: {event['reason']}")
    system = prompts.CLASSIFIER_SYSTEM.format(event=ev_text)

    def one(o):
        facts = {k: o[k] for k in ["order_id", "buyer_country", "account_age_days", "tickets", "amount_paid", "payment_method"]}
        resp = llm.chat(f"classify:{o['order_id']}", [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Order facts: {json.dumps(facts)}\nCustomer message: {o['message']}"}],
            response_format=json_schema_format("triage", CLASSIFY_SCHEMA), temperature=0.0, max_tokens=300)
        return o["order_id"], parse_json(resp["content"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        return dict(pool.map(one, orders))


def process_case(order: dict, cls: dict, event: dict, sections: list[dict]) -> dict:
    case = {"order_id": order["order_id"], "buyer": order["buyer"], "country": order["buyer_country"],
            "amount": order["amount_paid"], "tickets": order["tickets"], "message": order["message"],
            "classification": cls, "route_initial": cls.get("route"), "rules_fired": [], "path": ["trigger", "classify"],
            "timeline": [], "retrieval": []}

    def log(node, text, status="info"):
        case["timeline"].append({"node": NODE_LABELS.get(node, node), "text": text, "status": status})

    log("trigger", f"Match postponed ({event['reason'][:60]}…); order enters the refund-or-keep workflow.")
    log("classify", f"route={cls.get('route')} · confidence={cls.get('confidence')} · attends new date="
                    f"{cls.get('attends_new_date')} · language={cls.get('language')} — {cls.get('rationale')}")
    route = cls.get("route")
    escalate_reason = None

    # ---- recovery rules on the classification -------------------------------------------------
    case["path"].append("rules")
    conf = float(cls.get("confidence") or 0)
    attends = cls.get("attends_new_date")
    if order["account_age_days"] < 7 and (order["tickets"] >= 8 or "chargeback" in order["message"].lower()) \
            and route != "suspected_fraud":
        case["rules_fired"].append("R5 fraud signals (new account + bulk/chargeback) → re-route to suspected_fraud")
        log("rules", f"R5: account {order['account_age_days']} days old with {order['tickets']} tickets"
                     f"{' and a chargeback' if 'chargeback' in order['message'].lower() else ''}; classifier said "
                     f"'{route}' → re-routed to suspected_fraud.", "warn")
        route = "suspected_fraud"
    elif route == "keep_for_new_date" and attends == "no":
        case["rules_fired"].append("R2 contradiction: 'keep' but cannot attend → re-route to full_refund")
        log("rules", "R2: the classifier routed to KEEP but its own extracted fact says the customer cannot attend "
                     "the new date. Mis-route caught → re-routed to full_refund.", "warn")
        route = "full_refund"
    elif route == "full_refund" and attends == "yes":
        escalate_reason = "R3 contradiction: refund requested but customer can attend"
    elif route == "keep_for_new_date" and attends == "unclear":
        escalate_reason = "R2b: 'keep' without a clear statement that the customer can attend"
    if conf < CLASSIFIER_MIN_CONFIDENCE and not escalate_reason and route not in {"suspected_fraud"}:
        escalate_reason = f"R1 low confidence ({conf:.2f} < {CLASSIFIER_MIN_CONFIDENCE})"
    if escalate_reason:
        case["rules_fired"].append(escalate_reason + " → escalate")
        log("rules", escalate_reason + " → escalated to a human.", "warn")
    elif not case["rules_fired"]:
        log("rules", "No recovery rule fired.", "ok")

    # ---- knowledge retrieval + R4 -------------------------------------------------------------
    case["path"].append("retrieve")
    query = cls.get("summary_en") or order["message"]
    top_score, top = retrieve(query, sections)[0]
    case["retrieval"].append({"attempt": 1, "query": query, "hit": f"{top['policy_id']} §{top['section_id']}",
                              "scope": ", ".join(sorted(top["scopes"])), "score": top_score})
    log("retrieve", f"Attempt 1 (case summary) → {top['policy_id']} §{top['section_id']} '{top['heading']}' (score {top_score}).")
    case["path"].append("policy_check")
    allowed = ROUTE_SCOPES.get(route, {"weather_postponement"})
    attempt1_scopes = set(top["scopes"])
    if not (top["scopes"] & allowed):
        case["rules_fired"].append(f"R4 policy mismatch: {top['policy_id']} governs {', '.join(sorted(top['scopes']))}, "
                                   f"not this {event['type']} / {route} case → re-query")
        log("policy_check", f"R4: retrieved policy governs '{', '.join(sorted(top['scopes']))}', but this case is a "
                            f"{event['type']} on route '{route}'. Retrieval miss caught → re-querying within allowed scope.",
            "warn")
        filtered = [s for s in sections if s["scopes"] & allowed]
        q2 = query + " " + ROUTE_QUERY.get(route, "")
        if filtered:
            top_score, top = retrieve(q2, filtered)[0]
            case["retrieval"].append({"attempt": 2, "query": q2, "hit": f"{top['policy_id']} §{top['section_id']}",
                                      "scope": ", ".join(sorted(top["scopes"])), "score": top_score})
            log("retrieve", f"Attempt 2 (scoped to {', '.join(sorted(allowed))}) → {top['policy_id']} §{top['section_id']} "
                            f"'{top['heading']}' — citation recovered.", "ok")
            if route in {"full_refund", "keep_for_new_date"} and not escalate_reason:
                # The case was understood in terms of a different event than the one that happened, so the
                # classifier's premise is suspect: do not auto-execute, hand it to a human.
                escalate_reason = ("R4 premise mismatch: the customer's request is framed around a different event "
                                   f"({', '.join(sorted(attempt1_scopes))}) than the one that happened")
        else:
            escalate_reason = escalate_reason or "R4: no governing policy found"
    else:
        log("policy_check", f"Cited policy governs this case ({', '.join(sorted(top['scopes']))}).", "ok")
    case["policy"] = {"policy_id": top["policy_id"], "section": top["section_id"], "heading": top["heading"],
                      "title": top["policy_title"], "file": top["file"], "excerpt": top["text"]}

    if escalate_reason and not any(escalate_reason.split(":")[0] in r for r in case["rules_fired"]):
        case["rules_fired"].append(escalate_reason + " → escalate")
        log("policy_check", escalate_reason + " → escalated to a human instead of auto-executing.", "warn")

    # ---- conditional branch -------------------------------------------------------------------
    case["route_final"] = "escalated" if escalate_reason else route
    case["path"].append("branch")
    amt = order["amount_paid"]
    if escalate_reason:
        case["path"].append("escalate")
        case["status"] = "escalated"
        case["needs"] = "human review"
        log("escalate", "Waiting for a human to decide.", "warn")
    elif route == "full_refund" and amt <= REFUND_APPROVAL_THRESHOLD:
        case["path"].append("auto_refund")
        _record_refund(order, "auto (monitored)", case["policy"])
        case["status"] = "auto_refunded"
        log("auto_refund", f"${amt:,.0f} ≤ ${REFUND_APPROVAL_THRESHOLD:,.0f} threshold → refunded automatically to the "
                           "original payment method; visible in the monitor.", "ok")
    elif route == "full_refund":
        case["path"].append("gate")
        case["status"] = "awaiting_approval"
        case["needs"] = "refund approval"
        log("gate", f"${amt:,.0f} > ${REFUND_APPROVAL_THRESHOLD:,.0f} threshold → PAUSED for explicit human approval.", "warn")
    elif route == "keep_for_new_date":
        case["path"].append("reissue")
        case["status"] = "reissued_for_new_date"
        log("reissue", f"Mobile tickets reissued for {event['new_kickoff']} (same seat, reversible).", "ok")
        store.audit("ops_workflow", "reissue_tickets", order["order_id"], event["new_kickoff"], gated=False)
    elif route == "disputed":
        case["path"].append("dispute")
        case["status"] = "dispute_queue"
        case["needs"] = "trust agent"
        log("dispute", "Escrow frozen; moved to the dispute queue for a trust agent.", "warn")
        store.audit("ops_workflow", "move_to_dispute_queue", order["order_id"], "escrow frozen", gated=False)
    elif route == "suspected_fraud":
        case["path"].append("freeze")
        case["status"] = "frozen_flag_pending"
        case["needs"] = "account-flag approval"
        log("freeze", "Order frozen automatically (reversible). Account flag proposed — requires human approval.", "warn")
        store.audit("ops_workflow", "freeze_order", order["order_id"], "fraud signals", gated=False)
    case["decided_by"] = None
    return case


def run_workflow(llm: LLMClient, progress=None) -> dict:
    event = ingest_weather_feed()
    orders = affected_orders(event["match_id"])
    if progress:
        progress(f"Weather feed: {event['match_id']} postponed → {len(orders)} affected orders. Classifying…")
    cls = classify_all(llm, event, orders)
    sections = policy_sections()
    cases = {}
    for o in orders:
        cases[o["order_id"]] = process_case(o, cls[o["order_id"]], event, sections)
        if progress:
            c = cases[o["order_id"]]
            progress(f"{o['order_id']}: {c['route_final']} → {c['status']}")
    store.write_state("ops_cases.json", {"event": event, "cases": cases,
                                         "ran_at": datetime.now().isoformat(timespec="seconds")})
    return {"event": event, "cases": cases}


# ---- human actions from the UI ----------------------------------------------------------------
def _record_refund(order: dict, control: str, policy: dict) -> None:
    store.append_state("refunds.json", {"order_id": order["order_id"], "amount": order["amount_paid"],
                                        "to": order["payment_method"], "control": control,
                                        "policy": f"{policy['policy_id']} §{policy['section']}",
                                        "at": datetime.now().isoformat(timespec="seconds"), "note": "MOCK refund"})
    store.audit("ops_workflow" if control.startswith("auto") else "human (ops)", "issue_refund", order["order_id"],
                f"${order['amount_paid']} to {order['payment_method']}", gated=not control.startswith("auto"))


def human_action(order_id: str, action: str) -> dict:
    data = store.state("ops_cases.json", {})
    case = data["cases"][order_id]
    order = next(o for o in store.seed("orders.json") if o["order_id"] == order_id)
    note = {"approve_refund": "Refund approved by a human", "reject_refund": "Refund rejected by a human",
            "approve_flag": "Account flag approved by a human trust agent",
            "dismiss_flag": "Fraud flag dismissed by a human; order unfrozen",
            "escalate": "Escalated manually from the monitor",
            "resolve_refund": "Human resolved escalation: refund", "resolve_keep": "Human resolved escalation: keep"}[action]
    if action in {"approve_refund", "resolve_refund"}:
        _record_refund(order, "human-approved", case["policy"])
        case["status"] = "refunded_after_approval"
    elif action == "reject_refund":
        case["status"] = "refund_rejected"
        store.audit("human (ops)", "reject_refund", order_id, "", gated=True)
    elif action == "approve_flag":
        store.append_state("account_flags.json", {"order_id": order_id, "buyer": order["buyer"],
                                                  "reason": "; ".join(case["rules_fired"]) or case["classification"].get("rationale"),
                                                  "at": datetime.now().isoformat(timespec="seconds")})
        store.audit("human (trust)", "flag_account", order["buyer"], order_id, gated=True)
        case["status"] = "account_flagged"
    elif action == "dismiss_flag":
        case["status"] = "flag_dismissed"
        store.audit("human (trust)", "dismiss_flag", order_id, "", gated=True)
    elif action == "escalate":
        case["status"] = "escalated"
        case["route_final"] = "escalated"
        case["path"].append("escalate")
        store.audit("human (ops)", "escalate", order_id, "manual escalate control", gated=True)
    elif action == "resolve_keep":
        case["status"] = "reissued_for_new_date"
        store.audit("human (ops)", "reissue_tickets", order_id, "after escalation", gated=True)
    case["decided_by"] = "human"
    case["timeline"].append({"node": "Human", "text": note, "status": "ok"})
    store.write_state("ops_cases.json", data)
    return case
