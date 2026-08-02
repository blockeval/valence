# Availability and outage semantics

## Availability definitions

`proposal_availability` is completed proposal duties divided by assigned
proposal duties. `attestation_availability` is on-time attestation duties
divided by assigned attestation duties. `attestation_completion_rate` counts
late completions as completed, while the availability metric does not.

Stake-weighted availability uses the assigned validator stake as the
denominator. Operational availability is the fraction of nominal validator-time
spent outside the `offline` and `recovering` states.

## Validator states

- `online`: participates, receives, processes, and forwards;
- `degraded`: reserved for future resource-degradation policies and currently
  receives and forwards;
- `offline`: performs no protocol or network work; and
- `recovering`: performs no protocol or network work until recovery completes.

## Outage timing

Fault events scheduled at a slot boundary are inserted before the corresponding
slot-start event. An outage beginning at slot 2 therefore suppresses proposal
and committee duties assigned in slot 2.

## Overlapping outages

A validator remains offline until every active outage affecting it ends. Stale
recovery-complete events are ignored using a per-validator recovery generation.
