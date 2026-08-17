from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class DomainEvent:
    name: str
    payload: dict[str, Any]
    occurred_at: str


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[DomainEvent], None]]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable[[DomainEvent], None]) -> None:
        self._subscribers[event_name].append(handler)

    def publish(self, event_name: str, payload: dict[str, Any]) -> DomainEvent:
        event = DomainEvent(
            name=event_name,
            payload=payload,
            occurred_at=datetime.now(UTC).isoformat(),
        )
        for handler in tuple(self._subscribers.get(event_name, ())):
            handler(event)
        return event
