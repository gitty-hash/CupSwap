"""Human-readable agent trace. Every think / act / observe / guard / human step is an event.

The trace is the audit artifact of the whole app: the UI renders it as a timeline and it is
saved next to the recordings so a reviewer can answer "why did the agent do that?".
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable

KIND_ICON = {
    "user": "🙋", "memory": "🧠", "plan": "🗺️", "think": "💭", "act": "🔧", "observe": "👁️",
    "guard": "🛡️", "human": "✋", "final": "🏁", "error": "⚠️", "platform": "🏛️", "offer": "💬",
    "system": "⚙️", "rule": "📏", "route": "🔀", "policy": "📄", "judge": "⚖️", "mcp": "🔌",
}


@dataclass
class TraceEvent:
    step: int
    kind: str
    agent: str
    title: str
    detail: str = ""
    data: Any = None
    status: str = "info"         # info | ok | warn | fail
    at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    @property
    def icon(self) -> str:
        return KIND_ICON.get(self.kind, "•")


class Trace:
    def __init__(self, on_event: Callable[[TraceEvent], None] | None = None):
        self.events: list[TraceEvent] = []
        self.on_event = on_event
        self.step = 0

    def next_step(self) -> int:
        self.step += 1
        return self.step

    def add(self, kind: str, agent: str, title: str, detail: str = "", data: Any = None,
            status: str = "info", step: int | None = None) -> TraceEvent:
        ev = TraceEvent(step=self.step if step is None else step, kind=kind, agent=agent,
                        title=title, detail=detail, data=data, status=status)
        self.events.append(ev)
        if self.on_event:
            self.on_event(ev)
        return ev

    def to_list(self) -> list[dict]:
        return [asdict(e) for e in self.events]

    @staticmethod
    def from_list(items: list[dict]) -> "Trace":
        t = Trace()
        t.events = [TraceEvent(**i) for i in items]
        t.step = max((e.step for e in t.events), default=0)
        return t
