# VALENCE v0.6.3

This is the first public research-software release of VALENCE.

## Included

- deterministic discrete-event PoS simulator;
- 54 automated tests;
- regional, tail-aware, empirical, mixture, spliced, and Markov-modulated
  latency models;
- resource queues and stake-weighted consensus metrics;
- four frozen paper-strength experiment pipelines;
- reference outputs, statistical tables, and figures; and
- reproducibility, contribution, security, and citation metadata.

## Version note

The scientific simulator and frozen experiments correspond to v0.6.0.
Versions v0.6.1–v0.6.3 correct notebook display/resume behavior and prepare the
public repository; they do not change the validated simulator logic.

## Known limitations

VALENCE is Beacon-like and does not implement exact Ethereum client behavior.
Included regional profiles are synthetic unless explicitly labeled otherwise.
See README.md and VALIDATION_v0.6.md for scope and interpretation.
