"""Record every canonical scenario live, once, for cached demo mode.

Usage (PowerShell):
    $env:OPENAI_API_KEY = "sk-..."      # never hardcode the key
    python scripts/record_all.py              # all scenarios
    python scripts/record_all.py buyer_sofia  # just one

Human approval gates are clicked automatically here ONLY so the post-approval LLM calls (memory
reflection, platform settlement) are captured in the recording. In the app the human clicks them.
Each run also writes recordings/<scenario>.result.json (trace + outcome) as report evidence.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cupswap import buyer_agent, fairdrop, memory, negotiation, operations, store  # noqa: E402
from cupswap.config import RECORDINGS, live_available  # noqa: E402
from cupswap.llm import LLMClient, recording_meta  # noqa: E402
from cupswap.scenarios import BUYER, FAIRDROP, NEGOTIATION, OPS  # noqa: E402
from cupswap.trace import Trace  # noqa: E402
from cupswap.store import save_json  # noqa: E402


def log(ev):
    print(f"  [{ev.step:>2}] {ev.icon} {ev.title[:110]}")


def rec_buyer(sid, cfg):
    store.reset_files(["listings.json", "holds.json", "purchases.json", f"profiles/{cfg['fan_id']}.json"])
    llm = LLMClient("record", sid, inputs=cfg)
    t = Trace(on_event=log)
    before = memory.load(cfg["fan_id"])
    plan = buyer_agent.draft_plan(llm, before, cfg["goal"], t)
    session = buyer_agent.run_react(llm, before, cfg["goal"], plan, t, use_mcp=cfg["use_mcp"])
    rec = session.recommendation
    outcome = "approved" if rec and rec["status"] == "recommend" else "declined"
    buyer_agent.decide_purchase(session, outcome == "approved", t)
    after = buyer_agent.end_session(llm, before, session, outcome, t)
    return {"plan": plan, "recommendation": rec, "memory_before": before, "memory_after": after, "trace": t.to_list()}


def rec_nego(sid, cfg):
    store.reset_files(["listings.json", "settlements.json", "purchases.json"])
    llm = LLMClient("record", sid, inputs=cfg)
    t = Trace(on_event=log)
    setup = negotiation.Setup(cfg["listing_id"], cfg["fan_id"], cfg["quantity"], cfg["ceiling"], cfg["label"])
    state = negotiation.run(llm, setup, t)
    if state["status"] == "deal_pending_approval":
        state["surplus"] = negotiation.surplus(state)
        negotiation.settle(llm, state, t)
    state["leakage"] = negotiation.leakage_report(state)
    return {"state": state, "trace": t.to_list()}


def rec_ops(sid, cfg):
    store.reset_files(["matches.json", "refunds.json", "ops_cases.json", "account_flags.json"])
    llm = LLMClient("record", sid, inputs=cfg)
    return operations.run_workflow(llm, progress=lambda m: print("  ", m))


def rec_fairdrop(sid, cfg):
    store.reset_files(["fairdrop_allocations.json"])
    llm = LLMClient("record", sid, inputs=cfg)
    return fairdrop.run(llm, progress=lambda m: print("  ", m))


def main():
    if not live_available():
        sys.exit("OPENAI_API_KEY is not set. Set it as an environment variable (never in code).")
    store.ensure_state()
    wanted = set(sys.argv[1:])
    plan = [(BUYER, rec_buyer), (NEGOTIATION, rec_nego), (OPS, rec_ops), (FAIRDROP, rec_fairdrop)]
    for group, fn in plan:
        for sid, cfg in group.items():
            if wanted and sid not in wanted:
                continue
            print(f"\n=== recording {sid}: {cfg['label']}")
            result = fn(sid, cfg)
            save_json(RECORDINGS / f"{sid}.result.json", result)
            meta = recording_meta(sid)
            print(f"   saved: {meta['calls']} LLM calls, {meta['prompt_tokens']}+{meta['completion_tokens']} tokens, "
                  f"${meta['cost_usd']:.4f}")
    store.reset_state()
    print("\nDone. Demo state reset. Cached mode now replays these recordings without an API key.")


if __name__ == "__main__":
    main()
