"""CupSwap control room — run with:  streamlit run app.py"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cupswap import store  # noqa: E402
from ui import page_audit, page_buyer, page_fairdrop, page_negotiation, page_ops, page_overview  # noqa: E402
from ui import common  # noqa: E402
from ui.common import sidebar  # noqa: E402

st.set_page_config(page_title="CupSwap control room", page_icon="⚽", layout="wide")
store.ensure_state()
sidebar()

pages = [
    st.Page(page_overview.page, title="Overview", icon=":material/space_dashboard:", url_path="overview", default=True),
    st.Page(page_buyer.page, title="Buyer Agent", icon=":material/shopping_bag:", url_path="buyer"),
    st.Page(page_negotiation.page, title="Negotiation Arena", icon=":material/handshake:", url_path="negotiation"),
    st.Page(page_ops.page, title="Operations Desk", icon=":material/thunderstorm:", url_path="operations"),
    st.Page(page_fairdrop.page, title="Fair-Drop Desk", icon=":material/balance:", url_path="fairdrop"),
    st.Page(page_audit.page, title="Audit Log", icon=":material/fact_check:", url_path="audit"),
]
common.PAGES = {p.url_path: p for p in pages}
st.navigation(pages, position="top").run()
