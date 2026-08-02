from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from valence.consensus_analysis import (
    classify_blocks,
    reorganization_depth,
    stake_modal_head,
    supported_fork,
)
from valence.model import Block, Validator


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 12) if values else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] * (1 - fraction) + ordered[upper] * fraction, 12)


def _rate(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 12) if denominator else 0.0


def _new_duty_record() -> dict[str, float]:
    return {
        "proposal_assigned": 0,
        "proposal_completed": 0,
        "proposal_missed_offline": 0,
        "attestation_assigned": 0,
        "attestation_completed": 0,
        "attestation_on_time": 0,
        "attestation_late": 0,
        "attestation_missed_offline": 0,
        "attestation_current_head": 0,
        "attestation_stale_head": 0,
        "proposal_stake_assigned": 0.0,
        "proposal_stake_completed": 0.0,
        "attestation_stake_assigned": 0.0,
        "attestation_stake_completed": 0.0,
        "attestation_stake_on_time": 0.0,
    }


@dataclass
class MetricsCollector:
    blocks_created: int = 0
    attestations_created: int = 0
    on_time_attestations: int = 0
    late_attestations: int = 0
    current_slot_attestations: int = 0
    stale_head_attestations: int = 0
    processed_messages: int = 0
    stale_arrival_events: int = 0
    duplicate_arrivals_ignored: int = 0
    justification_transitions: int = 0
    finalization_transitions: int = 0
    transmission_bytes_attempted: int = 0
    delivered_bytes: int = 0
    processed_bytes: int = 0

    proposal_duties_assigned: int = 0
    proposal_duties_completed: int = 0
    proposal_duties_missed_offline: int = 0
    attestation_duties_assigned: int = 0
    attestation_duties_completed: int = 0
    attestation_duties_missed_offline: int = 0
    proposal_stake_assigned: float = 0.0
    proposal_stake_completed: float = 0.0
    attestation_stake_assigned: float = 0.0
    attestation_stake_completed: float = 0.0
    attestation_stake_on_time: float = 0.0

    outage_events_started: int = 0
    outage_events_ended: int = 0
    validator_outage_instances: int = 0
    validator_recoveries_completed: int = 0

    fork_episode_count: int = 0
    maximum_fork_width: int = 0
    local_reorganization_count: int = 0
    global_reorganization_count: int = 0
    validators_experiencing_reorganization: set[int] = field(default_factory=set)
    local_reorganization_depths: list[int] = field(default_factory=list)
    global_reorganization_depths: list[int] = field(default_factory=list)
    fork_episode_durations_slots: list[float] = field(default_factory=list)
    fork_episode_durations_ms: list[int] = field(default_factory=list)
    fork_episode_records: list[dict[str, Any]] = field(default_factory=list)

    head_agreement_by_epoch: list[float] = field(default_factory=list)
    stake_weighted_head_agreement_by_epoch: list[float] = field(default_factory=list)
    head_agreement_by_slot: list[float] = field(default_factory=list)
    stake_weighted_head_agreement_by_slot: list[float] = field(default_factory=list)
    modal_head_by_epoch: list[str] = field(default_factory=list)
    stake_modal_head_by_epoch: list[str] = field(default_factory=list)
    boundary_epochs: list[int] = field(default_factory=list)
    stake_weighted_justified_epoch: list[float] = field(default_factory=list)
    stake_weighted_finalized_epoch: list[float] = field(default_factory=list)
    finality_agreement_by_epoch: list[float] = field(default_factory=list)
    modal_finalized_checkpoint_by_epoch: list[str] = field(default_factory=list)

    _outbound_queue_delays: list[int] = field(default_factory=list, repr=False)
    _outbound_service_times: list[int] = field(default_factory=list, repr=False)
    _network_delays: list[int] = field(default_factory=list, repr=False)
    _inbound_queue_delays: list[int] = field(default_factory=list, repr=False)
    _inbound_service_times: list[int] = field(default_factory=list, repr=False)
    _processing_queue_delays: list[int] = field(default_factory=list, repr=False)
    _processing_service_times: list[int] = field(default_factory=list, repr=False)
    _end_to_end_delays: list[int] = field(default_factory=list, repr=False)
    _duty_by_validator: dict[int, dict[str, float]] = field(default_factory=dict, repr=False)
    _slot_attestation_assigned: dict[int, int] = field(default_factory=dict, repr=False)
    _slot_attestation_completed: dict[int, int] = field(default_factory=dict, repr=False)
    _slot_attestation_stake_assigned: dict[int, float] = field(default_factory=dict, repr=False)
    _slot_attestation_stake_completed: dict[int, float] = field(default_factory=dict, repr=False)
    _fork_active_start_slot: int | None = field(default=None, repr=False)
    _fork_active_start_ms: int | None = field(default=None, repr=False)
    _fork_active_max_width: int = field(default=0, repr=False)
    _fork_active_heads: set[str] = field(default_factory=set, repr=False)
    _fork_slot_duration_ms: int = field(default=1, repr=False)
    _previous_global_head: str | None = field(default=None, repr=False)
    _checkpoint_targets: dict[str, dict[str, int]] = field(default_factory=dict, repr=False)
    _checkpoint_finalized_at_ms: dict[str, int] = field(default_factory=dict, repr=False)

    def _validator_duties(self, validator_id: int) -> dict[str, float]:
        return self._duty_by_validator.setdefault(validator_id, _new_duty_record())

    def record_proposal_duty(self, validator: Validator, completed: bool) -> None:
        record = self._validator_duties(validator.validator_id)
        self.proposal_duties_assigned += 1
        self.proposal_stake_assigned += validator.stake
        record["proposal_assigned"] += 1
        record["proposal_stake_assigned"] += validator.stake
        if completed:
            self.proposal_duties_completed += 1
            self.proposal_stake_completed += validator.stake
            record["proposal_completed"] += 1
            record["proposal_stake_completed"] += validator.stake
        else:
            self.proposal_duties_missed_offline += 1
            record["proposal_missed_offline"] += 1

    def record_attestation_assignment(self, validator: Validator, slot: int) -> None:
        record = self._validator_duties(validator.validator_id)
        self.attestation_duties_assigned += 1
        self.attestation_stake_assigned += validator.stake
        record["attestation_assigned"] += 1
        record["attestation_stake_assigned"] += validator.stake
        self._slot_attestation_assigned[slot] = self._slot_attestation_assigned.get(slot, 0) + 1
        self._slot_attestation_stake_assigned[slot] = (
            self._slot_attestation_stake_assigned.get(slot, 0.0) + validator.stake
        )

    def record_attestation_missed_offline(self, validator: Validator, slot: int) -> None:
        record = self._validator_duties(validator.validator_id)
        self.attestation_duties_missed_offline += 1
        record["attestation_missed_offline"] += 1

    def record_attestation_completed(
        self,
        validator: Validator,
        slot: int,
        *,
        on_time: bool,
        current_head: bool,
    ) -> None:
        record = self._validator_duties(validator.validator_id)
        self.attestation_duties_completed += 1
        self.attestation_stake_completed += validator.stake
        record["attestation_completed"] += 1
        record["attestation_stake_completed"] += validator.stake
        self._slot_attestation_completed[slot] = self._slot_attestation_completed.get(slot, 0) + 1
        self._slot_attestation_stake_completed[slot] = (
            self._slot_attestation_stake_completed.get(slot, 0.0) + validator.stake
        )
        if on_time:
            self.on_time_attestations += 1
            self.attestation_stake_on_time += validator.stake
            record["attestation_on_time"] += 1
            record["attestation_stake_on_time"] += validator.stake
        else:
            self.late_attestations += 1
            record["attestation_late"] += 1
        if current_head:
            self.current_slot_attestations += 1
            record["attestation_current_head"] += 1
        else:
            self.stale_head_attestations += 1
            record["attestation_stale_head"] += 1

    def record_outbound(self, queue_delay_ms: int, service_time_ms: int, size_bytes: int) -> None:
        self._outbound_queue_delays.append(queue_delay_ms)
        self._outbound_service_times.append(service_time_ms)
        self.transmission_bytes_attempted += size_bytes

    def record_delivery_pipeline(
        self,
        *,
        network_delay_ms: int,
        inbound_queue_delay_ms: int,
        inbound_service_time_ms: int,
        processing_queue_delay_ms: int,
        processing_service_time_ms: int,
        end_to_end_delay_ms: int,
        size_bytes: int,
    ) -> None:
        self._network_delays.append(network_delay_ms)
        self._inbound_queue_delays.append(inbound_queue_delay_ms)
        self._inbound_service_times.append(inbound_service_time_ms)
        self._processing_queue_delays.append(processing_queue_delay_ms)
        self._processing_service_times.append(processing_service_time_ms)
        self._end_to_end_delays.append(end_to_end_delay_ms)
        self.delivered_bytes += size_bytes

    def record_processed_bytes(self, size_bytes: int) -> None:
        self.processed_bytes += size_bytes

    @staticmethod
    def _agreement(validators: dict[int, Validator]) -> tuple[str, float, str, float]:
        heads = [validator.view.head_id for validator in validators.values()]
        counts = Counter(heads)
        modal, frequency = min(
            ((head, count) for head, count in counts.items()),
            key=lambda item: (-item[1], item[0]),
        )
        stake_support: dict[str, float] = defaultdict(float)
        total_stake = 0.0
        for validator in validators.values():
            stake_support[validator.view.head_id] += validator.stake
            total_stake += validator.stake
        stake_modal, modal_stake = min(stake_support.items(), key=lambda item: (-item[1], item[0]))
        return modal, frequency / len(heads), stake_modal, modal_stake / total_stake if total_stake else 0.0

    def record_slot_chain_state(
        self,
        slot: int,
        validators: dict[int, Validator],
        blocks: dict[str, Block],
        minimum_branch_support: float,
        time_ms: int | None = None,
        slot_duration_ms: int = 1,
    ) -> None:
        if not validators:
            return
        _, count_agreement, _, stake_agreement = self._agreement(validators)
        self.head_agreement_by_slot.append(count_agreement)
        self.stake_weighted_head_agreement_by_slot.append(stake_agreement)

        current_global = stake_modal_head(validators)
        if self._previous_global_head is not None:
            depth = reorganization_depth(self._previous_global_head, current_global, blocks)
            if depth > 0:
                self.global_reorganization_count += 1
                self.global_reorganization_depths.append(depth)
        self._previous_global_head = current_global

        self.record_fork_observation(
            time_ms=slot if time_ms is None else time_ms,
            slot=slot,
            validators=validators,
            blocks=blocks,
            minimum_branch_support=minimum_branch_support,
            slot_duration_ms=slot_duration_ms,
        )

    def record_fork_observation(
        self,
        *,
        time_ms: int,
        slot: int,
        validators: dict[int, Validator],
        blocks: dict[str, Block],
        minimum_branch_support: float,
        slot_duration_ms: int = 1,
    ) -> None:
        self._fork_slot_duration_ms = max(1, slot_duration_ms)
        fork = supported_fork(validators, blocks, minimum_branch_support)
        observation_ms = time_ms
        if fork is not None:
            self.maximum_fork_width = max(self.maximum_fork_width, fork.width)
            if self._fork_active_start_slot is None:
                self._fork_active_start_slot = slot
                self._fork_active_start_ms = observation_ms
                self._fork_active_max_width = fork.width
                self._fork_active_heads = set(fork.heads)
                self.fork_episode_count += 1
            else:
                self._fork_active_max_width = max(self._fork_active_max_width, fork.width)
                self._fork_active_heads.update(fork.heads)
        elif self._fork_active_start_slot is not None:
            self._close_fork_episode(slot, observation_ms)

    def _close_fork_episode(self, end_slot: int, end_ms: int) -> None:
        if self._fork_active_start_slot is None:
            return
        start_ms = self._fork_active_start_ms if self._fork_active_start_ms is not None else end_ms
        duration_ms = max(0, end_ms - start_ms)
        duration_slots = round(duration_ms / self._fork_slot_duration_ms, 12)
        self.fork_episode_durations_slots.append(duration_slots)
        self.fork_episode_durations_ms.append(duration_ms)
        self.fork_episode_records.append(
            {
                "start_slot": self._fork_active_start_slot,
                "end_slot": end_slot,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_slots": duration_slots,
                "duration_ms": duration_ms,
                "maximum_width": self._fork_active_max_width,
                "observed_heads": sorted(self._fork_active_heads),
            }
        )
        self._fork_active_start_slot = None
        self._fork_active_start_ms = None
        self._fork_active_max_width = 0
        self._fork_active_heads.clear()

    def finalize_fork_tracking(self, end_slot: int, end_ms: int | None = None) -> None:
        if self._fork_active_start_slot is not None:
            self._close_fork_episode(end_slot, end_slot if end_ms is None else end_ms)

    def record_local_head_change(
        self,
        validator: Validator,
        old_head: str,
        new_head: str,
        blocks: dict[str, Block],
    ) -> None:
        depth = reorganization_depth(old_head, new_head, blocks)
        if depth <= 0:
            return
        self.local_reorganization_count += 1
        self.local_reorganization_depths.append(depth)
        self.validators_experiencing_reorganization.add(validator.validator_id)

    def record_head_agreement(self, validators: dict[int, Validator]) -> None:
        if not validators:
            return
        modal, count_agreement, stake_modal, stake_agreement = self._agreement(validators)
        self.modal_head_by_epoch.append(modal)
        self.stake_modal_head_by_epoch.append(stake_modal)
        self.head_agreement_by_epoch.append(count_agreement)
        self.stake_weighted_head_agreement_by_epoch.append(stake_agreement)

    def record_checkpoint_target(
        self,
        checkpoint_id: str,
        target_epoch: int,
        created_at_ms: int,
    ) -> None:
        if checkpoint_id == "genesis":
            return
        current = self._checkpoint_targets.get(checkpoint_id)
        record = {"target_epoch": int(target_epoch), "created_at_ms": int(created_at_ms)}
        if current is None or record["created_at_ms"] < current["created_at_ms"]:
            self._checkpoint_targets[checkpoint_id] = record

    def record_finality_state(
        self,
        validators: dict[int, Validator],
        boundary_epoch: int,
        now_ms: int | None = None,
        threshold: float = 2 / 3,
    ) -> None:
        self.boundary_epochs.append(boundary_epoch)
        justified = 0.0
        finalized = 0.0
        support: dict[tuple[int, str], float] = defaultdict(float)
        total_stake = sum(validator.stake for validator in validators.values())
        for validator in validators.values():
            stake = validator.stake
            view = validator.view
            justified += stake * view.justified_epoch
            finalized += stake * view.finalized_epoch
            support[(view.finalized_epoch, view.finalized_checkpoint)] += stake

        modal_state, modal_stake = max(support.items(), key=lambda item: (item[1], item[0][0], item[0][1]))
        self.stake_weighted_justified_epoch.append(round(justified / total_stake, 12))
        self.stake_weighted_finalized_epoch.append(round(finalized / total_stake, 12))
        self.finality_agreement_by_epoch.append(round(modal_stake / total_stake, 12))
        self.modal_finalized_checkpoint_by_epoch.append(modal_state[1])
        if now_ms is not None:
            for (_epoch, checkpoint_id), stake in support.items():
                if checkpoint_id == "genesis" or stake + 1e-12 < threshold:
                    continue
                self._checkpoint_finalized_at_ms.setdefault(checkpoint_id, int(now_ms))

    @staticmethod
    def _delay_summary(prefix: str, values: list[float]) -> dict[str, float]:
        return {
            f"mean_{prefix}_ms": _mean(values),
            f"p50_{prefix}_ms": _percentile(values, 0.50),
            f"p95_{prefix}_ms": _percentile(values, 0.95),
            f"p99_{prefix}_ms": _percentile(values, 0.99),
            f"p999_{prefix}_ms": _percentile(values, 0.999),
            f"max_{prefix}_ms": float(max(values, default=0)),
        }

    def _availability_group_summary(
        self,
        validator_ids: list[int],
    ) -> dict[str, float]:
        records = [self._validator_duties(validator_id) for validator_id in validator_ids]
        totals = {key: sum(float(record[key]) for record in records) for key in _new_duty_record()}
        return {
            "proposal_duties_assigned": int(totals["proposal_assigned"]),
            "proposal_duties_completed": int(totals["proposal_completed"]),
            "proposal_availability": _rate(totals["proposal_completed"], totals["proposal_assigned"]),
            "stake_weighted_proposal_availability": _rate(
                totals["proposal_stake_completed"], totals["proposal_stake_assigned"]
            ),
            "attestation_duties_assigned": int(totals["attestation_assigned"]),
            "attestation_duties_completed": int(totals["attestation_completed"]),
            "attestation_completion_rate": _rate(
                totals["attestation_completed"], totals["attestation_assigned"]
            ),
            "attestation_availability": _rate(
                totals["attestation_on_time"], totals["attestation_assigned"]
            ),
            "stake_weighted_attestation_availability": _rate(
                totals["attestation_stake_on_time"], totals["attestation_stake_assigned"]
            ),
            "attestation_duties_missed_offline": int(totals["attestation_missed_offline"]),
        }

    def availability_summary(
        self,
        validators: dict[int, Validator],
        nominal_time_ms: int,
        participation_threshold: float,
    ) -> dict[str, Any]:
        by_validator: dict[str, Any] = {}
        for validator_id, validator in sorted(validators.items()):
            record = self._validator_duties(validator_id)
            by_validator[str(validator_id)] = {
                **{key: round(value, 12) for key, value in record.items()},
                "region": validator.region,
                "isp": validator.isp,
                "stake": validator.stake,
                "operational_availability": _rate(
                    max(0, nominal_time_ms - validator.unavailable_time_ms), nominal_time_ms
                ),
            }

        region_ids: dict[str, list[int]] = defaultdict(list)
        isp_ids: dict[str, list[int]] = defaultdict(list)
        for validator_id, validator in validators.items():
            region_ids[validator.region].append(validator_id)
            isp_ids[validator.isp].append(validator_id)

        slot_count_rates: list[float] = []
        slot_stake_rates: list[float] = []
        slot_records: dict[str, dict[str, float]] = {}
        for slot in sorted(self._slot_attestation_assigned):
            assigned = self._slot_attestation_assigned[slot]
            completed = self._slot_attestation_completed.get(slot, 0)
            assigned_stake = self._slot_attestation_stake_assigned.get(slot, 0.0)
            completed_stake = self._slot_attestation_stake_completed.get(slot, 0.0)
            count_rate = _rate(completed, assigned)
            stake_rate = _rate(completed_stake, assigned_stake)
            slot_count_rates.append(count_rate)
            slot_stake_rates.append(stake_rate)
            slot_records[str(slot)] = {
                "assigned": assigned,
                "completed": completed,
                "participation_rate": count_rate,
                "assigned_stake": round(assigned_stake, 12),
                "completed_stake": round(completed_stake, 12),
                "stake_participation_rate": stake_rate,
            }

        total_validator_time = nominal_time_ms * len(validators)
        total_unavailable = sum(validator.unavailable_time_ms for validator in validators.values())
        return {
            "proposal_availability": _rate(
                self.proposal_duties_completed, self.proposal_duties_assigned
            ),
            "stake_weighted_proposal_availability": _rate(
                self.proposal_stake_completed, self.proposal_stake_assigned
            ),
            "attestation_completion_rate": _rate(
                self.attestation_duties_completed, self.attestation_duties_assigned
            ),
            "attestation_availability": _rate(
                self.on_time_attestations, self.attestation_duties_assigned
            ),
            "stake_weighted_attestation_availability": _rate(
                self.attestation_stake_on_time, self.attestation_stake_assigned
            ),
            "mean_committee_participation_rate": _mean(slot_count_rates),
            "mean_committee_stake_participation_rate": _mean(slot_stake_rates),
            "fraction_slots_below_participation_threshold": _rate(
                sum(value + 1e-12 < participation_threshold for value in slot_stake_rates),
                len(slot_stake_rates),
            ),
            "operational_availability": _rate(
                max(0, total_validator_time - total_unavailable), total_validator_time
            ),
            "committee_participation_by_slot": slot_records,
            "by_validator": by_validator,
            "by_region": {
                region: self._availability_group_summary(ids)
                for region, ids in sorted(region_ids.items())
            },
            "by_isp": {
                isp: self._availability_group_summary(ids)
                for isp, ids in sorted(isp_ids.items())
            },
        }

    def fork_summary(
        self,
        blocks: dict[str, Block],
        validators: dict[int, Validator],
        slots: int,
        settlement_slots: int,
    ) -> dict[str, Any]:
        canonical_head = stake_modal_head(validators)
        classifications = classify_blocks(
            blocks,
            canonical_head,
            final_slot=max(0, slots - 1),
            settlement_slots=settlement_slots,
        )
        counts = Counter(classifications.values())
        created = len(classifications)
        orphaned = counts.get("orphaned", 0)
        return {
            "canonical_head": canonical_head,
            "canonical_blocks": counts.get("canonical", 0),
            "orphaned_blocks": orphaned,
            "unresolved_blocks": counts.get("unresolved", 0),
            "orphaned_block_rate": _rate(orphaned, created),
            "orphaned_blocks_per_1000_slots": round(orphaned * 1000 / slots, 12) if slots else 0.0,
            "fork_episode_count": self.fork_episode_count,
            "fork_rate_per_1000_slots": round(self.fork_episode_count * 1000 / slots, 12) if slots else 0.0,
            "mean_fork_duration_slots": _mean(self.fork_episode_durations_slots),
            "maximum_fork_duration_slots": max(self.fork_episode_durations_slots, default=0),
            "mean_fork_duration_ms": _mean(self.fork_episode_durations_ms),
            "maximum_fork_duration_ms": max(self.fork_episode_durations_ms, default=0),
            "maximum_fork_width": self.maximum_fork_width,
            "fork_episode_records": self.fork_episode_records,
            "local_reorganization_count": self.local_reorganization_count,
            "global_reorganization_count": self.global_reorganization_count,
            "validators_experiencing_reorganization": len(self.validators_experiencing_reorganization),
            "mean_local_reorganization_depth": _mean(self.local_reorganization_depths),
            "maximum_local_reorganization_depth": max(self.local_reorganization_depths, default=0),
            "mean_global_reorganization_depth": _mean(self.global_reorganization_depths),
            "maximum_global_reorganization_depth": max(self.global_reorganization_depths, default=0),
            "block_classification": classifications,
        }

    def finality_timing_summary(self, end_ms: int) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        samples: list[float] = []
        for checkpoint_id, target in sorted(
            self._checkpoint_targets.items(), key=lambda item: (item[1]["target_epoch"], item[0])
        ):
            finalized_at = self._checkpoint_finalized_at_ms.get(checkpoint_id)
            created_at = target["created_at_ms"]
            if finalized_at is None:
                records.append(
                    {
                        "checkpoint_id": checkpoint_id,
                        **target,
                        "finalized_at_ms": None,
                        "time_to_finality_ms": None,
                        "right_censored": True,
                        "censor_time_ms": max(0, end_ms - created_at),
                    }
                )
            else:
                ttf = max(0, finalized_at - created_at)
                samples.append(float(ttf))
                records.append(
                    {
                        "checkpoint_id": checkpoint_id,
                        **target,
                        "finalized_at_ms": finalized_at,
                        "time_to_finality_ms": ttf,
                        "right_censored": False,
                        "censor_time_ms": None,
                    }
                )
        finalized = len(samples)
        total = len(records)
        return {
            "checkpoint_finality_records": records,
            "checkpoint_finalization_rate": _rate(finalized, total),
            "finalized_checkpoints": finalized,
            "censored_checkpoints": total - finalized,
            "mean_checkpoint_time_to_finality_ms": _mean(samples),
            "p50_checkpoint_time_to_finality_ms": _percentile(samples, 0.50),
            "p95_checkpoint_time_to_finality_ms": _percentile(samples, 0.95),
            "p99_checkpoint_time_to_finality_ms": _percentile(samples, 0.99),
            "maximum_checkpoint_time_to_finality_ms": max(samples, default=0.0),
        }

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        for key in list(result):
            if key.startswith("_"):
                result.pop(key)
        result["validators_experiencing_reorganization"] = len(
            self.validators_experiencing_reorganization
        )

        head_values = self.head_agreement_by_epoch
        stake_head_values = self.stake_weighted_head_agreement_by_epoch
        finality_values = self.finality_agreement_by_epoch
        result["mean_head_agreement"] = _mean(head_values)
        result["mean_stake_weighted_head_agreement"] = _mean(stake_head_values)
        slot_head_values = self.head_agreement_by_slot
        slot_stake_values = self.stake_weighted_head_agreement_by_slot
        result["mean_slot_head_agreement"] = _mean(slot_head_values)
        result["mean_slot_stake_weighted_head_agreement"] = _mean(slot_stake_values)
        result["minimum_slot_stake_weighted_head_agreement"] = (
            round(min(slot_stake_values), 12) if slot_stake_values else 0.0
        )
        result["slot_divergence_rate_below_0_9"] = _rate(
            sum(value < 0.9 for value in slot_stake_values), len(slot_stake_values)
        )
        total_attestations = self.current_slot_attestations + self.stale_head_attestations
        result["current_slot_attestation_rate"] = _rate(
            self.current_slot_attestations, total_attestations
        )
        result["stale_head_attestation_rate"] = _rate(
            self.stale_head_attestations, total_attestations
        )
        result["mean_finality_agreement"] = _mean(finality_values)
        if self.boundary_epochs and self.stake_weighted_finalized_epoch:
            finality_lags = [
                round(boundary - finalized, 12)
                for boundary, finalized in zip(
                    self.boundary_epochs, self.stake_weighted_finalized_epoch
                )
            ]
            result["finality_lag_by_boundary"] = finality_lags
            result["finality_lag_epochs"] = finality_lags[-1]
            result["maximum_finality_lag_epochs"] = round(max(finality_lags), 12)
            result["boundary_fraction_finality_lag_exceeds_one_epoch"] = _rate(
                sum(value > 1.0 for value in finality_lags), len(finality_lags)
            )
            result["first_boundary_finality_lag_exceeds_one_epoch"] = next(
                (
                    int(boundary)
                    for boundary, lag in zip(self.boundary_epochs, finality_lags)
                    if lag > 1.0
                ),
                None,
            )
            result["recovered_to_one_epoch_by_end"] = int(finality_lags[-1] <= 1.0)
        else:
            result["finality_lag_by_boundary"] = []
            result["finality_lag_epochs"] = 0.0
            result["maximum_finality_lag_epochs"] = 0.0
            result["boundary_fraction_finality_lag_exceeds_one_epoch"] = 0.0
            result["first_boundary_finality_lag_exceeds_one_epoch"] = None
            result["recovered_to_one_epoch_by_end"] = 1
        result["finality_delay_exceeds_one_epoch"] = int(
            float(result["finality_lag_epochs"]) > 1.0
        )
        result["finality_delay_ever_exceeds_one_epoch"] = int(
            float(result["maximum_finality_lag_epochs"]) > 1.0
        )

        result.update(self._delay_summary("outbound_queue_delay", self._outbound_queue_delays))
        result.update(self._delay_summary("outbound_service_time", self._outbound_service_times))
        result.update(self._delay_summary("network_delay", self._network_delays))
        result.update(self._delay_summary("inbound_queue_delay", self._inbound_queue_delays))
        result.update(self._delay_summary("inbound_service_time", self._inbound_service_times))
        result.update(self._delay_summary("processing_queue_delay", self._processing_queue_delays))
        result.update(self._delay_summary("processing_service_time", self._processing_service_times))
        result.update(self._delay_summary("end_to_end_delay", self._end_to_end_delays))
        result["delivery_pipeline_samples"] = len(self._end_to_end_delays)
        result["outbound_transmission_attempts"] = len(self._outbound_queue_delays)
        return result
