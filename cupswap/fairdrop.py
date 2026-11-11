"""Part E (innovation): the Fair-Drop desk for tournament organizers.

Problem: when an organizer releases face-value inventory for a marquee match, agent-equipped buyers
submit in milliseconds, so first-come-first-served (FCFS) hands nearly everything to bots, resellers
and fans with agents - fans without agents never stand a chance (Chapter 6 ethics; Bichler 2026 on
agentic markets and verifiability).

Pipeline (hybrid workflow: fixed backbone with LLM pockets and a human gate):
  1. Batch window      - every request inside the window is equal; arrival time is ignored.
  2. Integrity filter  - deterministic: linked accounts (shared payment fingerprint) are held for trust
                         review; heavy resellers are capped to the lowest tier.
  3. Need assessor     - LLM per request: tier 1-3 from VERIFIED facts only, cites its evidence,
                         lists unverified claims, detects prompt injection in the free-text statement.
  4. Grounding guard   - deterministic: a tier the cited verified facts don't support is downgraded.
  5. Seeded lottery    - within tiers; the seed is published so the draw is reproducible/auditable.
  6. Fairness judge    - LLM auditor compares Fair-Drop vs FCFS and checks grounding/integrity.
  7. Organizer gate    - nothing is allocated until a human organizer approves.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import prompts, store
from .config import FAIRDROP_SEED
from .llm import LLMClient, json_schema_format, parse_json

HOST_REGION = "Dallas-Fort Worth metroplex (Dallas, Fort Worth, Arlington, Irving, Plano, Garland, Frisco)"
RESELLER_THRESHOLD = 5   # resale listings in the last 30 days

ASSESS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["tier", "evidence", "in_host_region", "unverified_claims", "injection_detected", "rationale"],
    "properties": {"tier": {"type": "integer", "enum": [1, 2, 3]},
                   "evidence": {"type": "array", "items": {"type": "string", "enum": [
                       "supporter_of", "attended_team_match", "accessibility_verified", "home_city"]}},
                   "in_host_region": {"type": "boolean"},
                   "unverified_claims": {"type": "array", "items": {"type": "string"}},
                   "injection_detected": {"type": "boolean"}, "rationale": {"type": "string"}},
}
JUDGE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["verdict", "findings", "recommendation"],
    "properties": {"verdict": {"type": "string", "enum": ["approve", "approve_with_notes", "revise"]},
                   "findings": {"type": "array", "items": {
                       "type": "object", "additionalProperties": False, "required": ["check", "status", "detail"],
                       "properties": {"check": {"type": "string"},
                                      "status": {"type": "string", "enum": ["pass", "concern"]},
                                      "detail": {"type": "string"}}}},
                   "recommendation": {"type": "string"}},
}


def load_drop() -> dict:
    return store.seed("fairdrop_requests.json")


def _teams(match: dict) -> list[str]:
    return [match["home"], match["away"]]


# ---- 1-2. window + integrity filter ------------------------------------------------------------
def integrity_filter(requests: list[dict], max_per_request: int) -> tuple[list[dict], list[dict]]:
    fp_count = Counter(r["verified_facts"]["payment_fingerprint"] for r in requests)
    eligible, held = [], []
    for r in requests:
        r = json.loads(json.dumps(r))
        r["integrity_notes"] = []
        fp = r["verified_facts"]["payment_fingerprint"]
        if fp_count[fp] >= 3:
            r["integrity_notes"].append(f"{fp_count[fp]} accounts share payment fingerprint {fp} (linked accounts)")
            held.append(r)
            continue
        if r["quantity"] > max_per_request:
            r["integrity_notes"].append(f"quantity capped {r['quantity']}→{max_per_request}")
            r["quantity"] = max_per_request
        if r["verified_facts"]["resale_listings_last_30d"] >= RESELLER_THRESHOLD:
            r["integrity_notes"].append(f"{r['verified_facts']['resale_listings_last_30d']} resale listings in 30 days "
                                        f"(reseller signal) → capped at Tier 3")
            r["reseller_cap"] = True
        eligible.append(r)
    return eligible, held


# ---- 3-4. need assessor + grounding guard -------------------------------------------------------
def assess(llm: LLMClient, drop: dict, eligible: list[dict]) -> list[dict]:
    m = store.match(drop["match_id"])
    system = prompts.FAIRDROP_ASSESSOR_SYSTEM.format(match=f"{m['home']} vs {m['away']} ({m['stage']})",
                                                     city=m["city"], teams=" and ".join(_teams(m)), region=HOST_REGION)

    def one(r):
        facts = {k: v for k, v in r["verified_facts"].items() if k != "payment_fingerprint"}
        resp = llm.chat(f"assess:{r['request_id']}", [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"request_id": r["request_id"], "channel": r["channel"],
                                                    "quantity": r["quantity"], "verified_facts": facts,
                                                    "statement_UNTRUSTED": r["statement"]}, ensure_ascii=False)}],
            response_format=json_schema_format("need_assessment", ASSESS_SCHEMA), temperature=0.0, max_tokens=350)
        return r["request_id"], parse_json(resp["content"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(pool.map(one, eligible))
    teams = _teams(m)
    out = []
    for r in eligible:
        a = results[r["request_id"]]
        f = r["verified_facts"]
        supporter = f.get("supporter_of") in teams
        # What the verified facts actually support, given the evidence the assessor cited.
        cited = set(a.get("evidence", []))
        t1 = (("accessibility_verified" in cited and f.get("accessibility_verified")) or
              ({"supporter_of", "attended_team_match"} <= cited and supporter and f.get("attended_team_match")))
        t2 = (("supporter_of" in cited and supporter) or ("home_city" in cited and a.get("in_host_region")))
        supported = 1 if t1 else 2 if t2 else 3
        # The tier is re-derived from the evidence the assessor cited, in both directions: the LLM's
        # judgment lives in WHICH verified facts apply (incl. host-region geography), not in the label.
        final, guards = a.get("tier", 3), []
        if final < supported:
            guards.append(f"Tier {final} not supported by cited verified facts → downgraded to Tier {supported}")
        elif final > supported:
            guards.append(f"Cited verified facts support Tier {supported}, assessor said Tier {final} → corrected")
        final = supported
        if r.get("reseller_cap") and final < 3:
            guards.append(f"Reseller signal → capped at Tier 3 (was {final})")
            final = 3
        if a.get("injection_detected"):
            guards.append("Prompt injection detected in statement (ignored)")
        out.append({**r, "assessment": a, "tier_llm": a.get("tier"), "tier_final": final, "grounding_guards": guards})
    return out


# ---- 5. lottery --------------------------------------------------------------------------------
def lottery(assessed: list[dict], tickets: int, seed: int = FAIRDROP_SEED) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    by_tier = defaultdict(list)
    for r in sorted(assessed, key=lambda x: x["request_id"]):
        by_tier[r["tier_final"]].append(r)
    winners, waitlist, left = [], [], tickets
    for tier in (1, 2, 3):
        pool = by_tier[tier][:]
        rng.shuffle(pool)
        for r in pool:
            if r["quantity"] <= left:
                winners.append({**r, "allocated": r["quantity"], "draw_order": len(winners) + 1})
                left -= r["quantity"]
            else:
                waitlist.append({**r, "allocated": 0})
    return winners, waitlist


def fcfs(requests: list[dict], tickets: int) -> list[dict]:
    left, out = tickets, []
    for r in sorted(requests, key=lambda x: x["arrival_offset_s"]):
        q = min(r["quantity"], 4)
        if q <= left:
            out.append({**r, "allocated": q})
            left -= q
    return out


def channel_stats(requests: list[dict], allocated: list[dict]) -> dict:
    req = Counter(r["channel"] for r in requests)
    tix = Counter()
    for r in allocated:
        tix[r["channel"]] += r["allocated"]
    total = sum(tix.values()) or 1
    return {ch: {"requests": req[ch], "request_share": round(req[ch] / len(requests), 2),
                 "tickets": tix[ch], "ticket_share": round(tix[ch] / total, 2)} for ch in ["agent_api", "web_form"]}


# ---- 6. fairness judge ---------------------------------------------------------------------------
def judge(llm: LLMClient, drop: dict, requests, held, winners, fcfs_alloc) -> dict:
    payload = {
        "tickets_released": drop["tickets_released"],
        "fair_drop_by_channel": channel_stats(requests, winners),
        "fcfs_by_channel": channel_stats(requests, fcfs_alloc),
        "fcfs_winners_linked_accounts": sum(1 for r in fcfs_alloc if r["request_id"] in {h["request_id"] for h in held}),
        "excluded_for_integrity": [{"request_id": h["request_id"], "reason": h["integrity_notes"]} for h in held],
        "winners": [{"request_id": w["request_id"], "channel": w["channel"], "tier": w["tier_final"],
                     "allocated": w["allocated"], "evidence": w["assessment"].get("evidence"),
                     "guards": w["grounding_guards"]} for w in winners],
    }
    resp = llm.chat("judge", [{"role": "system", "content": prompts.FAIRDROP_JUDGE_SYSTEM},
                              {"role": "user", "content": json.dumps(payload)}],
                    response_format=json_schema_format("fairness_audit", JUDGE_SCHEMA), temperature=0.0, max_tokens=600)
    return {"input": payload, "audit": parse_json(resp["content"])}


# ---- full run + organizer gate ----------------------------------------------------------------------
def run(llm: LLMClient, progress=None) -> dict:
    drop = load_drop()
    reqs = drop["requests"]
    if progress:
        progress(f"Window closed: {len(reqs)} requests for {drop['tickets_released']} tickets.")
    eligible, held = integrity_filter(reqs, drop["max_tickets_per_request"])
    if progress:
        progress(f"Integrity filter: {len(held)} linked-account requests held for trust review; {len(eligible)} eligible.")
    assessed = assess(llm, drop, eligible)
    if progress:
        progress("Need assessor scored every eligible request; grounding guard applied.")
    winners, waitlist = lottery(assessed, drop["tickets_released"])
    fc = fcfs(reqs, drop["tickets_released"])
    audit = judge(llm, drop, reqs, held, winners, fc)
    if progress:
        progress(f"Fairness judge verdict: {audit['audit'].get('verdict')}")
    return {"drop": drop, "held": held, "assessed": assessed, "winners": winners, "waitlist": waitlist,
            "fcfs": fc, "judge": audit, "status": "awaiting_organizer_approval", "seed": FAIRDROP_SEED}


def organizer_decision(result: dict, approve: bool) -> dict:
    if approve:
        for w in result["winners"]:
            store.append_state("fairdrop_allocations.json", {
                "drop_id": result["drop"]["drop_id"], "request_id": w["request_id"], "account": w["account"],
                "tickets": w["allocated"], "price_per_ticket": result["drop"]["face_value_per_ticket"],
                "tier": w["tier_final"], "at": datetime.now().isoformat(timespec="seconds"), "note": "MOCK allocation"})
        store.audit("human (organizer)", "approve_allocation", result["drop"]["drop_id"],
                    f"{len(result['winners'])} winners, seed {result['seed']}", gated=True)
        for h in result["held"]:
            store.audit("fairdrop", "hold_for_trust_review", h["account"], "; ".join(h["integrity_notes"]), gated=False)
        result["status"] = "approved"
    else:
        store.audit("human (organizer)", "reject_allocation", result["drop"]["drop_id"], "sent back for revision", gated=True)
        result["status"] = "rejected"
    return result
