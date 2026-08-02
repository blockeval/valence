from __future__ import annotations

from math import sqrt
from statistics import mean, median, stdev
from typing import Iterable

import numpy as np


def _as_array(values: Iterable[float]) -> np.ndarray:
    array = np.asarray(list(values), dtype=float)
    if array.ndim != 1:
        raise ValueError("values must be one-dimensional")
    if array.size == 0:
        raise ValueError("values cannot be empty")
    if not np.all(np.isfinite(array)):
        raise ValueError("values must all be finite")
    return array


def _percentile(values: np.ndarray, probability: float) -> float:
    return float(np.quantile(values, probability, method="linear"))


def bootstrap_ci(
    values: Iterable[float],
    *,
    confidence: float = 0.95,
    resamples: int = 5_000,
    seed: int = 20260801,
) -> tuple[float, float]:
    """Percentile bootstrap interval for the sample mean."""
    array = _as_array(values)
    if not 0 < confidence < 1:
        raise ValueError("confidence must be in (0, 1)")
    if resamples < 100:
        raise ValueError("resamples must be at least 100")
    if array.size == 1:
        value = float(array[0])
        return value, value
    rng = np.random.default_rng(seed)
    samples = rng.choice(array, size=(resamples, array.size), replace=True)
    means = samples.mean(axis=1)
    alpha = 1.0 - confidence
    return (
        _percentile(means, alpha / 2.0),
        _percentile(means, 1.0 - alpha / 2.0),
    )


def sign_flip_pvalue(
    differences: Iterable[float],
    *,
    resamples: int = 50_000,
    seed: int = 20260801,
) -> float:
    """Two-sided paired randomization test based on sign flips.

    The exact test is used for at most 16 nonzero pairs. Larger samples use a
    deterministic Monte Carlo approximation with the add-one correction.
    """
    array = _as_array(differences)
    array = array[array != 0.0]
    if array.size == 0:
        return 1.0
    observed = abs(float(array.mean()))
    tolerance = 1e-15
    if array.size <= 16:
        count = 0
        extreme = 0
        for mask in range(1 << array.size):
            signs = np.fromiter(
                (1.0 if mask & (1 << index) else -1.0 for index in range(array.size)),
                dtype=float,
                count=array.size,
            )
            statistic = abs(float(np.mean(array * signs)))
            count += 1
            extreme += int(statistic + tolerance >= observed)
        return float(extreme / count)
    if resamples < 1_000:
        raise ValueError("resamples must be at least 1,000")
    rng = np.random.default_rng(seed)
    signs = rng.choice(np.asarray([-1.0, 1.0]), size=(resamples, array.size))
    statistics = np.abs((signs * array).mean(axis=1))
    extreme = int(np.count_nonzero(statistics + tolerance >= observed))
    return float((extreme + 1) / (resamples + 1))


def cohen_dz(differences: Iterable[float]) -> float:
    array = _as_array(differences)
    if array.size < 2:
        return 0.0
    standard_deviation = float(array.std(ddof=1))
    if standard_deviation == 0.0:
        sample_mean = float(array.mean())
        if sample_mean == 0.0:
            return 0.0
        return float("inf") if sample_mean > 0 else float("-inf")
    return float(array.mean() / standard_deviation)


def holm_adjust(p_values: Iterable[float]) -> list[float]:
    values = [float(value) for value in p_values]
    if any(value < 0 or value > 1 for value in values):
        raise ValueError("p-values must be in [0, 1]")
    count = len(values)
    if count == 0:
        return []
    order = sorted(range(count), key=lambda index: values[index])
    adjusted_sorted: list[float] = []
    running = 0.0
    for rank, index in enumerate(order):
        adjusted = min(1.0, (count - rank) * values[index])
        running = max(running, adjusted)
        adjusted_sorted.append(running)
    adjusted = [0.0] * count
    for index, value in zip(order, adjusted_sorted):
        adjusted[index] = value
    return adjusted


def paired_statistics(
    reference: Iterable[float],
    candidate: Iterable[float],
    *,
    bootstrap_resamples: int = 5_000,
    permutation_resamples: int = 50_000,
    seed: int = 20260801,
) -> dict[str, float | int]:
    reference_array = _as_array(reference)
    candidate_array = _as_array(candidate)
    if reference_array.size != candidate_array.size:
        raise ValueError("paired samples must have the same size")
    differences = candidate_array - reference_array
    lower, upper = bootstrap_ci(
        differences,
        resamples=bootstrap_resamples,
        seed=seed,
    )
    effect = cohen_dz(differences)
    return {
        "pairs": int(differences.size),
        "reference_mean": float(reference_array.mean()),
        "candidate_mean": float(candidate_array.mean()),
        "mean_difference": float(differences.mean()),
        "median_difference": float(np.median(differences)),
        "difference_sd": (
            float(differences.std(ddof=1)) if differences.size > 1 else 0.0
        ),
        "bootstrap_ci_low": lower,
        "bootstrap_ci_high": upper,
        "cohen_dz": effect,
        "randomization_p": sign_flip_pvalue(
            differences,
            resamples=permutation_resamples,
            seed=seed + 1,
        ),
        "positive_differences": int(np.count_nonzero(differences > 0)),
        "negative_differences": int(np.count_nonzero(differences < 0)),
        "zero_differences": int(np.count_nonzero(differences == 0)),
    }


def linear_slope(x_values: Iterable[float], y_values: Iterable[float]) -> float:
    x = _as_array(x_values)
    y = _as_array(y_values)
    if x.size != y.size:
        raise ValueError("x and y must have the same size")
    centered = x - x.mean()
    denominator = float(np.dot(centered, centered))
    if denominator == 0.0:
        raise ValueError("x values must not all be equal")
    return float(np.dot(centered, y - y.mean()) / denominator)
