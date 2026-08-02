from __future__ import annotations

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
from valence.network import NetworkModel
from valence.network.distributions import (
    component_quantile,
    sample_component_ms,
    sample_spliced_ms,
)


def sample(component: LatencyComponentConfig, size: int = 80_000) -> np.ndarray:
    rng = np.random.default_rng(1701)
    return np.asarray([sample_component_ms(rng, component) for _ in range(size)])


@pytest.mark.parametrize("family", ["lognormal", "weibull", "loglogistic"])
def test_p50_p95_calibration_for_analytic_families(family: str):
    component = LatencyComponentConfig(
        family=family,
        calibration_mode="p50_p95",
        p50_ms=150,
        p95_ms=800,
        p99_ms=3000,
        max_ms=20_000,
    )
    values = sample(component)
    assert np.quantile(values, 0.50) == pytest.approx(150, rel=0.025)
    assert np.quantile(values, 0.95) == pytest.approx(800, rel=0.04)


def test_gamma_and_erlang_have_expected_means():
    gamma = LatencyComponentConfig(
        family="gamma", shape=2.5, scale_ms=100, shift_ms=25
    )
    erlang = LatencyComponentConfig(
        family="erlang", erlang_stages=3, scale_ms=80, shift_ms=20
    )
    assert sample(gamma, 50_000).mean() == pytest.approx(275, rel=0.025)
    assert sample(erlang, 50_000).mean() == pytest.approx(260, rel=0.025)


def test_truncated_normal_never_produces_negative_delay():
    component = LatencyComponentConfig(
        family="truncated_normal", mean_ms=20, stddev_ms=100
    )
    values = sample(component, 30_000)
    assert values.min() >= 0
    assert np.quantile(values, 0.99) > np.quantile(values, 0.95)


def test_lomax_and_gpd_are_distinct_tail_parameterizations():
    lomax = LatencyComponentConfig(
        family="lomax", shape=2.2, scale_ms=180, shift_ms=30
    )
    gpd = LatencyComponentConfig(
        family="generalized_pareto", shape=0.25, scale_ms=300, shift_ms=40
    )
    assert component_quantile(lomax, 0.99) == pytest.approx(1310.035, rel=1e-3)
    assert component_quantile(gpd, 0.99) == pytest.approx(2634.733, rel=1e-3)


def test_bounded_negative_shape_gpd_has_finite_endpoint():
    component = LatencyComponentConfig(
        family="generalized_pareto", shape=-0.25, scale_ms=1000, shift_ms=100
    )
    values = sample(component, 50_000)
    # Endpoint = shift - scale / shape = 4100 ms.
    assert values.max() < 4100
    assert component_quantile(component, 0.999999) < 4100


def test_mixture_samples_both_fast_and_slow_components():
    component = LatencyComponentConfig(
        family="mixture",
        components=(
            LatencyComponentConfig(family="fixed", fixed_ms=50, weight=0.8),
            LatencyComponentConfig(family="fixed", fixed_ms=1000, weight=0.2),
        ),
    )
    values = sample(component, 20_000)
    slow_fraction = float(np.mean(values == 1000))
    assert set(values) == {50.0, 1000.0}
    assert slow_fraction == pytest.approx(0.2, abs=0.015)


def test_spliced_distribution_preserves_body_and_adds_gpd_tail():
    latency = LatencyConfig(
        distribution="spliced",
        splice_quantile=0.99,
        max_ms=30_000,
        body=LatencyComponentConfig(
            family="lognormal",
            calibration_mode="p50_p95",
            p50_ms=150,
            p95_ms=800,
            p99_ms=1600,
        ),
        tail=LatencyComponentConfig(
            family="generalized_pareto", shape=0.25, scale_ms=2000
        ),
    )
    rng = np.random.default_rng(19)
    values = np.asarray([sample_spliced_ms(rng, latency) for _ in range(150_000)])
    assert np.quantile(values, 0.50) == pytest.approx(150, rel=0.03)
    assert np.quantile(values, 0.95) == pytest.approx(800, rel=0.05)
    assert np.quantile(values, 0.999) > 2 * np.quantile(values, 0.99)


def test_markov_modulated_latency_records_state_occupancy():
    latency = LatencyConfig(
        distribution="markov_modulated",
        states=(
            LatencyStateConfig(
                "normal", LatencyComponentConfig(family="fixed", fixed_ms=50)
            ),
            LatencyStateConfig(
                "congested", LatencyComponentConfig(family="fixed", fixed_ms=500)
            ),
        ),
        transition_matrix=((0.98, 0.02), (0.20, 0.80)),
        initial_state=0,
    )
    model = NetworkModel(
        NetworkConfig(latency=latency),
        np.random.default_rng(20),
        np.random.default_rng(21),
    )
    values = [model.sample_latency_ms(0, 1, index, "a", "b") for index in range(30_000)]
    occupancy = model.calibration_summary()["latency_state_occupancy"]
    assert set(values) == {50, 500}
    assert occupancy["normal"] > 0.85
    assert 0.05 < occupancy["congested"] < 0.15


def test_invalid_markov_transition_matrix_is_rejected(tmp_path: Path):
    path = tmp_path / "bad_markov.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "network": {
                    "latency": {
                        "distribution": "markov_modulated",
                        "states": [
                            {"name": "a", "component": {"family": "fixed", "fixed_ms": 10}},
                            {"name": "b", "component": {"family": "fixed", "fixed_ms": 20}},
                        ],
                        "transition_matrix": [[0.9, 0.2], [0.1, 0.9]],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sum to 1"):
        load_config(path)


def test_regional_profile_can_use_parameterized_distribution(tmp_path: Path):
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        yaml.safe_dump(
            {
                "name": "parameterized-pair",
                "pairs": [
                    {
                        "source_region": "north_america",
                        "target_region": "europe",
                        "mode": "distribution",
                        "distribution": "gamma",
                        "shape": 2.0,
                        "scale_ms": 40,
                        "shift_ms": 20,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "validators": {"regions": ["north_america", "europe"]},
                "network": {
                    "latency": {
                        "distribution": "regional_profile",
                        "profile_path": "profile.yaml",
                        "p50_ms": 50,
                        "p95_ms": 100,
                        "p99_ms": 200,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    model = NetworkModel(
        config.network, np.random.default_rng(8), np.random.default_rng(9)
    )
    values = [
        model.sample_latency_ms(index, index + 1, index, "north_america", "europe")
        for index in range(20_000)
    ]
    assert np.mean(values) == pytest.approx(100, rel=0.035)
    target = model.calibration_summary()["region_pair_latency"][
        "north_america->europe"
    ]["target"]
    assert target["family"] == "gamma"
