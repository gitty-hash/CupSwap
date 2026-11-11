"""Canonical demo scenarios. Cached mode replays exactly these; live mode can run them or custom inputs."""
from __future__ import annotations

BUYER_GOAL = "Get me two tickets together for a Round-of-16 match, under $400 total."

BUYER = {
    "buyer_sofia": {"label": "Sofía — Mexico supporter based in Dallas", "fan_id": "sofia", "goal": BUYER_GOAL, "use_mcp": True},
    "buyer_julien": {"label": "Julien — France supporter based in New York", "fan_id": "julien", "goal": BUYER_GOAL, "use_mcp": True},
}

NEGOTIATION = {
    "nego_success": {"label": "Deal: Sofía's agent × listing L10 (Mexico vs Netherlands, Dallas, ask above cap)",
                     "listing_id": "L10", "fan_id": "sofia", "quantity": 2, "ceiling": 190.0},
    "nego_failure": {"label": "No deal: Julien's agent × listing L19 (France vs Portugal, seller floor > buyer ceiling)",
                     "listing_id": "L19", "fan_id": "julien", "quantity": 2, "ceiling": 300.0},
}

OPS = {"ops_postponement": {"label": "Storm postpones Brazil vs Morocco in Miami (14 affected orders)"}}

FAIRDROP = {"fairdrop_r16dal": {"label": "Organizer late release: 16 tickets for Mexico vs Netherlands (Dallas)"}}

ALL = {**BUYER, **NEGOTIATION, **OPS, **FAIRDROP}
