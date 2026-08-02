from __future__ import annotations

import pickle
import subprocess
import sys
import tempfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from valence.config import ValenceConfig


@dataclass(frozen=True)
class SimulationTask:
    condition: str
    seed: int
    config: ValenceConfig


@dataclass(frozen=True)
class SimulationTaskResult:
    condition: str
    seed: int
    summary: dict[str, object]


def run_simulation_tasks(
    tasks: Iterable[SimulationTask],
    *,
    maximum_group_size: int = 25,
) -> list[SimulationTaskResult]:
    """Execute experimental conditions in isolated worker processes.

    Each condition receives a fresh process, preserving paired-seed execution
    while preventing allocator state from carrying between heterogeneous
    latency models. Condition workers run concurrently; each worker processes
    its seeds sequentially and streams summaries to disk.
    """
    task_list = list(tasks)
    if not task_list:
        return []
    if maximum_group_size < 1:
        raise ValueError("maximum_group_size must be positive")

    grouped: OrderedDict[str, list[SimulationTask]] = OrderedDict()
    for task in task_list:
        grouped.setdefault(task.condition, []).append(task)

    batches: list[tuple[str, list[SimulationTask]]] = []
    for condition, condition_tasks in grouped.items():
        for start in range(0, len(condition_tasks), maximum_group_size):
            batches.append((condition, condition_tasks[start : start + maximum_group_size]))

    results: list[SimulationTaskResult] = []
    with tempfile.TemporaryDirectory(prefix="valence-experiment-") as temporary:
        root = Path(temporary)
        processes: list[tuple[str, Path, subprocess.Popen[bytes]]] = []
        for batch_index, (condition, batch) in enumerate(batches):
            print(
                f"Launching VALENCE condition {condition}: {len(batch)} simulations",
                flush=True,
            )
            input_path = root / f"batch-{batch_index:04d}.pkl"
            output_path = root / f"result-{batch_index:04d}.pkl"
            with input_path.open("wb") as handle:
                pickle.dump(batch, handle, protocol=pickle.HIGHEST_PROTOCOL)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "valence.analysis.worker",
                    str(input_path),
                    str(output_path),
                ]
            )
            processes.append((condition, output_path, process))

        for condition, output_path, process in processes:
            return_code = process.wait()
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, process.args)
            with output_path.open("rb") as handle:
                while True:
                    try:
                        results.append(pickle.load(handle))
                    except EOFError:
                        break
            print(f"Completed VALENCE condition {condition}", flush=True)
    return results
