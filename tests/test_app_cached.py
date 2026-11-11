"""Headless end-to-end test of the UI in cached mode (no API key), using Streamlit AppTest.

Run:  python -m pytest tests -q      (or:  python tests/test_app_cached.py)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.pop("OPENAI_API_KEY", None)  # prove cached mode needs no key

from streamlit.testing.v1 import AppTest  # noqa: E402

from cupswap import store  # noqa: E402

HARNESS = ROOT / "tests" / "_page_harness.py"


def _app(page: str) -> AppTest:
    at = AppTest.from_file(str(HARNESS), default_timeout=180)
    at.session_state["replay_delay"] = 0.0
    at.query_params["page"] = page
    at.run()
    assert not at.exception, at.exception
    return at


def _click(at: AppTest, label_part: str) -> AppTest:
    btn = next(b for b in at.button if label_part in b.label)
    btn.click().run()
    assert not at.exception, at.exception
    return at


def _texts(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown) + " " + " ".join(getattr(s, "value", "") for s in at.success)


def test_overview_and_audit():
    store.reset_state()
    _app("overview")
    _app("audit")


def test_buyer_flow_both_fans():
    store.reset_state()
    for idx, fan in enumerate(["sofia", "julien"]):
        at = _app("buyer")
        at.selectbox(key="buyer_sid").select_index(idx).run()
        _click(at, "Draft a plan")
        _click(at, "Approve plan")
        assert "Recommendation submitted" in _texts(at) or at.metric
        _click(at, "Approve purchase")
        assert any("Mock purchase" in s.value for s in at.success), "purchase not confirmed"
        assert "AFTER this session" in _texts(at)
        at.session_state["buyer"] = {"phase": "idle"}
    assert len(store.state("purchases.json")) == 2


def test_negotiation_success_and_failure():
    store.reset_state()
    at = _app("negotiation")
    at.selectbox(key="nego_sid").select_index(0).run()
    _click(at, "Run negotiation")
    _click(at, "Approve purchase")
    assert any("Settled by the platform agent" in s.value for s in at.success)
    at.session_state["nego"] = {"phase": "idle"}
    at.selectbox(key="nego_sid").select_index(1).run()
    _click(at, "Run negotiation")
    assert any("No agreement" in w.value for w in at.warning)


def test_operations_desk():
    store.reset_state()
    at = _app("operations")
    _click(at, "Ingest weather feed")
    cases = store.state("ops_cases.json")["cases"]
    statuses = {c["status"] for c in cases.values()}
    assert "auto_refunded" in statuses and "awaiting_approval" in statuses
    assert any("R4" in r for c in cases.values() for r in c["rules_fired"])
    assert any("R5" in r for c in cases.values() for r in c["rules_fired"])
    _click(at, "Approve $")  # first gated refund
    assert any(c["status"] == "refunded_after_approval" for c in store.state("ops_cases.json")["cases"].values())


def test_fairdrop():
    store.reset_state()
    at = _app("fairdrop")
    _click(at, "Close the window")
    _click(at, "Approve allocation")
    assert len(store.state("fairdrop_allocations.json")) > 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
    store.reset_state()
