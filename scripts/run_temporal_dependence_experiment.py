#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, replace
from math import isfinite
from pathlib import Path
from statistics import mean, median, stdev

from valence.analysis.statistics import bootstrap_ci, holm_adjust, paired_statistics
from valence.analysis.execution import SimulationTask, run_simulation_tasks
from valence.config import load_config
from valence.network.distributions import stationary_distribution

DEFAULT_SEEDS = "4,9,14,19,24,29,34,39,44,49,54,59,64,69,74,79,84,89,94,99"
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
    "boundary_fraction_finality_lag_exceeds_one_epoch",
    "simulation_end_time_ms",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare marginally matched i.i.d. and Markov-modulated latency"
    )
    parser.add_argument("--iid-config", default="configs/temporal_iid_matched.yaml")
    parser.add_argument("--markov-config", default="configs/temporal_markov_matched.yaml")
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--output", default="results/temporal-dependence-v0.6")
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


def _component_signature(component: object) -> dict[str, object]:
    data = asdict(component)
    data.pop("weight", None)
    data.pop("name", None)
    return data


def main() -> int:
    args = parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    if len(seeds) < 10 or len(set(seeds)) != len(seeds):
        raise ValueError("At least 10 unique paired seeds are required")

    iid = load_config(args.iid_config)
    markov = load_config(args.markov_config)
    if iid.network.latency.distribution != "mixture":
        raise ValueError("iid config must use a mixture latency model")
    if markov.network.latency.distribution != "markov_modulated":
        raise ValueError("markov config must use markov_modulated latency")

    stationary = stationary_distribution(markov.network.latency.transition_matrix)
    iid_weights = [component.weight for component in iid.network.latency.components]
    iid_weights = [value / sum(iid_weights) for value in iid_weights]
    iid_signatures = [_component_signature(value) for value in iid.network.latency.components]
    markov_signatures = [
        _component_signature(state.component) for state in markov.network.latency.states
    ]
    design_check = {
        "paired_seed_count": len(seeds),
        "same_seeds": True,
        "same_component_count": len(iid_signatures) == len(markov_signatures),
        "same_component_distributions": iid_signatures == markov_signatures,
        "iid_weights_match_stationary_probabilities": all(
            abs(left - right) < 1e-9 for left, right in zip(iid_weights, stationary)
        ),
        "markov_stationary_initialization": markov.network.latency.stationary_initialization,
        "markov_scope": markov.network.latency.markov_scope,
    }
    if not all(
        design_check[key]
        for key in (
            "same_component_count",
            "same_component_distributions",
            "iid_weights_match_stationary_probabilities",
            "markov_stationary_initialization",
        )
    ):
        raise RuntimeError(f"Temporal-dependence design check failed: {design_check}")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    bases = {"iid": iid, "markov": markov}
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
        attempted = summary["attempted_base_latency"]
        run_summary = summary.get("latency_state_run_summary", {})
        congested_runs = run_summary.get("congested", {})
        rows.append(
            {
                "condition": condition,
                "seed": seed,
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
                "boundary_fraction_finality_lag_exceeds_one_epoch": summary[
                    "boundary_fraction_finality_lag_exceeds_one_epoch"
                ],
                "simulation_end_time_ms": summary["simulation_end_time_ms"],
                "congested_state_occupancy": summary.get(
                    "latency_state_occupancy", {}
                ).get("congested", 0.0),
                "congested_mean_run_length": congested_runs.get(
                    "mean_run_length", 0.0
                ),
                "congested_p95_run_length": congested_runs.get(
                    "p95_run_length", 0.0
                ),
                "same_state_transition_rate": summary.get(
                    "latency_state_same_transition_rate", 0.0
                ),
            }
        )
    _write_csv(output / "per_seed.csv", rows)

    lookup = {(str(row["condition"]), int(row["seed"])): row for row in rows}
    metrics = PRIMARY_METRICS + SECONDARY_METRICS
    paired_rows: list[dict[str, object]] = []
    for index, metric in enumerate(metrics):
        reference = [float(lookup[("iid", seed)][metric]) for seed in seeds]
        candidate = [float(lookup[("markov", seed)][metric]) for seed in seeds]
        stats = paired_statistics(
            reference,
            candidate,
            bootstrap_resamples=args.bootstrap_resamples,
            permutation_resamples=args.permutation_resamples,
            seed=20264000 + index * 100,
        )
        stats["cohen_dz"] = _finite(float(stats["cohen_dz"]))
        paired_rows.append(
            {
                "comparison": "markov_vs_iid",
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

    aggregate: dict[str, dict[str, dict[str, float | int]]] = {}
    aggregate_metrics = (
        "observed_p50_ms",
        "observed_p95_ms",
        "observed_p99_ms",
        "observed_p999_ms",
    ) + metrics + (
        "congested_state_occupancy",
        "congested_mean_run_length",
        "congested_p95_run_length",
        "same_state_transition_rate",
    )
    for condition in bases:
        selected = [row for row in rows if row["condition"] == condition]
        aggregate[condition] = {
            metric: _summary(
                [float(row[metric]) for row in selected],
                seed=20265000 + metric_index,
            )
            for metric_index, metric in enumerate(aggregate_metrics)
        }

    marginal_relative_differences = {}
    for quantile in ("observed_p50_ms", "observed_p95_ms", "observed_p99_ms", "observed_p999_ms"):
        iid_mean = float(aggregate["iid"][quantile]["mean"])
        markov_mean = float(aggregate["markov"][quantile]["mean"])
        marginal_relative_differences[quantile] = (
            (markov_mean - iid_mean) / iid_mean if iid_mean else 0.0
        )

    report = {
        "design_check": design_check,
        "stationary_probabilities": [float(value) for value in stationary],
        "aggregate": aggregate,
        "marginal_relative_differences": marginal_relative_differences,
        "paired_statistics": paired_rows,
    }
    (output / "analysis.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(design_check, indent=2, sort_keys=True))
    print(f"Saved 2 conditions x {len(seeds)} paired seeds to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
