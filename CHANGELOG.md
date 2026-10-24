# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]: v0.1.0 candidate

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
