# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]: v0.3.0 candidate

### Added

- FPGA benchmark wrapper `fpga/rtl/bench_top.sv` (registered inputs and
  output, 2-cycle latency) and DSP-mapped baseline `fpga/rtl/mul8s_dsp.sv`.
- Vivado 2024.1 out-of-context flow `fpga/scripts/run_ooc.tcl` and sweep
  driver `fpga/scripts/run_sweep.py` (standard-library Python). The driver
  runs 27 variants on `xc7a35tfgg484-2`, with utilization and power at a
  common 10 ns constraint and an Fmax search that reports only passing
  post-route runs. It writes CSV, a manifest and reports to `results/fpga/`.
- `scripts/fpga_summary.py`: summary table and LUT-vs-MAE / Fmax-vs-K figures.
- Clocked wrapper testbench (`make bench-sim`), `mul8s_dsp` in the exhaustive
  regression, and a mock-Vivado test of the whole FPGA flow
  (`tests/test_fpga_flow.py`).
- `docs/fpga_methodology.md`.

### Pending

- Real Vivado results (to be produced on the project owner's machine).

## [0.2.0] - 2026-10-24

### Added

- `mul8s_tbw`: approximate truncated Baugh-Wooley multiplier with parameters
  `TRUNC_COLS` (0..7), `COMP_EN` (bias-compensation constant) and
  `ZERO_GATE` (exact zero for zero operands); 9-row carry-save tree, still
  four 3:2 levels.
- `bw_ppgen8` parameter `TRUNC_COLS` (default 0, so `mul8s_bw` is unchanged)
  with an elaboration-time range check.
- `models/approx_tbw.py`: bit-accurate model in two independent formulations
  (closed form `A*B - L_K + C_K` and truncated matrix), plus a closed-form
  compensation constant checked against the exhaustive mean.
- `models/metrics.py`: ER, MAE, NMED, MRED, bias and MSE (no worst-case error).
- `scripts/error_analysis.py` and `make results`: CSV/Markdown tables and
  figures in `results/`. `make check-results` keeps them in sync in CI.
- Exhaustive verification of all 24 `mul8s_tbw` configurations. The testbench
  forwards DUT parameters with `+define+TBW_PARAMS`.
- Five approximate-datapath mutants (12 in total).
- Documentation: `docs/approximation.md`, `docs/error_metrics.md`; updated
  spec, verification and README.

## [0.1.0] - 2026-10-24

### Added

- Arithmetic and interface specification (`docs/spec.md`), including the FPGA
  target: MicroPhase A7-Lite 35T, `xc7a35tfgg484-2`, Vivado 2024.1.
- `mul8s_behav`: behavioral exact signed INT8 multiplier.
- `mul8s_bw`: structural modified Baugh-Wooley multiplier (`bw_ppgen8`,
  `csa3to2`, four carry-save levels, single CPA).
- Python reference models: golden integer model and bit-level Baugh-Wooley
  model, plus a vector generator.
- Exhaustive self-checking testbench (Verilator and Icarus), Verilator lint,
  Yosys synthesizability check, and a mutation-testing self-check of the
  testbench.
- Architecture and verification documentation, Makefile regression, and a
  GitHub Actions CI workflow.
- Apache-2.0 license.
