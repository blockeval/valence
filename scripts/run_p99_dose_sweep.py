#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from math import isfinite, log2
from pathlib import Path
from statistics import mean, median, stdev

from valence.analysis.statistics import (
    bootstrap_ci,
    cohen_dz,
    holm_adjust,
    linear_slope,
    paired_statistics,
    sign_flip_pvalue,
)
from valence.analysis.execution import SimulationTask, run_simulation_tasks
from valence.config import load_config


DEFAULT_SEEDS = "4,9,14,19,24,29,34,39,44,49,54,59,64,69,74,79,84,89,94,99"
CONDITIONS = (
    ("low", "configs/p99_dose_low.yaml"),
    ("moderate", "configs/p99_dose_moderate.yaml"),
    ("high", "configs/p99_dose_high.yaml"),
    ("extreme", "configs/p99_dose_extreme.yaml"),
)
PRIMARY_METRICS = (
    "mean_slot_stake_weighted_head_agreement",
    "stale_head_attestation_rate",
    "slot_divergence_rate_below_0_9",
    "maximum_finality_lag_epochs",
)
COMPARISONS = (
    ("moderate", "low", "adjacent"),
    ("high", "moderate", "adjacent"),
    ("extreme", "high", "adjacent"),
    ("high", "low", "cumulative"),
    ("extreme", "low", "cumulative"),
)

SECONDARY_METRICS = (
    "minimum_slot_stake_weighted_head_agreement",
    "mean_stake_weighted_head_agreement",
    "mean_head_agreement",
    "mean_finality_agreement",
    "finality_lag_epochs",
    "finality_delay_ever_exceeds_one_epoch",
    "p99_network_delay_ms",
    "p999_network_delay_ms",
    "simulation_end_time_ms",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the VALENCE four-level p99 dose sweep")
    parser.add_argument("--low-config", default=CONDITIONS[0][1])
    parser.add_argument("--moderate-config", default=CONDITIONS[1][1])
    parser.add_argument("--high-config", default=CONDITIONS[2][1])
    parser.add_argument("--extreme-config", default=CONDITIONS[3][1])
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--output", default="results/p99-dose-sweep-v0.6")
    parser.add_argument("--bootstrap-resamples", type=int, default=5000)
    parser.add_argument("--permutation-resamples", type=int, default=50000)
    return parser.parse_args()


def _finite(value: float) -> float | None:
    return float(value) if isfinite(float(value)) else None


def _summary(values: list[float]) -> dict[str, float | int]:
    lower, upper = bootstrap_ci(values, resamples=5000)
    return {
        "n": len(values),
        "mean": float(mean(values)),
        "median": float(median(values)),
        "sd": float(stdev(values)) if len(values) > 1 else 0.0,
        "bootstrap_ci_low": lower,
        "bootstrap_ci_high": upper,
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    config_paths = {
        "low": args.low_config,
        "moderate": args.moderate_config,
        "high": args.high_config,
        "extreme": args.extreme_config,
    }
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    if len(seeds) < 3:
        raise ValueError("At least three paired seeds are required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Seeds must be unique")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    targets: dict[str, tuple[float, float, float]] = {}

    bases = {}
    for condition in ("low", "moderate", "high", "extreme"):
        base = load_config(config_paths[condition])
        bases[condition] = base
        latency = base.network.latency
        targets[condition] = (latency.p50_ms, latency.p95_ms, latency.p99_ms)
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
        latency = bases[condition].network.latency
        attempted = summary["attempted_base_latency"]
        rows.append(
            {
                "condition": condition,
                "seed": seed,
                "target_p50_ms": latency.p50_ms,
                "target_p95_ms": latency.p95_ms,
                "target_p99_ms": latency.p99_ms,
                "observed_base_p50_ms": attempted["p50_ms"],
                "observed_base_p95_ms": attempted["p95_ms"],
                "observed_base_p99_ms": attempted["p99_ms"],
                "observed_base_p999_ms": attempted["p999_ms"],
                "p99_network_delay_ms": summary["p99_network_delay_ms"],
                "p999_network_delay_ms": summary["p999_network_delay_ms"],
                "mean_head_agreement": summary["mean_head_agreement"],
                "mean_stake_weighted_head_agreement": summary[
                    "mean_stake_weighted_head_agreement"
                ],
                "mean_slot_stake_weighted_head_agreement": summary[
                    "mean_slot_stake_weighted_head_agreement"
                ],
                "minimum_slot_stake_weighted_head_agreement": summary[
                    "minimum_slot_stake_weighted_head_agreement"
                ],
                "slot_divergence_rate_below_0_9": summary[
                    "slot_divergence_rate_below_0_9"
                ],
                "stale_head_attestation_rate": summary[
                    "stale_head_attestation_rate"
                ],
                "mean_finality_agreement": summary["mean_finality_agreement"],
                "finality_lag_epochs": summary["finality_lag_epochs"],
                "maximum_finality_lag_epochs": summary[
                    "maximum_finality_lag_epochs"
                ],
                "finality_delay_ever_exceeds_one_epoch": summary[
                    "finality_delay_ever_exceeds_one_epoch"
                ],
                "simulation_end_time_ms": summary["simulation_end_time_ms"],
            }
        )

    _write_csv(output / "per_seed.csv", rows)

    design_check = {
        "same_target_p50": len({value[0] for value in targets.values()}) == 1,
        "same_target_p95": len({value[1] for value in targets.values()}) == 1,
        "strictly_increasing_target_p99": [targets[name][2] for name in targets]
        == sorted(targets[name][2] for name in targets)
        and len({targets[name][2] for name in targets}) == 4,
        "paired_seed_count": len(seeds),
        "same_seeds_all_conditions": all(
            {int(row["seed"]) for row in rows if row["condition"] == condition}
            == set(seeds)
            for condition in targets
        ),
    }
    if not all(
        design_check[key]
        for key in (
            "same_target_p50",
            "same_target_p95",
            "strictly_increasing_target_p99",
            "same_seeds_all_conditions",
        )
    ):
        raise RuntimeError(f"p99 dose design check failed: {design_check}")

    all_metrics = PRIMARY_METRICS + SECONDARY_METRICS
    aggregate: dict[str, dict[str, dict[str, float | int]]] = {}
    for condition in targets:
        selected = [row for row in rows if row["condition"] == condition]
        aggregate[condition] = {
            metric: _summary([float(row[metric]) for row in selected])
            for metric in all_metrics
        }

    row_lookup = {
        (str(row["condition"]), int(row["seed"])): row
        for row in rows
    }
    comparison_rows: list[dict[str, object]] = []
    for comparison_index, (candidate_condition, reference_condition, comparison_type) in enumerate(COMPARISONS):
        for metric_index, metric in enumerate(PRIMARY_METRICS + SECONDARY_METRICS):
            reference = [
                float(row_lookup[(reference_condition, seed)][metric]) for seed in seeds
            ]
            candidate = [
                float(row_lookup[(candidate_condition, seed)][metric]) for seed in seeds
            ]
            statistics = paired_statistics(
                reference,
                candidate,
                bootstrap_resamples=args.bootstrap_resamples,
                permutation_resamples=args.permutation_resamples,
                seed=20260801 + 1000 * comparison_index + 100 * metric_index,
            )
            statistics["cohen_dz"] = _finite(float(statistics["cohen_dz"]))
            comparison_rows.append(
                {
                    "comparison": f"{candidate_condition}_vs_{reference_condition}",
                    "comparison_type": comparison_type,
                    "metric": metric,
                    "family": "primary" if metric in PRIMARY_METRICS else "secondary",
                    **statistics,
                }
            )

    all_primary_indices = [
        index for index, row in enumerate(comparison_rows) if row["family"] == "primary"
    ]
    all_primary_adjusted = holm_adjust(
        float(comparison_rows[index]["randomization_p"])
        for index in all_primary_indices
    )
    for index, adjusted in zip(all_primary_indices, all_primary_adjusted):
        comparison_rows[index]["holm_adjusted_p_all_primary_family"] = adjusted

    adjacent_primary_indices = [
        index
        for index, row in enumerate(comparison_rows)
        if row["family"] == "primary" and row["comparison_type"] == "adjacent"
    ]
    adjacent_adjusted = holm_adjust(
        float(comparison_rows[index]["randomization_p"])
        for index in adjacent_primary_indices
    )
    for index, adjusted in zip(adjacent_primary_indices, adjacent_adjusted):
        comparison_rows[index]["holm_adjusted_p_adjacent_primary_family"] = adjusted
    for row in comparison_rows:
        row.setdefault("holm_adjusted_p_all_primary_family", "")
        row.setdefault("holm_adjusted_p_adjacent_primary_family", "")
        row["holm_adjusted_p_primary_family"] = row[
            "holm_adjusted_p_all_primary_family"
        ]

    _write_csv(output / "paired_statistics.csv", comparison_rows)

    difference_rows: list[dict[str, object]] = []
    for candidate_condition, reference_condition, comparison_type in COMPARISONS:
        for seed in seeds:
            row: dict[str, object] = {
                "comparison": f"{candidate_condition}_vs_{reference_condition}",
                "comparison_type": comparison_type,
                "seed": seed,
            }
            for metric in all_metrics:
                row[metric] = (
                    float(row_lookup[(candidate_condition, seed)][metric])
                    - float(row_lookup[(reference_condition, seed)][metric])
                )
            difference_rows.append(row)
    _write_csv(output / "paired_differences.csv", difference_rows)

    x_values = [log2(targets[name][2]) for name in ("low", "moderate", "high", "extreme")]
    slope_rows: list[dict[str, object]] = []
    slope_statistics: list[dict[str, object]] = []
    for metric_index, metric in enumerate(PRIMARY_METRICS):
        slopes: list[float] = []
        for seed in seeds:
            y_values = [
                float(row_lookup[(condition, seed)][metric])
                for condition in ("low", "moderate", "high", "extreme")
            ]
            slope = linear_slope(x_values, y_values)
            slopes.append(slope)
            slope_rows.append({"metric": metric, "seed": seed, "slope_per_p99_doubling": slope})
        lower, upper = bootstrap_ci(
            slopes,
            resamples=args.bootstrap_resamples,
            seed=20262000 + metric_index,
        )
        slope_statistics.append(
            {
                "metric": metric,
                "pairs": len(slopes),
                "mean_slope_per_p99_doubling": mean(slopes),
                "median_slope_per_p99_doubling": median(slopes),
                "bootstrap_ci_low": lower,
                "bootstrap_ci_high": upper,
                "cohen_dz": _finite(cohen_dz(slopes)),
                "randomization_p": sign_flip_pvalue(
                    slopes,
                    resamples=args.permutation_resamples,
                    seed=20263000 + metric_index,
                ),
            }
        )
    slope_adjusted = holm_adjust(float(row["randomization_p"]) for row in slope_statistics)
    for row, adjusted in zip(slope_statistics, slope_adjusted):
        row["holm_adjusted_p_primary_family"] = adjusted
    _write_csv(output / "dose_response_slopes.csv", slope_rows)
    _write_csv(output / "dose_response_statistics.csv", slope_statistics)

    report = {
        "design_check": design_check,
        "targets": {
            condition: {
                "p50_ms": values[0],
                "p95_ms": values[1],
                "p99_ms": values[2],
            }
            for condition, values in targets.items()
        },
        "aggregate": aggregate,
        "paired_statistics": comparison_rows,
        "dose_response_statistics": slope_statistics,
    }
    (output / "analysis.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["design_check"], indent=2, sort_keys=True))
    print(f"Saved 4 conditions x {len(seeds)} paired seeds to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
