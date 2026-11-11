"""Central configuration: paths, model, and every hard cap / threshold in one place."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE = ROOT / "state"            # mutable mock "databases" (all state-changing tools write here)
RECORDINGS = ROOT / "recordings"  # canonical recorded runs used by cached demo mode
LIVE_RUNS = RECORDINGS / "live"   # every live-mode run is also saved here as evidence

MODEL = os.getenv("CUPSWAP_MODEL", "gpt-4o-mini")
# gpt-4o-mini list prices (USD per 1M tokens), used only for the on-screen cost meter.
PRICE_IN_PER_M = 0.15
PRICE_OUT_PER_M = 0.60

# Demo clocks (the scenario is set in June/July 2026).
BUYER_CLOCK = "2026-07-02T09:00"   # Buyer Agent + Negotiation Arena + Fair-Drop
OPS_CLOCK = "2026-06-24T19:45"     # Operations Desk: storm night in Miami

# ---- Hard caps (required safety rails: no runaway agent can burn tokens) ----
BUYER_MAX_STEPS = 10           # LLM turns in the buyer ReAct loop
BUYER_MAX_TOOL_CALLS = 14      # total tool executions per buyer session
PLATFORM_MAX_STEPS = 4         # LLM turns for each platform-agent tool loop
NEGOTIATION_MAX_ROUNDS = 5     # alternating-offer rounds
LLM_MAX_TOKENS = 700           # per call

# ---- Marketplace rules (enforced by the platform agent / rule engine) ----
PRICE_CAP_MULTIPLIER = 1.5     # resale price may not exceed 150% of face value (organizer rule)
PLATFORM_FEE_RATE = 0.08       # 8% fee deducted from seller proceeds at settlement
HOLD_MINUTES = 15              # holds are reversible and expire on their own

# ---- Operations desk ----
REFUND_APPROVAL_THRESHOLD = 500.0   # refunds strictly above this wait for a human click
CLASSIFIER_MIN_CONFIDENCE = 0.75    # below this the case is escalated to a human

# ---- Fair-Drop ----
FAIRDROP_SEED = 2026                # published lottery seed so the draw is reproducible/auditable


def live_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))
