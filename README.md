# VALENCE

**Validator Availability and Latency Emulator for Network Consensus Evaluation**

VALENCE is a deterministic discrete-event simulation framework for studying how
network volatility and validator resource constraints affect Proof-of-Stake
consensus. Version 0.7 includes:

- one global, deterministically ordered event queue;
- isolated random-number streams for topology, stake, duties, latency, loss,
  shocks, and gossip;
- configurable equal, explicit, and lognormal validator stake distributions;
- configurable sparse gossip overlays;
- weighted or round-robin validator placement across regions and ISPs;
- region-aware clustered overlays with configurable within-region bias and cross-region peering;
- p50/p95/p99-anchored latency sampling with p99.9 diagnostics and optional upper caps;
- external regional calibration profiles with directed or symmetric region pairs;
- empirical latency-sample profiles alongside quantile-calibrated profiles;
- target-versus-observed quantile diagnostics for every region pair;
- attempted-link versus delivered-message tail metrics for measuring gossip masking;
- fixed, lognormal, p50/p95/p99-calibrated, empirical, and regional-profile latency with autoregressive jitter;
- Bernoulli and Gilbert–Elliott packet loss;
- regional latency and loss shocks;
- explicit outbound-interface serialization queues;
- explicit inbound-interface queues;
- validator message-processing queues with fixed and size-dependent cost;
- message-size-aware block and attestation transmission;
- stage-specific queue, service, end-to-end delay, byte, and utilization metrics;
- stake-weighted proposer and committee selection;
- scheduled validator crash, recovery, and restart-from-finalized-checkpoint faults;
- global, regional, ISP, explicit-validator, random-fraction, and stake-based outage selectors;
- explicit proposal and attestation availability with assigned-duty denominators;
- stake-weighted committee participation and operational availability by validator, region, and ISP;
- explicit fork episodes, fork duration, branch width, orphaned blocks, and reorganization depth;
- elapsed checkpoint time-to-finality with right-censored checkpoint records;
- local validator views and incremental LMD-GHOST-inspired fork choice;
- simplified Casper-FFG-style checkpoint justification and finalization;
- reproducibility hashes, resolved configurations, metadata, and event logs; and
- automated deterministic, statistical, stake, finality, resource, temporal-dependence, and tail-shape tests.

The protocol is intentionally described as **Beacon-like**. It is not presented
as an exact Ethereum implementation. The resource layer is a deterministic
single-server queue model, not a packet-level TCP or operating-system model.

## Install and test

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest
```

## Run demonstrations

```bash
valence validate configs/resource_congestion.yaml
valence run configs/smoke.yaml --output results/smoke
valence run configs/finality_demo.yaml --output results/finality-demo
valence run configs/resource_baseline.yaml --output results/resource-baseline
valence run configs/resource_congestion.yaml --output results/resource-congestion
valence run configs/heavy_tail.yaml --output results/heavy-tail
valence run configs/outage_demo.yaml --output results/outage-demo
python scripts/run_poster_compliance_demo.py --output results/poster-compliance-v0.7
```

Every output directory contains:

```text
summary.json
resolved_config.json
latency_calibration.json
availability.json
forks.json
finality_timing.json
faults.json
run_metadata.json
events.jsonl
run_hash.txt
```




## Availability, outages, forks, and finality timing

VALENCE v0.7 treats validator availability as an explicit measured outcome.
Every proposal and attestation duty is recorded when assigned, including duties
that are missed because a validator is offline or recovering. Results include
count-weighted and stake-weighted availability, per-slot committee
participation, and breakdowns by validator, region, and ISP.

Scheduled outage faults can target the entire network, regions, ISPs, explicit
validator IDs, random validator fractions, or stake fractions. Validators pass
through `offline` and optional `recovering` states before returning online. A
recovery may preserve the local view or restart from the last finalized
checkpoint. See `configs/outage_demo.yaml`.

Fork analysis distinguishes incompatible stake-supported branches from ordinary
propagation lag along a single chain. The simulator reports fork episodes,
duration, width, orphaned blocks, and local and network-wide reorganization
depth. Checkpoint finality timing records elapsed time to a stake-threshold
finalization and retains unfinalized checkpoints as right-censored observations.

```bash
valence run configs/outage_demo.yaml --output results/outage-demo
```

## Paper-strength v0.6 experiments

VALENCE v0.6 adds four frozen, paired-seed experiment pipelines:

```bash
python scripts/run_p99_dose_sweep.py --output results/v0.6/p99-dose
python scripts/run_temporal_dependence_experiment.py --output results/v0.6/temporal
python scripts/run_beyond_p99_experiment.py --output results/v0.6/beyond-p99
python scripts/run_finality_frontier.py --output results/v0.6/finality-frontier
pip install -e ".[paper]"
python scripts/build_paper_artifacts.py \
  --results-root results/v0.6 \
  --output results/paper-artifacts-v0.6
```

The p99 pipeline now reports both cumulative and adjacent contrasts. The
temporal-dependence experiment compares an i.i.d. mixture with a globally
Markov-modulated process built from the same component distributions and
stationary mixture weights. The beyond-p99 experiment holds p50, p95, p99, and
the splice quantile fixed while changing only the generalized-Pareto
continuation. The finality-frontier experiment varies the duration of a
correlated 40x latency shock and records maximum lag and recovery, rather than
looking only at final state.

Long sweeps execute each condition in an isolated worker process and stream
results to disk, avoiding allocator accumulation while preserving paired seeds.

## Regional calibration and p99

A regional profile is a separate YAML artifact:

```yaml
name: synthetic_global_quantiles_v1
source: "Illustrative synthetic profile; not production measurements."
symmetric: true
pairs:
  - source_region: north_america
    target_region: europe
    p50_ms: 90
    p95_ms: 170
    p99_ms: 330
```

Reference it from a run configuration:

```yaml
network:
  latency:
    distribution: regional_profile
    profile_path: ../calibration/profiles/synthetic_global_quantiles.yaml
    p50_ms: 120       # fallback for an unspecified pair
    p95_ms: 250
    p99_ms: 500
```

VALENCE uses a piecewise quantile function in normal-score/log-latency space.
The supplied p50, p95, and p99 are independent anchors; p99 is not inferred
from p95. An optional `max_ms` bounds extrapolation beyond p99. Pair entries
may instead use `mode: empirical` and provide `samples_ms`.

`latency_calibration.json` records target and simulated p50/p95/p99 values for
each region pair. The summary also separates all attempted link samples from
message deliveries that won earliest-arrival deduplication. The
`delivered_to_attempted_p99_ratio` indicates how much overlay redundancy masks
the raw link tail.

## Regional topology

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

The regional overlay guarantees global connectivity and the configured minimum
cross-region peer count, while treating the requested degree as a minimum.
Reported topology metrics include the edge count, degree range, and fractions
of intra-region, cross-region, and same-ISP edges.

## Resource pipeline

For each relayed message, VALENCE v0.3 models:

```text
message ready to send
→ sender outbound queue
→ sender serialization
→ network transit and possible loss
→ receiver inbound queue
→ receiver ingress service
→ validator processing queue
→ validation/processing service
→ local-view update
→ forwarding
```

The YAML configuration is:

```yaml
resources:
  enabled: true
  outbound_bandwidth_mbps: 100
  inbound_bandwidth_mbps: 100
  processing_rate_mbps: 50
  processing_fixed_ms: 1
```

Set `enabled: false` for an idealized zero-resource-delay experiment. Network
latency and loss remain active when the resource layer is disabled.

The model uses one aggregate outbound interface, one aggregate inbound
interface, and one processing server per validator. Sending the same message to
multiple peers therefore consumes shared sender bandwidth rather than assuming
unlimited parallel serialization.

## Principal resource metrics

`summary.json` now reports:

- mean, p95, and maximum outbound queue delay;
- mean, p95, and maximum outbound serialization time;
- mean, p95, and maximum network delay;
- mean, p95, and maximum inbound queue and service time;
- mean, p95, and maximum processing queue and service time;
- mean, p95, and maximum end-to-end delivery delay;
- attempted, delivered, and processed bytes;
- mean and maximum outbound, inbound, and processing utilization; and
- nominal protocol duration versus the time required to drain queued work.

## Controlled congestion demonstration

`resource_baseline.yaml` and `resource_congestion.yaml` hold the topology,
message sizes, protocol timing, seed, and network latency constant. Only
bandwidth and processing capacity change. This provides a paired oracle showing
that resource constraints—not WAN latency—can create stale-head attestations,
view divergence, and a long post-protocol queue-draining tail.

## Simplified finality model

Attestations contain a source checkpoint and a target epoch checkpoint. Each
validator maintains a local set of finality votes. At an epoch boundary:

1. votes are grouped by source and target checkpoint;
2. each validator contributes stake at most once per target epoch;
3. the target is justified when supporting stake meets the configured threshold;
4. when a directly linked child checkpoint is justified, its source checkpoint
   is finalized; and
5. justified and finalized epochs never move backward.

This captures stake-threshold and message-visibility effects while remaining
small enough to audit. The implementation and paper must continue to label it a
simplified FFG-style model.

## Current limitations

- Resource capacity is homogeneous unless separate scenarios are used; explicit
  per-validator capacities are not implemented yet.
- One aggregate interface is modeled in each direction; there is no packet
  fragmentation, TCP congestion control, retransmission, or link bandwidth.
- Scheduled crash/recovery faults are implemented; stochastic churn, slashing, equivocation, and adversarial validator strategies are not yet implemented.
- Included regional profiles are synthetic demonstrations; production calibration requires measured traces with provenance.
- Region-aware topology is configurable but is not an inferred mainnet peer graph.
- Simplified checkpoint rules rather than exact Ethereum state-transition logic.
- No imported empirical latency or bandwidth traces yet.

The next major milestone is reconstructing the historical ICBC poster scenarios with the new availability, fork, outage, and time-to-finality metrics, then repeating the frozen experiments under measured latency traces with provenance.
