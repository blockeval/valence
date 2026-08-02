from pathlib import Path

import numpy as np
import pytest
import yaml

from valence.config import LatencyConfig, LatencyPairConfig, NetworkConfig, load_config
from valence.network import NetworkModel, sample_quantile_latency_ms


def percentile(values: np.ndarray, q: float) -> float:
    return float(np.quantile(values, q))


def test_quantile_sampler_matches_p50_p95_p99():
    rng = np.random.default_rng(11)
    values = np.asarray(
        [sample_quantile_latency_ms(rng, 100.0, 400.0, 1200.0) for _ in range(120_000)]
    )
    assert percentile(values, 0.50) == pytest.approx(100.0, rel=0.03)
    assert percentile(values, 0.95) == pytest.approx(400.0, rel=0.05)
    assert percentile(values, 0.99) == pytest.approx(1200.0, rel=0.08)


def test_changing_only_p99_preserves_lower_anchors_and_changes_tail():
    low_rng = np.random.default_rng(29)
    high_rng = np.random.default_rng(29)
    low = np.asarray(
        [sample_quantile_latency_ms(low_rng, 100.0, 500.0, 1000.0) for _ in range(100_000)]
    )
    high = np.asarray(
        [sample_quantile_latency_ms(high_rng, 100.0, 500.0, 5000.0) for _ in range(100_000)]
    )
    assert percentile(high, 0.50) == pytest.approx(percentile(low, 0.50), rel=0.01)
    assert percentile(high, 0.95) == pytest.approx(percentile(low, 0.95), rel=0.02)
    assert percentile(high, 0.99) > 4 * percentile(low, 0.99)


def test_invalid_quantile_order_is_rejected(tmp_path: Path):
    config_path = tmp_path / "bad.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "network": {
                    "latency": {
                        "distribution": "quantile",
                        "p50_ms": 100,
                        "p95_ms": 90,
                        "p99_ms": 200,
                    }
                }
            }
        )
    )
    with pytest.raises(ValueError, match="p50_ms < p95_ms < p99_ms"):
        load_config(config_path)


def test_external_profile_is_loaded_relative_to_config(tmp_path: Path):
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        yaml.safe_dump(
            {
                "name": "test-profile",
                "source": "unit-test",
                "symmetric": True,
                "pairs": [
                    {
                        "source_region": "north_america",
                        "target_region": "europe",
                        "p50_ms": 80,
                        "p95_ms": 140,
                        "p99_ms": 280,
                    }
                ],
            }
        )
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "network": {
                    "latency": {
                        "distribution": "regional_profile",
                        "profile_path": "profile.yaml",
                    }
                }
            }
        )
    )
    config = load_config(config_path)
    assert config.network.latency.profile_name == "test-profile"
    assert config.network.latency.profile_source == "unit-test"
    assert len(config.network.latency.pairs) == 1
    assert config.network.latency.pairs[0].p99_ms == 280


def test_symmetric_profile_uses_reverse_pair():
    pair = LatencyPairConfig("north_america", "europe", p50_ms=80, p95_ms=140, p99_ms=280)
    config = NetworkConfig(
        latency=LatencyConfig(
            distribution="regional_profile",
            p50_ms=50,
            p95_ms=100,
            p99_ms=200,
            profile_symmetric=True,
            pairs=(pair,),
        )
    )
    model = NetworkModel(config, np.random.default_rng(5), np.random.default_rng(6))
    for time_ms in range(4000):
        model.sample_latency_ms(time_ms, time_ms + 1, time_ms, "europe", "north_america")
    summary = model.calibration_summary()["region_pair_latency"]["europe->north_america"]
    assert summary["target"]["p50_ms"] == 80
    assert summary["target"]["p99_ms"] == 280
    assert summary["observed_base"]["p99_ms"] > summary["observed_base"]["p95_ms"]


def test_empirical_pair_sampling_and_summary():
    pair = LatencyPairConfig(
        "north_america",
        "asia",
        mode="empirical",
        samples_ms=(10.0, 20.0, 30.0, 100.0),
    )
    config = NetworkConfig(
        latency=LatencyConfig(
            distribution="regional_profile",
            p50_ms=50,
            p95_ms=100,
            p99_ms=200,
            pairs=(pair,),
        )
    )
    model = NetworkModel(config, np.random.default_rng(4), np.random.default_rng(7))
    samples = [model.sample_latency_ms(i, i + 1, i, "north_america", "asia") for i in range(1000)]
    assert set(samples).issubset({10, 20, 30, 100})
    target = model.calibration_summary()["region_pair_latency"]["north_america->asia"]["target"]
    assert target["mode"] == "empirical"
    assert target["p99_ms"] <= 100
