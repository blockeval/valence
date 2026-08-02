import numpy as np

from valence.config import LatencyConfig, LossConfig, NetworkConfig
from valence.network import NetworkModel


def test_fixed_latency_is_exact():
    model = NetworkModel(
        NetworkConfig(latency=LatencyConfig(distribution="fixed", fixed_ms=75)),
        np.random.default_rng(1),
        np.random.default_rng(2),
    )
    arrivals = [model.transmit(0, 1, 1000, "a", "b") for _ in range(20)]
    assert arrivals == [1075] * 20


def test_gilbert_elliott_has_bursty_losses():
    config = NetworkConfig(
        latency=LatencyConfig(distribution="fixed", fixed_ms=1),
        loss=LossConfig(
            model="gilbert_elliott",
            good_to_bad=0.03,
            bad_to_good=0.15,
            loss_good=0.0,
            loss_bad=1.0,
        ),
    )
    model = NetworkModel(config, np.random.default_rng(1), np.random.default_rng(8))
    sequence = [model.is_dropped(0, 1, i, "a", "b") for i in range(5000)]
    loss_rate = sum(sequence) / len(sequence)
    # Stationary bad-state probability is 0.03 / (0.03 + 0.15) ~= 0.167.
    assert 0.12 < loss_rate < 0.22
    longest = 0
    current = 0
    for dropped in sequence:
        current = current + 1 if dropped else 0
        longest = max(longest, current)
    assert longest >= 5
