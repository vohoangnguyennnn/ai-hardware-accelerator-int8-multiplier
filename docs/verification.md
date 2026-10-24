# Verification

## 1. Strategy

An 8x8 multiplier has only 2^16 = 65,536 input pairs, so every RTL variant is
verified **exhaustively**. Every pair is checked against an independent
reference. No random sampling is used.

| Layer | Oracle | Independent of |
|---|---|---|
| `models/golden.py` | Python arbitrary-precision `a * b` | All RTL and the Baugh-Wooley derivation |
| `models/bw_model.py` | Bit-level Baugh-Wooley matrix, checked against golden for all pairs | RTL |
| Corner cases in `tests/test_models.py` | Hand-written literal products | Both Python models |
| `verif/tb_mul8s.sv` | Expected-value file generated from `golden.py` | DUT |
| `EXACT_ORACLE` mode | SystemVerilog `*` cross-checks the vector file | Python |

Acceptance criteria:

* Exact variants: `P_RTL(A, B) == P_golden(A, B)` for **65,536 / 65,536** pairs.
* Approximate variants (v0.2.0): `P_RTL(A, B) == P_model(A, B)` for all pairs.
  The intentional approximation error is characterised separately and is
  never treated as a pass/fail criterion.

## 2. Testbench: `verif/tb_mul8s.sv`

* One generic testbench for every `mul8s_*` variant. The DUT is chosen with
  `+define+DUT=<module>`.
* `+VECTORS=<file>` loads 65,536 expected 16-bit products. Line `k` holds the
  expected result for index `k = {a[7:0], b[7:0]}`.
* Phase 1 runs 17 named directed cases: -128 x -128, -128 x 127, -1 x -1,
  zero operands, alternating bit patterns, and mixed-sign pairs.
* Phase 2 sweeps all 256 x 256 pairs. The testbench also checks that exactly
  65,536 pairs were visited.
* On mismatch it prints the case tag, `a`, `b`, expected and actual values in
  decimal and hex, plus `diff = got ^ expected` to locate the wrong bits.
  The first 16 mismatches are printed in full.
* Any mismatch, a missing vector file or a malformed run ends in `$fatal`,
  giving a non-zero exit status.
* The same testbench runs on Verilator (2-state) and Icarus Verilog
  (4-state, so X or Z on `p` is also a failure through `!==`).

## 3. Testbench self-check (mutation testing)

`verif/run_mutants.py` copies the RTL, injects one realistic bug, and requires
the exhaustive simulation to report `FAIL`. A mutant that does not compile, or
an edit pattern that no longer matches exactly once, is a runner error, so the
check cannot silently become a no-op as the RTL changes.

| Mutant | Injected bug |
|---|---|
| `behav_unsigned` | Signedness lost in the behavioral multiply |
| `bw_no_nand` | Sign-mixed partial products not inverted |
| `bw_no_corr_lo` | Missing 2^8 correction constant |
| `bw_no_corr_hi` | Missing 2^15 correction constant |
| `csa_unshifted_carry` | Carry word not weighted by 2 |
| `tree_row_dup` | Reduction-tree wiring error |
| `cpa_no_carry` | Final adder without carry propagation |

## 4. Additional checks

* `make lint`: `verilator --lint-only -Wall` on every DUT, with no warnings
  allowed. The testbench is also built with `-Wall` as errors.
* `make synth-check`: Yosys `synth_xilinx -family xc7` on every DUT, as a
  synthesizability gate using a second front-end. Yosys cell counts are not
  Vivado results and are not used as PPA claims.

## 5. Running the regression

```bash
sudo apt-get install -y verilator iverilog yosys
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make test          # pytest, lint, Verilator + Icarus sims, Yosys check, mutants
make sim DUT=mul8s_bw
```

`make test` prints `REGRESSION PASSED` only if every step succeeds.

## 6. Recorded results

v0.1.0 regression, executed 2026-10-24 on Ubuntu 24.04.5 LTS with
Verilator 5.020, Icarus Verilog 12.0, Yosys 0.33, Python 3.13.17,
NumPy 2.5.4 and pytest 9.1.1:

| Check | Result |
|---|---|
| pytest (reference models) | 38 passed |
| Lint, `-Wall` | `mul8s_behav`, `mul8s_bw`: clean |
| `mul8s_behav`, Verilator | directed 17/17, exhaustive 65,536/65,536 |
| `mul8s_bw`, Verilator | directed 17/17, exhaustive 65,536/65,536 |
| `mul8s_behav`, Icarus | directed 17/17, exhaustive 65,536/65,536 |
| `mul8s_bw`, Icarus | directed 17/17, exhaustive 65,536/65,536 |
| Yosys synthesizability | both DUTs synthesize |
| Mutation check | 7/7 mutants detected |

CI (`.github/workflows/ci.yml`) re-runs `make test` on every push and pull
request.
