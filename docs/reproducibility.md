# Reproducibility

## Environment

VALENCE supports Python 3.10–3.13 in continuous integration. Create a clean
environment and install editable dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,paper]"
```

## Verify the release

```bash
pytest
valence run configs/smoke.yaml --output /tmp/valence-smoke-a
valence run configs/smoke.yaml --output /tmp/valence-smoke-b
diff /tmp/valence-smoke-a/run_hash.txt /tmp/valence-smoke-b/run_hash.txt
```

## Reproduce the frozen experiments

```bash
mkdir -p results/v0.6
python scripts/run_p99_dose_sweep.py --output results/v0.6/p99-dose
python scripts/run_temporal_dependence_experiment.py --output results/v0.6/temporal
python scripts/run_beyond_p99_experiment.py --output results/v0.6/beyond-p99
python scripts/run_finality_frontier.py --output results/v0.6/finality-frontier
python scripts/build_paper_artifacts.py \
  --results-root results/v0.6 \
  --output results/paper-artifacts-v0.6
```

Compare generated aggregates and figures with
`validation/reference/v0.6/`. Small floating-point formatting differences may
occur across platforms, but paired scientific conclusions and deterministic
hashes within one supported environment should remain stable.

## Run artifacts

Every simulation directory includes the resolved configuration, metadata,
event log, calibration diagnostics, and canonical run hash. Archive these files
with any reported result.

## Statistical unit

The seed-level paired result is the experimental unit. Messages, events,
validators, attestations, and slots within one run are not treated as
independent replicates.

## Reference outputs

Reference files are committed for auditability. A pull request that changes
reference values must include:

- the reason;
- affected code and configuration;
- before/after paired results;
- updated tests; and
- a new version and changelog entry.
