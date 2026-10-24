# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Arithmetic error metrics for approximate multipliers.

All metrics use e = P_approx - P_exact over the supplied operand pairs.
Definitions and conventions: docs/error_metrics.md.
Worst-case error is intentionally not reported (project decision).
"""

from __future__ import annotations

import numpy as np

# Largest exact product magnitude for signed INT8: (-128) * (-128).
NMED_NORMALIZER = 1 << 14

METRIC_FIELDS = ("er", "mae", "nmed", "mred", "bias", "mse", "n_pairs", "n_zero_exact", "n_zero_exact_wrong")


def error_metrics(p_approx: np.ndarray, p_exact: np.ndarray) -> dict[str, float]:
    """Return the metric set for paired approximate/exact products."""
    p_approx = np.asarray(p_approx, dtype=np.int64)
    p_exact = np.asarray(p_exact, dtype=np.int64)
    if p_approx.shape != p_exact.shape or p_exact.ndim != 1 or p_exact.size == 0:
        raise ValueError("expected two non-empty 1-D arrays of equal length")

    e = p_approx - p_exact
    abs_e = np.abs(e)
    nonzero = p_exact != 0
    zero = ~nonzero
    return {
        "er": float(np.mean(e != 0)),
        "mae": float(abs_e.mean()),
        "nmed": float(abs_e.mean() / NMED_NORMALIZER),
        # Relative error is undefined for P_exact = 0; those pairs are excluded
        # here and accounted for by n_zero_exact / n_zero_exact_wrong.
        "mred": float(np.mean(abs_e[nonzero] / np.abs(p_exact[nonzero]))) if nonzero.any() else float("nan"),
        "bias": float(e.mean()),
        "mse": float(np.mean(e.astype(np.float64) ** 2)),
        "n_pairs": int(e.size),
        "n_zero_exact": int(zero.sum()),
        "n_zero_exact_wrong": int(np.count_nonzero(e[zero])),
    }
