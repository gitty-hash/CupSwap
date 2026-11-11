"""Tiny JSON-file "database". Seed data lives in data/, mutable state in state/.

Every state-changing mock action also appends a line to state/audit_log.jsonl so a
human can audit what changed, who (which agent or human) changed it, and why.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DATA, STATE

_LOCK = threading.Lock()

SEEDED_FILES = ["matches.json", "listings.json"]
EMPTY_LISTS = ["holds.json", "purchases.json", "settlements.json", "refunds.json",
               "account_flags.json", "fairdrop_allocations.json"]
EMPTY_DICTS = ["ops_cases.json"]


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, obj: Any) -> None:
    """Atomic-ish write that tolerates OneDrive/antivirus briefly locking the file on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    for attempt in range(6):
        try:
            tmp.write_text(text, encoding="utf-8")
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.15 * (attempt + 1))
    path.write_text(text, encoding="utf-8")  # last resort: direct write
    try:
        tmp.unlink(missing_ok=True)
    except PermissionError:
        pass


def seed(name: str) -> Any:
    return load_json(DATA / name)


def state(name: str, default: Any = None) -> Any:
    ensure_state()
    return load_json(STATE / name, default)


def write_state(name: str, obj: Any) -> None:
    with _LOCK:
        save_json(STATE / name, obj)


def append_state(name: str, item: dict) -> None:
    with _LOCK:
        items = load_json(STATE / name, []) or []
        items.append(item)
        save_json(STATE / name, items)


def audit(actor: str, action: str, target: str, detail: str, gated: bool) -> None:
    line = {"at": datetime.now().isoformat(timespec="seconds"), "actor": actor, "action": action,
            "target": target, "detail": detail,
            "control": "human-approved" if gated else "auto (monitored)"}
    with _LOCK:
        STATE.mkdir(parents=True, exist_ok=True)
        with open(STATE / "audit_log.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")


def read_audit() -> list[dict]:
    p = STATE / "audit_log.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def reset_state() -> None:
    """Restore every mutable file to its seed version (used by 'Reset demo data')."""
    # Overwrite files in place instead of deleting folders: OneDrive/antivirus can lock directories.
    with _LOCK:
        (STATE / "profiles").mkdir(parents=True, exist_ok=True)
        for name in SEEDED_FILES:
            shutil.copyfile(DATA / name, STATE / name)
        for p in (DATA / "profiles").glob("*.json"):
            shutil.copyfile(p, STATE / "profiles" / p.name)
        for name in EMPTY_LISTS:
            save_json(STATE / name, [])
        for name in EMPTY_DICTS:
            save_json(STATE / name, {})
        (STATE / "audit_log.jsonl").write_text("", encoding="utf-8")


def reset_files(names: list[str]) -> None:
    """Reset a subset of state (each scenario starts from a clean, reproducible state)."""
    ensure_state()
    with _LOCK:
        for name in names:
            if name in SEEDED_FILES:
                shutil.copy(DATA / name, STATE / name)
            elif name in EMPTY_LISTS:
                save_json(STATE / name, [])
            elif name in EMPTY_DICTS:
                save_json(STATE / name, {})
            elif name.startswith("profiles/"):
                shutil.copy(DATA / name, STATE / name)


def ensure_state() -> None:
    if not (STATE / "matches.json").exists():
        reset_state()


# ---- convenience lookups over seed + state -------------------------------------------------
def matches() -> list[dict]:
    return state("matches.json", [])


def match(match_id: str) -> dict | None:
    return next((m for m in matches() if m["match_id"] == match_id), None)


def listings() -> list[dict]:
    return state("listings.json", [])


def listing(listing_id: str) -> dict | None:
    return next((x for x in listings() if x["listing_id"] == listing_id), None)


def sellers() -> list[dict]:
    return seed("sellers.json")


def seller(seller_id: str) -> dict | None:
    return next((s for s in sellers() if s["seller_id"] == seller_id), None)


def match_label(m: dict) -> str:
    return f"{m['home']} vs {m['away']} ({m['stage']}, {m['city']})"
