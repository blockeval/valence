# VALENCE v0.8 validation

## Release scope

VALENCE v0.8 introduces a version-pinned Ethereum-calibrated timing and duty
profile. It does not claim a complete Ethereum consensus state transition.

## Automated tests

The final release test suite contains 75 tests, including 11 focused Ethereum
profile tests. They cover:

- v1.6.1 minimal and mainnet timing and duty constants;
- swap-or-not shuffling under 10- and 90-round presets;
- committee partitioning with one attestation assignment per validator per epoch;
- deterministic, seed-sensitive proposer and committee schedules;
- version-pinned configuration rejection;
- emitted profile and simulation-adapter metadata; and
- minimal and mainnet smoke executions.

## Thirty-seed cross-model experiment

The experiment uses paired seeds `4, 9, ..., 149`, 32 validators, 32 slots, a
6-second slot, eight slots per epoch, and a matched budget of four attestation
duties per slot. It compares:

- `beacon_simplified`, using VALENCE's random committee sampler; and
- `ethereum_calibrated/minimal`, using specification-aligned shuffling, committee
  partitioning, committee indices, and balance-weighted proposer selection.

The low condition uses p50/p95/p99 = 75/400/750 ms. The high condition keeps
p50 and p95 fixed and raises p99 to 6000 ms.

| Duty model | Delta agreement | Delta stale rate | Delta slots below 0.9 |
|---|---:|---:|---:|
| Beacon-like simplified | -0.02771 | +0.14323 | +0.08750 |
| Ethereum-calibrated | -0.02926 | +0.12813 | +0.09167 |

Every within-model tail effect in the table is significant after Holm correction
(`p = 0.000320`). The model-by-tail interactions are not significant:

- agreement: Holm-adjusted `p = 0.5174`;
- stale-attestation rate: Holm-adjusted `p = 0.3475`; and
- divergent-slot rate: Holm-adjusted `p = 0.9297`.

The result supports a bounded robustness claim: the primary staged tail effect
persists when VALENCE's random duty assignment is replaced with a
version-pinned Ethereum-calibrated duty schedule. It does not validate the full
Ethereum fork-choice or state-transition implementation.
