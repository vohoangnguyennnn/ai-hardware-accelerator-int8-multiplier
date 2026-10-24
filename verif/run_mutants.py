# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Mutation check: prove that the testbench detects realistic RTL bugs.

Each mutant copies a DUT's sources into build/mutants/<name>/, applies one
textual edit, and runs the normal exhaustive simulation. A mutant counts as
detected only if it builds and the simulation reports FAIL. A build error
or an edit pattern that no longer matches exactly once is a runner error,
so the check cannot silently degrade as the RTL evolves.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build" / "mutants"


@dataclass(frozen=True)
class Mutant:
    name: str
    dut: str
    srcs: tuple[str, ...]
    file: str
    old: str
    new: str
    intent: str
    cfg: str = ""  # mul8s_tbw configuration tag the mutant is simulated with


BW_SRCS = ("rtl/csa3to2.sv", "rtl/bw_ppgen8.sv", "rtl/mul8s_bw.sv")
TBW_SRCS = ("rtl/csa3to2.sv", "rtl/bw_ppgen8.sv", "rtl/mul8s_tbw.sv")
# Exercises truncation, compensation and the zero gate at once.
TBW_CFG = "tbw_k4_compzg"

MUTANTS = [
    Mutant("behav_unsigned", "mul8s_behav", ("rtl/mul8s_behav.sv",), "rtl/mul8s_behav.sv",
           "assign p = a * b;", "assign p = $unsigned(a) * $unsigned(b);",
           "signedness lost in the behavioral multiply"),
    Mutant("bw_no_nand", "mul8s_bw", BW_SRCS, "rtl/bw_ppgen8.sv",
           "assign pp[W*j+i] = ~(a[i] & b[j]);", "assign pp[W*j+i] = a[i] & b[j];",
           "sign-mixed partial products not inverted"),
    Mutant("bw_no_corr_lo", "mul8s_bw", BW_SRCS, "rtl/bw_ppgen8.sv",
           "assign rows[PW*j +: PW] = placed | CORR_ROW0;", "assign rows[PW*j +: PW] = placed;",
           "missing 2^8 correction constant"),
    Mutant("bw_no_corr_hi", "mul8s_bw", BW_SRCS, "rtl/bw_ppgen8.sv",
           "assign rows[PW*j +: PW] = placed | CORR_ROW7;", "assign rows[PW*j +: PW] = placed;",
           "missing 2^15 correction constant"),
    Mutant("csa_unshifted_carry", "mul8s_bw", BW_SRCS, "rtl/csa3to2.sv",
           "assign carry = {majority[WIDTH-2:0], 1'b0};", "assign carry = majority;",
           "carry word not weighted by 2"),
    Mutant("tree_row_dup", "mul8s_bw", BW_SRCS, "rtl/mul8s_bw.sv",
           ".z(r7)", ".z(r6)",
           "reduction tree wiring error (row 7 dropped, row 6 used twice)"),
    Mutant("cpa_no_carry", "mul8s_bw", BW_SRCS, "rtl/mul8s_bw.sv",
           "assign p = $signed(l4_s + l4_c);", "assign p = $signed(l4_s ^ l4_c);",
           "final adder without carry propagation"),
    Mutant("tbw_trunc_off_by_one", "mul8s_tbw", TBW_SRCS, "rtl/bw_ppgen8.sv",
           "if (i + j < TRUNC_COLS) begin : g_trunc", "if (i + j <= TRUNC_COLS) begin : g_trunc",
           "one column too many truncated", TBW_CFG),
    Mutant("tbw_no_comp_row", "mul8s_tbw", TBW_SRCS, "rtl/mul8s_tbw.sv",
           "assign r8 = COMP_ROW;", "assign r8 = '0;",
           "compensation constant not added", TBW_CFG),
    Mutant("tbw_tree_wiring", "mul8s_tbw", TBW_SRCS, "rtl/mul8s_tbw.sv",
           ".z(l1_c2)", ".z(l1_s2)",
           "9-row reduction tree wiring error", TBW_CFG),
    Mutant("tbw_zero_gate_a_only", "mul8s_tbw", TBW_SRCS, "rtl/mul8s_tbw.sv",
           "(a == '0) || (b == '0)", "(a == '0)",
           "zero gate ignores b", TBW_CFG),
    Mutant("tbw_zero_gate_dropped", "mul8s_tbw", TBW_SRCS, "rtl/mul8s_tbw.sv",
           "assign p = zero_operand ? '0 : $signed(sum);", "assign p = $signed(sum);",
           "zero gate not applied", TBW_CFG),
]


def build_mutant(m: Mutant) -> list[str]:
    out_dir = BUILD / m.name
    shutil.rmtree(out_dir, ignore_errors=True)
    (out_dir / "rtl").mkdir(parents=True)
    paths = []
    for src in m.srcs:
        text = (ROOT / src).read_text()
        if src == m.file:
            count = text.count(m.old)
            if count != 1:
                raise RuntimeError(f"mutant {m.name}: pattern {m.old!r} found {count} times in {src}")
            text = text.replace(m.old, m.new)
        dst = out_dir / src
        dst.write_text(text)
        paths.append(str(dst.relative_to(ROOT)))
    return paths


def run_mutant(m: Mutant) -> bool:
    srcs = build_mutant(m)
    sim_dir = BUILD / m.name
    cmd = [
        "make", "--no-print-directory", "-C", str(ROOT), "sim",
        f"DUT={m.dut}", f"SRCS={' '.join(srcs)}", f"SIM_DIR={sim_dir.relative_to(ROOT)}",
        "EXTRA_VERILATOR_FLAGS=-Wno-fatal",
    ]
    if m.cfg:
        cmd.append(f"CFG={m.cfg}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    sim_log = sim_dir / "sim.log"
    if not sim_log.exists():
        print(result.stdout + result.stderr)
        raise RuntimeError(f"mutant {m.name}: did not build, so it cannot test the testbench")
    log = sim_log.read_text()
    detected = result.returncode != 0 and "FAIL:" in log
    mismatches = sum(1 for ln in log.splitlines() if ln.startswith("MISMATCH"))
    status = "detected" if detected else "SURVIVED"
    print(f"  {m.name:<22} {status:<9} ({m.intent}; {mismatches} mismatches printed)")
    return detected


def main() -> int:
    print(f"mutation check: {len(MUTANTS)} mutants")
    survivors = [m.name for m in MUTANTS if not run_mutant(m)]
    if survivors:
        print(f"MUTATION CHECK FAILED: surviving mutants: {', '.join(survivors)}")
        return 1
    print(f"MUTATION CHECK PASSED: {len(MUTANTS)}/{len(MUTANTS)} mutants detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
