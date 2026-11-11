"""Buyer-agent tools: OpenAI function schemas + mock implementations over local files.

The model selects tools only through structured function calls (strict JSON schema). Hard
constraints from the human-approved plan are enforced here, in code, not by the prompt.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import domain, store
from .config import BUYER_CLOCK, BUYER_MAX_TOOL_CALLS, HOLD_MINUTES

THOUGHT = {"type": "string", "description": "One sentence: why you are taking this action now, given what you observed."}


def _fn(name: str, description: str, props: dict) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description, "strict": True,
        "parameters": {"type": "object", "properties": {"thought": THOUGHT, **props},
                       "required": ["thought", *props.keys()], "additionalProperties": False}}}


NULL_STR = {"type": ["string", "null"]}

TOOL_SCHEMAS = {
    "search_listings": _fn("search_listings",
        "Search active CupSwap resale listings. Every filter is optional (pass null to skip it).", {
            "match_id": {**NULL_STR, "description": "e.g. R16-DAL"},
            "city": {**NULL_STR, "description": "host city, e.g. Dallas"},
            "stage": {**NULL_STR, "description": "e.g. Round of 16, Quarter-final"},
            "team": {**NULL_STR, "description": "national team name"},
            "max_price_per_ticket": {"type": ["number", "null"]},
            "min_quantity": {"type": ["integer", "null"]},
            "adjacent_only": {"type": ["boolean", "null"], "description": "only listings whose seats are together"},
        }),
    "check_match_status": _fn("check_match_status",
        "Get a match's status (scheduled/postponed/completed), teams, venue, kickoff and days to kickoff.",
        {"match_id": {"type": "string"}}),
    "get_price_history": _fn("get_price_history",
        "Get the median resale price trend for a match and the bracket events that moved it.",
        {"match_id": {"type": "string"}}),
    "get_seller_rating": _fn("get_seller_rating",
        "Get a seller's reputation: rating, completed sales, on-time transfer rate, account age, open disputes.",
        {"seller_id": {"type": "string"}}),
    "place_hold": _fn("place_hold",
        f"Place a reversible {HOLD_MINUTES}-minute hold on a listing so it is not sold while the human decides. "
        "At most one active hold per session. This is NOT a purchase.",
        {"listing_id": {"type": "string"}, "quantity": {"type": "integer"}}),
    "submit_recommendation": _fn("submit_recommendation",
        "End the session with a recommendation for the human to approve or decline.", {
            "status": {"type": "string", "enum": ["recommend", "no_suitable_listing"]},
            "listing_id": {**NULL_STR},
            "quantity": {"type": "integer"},
            "price_per_ticket": {"type": "number"},
            "total_price": {"type": "number"},
            "why_this_listing": {"type": "string"},
            "alternatives_rejected": {"type": "array", "items": {
                "type": "object", "properties": {"listing_id": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["listing_id", "reason"], "additionalProperties": False}},
            "memory_factors": {"type": "array", "items": {"type": "string"}},
        }),
}


@dataclass
class ToolResult:
    payload: dict | list          # what the model sees (JSON)
    summary: str                  # one human sentence for the trace
    table: list[dict] | None = None
    chart: list[dict] | None = None
    status: str = "ok"            # ok | warn | fail
    via: str = "local"


@dataclass
class BuyerSession:
    session_id: str
    fan_id: str
    constraints: dict
    profile: dict
    use_mcp: bool = False
    tool_calls: int = 0
    hold: dict | None = None
    recommendation: dict | None = None
    seen_listings: dict = field(default_factory=dict)
    checked_matches: set = field(default_factory=set)

    # ------------------------------------------------------------------------------------------
    def run(self, name: str, args: dict) -> ToolResult:
        self.tool_calls += 1
        if self.tool_calls > BUYER_MAX_TOOL_CALLS:
            return ToolResult({"error": "Tool-call cap reached for this session."},
                              f"Refused: tool-call cap of {BUYER_MAX_TOOL_CALLS} reached.", status="fail")
        fn = getattr(self, f"_t_{name}", None)
        if fn is None:
            return ToolResult({"error": f"Unknown tool {name}"}, f"Unknown tool {name}", status="fail")
        try:
            return fn(**args)
        except TypeError as e:
            return ToolResult({"error": f"Bad arguments: {e}"}, f"Bad arguments for {name}: {e}", status="fail")

    # ---- read-only tools -----------------------------------------------------------------------
    def _t_search_listings(self, match_id=None, city=None, stage=None, team=None, max_price_per_ticket=None,
                           min_quantity=None, adjacent_only=None) -> ToolResult:
        rows = domain.search_listings(match_id, city, stage, team, max_price_per_ticket, min_quantity, adjacent_only)
        for r in rows:
            self.seen_listings[r["listing_id"]] = r
        if not rows:
            return ToolResult({"results": [], "count": 0}, "No active listings match these filters.", status="warn")
        cheapest = min(rows, key=lambda r: r["price_per_ticket"])
        summary = (f"{len(rows)} listing(s) found across {len({r['match_id'] for r in rows})} match(es). "
                   f"Cheapest: {cheapest['listing_id']} at ${cheapest['price_per_ticket']}/ticket "
                   f"(seller {cheapest['seller_id']}).")
        table = [{"listing": r["listing_id"], "match": r["match"], "city": r["city"], "cat": r["category"],
                  "section": r["section"], "qty": r["quantity"], "together": "yes" if r["seats_adjacent"] else "no",
                  "$/ticket": r["price_per_ticket"], "seller": r["seller_id"]} for r in rows]
        return ToolResult({"count": len(rows), "results": rows}, summary, table=table)

    def _t_check_match_status(self, match_id: str) -> ToolResult:
        via = "local"
        if self.use_mcp:
            from . import mcp_client
            res, via = mcp_client.call_tool("check_match_status", {"match_id": match_id}), "MCP server"
        else:
            res = domain.match_status(match_id)
        if "error" in res:
            return ToolResult(res, res["error"], status="fail", via=via)
        self.checked_matches.add(res["match_id"])
        s = (f"{res['match_id']}: {res['teams']} at {res['venue']} — {res['status']}, kickoff {res['kickoff']} "
             f"({res['days_to_kickoff']} days away){', marquee matchup' if res.get('marquee_matchup') else ''}.")
        return ToolResult(res, s, status="ok" if res["status"] == "scheduled" else "warn", via=via)

    def _t_get_price_history(self, match_id: str) -> ToolResult:
        res = domain.price_history(match_id)
        if "error" in res:
            return ToolResult(res, res["error"], status="fail")
        ev = "; ".join(f"{e['date']}: {e['event']} ({e['impact']})" for e in res["bracket_events"])
        s = (f"Median resale price now ${res['current_median']} ({res['change_7d_pct']:+}% over 7 days, "
             f"range ${res['low']}–${res['high']}). Bracket events: {ev}")
        model_view = {k: v for k, v in res.items() if k != "series"}
        return ToolResult(model_view, s, chart=res["series"])

    def _t_get_seller_rating(self, seller_id: str) -> ToolResult:
        res = domain.seller_profile(seller_id)
        if "error" in res:
            return ToolResult(res, res["error"], status="fail")
        rules = self.profile["seller_rules"]
        breaks = res["rating"] < rules["min_seller_rating"] or seller_id in rules["avoid_sellers"]
        s = (f"{seller_id} {res['display_name']}: {res['rating']}★, {res['completed_sales']} sales, "
             f"{int(res['on_time_transfer_rate'] * 100)}% on-time transfers, account {res['account_age_days']} days old, "
             f"{res['open_disputes']} open dispute(s)."
             + (" ⚠ Breaks the fan's seller rules (memory)." if breaks else ""))
        return ToolResult(res, s, status="warn" if breaks else "ok")

    # ---- state-changing tool (reversible, monitored - not gated) -------------------------------
    def _t_place_hold(self, listing_id: str, quantity: int) -> ToolResult:
        x = store.listing(listing_id)
        if not x or x["status"] != "active":
            return ToolResult({"error": "Listing not available."}, f"Hold refused: {listing_id} not available.", status="fail")
        if self.hold:
            return ToolResult({"error": f"Session already holds {self.hold['listing_id']}. One hold per session."},
                              "Hold refused: one hold per session (guard).", status="fail")
        if x["match_id"] not in self.checked_matches:
            return ToolResult({"error": f"Call check_match_status for {x['match_id']} first: never hold tickets for a "
                                        f"match you have not confirmed is still scheduled (it could be postponed)."},
                              f"Hold refused by pre-hold guard: match {x['match_id']} status not checked yet.",
                              status="fail")
        m = store.match(x["match_id"]) or {}
        if m.get("status") != "scheduled":
            return ToolResult({"error": f"Match {x['match_id']} is {m.get('status')}; holds are only allowed for "
                                        f"scheduled matches."}, f"Hold refused: match is {m.get('status')}.", status="fail")
        need = self.constraints.get("quantity") or quantity
        if quantity < need or quantity > x["quantity"]:
            return ToolResult({"error": f"Quantity {quantity} invalid: request needs {need}, listing has {x['quantity']}."},
                              f"Hold refused: quantity guard ({quantity} vs needed {need}, available {x['quantity']}).",
                              status="fail")
        total = x["price_per_ticket"] * quantity
        budget = self.constraints.get("max_total_budget")
        if budget and total > budget:
            return ToolResult({"error": f"Total ${total} exceeds the approved budget ${budget}. Hold refused."},
                              f"Hold refused by budget guard: ${total} > approved budget ${budget}.", status="fail")
        if self.constraints.get("seats_together") and not x["seats_adjacent"]:
            return ToolResult({"error": "Seats are not together; the approved plan requires seats together."},
                              "Hold refused: seats-together guard.", status="fail")
        expires = datetime.fromisoformat(BUYER_CLOCK) + timedelta(minutes=HOLD_MINUTES)
        self.hold = {"hold_id": f"H-{uuid.uuid4().hex[:6].upper()}", "listing_id": listing_id, "quantity": quantity,
                     "price_per_ticket": x["price_per_ticket"], "total": total, "fan_id": self.fan_id,
                     "session_id": self.session_id, "expires_at": expires.isoformat(timespec="minutes"),
                     "status": "active"}
        store.append_state("holds.json", self.hold)
        _set_listing_status(listing_id, "on_hold")
        store.audit("buyer_agent", "place_hold", listing_id,
                    f"{quantity} tickets, ${total}, expires {self.hold['expires_at']}", gated=False)
        return ToolResult({"hold": self.hold},
                          f"Hold {self.hold['hold_id']} placed on {listing_id} ×{quantity} (${total} total), "
                          f"expires in {HOLD_MINUTES} min. Monitored, reversible — not a purchase.")

    def _t_submit_recommendation(self, status, listing_id, quantity, price_per_ticket, total_price,
                                 why_this_listing, alternatives_rejected, memory_factors) -> ToolResult:
        rec = {"status": status, "listing_id": listing_id, "quantity": quantity, "price_per_ticket": price_per_ticket,
               "total_price": total_price, "why_this_listing": why_this_listing,
               "alternatives_rejected": alternatives_rejected, "memory_factors": memory_factors}
        if status == "recommend":
            x = store.listing(listing_id or "")
            budget = self.constraints.get("max_total_budget")
            if not x:
                return ToolResult({"error": f"Unknown listing {listing_id}."}, "Recommendation rejected: unknown listing.", status="fail")
            true_total = x["price_per_ticket"] * quantity
            if abs(true_total - total_price) > 0.5:
                rec["total_price"], rec["price_per_ticket"] = true_total, x["price_per_ticket"]
            if budget and true_total > budget:
                return ToolResult({"error": f"${true_total} exceeds budget ${budget}. Choose another listing."},
                                  f"Recommendation rejected by budget guard (${true_total} > ${budget}).", status="fail")
        self.recommendation = rec
        s = (f"Recommends {listing_id} ×{quantity} for ${rec['total_price']} total."
             if status == "recommend" else "No suitable listing found under the constraints.")
        return ToolResult({"accepted": True}, s)


# ---- human-gated actions (never callable by the agent) -----------------------------------------
def _set_listing_status(listing_id: str, status: str) -> None:
    rows = store.listings()
    for r in rows:
        if r["listing_id"] == listing_id:
            r["status"] = status
    store.write_state("listings.json", rows)


def release_hold(hold: dict | None, reason: str) -> None:
    if not hold:
        return
    holds = store.state("holds.json", [])
    for h in holds:
        if h["hold_id"] == hold["hold_id"]:
            h["status"] = "released"
    store.write_state("holds.json", holds)
    _set_listing_status(hold["listing_id"], "active")
    store.audit("buyer_agent", "release_hold", hold["listing_id"], reason, gated=False)


def execute_purchase(fan_id: str, listing_id: str, quantity: int, price_per_ticket: float, approved_by: str,
                     hold: dict | None = None, channel: str = "buyer_agent") -> dict:
    """Mock purchase. Only ever called from a human approval click in the UI."""
    order = {"order_id": f"P-{uuid.uuid4().hex[:6].upper()}", "fan_id": fan_id, "listing_id": listing_id,
             "quantity": quantity, "price_per_ticket": price_per_ticket, "total": round(price_per_ticket * quantity, 2),
             "approved_by": approved_by, "channel": channel, "at": datetime.now().isoformat(timespec="seconds"),
             "note": "MOCK purchase - no real money or tickets"}
    store.append_state("purchases.json", order)
    if hold:
        holds = store.state("holds.json", [])
        for h in holds:
            if h["hold_id"] == hold["hold_id"]:
                h["status"] = "converted_to_purchase"
        store.write_state("holds.json", holds)
    _set_listing_status(listing_id, "sold")
    store.audit(approved_by, "execute_purchase", listing_id, f"{quantity} × ${price_per_ticket} (mock)", gated=True)
    return order


def schema_list(use_mcp: bool) -> list[dict]:
    schemas = [TOOL_SCHEMAS[k] for k in ["search_listings", "check_match_status", "get_price_history",
                                         "get_seller_rating", "place_hold", "submit_recommendation"]]
    if use_mcp:
        from . import mcp_client
        mcp_tools = {t["name"]: t for t in mcp_client.list_tools()}
        if "check_match_status" in mcp_tools:
            schemas[1] = mcp_client.openai_schema_from_mcp(mcp_tools["check_match_status"])
    return schemas


def args_for_display(args: dict) -> str:
    return ", ".join(f"{k}={json.dumps(v)}" for k, v in args.items() if v is not None)
