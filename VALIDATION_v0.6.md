# VALENCE v0.6 Validation Snapshot

Validation date: 2026-08-01

## Software validation

- 54 automated tests passed.
- The smoke configuration remains exactly reproducible by canonical hash.
- Long experiments isolate conditions in separate worker processes and stream summaries to disk.
- All primary experiments use predetermined paired seeds.

## 1. Four-level p99 dose response

Twenty paired seeds were run at fixed target p50 = 150 ms and p95 = 800 ms,
with target p99 in {1.5, 3, 6, 12} seconds.

| Target p99 | Stake-weighted slot agreement | Stale-attestation rate | Slots below 0.9 agreement |
|---:|---:|---:|---:|
| 1.5 s | 1.0000 | 0.0637 | 0.0000 |
| 3 s | 1.0000 | 0.1152 | 0.0000 |
| 6 s | 0.9916 | 0.1707 | 0.0290 |
| 12 s | 0.9734 | 0.2016 | 0.0887 |

Adjacent contrasts after Holm correction within the adjacent-primary family:

- Moderate versus low: stale-attestation rate +0.0516, adjusted p = 0.000240.
- High versus moderate: agreement -0.00845, stale rate +0.0555, and divergence +0.0290; all adjusted p <= 0.00171.
- Extreme versus high: agreement -0.0181 and divergence +0.0597, adjusted p = 0.00126; stale rate +0.0309, adjusted p = 0.0380.
- Maximum finality lag did not change in this p99 range.

## 2. Marginally matched temporal-dependence experiment

The i.i.d. mixture and globally Markov-modulated model use identical component
distributions and stationary weights (0.9 normal, 0.1 congested). Aggregate
marginal differences were below 1.1% at p50, p95, p99, and p99.9.

| Condition | Observed p99 | Observed p99.9 | Stale rate | Slot agreement | Slots below 0.9 |
|---|---:|---:|---:|---:|---:|
| i.i.d. mixture | 5.544 s | 11.871 s | 0.3363 | 0.9889 | 0.0383 |
| Markov-modulated | 5.600 s | 11.866 s | 0.2711 | 0.9626 | 0.1160 |

Paired Markov-minus-i.i.d. effects:

- Slot agreement -0.0263, 95% CI [-0.0340, -0.0189], d_z = -1.48, Holm p = 0.000080.
- Stale-attestation rate -0.0652, 95% CI [-0.0966, -0.0328], d_z = -0.88, Holm p = 0.00224.
- Slots below 0.9 agreement +0.0777, 95% CI [0.0543, 0.1000], d_z = 1.43, Holm p = 0.000080.
- Maximum finality lag was unchanged.

This shows that temporal clustering can increase transient divergence even when
marginal latency quantiles are nearly identical and the raw stale-vote count is lower.

## 3. Beyond-p99 tail shape

All three conditions share p50 = 150 ms, p95 = 800 ms, p99 = 8 s, and a 0.99
splice. Only the generalized-Pareto continuation changes.

| Tail | Observed p99 | Observed p99.9 | Slot agreement | Slots below 0.9 |
|---|---:|---:|---:|---:|
| Bounded GPD | 7.812 s | 9.368 s | 0.9962 | 0.0160 |
| Exponential continuation | 7.944 s | 17.243 s | 0.9907 | 0.0287 |
| Heavy GPD | 7.949 s | 25.497 s | 0.9889 | 0.0372 |

Heavy versus bounded:

- Slot agreement -0.00736, 95% CI [-0.01027, -0.00500], d_z = -1.18, Holm p = 0.000240.
- Slots below 0.9 agreement +0.0213, 95% CI [0.0128, 0.0298], d_z = 1.03, Holm p = 0.00269.
- Stale-attestation rate and maximum finality lag did not differ significantly.

Thus p50, p95, and p99 do not fully determine consensus outcomes when the
continuation above p99 differs.

## 4. Correlated-shock finality frontier

Twenty paired seeds were run with a 40x global latency shock beginning at slot 8.
Shock duration varied over {0, 4, 8, 12, 16} slots.

| Duration | Probability max lag > 1 epoch | Mean maximum lag | Recovered by end | Stale rate | Slot agreement |
|---:|---:|---:|---:|---:|---:|
| 0 slots | 0.00 | 1.00 | 1.00 | 0.0592 | 1.0000 |
| 4 slots | 0.00 | 1.00 | 1.00 | 0.1440 | 0.9655 |
| 8 slots | 1.00 | 2.04 | 0.80 | 0.2195 | 0.9095 |
| 12 slots | 1.00 | 2.15 | 0.80 | 0.2966 | 0.8522 |
| 16 slots | 1.00 | 3.00 | 0.80 | 0.3688 | 0.7982 |

The first observed, majority, and near-certain finality-delay boundary all occur
at eight slots under this specific shock magnitude and protocol configuration.
This boundary is scenario-specific and must not be generalized beyond the tested model.

## Paper-ready artifacts

`validation/reference/v0.6/paper-artifacts/` contains separate 300-dpi PNG and
PDF figures for p99 dose response, temporal dependence, beyond-p99 shape, and
the finality frontier, plus a machine-readable key-results file and Markdown summary.
