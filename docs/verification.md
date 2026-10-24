# Verification

## 1. Strategy

An 8x8 multiplier has only 2^16 = 65,536 input pairs, so every RTL variant and
every supported parameter configuration is verified **exhaustively**. Every
pair is checked against an independent reference. No random sampling is used.

| Layer | Oracle | Independent of |
|---|---|---|
| `models/golden.py` | Python arbitrary-precision `a * b` | All RTL and the Baugh-Wooley derivation |
| `models/bw_model.py` | Bit-level Baugh-Wooley matrix, checked against golden for all pairs | RTL |
| `models/approx_tbw.py` closed form | `A*B - L_K + C_K`, built on golden | RTL and the matrix structure |
| `models/approx_tbw.py` matrix form | Truncated Baugh-Wooley matrix, cross-checked against the closed form for all 24 configurations | RTL |
| Corner cases in `tests/` | Hand-written literal values | The models |
| `verif/tb_mul8s.sv` | Expected-value file generated from the models | DUT |
| `EXACT_ORACLE` mode | SystemVerilog `*` cross-checks the vector file (exact DUTs) | Python |

Acceptance criteria:

* Exact variants: `P_RTL(A, B) == P_golden(A, B)` for **65,536 / 65,536** pairs.
* Approximate variant: `P_RTL(A, B) == P_model(A, B)` for **65,536 / 65,536**
  pairs in **every one of the 24 configurations**. The intentional
  approximation error is characterised separately
  ([error_metrics.md](error_metrics.md)) and is never a pass/fail criterion.

## 2. Testbench: `verif/tb_mul8s.sv`

* One generic testbench for every `mul8s_*` variant. The DUT is chosen with
  `+define+DUT=<module>`. For `mul8s_tbw`, `+define+TBW_PARAMS` forwards the
  testbench's top-level parameters `TRUNC_COLS`, `COMP_EN` and `ZERO_GATE`
  (set with `-G` in Verilator or `-P` in Icarus).
* `+VECTORS=<file>` loads 65,536 expected 16-bit products. Line `k` holds the
  expected result for index `k = {a[7:0], b[7:0]}`.
* Phase 1 runs 17 named directed cases: -128 x -128, -128 x 127, -1 x -1,
  zero operands, alternating bit patterns, and mixed-sign pairs.
* Phase 2 sweeps all 256 x 256 pairs. The testbench also checks that exactly
  65,536 pairs were visited.
* On mismatch it prints the case tag, `a`, `b`, expected and actual values in
  decimal and hex, plus `diff = got ^ expected`. The first 16 mismatches are
  printed in full. Any mismatch, a missing vector file or a malformed run
  ends in `$fatal`.

## 3. Coverage of configurations

| Target | Configurations | Simulator |
|---|---|---|
| `mul8s_behav`, `mul8s_bw` | exact | Verilator and Icarus |
| `mul8s_tbw` | all 24: `K = 0..7` with modes none, comp, compzg | Verilator |
| `mul8s_tbw` | spot set: `k0_none`, `k4_comp`, `k4_compzg`, `k7_compzg` | Icarus (4-state) |

Verilator lint (`-Wall`, no warnings) runs on every exact DUT and on all 24
`mul8s_tbw` configurations. `TRUNC_COLS` outside 0..7 is rejected at
elaboration by Verilator, Yosys and Vivado. Icarus 12 ignores elaboration-time
`$error`.

## 4. Testbench self-check (mutation testing)

`verif/run_mutants.py` copies the RTL, injects one realistic bug, and requires
the exhaustive simulation to report `FAIL`. A mutant that does not compile, or
an edit pattern that no longer matches exactly once, is a runner error.
Approximate-datapath mutants are simulated as `tbw_k4_compzg`, which
exercises truncation, compensation and the zero gate together.

| Mutant | Injected bug |
|---|---|
| `behav_unsigned` | Signedness lost in the behavioral multiply |
| `bw_no_nand` | Sign-mixed partial products not inverted |
| `bw_no_corr_lo` | Missing 2^8 correction constant |
| `bw_no_corr_hi` | Missing 2^15 correction constant |
| `csa_unshifted_carry` | Carry word not weighted by 2 |
| `tree_row_dup` | Reduction-tree wiring error (8-row tree) |
| `cpa_no_carry` | Final adder without carry propagation |
| `tbw_trunc_off_by_one` | One column too many truncated |
| `tbw_no_comp_row` | Compensation constant not added |
| `tbw_tree_wiring` | Reduction-tree wiring error (9-row tree) |
| `tbw_zero_gate_a_only` | Zero gate ignores `b` |
| `tbw_zero_gate_dropped` | Zero gate not applied |

## 5. Additional checks

* `make synth-check`: Yosys `synth_xilinx -family xc7` on the exact DUTs and
  the `mul8s_tbw` spot set, as a synthesizability gate. Yosys cell counts are
  not Vivado results and are not used as PPA claims.
* `make check-results`: regenerates `results/error_metrics.csv` and
  `results/error_by_quadrant.csv` and fails if the committed files are stale.

## 6. Running the regression

```bash
sudo apt-get install -y verilator iverilog yosys
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make test                 # everything below; prints REGRESSION PASSED
make sim DUT=mul8s_bw     # one exact DUT
make sim-tbw_k4_comp      # one approximate configuration
make results              # regenerate metrics and figures
```

## 7. Recorded results

v0.2.0 regression, executed 2026-10-24 on Ubuntu 24.04.5 LTS with
Verilator 5.020, Icarus Verilog 12.0, Yosys 0.33, Python 3.13.17,
NumPy 2.5.4, pytest 9.1.1 and Matplotlib 3.11.2:

| Check | Result |
|---|---|
| pytest (reference models, metrics) | 124 passed |
| Verilator `-Wall` lint | clean: 2 exact DUTs + 24 `mul8s_tbw` configurations |
| `mul8s_behav`, `mul8s_bw` (Verilator and Icarus) | directed 17/17, exhaustive 65,536/65,536 each |
| `mul8s_tbw`, 24 configurations (Verilator) | directed 17/17, exhaustive 65,536/65,536 each |
| `mul8s_tbw`, 4 spot configurations (Icarus) | directed 17/17, exhaustive 65,536/65,536 each |
| Yosys synthesizability | all checked targets synthesize |
| Mutation check | 12/12 mutants detected |
| Results consistency | committed CSV files match the models |

CI (`.github/workflows/ci.yml`) re-runs `make test` on every push and pull
request.
