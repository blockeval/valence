from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import yaml

from valence.config import (
    LatencyComponentConfig,
    LatencyConfig,
    LatencyStateConfig,
    NetworkConfig,
    load_config,
)
from valence.metrics.collector import MetricsCollector
from valence.network import NetworkModel
from valence.network.distributions import stationary_distribution


ROOT = Path(__file__).resolve().parents[1]


def test_stationary_distribution_matches_two_state_closed_form():
    result = stationary_distribution(((0.995, 0.005), (0.045, 0.955)))
    assert result.tolist() == pytest.approx([0.9, 0.1], abs=1e-10)
    assert (result @ np.asarray(((0.995, 0.005), (0.045, 0.955)))).tolist() == pytest.approx(
        result.tolist(), abs=1e-10
    )


def test_stationary_initialization_produces_expected_global_occupancy():
    latency = LatencyConfig(
        distribution="markov_modulated",
        stationary_initialization=True,
        markov_scope="global",
        states=(
            LatencyStateConfig(
                "normal", LatencyComponentConfig(family="fixed", fixed_ms=50)
            ),
            LatencyStateConfig(
                "congested", LatencyComponentConfig(family="fixed", fixed_ms=500)
            ),
        ),
        transition_matrix=((0.995, 0.005), (0.045, 0.955)),
    )
    model = NetworkModel(
        NetworkConfig(latency=latency),
        np.random.default_rng(70),
        np.random.default_rng(71),
    )
    for index in range(50_000):
        model.sample_latency_ms(index % 4, (index + 1) % 4, index, "a", "b")
    summary = model.calibration_summary()
    assert summary["latency_state_occupancy"]["congested"] == pytest.approx(0.1, abs=0.025)
    assert summary["latency_state_same_transition_rate"] > 0.97
    assert summary["latency_state_run_summary"]["congested"]["mean_run_length"] > 10


def test_top_level_mixture_records_component_occupancy():
    latency = LatencyConfig(
        distribution="mixture",
        components=(
            LatencyComponentConfig(name="fast", family="fixed", fixed_ms=50, weight=0.8),
            LatencyComponentConfig(name="slow", family="fixed", fixed_ms=500, weight=0.2),
        ),
    )
    model = NetworkModel(
        NetworkConfig(latency=latency),
        np.random.default_rng(72),
        np.random.default_rng(73),
    )
    for index in range(30_000):
        model.sample_latency_ms(0, 1, index, "a", "b")
    occupancy = model.calibration_summary()["latency_component_occupancy"]
    assert occupancy["fast"] == pytest.approx(0.8, abs=0.02)
    assert occupancy["slow"] == pytest.approx(0.2, abs=0.02)


def test_invalid_markov_scope_is_rejected(tmp_path: Path):
    path = tmp_path / "bad_scope.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "network": {
                    "latency": {
                        "distribution": "markov_modulated",
                        "markov_scope": "planet",
                        "states": [
                            {"name": "a", "component": {"family": "fixed", "fixed_ms": 10}},
                            {"name": "b", "component": {"family": "fixed", "fixed_ms": 20}},
                        ],
                        "transition_matrix": [[0.9, 0.1], [0.2, 0.8]],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="markov_scope"):
        load_config(path)


def test_finality_collector_reports_maximum_and_recovery_metrics():
    collector = MetricsCollector(
        boundary_epochs=[0, 1, 2, 3, 4],
        stake_weighted_finalized_epoch=[0.0, 0.0, 0.0, 2.0, 3.0],
    )
    result = collector.to_dict()
    assert result["finality_lag_by_boundary"] == [0.0, 1.0, 2.0, 1.0, 1.0]
    assert result["maximum_finality_lag_epochs"] == 2.0
    assert result["boundary_fraction_finality_lag_exceeds_one_epoch"] == pytest.approx(0.2)
    assert result["first_boundary_finality_lag_exceeds_one_epoch"] == 2
    assert result["recovered_to_one_epoch_by_end"] == 1
    assert result["finality_delay_ever_exceeds_one_epoch"] == 1


def test_temporal_configs_have_identical_stationary_marginals_by_construction():
    iid = load_config(ROOT / "configs" / "temporal_iid_matched.yaml")
    markov = load_config(ROOT / "configs" / "temporal_markov_matched.yaml")
    weights = np.asarray([component.weight for component in iid.network.latency.components])
    weights = weights / weights.sum()
    stationary = stationary_distribution(markov.network.latency.transition_matrix)
    assert weights.tolist() == pytest.approx(stationary.tolist(), abs=1e-10)
    for component, state in zip(iid.network.latency.components, markov.network.latency.states):
        assert replace(component, name="", weight=1.0) == state.component


def test_tail_shape_configs_match_through_p99_and_differ_above_it():
    configs = [
        load_config(ROOT / "configs" / f"tail_{name}.yaml")
        for name in ("bounded", "exponential", "heavy")
    ]
    anchors = [
        (
            config.network.latency.splice_quantile,
            config.network.latency.body.p50_ms,
            config.network.latency.body.p95_ms,
            config.network.latency.body.p99_ms,
        )
        for config in configs
    ]
    assert len(set(anchors)) == 1
    shapes = [config.network.latency.tail.shape for config in configs]
    assert shapes == [-0.5, 0.0, 0.5]


def test_p99_runner_declares_adjacent_comparisons():
    import importlib.util

    path = ROOT / "scripts" / "run_p99_dose_sweep.py"
    spec = importlib.util.spec_from_file_location("p99_runner_v06", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    adjacent = [item for item in module.COMPARISONS if item[2] == "adjacent"]
    assert adjacent == [
        ("moderate", "low", "adjacent"),
        ("high", "moderate", "adjacent"),
        ("extreme", "high", "adjacent"),
    ]
