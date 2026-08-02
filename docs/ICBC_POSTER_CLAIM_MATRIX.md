# ICBC poster claim matrix

This matrix links the capabilities described in the ICBC VALENCE poster to
public VALENCE v0.7 implementation points, outputs, examples, and tests.

| Poster claim | v0.7 implementation | Output | Demonstration/test |
|---|---|---|---|
| Tracks validator availability | Every proposal and attestation duty is recorded when assigned; offline and recovering validators create explicit missed-duty outcomes | `availability.json`; `proposal_availability`; `attestation_availability`; stake-weighted variants | `configs/outage_demo.yaml`; `test_healthy_run_reports_full_explicit_availability`; `test_regional_outage_counts_missed_duties_and_recovers` |
| Tracks committee participation | Per-slot count and stake participation, plus threshold crossings | `availability.committee_participation_by_slot`; `fraction_slots_below_participation_threshold` | regional-outage tests |
| Models outages | Scheduled `FAULT_START`, `FAULT_END`, and recovery-complete events change validator state | `faults.json`; `validator_status`; operational availability | `configs/outage_demo.yaml`; region/ISP/highest-stake selector tests |
| Models recovery | Preserve-view or restart-from-finalized-checkpoint recovery, with optional resynchronization delay | fault records and validator recovery counters | `test_restart_recovery_prunes_unfinalized_branch` |
| Tracks forks | Detects incompatible stake-supported heads and records event-time fork episodes | `forks.json`; `fork_episode_count`; duration and width | `test_supported_fork_requires_incompatible_stake_supported_heads` |
| Tracks orphaned blocks | End-of-run canonical-chain classification with a configurable settlement horizon | `orphaned_blocks`; `orphaned_block_rate`; `orphaned_blocks_per_1000_slots` | outage demo and orphan-classification test |
| Tracks reorganizations | Detects non-descendant local and stake-modal head changes and computes rollback depth | local/global reorganization counts and depths | reorganization-depth and outage tests |
| Tracks time to finality | Records stake-threshold checkpoint finalization timestamps and preserves unfinalized checkpoints as right-censored | `finality_timing.json`; p50/p95/p99 checkpoint time-to-finality | `configs/finality_demo.yaml`; finality timing test |
| Finality delays grow under sustained correlated shocks | Frozen v0.6 finality-frontier experiment records maximum lag and recovery | v0.6 frontier analysis and figures | `scripts/run_finality_frontier.py` |

## Scope boundaries

VALENCE v0.7 does not claim exact Ethereum compatibility. It does not yet model
validator equivocation, slashing, conflicting finalized checkpoints,
stochastic churn, TCP retransmission, or adversarial economic strategy. A
temporary fork or delayed finality is not labeled a safety violation.
