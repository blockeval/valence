from __future__ import annotations

import argparse
import gc
import pickle
from pathlib import Path

from valence.analysis.execution import SimulationTask, SimulationTaskResult
from valence.simulation import ValenceSimulation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VALENCE experiment batch worker")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with args.input.open("rb") as handle:
        tasks: list[SimulationTask] = pickle.load(handle)
    with args.output.open("wb") as handle:
        for task in tasks:
            simulation = ValenceSimulation(task.config)
            result = simulation.run()
            record = SimulationTaskResult(
                condition=task.condition,
                seed=task.seed,
                summary=result.summary,
            )
            pickle.dump(record, handle, protocol=pickle.HIGHEST_PROTOCOL)
            handle.flush()
            del record, result, simulation
            gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
