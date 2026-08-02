from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from valence.config import ProtocolConfig
from valence.model import Attestation, Block, Message, MessageType, Validator
from valence.protocols.ethereum_calibrated import (
    DOMAIN_BEACON_ATTESTER,
    DOMAIN_BEACON_PROPOSER,
    base_seed_from_integer,
    committee_count_per_slot,
    compute_committee,
    compute_proposer_index,
    epoch_seed,
    get_preset,
    logical_effective_balances_gwei,
)
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
    committee_index_by_slot_validator: tuple[dict[int, int], ...]
    committees_per_slot: tuple[int, ...]


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
        simulation_seed: int = 1,
    ) -> None:
        self.config = config
        self.validators = validators
        self.block_size_bytes = block_size_bytes
        self.attestation_size_bytes = attestation_size_bytes
        if config.implementation == "ethereum_calibrated":
            self.schedule = self._build_ethereum_schedule(total_slots, simulation_seed)
        else:
            self.schedule = self._build_simplified_schedule(
                total_slots,
                proposer_rng,
                committee_rng,
            )
        self.stake_by_validator = {
            validator_id: validator.stake
            for validator_id, validator in validators.items()
        }

    def _build_simplified_schedule(
        self,
        total_slots: int,
        proposer_rng: np.random.Generator,
        committee_rng: np.random.Generator,
    ) -> DutySchedule:
        ids = np.array(sorted(self.validators), dtype=int)
        stakes = np.array([self.validators[int(i)].stake for i in ids], dtype=float)
        probabilities = stakes / stakes.sum()
        proposer_by_slot = tuple(
            int(proposer_rng.choice(ids, p=probabilities)) for _ in range(total_slots)
        )
        committee_size = max(1, int(round(len(ids) * self.config.committee_fraction)))
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
        committee_indices = tuple(
            {validator_id: 0 for validator_id in committee}
            for committee in committees
        )
        return DutySchedule(
            proposer_by_slot=proposer_by_slot,
            committee_by_slot=committees,
            committee_index_by_slot_validator=committee_indices,
            committees_per_slot=tuple(1 for _ in range(total_slots)),
        )

    def _build_ethereum_schedule(self, total_slots: int, simulation_seed: int) -> DutySchedule:
        preset = get_preset(self.config.ethereum_preset)
        ids = tuple(sorted(self.validators))
        stakes = tuple(self.validators[validator_id].stake for validator_id in ids)
        effective_balances = logical_effective_balances_gwei(stakes, preset)
        # Validator IDs are dense in VALENCE, so the tuple is directly indexable.
        effective_by_id = [0] * (max(ids) + 1)
        for validator_id, balance in zip(ids, effective_balances):
            effective_by_id[validator_id] = balance

        base_seed = base_seed_from_integer(
            simulation_seed,
            spec_release=self.config.ethereum_spec_release,
        )
        proposers: list[int] = []
        committees_by_slot: list[tuple[int, ...]] = []
        committee_index_by_slot_validator: list[dict[int, int]] = []
        counts_by_slot: list[int] = []

        epoch_length = preset.slots_per_epoch
        for epoch_start in range(0, total_slots, epoch_length):
            epoch = epoch_start // epoch_length
            committees_per_slot = committee_count_per_slot(len(ids), preset)
            total_committees = committees_per_slot * epoch_length
            attester_seed = epoch_seed(base_seed, epoch, DOMAIN_BEACON_ATTESTER)
            proposer_epoch_seed = epoch_seed(base_seed, epoch, DOMAIN_BEACON_PROPOSER)

            for offset in range(epoch_length):
                slot = epoch_start + offset
                if slot >= total_slots:
                    break
                flattened: list[int] = []
                index_map: dict[int, int] = {}
                for committee_index in range(committees_per_slot):
                    global_index = offset * committees_per_slot + committee_index
                    committee = compute_committee(
                        ids,
                        attester_seed,
                        global_index,
                        total_committees,
                        preset.shuffle_round_count,
                    )
                    flattened.extend(committee)
                    index_map.update(
                        {validator_id: committee_index for validator_id in committee}
                    )
                committees_by_slot.append(tuple(flattened))
                committee_index_by_slot_validator.append(index_map)
                counts_by_slot.append(committees_per_slot)

                proposer_seed = __import__("hashlib").sha256(
                    proposer_epoch_seed + int(slot).to_bytes(8, "little")
                ).digest()
                proposers.append(
                    compute_proposer_index(
                        ids,
                        effective_by_id,
                        proposer_seed,
                        preset,
                    )
                )

        return DutySchedule(
            proposer_by_slot=tuple(proposers),
            committee_by_slot=tuple(committees_by_slot),
            committee_index_by_slot_validator=tuple(committee_index_by_slot_validator),
            committees_per_slot=tuple(counts_by_slot),
        )

    def proposer_for_slot(self, slot: int) -> int:
        return self.schedule.proposer_by_slot[slot]

    def committee_for_slot(self, slot: int) -> tuple[int, ...]:
        return self.schedule.committee_by_slot[slot]

    def committee_index_for_validator(self, slot: int, validator_id: int) -> int:
        return self.schedule.committee_index_by_slot_validator[slot].get(validator_id, 0)

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "implementation": self.config.implementation,
            "slot_duration_ms": self.config.slot_duration_ms,
            "epoch_length_slots": self.config.epoch_length_slots,
        }
        if self.config.implementation == "ethereum_calibrated":
            metadata.update(
                {
                    "ethereum_spec_release": self.config.ethereum_spec_release,
                    "ethereum_fork": self.config.ethereum_fork,
                    "ethereum_preset": self.config.ethereum_preset,
                    "target_committee_size": self.config.target_committee_size,
                    "max_committees_per_slot": self.config.max_committees_per_slot,
                    "shuffle_round_count": self.config.shuffle_round_count,
                    "attestation_due_bps": self.config.attestation_due_bps,
                    "aggregate_due_bps": self.config.aggregate_due_bps,
                    "proposer_score_boost": self.config.proposer_score_boost,
                    "committees_per_slot_observed": sorted(
                        set(self.schedule.committees_per_slot)
                    ),
                    "randao_mode": "deterministic_simulation_surrogate",
                    "consensus_engine": "beacon_like_simplified",
                    "proposer_score_boost_applied": False,
                }
            )
        return metadata

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
            committee_index=self.committee_index_for_validator(slot, validator.validator_id),
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
