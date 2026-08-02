#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build paper-ready VALENCE v0.6 figures")
    parser.add_argument("--results-root", default="results/v0.6")
    parser.add_argument("--output", default="results/paper-artifacts-v0.6")
    return parser.parse_args()


def _load(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _error(summary: dict) -> tuple[float, float]:
    value = float(summary["mean"])
    return value - float(summary["bootstrap_ci_low"]), float(summary["bootstrap_ci_high"]) - value


def _save_line(path: Path, x, y, yerr, xlabel: str, ylabel: str) -> None:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots()
    axis.errorbar(x, y, yerr=yerr, marker="o", capsize=4)
    axis.set_xlabel(xlabel)
    axis.set_ylabel(ylabel)
    axis.grid(True, alpha=0.25)
    figure.tight_layout()
    figure.savefig(path.with_suffix(".png"), dpi=300)
    figure.savefig(path.with_suffix(".pdf"))
    plt.close(figure)


def _save_bar(path: Path, labels, values, errors, ylabel: str) -> None:
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots()
    axis.bar(labels, values, yerr=errors, capsize=4)
    axis.set_ylabel(ylabel)
    axis.grid(True, axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(path.with_suffix(".png"), dpi=300)
    figure.savefig(path.with_suffix(".pdf"))
    plt.close(figure)


def main() -> int:
    args = parse_args()
    root = Path(args.results_root)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    p99 = _load(root / "p99-dose" / "analysis.json")
    temporal = _load(root / "temporal" / "analysis.json")
    tails = _load(root / "beyond-p99" / "analysis.json")
    frontier = _load(root / "finality-frontier" / "analysis.json")

    conditions = ["low", "moderate", "high", "extreme"]
    p99_seconds = [float(p99["targets"][name]["p99_ms"]) / 1000.0 for name in conditions]
    stale = [float(p99["aggregate"][name]["stale_head_attestation_rate"]["mean"]) for name in conditions]
    stale_err = list(zip(*[_error(p99["aggregate"][name]["stale_head_attestation_rate"]) for name in conditions]))
    agreement = [float(p99["aggregate"][name]["mean_slot_stake_weighted_head_agreement"]["mean"]) for name in conditions]
    agreement_err = list(zip(*[_error(p99["aggregate"][name]["mean_slot_stake_weighted_head_agreement"]) for name in conditions]))
    _save_line(output / "figure_p99_stale_rate", p99_seconds, stale, stale_err, "Target p99 latency (s)", "Stale-attestation rate")
    _save_line(output / "figure_p99_head_agreement", p99_seconds, agreement, agreement_err, "Target p99 latency (s)", "Stake-weighted slot head agreement")

    temporal_labels = ["i.i.d. mixture", "Markov-modulated"]
    temporal_agreement = [float(temporal["aggregate"][name]["mean_slot_stake_weighted_head_agreement"]["mean"]) for name in ("iid", "markov")]
    temporal_agreement_err = [_error(temporal["aggregate"][name]["mean_slot_stake_weighted_head_agreement"])[1] for name in ("iid", "markov")]
    temporal_divergence = [float(temporal["aggregate"][name]["slot_divergence_rate_below_0_9"]["mean"]) for name in ("iid", "markov")]
    temporal_divergence_err = [_error(temporal["aggregate"][name]["slot_divergence_rate_below_0_9"])[1] for name in ("iid", "markov")]
    _save_bar(output / "figure_temporal_head_agreement", temporal_labels, temporal_agreement, temporal_agreement_err, "Stake-weighted slot head agreement")
    _save_bar(output / "figure_temporal_divergence", temporal_labels, temporal_divergence, temporal_divergence_err, "Rate of slots below 0.9 agreement")

    tail_labels = ["Bounded", "Exponential", "Heavy GPD"]
    tail_conditions = ["bounded", "exponential", "heavy"]
    tail_p999 = [float(tails["aggregate"][name]["observed_p999_ms"]["mean"]) / 1000.0 for name in tail_conditions]
    tail_p999_err = [_error(tails["aggregate"][name]["observed_p999_ms"])[1] / 1000.0 for name in tail_conditions]
    tail_divergence = [float(tails["aggregate"][name]["slot_divergence_rate_below_0_9"]["mean"]) for name in tail_conditions]
    tail_divergence_err = [_error(tails["aggregate"][name]["slot_divergence_rate_below_0_9"])[1] for name in tail_conditions]
    _save_bar(output / "figure_beyond_p99_latency", tail_labels, tail_p999, tail_p999_err, "Observed attempted-link p99.9 (s)")
    _save_bar(output / "figure_beyond_p99_divergence", tail_labels, tail_divergence, tail_divergence_err, "Rate of slots below 0.9 agreement")

    duration_keys = sorted((int(value) for value in frontier["aggregate"]), key=int)
    delay_probability = [float(frontier["aggregate"][str(value)]["finality_delay_ever_exceeds_one_epoch"]["mean"]) for value in duration_keys]
    delay_probability_err = [_error(frontier["aggregate"][str(value)]["finality_delay_ever_exceeds_one_epoch"])[1] for value in duration_keys]
    maximum_lag = [float(frontier["aggregate"][str(value)]["maximum_finality_lag_epochs"]["mean"]) for value in duration_keys]
    maximum_lag_err = list(zip(*[_error(frontier["aggregate"][str(value)]["maximum_finality_lag_epochs"]) for value in duration_keys]))
    _save_line(output / "figure_finality_delay_probability", duration_keys, delay_probability, [delay_probability_err, delay_probability_err], "Correlated shock duration (slots)", "Probability maximum finality lag exceeds one epoch")
    _save_line(output / "figure_finality_maximum_lag", duration_keys, maximum_lag, maximum_lag_err, "Correlated shock duration (slots)", "Maximum finality lag (epochs)")

    key_results = {
        "p99_dose": {
            "stale_rate_low": stale[0],
            "stale_rate_extreme": stale[-1],
            "agreement_low": agreement[0],
            "agreement_extreme": agreement[-1],
        },
        "temporal_dependence": {
            "iid_agreement": temporal_agreement[0],
            "markov_agreement": temporal_agreement[1],
            "iid_divergence": temporal_divergence[0],
            "markov_divergence": temporal_divergence[1],
            "marginal_relative_differences": temporal["marginal_relative_differences"],
        },
        "beyond_p99": {
            "bounded_p999_seconds": tail_p999[0],
            "heavy_p999_seconds": tail_p999[-1],
            "bounded_divergence": tail_divergence[0],
            "heavy_divergence": tail_divergence[-1],
        },
        "finality_frontier": frontier["boundary_estimates"],
    }
    (output / "key_results.json").write_text(
        json.dumps(key_results, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    summary = f"""# VALENCE v0.6 paper-results summary

- Raising target p99 from 1.5 s to 12 s increased the stale-attestation rate from {stale[0]:.4f} to {stale[-1]:.4f} and reduced mean stake-weighted slot agreement from {agreement[0]:.4f} to {agreement[-1]:.4f}.
- The marginally matched Markov condition reduced mean stake-weighted slot agreement from {temporal_agreement[0]:.4f} to {temporal_agreement[1]:.4f}, while increasing the rate of slots below 0.9 agreement from {temporal_divergence[0]:.4f} to {temporal_divergence[1]:.4f}.
- Matching p50, p95, and p99 but changing the beyond-p99 tail increased attempted-link p99.9 from {tail_p999[0]:.2f} s under the bounded tail to {tail_p999[-1]:.2f} s under the heavy GPD tail; divergence rose from {tail_divergence[0]:.4f} to {tail_divergence[-1]:.4f}.
- Under the tested 40x correlated latency shock, the first observed, majority, and near-certain finality-delay boundary all occurred at {frontier['boundary_estimates']['majority_delay_duration_slots']} slots.
"""
    (output / "paper_results_summary.md").write_text(summary, encoding="utf-8")
    print(f"Paper artifacts saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
