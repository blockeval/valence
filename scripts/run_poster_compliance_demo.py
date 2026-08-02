#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from valence import ValenceSimulation, load_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic VALENCE poster-capability demonstrations."
    )
    parser.add_argument("--output", default="results/poster-compliance-v0.7")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    scenarios = {
        "healthy": root / "configs" / "smoke.yaml",
        "regional_outage": root / "configs" / "outage_demo.yaml",
        "finality": root / "configs" / "finality_demo.yaml",
    }
    summaries: dict[str, dict[str, object]] = {}
    for name, config_path in scenarios.items():
        result = ValenceSimulation(load_config(config_path)).run()
        summaries[name] = result.summary
        scenario_dir = output / name
        scenario_dir.mkdir(parents=True, exist_ok=True)
        (scenario_dir / "summary.json").write_text(
            json.dumps(result.summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (scenario_dir / "run_hash.txt").write_text(
            result.canonical_hash() + "\n", encoding="utf-8"
        )

    healthy = summaries["healthy"]
    outage = summaries["regional_outage"]
    finality = summaries["finality"]
    poster = {
        "healthy_availability": {
            "proposal_availability": healthy["proposal_availability"],
            "attestation_availability": healthy["attestation_availability"],
            "operational_availability": healthy["availability"]["operational_availability"],
        },
        "outage_effects": {
            "attestation_availability": outage["attestation_availability"],
            "missed_attestation_duties": outage["attestation_duties_missed_offline"],
            "fork_episodes": outage["forks"]["fork_episode_count"],
            "orphaned_blocks": outage["forks"]["orphaned_blocks"],
            "maximum_reorganization_depth": outage["maximum_reorganization_depth"],
        },
        "finality_timing": {
            "p95_checkpoint_time_to_finality_ms": finality[
                "p95_checkpoint_time_to_finality_ms"
            ],
            "finalized_checkpoints": finality["finality_timing"]["finalized_checkpoints"],
            "right_censored_checkpoints": finality["finality_timing"]["censored_checkpoints"],
        },
    }
    (output / "poster_capability_summary.json").write_text(
        json.dumps(poster, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(poster, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
