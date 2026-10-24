# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Generate exhaustive expected-result vector files for the RTL testbench.

Output format ($readmemh compatible): leading '//' comment lines, then
65,536 lines of 4 hex digits. Line k holds the expected 16-bit product
(two's complement) for the pair with index k = {a[7:0], b[7:0]}.

Usage:
    python -m models.gen_vectors --model exact --out build/vectors/exact.hex
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from models import bw_model, golden

MODELS = {
    "exact": golden.mul_exact_vec,
    "bw": bw_model.mul_bw_vec,
}


def generate(model: str) -> np.ndarray:
    a, b = golden.all_pairs()
    return MODELS[model](a, b)


def write_hex(path: Path, products: np.ndarray, model: str) -> None:
    if products.shape != (golden.NUM_PAIRS,):
        raise ValueError(f"expected {golden.NUM_PAIRS} products, got shape {products.shape}")
    path.parent.mkdir(parents=True, exist_ok=True)
    words = products.astype(np.int64) & bw_model.PRODUCT_MASK
    with path.open("w", encoding="ascii") as f:
        f.write(f"// model={model} entries={golden.NUM_PAIRS}\n")
        f.write("// line k = expected p[15:0] for index k = {a[7:0], b[7:0]}\n")
        f.writelines(f"{w:04x}\n" for w in words.tolist())


def read_hex(path: Path) -> np.ndarray:
    """Parse a vector file back into signed int64 products."""
    lines = [ln for ln in path.read_text(encoding="ascii").splitlines() if ln and not ln.startswith("//")]
    words = np.array([int(ln, 16) for ln in lines], dtype=np.int64)
    return np.where(words >> 15, words - (1 << 16), words)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", choices=sorted(MODELS), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    write_hex(args.out, generate(args.model), args.model)
    print(f"wrote {golden.NUM_PAIRS} vectors ({args.model}) to {args.out}")


if __name__ == "__main__":
    main()
