# VALENCE v0.8.0

VALENCE v0.8.0 adds a version-pinned Ethereum-calibrated timing and validator-duty
profile while retaining the stable v0.7 Beacon-like engine.

## Added

- Ethereum `consensus-specs` v1.6.1 / stable Fulu profile metadata.
- Official minimal and mainnet timing and duty constants.
- Swap-or-not shuffling, committee partitioning, committee indices, effective-
  balance adaptation, and balance-weighted proposer selection.
- Deterministic domain-separated duty seeds for paired simulation experiments.
- Minimal and mainnet smoke configurations.
- Eleven Ethereum-focused tests and a 30-seed cross-model experiment.
- Explicit run metadata describing the deterministic RANDAO surrogate and the
  retained Beacon-like consensus engine.

## Scope warning

This release is Ethereum-calibrated for timing and duties; it is not a complete
Ethereum client and does not implement the full Fulu state transition, SSZ/BLS,
execution payloads, Engine API, or Ethereum peer-to-peer networking.
