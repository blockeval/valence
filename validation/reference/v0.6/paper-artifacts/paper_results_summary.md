# VALENCE v0.6 paper-results summary

- Raising target p99 from 1.5 s to 12 s increased the stale-attestation rate from 0.0637 to 0.2016 and reduced mean stake-weighted slot agreement from 1.0000 to 0.9734.
- The marginally matched Markov condition reduced mean stake-weighted slot agreement from 0.9889 to 0.9626, while increasing the rate of slots below 0.9 agreement from 0.0383 to 0.1160.
- Matching p50, p95, and p99 but changing the beyond-p99 tail increased attempted-link p99.9 from 9.37 s under the bounded tail to 25.50 s under the heavy GPD tail; divergence rose from 0.0160 to 0.0372.
- Under the tested 40x correlated latency shock, the first observed, majority, and near-certain finality-delay boundary all occurred at 8 slots.
