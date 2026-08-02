# Latency models in VALENCE v0.5

VALENCE distinguishes a latency **marginal distribution** from temporal and
spatial dependence. A marginal determines a single link-delay draw. Jitter,
Markov modulation, regional shocks, packet loss, and gossip topology determine
how those draws interact over time and across validators.

## Exact quantile-piecewise model

`quantile_piecewise` is the preferred model for controlled p99 experiments. Its
inverse CDF is piecewise linear in normal-score/log-delay space and passes
through the supplied p50, p95, and p99 anchors. `max_ms` optionally caps
extrapolation beyond p99.

This model is designed for causal isolation. It is not asserted to be a unique
physical distribution for Internet latency.

## Parametric families

- `shifted_exponential`: explicit shift and scale.
- `truncated_normal`: normal location and standard deviation, conditioned on
  nonnegative delay.
- `gamma`: explicit shape and scale, plus optional shift.
- `erlang`: integer gamma shape (`erlang_stages`) and scale.
- `lognormal`: explicit arithmetic mean/sigma or p50/p95 fitting.
- `weibull`: explicit shape/scale or p50/p95 fitting.
- `loglogistic`: explicit shape/scale or p50/p95 fitting.
- `lomax`: explicit Pareto-II shape/scale or p50/p95 fitting where feasible.
- `generalized_pareto`: shape may be negative, zero, or positive; negative
  shape gives a bounded endpoint. Explicit parameters or p50/p95 fitting are
  supported.

Two-parameter fitting matches p50 and p95. The p99 and p99.9 are then implied
by the selected family and are reported in calibration output. VALENCE never
silently treats a supplied p99 as exactly matched by a two-parameter family.

## Composition models

### Mixture

A component is selected according to normalized weights, then sampled. Mixtures
can represent fast and slow path classes, routing modes, or heterogeneous link
populations.

### Spliced body and tail

A body distribution is used through `splice_quantile`. Above the threshold,
VALENCE adds generalized-Pareto excess to the body threshold. The current
implementation requires an analytic body quantile and a generalized-Pareto
tail.

### Markov-modulated

Each directed overlay edge has a latency state. The current state's component
is sampled, then the edge transitions according to the configured matrix.
State occupancy is reported in `latency_calibration.json`.

## Calibration outputs

VALENCE reports:

- target/model descriptors;
- observed attempted-link p50, p95, p99, and p99.9;
- observed effective values after jitter and shocks;
- delivered-message p50, p95, p99, and p99.9;
- delivered-to-attempted p99 and p99.9 ratios; and
- per-region-pair targets, observed values, sample counts, and drop rates.

Earliest-arrival gossip deduplication means delivered tails may be much smaller
than attempted-link tails. Both must be reported.

## v0.6 temporal dependence and tail isolation

`markov_modulated` supports `stationary_initialization: true` and
`markov_scope: edge|global`. Stationary initialization samples the first state
from the invariant distribution of the transition matrix. Global scope uses a
shared network regime; edge scope maintains an independent process per directed
edge. Output records occupancy, transition counts, same-state transition rate,
and state run-length summaries.

The matched temporal experiment uses the same component distributions and the
same stationary weights in an i.i.d. mixture and a Markov-modulated process.
The beyond-p99 experiment uses a common quantile-piecewise body through p99 and
changes only the generalized-Pareto continuation above the 0.99 splice.
