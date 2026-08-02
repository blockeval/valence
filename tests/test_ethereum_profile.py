from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from valence import ValenceSimulation, load_config
from valence.protocols.ethereum_calibrated import (
    base_seed_from_integer,
    committee_count_per_slot,
    compute_committee,
    compute_shuffled_index,
    epoch_seed,
    get_preset,
)
from valence.protocols.ethereum_calibrated.spec import DOMAIN_BEACON_ATTESTER


ROOT = Path(__file__).parents[1]


def test_v161_minimal_profile_constants_match_published_preset():
    preset = get_preset("minimal")
    assert preset.slot_duration_ms == 6_000
    assert preset.slots_per_epoch == 8
    assert preset.max_committees_per_slot == 4
    assert preset.target_committee_size == 4
    assert preset.shuffle_round_count == 10
    assert preset.attestation_due_bps == 3333
    assert preset.aggregate_due_bps == 6667
    assert preset.attestation_due_ms == 1_999
    assert preset.aggregate_due_ms == 4_000


def test_v161_mainnet_profile_constants_match_published_preset():
    preset = get_preset("mainnet")
    assert preset.slot_duration_ms == 12_000
    assert preset.slots_per_epoch == 32
    assert preset.max_committees_per_slot == 64
    assert preset.target_committee_size == 128
    assert preset.shuffle_round_count == 90
    assert preset.attestation_due_ms == 3_999
    assert preset.aggregate_due_ms == 8_000


@pytest.mark.parametrize(
    ("rounds", "expected"),
    [
        (
            10,
            [12, 5, 2, 29, 31, 17, 6, 25, 26, 22, 20, 15, 16, 10, 7, 21,
             14, 13, 8, 0, 28, 27, 19, 18, 23, 11, 24, 4, 9, 3, 1, 30],
        ),
        (
            90,
            [13, 10, 19, 28, 26, 29, 21, 27, 7, 3, 6, 16, 12, 18, 30, 22,
             15, 23, 31, 2, 5, 20, 1, 0, 9, 8, 4, 24, 25, 17, 11, 14],
        ),
    ],
)
def test_swap_or_not_shuffling_vectors(rounds: int, expected: list[int]):
    seed = bytes.fromhex("00" * 31 + "01")
    actual = [compute_shuffled_index(i, 32, seed, rounds) for i in range(32)]
    assert actual == expected
    assert sorted(actual) == list(range(32))


def test_minimal_committees_partition_every_validator_once_per_epoch():
    preset = get_preset("minimal")
    indices = tuple(range(32))
    seed = epoch_seed(base_seed_from_integer(14), 0, DOMAIN_BEACON_ATTESTER)
    committees_per_slot = committee_count_per_slot(len(indices), preset)
    assert committees_per_slot == 1
    committees = [
        compute_committee(
            indices,
            seed,
            slot,
            preset.slots_per_epoch,
            preset.shuffle_round_count,
        )
        for slot in range(preset.slots_per_epoch)
    ]
    assert {len(committee) for committee in committees} == {4}
    flattened = [validator for committee in committees for validator in committee]
    assert sorted(flattened) == list(range(32))


def test_ethereum_profile_is_resolved_and_version_pinned():
    config = load_config(ROOT / "configs" / "ethereum_minimal_smoke.yaml")
    protocol = config.protocol
    assert protocol.implementation == "ethereum_calibrated"
    assert protocol.ethereum_spec_release == "v1.6.1"
    assert protocol.ethereum_fork == "fulu"
    assert protocol.ethereum_preset == "minimal"
    assert protocol.slot_duration_ms == 6_000
    assert protocol.epoch_length_slots == 8
    assert protocol.attestation_delay_ms == 1_999
    assert protocol.attestation_deadline_ms == 4_000


def test_version_pinned_fields_cannot_be_overridden(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text(
        """
simulation: {slots: 8}
validators:
  count: 32
  regions: [global]
  isps: [isp_a]
topology:
  degree: 2
  minimum_cross_region_peers: 0
protocol:
  implementation: ethereum_calibrated
  ethereum_preset: minimal
  slot_duration_ms: 12000
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="version-pinned"):
        load_config(path)


def test_ethereum_minimal_assigns_one_attestation_duty_per_epoch():
    config = load_config(ROOT / "configs" / "ethereum_minimal_smoke.yaml")
    simulation = ValenceSimulation(config)
    assignments = Counter(
        validator_id
        for slot in range(config.protocol.epoch_length_slots)
        for validator_id in simulation.protocol.committee_for_slot(slot)
    )
    assert set(assignments) == set(range(config.validators.count))
    assert set(assignments.values()) == {1}


def test_ethereum_schedule_is_deterministic_and_seed_sensitive():
    config = load_config(ROOT / "configs" / "ethereum_minimal_smoke.yaml")
    first = ValenceSimulation(config).protocol.schedule
    second = ValenceSimulation(config).protocol.schedule
    changed = ValenceSimulation(
        replace(config, simulation=replace(config.simulation, seed=config.simulation.seed + 1))
    ).protocol.schedule
    assert first == second
    assert first != changed


def test_ethereum_profile_metadata_and_duty_counts_are_emitted():
    result = ValenceSimulation(
        load_config(ROOT / "configs" / "ethereum_minimal_smoke.yaml")
    ).run()
    profile = result.summary["protocol_profile"]
    assert profile["implementation"] == "ethereum_calibrated"
    assert profile["ethereum_spec_release"] == "v1.6.1"
    assert profile["ethereum_fork"] == "fulu"
    assert profile["ethereum_preset"] == "minimal"
    assert profile["committees_per_slot_observed"] == [1]
    assert result.summary["attestation_duties_assigned"] == 64
    assert result.summary["attestations_created"] == 64


def test_ethereum_mainnet_profile_runs_one_epoch_with_spec_timing():
    config = load_config(ROOT / "configs" / "ethereum_mainnet_smoke.yaml")
    assert config.protocol.slot_duration_ms == 12_000
    assert config.protocol.epoch_length_slots == 32
    simulation = ValenceSimulation(config)
    assignments = Counter(
        validator_id
        for slot in range(config.protocol.epoch_length_slots)
        for validator_id in simulation.protocol.committee_for_slot(slot)
    )
    assert set(assignments) == set(range(config.validators.count))
    assert set(assignments.values()) == {1}
    result = simulation.run()
    assert result.summary["attestation_duties_assigned"] == 128
    assert result.summary["protocol_profile"]["ethereum_preset"] == "mainnet"
    assert result.summary["protocol_profile"]["randao_mode"] == "deterministic_simulation_surrogate"
    assert result.summary["protocol_profile"]["proposer_score_boost_applied"] is False
