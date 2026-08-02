# Frozen v0.6 experiments

The public release includes four experiment families. Each uses predetermined
paired seeds and writes per-seed results before aggregate statistics.

## 1. p99 dose response

The p50 and p95 targets remain fixed while p99 takes four values. Primary
outcomes are slot-level stake-weighted agreement, stale-head attestation rate,
slot divergence below 0.9 agreement, and finality lag.

The analysis reports cumulative and adjacent contrasts, bootstrap confidence
intervals, paired sign-flip tests, Cohen's d_z, and Holm-adjusted p-values.

## 2. Temporal dependence

An i.i.d. mixture is compared with a Markov-modulated process using the same
component distributions and stationary weights. The design tests whether
marginal quantiles alone characterize consensus risk.

Markov diagnostics include occupancy, transitions, and run lengths.

## 3. Beyond-p99 continuation

The body, p50, p95, p99, and splice quantile remain fixed. Only the continuation
above p99 changes among bounded, exponential-like, and heavier generalized
Pareto tails.

The experiment tests whether matching through p99 is sufficient.

## 4. Finality frontier

A correlated global latency shock begins at a fixed slot. Its duration varies
across conditions. The analysis records:

- whether finality lag ever exceeds one epoch;
- maximum lag;
- recovery to one epoch by the end; and
- the first observed, majority, and near-certain delay boundaries.

The resulting boundary is scenario-specific and must not be generalized to all
Proof-of-Stake protocols.

## Frozen seeds

The scripts contain the predetermined seed lists. Do not alter them in a frozen
release. Exploratory runs should use separate output directories and clearly
labeled configurations.
