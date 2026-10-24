# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Bit-accurate model of the truncated Baugh-Wooley multiplier (mul8s_tbw).

Configuration (identical to the RTL parameters):
    trunc_cols  K in [0, 7]  partial-product bits with i + j < K are removed
    comp_en     bool         add the bias-compensation constant C_K
    zero_gate   bool         force p = 0 when a == 0 or b == 0

Two formulations are implemented and cross-checked by the test suite:

1. Matrix form (`mul_tbw_matrix_vec`): sum the Baugh-Wooley partial-product
   matrix of models/bw_model.py with the low columns removed. This mirrors
   the hardware structure.

2. Closed form (`mul_tbw_vec`): for K <= 7 every removed bit is an
   unsigned term a_i*b_j with i, j <= 6 (no sign bits, no inverted terms), so

       P~ = A*B - L_K(A, B) + C_K,   L_K = sum_{i+j<K} a_i b_j 2^(i+j)

   This needs only the golden product and the operand bit patterns.

Under uniform operands each a_i*b_j (i, j <= 6) is 1 with probability 1/4:

    E[L_K] = (1/4) * sum_{s=0}^{K-1} (s+1) 2^s = ((K-1) 2^K + 1) / 4

C_K is E[L_K] rounded to the nearest integer. `comp_constant` computes it
from that closed form, which is also what the RTL uses. `comp_constant_empirical`
recomputes it from the exhaustive mean, and the tests check that the two agree.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from models import bw_model, golden

MAX_TRUNC_COLS = 7
MODES = ("none", "comp", "compzg")


@dataclass(frozen=True)
class TbwConfig:
    trunc_cols: int
    comp_en: bool = False
    zero_gate: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.trunc_cols <= MAX_TRUNC_COLS:
            raise ValueError(f"trunc_cols={self.trunc_cols} outside [0, {MAX_TRUNC_COLS}]")

    @property
    def mode(self) -> str:
        if not self.comp_en:
            if self.zero_gate:
                return "zg"
            return "none"
        return "compzg" if self.zero_gate else "comp"

    @property
    def name(self) -> str:
        """Configuration tag used for vector files and simulation directories."""
        return f"tbw_k{self.trunc_cols}_{self.mode}"

    @classmethod
    def from_name(cls, name: str) -> "TbwConfig":
        """Parse a tag such as 'tbw_k4_compzg'."""
        try:
            prefix, k, mode = name.split("_")
            if prefix != "tbw" or not k.startswith("k") or mode not in (*MODES, "zg"):
                raise ValueError
            trunc_cols = int(k[1:])
        except ValueError:
            raise ValueError(f"invalid tbw configuration name {name!r}") from None
        return cls(trunc_cols, comp_en=mode.startswith("comp"), zero_gate=mode.endswith("zg"))


def all_configs() -> list[TbwConfig]:
    """The supported configuration grid: K = 0..7 x {none, comp, comp+zero-gate}."""
    return [
        TbwConfig(k, comp_en=(m != "none"), zero_gate=(m == "compzg"))
        for k in range(MAX_TRUNC_COLS + 1)
        for m in MODES
    ]


def comp_constant(trunc_cols: int) -> int:
    """C_K = round(((K-1) 2^K + 1) / 4), written with integer arithmetic as in the RTL."""
    return (((trunc_cols - 1) << trunc_cols) + 3) // 4 if trunc_cols > 0 else 0


def dropped_term_vec(a: np.ndarray, b: np.ndarray, trunc_cols: int) -> np.ndarray:
    """L_K(A, B): value of the partial-product bits removed by truncation."""
    a_u = np.asarray(a, dtype=np.int64) & 0xFF
    b_u = np.asarray(b, dtype=np.int64) & 0xFF
    low = np.zeros_like(a_u)
    for i in range(trunc_cols):
        for j in range(trunc_cols - i):
            low += (((a_u >> i) & 1) & ((b_u >> j) & 1)) << (i + j)
    return low


def comp_constant_empirical(trunc_cols: int) -> int:
    """round(mean L_K) over all 65,536 pairs (independent check of comp_constant)."""
    a, b = golden.all_pairs()
    return int(np.floor(dropped_term_vec(a, b, trunc_cols).mean() + 0.5))


def _finish(p: np.ndarray, a: np.ndarray, b: np.ndarray, cfg: TbwConfig) -> np.ndarray:
    if cfg.zero_gate:
        p = np.where((np.asarray(a) == 0) | (np.asarray(b) == 0), 0, p)
    return p


def mul_tbw_vec(a: np.ndarray, b: np.ndarray, cfg: TbwConfig) -> np.ndarray:
    """Closed-form model: A*B - L_K + C_K (optionally zero-gated)."""
    p = golden.mul_exact_vec(a, b) - dropped_term_vec(a, b, cfg.trunc_cols)
    if cfg.comp_en:
        p = p + comp_constant(cfg.trunc_cols)
    if p.min() < -(1 << 15) or p.max() >= (1 << 15):
        raise AssertionError("approximate product left the 16-bit signed range")
    return _finish(p, a, b, cfg)


def mul_tbw_matrix_vec(a: np.ndarray, b: np.ndarray, cfg: TbwConfig) -> np.ndarray:
    """Matrix model: truncated Baugh-Wooley matrix plus constant, modulo 2^16."""
    a_u = np.asarray(a, dtype=np.int64) & 0xFF
    b_u = np.asarray(b, dtype=np.int64) & 0xFF
    acc = np.zeros_like(a_u)
    for i in range(bw_model.W):
        for j in range(bw_model.W):
            if i + j < cfg.trunc_cols:
                continue
            pp = ((a_u >> i) & 1) & ((b_u >> j) & 1)
            if bw_model.is_inverted(i, j):
                pp = pp ^ 1
            acc += pp << (i + j)
    for col in bw_model.CORRECTION_COLUMNS:
        acc += 1 << col
    if cfg.comp_en:
        acc += comp_constant(cfg.trunc_cols)
    acc &= bw_model.PRODUCT_MASK
    p = np.where(acc >> 15, acc - (1 << 16), acc)
    return _finish(p, a, b, cfg)
