from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    FAULT_START = auto()
    FAULT_END = auto()
    VALIDATOR_RECOVERY_COMPLETE = auto()
    SLOT_START = auto()
    MESSAGE_ARRIVAL = auto()
    MESSAGE_PROCESSING_COMPLETE = auto()
    ATTESTATION_TIME = auto()
    EPOCH_BOUNDARY = auto()


@dataclass(order=True, frozen=True)
class Event:
    """A deterministic event ordered by simulation time and insertion sequence."""

    time_ms: int
    sequence: int
    event_type: EventType = field(compare=False)
    payload: Any = field(compare=False, default=None)
