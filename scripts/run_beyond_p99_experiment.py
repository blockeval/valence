#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from math import isfinite
from pathlib import Path
from statistics import mean, median, stdev

from valence.analysis.statistics import bootstrap_ci, holm_adjust, paired_statistics
from valence.analysis.execution import SimulationTask, run_simulation_tasks
from valence.config import load_config

DEFAULT_SEEDS = "4,9,14,19,24,29,34,39,44,49,54,59,64,69,74,79,84,89,94,99"
CONDITIONS = (
    ("bounded", "configs/tail_bounded.yaml"),
    ("exponential", "configs/tail_exponential.yaml"),
    ("heavy", "configs/tail_heavy.yaml"),
)
COMPARISONS = (
    ("exponential", "bounded"),
    ("heavy", "bounded"),
    ("heavy", "exponential"),
)
PRIMARY_METRICS = (
    "mean_slot_stake_weighted_head_agreement",
    "stale_head_attestation_rate",
    "slot_divergence_rate_below_0_9",
    "maximum_finality_lag_epochs",
)
SECONDARY_METRICS = (
    "minimum_slot_stake_weighted_head_agreement",
    "p99_network_delay_ms",
    "p999_network_delay_ms",
    "simulation_end_time_ms",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare beyond-p99 tail shapes with matched p50/p95/p99"
    )
    parser.add_argument("--bounded-config", default=CONDITIONS[0][1])
    parser.add_argument("--exponential-config", default=CONDITIONS[1][1])
    parser.add_argument("--heavy-config", default=CONDITIONS[2][1])
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--output", default="results/beyond-p99-v0.6")
    parser.add_argument("--bootstrap-resamples", type=int, default=5000)
    parser.add_argument("--permutation-resamples", type=int, default=50000)
    return parser.parse_args()


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _summary(values: list[float], seed: int) -> dict[str, float | int]:
    lower, upper = bootstrap_ci(values, resamples=5000, seed=seed)
    return {
        "n": len(values),
        "mean": float(mean(values)),
        "median": float(median(values)),
        "sd": float(stdev(values)) if len(values) > 1 else 0.0,
        "bootstrap_ci_low": lower,
        "bootstrap_ci_high": upper,
    }


def _finite(value: float) -> float | None:
    return float(value) if isfinite(float(value)) else None


def main() -> int:
    args = parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    if len(seeds) < 10 or len(set(seeds)) != len(seeds):
        raise ValueError("At least 10 unique paired seeds are required")
    paths = {
        "bounded": args.bounded_config,
        "exponential": args.exponential_config,
        "heavy": args.heavy_config,
    }
    bases = {name: load_config(path) for name, path in paths.items()}
    anchors = {
        name: (
            base.network.latency.splice_quantile,
            base.network.latency.body.p50_ms if base.network.latency.body else None,
            base.network.latency.body.p95_ms if base.network.latency.body else None,
            base.network.latency.body.p99_ms if base.network.latency.body else None,
        )
        for name, base in bases.items()
    }
    design_check = {
        "paired_seed_count": len(seeds),
        "same_splice_quantile": len({value[0] for value in anchors.values()}) == 1,
        "same_target_p50": len({value[1] for value in anchors.values()}) == 1,
        "same_target_p95": len({value[2] for value in anchors.values()}) == 1,
        "same_target_p99": len({value[3] for value in anchors.values()}) == 1,
        "tail_families_are_gpd": all(
            base.network.latency.tail is not None
            and base.network.latency.tail.family == "generalized_pareto"
            for base in bases.values()
        ),
    }
    if not all(design_check.values()):
        raise RuntimeError(f"Beyond-p99 design check failed: {design_check}")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    tasks = [
        SimulationTask(
            condition,
            seed,
            replace(base, simulation=replace(base.simulation, seed=seed)),
        )
        for condition, base in bases.items()
        for seed in seeds
    ]
    for result in run_simulation_tasks(tasks):
        condition, seed, summary = result.condition, result.seed, result.summary
        tail = bases[condition].network.latency.tail
        assert tail is not None
        attempted = summary["attempted_base_latency"]
        rows.append(
            {
                "condition": condition,
                "seed": seed,
                "tail_shape": tail.shape,
                "tail_scale_ms": tail.scale_ms,
                "observed_p50_ms": attempted["p50_ms"],
                "observed_p95_ms": attempted["p95_ms"],
                "observed_p99_ms": attempted["p99_ms"],
                "observed_p999_ms": attempted["p999_ms"],
                "p99_network_delay_ms": summary["p99_network_delay_ms"],
                "p999_network_delay_ms": summary["p999_network_delay_ms"],
                "mean_slot_stake_weighted_head_agreement": summary[
                    "mean_slot_stake_weighted_head_agreement"
                ],
                "minimum_slot_stake_weighted_head_agreement": summary[
                    "minimum_slot_stake_weighted_head_agreement"
                ],
                "stale_head_attestation_rate": summary[
                    "stale_head_attestation_rate"
                ],
                "slot_divergence_rate_below_0_9": summary[
                    "slot_divergence_rate_below_0_9"
                ],
                "maximum_finality_lag_epochs": summary[
                    "maximum_finality_lag_epochs"
                ],
                "simulation_end_time_ms": summary["simulation_end_time_ms"],
            }
        )
    _write_csv(output / "per_seed.csv", rows)

    lookup = {(str(row["condition"]), int(row["seed"])): row for row in rows}
    paired_rows: list[dict[str, object]] = []
    all_metrics = PRIMARY_METRICS + SECONDARY_METRICS
    for comparison_index, (candidate_condition, reference_condition) in enumerate(COMPARISONS):
        for metric_index, metric in enumerate(all_metrics):
            reference = [float(lookup[(reference_condition, seed)][metric]) for seed in seeds]
            candidate = [float(lookup[(candidate_condition, seed)][metric]) for seed in seeds]
            stats = paired_statistics(
                reference,
                candidate,
                bootstrap_resamples=args.bootstrap_resamples,
                permutation_resamples=args.permutation_resamples,
                seed=20266000 + comparison_index * 1000 + metric_index * 100,
            )
            stats["cohen_dz"] = _finite(float(stats["cohen_dz"]))
            paired_rows.append(
                {
                    "comparison": f"{candidate_condition}_vs_{reference_condition}",
                    "metric": metric,
                    "family": "primary" if metric in PRIMARY_METRICS else "secondary",
                    **stats,
                }
            )
    primary_indices = [
        index for index, row in enumerate(paired_rows) if row["family"] == "primary"
    ]
    adjusted = holm_adjust(
        float(paired_rows[index]["randomization_p"]) for index in primary_indices
    )
    for index, value in zip(primary_indices, adjusted):
        paired_rows[index]["holm_adjusted_p_primary_family"] = value
    for row in paired_rows:
        row.setdefault("holm_adjusted_p_primary_family", "")
    _write_csv(output / "paired_statistics.csv", paired_rows)

    aggregate_metrics = (
        "observed_p50_ms",
        "observed_p95_ms",
        "observed_p99_ms",
        "observed_p999_ms",
    ) + all_metrics
    aggregate = {
        condition: {
            metric: _summary(
                [float(row[metric]) for row in rows if row["condition"] == condition],
                seed=20267000 + metric_index,
            )
            for metric_index, metric in enumerate(aggregate_metrics)
        }
        for condition in bases
    }
    report = {
        "design_check": design_check,
        "anchors": {
            name: {
                "splice_quantile": values[0],
                "p50_ms": values[1],
                "p95_ms": values[2],
                "p99_ms": values[3],
            }
            for name, values in anchors.items()
        },
        "aggregate": aggregate,
        "paired_statistics": paired_rows,
    }
    (output / "analysis.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(design_check, indent=2, sort_keys=True))
    print(f"Saved 3 conditions x {len(seeds)} paired seeds to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
