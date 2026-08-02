#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from pathlib import Path
from statistics import mean

from valence.config import load_config
from valence.simulation import ValenceSimulation


DEFAULT_MODELS = (
    ("quantile_piecewise", "configs/distribution_quantile.yaml"),
    ("lognormal", "configs/distribution_lognormal.yaml"),
    ("weibull", "configs/distribution_weibull.yaml"),
    ("loglogistic", "configs/distribution_loglogistic.yaml"),
    ("spliced_gpd", "configs/distribution_spliced_gpd.yaml"),
    ("markov_modulated", "configs/distribution_markov.yaml"),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a diagnostic VALENCE distribution sweep")
    parser.add_argument("--seeds", default="4,9,14,19,24")
    parser.add_argument("--output", default="results/distribution-sweep-v0.5")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for model_name, path in DEFAULT_MODELS:
        base = load_config(path)
        for seed in seeds:
            config = replace(base, simulation=replace(base.simulation, seed=seed))
            summary = ValenceSimulation(config).run().summary
            attempted = summary["attempted_base_latency"]
            rows.append(
                {
                    "model": model_name,
                    "seed": seed,
                    "observed_p50_ms": attempted["p50_ms"],
                    "observed_p95_ms": attempted["p95_ms"],
                    "observed_p99_ms": attempted["p99_ms"],
                    "observed_p999_ms": attempted["p999_ms"],
                    "delivered_p99_ms": summary["p99_network_delay_ms"],
                    "delivered_p999_ms": summary["p999_network_delay_ms"],
                    "mean_stake_weighted_head_agreement": summary[
                        "mean_stake_weighted_head_agreement"
                    ],
                    "stale_head_attestation_rate": summary[
                        "stale_head_attestation_rate"
                    ],
                    "finality_lag_epochs": summary["finality_lag_epochs"],
                }
            )

    with (output / "per_seed.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    numeric = [key for key in rows[0] if key not in {"model", "seed"}]
    aggregate = {
        model: {
            key: mean(float(row[key]) for row in rows if row["model"] == model)
            for key in numeric
        }
        for model, _ in DEFAULT_MODELS
    }
    (output / "aggregate.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(aggregate, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
