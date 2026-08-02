from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RandomStreams:
    topology: np.random.Generator
    stake: np.random.Generator
    proposer: np.random.Generator
    committee: np.random.Generator
    latency: np.random.Generator
    loss: np.random.Generator
    shock: np.random.Generator
    gossip: np.random.Generator
    placement: np.random.Generator
    faults: np.random.Generator

    @classmethod
    def from_seed(cls, seed: int) -> "RandomStreams":
        parent = np.random.SeedSequence(seed)
        children = parent.spawn(10)
        generators = [np.random.default_rng(child) for child in children]
        return cls(*generators)
