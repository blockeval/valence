from __future__ import annotations

import heapq
from collections.abc import Iterator

from .event import Event, EventType


class EventQueue:
    def __init__(self) -> None:
        self._heap: list[Event] = []
        self._sequence = 0

    def push(self, time_ms: int, event_type: EventType, payload: object = None) -> Event:
        if time_ms < 0:
            raise ValueError("Event time cannot be negative")
        event = Event(time_ms, self._sequence, event_type, payload)
        self._sequence += 1
        heapq.heappush(self._heap, event)
        return event

    def pop(self) -> Event:
        return heapq.heappop(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)

    def __len__(self) -> int:
        return len(self._heap)

    def __iter__(self) -> Iterator[Event]:
        while self:
            yield self.pop()
