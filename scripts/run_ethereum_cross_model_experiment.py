#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from math import isfinite
from pathlib import Path
from statistics import mean, median, stdev

from valence.analysis.execution import SimulationTask, run_simulation_tasks
from valence.analysis.statistics import bootstrap_ci, holm_adjust, paired_statistics
from valence.config import load_config


DEFAULT_SEEDS = ",".join(str(4 + 5 * index) for index in range(30))
CONDITIONS = {
    "simplified_low": "configs/cross_model_simplified_low.yaml",
    "simplified_high": "configs/cross_model_simplified_high.yaml",
    "ethereum_low": "configs/cross_model_ethereum_low.yaml",
    "ethereum_high": "configs/cross_model_ethereum_high.yaml",
}
PRIMARY_METRICS = (
    "mean_slot_stake_weighted_head_agreement",
    "stale_head_attestation_rate",
    "slot_divergence_rate_below_0_9",
    "maximum_finality_lag_epochs",
)
SECONDARY_METRICS = (
    "attestation_availability",
    "stake_weighted_attestation_availability",
    "minimum_slot_stake_weighted_head_agreement",
    "mean_finality_agreement",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run paired simplified-versus-Ethereum-calibrated validation"
    )
    for condition, default in CONDITIONS.items():
        parser.add_argument(f"--{condition.replace('_', '-')}-config", default=default)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--output", default="results/ethereum-cross-model-v0.8")
    parser.add_argument("--bootstrap-resamples", type=int, default=5000)
    parser.add_argument("--permutation-resamples", type=int, default=50000)
    return parser.parse_args()


def summarize(values: list[float]) -> dict[str, float | int]:
    low, high = bootstrap_ci(values, resamples=5000)
    return {
        "n": len(values),
        "mean": float(mean(values)),
        "median": float(median(values)),
        "sd": float(stdev(values)) if len(values) > 1 else 0.0,
        "bootstrap_ci_low": low,
        "bootstrap_ci_high": high,
    }


def finite(value: float) -> float | None:
    return float(value) if isfinite(float(value)) else None


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    if len(seeds) < 3 or len(set(seeds)) != len(seeds):
        raise ValueError("At least three unique paired seeds are required")

    config_paths = {
        condition: getattr(args, f"{condition}_config")
        for condition in CONDITIONS
    }
    bases = {condition: load_config(path) for condition, path in config_paths.items()}
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    tasks = [
        SimulationTask(
            condition,
            seed,
            replace(base, simulation=replace(base.simulation, seed=seed)),
        )
        for condition, base in bases.items()
        for seed in seeds
    ]
    results = run_simulation_tasks(tasks)
    rows: list[dict[str, object]] = []
    for result in results:
        summary = result.summary
        base = bases[result.condition]
        rows.append(
            {
                "condition": result.condition,
                "model": result.condition.split("_")[0],
                "tail_level": result.condition.split("_")[1],
                "seed": result.seed,
                "target_p50_ms": base.network.latency.p50_ms,
                "target_p95_ms": base.network.latency.p95_ms,
                "target_p99_ms": base.network.latency.p99_ms,
                **{
                    metric: float(summary[metric])
                    for metric in PRIMARY_METRICS + SECONDARY_METRICS
                },
                "attestation_duties_assigned": int(summary["attestation_duties_assigned"]),
            }
        )
    rows.sort(key=lambda row: (str(row["condition"]), int(row["seed"])))
    write_csv(output / "per_seed.csv", rows)

    lookup = {(str(row["condition"]), int(row["seed"])): row for row in rows}
    metrics = PRIMARY_METRICS + SECONDARY_METRICS
    aggregate = {
        condition: {
            metric: summarize(
                [float(lookup[(condition, seed)][metric]) for seed in seeds]
            )
            for metric in metrics
        }
        for condition in CONDITIONS
    }

    comparisons: list[dict[str, object]] = []
    pairs = (
        ("simplified_high", "simplified_low", "tail_effect_simplified"),
        ("ethereum_high", "ethereum_low", "tail_effect_ethereum"),
        ("ethereum_low", "simplified_low", "model_effect_low"),
        ("ethereum_high", "simplified_high", "model_effect_high"),
    )
    for pair_index, (candidate, reference, label) in enumerate(pairs):
        for metric_index, metric in enumerate(metrics):
            reference_values = [float(lookup[(reference, seed)][metric]) for seed in seeds]
            candidate_values = [float(lookup[(candidate, seed)][metric]) for seed in seeds]
            stats = paired_statistics(
                reference_values,
                candidate_values,
                bootstrap_resamples=args.bootstrap_resamples,
                permutation_resamples=args.permutation_resamples,
                seed=20260802 + pair_index * 100 + metric_index,
            )
            stats["cohen_dz"] = finite(float(stats["cohen_dz"]))
            comparisons.append(
                {
                    "comparison": label,
                    "candidate": candidate,
                    "reference": reference,
                    "metric": metric,
                    "family": "primary" if metric in PRIMARY_METRICS else "secondary",
                    **stats,
                }
            )

    interaction_rows: list[dict[str, object]] = []
    for metric_index, metric in enumerate(metrics):
        simplified_delta = [
            float(lookup[("simplified_high", seed)][metric])
            - float(lookup[("simplified_low", seed)][metric])
            for seed in seeds
        ]
        ethereum_delta = [
            float(lookup[("ethereum_high", seed)][metric])
            - float(lookup[("ethereum_low", seed)][metric])
            for seed in seeds
        ]
        stats = paired_statistics(
            simplified_delta,
            ethereum_delta,
            bootstrap_resamples=args.bootstrap_resamples,
            permutation_resamples=args.permutation_resamples,
            seed=20261802 + metric_index,
        )
        stats["cohen_dz"] = finite(float(stats["cohen_dz"]))
        interaction_rows.append(
            {
                "comparison": "ethereum_minus_simplified_tail_effect",
                "metric": metric,
                "family": "primary" if metric in PRIMARY_METRICS else "secondary",
                **stats,
            }
        )

    primary_indices = [
        index for index, row in enumerate(comparisons) if row["family"] == "primary"
    ]
    adjusted = holm_adjust(float(comparisons[index]["randomization_p"]) for index in primary_indices)
    for index, value in zip(primary_indices, adjusted):
        comparisons[index]["holm_adjusted_p_primary_family"] = value

    interaction_primary = [
        index for index, row in enumerate(interaction_rows) if row["family"] == "primary"
    ]
    adjusted_interaction = holm_adjust(
        float(interaction_rows[index]["randomization_p"])
        for index in interaction_primary
    )
    for index, value in zip(interaction_primary, adjusted_interaction):
        interaction_rows[index]["holm_adjusted_p_primary_family"] = value

    design = {
        "paired_seed_count": len(seeds),
        "seeds": seeds,
        "same_network_targets_within_tail_level": all(
            bases[f"simplified_{level}"].network.latency
            == bases[f"ethereum_{level}"].network.latency
            for level in ("low", "high")
        ),
        "matched_slot_duration_ms": {
            condition: bases[condition].protocol.slot_duration_ms for condition in CONDITIONS
        },
        "matched_epoch_length_slots": {
            condition: bases[condition].protocol.epoch_length_slots for condition in CONDITIONS
        },
        "assigned_duties_per_run": sorted(
            {int(row["attestation_duties_assigned"]) for row in rows}
        ),
        "ethereum_profile": bases["ethereum_low"].protocol.__dict__,
    }
    if not design["same_network_targets_within_tail_level"]:
        raise RuntimeError("cross-model network targets are not matched")
    if set(design["matched_slot_duration_ms"].values()) != {6000}:
        raise RuntimeError("cross-model slot durations are not matched")
    if set(design["matched_epoch_length_slots"].values()) != {8}:
        raise RuntimeError("cross-model epoch lengths are not matched")

    write_csv(output / "paired_statistics.csv", comparisons)
    write_csv(output / "interaction_statistics.csv", interaction_rows)
    analysis = {
        "design": design,
        "aggregate": aggregate,
        "paired_statistics": comparisons,
        "interaction_statistics": interaction_rows,
    }
    (output / "analysis.json").write_text(
        json.dumps(analysis, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(analysis, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
