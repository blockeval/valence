# Configuration guide

VALENCE scenarios are YAML files validated before execution.

## Minimal run

```yaml
simulation:
  seed: 14
  slots: 8

validators:
  count: 16
  stake_distribution: equal

protocol:
  slot_duration_ms: 12000
  committee_fraction: 0.25

network:
  latency:
    distribution: fixed
    value_ms: 40
  packet_loss:
    model: none

resources:
  enabled: false
```

Run:

```bash
valence validate path/to/config.yaml
valence run path/to/config.yaml --output results/example
```

## Stake

Supported stake modes include equal, explicit values, and reproducible
lognormal samples. Metrics should be interpreted with stake-weighted results
when stake is heterogeneous.

## Topology

A regional overlay can be configured with weighted validator placement,
within-region bias, same-ISP bias, and minimum cross-region peers.

```yaml
validators:
  regions: [north_america, europe, asia, oceania]
  region_assignment: weighted
  region_weights: [0.40, 0.30, 0.20, 0.10]

topology:
  kind: regional_clustered
  degree: 6
  same_region_bias: 0.82
  same_isp_bias: 0.20
  minimum_cross_region_peers: 1
```

## Quantile-calibrated latency

```yaml
network:
  latency:
    distribution: quantile_piecewise
    p50_ms: 150
    p95_ms: 800
    p99_ms: 3000
    max_ms: 12000
```

The p50, p95, and p99 entries are independent anchors. VALENCE records target
and observed values in `latency_calibration.json`.

## Regional profiles

```yaml
network:
  latency:
    distribution: regional_profile
    profile_path: ../calibration/profiles/synthetic_global_quantiles.yaml
    p50_ms: 120
    p95_ms: 250
    p99_ms: 500
```

Fallback quantiles apply to unspecified region pairs.

## Resource constraints

```yaml
resources:
  enabled: true
  outbound_bandwidth_mbps: 100
  inbound_bandwidth_mbps: 100
  processing_rate_mbps: 50
  processing_fixed_ms: 1
```

Set `enabled: false` to isolate network latency and loss from validator
bandwidth and processing delays.

## Validation principle

A configuration should fail rather than silently approximate an unsupported or
underidentified model. New configuration fields must be represented in the
resolved configuration and run hash.

## Scheduled validator outages

Validator outages are separate from network latency/loss shocks. An outage
changes validator operational state, so the validator cannot propose, attest,
receive, process, or forward messages while offline.

```yaml
faults:
  - name: europe_crash
    action: validator_outage
    scope: region
    targets: [europe]
    start_slot: 20
    duration_slots: 8
    recovery_mode: preserve_view
    resynchronization_ms: 3000
```

Supported scopes are:

- `global`;
- `region`, using `targets`;
- `isp`, using `targets`;
- `validator_ids`, using `validator_ids`;
- `random_fraction`, using `fraction`;
- `stake_fraction`, using `stake_fraction`; and
- `highest_stake`, using `stake_fraction`.

Recovery modes are `preserve_view` and
`restart_from_finalized_checkpoint`. A positive `resynchronization_ms` places
the validator in a nonparticipating `recovering` state before it returns
online.

## Fork-analysis settings

```yaml
metrics:
  minimum_branch_support: 0.01
  orphan_settlement_slots: 2
```

A fork requires at least two incompatible heads, each with the configured
minimum exact-head stake support. Blocks outside the final stake-modal chain
are classified as orphaned only after the settlement horizon; newer blocks are
reported as unresolved.
