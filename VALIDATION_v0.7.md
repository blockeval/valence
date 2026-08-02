# VALENCE v0.7 validation report

## Release audit

- Package version: `0.7.0`
- Automated tests: **64 passed**
- Configuration files validated: all public YAML scenarios
- Clean editable installation: passed
- Deterministic smoke hash: `bb2f4f25455ad81f92fb06b39b7784a2bc696f62d8045cbce688c5cc5cda7e44`

## Healthy availability oracle

| Metric | Result |
|---|---:|
| Proposal availability | 1.0000 |
| Attestation availability | 1.0000 |
| Stake-weighted attestation availability | 1.0000 |
| Operational availability | 1.0000 |
| Fork episodes | 0 |
| Orphaned blocks | 0 |
| Maximum reorganization depth | 0 |

## Regional outage oracle

The deterministic demonstration takes the four Europe validators (50% of
validator count and stake) offline for slots 2 and 3, followed by a 2-second
recovery period.

| Metric | Result |
|---|---:|
| Affected validators | 4 |
| Affected stake | 0.5000 |
| Proposal availability | 0.7500 |
| Attestation availability | 0.8750 |
| Missed proposal duties | 2 |
| Missed attestation duties | 8 |
| Slot-2 stake participation | 0.5000 |
| Slot-3 stake participation | 0.5000 |
| Validators recovered | 4 |
| Fork episodes | 1 |
| Maximum fork width | 2 |
| Orphaned blocks | 1 |
| Local reorganizations | 1 |
| Maximum reorganization depth | 1 |

All validators were online at simulation completion.

## Checkpoint time-to-finality oracle

| Metric | Result |
|---|---:|
| Finalized checkpoints | 2 |
| Right-censored checkpoints | 1 |
| p50 checkpoint TTF | 83999 ms |
| p95 checkpoint TTF | 83999 ms |
| Maximum checkpoint TTF | 83999 ms |

The final checkpoint is retained as right-censored rather than being silently
excluded because the simulation ends before it reaches the stake-threshold
finalization event.

## Poster-capability assessment

VALENCE v0.7 now directly implements and reports validator availability,
committee participation, scheduled outages and recovery, fork episodes,
orphaned blocks, reorganization depth, and elapsed checkpoint time-to-finality.
The release does not claim exact reproduction of the historical poster numbers;
that requires reconstruction of the original scenario grids, seeds, and model
parameters.
