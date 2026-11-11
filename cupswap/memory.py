"""Long-term memory: the fan preference store (Chapter 5 lab pattern).

Loaded into the agent's context at session start; updated at session end (deterministic
purchase record + an LLM reflection that proposes at most two new notes).
"""
from __future__ import annotations

import copy
import json

from . import store
from .config import BUYER_CLOCK


def load(fan_id: str) -> dict:
    return store.state(f"profiles/{fan_id}.json")


def save(profile: dict) -> None:
    store.write_state(f"profiles/{profile['fan_id']}.json", profile)


def list_fans() -> list[str]:
    return ["sofia", "julien"]


def context_block(p: dict) -> str:
    """The memory as it is injected into the agent's system prompt (short-term context)."""
    lines = [
        f"- Name: {p['display_name']}; home city: {p['home_city']}; languages: {p.get('language', 'en')}",
        f"- Favorite national teams: {', '.join(p['favorite_teams'])}",
        f"- Host cities within reach: {', '.join(p['cities_within_reach'])}",
        f"- Budget habits: typically up to ${p['budget_habits']['typical_max_per_ticket']}/ticket. "
        f"{p['budget_habits'].get('notes', '')}",
        f"- Seat preferences: " + "; ".join(f"{k}: {v}" for k, v in p["seat_preferences"].items()),
        f"- Seller rules: minimum seller rating {p['seller_rules']['min_seller_rating']}; avoid sellers: "
        f"{', '.join(p['seller_rules']['avoid_sellers']) or 'none'}",
        "- Past purchases: " + "; ".join(
            f"{x['match_id']} ({x['city']}) x{x['tickets']} at ${x['price_per_ticket']} from {x['seller_id']}: {x['outcome']}"
            for x in p["past_purchases"]),
        "- Agent notes: " + " | ".join(p.get("agent_notes", [])),
    ]
    return "\n".join(lines)


def apply_session(before: dict, outcome: str, recommendation: dict | None, reflection: dict | None) -> dict:
    after = copy.deepcopy(before)
    if outcome == "approved" and recommendation and recommendation.get("status") == "recommend":
        lst = store.listing(recommendation["listing_id"]) or {}
        m = store.match(lst.get("match_id", "")) or {}
        after["past_purchases"].append({
            "match_id": lst.get("match_id"), "city": m.get("city"), "tickets": recommendation["quantity"],
            "price_per_ticket": recommendation["price_per_ticket"], "seller_id": lst.get("seller_id"),
            "outcome": "bought via CupSwap buyer agent (human-approved)"})
    if reflection:
        for note in (reflection.get("notes_to_add") or [])[:2]:
            if note and note not in after["agent_notes"]:
                after["agent_notes"].append(note)
        new_max = reflection.get("typical_max_per_ticket")
        if isinstance(new_max, (int, float)) and 50 <= new_max <= 2000:
            after["budget_habits"]["typical_max_per_ticket"] = int(new_max)
    after["last_updated"] = BUYER_CLOCK[:10]
    return after


def diff(before: dict, after: dict) -> list[dict]:
    """Field-level changes for the memory panel."""
    rows = []
    for key in ["budget_habits", "past_purchases", "agent_notes", "seller_rules", "seat_preferences",
                "favorite_teams", "cities_within_reach", "last_updated"]:
        b, a = before.get(key), after.get(key)
        if b != a:
            if isinstance(b, list) and isinstance(a, list):
                added = [x for x in a if x not in b]
                rows.append({"field": key, "change": "added", "value": "; ".join(
                    json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else str(x) for x in added)})
            else:
                rows.append({"field": key, "change": "updated",
                             "value": f"{json.dumps(b, ensure_ascii=False)} → {json.dumps(a, ensure_ascii=False)}"})
    return rows
