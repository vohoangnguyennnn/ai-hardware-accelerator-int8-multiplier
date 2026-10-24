# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Golden exact reference model for signed INT8 multiplication.

The golden model deliberately uses Python's arbitrary-precision integer
multiplication only. It shares no bit-level structure with the RTL or with
the Baugh-Wooley model, so it acts as an independent oracle.

Vector ordering convention (shared with the testbench):
    index = ((a & 0xFF) << 8) | (b & 0xFF)
i.e. the 16-bit concatenation {a[7:0], b[7:0]} interpreted as unsigned.
"""

from __future__ import annotations

import numpy as np

OPERAND_WIDTH = 8
PRODUCT_WIDTH = 2 * OPERAND_WIDTH
INT8_MIN = -(1 << (OPERAND_WIDTH - 1))
INT8_MAX = (1 << (OPERAND_WIDTH - 1)) - 1
NUM_PAIRS = 1 << PRODUCT_WIDTH


def _check_int8(name: str, value: int) -> None:
    if not isinstance(value, (int, np.integer)) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    if not INT8_MIN <= value <= INT8_MAX:
        raise ValueError(f"{name}={value} is outside signed INT8 range [{INT8_MIN}, {INT8_MAX}]")


def mul_exact(a: int, b: int) -> int:
    """Return the exact signed product a * b for signed INT8 operands."""
    _check_int8("a", a)
    _check_int8("b", b)
    return int(a) * int(b)


def pair_index(a: int, b: int) -> int:
    """Vector-file index of the operand pair (a, b)."""
    return ((a & 0xFF) << OPERAND_WIDTH) | (b & 0xFF)


def all_pairs() -> tuple[np.ndarray, np.ndarray]:
    """Return (A, B) as int64 arrays covering all 65,536 pairs in index order."""
    idx = np.arange(NUM_PAIRS, dtype=np.int64)
    a_u = idx >> OPERAND_WIDTH
    b_u = idx & 0xFF
    a = np.where(a_u > INT8_MAX, a_u - (1 << OPERAND_WIDTH), a_u)
    b = np.where(b_u > INT8_MAX, b_u - (1 << OPERAND_WIDTH), b_u)
    return a, b


def mul_exact_vec(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Vectorized exact product over int64 arrays."""
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    if a.min() < INT8_MIN or a.max() > INT8_MAX or b.min() < INT8_MIN or b.max() > INT8_MAX:
        raise ValueError("operands outside signed INT8 range")
    return a * b
