from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, DefaultDict

logger = logging.getLogger("trading")

@dataclass(frozen=True)
class Event:
    name: str
    payload: dict = field(default_factory=dict)


class EventBus:
    def __init__(self):
        self._subscribers: DefaultDict[str, list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable[[Event], None]) -> None:
        self._subscribers[event_name].append(handler)

    def publish(self, event: Event) -> None:
        logger.info("event_published", extra={"event": event.name})
        for handler in self._subscribers.get(event.name, []):
            try:
                handler(event)
            except Exception:
                logger.exception("event_handler_failed", extra={"event": event.name, "handler": repr(handler)})


bus = EventBus()
