# FPGA-Based Approximate INT8 Multiplier for AI Acceleration

Design, verification, and FPGA PPA evaluation of exact and approximate INT8
multiplier architectures for resource-efficient AI arithmetic.

The project follows one RTL engineering workflow end to end:
**arithmetic specification -> architecture -> SystemVerilog RTL -> exhaustive
verification -> error characterisation -> FPGA implementation -> PPA evaluation.**

## Project status

| Milestone | Content | Status |
|---|---|---|
| v0.1.0 | Exact behavioral and structural Baugh-Wooley multipliers, Python reference models, exhaustive verification | **Done** |
| v0.2.0 | Parameterized truncated Baugh-Wooley approximate multiplier, bit-accurate model, error characterisation | **Done** (all checks pass, see below) |
| v0.3.0 | Vivado 2024.1 out-of-context PPA evaluation on Artix-7 (`xc7a35tfgg484-2`) | **In progress**: flow implemented and tested with a mock Vivado; awaiting real Vivado runs |
| v1.0.0 | Stable IP, documentation, reproducible benchmark | Planned |

No FPGA utilization, timing or power numbers have been measured yet. Any
hardware benefit of the approximate design is still unverified. The
measurement method is fixed in advance in
[docs/fpga_methodology.md](docs/fpga_methodology.md).

## Arithmetic specification (summary)

* Operands `a`, `b`: signed INT8, two's complement, [-128, 127]
* Product `p`: signed 16-bit, [-16256, 16384] for the exact variants, no overflow
* Purely combinational, latency 0, one shared interface for all variants

Full details: [docs/spec.md](docs/spec.md).

## Implemented architectures

| Module | Description |
|---|---|
| [`rtl/mul8s_behav.sv`](rtl/mul8s_behav.sv) | Exact. Behavioral `a * b`; baseline for DSP and LUT mapping |
| [`rtl/mul8s_bw.sv`](rtl/mul8s_bw.sv) | Exact. Structural modified Baugh-Wooley: 8 partial-product rows (50 AND, 14 NAND, 2 correction constants), four levels of row-level 3:2 carry-save reduction, one 16-bit carry-propagate adder |
| [`rtl/mul8s_tbw.sv`](rtl/mul8s_tbw.sv) | Approximate. Truncated Baugh-Wooley: removes the `TRUNC_COLS` (0..7) lowest matrix columns, with an optional bias-compensation constant (`COMP_EN`) and an optional zero-operand gate (`ZERO_GATE`) |
| [`rtl/bw_ppgen8.sv`](rtl/bw_ppgen8.sv) | Baugh-Wooley partial-product generator (with column truncation) |
| [`rtl/csa3to2.sv`](rtl/csa3to2.sv) | Row-level 3:2 carry-save adder |
| [`fpga/rtl/mul8s_dsp.sv`](fpga/rtl/mul8s_dsp.sv) | Exact, DSP48E1-mapped FPGA baseline (same arithmetic as `mul8s_behav`) |
| [`fpga/rtl/bench_top.sv`](fpga/rtl/bench_top.sv) | FPGA benchmark wrapper: registered inputs, multiplier, registered output (2-cycle latency) |

Derivations: [docs/architecture.md](docs/architecture.md) (exact) and
[docs/approximation.md](docs/approximation.md) (approximate).

## Approximation results

Truncating `K` columns removes `L_K = sum_{i+j<K} a_i b_j 2^(i+j)`, so plain
truncation is biased by `-((K-1) 2^K + 1) / 4`. The compensation constant
cancels that bias to within -0.25 LSB. The figures below are measured
exhaustively over all 65,536 operand pairs from the bit-accurate model, which
the RTL matches exactly.

| K | Mode | MAE | NMED | MRED | Bias |
|---|---|---|---|---|---|
| 4 | truncation only | 12.250 | 7.48e-04 | 2.53% | -12.250 |
| 4 | + compensation + zero gate | 7.758 | 4.74e-04 | 1.49% | -0.344 |
| 6 | truncation only | 80.250 | 4.90e-03 | 15.96% | -80.250 |
| 6 | + compensation + zero gate | 41.147 | 2.51e-03 | 9.60% | -0.874 |

![MAE and MRED vs truncation depth](results/figures/metrics_vs_k.png)

The full table covering all 24 configurations is in
[results/error_metrics.md](results/error_metrics.md), and metric definitions
are in [docs/error_metrics.md](docs/error_metrics.md).

## Verification

Every variant and configuration is checked against independent Python models
for all 65,536 input pairs. The testbench is itself validated by mutation
testing. Full method: [docs/verification.md](docs/verification.md).

| Check | Result (2026-10-24) |
|---|---|
| Python tests (models, metrics, FPGA flow on a mock Vivado) | 133 passed |
| `mul8s_behav`, `mul8s_bw`, exhaustive (Verilator, Icarus) | 65,536 / 65,536 |
| `mul8s_tbw`, exhaustive, all 24 configurations (Verilator) | 65,536 / 65,536 each |
| `mul8s_tbw`, exhaustive, 4 spot configurations (Icarus) | 65,536 / 65,536 each |
| FPGA benchmark wrapper, clocked (5 configurations) | 65,536 / 65,536, 2-cycle latency |
| Verilator `-Wall` lint (all DUTs and configurations) | clean |
| Injected RTL bugs detected by the testbench | 12 / 12 |

## Reproducing

Tested on Ubuntu 24.04 with Verilator 5.020, Icarus Verilog 12.0, Yosys 0.33
and Python 3.13.

```bash
sudo apt-get install -y verilator iverilog yosys
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make test                # full regression; prints REGRESSION PASSED
make sim-tbw_k4_comp     # one approximate configuration
make results             # regenerate error metrics and figures
make help
```

FPGA PPA sweep (needs Vivado 2024.1; see
[docs/fpga_methodology.md](docs/fpga_methodology.md)):

```bash
source /tools/Xilinx/Vivado/2024.1/settings64.sh
make fpga FPGA_JOBS=2      # writes results/fpga/
make fpga-summary          # tables and trade-off figures
```

## Repository layout

```
rtl/       synthesizable SystemVerilog (no tool-specific attributes)
models/    Python reference models, error metrics, vector generator
tests/     pytest tests for the models and metrics
verif/     self-checking testbench and mutation runner
scripts/   error characterisation and FPGA result summaries
fpga/      benchmark wrapper, DSP variant, Vivado Tcl flow and sweep driver
results/   generated error metrics, figures and (after Vivado runs) FPGA results
docs/      specification, architecture, approximation, metrics, verification, FPGA method
```

## Roadmap

* **v0.3.0**: run the Vivado 2024.1 OOC sweep on the MicroPhase A7-Lite 35T
  device. Compare exact DSP, exact LUT, structural Baugh-Wooley and all 24
  `mul8s_tbw` configurations by post-route utilization and Fmax, then select
  the recommended approximate configuration.
* **v1.0.0**: Interface freeze, documentation, release packaging.

## License

[Apache License 2.0](LICENSE).
