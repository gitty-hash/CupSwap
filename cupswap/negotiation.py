"""Part C: the negotiation arena (agent-to-agent market in miniature).

Roles (each with its own system prompt):
  * Platform agent  - LLM with tools: verify_ticket, get_price_cap, publish_ruling; later compute_fee,
                      record_settlement. Neutral; never sees private limits.
  * Buyer agent     - LLM; private ceiling; reads the shared state.
  * Seller agent    - LLM; private floor + concession schedule tied to kickoff proximity; reads the shared state.

Protocol: seller's (capped) ask opens; then alternating buyer offer -> seller response, hard cap of
NEGOTIATION_MAX_ROUNDS rounds. Every offer, counter and platform check is appended to one shared
negotiation state (collective memory). Deterministic guards enforce private limits and the cap.
A deal never executes until the human clicks Approve.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from . import domain, prompts, store
from .buyer_tools import execute_purchase
from .config import NEGOTIATION_MAX_ROUNDS, PLATFORM_FEE_RATE, PLATFORM_MAX_STEPS, PRICE_CAP_MULTIPLIER
from .llm import LLMClient, assistant_message, json_schema_format, parse_json
from .trace import Trace


@dataclass
class Setup:
    listing_id: str
    fan_id: str
    quantity: int
    ceiling_per_ticket: float
    label: str = ""


# ---- seller pricing policy (private) -----------------------------------------------------------
def seller_private(listing_id: str) -> dict:
    pol = store.seed("seller_policies.json")
    x = store.listing(listing_id)
    m = store.match(x["match_id"])
    p = pol.get(listing_id) or {}
    base = p.get("base_floor_per_ticket") or round(x["price_per_ticket"] * pol["_default"]["floor_ratio"])
    mult = p.get("marquee_multiplier", 1.05) if m.get("marquee") else 0.95
    days = domain.days_until(m["kickoff"])
    rate = 0.30 if days <= 3 else 0.18 if days <= 7 else 0.10
    return {"floor": round(base * mult), "base_floor": base, "marquee_adjustment": mult,
            "days_to_kickoff": days, "concession_rate_per_round": rate,
            "persona": p.get("persona", "A fan reselling tickets they can no longer use.")}


def round_min(opening: float, floor: float, rate: float, r: int) -> float:
    return round(max(floor, opening - (opening - floor) * min(1.0, rate * r)), 2)


TURN_SCHEMA = {
    "buyer": {"type": "object", "additionalProperties": False, "required": ["action", "price_per_ticket", "message"],
              "properties": {"action": {"type": "string", "enum": ["offer", "accept"]},
                             "price_per_ticket": {"type": "number"}, "message": {"type": "string"}}},
    "seller": {"type": "object", "additionalProperties": False, "required": ["action", "price_per_ticket", "message"],
               "properties": {"action": {"type": "string", "enum": ["counter", "accept"]},
                              "price_per_ticket": {"type": "number"}, "message": {"type": "string"}}},
}

PLATFORM_TOOLS = [
    {"type": "function", "function": {"name": "verify_ticket", "description": "Check the listing's barcodes against the organizer registry.",
     "strict": True, "parameters": {"type": "object", "properties": {"listing_id": {"type": "string"}}, "required": ["listing_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "get_price_cap", "description": "Return face value and the organizer resale cap for the listing.",
     "strict": True, "parameters": {"type": "object", "properties": {"listing_id": {"type": "string"}}, "required": ["listing_id"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "publish_ruling", "description": "Publish the platform ruling that opens (or blocks) the negotiation.",
     "strict": True, "parameters": {"type": "object", "properties": {
         "trading_allowed": {"type": "boolean"}, "enforced_opening_price": {"type": "number"},
         "badges": {"type": "array", "items": {"type": "string"}}, "note": {"type": "string"}},
         "required": ["trading_allowed", "enforced_opening_price", "badges", "note"], "additionalProperties": False}}},
]
SETTLE_TOOLS = [
    {"type": "function", "function": {"name": "compute_fee", "description": "Compute the platform fee and seller proceeds.",
     "strict": True, "parameters": {"type": "object", "properties": {"price_per_ticket": {"type": "number"}, "quantity": {"type": "integer"}},
                                    "required": ["price_per_ticket", "quantity"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "record_settlement", "description": "Record the settlement in the platform ledger.",
     "strict": True, "parameters": {"type": "object", "properties": {
         "price_per_ticket": {"type": "number"}, "quantity": {"type": "integer"}, "buyer_total": {"type": "number"},
         "platform_fee": {"type": "number"}, "seller_proceeds": {"type": "number"}},
         "required": ["price_per_ticket", "quantity", "buyer_total", "platform_fee", "seller_proceeds"], "additionalProperties": False}}},
]


def compute_fee(price_per_ticket: float, quantity: int) -> dict:
    gross = round(price_per_ticket * quantity, 2)
    fee = round(gross * PLATFORM_FEE_RATE, 2)
    return {"buyer_total": gross, "platform_fee": fee, "seller_proceeds": round(gross - fee, 2),
            "fee_rate": PLATFORM_FEE_RATE}


# ---- shared state (collective memory) ---------------------------------------------------------
def new_state(setup: Setup) -> dict:
    x = store.listing(setup.listing_id)
    m = store.match(x["match_id"])
    return {
        "negotiation_id": f"N-{uuid.uuid4().hex[:6].upper()}",
        "listing": domain.public_listing(x), "quantity": setup.quantity,
        "match": domain.match_status(x["match_id"]),
        "rules": {"price_cap_per_ticket": round(x["face_value"] * PRICE_CAP_MULTIPLIER, 2),
                  "cap_rule": f"resale price <= {PRICE_CAP_MULTIPLIER}x face value",
                  "platform_fee_rate": PLATFORM_FEE_RATE, "max_rounds": NEGOTIATION_MAX_ROUNDS},
        "ruling": None, "history": [], "status": "open", "deal_price_per_ticket": None,
        "buyer": setup.fan_id, "seller": x["seller_id"], "label": setup.label,
    }


def public_view(state: dict) -> str:
    view = {k: state[k] for k in ["negotiation_id", "listing", "quantity", "match", "rules", "ruling", "status"]}
    view["history"] = [{k: h[k] for k in ["round", "role", "action", "price_per_ticket", "message", "platform_checks"]}
                       for h in state["history"]]
    return json.dumps(view, ensure_ascii=False)


def _reconcile(message: str, price: float, guards: list[str]) -> str:
    """The structured price is binding; flag any dollar figure in the text that disagrees with it."""
    figures = [float(n) for n in NUM.findall(message or "") if 50 <= float(n) <= 5000]
    wrong = [f for f in figures if abs(f - price) > 1.0]
    if wrong and price:
        guards.append(f"Message quoted ${wrong[0]:g} but the binding offer is ${price:g} → message annotated")
        return f"{message} [platform note: binding price is ${price:g}/ticket; figures in the text are not binding]"
    return message


def _append(state: dict, trace: Trace, round_no: int, role: str, action: str, price: float, message: str,
            checks: list[dict], guards: list[str]) -> None:
    if round_no > 0:
        message = _reconcile(message, price, guards)
    entry = {"round": round_no, "role": role, "action": action, "price_per_ticket": price, "message": message,
             "platform_checks": checks, "guards": guards}
    state["history"].append(entry)
    trace.add("offer", role, f"Round {round_no} · {role} · {action} ${price:,.2f}/ticket", message,
              data={"checks": checks, "guards": guards},
              status="ok" if action in {"accept", "deal"} else "info")
    for g in guards:
        trace.add("guard", "Policy guard (code)", g, status="warn")


def rule_engine(state: dict, price: float) -> list[dict]:
    """Platform's deterministic per-offer checks, shown as badges in the UI."""
    cap = state["rules"]["price_cap_per_ticket"]
    checks = [{"rule": "price cap", "ok": price <= cap + 1e-6, "detail": f"${price:,.2f} vs cap ${cap:,.2f}"}]
    if state.get("ruling"):
        checks.append({"rule": "ticket verified", "ok": bool(state["ruling"].get("verified")), "detail": "verify_ticket"})
    return checks


# ---- platform agent: opening -------------------------------------------------------------------
def platform_open(llm: LLMClient, state: dict, trace: Trace) -> dict:
    lid = state["listing"]["listing_id"]
    trace.next_step()
    trace.add("platform", "Platform agent", "Platform agent reviews the listing before trading opens",
              f"Listing {lid}: {state['listing']['match']} · {state['listing']['category']} §{state['listing']['section']}")
    messages = [{"role": "system", "content": prompts.PLATFORM_OPEN_SYSTEM.format(
                    listing_id=lid, cap_mult=PRICE_CAP_MULTIPLIER, fee_pct=int(PLATFORM_FEE_RATE * 100))},
                {"role": "user", "content": f"Shared negotiation state:\n{public_view(state)}"}]
    facts: dict = {}
    ruling = None
    for step in range(1, PLATFORM_MAX_STEPS + 1):
        resp = llm.chat(f"platform_open:{step}", messages, tools=PLATFORM_TOOLS)
        messages.append(assistant_message(resp))
        if not resp["tool_calls"]:
            break
        for tc in resp["tool_calls"]:
            args = parse_json(tc["arguments"])
            if tc["name"] == "verify_ticket":
                res = domain.verify_ticket(lid)
                facts["verify"] = res
                trace.add("act", "Platform agent", f"verify_ticket({lid})", res["reason"],
                          status="ok" if res["verified"] else "fail")
            elif tc["name"] == "get_price_cap":
                res = domain.price_cap(lid)
                facts["cap"] = res
                trace.add("act", "Platform agent", f"get_price_cap({lid})",
                          f"Face ${res['face_value']} → cap ${res['price_cap_per_ticket']}; ask ${res['asking_price']}"
                          + (" exceeds the cap" if res["ask_exceeds_cap"] else " is within the cap"),
                          status="warn" if res["ask_exceeds_cap"] else "ok")
            elif tc["name"] == "publish_ruling":
                ruling = args
                res = {"published": True}
            else:
                res = {"error": "unknown tool"}
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(res)})
        if ruling:
            break
    # Code-level guard: the ruling must agree with the tool facts, whatever the LLM wrote.
    verify = facts.get("verify") or domain.verify_ticket(lid)
    cap = facts.get("cap") or domain.price_cap(lid)
    correct_open = min(cap["asking_price"], cap["price_cap_per_ticket"])
    ruling = ruling or {"trading_allowed": verify["verified"], "enforced_opening_price": correct_open,
                        "badges": [], "note": "Ruling synthesized by the rule engine (agent did not publish)."}
    if bool(ruling["trading_allowed"]) != verify["verified"] or abs(ruling["enforced_opening_price"] - correct_open) > 0.01:
        trace.add("guard", "Policy guard (code)", "Ruling corrected to match tool facts",
                  f"LLM said allowed={ruling['trading_allowed']} open=${ruling['enforced_opening_price']}; "
                  f"facts say allowed={verify['verified']} open=${correct_open}", status="warn")
        ruling["trading_allowed"], ruling["enforced_opening_price"] = verify["verified"], correct_open
    ruling["verified"] = verify["verified"]
    ruling["ask_capped"] = cap["ask_exceeds_cap"]
    state["ruling"] = ruling
    trace.add("platform", "Platform agent", "Ruling published" + ("" if ruling["trading_allowed"] else " — TRADING BLOCKED"),
              ruling["note"], data=ruling, status="ok" if ruling["trading_allowed"] else "fail")
    return ruling


# ---- the bounded alternating-offer protocol ----------------------------------------------------
def run(llm: LLMClient, setup: Setup, trace: Trace, state: dict | None = None) -> dict:
    state = state or new_state(setup)
    priv = seller_private(setup.listing_id)
    state["_private"] = {"seller_floor": priv["floor"], "buyer_ceiling": setup.ceiling_per_ticket,
                         "concession_rate": priv["concession_rate_per_round"], "days_to_kickoff": priv["days_to_kickoff"],
                         "base_floor": priv["base_floor"], "marquee_adjustment": priv["marquee_adjustment"]}
    ruling = platform_open(llm, state, trace)
    if not ruling["trading_allowed"]:
        state["status"] = "blocked"
        return state

    x = store.listing(setup.listing_id)
    seller = store.seller(x["seller_id"])
    fan = store.state(f"profiles/{setup.fan_id}.json")
    ph = domain.price_history(x["match_id"])
    market = (f"median resale price for this match ${ph.get('current_median')} ({ph.get('change_7d_pct'):+}% in 7 days); "
              f"kickoff in {priv['days_to_kickoff']} days; face value ${x['face_value']}; "
              f"cap ${state['rules']['price_cap_per_ticket']}")
    opening = ruling["enforced_opening_price"]
    trace.next_step()
    _append(state, trace, 0, "Seller agent", "ask", opening, f"Listed: {x['description']}",
            rule_engine(state, opening), ["Ask reduced to the price cap"] if ruling.get("ask_capped") else [])
    last_seller, last_buyer = opening, None
    ceiling = setup.ceiling_per_ticket
    anchor = round(min(ceiling * 0.85, opening * 0.80))
    step = (ceiling - anchor) / max(1, NEGOTIATION_MAX_ROUNDS - 1)
    state["_private"]["buyer_anchor"] = anchor

    for r in range(1, NEGOTIATION_MAX_ROUNDS + 1):
        trace.next_step()
        # ---------------- buyer turn ----------------
        guide = round(min(ceiling, anchor + step * (r - 1)))
        guide_accept = round(min(ceiling, anchor + step * r))
        bsys = prompts.BUYER_NEGOTIATE_SYSTEM.format(
            name=fan["display_name"], listing_id=setup.listing_id, listing_desc=x["description"],
            ceiling=setup.ceiling_per_ticket, qty=setup.quantity, budget=setup.ceiling_per_ticket * setup.quantity,
            market=market, max_rounds=NEGOTIATION_MAX_ROUNDS, round=r, guide=guide, guide_accept=guide_accept,
            fan_context=f"favorite teams {', '.join(fan['favorite_teams'])}; {fan['budget_habits']['notes']}")
        resp = llm.chat(f"buyer:r{r}", [{"role": "system", "content": bsys},
                                        {"role": "user", "content": f"SHARED NEGOTIATION STATE:\n{public_view(state)}\n\nYour move."}],
                        response_format=json_schema_format("buyer_turn", TURN_SCHEMA["buyer"]), temperature=0.4)
        b = parse_json(resp["content"])
        action, price, guards = b.get("action", "offer"), float(b.get("price_per_ticket") or 0), []
        if action == "accept":
            if last_seller > setup.ceiling_per_ticket:
                guards.append(f"Buyer tried to accept ${last_seller} above its ceiling → converted to an offer at the ceiling")
                action, price = "offer", setup.ceiling_per_ticket
            else:
                price = last_seller
        if action == "offer":
            if price > setup.ceiling_per_ticket:
                guards.append(f"Buyer offer ${price} exceeded its private ceiling → clamped")
                price = setup.ceiling_per_ticket
            if last_buyer is not None and price < last_buyer:
                guards.append(f"Buyer tried to retract below its previous offer ${last_buyer} → held")
                price = last_buyer
            if price >= last_seller:
                guards.append("Buyer offer met the seller's price → treated as acceptance")
                action, price = "accept", last_seller
        _append(state, trace, r, "Buyer agent", action, price, b.get("message", ""), rule_engine(state, price), guards)
        if action == "accept":
            return _deal(state, trace, price)
        last_buyer = price

        # ---------------- seller turn ----------------
        rmin = round_min(opening, priv["floor"], priv["concession_rate_per_round"], r)
        suggest = round(max(rmin, (last_seller + rmin) / 2))
        ssys = prompts.SELLER_SYSTEM.format(
            seller_name=seller["display_name"], seller_id=seller["seller_id"], listing_id=setup.listing_id,
            listing_desc=x["description"], persona=priv["persona"], days=priv["days_to_kickoff"],
            floor=priv["floor"], round_min=rmin, max_rounds=NEGOTIATION_MAX_ROUNDS, round=r, qty=setup.quantity,
            cap=state["rules"]["price_cap_per_ticket"], prev=last_seller, suggest=suggest)
        resp = llm.chat(f"seller:r{r}", [{"role": "system", "content": ssys},
                                         {"role": "user", "content": f"SHARED NEGOTIATION STATE:\n{public_view(state)}\n\nYour move."}],
                        response_format=json_schema_format("seller_turn", TURN_SCHEMA["seller"]), temperature=0.4)
        s = parse_json(resp["content"])
        action, price, guards = s.get("action", "counter"), float(s.get("price_per_ticket") or last_seller), []
        if action == "accept":
            if last_buyer < priv["floor"]:
                guards.append(f"Seller tried to accept ${last_buyer} below its private floor → converted to a counter")
                action, price = "counter", max(priv["floor"], suggest)
            else:
                price = last_buyer
        if action == "counter":
            if price < priv["floor"]:
                guards.append("Seller counter below its private floor → raised to the floor")
                price = priv["floor"]
            if price > last_seller:
                guards.append(f"Seller tried to raise its price above ${last_seller} → held")
                price = last_seller
            if price > state["rules"]["price_cap_per_ticket"]:
                guards.append("Seller counter above the price cap → capped")
                price = state["rules"]["price_cap_per_ticket"]
            if price <= last_buyer:
                guards.append("Seller counter met the buyer's offer → treated as acceptance")
                action, price = "accept", last_buyer
        _append(state, trace, r, "Seller agent", action, price, s.get("message", ""), rule_engine(state, price), guards)
        if action == "accept":
            return _deal(state, trace, price)
        last_seller = price

    trace.next_step()
    state["status"] = "no_agreement"
    trace.add("guard", "Protocol", f"Round cap reached ({NEGOTIATION_MAX_ROUNDS}) — no agreement, ended gracefully",
              f"Final gap: buyer ${last_buyer} vs seller ${last_seller}. No hold, no payment, nothing to undo.",
              status="warn")
    store.audit("negotiation_protocol", "no_agreement", setup.listing_id, f"gap {last_buyer}..{last_seller}", gated=False)
    return state


def _deal(state: dict, trace: Trace, price: float) -> dict:
    state["status"] = "deal_pending_approval"
    state["deal_price_per_ticket"] = price
    trace.next_step()
    trace.add("human", "Protocol", "Agreement reached — waiting for the HUMAN buyer to approve",
              f"${price:,.2f}/ticket × {state['quantity']} = ${price * state['quantity']:,.2f}. Nothing executes until approved.",
              status="ok")
    return state


# ---- settlement (only after the human clicks Approve) ------------------------------------------
def settle(llm: LLMClient, state: dict, trace: Trace) -> dict:
    trace.next_step()
    trace.add("human", "Human", "Purchase APPROVED by the human buyer", "Platform agent settles the deal.", status="ok")
    p, q = state["deal_price_per_ticket"], state["quantity"]
    truth = compute_fee(p, q)
    messages = [{"role": "system", "content": prompts.PLATFORM_SETTLE_SYSTEM},
                {"role": "user", "content": f"Deal: listing {state['listing']['listing_id']}, ${p}/ticket × {q}."}]
    recorded = None
    for step in range(1, PLATFORM_MAX_STEPS + 1):
        resp = llm.chat(f"platform_settle:{step}", messages, tools=SETTLE_TOOLS)
        messages.append(assistant_message(resp))
        if not resp["tool_calls"]:
            if resp.get("content"):
                trace.add("platform", "Platform agent", "Settlement summary", resp["content"], status="ok")
            break
        for tc in resp["tool_calls"]:
            args = parse_json(tc["arguments"])
            if tc["name"] == "compute_fee":
                res = compute_fee(args.get("price_per_ticket", p), args.get("quantity", q))
                trace.add("act", "Platform agent", f"compute_fee(${args.get('price_per_ticket')}, ×{args.get('quantity')})",
                          f"buyer pays ${res['buyer_total']}, fee ${res['platform_fee']}, seller receives ${res['seller_proceeds']}")
            elif tc["name"] == "record_settlement":
                ok = all(abs(args.get(k, -1) - truth[k]) < 0.01 for k in ["buyer_total", "platform_fee", "seller_proceeds"])
                if not ok:
                    trace.add("guard", "Policy guard (code)", "Settlement numbers corrected to the computed fee",
                              json.dumps(args), status="warn")
                recorded = {"negotiation_id": state["negotiation_id"], "listing_id": state["listing"]["listing_id"],
                            "price_per_ticket": p, "quantity": q, **truth}
                store.append_state("settlements.json", recorded)
                store.audit("platform_agent", "record_settlement", state["listing"]["listing_id"],
                            json.dumps(truth), gated=True)
                res = {"recorded": True}
                trace.add("act", "Platform agent", "record_settlement(...)", "Written to the settlement ledger (mock).", status="ok")
            else:
                res = {"error": "unknown tool"}
            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": json.dumps(res)})
    if recorded is None:  # the agent failed to record: the rule engine records the computed truth
        recorded = {"negotiation_id": state["negotiation_id"], "listing_id": state["listing"]["listing_id"],
                    "price_per_ticket": p, "quantity": q, **truth}
        store.append_state("settlements.json", recorded)
        trace.add("guard", "Policy guard (code)", "Settlement recorded by the rule engine (agent did not)", status="warn")
    execute_purchase(state["buyer"], state["listing"]["listing_id"], q, p, approved_by="human (buyer)",
                     channel="negotiation")
    state["status"] = "settled"
    state["settlement"] = recorded
    return state


def decline(state: dict, trace: Trace) -> dict:
    trace.next_step()
    trace.add("human", "Human", "Deal DECLINED by the human buyer", "Nothing was purchased.", status="warn")
    store.audit("human (buyer)", "decline_deal", state["listing"]["listing_id"], "", gated=True)
    state["status"] = "declined"
    return state


# ---- analysis helpers --------------------------------------------------------------------------
# Language that reveals the speaker's OWN limit (role-specific, so "your budget" from a seller is not a leak).
SELLER_LIMIT = re.compile(r"(my (floor|minimum|bottom line|lowest)|lowest i can|can'?t go (any )?(lower|below|that low)|"
                          r"final offer|best i can do|bottom line)", re.I)
BUYER_LIMIT = re.compile(r"(my (budget|ceiling|max(imum)?|limit)|most i can|stretch my|can'?t go (any )?(higher|above)|"
                         r"above my budget|final offer|best i can do)", re.I)
NUM = re.compile(r"\$?\s?(\d{2,4}(?:\.\d{1,2})?)")


def leakage_report(state: dict) -> list[dict]:
    """Scan the transcript the counterparty sees for private limits it could exploit."""
    priv = state.get("_private", {})
    floor, ceiling = priv.get("seller_floor"), priv.get("buyer_ceiling")
    rows = []
    for h in state["history"]:
        if h["round"] == 0:
            continue
        msg = (h["message"] or "").split(" [platform note:")[0]
        seller_turn = h["role"] == "Seller agent"
        secret, label = (floor, "floor") if seller_turn else (ceiling, "ceiling")
        m = (SELLER_LIMIT if seller_turn else BUYER_LIMIT).search(msg)
        nums = [float(n) for n in NUM.findall(msg)]
        hits = [n for n in nums if secret is not None and abs(n - secret) <= 1.0]
        if hits and (m or abs(hits[0] - h["price_per_ticket"]) > 1.0):
            rows.append({"round": h["round"], "role": h["role"], "type": f"EXPLICIT: states its private {label}",
                         "evidence": msg})
        elif m:
            rows.append({"round": h["round"], "role": h["role"],
                         "type": f"SIGNAL: limit language ('{m.group(0)}')", "evidence": msg})
    hist = [h for h in state["history"] if h["round"] > 0]
    if hist:
        last_s = [h for h in hist if h["role"] == "Seller agent"]
        last_b = [h for h in hist if h["role"] == "Buyer agent"]
        if last_s and floor is not None and abs(last_s[-1]["price_per_ticket"] - floor) < 0.5:
            rows.append({"round": last_s[-1]["round"], "role": "Seller agent",
                         "type": "BEHAVIORAL: final price sits exactly on the floor", "evidence": "price trajectory"})
        if last_b and ceiling is not None and abs(last_b[-1]["price_per_ticket"] - ceiling) < 0.5:
            rows.append({"round": last_b[-1]["round"], "role": "Buyer agent",
                         "type": "BEHAVIORAL: final offer sits exactly on the ceiling", "evidence": "price trajectory"})
    return rows


def surplus(state: dict) -> dict | None:
    if state.get("deal_price_per_ticket") is None:
        return None
    p, q = state["deal_price_per_ticket"], state["quantity"]
    priv = state["_private"]
    fee = p * PLATFORM_FEE_RATE
    return {"deal_price": p, "quantity": q,
            "zopa_per_ticket": round(priv["buyer_ceiling"] - priv["seller_floor"], 2),
            "buyer_surplus": round((priv["buyer_ceiling"] - p) * q, 2),
            "seller_surplus_after_fee": round((p - fee - priv["seller_floor"]) * q, 2),
            "platform_fee": round(fee * q, 2)}
