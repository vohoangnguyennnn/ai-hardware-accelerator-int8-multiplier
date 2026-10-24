# FPGA-Based Approximate INT8 Multiplier for AI Acceleration

Design, verification, and FPGA PPA evaluation of exact and approximate INT8
multiplier architectures for resource-efficient AI arithmetic.

The project follows one RTL engineering workflow end to end:
**arithmetic specification -> architecture -> SystemVerilog RTL -> exhaustive
verification -> error characterisation -> FPGA implementation -> PPA evaluation.**

## Project status

| Milestone | Content | Status |
|---|---|---|
| v0.1.0 | Exact behavioral and structural Baugh-Wooley multipliers, Python reference models, exhaustive verification | **Done** (all checks pass, see below) |
| v0.2.0 | Truncated Baugh-Wooley approximate multiplier, bit-accurate model, error metrics | Planned |
| v0.3.0 | Vivado 2024.1 out-of-context PPA evaluation on Artix-7 (`xc7a35tfgg484-2`) | Planned |
| v1.0.0 | Stable IP, documentation, reproducible benchmark | Planned |

No FPGA utilization, timing or power numbers have been measured yet.

## Arithmetic specification (summary)

* Operands `a`, `b`: signed INT8, two's complement, [-128, 127]
* Product `p`: signed 16-bit full product, [-16256, 16384], no overflow
* Purely combinational, latency 0, one shared interface for all variants

Full details: [docs/spec.md](docs/spec.md).

## Implemented architectures

| Module | Description |
|---|---|
| [`rtl/mul8s_behav.sv`](rtl/mul8s_behav.sv) | Behavioral `a * b`; baseline for DSP and LUT mapping |
| [`rtl/mul8s_bw.sv`](rtl/mul8s_bw.sv) | Structural modified Baugh-Wooley: 8 partial-product rows (50 AND, 14 NAND, 2 correction constants), four levels of row-level 3:2 carry-save reduction, one 16-bit carry-propagate adder |
| [`rtl/bw_ppgen8.sv`](rtl/bw_ppgen8.sv) | Baugh-Wooley partial-product generator |
| [`rtl/csa3to2.sv`](rtl/csa3to2.sv) | Row-level 3:2 carry-save adder |

The derivation and how it maps to the datapath:
[docs/architecture.md](docs/architecture.md).

## Verification

Every variant is checked against an independent Python golden model for all
65,536 input pairs, on two simulators. The testbench is itself validated by
mutation testing. Full method: [docs/verification.md](docs/verification.md).

| Check | Result (2026-10-24) |
|---|---|
| Reference-model tests (pytest) | 38 passed |
| `mul8s_behav`, exhaustive (Verilator, Icarus) | 65,536 / 65,536 |
| `mul8s_bw`, exhaustive (Verilator, Icarus) | 65,536 / 65,536 |
| Verilator `-Wall` lint | clean |
| Injected RTL bugs detected by the testbench | 7 / 7 |

## Reproducing

Tested on Ubuntu 24.04 with Verilator 5.020, Icarus Verilog 12.0, Yosys 0.33
and Python 3.13.

```bash
sudo apt-get install -y verilator iverilog yosys
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
make test                # full regression; prints REGRESSION PASSED
make sim DUT=mul8s_bw    # one exhaustive simulation
make help
```

## Repository layout

```
rtl/       synthesizable SystemVerilog (no tool-specific attributes)
models/    Python reference models and vector generator
tests/     pytest tests for the reference models
verif/     self-checking testbench and mutation runner
docs/      specification, architecture, verification
```

## Roadmap

* **v0.2.0**: Truncated Baugh-Wooley `mul8s_tbw` with parameter `TRUNC_COLS`
  (0..7), plus a compensation and zero-gating study. Report ER, MAE, NMED,
  MRED, bias and MSE with plots.
* **v0.3.0**: Vivado 2024.1 OOC flow on the MicroPhase A7-Lite 35T device.
  Compare exact DSP, exact LUT, structural Baugh-Wooley and approximate
  variants using post-route utilization and timing.
* **v1.0.0**: Interface freeze, documentation, release packaging.

## License

[Apache License 2.0](LICENSE).
