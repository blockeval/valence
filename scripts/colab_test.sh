#!/usr/bin/env bash
set -euo pipefail
python -m pip install -q -e ".[dev]"
pytest
valence run configs/smoke.yaml --output results/smoke
