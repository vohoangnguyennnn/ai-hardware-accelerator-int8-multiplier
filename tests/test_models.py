# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Tests for the Python reference models (golden and Baugh-Wooley)."""

import numpy as np
import pytest

from models import bw_model, gen_vectors, golden

# Literal expected values: a third, hand-checked oracle for corner cases.
CORNER_CASES = [
    (-128, -128, 16384),
    (-128, 127, -16256),
    (127, -128, -16256),
    (127, 127, 16129),
    (-1, -1, 1),
    (-1, -128, 128),
    (-1, 127, -127),
    (1, -128, -128),
    (-128, 0, 0),
    (0, -128, 0),
    (0, 0, 0),
    (85, -86, -7310),
    (-86, 85, -7310),
]


@pytest.fixture(scope="module")
def pairs():
    return golden.all_pairs()


@pytest.mark.parametrize("a,b,expected", CORNER_CASES)
def test_exact_corner_cases(a, b, expected):
    assert golden.mul_exact(a, b) == expected


@pytest.mark.parametrize("a,b,expected", CORNER_CASES)
def test_bw_corner_cases(a, b, expected):
    assert bw_model.mul_bw(a, b) == expected


@pytest.mark.parametrize("a,b", [(128, 0), (0, -129), (True, 1), (1.0, 1)])
def test_exact_rejects_invalid_operands(a, b):
    with pytest.raises((ValueError, TypeError)):
        golden.mul_exact(a, b)


def test_all_pairs_ordering(pairs):
    a, b = pairs
    assert a.shape == b.shape == (golden.NUM_PAIRS,)
    assert len(set(zip(a.tolist(), b.tolist()))) == golden.NUM_PAIRS
    for k in (0, 1, 0x00FF, 0x7F80, 0x8000, 0xFFFF):
        assert golden.pair_index(int(a[k]), int(b[k])) == k


def test_exact_product_range(pairs):
    p = golden.mul_exact_vec(*pairs)
    assert p.min() == -16256
    assert p.max() == 16384
    assert int((p == 0).sum()) == 511


def test_product_needs_full_16_bits(pairs):
    """p[15] == p[14] holds for every pair except (-128) x (-128) = 0x4000."""
    a, b = pairs
    p = golden.mul_exact_vec(a, b) & 0xFFFF
    differs = ((p >> 15) & 1) != ((p >> 14) & 1)
    assert int(differs.sum()) == 1
    k = int(np.flatnonzero(differs)[0])
    assert (int(a[k]), int(b[k]), int(p[k])) == (-128, -128, 0x4000)


def test_bw_matches_exact_exhaustive(pairs):
    exact = golden.mul_exact_vec(*pairs)
    bw = bw_model.mul_bw_vec(*pairs)
    mismatches = np.flatnonzero(bw != exact)
    assert mismatches.size == 0, f"first mismatching indices: {mismatches[:10]}"


def test_bw_scalar_matches_vector(pairs):
    a, b = pairs
    rng = np.random.default_rng(seed=2026)
    for k in rng.choice(golden.NUM_PAIRS, size=512, replace=False):
        assert bw_model.mul_bw(int(a[k]), int(b[k])) == bw_model.mul_bw_vec(a[k : k + 1], b[k : k + 1])[0]


def test_bw_partial_product_matrix_shape():
    """Rows occupy only columns j..j+7, plus the two correction constants."""
    rows = bw_model.pp_rows(-1, -1)  # all a_i = b_j = 1 -> every AND term is 1, every NAND is 0
    inverted = sum(bw_model.is_inverted(i, j) for i in range(8) for j in range(8))
    assert inverted == 14
    for j, row in enumerate(rows):
        allowed = ((1 << 8) - 1) << j
        if j == 0:
            allowed |= 1 << 8
        if j == 7:
            allowed |= 1 << 15
        assert row & ~allowed == 0, f"row {j} has bits outside its columns"
    rows_zero = bw_model.pp_rows(0, 0)  # every AND term is 0, every NAND is 1
    assert sum(bin(r).count("1") for r in rows_zero) == 14 + 2


@pytest.mark.parametrize("model", sorted(gen_vectors.MODELS))
def test_vector_file_roundtrip(tmp_path, pairs, model):
    path = tmp_path / f"{model}.hex"
    gen_vectors.write_hex(path, gen_vectors.generate(model), model)
    lines = path.read_text().splitlines()
    data = [ln for ln in lines if not ln.startswith("//")]
    assert len(data) == golden.NUM_PAIRS
    assert all(len(ln) == 4 for ln in data)
    np.testing.assert_array_equal(gen_vectors.read_hex(path), golden.mul_exact_vec(*pairs))
