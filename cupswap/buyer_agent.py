"""Part B: the buyer agent (Chapter 5 anatomy).

plan (LLM, structured)  ->  HUMAN approves plan  ->  ReAct loop with function calling (capped)
->  HUMAN approves or declines the purchase  ->  memory update (deterministic + LLM reflection)
"""
from __future__ import annotations

import json
import uuid

from . import memory, prompts, store
from .buyer_tools import BuyerSession, args_for_display, execute_purchase, release_hold, schema_list
from .config import BUYER_CLOCK, BUYER_MAX_STEPS
from .llm import CacheMiss, LLMClient, assistant_message, json_schema_format, parse_json
from .trace import Trace

AGENT = "Buyer agent"

PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["goal_summary", "constraints", "steps", "memory_applied", "assumptions"],
    "properties": {
        "goal_summary": {"type": "string"},
        "constraints": {
            "type": "object", "additionalProperties": False,
            "required": ["quantity", "max_total_budget", "city", "stage", "seats_together"],
            "properties": {
                "quantity": {"type": "integer"},
                "max_total_budget": {"type": ["number", "null"]},
                "city": {"type": ["string", "null"]},
                "stage": {"type": ["string", "null"]},
                "seats_together": {"type": "boolean"},
            }},
        "steps": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["step", "action", "tool", "why"],
            "properties": {"step": {"type": "integer"}, "action": {"type": "string"},
                           "tool": {"type": "string", "enum": ["search_listings", "check_match_status",
                                    "get_price_history", "get_seller_rating", "place_hold",
                                    "submit_recommendation", "none"]},
                           "why": {"type": "string"}}}},
        "memory_applied": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
    },
}

REFLECT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["notes_to_add", "typical_max_per_ticket", "summary"],
    "properties": {"notes_to_add": {"type": "array", "items": {"type": "string"}},
                   "typical_max_per_ticket": {"type": ["number", "null"]},
                   "summary": {"type": "string"}},
}


# ---------------------------------------------------------------------------------------------
def draft_plan(llm: LLMClient, profile: dict, goal: str, trace: Trace, feedback: str | None = None,
               previous: dict | None = None, version: int = 1) -> dict:
    trace.next_step()
    if version == 1:
        trace.add("user", "Human", "Goal delegated to the buyer agent", goal)
        trace.add("memory", AGENT, "Long-term memory loaded into context",
                  f"Preference store for {profile['display_name']} injected into the system prompt.",
                  data=memory.context_block(profile))
    msgs = [{"role": "system", "content": prompts.BUYER_PLAN_SYSTEM.format(
                clock=BUYER_CLOCK, memory=memory.context_block(profile))},
            {"role": "user", "content": f"Fan request: {goal}\n(List at least two concrete memory items in "
                                        f"memory_applied.)"}]
    if feedback and previous:
        msgs += [{"role": "assistant", "content": json.dumps(previous)},
                 {"role": "user", "content": f"The human asked for changes to the plan: {feedback}. Revise it."}]
        trace.add("human", "Human", "Plan revision requested", feedback, status="warn")
    resp = llm.chat(f"plan:v{version}", msgs, response_format=json_schema_format("buyer_plan", PLAN_SCHEMA))
    plan = parse_json(resp["content"])
    trace.add("plan", AGENT, f"Plan v{version} drafted — waiting for human approval",
              plan.get("goal_summary", ""), data=plan)
    return plan


def constraints_text(c: dict) -> str:
    parts = [f"quantity = {c.get('quantity')}"]
    if c.get("max_total_budget"):
        parts.append(f"total price <= ${c['max_total_budget']}")
    if c.get("city"):
        parts.append(f"city = {c['city']}")
    if c.get("stage"):
        parts.append(f"stage = {c['stage']}")
    if c.get("seats_together"):
        parts.append("seats must be together")
    return "; ".join(parts)


def run_react(llm: LLMClient, profile: dict, goal: str, plan: dict, trace: Trace, use_mcp: bool = False) -> BuyerSession:
    session = BuyerSession(session_id=uuid.uuid4().hex[:8], fan_id=profile["fan_id"],
                           constraints=plan.get("constraints", {}), profile=profile, use_mcp=use_mcp)
    trace.next_step()
    trace.add("human", "Human", "Plan approved — agent may act",
              f"Hard constraints now enforced in code: {constraints_text(session.constraints)}", status="ok")
    tools = schema_list(use_mcp)
    if use_mcp:
        trace.add("mcp", AGENT, "Connected to MCP server 'cupswap-match-status'",
                  "Discovered check_match_status via list_tools; calls go over stdio JSON-RPC.")
    plan_text = "\n".join(f"{s['step']}. {s['action']} [{s['tool']}]" for s in plan.get("steps", []))
    messages = [
        {"role": "system", "content": prompts.BUYER_REACT_SYSTEM.format(
            name=profile["display_name"], clock=BUYER_CLOCK, constraints=constraints_text(session.constraints),
            memory=memory.context_block(profile), max_steps=BUYER_MAX_STEPS)},
        {"role": "user", "content": f"Request: {goal}\n\nApproved plan:\n{plan_text}\n\nExecute it now."},
    ]
    for step in range(1, BUYER_MAX_STEPS + 1):
        left = BUYER_MAX_STEPS - step + 1
        if left <= 2 and not session.recommendation:
            # Budget awareness: the runtime (not the model) tells the agent its step budget is nearly spent.
            messages.append({"role": "user", "content": f"STEP BUDGET: {left} step(s) left. "
                             + ("You hold a listing: call submit_recommendation now." if session.hold
                                else "Place a hold on your best candidate or submit_recommendation now.")})
            trace.add("guard", "Runtime", f"Step budget warning: {left} step(s) left", status="warn")
        resp = llm.chat(f"react:{step}", messages, tools=tools)
        messages.append(assistant_message(resp))
        if not resp["tool_calls"]:
            trace.next_step()
            trace.add("think", AGENT, "Reasoning without a tool call", resp.get("content") or "(empty)")
            messages.append({"role": "user", "content": "Continue: call the next tool, or call submit_recommendation."})
            continue
        for tc in resp["tool_calls"]:
            trace.next_step()
            args = parse_json(tc["arguments"])
            thought = args.pop("thought", "") or (resp.get("content") or "")
            trace.add("think", AGENT, "Thought", thought)
            res = session.run(tc["name"], args)
            trace.add("act", AGENT, f"{tc['name']}({args_for_display(args)})",
                      f"Executed via {res.via}", data={"tool": tc["name"], "args": args, "via": res.via})
            trace.add("observe", AGENT, "Observation", res.summary,
                      data={"table": res.table, "chart": res.chart}, status=res.status)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(res.payload)})
        if session.recommendation:
            r = session.recommendation
            trace.next_step()
            trace.add("final", AGENT, "Recommendation submitted — waiting for human purchase decision",
                      r["why_this_listing"], data=r, status="ok")
            return session
    trace.next_step()
    trace.add("guard", "Runtime", f"Step cap reached ({BUYER_MAX_STEPS}) — loop stopped",
              "The agent did not submit a recommendation within its step budget; any hold is released.",
              status="warn")
    release_hold(session.hold, "step cap reached")
    session.hold = None
    return session


def decide_purchase(session: BuyerSession, approved: bool, trace: Trace) -> dict | None:
    r = session.recommendation
    trace.next_step()
    if approved and r and r["status"] == "recommend":
        order = execute_purchase(session.fan_id, r["listing_id"], r["quantity"], r["price_per_ticket"],
                                 approved_by="human (buyer)", hold=session.hold)
        trace.add("human", "Human", "Purchase APPROVED — mock purchase executed",
                  f"Order {order['order_id']}: {r['listing_id']} ×{r['quantity']} = ${order['total']}", status="ok")
        return order
    release_hold(session.hold, "human declined")
    trace.add("human", "Human", "Purchase DECLINED — hold released", "No money moved.", status="warn")
    return None


def end_session(llm: LLMClient, before: dict, session: BuyerSession, outcome: str, trace: Trace) -> dict:
    """Session end: update long-term memory and persist it."""
    reflection = None
    summary = {"outcome": outcome, "recommendation": session.recommendation,
               "constraints": session.constraints}
    try:
        resp = llm.chat(f"reflect:{outcome}", [
            {"role": "system", "content": prompts.BUYER_REFLECT_SYSTEM},
            {"role": "user", "content": f"Current memory:\n{memory.context_block(before)}\n\nSession:\n{json.dumps(summary)}"}],
            response_format=json_schema_format("memory_reflection", REFLECT_SCHEMA))
        reflection = parse_json(resp["content"])
    except CacheMiss:
        trace.add("system", "Runtime", "Reflection not in recording — deterministic memory update only",
                  "Cached mode replays only the recorded path.", status="warn")
    after = memory.apply_session(before, outcome, session.recommendation, reflection)
    memory.save(after)
    trace.next_step()
    trace.add("memory", AGENT, "Long-term memory updated at session end",
              (reflection or {}).get("summary", "Purchase history updated."),
              data=memory.diff(before, after), status="ok")
    store.audit("buyer_agent", "update_memory", f"profile:{before['fan_id']}", outcome, gated=False)
    return after
