"""Renders one page by name (used by the AppTest suite; the real app uses st.navigation)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from cupswap import store  # noqa: E402
from ui import page_audit, page_buyer, page_fairdrop, page_negotiation, page_ops, page_overview  # noqa: E402
from ui.common import sidebar  # noqa: E402

store.ensure_state()
sidebar()
{"overview": page_overview.page, "buyer": page_buyer.page, "negotiation": page_negotiation.page,
 "operations": page_ops.page, "fairdrop": page_fairdrop.page, "audit": page_audit.page}[st.query_params.get("page", "overview")]()
