from __future__ import annotations

import math
from dataclasses import dataclass, field

from valence.config import ResourceConfig


@dataclass(frozen=True)
class OutboundPlan:
    requested_at_ms: int
    started_at_ms: int
    completed_at_ms: int
    queue_delay_ms: int
    service_time_ms: int


@dataclass(frozen=True)
class ProcessingPlan:
    arrived_at_ms: int
    ingress_started_at_ms: int
    ingress_completed_at_ms: int
    processing_started_at_ms: int
    processing_completed_at_ms: int
    inbound_queue_delay_ms: int
    inbound_service_time_ms: int
    processing_queue_delay_ms: int
    processing_service_time_ms: int


@dataclass
class ResourceModel:
    """Deterministic per-validator network-interface and CPU queues.

    Each validator has three single-server resources:

    * an aggregate outbound interface shared by all peers;
    * an aggregate inbound interface; and
    * one message-validation/processing server.

    The model intentionally uses integer milliseconds so runs remain exactly
    reproducible across platforms. It is a controlled resource model, not a
    packet-level TCP implementation.
    """

    config: ResourceConfig
    outbound_available_ms: dict[int, int] = field(default_factory=dict)
    inbound_available_ms: dict[int, int] = field(default_factory=dict)
    processor_available_ms: dict[int, int] = field(default_factory=dict)
    outbound_busy_ms: dict[int, int] = field(default_factory=dict)
    inbound_busy_ms: dict[int, int] = field(default_factory=dict)
    processing_busy_ms: dict[int, int] = field(default_factory=dict)

    @staticmethod
    def _transfer_time_ms(size_bytes: int, rate_mbps: float) -> int:
        if size_bytes <= 0:
            return 0
        milliseconds = (size_bytes * 8.0 * 1000.0) / (rate_mbps * 1_000_000.0)
        return max(1, int(math.ceil(milliseconds - 1e-12)))

    def schedule_outbound(
        self,
        validator_id: int,
        requested_at_ms: int,
        size_bytes: int,
    ) -> OutboundPlan:
        if not self.config.enabled:
            return OutboundPlan(
                requested_at_ms=requested_at_ms,
                started_at_ms=requested_at_ms,
                completed_at_ms=requested_at_ms,
                queue_delay_ms=0,
                service_time_ms=0,
            )

        started = max(
            requested_at_ms,
            self.outbound_available_ms.get(validator_id, requested_at_ms),
        )
        service = self._transfer_time_ms(
            size_bytes,
            self.config.outbound_bandwidth_mbps,
        )
        completed = started + service
        self.outbound_available_ms[validator_id] = completed
        self.outbound_busy_ms[validator_id] = (
            self.outbound_busy_ms.get(validator_id, 0) + service
        )
        return OutboundPlan(
            requested_at_ms=requested_at_ms,
            started_at_ms=started,
            completed_at_ms=completed,
            queue_delay_ms=started - requested_at_ms,
            service_time_ms=service,
        )

    def schedule_processing(
        self,
        validator_id: int,
        arrived_at_ms: int,
        size_bytes: int,
    ) -> ProcessingPlan:
        if not self.config.enabled:
            return ProcessingPlan(
                arrived_at_ms=arrived_at_ms,
                ingress_started_at_ms=arrived_at_ms,
                ingress_completed_at_ms=arrived_at_ms,
                processing_started_at_ms=arrived_at_ms,
                processing_completed_at_ms=arrived_at_ms,
                inbound_queue_delay_ms=0,
                inbound_service_time_ms=0,
                processing_queue_delay_ms=0,
                processing_service_time_ms=0,
            )

        ingress_started = max(
            arrived_at_ms,
            self.inbound_available_ms.get(validator_id, arrived_at_ms),
        )
        inbound_service = self._transfer_time_ms(
            size_bytes,
            self.config.inbound_bandwidth_mbps,
        )
        ingress_completed = ingress_started + inbound_service
        self.inbound_available_ms[validator_id] = ingress_completed
        self.inbound_busy_ms[validator_id] = (
            self.inbound_busy_ms.get(validator_id, 0) + inbound_service
        )

        processing_started = max(
            ingress_completed,
            self.processor_available_ms.get(validator_id, ingress_completed),
        )
        variable_processing = self._transfer_time_ms(
            size_bytes,
            self.config.processing_rate_mbps,
        )
        fixed_processing = int(math.ceil(self.config.processing_fixed_ms - 1e-12))
        processing_service = max(0, fixed_processing) + variable_processing
        processing_completed = processing_started + processing_service
        self.processor_available_ms[validator_id] = processing_completed
        self.processing_busy_ms[validator_id] = (
            self.processing_busy_ms.get(validator_id, 0) + processing_service
        )

        return ProcessingPlan(
            arrived_at_ms=arrived_at_ms,
            ingress_started_at_ms=ingress_started,
            ingress_completed_at_ms=ingress_completed,
            processing_started_at_ms=processing_started,
            processing_completed_at_ms=processing_completed,
            inbound_queue_delay_ms=ingress_started - arrived_at_ms,
            inbound_service_time_ms=inbound_service,
            processing_queue_delay_ms=processing_started - ingress_completed,
            processing_service_time_ms=processing_service,
        )

    @staticmethod
    def _utilization(
        busy: dict[int, int],
        validator_count: int,
        horizon_ms: int,
    ) -> tuple[float, float]:
        if validator_count <= 0 or horizon_ms <= 0:
            return 0.0, 0.0
        values = [busy.get(validator_id, 0) / horizon_ms for validator_id in range(validator_count)]
        return sum(values) / validator_count, max(values, default=0.0)

    def utilization_summary(
        self,
        validator_count: int,
        horizon_ms: int,
    ) -> dict[str, float | bool]:
        outbound_mean, outbound_max = self._utilization(
            self.outbound_busy_ms,
            validator_count,
            horizon_ms,
        )
        inbound_mean, inbound_max = self._utilization(
            self.inbound_busy_ms,
            validator_count,
            horizon_ms,
        )
        processing_mean, processing_max = self._utilization(
            self.processing_busy_ms,
            validator_count,
            horizon_ms,
        )
        return {
            "resource_model_enabled": self.config.enabled,
            "mean_outbound_utilization": round(outbound_mean, 12),
            "max_outbound_utilization": round(outbound_max, 12),
            "mean_inbound_utilization": round(inbound_mean, 12),
            "max_inbound_utilization": round(inbound_max, 12),
            "mean_processing_utilization": round(processing_mean, 12),
            "max_processing_utilization": round(processing_max, 12),
        }
