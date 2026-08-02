# Changelog

## 0.8.0 - 2026-08-02

### Added

- Version-pinned Ethereum consensus-specs v1.6.1 / Fulu timing and duty profiles.
- Minimal and mainnet presets, swap-or-not shuffling, committee partitioning,
  committee indices, logical effective balances, and proposer selection.
- Thirty-seed cross-model tail validation and eleven Ethereum-profile tests.

### Clarified

- The Ethereum-calibrated profile retains VALENCE's simplified fork-choice and
  finality engine and is not a full Ethereum client.

## 0.7.0

- Added explicit proposal and attestation duty assignment, completion, and offline-miss accounting.
- Added count-weighted and stake-weighted availability and per-slot committee participation.
- Added operational availability by validator, region, and ISP.
- Added scheduled validator outages with global, region, ISP, validator-ID, random-fraction, and stake-based selectors.
- Added preserve-view and restart-from-finalized-checkpoint recovery modes.
- Added explicit fork episodes, fork duration, branch width, orphan classification, and local/global reorganization depth.
- Added checkpoint time-to-finality distributions with right-censored checkpoint records.
- Added dedicated `availability.json`, `forks.json`, `finality_timing.json`, and `faults.json` artifacts.
- Added `configs/outage_demo.yaml` and an ICBC poster claim-to-implementation matrix.
- Expanded the test suite from 54 to 64 tests.

## 0.6.0

- Added adjacent p99-dose contrasts with separate Holm correction families.
- Added stationary initialization and edge/global scope for Markov-modulated latency.
- Added stationary-distribution validation, state transitions, run lengths, and mixture-component occupancy.
- Added a marginally matched i.i.d.-versus-Markov temporal-dependence experiment.
- Added a beyond-p99 experiment that fixes p50, p95, and p99 while varying the GPD continuation.
- Added maximum and boundary-level finality-lag metrics, recovery indicators, and a correlated-shock frontier.
- Added isolated condition workers for stable long sweeps.
- Added paper-ready PNG/PDF figures and a generated result summary.
- Expanded the test suite from 46 to 54 tests.

## 0.5.0

- Added literature-backed latency families, mixtures, spliced tails, and Markov-modulated models.
- Added p99.9 calibration and delivered-tail metrics.
- Added slot-level stake-weighted agreement and normalized stale-attestation/divergence outcomes.
- Added a four-level, 20-seed paired p99 dose experiment with bootstrap confidence intervals, sign-flip tests, Cohen's d_z, and Holm correction.
- Added distribution-family diagnostics and expanded the test suite from 29 to 46 tests.

## 0.4.0

- Added weighted and round-robin region/ISP placement.
- Added a region-aware clustered overlay generator with geographic and ISP bias.
- Added independent p50, p95, and p99 latency anchors with optional tail caps.
- Added external regional quantile and empirical calibration profiles.
- Added target-versus-observed calibration diagnostics by directed region pair.
- Added attempted-link and effective delivered-tail summaries, including a p99 masking ratio.
- Added p50 and p99 to every resource/network pipeline delay summary.
- Added `latency_calibration.json` and a resolved-configuration digest to run artifacts.
- Added regional, matched-p99, and sparse-tail demonstration configurations.
- Added a paired multi-seed p99 sweep script.
- Expanded the test suite from 21 to 29 tests.

## 0.3.0

- Added outbound, inbound, and processing queues.
- Added message-size-aware service times and resource utilization metrics.
- Added paired baseline/congestion demonstrations.
