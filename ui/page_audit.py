"""Audit log + mock ledgers: every state change, who made it, and whether a human approved it."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from cupswap import store
from ui.style import hero, kpis, section


def page() -> None:
    hero("Auditability", "Audit Log & Mock Ledgers",
         "Agents act on people's behalf, so every state-changing action leaves a record a human can read: what "
         "changed, which agent or human changed it, and whether it went through an approval gate.",
         ["Append-only log", "Human-approved vs monitored", "Mock ledgers only — no real money"])
    log = store.read_audit()
    gated = sum(1 for x in log if x["control"] == "human-approved")
    kpis([("Logged actions", len(log), "this demo session", "blue"),
          ("Human-approved", gated, "passed an approval gate", "red"),
          ("Automatic, monitored", len(log) - gated, "visible here and in the desks", "green")])
    section("Audit log", "Newest first")
    if log:
        df = pd.DataFrame(log)[["at", "actor", "action", "target", "detail", "control"]]
        df.columns = ["Time", "Actor", "Action", "Target", "Detail", "Control"]
        st.dataframe(df.iloc[::-1], hide_index=True, width="stretch")
    else:
        st.info("No state-changing actions yet. Run a desk to populate the log.")
    section("Mock ledgers", "The local files every state-changing tool writes to")
    tabs = st.tabs(["Holds", "Purchases", "Settlements", "Refunds", "Account flags", "Fair-Drop allocations"])
    for tab, name in zip(tabs, ["holds.json", "purchases.json", "settlements.json", "refunds.json",
                                "account_flags.json", "fairdrop_allocations.json"]):
        with tab:
            rows = store.state(name, [])
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            else:
                st.caption(f"state/{name} is empty.")
