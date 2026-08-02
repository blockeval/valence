from pathlib import Path

from valence import ValenceSimulation, load_config


CONFIG = Path(__file__).parents[1] / "configs" / "smoke.yaml"


def test_same_seed_is_bitwise_reproducible():
    config = load_config(CONFIG)
    first = ValenceSimulation(config).run()
    second = ValenceSimulation(config).run()
    assert first.canonical_hash() == second.canonical_hash()
    assert first.summary == second.summary


def test_no_loss_run_reaches_full_head_agreement():
    result = ValenceSimulation(load_config(CONFIG)).run()
    assert result.summary["network_drops"] == 0
    assert result.summary["blocks_created"] == 8
    assert result.summary["attestations_created"] == 32
    assert result.summary["mean_head_agreement"] == 1.0
    assert len(set(result.summary["final_heads"].values())) == 1


def test_every_created_message_is_processed_by_every_validator_without_loss():
    result = ValenceSimulation(load_config(CONFIG)).run()
    message_count = result.summary["blocks_created"] + result.summary["attestations_created"]
    assert result.summary["processed_messages"] == message_count * 16


def test_high_latency_causes_stale_head_attestations():
    from dataclasses import replace

    config = load_config(CONFIG)
    slow_latency = replace(config.network.latency, distribution="fixed", fixed_ms=5000)
    slow_network = replace(config.network, latency=slow_latency)
    fast_attestation = replace(config.protocol, attestation_delay_ms=1000)
    slow_config = replace(config, network=slow_network, protocol=fast_attestation)
    slow_config.validate()
    result = ValenceSimulation(slow_config).run()
    assert result.summary["stale_head_attestations"] > 0
    assert result.summary["current_slot_attestations"] < result.summary["attestations_created"]


def test_no_loss_full_committee_advances_finality():
    from dataclasses import replace

    config = load_config(CONFIG)
    simulation_config = replace(config.simulation, slots=12, record_events=False)
    protocol = replace(
        config.protocol,
        epoch_length_slots=3,
        committee_fraction=1.0,
        finality_enabled=True,
    )
    finality_config = replace(
        config,
        simulation=simulation_config,
        protocol=protocol,
    )
    finality_config.validate()
    result = ValenceSimulation(finality_config).run()
    states = result.summary["finality_states"].values()
    assert {state["justified_epoch"] for state in states} == {3}
    assert {state["finalized_epoch"] for state in states} == {2}
    assert result.summary["mean_finality_agreement"] == 1.0
    assert result.summary["finality_lag_epochs"] == 1.0
