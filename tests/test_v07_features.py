from dataclasses import replace
from pathlib import Path

import pytest

from valence import ValenceSimulation, load_config
from valence.config import FaultConfig, ValidatorConfig
from valence.consensus_analysis import (
    classify_blocks,
    reorganization_depth,
    supported_fork,
)
from valence.model import Block, LocalView, Validator


ROOT = Path(__file__).parents[1]
SMOKE = ROOT / "configs" / "smoke.yaml"
OUTAGE = ROOT / "configs" / "outage_demo.yaml"
FINALITY = ROOT / "configs" / "finality_demo.yaml"


def test_healthy_run_reports_full_explicit_availability():
    summary = ValenceSimulation(load_config(SMOKE)).run().summary
    assert summary["proposal_availability"] == 1.0
    assert summary["attestation_availability"] == 1.0
    assert summary["stake_weighted_attestation_availability"] == 1.0
    assert summary["availability"]["operational_availability"] == 1.0
    assert summary["attestation_duties_missed_offline"] == 0


def test_regional_outage_counts_missed_duties_and_recovers():
    summary = ValenceSimulation(load_config(OUTAGE)).run().summary
    assert summary["faults"][0]["target_ids"] == [1, 3, 5, 7]
    assert summary["faults"][0]["target_stake"] == pytest.approx(0.5)
    assert summary["attestation_duties_missed_offline"] == 8
    assert summary["proposal_duties_missed_offline"] == 2
    assert summary["attestation_availability"] == pytest.approx(0.875)
    slots = summary["availability"]["committee_participation_by_slot"]
    assert slots["2"]["stake_participation_rate"] == pytest.approx(0.5)
    assert slots["3"]["stake_participation_rate"] == pytest.approx(0.5)
    assert set(summary["validator_status"].values()) == {"online"}
    assert summary["validator_recoveries_completed"] == 4


def test_high_stake_outage_changes_stake_weighted_availability_more_than_count_rate():
    config = load_config(SMOKE)
    validators = ValidatorConfig(
        count=4,
        regions=("r",),
        isps=("i",),
        stake_distribution="explicit",
        explicit_stakes=(0.7, 0.1, 0.1, 0.1),
    )
    simulation = replace(config.simulation, slots=4, record_events=False)
    topology = replace(config.topology, degree=2, minimum_cross_region_peers=0)
    protocol = replace(config.protocol, committee_fraction=1.0, epoch_length_slots=2)
    faults = (
        FaultConfig(
            name="large_validator",
            scope="validator_ids",
            validator_ids=(0,),
            start_slot=1,
            duration_slots=1,
        ),
    )
    custom = replace(
        config,
        simulation=simulation,
        validators=validators,
        topology=topology,
        protocol=protocol,
        faults=faults,
    )
    custom.validate()
    summary = ValenceSimulation(custom).run().summary
    assert summary["availability"]["attestation_completion_rate"] == pytest.approx(15 / 16)
    assert summary["stake_weighted_attestation_availability"] == pytest.approx(3.3 / 4)
    assert summary["stake_weighted_attestation_availability"] < summary["attestation_availability"]


def _fork_fixture() -> tuple[dict[str, Block], dict[int, Validator]]:
    blocks = {
        "genesis": Block("genesis", -1, -1, None, 0),
        "a": Block("a", 0, 0, "genesis", 0),
        "b": Block("b", 1, 0, "a", 12_000),
        "c": Block("c", 1, 1, "a", 12_000),
    }
    validators = {
        0: Validator(0, 0.55, "r", "i", (1,), view=LocalView(known_blocks=blocks, head_id="b")),
        1: Validator(1, 0.45, "r", "i", (0,), view=LocalView(known_blocks=blocks, head_id="c")),
    }
    return blocks, validators


def test_supported_fork_requires_incompatible_stake_supported_heads():
    blocks, validators = _fork_fixture()
    fork = supported_fork(validators, blocks, minimum_support=0.1)
    assert fork is not None
    assert fork.width == 2
    assert set(fork.heads) == {"b", "c"}


def test_orphan_classification_and_reorganization_depth_are_explicit():
    blocks, _validators = _fork_fixture()
    classes = classify_blocks(blocks, canonical_head="b", final_slot=4, settlement_slots=1)
    assert classes["a"] == "canonical"
    assert classes["b"] == "canonical"
    assert classes["c"] == "orphaned"
    assert reorganization_depth("b", "c", blocks) == 1
    assert reorganization_depth("a", "b", blocks) == 0


def test_outage_run_reports_orphans_and_reorganizations():
    summary = ValenceSimulation(load_config(OUTAGE)).run().summary
    assert summary["forks"]["orphaned_blocks"] >= 1
    assert summary["forks"]["local_reorganization_count"] >= 1
    assert summary["maximum_reorganization_depth"] >= 1


def test_checkpoint_time_to_finality_records_finalized_and_censored_checkpoints():
    summary = ValenceSimulation(load_config(FINALITY)).run().summary
    timing = summary["finality_timing"]
    assert timing["finalized_checkpoints"] == 2
    assert timing["censored_checkpoints"] == 1
    assert timing["p95_checkpoint_time_to_finality_ms"] == 83_999
    for record in timing["checkpoint_finality_records"]:
        if not record["right_censored"]:
            assert record["finalized_at_ms"] >= record["created_at_ms"]


def test_isp_fault_selector_targets_only_matching_validators():
    config = load_config(OUTAGE)
    fault = replace(
        config.faults[0],
        name="isp_a_crash",
        scope="isp",
        targets=("isp_a",),
        start_slot=1,
        duration_slots=1,
        resynchronization_ms=0,
    )
    custom = replace(config, faults=(fault,))
    custom.validate()
    summary = ValenceSimulation(custom).run().summary
    assert summary["faults"][0]["target_ids"] == [0, 2, 4, 6]
    assert summary["faults"][0]["target_stake"] == pytest.approx(0.5)


def test_highest_stake_selector_reaches_requested_stake_fraction():
    config = load_config(SMOKE)
    validators = ValidatorConfig(
        count=4,
        regions=("r",),
        isps=("i",),
        stake_distribution="explicit",
        explicit_stakes=(0.7, 0.1, 0.1, 0.1),
    )
    custom = replace(
        config,
        simulation=replace(config.simulation, slots=3, record_events=False),
        validators=validators,
        topology=replace(config.topology, degree=2, minimum_cross_region_peers=0),
        protocol=replace(config.protocol, committee_fraction=1.0, epoch_length_slots=2),
        faults=(
            FaultConfig(
                name="highest_stake",
                scope="highest_stake",
                stake_fraction=0.6,
                start_slot=1,
                duration_slots=1,
            ),
        ),
    )
    custom.validate()
    summary = ValenceSimulation(custom).run().summary
    assert summary["faults"][0]["target_ids"] == [0]
    assert summary["faults"][0]["target_stake"] == pytest.approx(0.7)


def test_restart_recovery_prunes_unfinalized_branch():
    config = load_config(SMOKE)
    simulation = ValenceSimulation(config)
    validator = simulation.validators[0]
    genesis = validator.view.known_blocks["genesis"]
    finalized = Block("finalized", 1, 0, "genesis", 12_000)
    unfinalized = Block("unfinalized", 2, 0, "finalized", 24_000)
    validator.view.known_blocks = {
        "genesis": genesis,
        "finalized": finalized,
        "unfinalized": unfinalized,
    }
    validator.view.children = {
        "genesis": {"finalized"},
        "finalized": {"unfinalized"},
        "unfinalized": set(),
    }
    validator.view.finalized_checkpoint = "finalized"
    validator.view.finalized_epoch = 1
    validator.view.justified_checkpoint = "unfinalized"
    validator.view.justified_epoch = 2
    validator.view.head_id = "unfinalized"
    simulation._restart_from_finalized_checkpoint(validator)
    assert validator.view.head_id == "finalized"
    assert validator.view.justified_checkpoint == "finalized"
    assert validator.view.justified_epoch == 1
    assert "unfinalized" not in validator.view.known_blocks
