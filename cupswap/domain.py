"""Pure domain functions over the mock data. No LLM here: these are what tools *do*.

Shared by the buyer tools, the platform agent, and the MCP server (bonus).
"""
from __future__ import annotations

from datetime import datetime

from . import store
from .config import BUYER_CLOCK, PRICE_CAP_MULTIPLIER


def days_until(iso: str, clock: str = BUYER_CLOCK) -> float:
    return round((datetime.fromisoformat(iso) - datetime.fromisoformat(clock)).total_seconds() / 86400, 1)


def match_status(match_id: str) -> dict:
    m = store.match(match_id)
    if not m:
        return {"error": f"Unknown match_id '{match_id}'."}
    out = {
        "match_id": m["match_id"], "stage": m["stage"], "teams": f"{m['home']} vs {m['away']}",
        "city": m["city"], "venue": m["venue"], "kickoff": m["kickoff"], "status": m["status"],
        "days_to_kickoff": days_until(m["kickoff"]), "marquee_matchup": m.get("marquee", False),
    }
    if m.get("result"):
        out["result"] = m["result"]
    if m.get("new_kickoff"):
        out["rescheduled_kickoff"] = m["new_kickoff"]
        out["postponement_reason"] = m.get("postponement_reason")
    if m.get("notes"):
        out["notes"] = m["notes"]
    return out


def public_listing(x: dict) -> dict:
    """What any buyer may see (never the barcode status or the seller's hidden floor)."""
    m = store.match(x["match_id"]) or {}
    return {
        "listing_id": x["listing_id"], "match_id": x["match_id"],
        "match": f"{m.get('home')} vs {m.get('away')}", "stage": m.get("stage"), "city": m.get("city"),
        "kickoff": m.get("kickoff"), "category": x["category"], "section": x["section"], "row": x["row"],
        "quantity": x["quantity"], "seats_adjacent": x["seats_adjacent"], "seat_note": x.get("seat_note", ""),
        "price_per_ticket": x["price_per_ticket"], "face_value": x["face_value"], "seller_id": x["seller_id"],
        "description": x["description"],
    }


_STAGE_ALIASES = {"r16": "round of 16", "roundof16": "round of 16", "last16": "round of 16",
                  "r32": "round of 32", "roundof32": "round of 32", "qf": "quarter-final",
                  "quarterfinal": "quarter-final", "quarterfinals": "quarter-final", "group": "group",
                  "groupstage": "group"}


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _stage_ok(wanted: str, actual: str) -> bool:
    w = _norm(wanted)
    w = _norm(_STAGE_ALIASES.get(w, w))
    return w in _norm(actual)


def search_listings(match_id=None, city=None, stage=None, team=None, max_price_per_ticket=None,
                    min_quantity=None, adjacent_only=None) -> list[dict]:
    rows = []
    for x in store.listings():
        if x["status"] != "active":
            continue
        m = store.match(x["match_id"]) or {}
        if match_id and _norm(x["match_id"]) != _norm(match_id):
            continue
        if city and _norm(city) not in _norm(m.get("city", "")):
            continue
        if stage and not _stage_ok(stage, m.get("stage", "")):
            continue
        if team and _norm(team) not in _norm(f"{m.get('home')} {m.get('away')}"):
            continue
        if max_price_per_ticket and x["price_per_ticket"] > max_price_per_ticket:
            continue
        if min_quantity and x["quantity"] < min_quantity:
            continue
        if adjacent_only and not x["seats_adjacent"]:
            continue
        rows.append(public_listing(x))
    return sorted(rows, key=lambda r: (r["match_id"], r["price_per_ticket"]))


def price_history(match_id: str) -> dict:
    ph = store.seed("price_history.json").get(match_id)
    if not ph:
        return {"error": f"No price history for '{match_id}'."}
    s = ph["series"]
    cur, week_ago = s[-1]["median_price"], s[max(0, len(s) - 8)]["median_price"]
    return {
        "match_id": match_id, "current_median": cur, "change_7d_pct": round((cur - week_ago) / week_ago * 100, 1),
        "low": min(p["median_price"] for p in s), "high": max(p["median_price"] for p in s),
        "bracket_events": ph["events"], "series": s,
    }


def seller_profile(seller_id: str) -> dict:
    s = store.seller(seller_id)
    if not s:
        return {"error": f"Unknown seller_id '{seller_id}'."}
    return dict(s)


def price_cap(listing_id: str) -> dict:
    x = store.listing(listing_id)
    if not x:
        return {"error": f"Unknown listing '{listing_id}'."}
    cap = round(x["face_value"] * PRICE_CAP_MULTIPLIER, 2)
    return {"listing_id": listing_id, "face_value": x["face_value"], "cap_multiplier": PRICE_CAP_MULTIPLIER,
            "price_cap_per_ticket": cap, "asking_price": x["price_per_ticket"],
            "ask_exceeds_cap": x["price_per_ticket"] > cap}


def verify_ticket(listing_id: str) -> dict:
    """Mock ticket verification against the organizer's (fake) barcode registry."""
    x = store.listing(listing_id)
    if not x:
        return {"listing_id": listing_id, "verified": False, "reason": "listing not found"}
    status = x.get("barcode_status", "valid")
    reasons = {
        "valid": "Barcodes registered to the seller and not previously transferred.",
        "duplicate_barcode": "Barcode already transferred to another account (likely duplicate/counterfeit).",
        "unregistered": "Barcodes not found in the organizer registry.",
    }
    return {"listing_id": listing_id, "verified": status == "valid", "registry_status": status,
            "reason": reasons.get(status, status), "seller_id": x["seller_id"]}
