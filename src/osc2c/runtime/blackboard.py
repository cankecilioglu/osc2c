"""Minimal blackboard used for OSC2 events and shared runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EventRecord:
    time: float
    name: str
    payload: Any = None


@dataclass
class Blackboard:
    values: dict[str, Any] = field(default_factory=dict)
    events: dict[str, int] = field(default_factory=dict)
    trace: list[EventRecord] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def emit(self, name: str, time: float, payload: Any = None) -> None:
        key = name.lstrip("@")
        self.events[key] = self.events.get(key, 0) + 1
        self.trace.append(EventRecord(time, key, payload))

    def raised(self, name: str) -> bool:
        return self.events.get(name.lstrip("@"), 0) > 0

    def count(self, name: str) -> int:
        return self.events.get(name.lstrip("@"), 0)
