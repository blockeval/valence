from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from valence.config import FaultConfig, ValenceConfig
from valence.engine import EventQueue, EventType, RandomStreams
from valence.metrics import MetricsCollector
from valence.consensus_analysis import ancestor_path
from valence.model import (
    Attestation,
    Block,
    LocalView,
    Message,
    Validator,
    ValidatorStatus,
)
from valence.network import (
    NetworkModel,
    build_regional_clustered,
    build_ring_plus_random,
    topology_summary,
)
from valence.protocols import BeaconLikeProtocol
from valence.resources import ProcessingPlan, ResourceModel


@dataclass(frozen=True)
class ArrivalPayload:
    target_id: int
    source_id: int
    message: Message
    scheduled_time_ms: int
    requested_send_time_ms: int
    send_started_at_ms: int
    send_completed_at_ms: int
    network_delay_ms: int


@dataclass(frozen=True)
class ProcessingPayload:
    target_id: int
    source_id: int
    message: Message
    processing_plan: ProcessingPlan
    network_delay_ms: int


@dataclass(frozen=True)
class AttestationPayload:
    validator_id: int
    slot: int


@dataclass(frozen=True)
class FaultEventPayload:
    fault: FaultConfig
    target_ids: tuple[int, ...]
    recovery_generation: int = 0


@dataclass
class SimulationResult:
    summary: dict[str, Any]
    event_log: list[dict[str, Any]]

    def canonical_hash(self) -> str:
        payload = json.dumps(
            {"summary": self.summary, "event_log": self.event_log},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class ValenceSimulation:
    def __init__(self, config: ValenceConfig):
        config.validate()
        self.config = config
        self.streams = RandomStreams.from_seed(config.simulation.seed)
        self.region_assignments = self._build_assignments(
            config.validators.regions,
            config.validators.region_assignment,
            config.validators.region_weights,
            config.validators.count,
        )
        self.isp_assignments = self._build_assignments(
            config.validators.isps,
            config.validators.isp_assignment,
            config.validators.isp_weights,
            config.validators.count,
        )
        if config.topology.kind == "regional_clustered":
            topology = build_regional_clustered(
                self.region_assignments,
                self.isp_assignments,
                config.topology.degree,
                self.streams.topology,
                same_region_bias=config.topology.same_region_bias,
                same_isp_bias=config.topology.same_isp_bias,
                minimum_cross_region_peers=config.topology.minimum_cross_region_peers,
            )
        else:
            topology = build_ring_plus_random(
                config.validators.count,
                config.topology.degree,
                self.streams.topology,
            )
        self.topology = topology
        self.validators = self._build_validators(topology)
        self.protocol = BeaconLikeProtocol(
            config.protocol,
            self.validators,
            self.streams.proposer,
            self.streams.committee,
            config.simulation.slots,
            block_size_bytes=config.network.block_size_bytes,
            attestation_size_bytes=config.network.attestation_size_bytes,
        )
        self.network = NetworkModel(
            config.network,
            self.streams.latency,
            self.streams.loss,
        )
        self.resources = ResourceModel(config.resources)
        self.queue = EventQueue()
        self.metrics = MetricsCollector()
        self.event_log: list[dict[str, Any]] = []
        self.earliest_arrival: dict[tuple[str, int], int] = {}
        self.pending_processing: set[tuple[str, int]] = set()
        self.now_ms = 0
        self.nominal_end_ms = (
            config.simulation.slots * config.protocol.slot_duration_ms
        )
        self.all_blocks: dict[str, Block] = dict(
            self.validators[0].view.known_blocks
        )
        self.active_outages: dict[int, set[str]] = {
            validator_id: set() for validator_id in self.validators
        }
        self.recovery_generation: dict[int, int] = {
            validator_id: 0 for validator_id in self.validators
        }
        self.fault_targets: dict[str, tuple[int, ...]] = {}
        self.fault_records: list[dict[str, Any]] = []

    def _build_assignments(
        self,
        labels: tuple[str, ...],
        mode: str,
        weights: tuple[float, ...],
        count: int,
    ) -> list[str]:
        if mode == "round_robin":
            return [labels[index % len(labels)] for index in range(count)]
        probabilities = np.asarray(weights, dtype=float)
        probabilities /= probabilities.sum()
        assignments: list[str] = []
        if count >= len(labels):
            assignments.extend(labels)
        remaining = count - len(assignments)
        if remaining > 0:
            sampled = self.streams.placement.choice(
                labels,
                size=remaining,
                replace=True,
                p=probabilities,
            )
            assignments.extend(str(value) for value in sampled)
        self.streams.placement.shuffle(assignments)
        return assignments

    def _build_stakes(self) -> np.ndarray:
        cfg = self.config.validators
        if cfg.stake_distribution == "equal":
            raw = np.ones(cfg.count, dtype=float)
        elif cfg.stake_distribution == "lognormal":
            raw = self.streams.stake.lognormal(
                mean=0.0,
                sigma=cfg.stake_sigma,
                size=cfg.count,
            )
        elif cfg.stake_distribution == "explicit":
            raw = np.asarray(cfg.explicit_stakes, dtype=float)
        else:  # Defensive; validation should reject this earlier.
            raise ValueError(f"Unsupported stake distribution: {cfg.stake_distribution}")
        total = float(raw.sum())
        if total <= 0:
            raise ValueError("Total validator stake must be positive")
        return raw / total

    def _build_validators(
        self,
        topology: dict[int, tuple[int, ...]],
    ) -> dict[int, Validator]:
        cfg = self.config.validators
        stakes = self._build_stakes()
        genesis = Block("genesis", -1, -1, None, 0)
        validators: dict[int, Validator] = {}
        for validator_id in range(cfg.count):
            region = self.region_assignments[validator_id]
            isp = self.isp_assignments[validator_id]
            view = LocalView(
                known_blocks={"genesis": genesis},
                children={"genesis": set()},
            )
            validators[validator_id] = Validator(
                validator_id=validator_id,
                stake=float(stakes[validator_id]),
                region=region,
                isp=isp,
                peers=topology[validator_id],
                view=view,
            )
        return validators

    def _log(self, event: str, **fields: object) -> None:
        if self.config.simulation.record_events:
            self.event_log.append({"time_ms": self.now_ms, "event": event, **fields})

    def run(self) -> SimulationResult:
        self._schedule_faults()
        self.queue.push(0, EventType.SLOT_START, {"slot": 0})
        while self.queue:
            event = self.queue.pop()
            self.now_ms = event.time_ms
            if event.event_type == EventType.FAULT_START:
                self._on_fault_start(event.payload)
            elif event.event_type == EventType.FAULT_END:
                self._on_fault_end(event.payload)
            elif event.event_type == EventType.VALIDATOR_RECOVERY_COMPLETE:
                self._on_recovery_complete(event.payload)
            elif event.event_type == EventType.SLOT_START:
                self._on_slot_start(int(event.payload["slot"]))
            elif event.event_type == EventType.ATTESTATION_TIME:
                self._on_attestation_time(event.payload)
            elif event.event_type == EventType.MESSAGE_ARRIVAL:
                self._on_message_arrival(event.payload)
            elif event.event_type == EventType.MESSAGE_PROCESSING_COMPLETE:
                self._on_message_processing_complete(event.payload)
            elif event.event_type == EventType.EPOCH_BOUNDARY:
                self._on_epoch_boundary(int(event.payload["slot"]))

        self.metrics.record_slot_chain_state(
            self.config.simulation.slots - 1,
            self.validators,
            self.all_blocks,
            self.config.metrics.minimum_branch_support,
            time_ms=self.nominal_end_ms,
            slot_duration_ms=self.config.protocol.slot_duration_ms,
        )
        self.metrics.finalize_fork_tracking(
            self.config.simulation.slots, self.nominal_end_ms
        )
        for validator in self.validators.values():
            self._finalize_validator_unavailability(validator)

        stakes = [validator.stake for validator in self.validators.values()]
        summary = self.metrics.to_dict()
        region_counts: dict[str, int] = {}
        region_stake: dict[str, float] = {}
        isp_counts: dict[str, int] = {}
        for validator in self.validators.values():
            region_counts[validator.region] = region_counts.get(validator.region, 0) + 1
            region_stake[validator.region] = region_stake.get(validator.region, 0.0) + validator.stake
            isp_counts[validator.isp] = isp_counts.get(validator.isp, 0) + 1
        summary.update(
            {
                "seed": self.config.simulation.seed,
                "slots": self.config.simulation.slots,
                "validator_count": self.config.validators.count,
                "simulation_end_time_ms": self.now_ms,
                "nominal_protocol_time_ms": self.nominal_end_ms,
                "stake_distribution": self.config.validators.stake_distribution,
                "minimum_validator_stake": min(stakes),
                "maximum_validator_stake": max(stakes),
                "stake_hhi": sum(stake * stake for stake in stakes),
                "region_validator_counts": dict(sorted(region_counts.items())),
                "region_stake": {
                    key: round(value, 12) for key, value in sorted(region_stake.items())
                },
                "isp_validator_counts": dict(sorted(isp_counts.items())),
                "network_transmissions": self.network.transmissions,
                "network_drops": self.network.drops,
                "drop_rate": (
                    self.network.drops / self.network.transmissions
                    if self.network.transmissions
                    else 0.0
                ),
                "final_heads": {
                    str(validator_id): validator.view.head_id
                    for validator_id, validator in self.validators.items()
                },
                "validator_status": {
                    str(validator_id): validator.status.value
                    for validator_id, validator in self.validators.items()
                },
                "finality_states": {
                    str(validator_id): {
                        "justified_epoch": validator.view.justified_epoch,
                        "justified_checkpoint": validator.view.justified_checkpoint,
                        "finalized_epoch": validator.view.finalized_epoch,
                        "finalized_checkpoint": validator.view.finalized_checkpoint,
                    }
                    for validator_id, validator in self.validators.items()
                },
                "faults": self.fault_records,
            }
        )
        summary["availability"] = self.metrics.availability_summary(
            self.validators,
            self.nominal_end_ms,
            self.config.protocol.justification_threshold,
        )
        summary["forks"] = self.metrics.fork_summary(
            self.all_blocks,
            self.validators,
            self.config.simulation.slots,
            self.config.metrics.orphan_settlement_slots,
        )
        summary["finality_timing"] = self.metrics.finality_timing_summary(
            self.nominal_end_ms
        )
        # Convenient top-level aliases for poster-facing metrics.
        summary.update(
            {
                "proposal_availability": summary["availability"]["proposal_availability"],
                "attestation_availability": summary["availability"]["attestation_availability"],
                "stake_weighted_attestation_availability": summary["availability"][
                    "stake_weighted_attestation_availability"
                ],
                "fork_rate_per_1000_slots": summary["forks"]["fork_rate_per_1000_slots"],
                "orphaned_block_rate": summary["forks"]["orphaned_block_rate"],
                "maximum_reorganization_depth": max(
                    summary["forks"]["maximum_local_reorganization_depth"],
                    summary["forks"]["maximum_global_reorganization_depth"],
                ),
                "p95_checkpoint_time_to_finality_ms": summary["finality_timing"][
                    "p95_checkpoint_time_to_finality_ms"
                ],
            }
        )
        summary.update(
            topology_summary(
                self.topology,
                self.region_assignments,
                self.isp_assignments,
            )
        )
        summary.update(self.network.calibration_summary())
        attempted_p99 = float(summary["attempted_effective_latency"]["p99_ms"])
        delivered_p99 = float(summary.get("p99_network_delay_ms", 0.0))
        summary["delivered_to_attempted_p99_ratio"] = (
            round(delivered_p99 / attempted_p99, 12) if attempted_p99 else 0.0
        )
        attempted_p999 = float(summary["attempted_effective_latency"]["p999_ms"])
        delivered_p999 = float(summary.get("p999_network_delay_ms", 0.0))
        summary["delivered_to_attempted_p999_ratio"] = (
            round(delivered_p999 / attempted_p999, 12) if attempted_p999 else 0.0
        )
        summary.update(
            self.resources.utilization_summary(
                self.config.validators.count,
                max(1, self.now_ms),
            )
        )
        return SimulationResult(summary, self.event_log)

    def _resolve_fault_targets(self, fault: FaultConfig) -> tuple[int, ...]:
        ids = sorted(self.validators)
        if fault.scope == "global":
            selected = ids
        elif fault.scope == "region":
            selected = [
                validator_id
                for validator_id, validator in self.validators.items()
                if validator.region in set(fault.targets)
            ]
        elif fault.scope == "isp":
            selected = [
                validator_id
                for validator_id, validator in self.validators.items()
                if validator.isp in set(fault.targets)
            ]
        elif fault.scope == "validator_ids":
            selected = list(fault.validator_ids)
        elif fault.scope == "random_fraction":
            count = max(1, int(round(len(ids) * fault.fraction)))
            selected = sorted(
                int(value)
                for value in self.streams.faults.choice(
                    ids, size=min(count, len(ids)), replace=False
                )
            )
        elif fault.scope == "highest_stake":
            selected = []
            total = 0.0
            for validator_id in sorted(
                ids, key=lambda value: (-self.validators[value].stake, value)
            ):
                selected.append(validator_id)
                total += self.validators[validator_id].stake
                if total + 1e-12 >= fault.stake_fraction:
                    break
        elif fault.scope == "stake_fraction":
            order = [int(value) for value in self.streams.faults.permutation(ids)]
            selected = []
            total = 0.0
            for validator_id in order:
                selected.append(validator_id)
                total += self.validators[validator_id].stake
                if total + 1e-12 >= fault.stake_fraction:
                    break
            selected.sort()
        else:  # Defensive; validation rejects unsupported scopes.
            raise ValueError(f"Unsupported fault scope: {fault.scope}")
        return tuple(sorted(set(selected)))

    def _schedule_faults(self) -> None:
        slot_ms = self.config.protocol.slot_duration_ms
        for fault in self.config.faults:
            targets = self._resolve_fault_targets(fault)
            self.fault_targets[fault.name] = targets
            start_ms = fault.start_slot * slot_ms
            end_ms = (fault.start_slot + fault.duration_slots) * slot_ms
            payload = FaultEventPayload(fault=fault, target_ids=targets)
            self.queue.push(start_ms, EventType.FAULT_START, payload)
            self.queue.push(end_ms, EventType.FAULT_END, payload)
            self.fault_records.append(
                {
                    "name": fault.name,
                    "action": fault.action,
                    "scope": fault.scope,
                    "target_ids": list(targets),
                    "target_count": len(targets),
                    "target_stake": round(
                        sum(self.validators[value].stake for value in targets), 12
                    ),
                    "start_slot": fault.start_slot,
                    "duration_slots": fault.duration_slots,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "recovery_mode": fault.recovery_mode,
                    "resynchronization_ms": fault.resynchronization_ms,
                }
            )

    def _transition_status(
        self,
        validator: Validator,
        status: ValidatorStatus,
        time_ms: int,
    ) -> None:
        old = validator.status
        if old == status:
            return
        effective_time = min(max(0, time_ms), self.nominal_end_ms)
        old_unavailable = old in {ValidatorStatus.OFFLINE, ValidatorStatus.RECOVERING}
        new_unavailable = status in {ValidatorStatus.OFFLINE, ValidatorStatus.RECOVERING}
        if not old_unavailable and new_unavailable:
            validator.unavailable_since_ms = effective_time
        elif old_unavailable and not new_unavailable:
            if validator.unavailable_since_ms is not None:
                validator.unavailable_time_ms += max(
                    0, effective_time - validator.unavailable_since_ms
                )
            validator.unavailable_since_ms = None
        validator.status = status

    def _finalize_validator_unavailability(self, validator: Validator) -> None:
        if validator.unavailable_since_ms is None:
            return
        validator.unavailable_time_ms += max(
            0, self.nominal_end_ms - validator.unavailable_since_ms
        )
        validator.unavailable_since_ms = None

    def _on_fault_start(self, payload: FaultEventPayload) -> None:
        self.metrics.outage_events_started += 1
        for validator_id in payload.target_ids:
            validator = self.validators[validator_id]
            was_available = not self.active_outages[validator_id]
            self.active_outages[validator_id].add(payload.fault.name)
            self.recovery_generation[validator_id] += 1
            if was_available:
                validator.outage_count += 1
                self.metrics.validator_outage_instances += 1
                self._transition_status(validator, ValidatorStatus.OFFLINE, self.now_ms)
        self._log(
            "fault_started",
            fault_name=payload.fault.name,
            scope=payload.fault.scope,
            target_ids=list(payload.target_ids),
        )

    def _on_fault_end(self, payload: FaultEventPayload) -> None:
        self.metrics.outage_events_ended += 1
        for validator_id in payload.target_ids:
            active = self.active_outages[validator_id]
            active.discard(payload.fault.name)
            if active:
                continue
            validator = self.validators[validator_id]
            self.recovery_generation[validator_id] += 1
            generation = self.recovery_generation[validator_id]
            if payload.fault.resynchronization_ms > 0:
                self._transition_status(validator, ValidatorStatus.RECOVERING, self.now_ms)
                self.queue.push(
                    self.now_ms + payload.fault.resynchronization_ms,
                    EventType.VALIDATOR_RECOVERY_COMPLETE,
                    FaultEventPayload(
                        fault=payload.fault,
                        target_ids=(validator_id,),
                        recovery_generation=generation,
                    ),
                )
            else:
                self._complete_recovery(validator, payload.fault)
        self._log(
            "fault_ended",
            fault_name=payload.fault.name,
            target_ids=list(payload.target_ids),
        )

    def _on_recovery_complete(self, payload: FaultEventPayload) -> None:
        for validator_id in payload.target_ids:
            if self.active_outages[validator_id]:
                continue
            if payload.recovery_generation != self.recovery_generation[validator_id]:
                continue
            self._complete_recovery(self.validators[validator_id], payload.fault)

    def _complete_recovery(self, validator: Validator, fault: FaultConfig) -> None:
        if fault.recovery_mode == "restart_from_finalized_checkpoint":
            self._restart_from_finalized_checkpoint(validator)
        self._transition_status(validator, ValidatorStatus.ONLINE, self.now_ms)
        validator.recovery_count += 1
        self.metrics.validator_recoveries_completed += 1
        self._log(
            "validator_recovered",
            validator_id=validator.validator_id,
            fault_name=fault.name,
            recovery_mode=fault.recovery_mode,
        )

    def _restart_from_finalized_checkpoint(self, validator: Validator) -> None:
        view = validator.view
        finalized = view.finalized_checkpoint
        keep_ids = set(ancestor_path(finalized, view.known_blocks))
        if "genesis" not in keep_ids:
            keep_ids.add("genesis")
        kept = {
            block_id: block
            for block_id, block in view.known_blocks.items()
            if block_id in keep_ids
        }
        children: dict[str, set[str]] = {block_id: set() for block_id in kept}
        for block_id, block in kept.items():
            if block.parent_id in children:
                children[block.parent_id].add(block_id)
        view.known_blocks = kept
        view.children = children
        view.latest_attestations.clear()
        view.finality_votes.clear()
        view.subtree_vote_weight = {block_id: 0.0 for block_id in kept}
        view.head_id = finalized
        view.justified_checkpoint = finalized
        view.justified_epoch = view.finalized_epoch
        validator.seen_messages.clear()

    def _on_slot_start(self, slot: int) -> None:
        if slot >= self.config.simulation.slots:
            return
        if slot > 0:
            self.metrics.record_slot_chain_state(
                slot - 1,
                self.validators,
                self.all_blocks,
                self.config.metrics.minimum_branch_support,
                time_ms=self.now_ms,
                slot_duration_ms=self.config.protocol.slot_duration_ms,
            )
        slot_start = slot * self.config.protocol.slot_duration_ms
        self._log("slot_start", slot=slot)
        proposer_id = self.protocol.proposer_for_slot(slot)
        proposer = self.validators[proposer_id]
        self.metrics.record_proposal_duty(proposer, proposer.can_participate)
        if proposer.can_participate:
            block_message = self.protocol.create_block(proposer, slot, slot_start)
            self.metrics.blocks_created += 1
            self._process_local_and_forward(proposer_id, block_message)
            block = block_message.body
            assert isinstance(block, Block)
            self.all_blocks[block.block_id] = block
            self._log(
                "block_created",
                slot=slot,
                proposer_id=proposer_id,
                block_id=block.block_id,
                parent_id=block.parent_id,
                size_bytes=block_message.size_bytes,
            )

        attestation_time = slot_start + self.config.protocol.attestation_delay_ms
        for validator_id in self.protocol.committee_for_slot(slot):
            self.metrics.record_attestation_assignment(
                self.validators[validator_id], slot
            )
            self.queue.push(
                attestation_time,
                EventType.ATTESTATION_TIME,
                AttestationPayload(validator_id, slot),
            )

        next_slot = slot + 1
        if next_slot < self.config.simulation.slots:
            self.queue.push(
                next_slot * self.config.protocol.slot_duration_ms,
                EventType.SLOT_START,
                {"slot": next_slot},
            )
        if (slot + 1) % self.config.protocol.epoch_length_slots == 0:
            self.queue.push(
                (slot + 1) * self.config.protocol.slot_duration_ms - 1,
                EventType.EPOCH_BOUNDARY,
                {"slot": slot},
            )

    def _on_attestation_time(self, payload: AttestationPayload) -> None:
        validator = self.validators[payload.validator_id]
        if not validator.can_participate:
            self.metrics.record_attestation_missed_offline(validator, payload.slot)
            self._log(
                "attestation_duty_missed",
                slot=payload.slot,
                validator_id=payload.validator_id,
                reason=validator.status.value,
            )
            return
        message = self.protocol.create_attestation(
            validator,
            payload.slot,
            self.now_ms,
        )
        self.metrics.attestations_created += 1
        slot_start = payload.slot * self.config.protocol.slot_duration_ms
        deadline = slot_start + self.config.protocol.attestation_deadline_ms
        on_time = self.now_ms <= deadline
        head_block = validator.view.known_blocks[validator.view.head_id]
        current_head = head_block.slot == payload.slot
        self.metrics.record_attestation_completed(
            validator,
            payload.slot,
            on_time=on_time,
            current_head=current_head,
        )
        self._process_local_and_forward(payload.validator_id, message)
        attestation = message.body
        assert isinstance(attestation, Attestation)
        target_block = validator.view.known_blocks.get(attestation.target_checkpoint_id)
        if target_block is not None:
            self.metrics.record_checkpoint_target(
                attestation.target_checkpoint_id,
                attestation.target_epoch,
                target_block.created_at_ms,
            )
        self._log(
            "attestation_created",
            slot=payload.slot,
            validator_id=payload.validator_id,
            block_id=attestation.block_id,
            source_checkpoint_id=attestation.source_checkpoint_id,
            source_epoch=attestation.source_epoch,
            target_checkpoint_id=attestation.target_checkpoint_id,
            target_epoch=attestation.target_epoch,
            size_bytes=message.size_bytes,
        )

    def _on_message_arrival(self, payload: ArrivalPayload) -> None:
        key = (payload.message.message_id, payload.target_id)
        if self.earliest_arrival.get(key) != payload.scheduled_time_ms:
            self.metrics.stale_arrival_events += 1
            return

        receiver = self.validators[payload.target_id]
        if (
            not receiver.can_receive
            or payload.message.message_id in receiver.seen_messages
            or key in self.pending_processing
        ):
            self.metrics.duplicate_arrivals_ignored += 1
            return

        self.pending_processing.add(key)
        plan = self.resources.schedule_processing(
            payload.target_id,
            self.now_ms,
            payload.message.size_bytes,
        )
        self.metrics.record_delivery_pipeline(
            network_delay_ms=payload.network_delay_ms,
            inbound_queue_delay_ms=plan.inbound_queue_delay_ms,
            inbound_service_time_ms=plan.inbound_service_time_ms,
            processing_queue_delay_ms=plan.processing_queue_delay_ms,
            processing_service_time_ms=plan.processing_service_time_ms,
            end_to_end_delay_ms=(
                plan.processing_completed_at_ms - payload.message.created_at_ms
            ),
            size_bytes=payload.message.size_bytes,
        )
        self._log(
            "message_arrived",
            receiver_id=payload.target_id,
            source_id=payload.source_id,
            message_id=payload.message.message_id,
            message_type=payload.message.message_type.value,
            requested_send_time_ms=payload.requested_send_time_ms,
            send_started_at_ms=payload.send_started_at_ms,
            send_completed_at_ms=payload.send_completed_at_ms,
            network_delay_ms=payload.network_delay_ms,
            inbound_queue_delay_ms=plan.inbound_queue_delay_ms,
            inbound_service_time_ms=plan.inbound_service_time_ms,
            processing_queue_delay_ms=plan.processing_queue_delay_ms,
            processing_service_time_ms=plan.processing_service_time_ms,
            processing_completed_at_ms=plan.processing_completed_at_ms,
        )
        self.queue.push(
            plan.processing_completed_at_ms,
            EventType.MESSAGE_PROCESSING_COMPLETE,
            ProcessingPayload(
                target_id=payload.target_id,
                source_id=payload.source_id,
                message=payload.message,
                processing_plan=plan,
                network_delay_ms=payload.network_delay_ms,
            ),
        )

    def _on_message_processing_complete(self, payload: ProcessingPayload) -> None:
        key = (payload.message.message_id, payload.target_id)
        self.pending_processing.discard(key)
        receiver = self.validators[payload.target_id]
        if not receiver.can_receive or payload.message.message_id in receiver.seen_messages:
            return
        self._process_and_forward(
            receiver_id=payload.target_id,
            source_id=payload.source_id,
            message=payload.message,
        )

    def _process_local_and_forward(self, validator_id: int, message: Message) -> None:
        self._process_and_forward(
            receiver_id=validator_id,
            source_id=validator_id,
            message=message,
        )

    def _process_and_forward(
        self,
        receiver_id: int,
        source_id: int,
        message: Message,
    ) -> None:
        receiver = self.validators[receiver_id]
        if not receiver.can_receive or message.message_id in receiver.seen_messages:
            return
        receiver.seen_messages.add(message.message_id)
        old_head = receiver.view.head_id
        self.protocol.process_message(receiver, message)
        new_head = receiver.view.head_id
        self.metrics.record_local_head_change(
            receiver, old_head, new_head, receiver.view.known_blocks
        )
        if message.message_type.value == "block":
            block = message.body
            assert isinstance(block, Block)
            self.all_blocks[block.block_id] = block
        self.metrics.record_fork_observation(
            time_ms=self.now_ms,
            slot=max(0, message.slot),
            validators=self.validators,
            blocks=self.all_blocks,
            minimum_branch_support=self.config.metrics.minimum_branch_support,
            slot_duration_ms=self.config.protocol.slot_duration_ms,
        )
        self.metrics.processed_messages += 1
        self.metrics.record_processed_bytes(message.size_bytes)
        self._log(
            "message_processed",
            receiver_id=receiver_id,
            source_id=source_id,
            message_id=message.message_id,
            message_type=message.message_type.value,
            end_to_end_delay_ms=self.now_ms - message.created_at_ms,
        )

        if not receiver.can_forward:
            return
        peers = list(receiver.peers)
        if 0 < self.config.network.fanout < len(peers):
            peers = sorted(
                int(value)
                for value in self.streams.gossip.choice(
                    peers,
                    size=self.config.network.fanout,
                    replace=False,
                )
            )
        for peer_id in peers:
            if (
                peer_id == source_id
                or message.message_id in self.validators[peer_id].seen_messages
                or (message.message_id, peer_id) in self.pending_processing
            ):
                continue
            self._schedule_transmission(receiver_id, peer_id, message)

    def _schedule_transmission(
        self,
        source_id: int,
        target_id: int,
        message: Message,
    ) -> None:
        source = self.validators[source_id]
        target = self.validators[target_id]
        outbound = self.resources.schedule_outbound(
            source_id,
            self.now_ms,
            message.size_bytes,
        )
        self.metrics.record_outbound(
            outbound.queue_delay_ms,
            outbound.service_time_ms,
            message.size_bytes,
        )

        arrival = self.network.transmit(
            source_id,
            target_id,
            outbound.completed_at_ms,
            source.region,
            target.region,
        )
        if arrival is None:
            self._log(
                "message_dropped",
                source_id=source_id,
                target_id=target_id,
                message_id=message.message_id,
                requested_send_time_ms=outbound.requested_at_ms,
                send_started_at_ms=outbound.started_at_ms,
                send_completed_at_ms=outbound.completed_at_ms,
                outbound_queue_delay_ms=outbound.queue_delay_ms,
                outbound_service_time_ms=outbound.service_time_ms,
                source_region=source.region,
                target_region=target.region,
            )
            return

        network_delay = arrival - outbound.completed_at_ms
        key = (message.message_id, target_id)
        current = self.earliest_arrival.get(key)
        if current is None or arrival < current:
            self.earliest_arrival[key] = arrival
            self.queue.push(
                arrival,
                EventType.MESSAGE_ARRIVAL,
                ArrivalPayload(
                    target_id=target_id,
                    source_id=source_id,
                    message=message,
                    scheduled_time_ms=arrival,
                    requested_send_time_ms=outbound.requested_at_ms,
                    send_started_at_ms=outbound.started_at_ms,
                    send_completed_at_ms=outbound.completed_at_ms,
                    network_delay_ms=network_delay,
                ),
            )
        self._log(
            "message_transmission_scheduled",
            source_id=source_id,
            target_id=target_id,
            message_id=message.message_id,
            requested_send_time_ms=outbound.requested_at_ms,
            send_started_at_ms=outbound.started_at_ms,
            send_completed_at_ms=outbound.completed_at_ms,
            outbound_queue_delay_ms=outbound.queue_delay_ms,
            outbound_service_time_ms=outbound.service_time_ms,
            network_delay_ms=network_delay,
            arrival_time_ms=arrival,
            source_region=source.region,
            target_region=target.region,
        )

    def _on_epoch_boundary(self, slot: int) -> None:
        epoch = slot // self.config.protocol.epoch_length_slots
        transitions: list[dict[str, object]] = []
        for validator_id, validator in self.validators.items():
            if not validator.can_participate:
                continue
            old_head = validator.view.head_id
            transition = self.protocol.update_finality(validator, epoch)
            self.metrics.record_local_head_change(
                validator, old_head, validator.view.head_id, validator.view.known_blocks
            )
            if transition is None:
                continue
            if transition.justified:
                self.metrics.justification_transitions += 1
            if transition.finalized_epoch is not None:
                self.metrics.finalization_transitions += 1
            transitions.append(
                {
                    "validator_id": validator_id,
                    "target_epoch": transition.target_epoch,
                    "target_checkpoint_id": transition.target_checkpoint_id,
                    "supporting_stake": transition.supporting_stake,
                    "justified": transition.justified,
                    "finalized_epoch": transition.finalized_epoch,
                    "finalized_checkpoint_id": transition.finalized_checkpoint_id,
                }
            )

        heads = [validator.view.head_id for validator in self.validators.values()]
        self.metrics.record_head_agreement(self.validators)
        self.metrics.record_finality_state(
            self.validators,
            epoch,
            now_ms=self.now_ms,
            threshold=self.config.protocol.justification_threshold,
        )
        self._log(
            "epoch_boundary",
            slot=slot,
            epoch=epoch,
            heads=heads,
            finality_transitions=transitions,
        )
