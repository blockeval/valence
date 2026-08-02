from dataclasses import replace
from pathlib import Path
import pytest

from valence import ValenceSimulation, load_config


CONFIG = Path(__file__).parents[1] / "configs" / "smoke.yaml"


def test_explicit_stakes_are_normalized_and_preserved_proportionally():
    base = load_config(CONFIG)
    validator_config = replace(
        base.validators,
        count=4,
        explicit_stakes=(4.0, 3.0, 2.0, 1.0),
        stake_distribution="explicit",
    )
    topology = replace(base.topology, degree=2)
    config = replace(base, validators=validator_config, topology=topology)
    config.validate()
    simulation = ValenceSimulation(config)
    stakes = [simulation.validators[i].stake for i in range(4)]
    assert stakes == pytest.approx([0.4, 0.3, 0.2, 0.1])
    assert sum(stakes) == pytest.approx(1.0)


def test_lognormal_stakes_are_reproducible():
    base = load_config(CONFIG)
    validators = replace(
        base.validators,
        stake_distribution="lognormal",
        stake_sigma=1.2,
    )
    config = replace(base, validators=validators)
    first = ValenceSimulation(config)
    second = ValenceSimulation(config)
    first_stakes = [first.validators[i].stake for i in sorted(first.validators)]
    second_stakes = [second.validators[i].stake for i in sorted(second.validators)]
    assert first_stakes == second_stakes
    assert max(first_stakes) > min(first_stakes)
