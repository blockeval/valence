from __future__ import annotations

from math import exp, isfinite, log, sqrt
from statistics import NormalDist

import numpy as np

from valence.config import LatencyComponentConfig, LatencyConfig

_NORMAL = NormalDist()
_Z50 = _NORMAL.inv_cdf(0.50)
_Z95 = _NORMAL.inv_cdf(0.95)
_Z99 = _NORMAL.inv_cdf(0.99)
_EPSILON = 1e-12




def stationary_distribution(
    transition_matrix: tuple[tuple[float, ...], ...] | list[list[float]],
) -> np.ndarray:
    """Return the stationary distribution of an ergodic transition matrix.

    The least-squares formulation is numerically stable for the small state
    spaces used by VALENCE and also provides a clear failure mode for invalid
    or non-identifiable matrices.
    """
    matrix = np.asarray(transition_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] < 2:
        raise ValueError("transition_matrix must be square with at least two states")
    if np.any(matrix < 0) or not np.allclose(matrix.sum(axis=1), 1.0, atol=1e-9):
        raise ValueError("transition_matrix rows must be nonnegative and sum to 1")
    size = matrix.shape[0]
    system = np.vstack((matrix.T - np.eye(size), np.ones(size)))
    target = np.concatenate((np.zeros(size), np.ones(1)))
    solution, *_ = np.linalg.lstsq(system, target, rcond=None)
    solution = np.where(solution < 0.0, 0.0, solution)
    total = float(solution.sum())
    if not np.isfinite(total) or total <= 0:
        raise ValueError("transition_matrix has no usable stationary distribution")
    solution = solution / total
    if not np.allclose(solution @ matrix, solution, atol=1e-8):
        raise ValueError("transition_matrix stationary distribution is not identifiable")
    return solution

def _bounded_probability(probability: float) -> float:
    return min(1.0 - _EPSILON, max(_EPSILON, float(probability)))


def _cap(value: float, maximum: float) -> float:
    value = max(0.0, float(value))
    return min(value, maximum) if maximum > 0 else value


def sample_quantile_latency_ms(
    rng: np.random.Generator,
    p50_ms: float,
    p95_ms: float,
    p99_ms: float,
    max_ms: float = 0.0,
) -> float:
    """Sample a smooth distribution anchored exactly at p50, p95, and p99.

    The inverse CDF is piecewise linear in normal-score/log-latency space. The
    lower segment passes through p50 and p95; the upper segment passes through
    p95 and p99. The optional cap limits extrapolation beyond p99.
    """
    return quantile_piecewise(
        float(rng.random()), p50_ms, p95_ms, p99_ms, max_ms=max_ms
    )


def quantile_piecewise(
    probability: float,
    p50_ms: float,
    p95_ms: float,
    p99_ms: float,
    *,
    max_ms: float = 0.0,
) -> float:
    probability = _bounded_probability(probability)
    z = _NORMAL.inv_cdf(probability)
    log50, log95, log99 = map(log, (p50_ms, p95_ms, p99_ms))
    lower_slope = (log95 - log50) / (_Z95 - _Z50)
    upper_slope = (log99 - log95) / (_Z99 - _Z95)
    if z <= _Z95:
        value = log50 + lower_slope * (z - _Z50)
    else:
        value = log95 + upper_slope * (z - _Z95)
    return _cap(exp(value), max_ms)


def _fit_lognormal(component: LatencyComponentConfig) -> tuple[float, float]:
    if component.calibration_mode == "p50_p95":
        mu = log(component.p50_ms)
        sigma = (log(component.p95_ms) - mu) / _Z95
        return mu, sigma
    mu = log(component.mean_ms) - 0.5 * component.sigma**2
    return mu, component.sigma


def _fit_weibull(component: LatencyComponentConfig) -> tuple[float, float]:
    if component.calibration_mode == "p50_p95":
        ratio = component.p95_ms / component.p50_ms
        shape = log(log(20.0) / log(2.0)) / log(ratio)
        scale = component.p50_ms / (log(2.0) ** (1.0 / shape))
        return shape, scale
    return component.shape, component.scale_ms


def _fit_loglogistic(component: LatencyComponentConfig) -> tuple[float, float]:
    if component.calibration_mode == "p50_p95":
        scale = component.p50_ms
        shape = log(19.0) / log(component.p95_ms / component.p50_ms)
        return shape, scale
    return component.shape, component.scale_ms


def _gpd_ratio(shape: float) -> float:
    if abs(shape) < 1e-9:
        return log(20.0) / log(2.0)
    numerator = 0.05 ** (-shape) - 1.0
    denominator = 0.5 ** (-shape) - 1.0
    return numerator / denominator


def _lomax_ratio(alpha: float) -> float:
    return (20.0 ** (1.0 / alpha) - 1.0) / (2.0 ** (1.0 / alpha) - 1.0)


def _fit_gpd(component: LatencyComponentConfig) -> tuple[float, float]:
    if component.calibration_mode != "p50_p95":
        return component.shape, component.scale_ms
    target_ratio = component.p95_ms / component.p50_ms
    low, high = -0.95, 20.0
    low_ratio = _gpd_ratio(low)
    high_ratio = _gpd_ratio(high)
    if not low_ratio <= target_ratio <= high_ratio:
        raise ValueError("p50/p95 ratio cannot be represented by generalized Pareto")
    for _ in range(120):
        middle = (low + high) / 2.0
        if _gpd_ratio(middle) < target_ratio:
            low = middle
        else:
            high = middle
    shape = (low + high) / 2.0
    if abs(shape) < 1e-9:
        scale = component.p50_ms / log(2.0)
    else:
        scale = component.p50_ms * shape / (0.5 ** (-shape) - 1.0)
    return shape, scale


def _fit_lomax(component: LatencyComponentConfig) -> tuple[float, float]:
    if component.calibration_mode != "p50_p95":
        return component.shape, component.scale_ms
    target_ratio = component.p95_ms / component.p50_ms
    minimum_ratio = log(20.0) / log(2.0)
    if target_ratio <= minimum_ratio:
        raise ValueError(
            "Lomax p95/p50 ratio must exceed ln(20)/ln(2) for zero-location fitting"
        )
    low, high = 0.02, 1_000.0
    for _ in range(160):
        middle = (low + high) / 2.0
        ratio = _lomax_ratio(middle)
        if ratio > target_ratio:
            low = middle
        else:
            high = middle
    alpha = (low + high) / 2.0
    scale = component.p50_ms / (2.0 ** (1.0 / alpha) - 1.0)
    return alpha, scale


def component_quantile(component: LatencyComponentConfig, probability: float) -> float:
    probability = _bounded_probability(probability)
    family = "quantile_piecewise" if component.family == "quantile" else component.family

    if family == "fixed":
        value = component.fixed_ms
    elif family == "shifted_exponential":
        value = component.shift_ms - component.scale_ms * log(1.0 - probability)
    elif family == "truncated_normal":
        location = component.mean_ms
        standard_deviation = component.stddev_ms
        lower_cdf = _NORMAL.cdf((0.0 - location) / standard_deviation)
        adjusted = lower_cdf + probability * (1.0 - lower_cdf)
        value = location + standard_deviation * _NORMAL.inv_cdf(adjusted)
    elif family == "lognormal":
        mu, sigma = _fit_lognormal(component)
        value = exp(mu + sigma * _NORMAL.inv_cdf(probability)) + component.shift_ms
    elif family == "weibull":
        shape, scale = _fit_weibull(component)
        value = component.shift_ms + scale * (-log(1.0 - probability)) ** (1.0 / shape)
    elif family == "loglogistic":
        shape, scale = _fit_loglogistic(component)
        value = component.shift_ms + scale * (probability / (1.0 - probability)) ** (1.0 / shape)
    elif family == "lomax":
        alpha, scale = _fit_lomax(component)
        value = component.shift_ms + scale * ((1.0 - probability) ** (-1.0 / alpha) - 1.0)
    elif family == "generalized_pareto":
        shape, scale = _fit_gpd(component)
        if abs(shape) < 1e-9:
            excess = -scale * log(1.0 - probability)
        else:
            excess = scale / shape * ((1.0 - probability) ** (-shape) - 1.0)
        value = component.shift_ms + excess
    elif family == "quantile_piecewise":
        value = quantile_piecewise(
            probability,
            component.p50_ms,
            component.p95_ms,
            component.p99_ms,
            max_ms=component.max_ms,
        )
    else:
        raise ValueError(f"Family {family} does not provide an analytic quantile")
    return _cap(value, component.max_ms)


def sample_component_ms(
    rng: np.random.Generator,
    component: LatencyComponentConfig,
) -> float:
    family = "quantile_piecewise" if component.family == "quantile" else component.family
    if family in {
        "fixed",
        "shifted_exponential",
        "truncated_normal",
        "lognormal",
        "weibull",
        "loglogistic",
        "lomax",
        "generalized_pareto",
        "quantile_piecewise",
    }:
        return component_quantile(component, float(rng.random()))
    if family == "gamma":
        value = component.shift_ms + float(rng.gamma(component.shape, component.scale_ms))
        return _cap(value, component.max_ms)
    if family == "erlang":
        value = component.shift_ms + float(
            rng.gamma(component.erlang_stages, component.scale_ms)
        )
        return _cap(value, component.max_ms)
    if family == "empirical":
        value = float(rng.choice(component.empirical_samples_ms))
        return _cap(value, component.max_ms)
    if family == "mixture":
        weights = np.asarray([child.weight for child in component.components], dtype=float)
        weights = weights / weights.sum()
        index = int(rng.choice(len(component.components), p=weights))
        value = sample_component_ms(rng, component.components[index])
        return _cap(value, component.max_ms)
    raise ValueError(f"Unsupported component family: {family}")


def latency_as_component(latency: LatencyConfig) -> LatencyComponentConfig:
    return LatencyComponentConfig(
        family=latency.distribution,
        calibration_mode=latency.calibration_mode,
        fixed_ms=latency.fixed_ms,
        shift_ms=latency.shift_ms,
        mean_ms=latency.mean_ms,
        sigma=latency.sigma,
        stddev_ms=latency.stddev_ms,
        shape=latency.shape,
        scale_ms=latency.scale_ms,
        erlang_stages=latency.erlang_stages,
        p50_ms=latency.p50_ms,
        p95_ms=latency.p95_ms,
        p99_ms=latency.p99_ms,
        max_ms=latency.max_ms,
        empirical_samples_ms=latency.empirical_samples_ms,
        components=latency.components,
    )


def sample_spliced_ms(rng: np.random.Generator, latency: LatencyConfig) -> float:
    if latency.body is None or latency.tail is None:
        raise ValueError("spliced latency requires body and tail")
    probability = float(rng.random())
    threshold_probability = latency.splice_quantile
    if probability <= threshold_probability:
        return component_quantile(latency.body, probability)

    threshold = component_quantile(latency.body, threshold_probability)
    tail_probability = (probability - threshold_probability) / (1.0 - threshold_probability)
    tail = latency.tail
    shape, scale = _fit_gpd(tail)
    tail_probability = _bounded_probability(tail_probability)
    if abs(shape) < 1e-9:
        excess = -scale * log(1.0 - tail_probability)
    else:
        excess = scale / shape * ((1.0 - tail_probability) ** (-shape) - 1.0)
    maximum = latency.max_ms or tail.max_ms
    return _cap(threshold + excess, maximum)


def component_descriptor(component: LatencyComponentConfig) -> dict[str, object]:
    result: dict[str, object] = {
        "family": component.family,
        "name": component.name,
        "weight": component.weight,
        "calibration_mode": component.calibration_mode,
        "shift_ms": component.shift_ms,
        "max_ms": component.max_ms,
    }
    if component.family in {"quantile", "quantile_piecewise"} or component.calibration_mode == "p50_p95":
        result.update(
            {
                "p50_ms": component.p50_ms,
                "p95_ms": component.p95_ms,
                "p99_ms": component.p99_ms,
            }
        )
    elif component.family == "fixed":
        result["fixed_ms"] = component.fixed_ms
    elif component.family == "truncated_normal":
        result.update({"mean_ms": component.mean_ms, "stddev_ms": component.stddev_ms})
    elif component.family == "lognormal":
        result.update({"mean_ms": component.mean_ms, "sigma": component.sigma})
    elif component.family == "erlang":
        result.update(
            {"erlang_stages": component.erlang_stages, "scale_ms": component.scale_ms}
        )
    elif component.family == "empirical":
        result["sample_count"] = len(component.empirical_samples_ms)
    elif component.family == "mixture":
        result["components"] = [component_descriptor(child) for child in component.components]
    else:
        result.update({"shape": component.shape, "scale_ms": component.scale_ms})
    return result


def theoretical_quantiles(
    component: LatencyComponentConfig,
    probabilities: tuple[float, ...] = (0.50, 0.95, 0.99, 0.999),
) -> dict[str, float]:
    result: dict[str, float] = {}
    for probability in probabilities:
        try:
            value = component_quantile(component, probability)
        except ValueError:
            return {}
        label = "p999_ms" if probability == 0.999 else f"p{int(probability * 100)}_ms"
        result[label] = round(float(value), 6)
    return result
