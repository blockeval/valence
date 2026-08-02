from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from valence.config import ProtocolConfig
from valence.model import Attestation, Block, Message, MessageType, Validator
from .finality import (
    FinalityTransition,
    checkpoint_for_epoch,
    record_finality_vote,
    update_finality,
)
from .fork_choice import adjust_vote, lmd_ghost_head, rebuild_vote_weights


@dataclass(frozen=True)
class DutySchedule:
    proposer_by_slot: tuple[int, ...]
    committee_by_slot: tuple[tuple[int, ...], ...]


class BeaconLikeProtocol:
    def __init__(
        self,
        config: ProtocolConfig,
        validators: dict[int, Validator],
        proposer_rng: np.random.Generator,
        committee_rng: np.random.Generator,
        total_slots: int,
        block_size_bytes: int = 120_000,
        attestation_size_bytes: int = 512,
    ) -> None:
        self.config = config
        self.validators = validators
        self.block_size_bytes = block_size_bytes
        self.attestation_size_bytes = attestation_size_bytes
        ids = np.array(sorted(validators), dtype=int)
        stakes = np.array([validators[int(i)].stake for i in ids], dtype=float)
        probabilities = stakes / stakes.sum()
        proposer_by_slot = tuple(
            int(proposer_rng.choice(ids, p=probabilities)) for _ in range(total_slots)
        )
        committee_size = max(1, int(round(len(ids) * config.committee_fraction)))
        committees = tuple(
            tuple(
                sorted(
                    int(x)
                    for x in committee_rng.choice(
                        ids,
                        size=committee_size,
                        replace=False,
                        p=probabilities,
                    )
                )
            )
            for _ in range(total_slots)
        )
        self.schedule = DutySchedule(proposer_by_slot, committees)
        self.stake_by_validator = {
            validator_id: validator.stake
            for validator_id, validator in validators.items()
        }

    def proposer_for_slot(self, slot: int) -> int:
        return self.schedule.proposer_by_slot[slot]

    def committee_for_slot(self, slot: int) -> tuple[int, ...]:
        return self.schedule.committee_by_slot[slot]

    def create_block(self, proposer: Validator, slot: int, time_ms: int) -> Message:
        parent_id = proposer.view.head_id
        block_id = f"b{slot:06d}-v{proposer.validator_id:05d}"
        block = Block(block_id, slot, proposer.validator_id, parent_id, time_ms)
        return Message(
            message_id=f"msg-{block_id}",
            message_type=MessageType.BLOCK,
            creator_id=proposer.validator_id,
            slot=slot,
            created_at_ms=time_ms,
            size_bytes=self.block_size_bytes,
            body=block,
        )

    def create_attestation(self, validator: Validator, slot: int, time_ms: int) -> Message:
        block_id = validator.view.head_id
        target_epoch = slot // self.config.epoch_length_slots
        target_checkpoint_id = checkpoint_for_epoch(
            validator.view,
            target_epoch,
            self.config.epoch_length_slots,
        )
        attestation_id = f"a{slot:06d}-v{validator.validator_id:05d}"
        attestation = Attestation(
            attestation_id=attestation_id,
            slot=slot,
            validator_id=validator.validator_id,
            block_id=block_id,
            created_at_ms=time_ms,
            stake=validator.stake,
            source_checkpoint_id=validator.view.justified_checkpoint,
            source_epoch=validator.view.justified_epoch,
            target_checkpoint_id=target_checkpoint_id,
            target_epoch=target_epoch,
        )
        return Message(
            message_id=f"msg-{attestation_id}",
            message_type=MessageType.ATTESTATION,
            creator_id=validator.validator_id,
            slot=slot,
            created_at_ms=time_ms,
            size_bytes=self.attestation_size_bytes,
            body=attestation,
        )

    def process_message(self, validator: Validator, message: Message) -> None:
        view = validator.view
        if message.message_type == MessageType.BLOCK:
            block = message.body
            assert isinstance(block, Block)
            if block.block_id not in view.known_blocks:
                view.known_blocks[block.block_id] = block
                view.children.setdefault(block.block_id, set())
                if block.parent_id is not None:
                    view.children.setdefault(block.parent_id, set()).add(block.block_id)
                # A previously received attestation may have referenced this block.
                rebuild_vote_weights(view, self.stake_by_validator)
        else:
            attestation = message.body
            assert isinstance(attestation, Attestation)
            previous = view.latest_attestations.get(attestation.validator_id)
            if previous is None or (attestation.slot, attestation.created_at_ms) > (
                previous.slot,
                previous.created_at_ms,
            ):
                if previous is not None:
                    adjust_vote(
                        view,
                        previous.block_id,
                        -self.stake_by_validator[attestation.validator_id],
                    )
                view.latest_attestations[attestation.validator_id] = attestation
                adjust_vote(
                    view,
                    attestation.block_id,
                    self.stake_by_validator[attestation.validator_id],
                )
            record_finality_vote(view, attestation)
        view.head_id = lmd_ghost_head(view)

    def update_finality(
        self,
        validator: Validator,
        target_epoch: int,
    ) -> FinalityTransition | None:
        if not self.config.finality_enabled:
            return None
        transition = update_finality(
            validator.view,
            target_epoch,
            self.stake_by_validator,
            self.config.justification_threshold,
        )
        if transition is not None and transition.justified:
            validator.view.head_id = lmd_ghost_head(validator.view)
        return transition
