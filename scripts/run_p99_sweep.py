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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a paired VALENCE p99 sweep")
    parser.add_argument("--low-config", default="configs/p99_global_low.yaml")
    parser.add_argument("--high-config", default="configs/p99_global_high.yaml")
    parser.add_argument("--seeds", default="4,9,14,19,24")
    parser.add_argument("--output", default="results/p99-sweep")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for condition, path in [("low_p99", args.low_config), ("high_p99", args.high_config)]:
        base = load_config(path)
        for seed in seeds:
            config = replace(base, simulation=replace(base.simulation, seed=seed))
            summary = ValenceSimulation(config).run().summary
            pair = summary["region_pair_latency"]["global->global"]
            rows.append(
                {
                    "condition": condition,
                    "seed": seed,
                    "target_p50_ms": pair["target"]["p50_ms"],
                    "target_p95_ms": pair["target"]["p95_ms"],
                    "target_p99_ms": pair["target"]["p99_ms"],
                    "observed_base_p50_ms": pair["observed_base"]["p50_ms"],
                    "observed_base_p95_ms": pair["observed_base"]["p95_ms"],
                    "observed_base_p99_ms": pair["observed_base"]["p99_ms"],
                    "delivered_p99_ms": summary["p99_network_delay_ms"],
                    "stale_head_attestations": summary["stale_head_attestations"],
                    "mean_head_agreement": summary["mean_head_agreement"],
                    "mean_finality_agreement": summary["mean_finality_agreement"],
                    "finality_lag_epochs": summary["finality_lag_epochs"],
                    "simulation_end_time_ms": summary["simulation_end_time_ms"],
                }
            )

    csv_path = output / "per_seed.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    aggregate: dict[str, dict[str, float]] = {}
    numeric_fields = [
        "observed_base_p50_ms",
        "observed_base_p95_ms",
        "observed_base_p99_ms",
        "delivered_p99_ms",
        "stale_head_attestations",
        "mean_head_agreement",
        "mean_finality_agreement",
        "finality_lag_epochs",
        "simulation_end_time_ms",
    ]
    for condition in ("low_p99", "high_p99"):
        selected = [row for row in rows if row["condition"] == condition]
        aggregate[condition] = {
            field: round(mean(float(row[field]) for row in selected), 12)
            for field in numeric_fields
        }
    aggregate["design_check"] = {
        "same_target_p50": rows[0]["target_p50_ms"] == rows[-1]["target_p50_ms"],
        "same_target_p95": rows[0]["target_p95_ms"] == rows[-1]["target_p95_ms"],
        "different_target_p99": rows[0]["target_p99_ms"] != rows[-1]["target_p99_ms"],
    }
    (output / "aggregate.json").write_text(
        json.dumps(aggregate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(aggregate, indent=2, sort_keys=True))
    print(f"Saved: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
