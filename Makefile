.PHONY: install test smoke outage poster paper clean

install:
	python -m pip install -e ".[dev,paper]"

test:
	pytest

smoke:
	valence run configs/smoke.yaml --output results/smoke

outage:
	valence run configs/outage_demo.yaml --output results/outage-demo

poster:
	python scripts/run_poster_compliance_demo.py --output results/poster-compliance-v0.7

paper:
	python scripts/run_p99_dose_sweep.py --output results/v0.6/p99-dose
	python scripts/run_temporal_dependence_experiment.py --output results/v0.6/temporal
	python scripts/run_beyond_p99_experiment.py --output results/v0.6/beyond-p99
	python scripts/run_finality_frontier.py --output results/v0.6/finality-frontier
	python scripts/build_paper_artifacts.py --results-root results/v0.6 --output results/paper-artifacts-v0.6

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache results
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

ethereum-smoke:
	valence run configs/ethereum_minimal_smoke.yaml --output results/ethereum-minimal
	valence run configs/ethereum_mainnet_smoke.yaml --output results/ethereum-mainnet

ethereum-cross-model:
	python scripts/run_ethereum_cross_model_experiment.py --output results/ethereum-cross-model-30
