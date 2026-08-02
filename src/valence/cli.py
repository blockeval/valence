from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

from valence.config import load_config
from valence.simulation import ValenceSimulation


def _package_version() -> str:
    try:
        return importlib.metadata.version("valence-sim")
    except importlib.metadata.PackageNotFoundError:
        from valence import __version__

        return __version__


def run_command(config_path: str, output: str | None) -> int:
    config_file = Path(config_path)
    config = load_config(config_file)
    result = ValenceSimulation(config).run()
    text = json.dumps(result.summary, indent=2, sort_keys=True)
    print(text)
    if output:
        output_dir = Path(output)
        output_dir.mkdir(parents=True, exist_ok=True)
        run_hash = result.canonical_hash()
        (output_dir / "summary.json").write_text(text + "\n", encoding="utf-8")
        (output_dir / "events.jsonl").write_text(
            "".join(
                json.dumps(item, sort_keys=True) + "\n"
                for item in result.event_log
            ),
            encoding="utf-8",
        )
        (output_dir / "run_hash.txt").write_text(run_hash + "\n", encoding="utf-8")
        resolved_config_text = json.dumps(asdict(config), indent=2, sort_keys=True) + "\n"
        (output_dir / "resolved_config.json").write_text(
            resolved_config_text,
            encoding="utf-8",
        )
        calibration = {
            "latency_distribution": result.summary.get("latency_distribution"),
            "latency_model": result.summary.get("latency_model", {}),
            "latency_profile_name": result.summary.get("latency_profile_name"),
            "latency_profile_source": result.summary.get("latency_profile_source"),
            "latency_profile_symmetric": result.summary.get("latency_profile_symmetric"),
            "latency_profile_pair_count": result.summary.get("latency_profile_pair_count"),
            "attempted_base_latency": result.summary.get("attempted_base_latency", {}),
            "attempted_effective_latency": result.summary.get(
                "attempted_effective_latency", {}
            ),
            "latency_state_occupancy": result.summary.get(
                "latency_state_occupancy", {}
            ),
            "latency_state_transition_counts": result.summary.get(
                "latency_state_transition_counts", {}
            ),
            "latency_state_same_transition_rate": result.summary.get(
                "latency_state_same_transition_rate", 0.0
            ),
            "latency_state_run_summary": result.summary.get(
                "latency_state_run_summary", {}
            ),
            "latency_component_occupancy": result.summary.get(
                "latency_component_occupancy", {}
            ),
            "delivered_to_attempted_p99_ratio": result.summary.get(
                "delivered_to_attempted_p99_ratio"
            ),
            "delivered_to_attempted_p999_ratio": result.summary.get(
                "delivered_to_attempted_p999_ratio"
            ),
            "region_pair_latency": result.summary.get("region_pair_latency", {}),
        }
        (output_dir / "latency_calibration.json").write_text(
            json.dumps(calibration, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        for filename, key in (
            ("availability.json", "availability"),
            ("forks.json", "forks"),
            ("finality_timing.json", "finality_timing"),
            ("faults.json", "faults"),
        ):
            (output_dir / filename).write_text(
                json.dumps(result.summary.get(key, {}), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        config_bytes = config_file.read_bytes()
        metadata = {
            "valence_version": _package_version(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "config_path": str(config_file.resolve()),
            "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
            "resolved_config_sha256": hashlib.sha256(
                resolved_config_text.encode("utf-8")
            ).hexdigest(),
            "run_hash": run_hash,
            "argv": sys.argv,
        }
        (output_dir / "run_metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


def validate_command(config_path: str) -> int:
    config = load_config(config_path)
    print(json.dumps(asdict(config), indent=2, sort_keys=True))
    print("\nConfiguration is valid.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="valence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run a VALENCE simulation")
    run.add_argument("config", help="YAML configuration file")
    run.add_argument("--output", help="Directory for summary and event records")

    validate = subparsers.add_parser("validate", help="Validate and resolve a configuration")
    validate.add_argument("config", help="YAML configuration file")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run":
        return run_command(args.config, args.output)
    if args.command == "validate":
        return validate_command(args.config)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
