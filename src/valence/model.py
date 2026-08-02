from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MessageType(str, Enum):
    BLOCK = "block"
    ATTESTATION = "attestation"


class ValidatorStatus(str, Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    RECOVERING = "recovering"


@dataclass(frozen=True)
class Block:
    block_id: str
    slot: int
    proposer_id: int
    parent_id: str | None
    created_at_ms: int


@dataclass(frozen=True)
class Attestation:
    attestation_id: str
    slot: int
    validator_id: int
    block_id: str
    created_at_ms: int
    stake: float
    source_checkpoint_id: str = "genesis"
    source_epoch: int = 0
    target_checkpoint_id: str = "genesis"
    target_epoch: int = 0


@dataclass(frozen=True)
class Message:
    message_id: str
    message_type: MessageType
    creator_id: int
    slot: int
    created_at_ms: int
    size_bytes: int
    body: Block | Attestation


@dataclass
class LocalView:
    known_blocks: dict[str, Block] = field(default_factory=dict)
    children: dict[str, set[str]] = field(default_factory=dict)
    latest_attestations: dict[int, Attestation] = field(default_factory=dict)
    finality_votes: dict[tuple[int, int], Attestation] = field(default_factory=dict)
    subtree_vote_weight: dict[str, float] = field(default_factory=dict)
    head_id: str = "genesis"
    justified_checkpoint: str = "genesis"
    justified_epoch: int = 0
    finalized_checkpoint: str = "genesis"
    finalized_epoch: int = 0


@dataclass
class Validator:
    validator_id: int
    stake: float
    region: str
    isp: str
    peers: tuple[int, ...]
    status: ValidatorStatus = ValidatorStatus.ONLINE
    processing_delay_ms: int = 0
    view: LocalView = field(default_factory=LocalView)
    seen_messages: set[str] = field(default_factory=set)
    unavailable_since_ms: int | None = None
    unavailable_time_ms: int = 0
    outage_count: int = 0
    recovery_count: int = 0

    @property
    def online(self) -> bool:
        """Compatibility helper for code that treats only ONLINE as participating."""
        return self.status == ValidatorStatus.ONLINE

    @property
    def can_participate(self) -> bool:
        return self.status == ValidatorStatus.ONLINE

    @property
    def can_receive(self) -> bool:
        return self.status in {ValidatorStatus.ONLINE, ValidatorStatus.DEGRADED}

    @property
    def can_forward(self) -> bool:
        return self.status in {ValidatorStatus.ONLINE, ValidatorStatus.DEGRADED}
