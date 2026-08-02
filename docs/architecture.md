# Architecture

## Event engine

VALENCE uses one deterministic priority queue. Every event is ordered by
simulation time and a monotonically increasing sequence number. This guarantees
a stable order when two events have identical timestamps.

Major event categories include:

- slot and epoch boundaries;
- block and attestation creation;
- outbound serialization;
- network arrival or loss;
- inbound service;
- validator processing;
- local-view and fork-choice updates;
- checkpoint justification and finalization; and
- shock start and end events.

## Randomness

A master seed is expanded into isolated streams for:

- topology;
- validator placement and stake;
- proposer and committee duties;
- latency;
- packet loss;
- shocks; and
- gossip.

This separation allows one subsystem to change without silently changing every
other stochastic realization.

## Validator state

Each validator maintains a local view of known blocks, attestations, head,
justified checkpoint, and finalized checkpoint. Consensus disagreement emerges
from delayed or missing information rather than from an imposed fork
probability.

## Message pipeline

```text
message ready
→ outbound queue
→ serialization
→ network transit or loss
→ inbound queue
→ ingress service
→ processing queue
→ validation/processing
→ local-view update
→ forwarding
```

The resource model uses one aggregate outbound interface, one aggregate inbound
interface, and one processing server per validator.

## Network model

The overlay determines who communicates with whom. Latency and failure models
then determine how each communication behaves.

Supported structures include sparse random and regional-clustered overlays.
Regional topology can bias peer selection toward the same region or ISP while
requiring cross-region connections and global connectivity.

## Consensus model

The protocol is Beacon-like:

- one proposer per slot;
- configurable stake-weighted committees;
- local attestation timing;
- incremental LMD-GHOST-inspired fork choice; and
- simplified FFG-style checkpoint justification and finalization.

The implementation is intentionally auditable and suitable for controlled
experiments. It must not be described as exact Ethereum client behavior.

## Metrics

VALENCE reports:

- count- and stake-weighted head agreement;
- slot-level divergence;
- current- versus stale-head attestations;
- fork and convergence diagnostics;
- justification and finality lag;
- maximum lag and end-of-run recovery;
- attempted and delivered p50, p95, p99, and p99.9 delay;
- queue, service, and end-to-end timing; and
- byte volume and utilization.
