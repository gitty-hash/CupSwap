"""One LLM client for every agent, with three modes:

* ``live``   - calls the OpenAI API (key read from the OPENAI_API_KEY env var, never hardcoded)
               and saves the run under recordings/live/ as evidence.
* ``record`` - same as live but writes the canonical recording used by cached mode.
* ``cached`` - no API key needed: every LLM response is replayed from the recording, keyed by
               an explicit call key (e.g. "react:3", "seller:r2", "classify:O-1009").

Only the *model* is replayed. Tools, guards, rule engines and state changes run for real
against the local mock data, so cached mode exercises the same code path as live mode.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Any, Callable

from .config import LIVE_RUNS, LLM_MAX_TOKENS, MODEL, PRICE_IN_PER_M, PRICE_OUT_PER_M, RECORDINGS
from .store import load_json, save_json


class CacheMiss(RuntimeError):
    pass


class LLMClient:
    def __init__(self, mode: str, scenario: str, inputs: dict | None = None,
                 usage_sink: Callable[[dict], None] | None = None):
        assert mode in {"live", "record", "cached"}, mode
        self.mode = mode
        self.scenario = scenario
        self.usage_sink = usage_sink
        self._lock = threading.Lock()
        self.model = MODEL
        if mode == "cached":
            path = RECORDINGS / f"{scenario}.json"
            rec = load_json(path)
            if rec is None:
                raise CacheMiss(f"No recording for scenario '{scenario}'. Run scripts/record_all.py with an API key.")
            self.recording = rec
            self.model = rec.get("model", MODEL)
            self.path = path
        else:
            from openai import OpenAI  # imported lazily so cached mode needs no key at all
            self._client = OpenAI()
            if mode == "record":
                self.path = RECORDINGS / f"{scenario}.json"
            else:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                self.path = LIVE_RUNS / f"{scenario}__{stamp}.json"
            self.recording = {"scenario": scenario, "model": MODEL, "mode": mode,
                              "recorded_at": datetime.now().isoformat(timespec="seconds"),
                              "inputs": inputs or {}, "calls": {}}
            save_json(self.path, self.recording)

    # ------------------------------------------------------------------------------------------
    def chat(self, key: str, messages: list[dict], tools: list[dict] | None = None,
             response_format: dict | None = None, temperature: float = 0.3,
             max_tokens: int = LLM_MAX_TOKENS) -> dict:
        """Return a normalized response: {content, tool_calls:[{id,name,arguments}], finish_reason}."""
        if self.mode == "cached":
            call = self.recording.get("calls", {}).get(key)
            if call is None:
                raise CacheMiss(f"Recording '{self.scenario}' has no response for call '{key}'. "
                                f"Cached mode can only replay the recorded scenario path.")
            if self.usage_sink:
                self.usage_sink({"replayed": True, "prompt_tokens": 0, "completion_tokens": 0})
            return call["response"]

        kwargs: dict[str, Any] = dict(model=self.model, messages=messages, temperature=temperature,
                                      max_tokens=max_tokens)
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = False  # one action per step keeps the trace readable
        if response_format:
            kwargs["response_format"] = response_format
        t0 = time.time()
        r = self._client.chat.completions.create(**kwargs)
        msg = r.choices[0].message
        norm = {
            "content": msg.content,
            "tool_calls": [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                           for tc in (msg.tool_calls or [])],
            "finish_reason": r.choices[0].finish_reason,
        }
        usage = {"prompt_tokens": r.usage.prompt_tokens, "completion_tokens": r.usage.completion_tokens,
                 "latency_s": round(time.time() - t0, 2)}
        with self._lock:
            self.recording["calls"][key] = {"response": norm, "usage": usage,
                                            "last_user_or_tool_msg": _tail(messages)}
            save_json(self.path, self.recording)
        if self.usage_sink:
            self.usage_sink({"replayed": False, **usage})
        return norm


# ---- helpers ----------------------------------------------------------------------------------
def assistant_message(resp: dict) -> dict:
    """Turn a normalized response back into an assistant message for the conversation history."""
    m: dict[str, Any] = {"role": "assistant", "content": resp.get("content")}
    if resp.get("tool_calls"):
        m["tool_calls"] = [{"id": tc["id"], "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                           for tc in resp["tool_calls"]]
    return m


def parse_json(text: str | None) -> dict:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}


def json_schema_format(name: str, schema: dict) -> dict:
    return {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}}


def cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return prompt_tokens / 1e6 * PRICE_IN_PER_M + completion_tokens / 1e6 * PRICE_OUT_PER_M


def recording_inputs(scenario: str) -> dict | None:
    rec = load_json(RECORDINGS / f"{scenario}.json")
    return None if rec is None else rec.get("inputs", {})


def recording_meta(scenario: str) -> dict | None:
    rec = load_json(RECORDINGS / f"{scenario}.json")
    if rec is None:
        return None
    calls = rec.get("calls", {})
    pt = sum(c.get("usage", {}).get("prompt_tokens", 0) for c in calls.values())
    ct = sum(c.get("usage", {}).get("completion_tokens", 0) for c in calls.values())
    return {"model": rec.get("model"), "recorded_at": rec.get("recorded_at"), "calls": len(calls),
            "prompt_tokens": pt, "completion_tokens": ct, "cost_usd": cost_usd(pt, ct)}


def _tail(messages: list[dict]) -> str:
    for m in reversed(messages):
        if m.get("role") in {"user", "tool"} and m.get("content"):
            return str(m["content"])[:300]
    return ""
