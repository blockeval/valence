# Ethereum-calibrated protocol profile

VALENCE v0.8 adds a version-pinned protocol profile for controlled timing and
validator-duty experiments. The profile is pinned to Ethereum
`consensus-specs` release **v1.6.1**, stable **Fulu**, and supports the official
`minimal` and `mainnet` presets.

## Implemented scope

The profile implements or pins:

- slot duration and slots per epoch;
- maximum committees per slot and target committee size;
- swap-or-not validator shuffling;
- committee partitioning and committee indices;
- balance-weighted proposer selection;
- effective-balance quantization for VALENCE stake;
- attestation and aggregation timing in basis points;
- source, target, and head fields in logical attestations; and
- deterministic, domain-separated epoch and slot seeds for repeatable studies.

Use either preset:

```yaml
protocol:
  implementation: ethereum_calibrated
  ethereum_spec_release: v1.6.1
  ethereum_fork: fulu
  ethereum_preset: minimal  # or mainnet
```

Version-pinned fields cannot be overridden. This prevents configurations from
claiming one Ethereum release while silently using incompatible timing or duty
constants.

## Deliberate simulation adapter

Ethereum derives duty seeds from beacon state and RANDAO mixes. VALENCE instead
uses a deterministic 32-byte simulation seed while preserving the specification's
domain, epoch, slot, shuffling, committee-partition, and proposer-selection
structure. This enables paired and exactly reproducible network experiments.
The resolved run metadata records `randao_mode: deterministic_simulation_surrogate`.

## Conformance boundary

`ethereum_calibrated` does **not** mean a complete Ethereum client or a complete
Fulu state transition. In v0.8, the following remain outside scope:

- SSZ serialization and hash-tree roots;
- BLS signature generation and verification;
- execution-payload validation and the Engine API;
- validator activation, exit, rewards, penalties, and slashing;
- sync committees and fork-specific data-availability processing;
- libp2p, GossipSub, discovery, and Req/Resp wire protocols; and
- the full Ethereum fork-choice store and proposer-boost behavior.

The underlying fork-choice and checkpoint-finality engine remains VALENCE's
auditable Beacon-like abstraction. `PROPOSER_SCORE_BOOST` is recorded as a
version-pinned profile constant but is not applied in v0.8.

## Validation

The automated suite checks both preset constants, fixed shuffle vectors derived
from the published swap-or-not algorithm, committee partitioning, proposer
selection determinism, version-pinning, one-attestation-duty-per-epoch behavior,
and emitted run metadata. The cross-model experiment compares the same low- and
high-p99 network conditions under matched duty budgets using the simplified and
Ethereum-calibrated duty schedulers.

Run:

```bash
pytest tests/test_ethereum_profile.py
valence run configs/ethereum_minimal_smoke.yaml --output results/ethereum-minimal
valence run configs/ethereum_mainnet_smoke.yaml --output results/ethereum-mainnet
python scripts/run_ethereum_cross_model_experiment.py \
  --output results/ethereum-cross-model-30
```
