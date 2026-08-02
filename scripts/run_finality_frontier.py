#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import replace
from pathlib import Path
from statistics import mean, median, stdev

from valence.analysis.statistics import bootstrap_ci
from valence.analysis.execution import SimulationTask, run_simulation_tasks
from valence.config import ShockConfig, load_config

DEFAULT_SEEDS = "4,9,14,19,24,29,34,39,44,49,54,59,64,69,74,79,84,89,94,99"
DEFAULT_DURATIONS = "0,4,8,12,16"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Locate the transient finality boundary under a correlated latency shock"
    )
    parser.add_argument("--config", default="configs/finality_frontier_base.yaml")
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--durations", default=DEFAULT_DURATIONS)
    parser.add_argument("--shock-start-slot", type=int, default=8)
    parser.add_argument("--latency-multiplier", type=float, default=40.0)
    parser.add_argument("--output", default="results/finality-frontier-v0.6")
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


def main() -> int:
    args = parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    durations = [int(value.strip()) for value in args.durations.split(",") if value.strip()]
    if len(seeds) < 10 or len(set(seeds)) != len(seeds):
        raise ValueError("At least 10 unique paired seeds are required")
    if durations != sorted(set(durations)) or durations[0] != 0:
        raise ValueError("durations must be unique, increasing, and begin with 0")

    base = load_config(args.config)
    slot_ms = base.protocol.slot_duration_ms
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    tasks: list[SimulationTask] = []
    for duration_slots in durations:
        shocks = ()
        if duration_slots > 0:
            shocks = (
                ShockConfig(
                    start_ms=args.shock_start_slot * slot_ms,
                    end_ms=(args.shock_start_slot + duration_slots) * slot_ms,
                    region="global",
                    latency_multiplier=args.latency_multiplier,
                ),
            )
        for seed in seeds:
            config = replace(
                base,
                simulation=replace(base.simulation, seed=seed),
                network=replace(base.network, shocks=shocks),
            )
            tasks.append(SimulationTask(str(duration_slots), seed, config))
    for result in run_simulation_tasks(tasks):
        duration_slots = int(result.condition)
        seed, summary = result.seed, result.summary
        rows.append(
            {
                "duration_slots": duration_slots,
                "duration_epochs": duration_slots / base.protocol.epoch_length_slots,
                "seed": seed,
                "maximum_finality_lag_epochs": summary[
                    "maximum_finality_lag_epochs"
                ],
                "finality_delay_ever_exceeds_one_epoch": summary[
                    "finality_delay_ever_exceeds_one_epoch"
                ],
                "boundary_fraction_finality_lag_exceeds_one_epoch": summary[
                    "boundary_fraction_finality_lag_exceeds_one_epoch"
                ],
                "recovered_to_one_epoch_by_end": summary[
                    "recovered_to_one_epoch_by_end"
                ],
                "finality_lag_epochs_at_end": summary["finality_lag_epochs"],
                "stale_head_attestation_rate": summary[
                    "stale_head_attestation_rate"
                ],
                "mean_slot_stake_weighted_head_agreement": summary[
                    "mean_slot_stake_weighted_head_agreement"
                ],
                "slot_divergence_rate_below_0_9": summary[
                    "slot_divergence_rate_below_0_9"
                ],
            }
        )
    _write_csv(output / "per_seed.csv", rows)

    metrics = (
        "maximum_finality_lag_epochs",
        "finality_delay_ever_exceeds_one_epoch",
        "boundary_fraction_finality_lag_exceeds_one_epoch",
        "recovered_to_one_epoch_by_end",
        "finality_lag_epochs_at_end",
        "stale_head_attestation_rate",
        "mean_slot_stake_weighted_head_agreement",
        "slot_divergence_rate_below_0_9",
    )
    aggregate = {}
    aggregate_rows: list[dict[str, object]] = []
    for duration_index, duration_slots in enumerate(durations):
        selected = [row for row in rows if row["duration_slots"] == duration_slots]
        aggregate[str(duration_slots)] = {
            metric: _summary(
                [float(row[metric]) for row in selected],
                seed=20268000 + duration_index * 100 + metric_index,
            )
            for metric_index, metric in enumerate(metrics)
        }
        aggregate_rows.append(
            {
                "duration_slots": duration_slots,
                "duration_epochs": duration_slots / base.protocol.epoch_length_slots,
                **{
                    f"mean_{metric}": aggregate[str(duration_slots)][metric]["mean"]
                    for metric in metrics
                },
            }
        )
    _write_csv(output / "aggregate.csv", aggregate_rows)

    probabilities = {
        duration: float(
            aggregate[str(duration)]["finality_delay_ever_exceeds_one_epoch"]["mean"]
        )
        for duration in durations
    }
    first_observed = next((duration for duration in durations if probabilities[duration] > 0), None)
    majority_boundary = next(
        (duration for duration in durations if probabilities[duration] >= 0.5), None
    )
    near_certain_boundary = next(
        (duration for duration in durations if probabilities[duration] >= 0.9), None
    )
    report = {
        "design": {
            "paired_seed_count": len(seeds),
            "shock_start_slot": args.shock_start_slot,
            "latency_multiplier": args.latency_multiplier,
            "durations_slots": durations,
            "epoch_length_slots": base.protocol.epoch_length_slots,
        },
        "aggregate": aggregate,
        "boundary_estimates": {
            "first_observed_delay_duration_slots": first_observed,
            "majority_delay_duration_slots": majority_boundary,
            "near_certain_delay_duration_slots": near_certain_boundary,
        },
    }
    (output / "analysis.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["boundary_estimates"], indent=2, sort_keys=True))
    print(f"Saved {len(durations)} durations x {len(seeds)} paired seeds to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
