from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from valence import ValenceSimulation, load_config
from valence.config import ResourceConfig
from valence.resources import ResourceModel


CONFIG = Path(__file__).parents[1] / "configs" / "smoke.yaml"


def test_outbound_bandwidth_queue_is_deterministic():
    model = ResourceModel(
        ResourceConfig(
            enabled=True,
            outbound_bandwidth_mbps=8.0,
            inbound_bandwidth_mbps=8.0,
            processing_rate_mbps=8.0,
        )
    )
    first = model.schedule_outbound(validator_id=1, requested_at_ms=0, size_bytes=1_000_000)
    second = model.schedule_outbound(validator_id=1, requested_at_ms=100, size_bytes=1_000_000)

    assert first.started_at_ms == 0
    assert first.service_time_ms == 1000
    assert first.completed_at_ms == 1000
    assert second.started_at_ms == 1000
    assert second.queue_delay_ms == 900
    assert second.completed_at_ms == 2000


def test_inbound_and_processing_queues_are_separate():
    model = ResourceModel(
        ResourceConfig(
            enabled=True,
            outbound_bandwidth_mbps=8.0,
            inbound_bandwidth_mbps=4.0,
            processing_rate_mbps=2.0,
            processing_fixed_ms=5.0,
        )
    )
    first = model.schedule_processing(validator_id=2, arrived_at_ms=0, size_bytes=500_000)
    second = model.schedule_processing(validator_id=2, arrived_at_ms=100, size_bytes=500_000)

    assert first.inbound_service_time_ms == 1000
    assert first.processing_service_time_ms == 2005
    assert first.processing_completed_at_ms == 3005
    assert second.inbound_queue_delay_ms == 900
    assert second.processing_queue_delay_ms == 1005
    assert second.processing_completed_at_ms == 5010


def test_resource_model_can_be_disabled_for_idealized_runs():
    model = ResourceModel(ResourceConfig(enabled=False))
    outbound = model.schedule_outbound(0, 50, 10_000_000)
    processing = model.schedule_processing(1, 75, 10_000_000)

    assert outbound.completed_at_ms == 50
    assert outbound.queue_delay_ms == 0
    assert processing.processing_completed_at_ms == 75
    assert processing.inbound_queue_delay_ms == 0
    assert processing.processing_queue_delay_ms == 0


def test_invalid_resource_rate_is_rejected(tmp_path: Path):
    path = tmp_path / "bad-resources.yaml"
    path.write_text(
        yaml.safe_dump({"resources": {"processing_rate_mbps": 0}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="processing_rate_mbps"):
        load_config(path)


def test_resource_constraints_create_queueing_and_stale_attestations():
    base = load_config(CONFIG)
    network = replace(
        base.network,
        block_size_bytes=1_000_000,
        attestation_size_bytes=50_000,
        fanout=4,
    )
    protocol = replace(base.protocol, attestation_delay_ms=1000)
    fast_resources = replace(
        base.resources,
        enabled=True,
        outbound_bandwidth_mbps=10_000,
        inbound_bandwidth_mbps=10_000,
        processing_rate_mbps=10_000,
        processing_fixed_ms=0,
    )
    slow_resources = replace(
        base.resources,
        enabled=True,
        outbound_bandwidth_mbps=0.5,
        inbound_bandwidth_mbps=0.5,
        processing_rate_mbps=0.25,
        processing_fixed_ms=5,
    )

    fast_config = replace(
        base,
        network=network,
        protocol=protocol,
        resources=fast_resources,
    )
    slow_config = replace(
        base,
        network=network,
        protocol=protocol,
        resources=slow_resources,
    )
    fast_config.validate()
    slow_config.validate()

    fast = ValenceSimulation(fast_config).run().summary
    slow = ValenceSimulation(slow_config).run().summary

    assert slow["mean_outbound_queue_delay_ms"] > fast["mean_outbound_queue_delay_ms"]
    assert slow["mean_processing_queue_delay_ms"] > fast["mean_processing_queue_delay_ms"]
    assert slow["p95_end_to_end_delay_ms"] > fast["p95_end_to_end_delay_ms"]
    assert slow["stale_head_attestations"] > fast["stale_head_attestations"]
    assert slow["simulation_end_time_ms"] > slow["nominal_protocol_time_ms"]


def test_event_log_exposes_each_resource_stage():
    result = ValenceSimulation(load_config(CONFIG)).run()
    arrivals = [item for item in result.event_log if item["event"] == "message_arrived"]
    assert arrivals
    required = {
        "send_started_at_ms",
        "send_completed_at_ms",
        "network_delay_ms",
        "inbound_queue_delay_ms",
        "inbound_service_time_ms",
        "processing_queue_delay_ms",
        "processing_service_time_ms",
        "processing_completed_at_ms",
    }
    assert required.issubset(arrivals[0])
