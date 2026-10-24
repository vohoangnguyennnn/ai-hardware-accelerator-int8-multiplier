# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Tests for the truncated Baugh-Wooley model and the error metrics."""

import numpy as np
import pytest

from models import approx_tbw, golden, metrics
from models.approx_tbw import TbwConfig

CONFIGS = approx_tbw.all_configs()


@pytest.fixture(scope="module")
def pairs():
    return golden.all_pairs()


@pytest.fixture(scope="module")
def exact(pairs):
    return golden.mul_exact_vec(*pairs)


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda c: c.name)
def test_closed_form_matches_matrix_model(pairs, cfg):
    """The two independent formulations agree on all 65,536 pairs."""
    closed = approx_tbw.mul_tbw_vec(*pairs, cfg)
    matrix = approx_tbw.mul_tbw_matrix_vec(*pairs, cfg)
    mismatches = np.flatnonzero(closed != matrix)
    assert mismatches.size == 0, f"first mismatching indices: {mismatches[:10]}"


@pytest.mark.parametrize("mode", approx_tbw.MODES)
def test_k0_is_exact(pairs, exact, mode):
    cfg = TbwConfig(0, comp_en=(mode != "none"), zero_gate=(mode == "compzg"))
    np.testing.assert_array_equal(approx_tbw.mul_tbw_vec(*pairs, cfg), exact)


@pytest.mark.parametrize("k", range(approx_tbw.MAX_TRUNC_COLS + 1))
def test_comp_constant_closed_form_matches_exhaustive_mean(k):
    assert approx_tbw.comp_constant(k) == approx_tbw.comp_constant_empirical(k)


def test_comp_constant_values():
    # round(((K-1) 2^K + 1) / 4) for K = 0..7
    assert [approx_tbw.comp_constant(k) for k in range(8)] == [0, 0, 1, 4, 12, 32, 80, 192]


@pytest.mark.parametrize("k", range(1, approx_tbw.MAX_TRUNC_COLS + 1))
def test_uncompensated_error_is_never_positive(pairs, exact, k):
    """All removed bits have positive weight, so plain truncation only under-estimates."""
    e = approx_tbw.mul_tbw_vec(*pairs, TbwConfig(k)) - exact
    assert e.max() == 0
    assert e.mean() == pytest.approx(-((k - 1) * 2**k + 1) / 4)


@pytest.mark.parametrize("k", range(approx_tbw.MAX_TRUNC_COLS + 1))
def test_zero_operand_behaviour(pairs, k):
    """No compensation or zero gate: 0 * x = 0. Compensation alone: 0 * x = C_K."""
    a, b = pairs
    zero = (a == 0) | (b == 0)
    assert np.all(approx_tbw.mul_tbw_vec(a, b, TbwConfig(k))[zero] == 0)
    assert np.all(approx_tbw.mul_tbw_vec(a, b, TbwConfig(k, comp_en=True))[zero] == approx_tbw.comp_constant(k))
    assert np.all(approx_tbw.mul_tbw_vec(a, b, TbwConfig(k, comp_en=True, zero_gate=True))[zero] == 0)


def test_dropped_term_depends_only_on_low_bits(pairs):
    a, b = pairs
    for k in (3, 7):
        low = approx_tbw.dropped_term_vec(a, b, k)
        mask = (1 << k) - 1
        np.testing.assert_array_equal(low, approx_tbw.dropped_term_vec(a & mask, b & mask, k))


@pytest.mark.parametrize("bad", [-1, 8])
def test_trunc_cols_range_enforced(bad):
    with pytest.raises(ValueError):
        TbwConfig(bad)


@pytest.mark.parametrize("cfg", CONFIGS, ids=lambda c: c.name)
def test_config_name_roundtrip(cfg):
    assert TbwConfig.from_name(cfg.name) == cfg


@pytest.mark.parametrize("name", ["tbw_k8_none", "tbw_k4", "tbw_kx_comp", "foo_k4_comp", "tbw_k4_bogus"])
def test_invalid_config_names(name):
    with pytest.raises(ValueError):
        TbwConfig.from_name(name)


def test_metrics_on_known_errors():
    p_exact = np.array([0, 10, -20, 40])
    p_approx = np.array([2, 10, -22, 36])  # e = [2, 0, -2, -4]
    m = metrics.error_metrics(p_approx, p_exact)
    assert m["er"] == pytest.approx(0.75)
    assert m["mae"] == pytest.approx(2.0)
    assert m["nmed"] == pytest.approx(2.0 / 16384)
    assert m["mred"] == pytest.approx((0 / 10 + 2 / 20 + 4 / 40) / 3)
    assert m["bias"] == pytest.approx(-1.0)
    assert m["mse"] == pytest.approx(6.0)
    assert (m["n_zero_exact"], m["n_zero_exact_wrong"]) == (1, 1)


def test_metrics_exact_is_zero(exact):
    m = metrics.error_metrics(exact, exact)
    assert m["er"] == m["mae"] == m["mred"] == m["bias"] == m["mse"] == 0.0
    assert m["n_zero_exact"] == 511


def test_metrics_reject_mismatched_shapes():
    with pytest.raises(ValueError):
        metrics.error_metrics(np.zeros(3), np.zeros(4))
