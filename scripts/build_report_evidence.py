"""Extract report-ready FACTS (quotes, numbers, outcomes) from the recorded runs into report/REPORT_EVIDENCE.md.

This is an evidence pack, not the report: the interpretation, autonomy reasoning, failure diagnosis and ethics
discussion must be written by the student (HW3 Section 9).
Run:  python scripts/build_report_evidence.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cupswap.config import (PLATFORM_FEE_RATE, PRICE_CAP_MULTIPLIER, REFUND_APPROVAL_THRESHOLD,  # noqa: E402
                            RECORDINGS)
from cupswap.llm import recording_meta  # noqa: E402
from cupswap.scenarios import ALL  # noqa: E402


def load(name):
    return json.loads((RECORDINGS / f"{name}.result.json").read_text(encoding="utf-8"))


def buyer_section(sid):
    r = load(sid)
    out = [f"### {ALL[sid]['label']}\n", f"Request: “{ALL[sid]['goal']}”\n",
           f"Plan constraints: `{json.dumps(r['plan']['constraints'])}`  ", f"Memory applied in plan: {r['plan'].get('memory_applied')}\n",
           "| step | think | act | observe |", "|---|---|---|---|"]
    steps = {}
    for e in r["trace"]:
        if e["kind"] in {"think", "act", "observe"}:
            steps.setdefault(e["step"], {})[e["kind"]] = (e["title"] if e["kind"] == "act" else e["detail"]).replace("|", "/")
        if e["kind"] == "guard":
            steps.setdefault(e["step"], {})["guard"] = e["title"]
    for s, d in steps.items():
        obs = d.get("observe", "") + (f" **[{d['guard']}]**" if "guard" in d else "")
        out.append(f"| {s} | {d.get('think', '')} | `{d.get('act', '')}` | {obs} |")
    rec = r["recommendation"] or {}
    out += ["", f"**Recommendation:** {rec.get('listing_id')} ×{rec.get('quantity')} = ${rec.get('total_price')} — "
            f"{rec.get('why_this_listing')}", "", "Rejected alternatives:"]
    out += [f"- {a['listing_id']}: {a['reason']}" for a in rec.get("alternatives_rejected", [])]
    out += ["", f"Memory factors cited: {rec.get('memory_factors')}", ""]
    mem = next((e for e in r["trace"] if e["kind"] == "memory" and isinstance(e.get("data"), list)), None)
    if mem:
        out.append("Memory diff at session end:")
        out += [f"- {d['field']} ({d['change']}): {d['value']}" for d in mem["data"]]
    return "\n".join(out) + "\n"


def nego_section(sid):
    r = load(sid)
    st = r["state"]
    p = st["_private"]
    out = [f"### {ALL[sid]['label']}\n",
           f"Private limits (hidden from the counterparty): seller floor ${p['seller_floor']} "
           f"(base ${p['base_floor']} × marquee {p['marquee_adjustment']}), buyer ceiling ${p['buyer_ceiling']}, "
           f"buyer anchor ${p.get('buyer_anchor')}, kickoff in {p['days_to_kickoff']} days → seller concession rate "
           f"{p['concession_rate']}/round. Price cap ${st['rules']['price_cap_per_ticket']} ({PRICE_CAP_MULTIPLIER}× face); "
           f"platform ruling: verified={st['ruling'].get('verified')}, opening ${st['ruling'].get('enforced_opening_price')} "
           f"(ask capped: {st['ruling'].get('ask_capped')}).\n",
           "| round | role | action | $/ticket | message | guards |", "|---|---|---|---|---|---|"]
    for h in st["history"]:
        out.append(f"| {h['round']} | {h['role']} | {h['action']} | {h['price_per_ticket']} | "
                   f"{h['message'].replace('|', '/')} | {'; '.join(h.get('guards', []))} |")
    out.append(f"\n**Outcome:** {st['status']}" + (f" at ${st['deal_price_per_ticket']}" if st.get("deal_price_per_ticket") else ""))
    if st.get("surplus"):
        s = st["surplus"]
        out.append(f"\nSurplus split: buyer ${s['buyer_surplus']}, seller after fee ${s['seller_surplus_after_fee']}, "
                   f"platform fee ${s['platform_fee']} (fee rate {PLATFORM_FEE_RATE:.0%}); ZOPA ${s['zopa_per_ticket']}/ticket.")
    if st.get("settlement"):
        out.append(f"Settlement recorded: {st['settlement']}")
    out.append("\nLeakage test results:")
    out += [f"- round {l['round']} {l['role']}: {l['type']} — “{l['evidence']}”" for l in st.get("leakage", [])] or ["- none"]
    return "\n".join(out) + "\n"


def ops_section():
    r = load("ops_postponement")
    out = [f"Event: {r['event']['reason']} {r['event']['original_kickoff']} → {r['event']['new_kickoff']}. "
           f"Approval threshold ${REFUND_APPROVAL_THRESHOLD:,.0f}.\n",
           "| order | amount | language | classifier route (conf) | attends | final route | status | cited policy | rules fired |",
           "|---|---|---|---|---|---|---|---|---|"]
    for c in r["cases"].values():
        cl = c["classification"]
        out.append(f"| {c['order_id']} | ${c['amount']} | {cl.get('language')} | {c['route_initial']} ({cl.get('confidence')}) | "
                   f"{cl.get('attends_new_date')} | {c['route_final']} | {c['status']} | {c['policy']['policy_id']} §{c['policy']['section']} | "
                   f"{'; '.join(c['rules_fired']) or '—'} |")
    for oid in ["O-1010", "O-1014", "O-1009"]:
        c = r["cases"][oid]
        out.append(f"\n**{oid} timeline** — message: “{c['message']}”")
        out += [f"- [{t['node']}] {t['text']}" for t in c["timeline"]]
    return "\n".join(out) + "\n"


def fairdrop_section():
    r = load("fairdrop_r16dal")
    from cupswap.fairdrop import channel_stats
    reqs = r["drop"]["requests"]
    fc, fd = channel_stats(reqs, r["fcfs"]), channel_stats(reqs, r["winners"])
    out = [f"{r['drop']['tickets_released']} tickets, {len(reqs)} requests (10 agent_api, 10 web_form). Lottery seed {r['seed']}.\n",
           f"- FCFS: agent_api {fc['agent_api']['tickets']} tickets, web_form {fc['web_form']['tickets']} tickets; FCFS winners: "
           f"{[x['request_id'] for x in r['fcfs']]}",
           f"- Fair-Drop: agent_api {fd['agent_api']['tickets']} tickets, web_form {fd['web_form']['tickets']} tickets; winners: "
           f"{[(w['request_id'], w['channel'], 'T' + str(w['tier_final'])) for w in r['winners']]}",
           f"- Held for trust review (linked accounts): {[h['request_id'] for h in r['held']]}",
           "- Grounding guards / injection: " + "; ".join(f"{a['request_id']}: {g}" for a in r["assessed"] for g in a["grounding_guards"]),
           f"- Judge verdict: {r['judge']['audit'].get('verdict')}"]
    out += [f"  - {f['check']} ({f['status']}): {f['detail']}" for f in r["judge"]["audit"].get("findings", [])]
    return "\n".join(out) + "\n"


def cost_section():
    rows, total = [], 0.0
    for sid in ALL:
        m = recording_meta(sid)
        if m:
            total += m["cost_usd"]
            rows.append(f"| {sid} | {m['calls']} | {m['prompt_tokens'] + m['completion_tokens']:,} | ${m['cost_usd']:.4f} |")
    return "\n".join(["| scenario | LLM calls | tokens | cost |", "|---|---|---|---|", *rows,
                      f"| **total (canonical recordings)** | | | **${total:.4f}** |"]) + "\n"


def main():
    parts = ["# CupSwap — report evidence pack (facts extracted from the recorded live runs)\n",
             "> Facts only. The interpretation (why the agent did what it did, who captured the surplus and why, what the "
             "failures teach, your autonomy reasoning and ethics) is yours to write — see report/REPORT_TEMPLATE.md.\n",
             "## Part B — Buyer agent traces (same request, two memories)\n",
             buyer_section("buyer_sofia"), buyer_section("buyer_julien"),
             "## Part C — Negotiation arena\n", nego_section("nego_success"), nego_section("nego_failure"),
             "## Part D — Operations desk\n", ops_section(),
             "## Part E — Fair-Drop desk\n", fairdrop_section(),
             "## API cost of the recordings\n", cost_section()]
    out = ROOT / "report" / "REPORT_EVIDENCE.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
