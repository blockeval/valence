from __future__ import annotations

import pytest

from valence.analysis.statistics import (
    bootstrap_ci,
    cohen_dz,
    holm_adjust,
    linear_slope,
    paired_statistics,
    sign_flip_pvalue,
)


def test_bootstrap_ci_is_deterministic_and_contains_mean():
    values = [1, 2, 3, 4, 5]
    first = bootstrap_ci(values, resamples=2000, seed=7)
    second = bootstrap_ci(values, resamples=2000, seed=7)
    assert first == second
    assert first[0] < 3 < first[1]


def test_exact_sign_flip_detects_consistent_paired_change():
    differences = [1.0] * 10
    assert sign_flip_pvalue(differences) == pytest.approx(2 / 1024)
    assert cohen_dz(differences) == float("inf")


def test_holm_adjustment_is_monotonic_in_sorted_order():
    adjusted = holm_adjust([0.01, 0.04, 0.03])
    assert adjusted == pytest.approx([0.03, 0.06, 0.06])


def test_paired_statistics_uses_candidate_minus_reference():
    result = paired_statistics([1, 2, 3, 4], [2, 3, 4, 5], bootstrap_resamples=1000)
    assert result["mean_difference"] == 1.0
    assert result["positive_differences"] == 4
    assert result["negative_differences"] == 0


def test_linear_slope_recovers_known_relationship():
    assert linear_slope([0, 1, 2, 3], [1, 3, 5, 7]) == pytest.approx(2.0)
