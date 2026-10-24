# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Bit-level model of the modified Baugh-Wooley 8x8 signed multiplier.

This model reproduces the partial-product matrix described in
docs/architecture.md, using only bit operations, and sums it modulo 2^16.
It validates the arithmetic derivation independently of the RTL. The
golden model (Python integer multiplication) is the oracle the RTL is
verified against.

Partial-product matrix (W = 8, p_ij = a_i & b_j, weight 2^(i+j)):
    * p_ij                     for i < 7 and j < 7      (49 AND terms)
    * p_77                     at column 14             (1 AND term)
    * ~p_7j, ~p_i7             for i, j < 7             (14 NAND terms)
    * constant 1 at column W   (2^8)
    * constant 1 at column 2W-1 (2^15)
"""

from __future__ import annotations

import numpy as np

from models.golden import OPERAND_WIDTH, PRODUCT_WIDTH

W = OPERAND_WIDTH
PRODUCT_MASK = (1 << PRODUCT_WIDTH) - 1
# Baugh-Wooley correction constant columns (see docs/architecture.md).
CORRECTION_COLUMNS = (W, 2 * W - 1)


def is_inverted(i: int, j: int) -> bool:
    """True when partial product a_i*b_j carries a negative weight (exactly one sign bit)."""
    return (i == W - 1) != (j == W - 1)


def pp_rows(a: int, b: int) -> list[int]:
    """Return the eight 16-bit partial-product row words, matching rtl/bw_ppgen8.sv.

    Row j holds a_i*b_j (or its inverse) at column i+j. The two correction
    constants occupy otherwise-empty slots: row 0 column 8 and row 7 column 15.
    """
    a_u = a & 0xFF
    b_u = b & 0xFF
    rows = []
    for j in range(W):
        row = 0
        b_j = (b_u >> j) & 1
        for i in range(W):
            pp = ((a_u >> i) & 1) & b_j
            if is_inverted(i, j):
                pp ^= 1
            row |= pp << (i + j)
        rows.append(row)
    rows[0] |= 1 << CORRECTION_COLUMNS[0]
    rows[W - 1] |= 1 << CORRECTION_COLUMNS[1]
    return rows


def to_signed16(value: int) -> int:
    value &= PRODUCT_MASK
    return value - (1 << PRODUCT_WIDTH) if value >> (PRODUCT_WIDTH - 1) else value


def mul_bw(a: int, b: int) -> int:
    """Scalar Baugh-Wooley product (sum of partial-product rows modulo 2^16)."""
    return to_signed16(sum(pp_rows(a, b)))


def mul_bw_vec(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Vectorized Baugh-Wooley product over int64 arrays."""
    a_u = np.asarray(a, dtype=np.int64) & 0xFF
    b_u = np.asarray(b, dtype=np.int64) & 0xFF
    acc = np.zeros_like(a_u)
    for i in range(W):
        a_i = (a_u >> i) & 1
        for j in range(W):
            pp = a_i & ((b_u >> j) & 1)
            if is_inverted(i, j):
                pp = pp ^ 1
            acc += pp << (i + j)
    for col in CORRECTION_COLUMNS:
        acc += 1 << col
    acc &= PRODUCT_MASK
    return np.where(acc >> (PRODUCT_WIDTH - 1), acc - (1 << PRODUCT_WIDTH), acc)
