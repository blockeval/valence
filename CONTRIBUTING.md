# Contributing

1. Create a focused branch.
2. Add or update tests for every behavioral change.
3. Run `pytest` and the smoke reproducibility check.
4. Preserve deterministic random-stream separation.
5. Do not change an existing metric's meaning without a versioned migration.
6. Document whether a latency model uses exact quantile anchors, fitted
   parameters, or direct parameters.
7. Include resolved configurations and per-seed results for experiment changes.

Bug reports should include the configuration, seed, VALENCE version, Python
version, run hash, and the smallest reproducible output.
