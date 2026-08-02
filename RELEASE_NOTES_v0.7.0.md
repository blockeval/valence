# VALENCE v0.7.0

VALENCE v0.7.0 aligns the public simulator with the capabilities described in
the ICBC VALENCE poster. The release turns availability, outages, forks,
reorganizations, orphaned blocks, and elapsed finality delay into explicit,
auditable outputs.

## Highlights

- 64 automated tests;
- assigned-duty availability denominators;
- count- and stake-weighted committee participation;
- scheduled validator crash and recovery events;
- region, ISP, validator, random-fraction, and stake-based selectors;
- preserve-view and checkpoint-restart recovery;
- explicit fork episodes and orphan classification;
- local and global reorganization depth;
- checkpoint time-to-finality with right censoring; and
- separate machine-readable availability, fork, finality, and fault artifacts.

The consensus protocol remains intentionally Beacon-like and simplified.
Safety violations, slashing, equivocation, and stochastic churn are outside the
scope of this release.
