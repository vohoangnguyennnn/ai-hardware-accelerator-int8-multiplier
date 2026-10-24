# FPGA Implementation and PPA Methodology

This document defines how utilization, timing and power are measured, so that
every variant is compared under identical, reproducible conditions. Results
are reported in `results/fpga/` only after real Vivado runs. **No FPGA results
have been recorded yet.**

## 1. Target and tools

| Item | Value |
|---|---|
| Device | Xilinx Artix-7 XC7A35T-2FGG484 (`xc7a35tfgg484-2`), MicroPhase A7-Lite 35T |
| Tool | AMD Vivado 2024.1, non-project batch mode |
| Host | Ubuntu 22.04 (project owner's machine); the actual tool version is recorded per run |

## 2. Benchmark wrapper

A purely combinational multiplier has no clock-to-clock path, so it cannot be
given a meaningful Fmax on its own. Every variant is therefore implemented
inside the same wrapper, `fpga/rtl/bench_top.sv`:

```
 a_in ──►[a_q]──┐
                ├──► multiplier variant ──► p_d ──►[p_q]──► p_out
 b_in ──►[b_q]──┘
          clk ─────────────────────────────────────┘
```

* The measured path is register to register: `a_q`/`b_q` → multiplier → `p_q`.
  This is the path a multiplier sits on inside a pipelined datapath.
* Latency is 2 cycles and throughput is one product per cycle. The data
  registers have no reset.
* The wrapper is verified with a clocked testbench (`make bench-sim`). All
  65,536 pairs are streamed through it with a 2-cycle latency check, for the
  behavioral, DSP, Baugh-Wooley and two `mul8s_tbw` configurations.

## 3. Variants and mapping control

| Variant | RTL | DSP use | How mapping is controlled |
|---|---|---|---|
| `exact_dsp` | `fpga/rtl/mul8s_dsp.sv` | 1 DSP48E1 expected | `(* use_dsp = "yes" *)`, no `-max_dsp` limit |
| `exact_lut` | `rtl/mul8s_behav.sv` | none | `synth_design -max_dsp 0` |
| `exact_bw` | `rtl/mul8s_bw.sv` | none | `-max_dsp 0` |
| `tbw_k<K>_<mode>` (24) | `rtl/mul8s_tbw.sv` | none | `-max_dsp 0` |

`mul8s_dsp` has the same arithmetic as `mul8s_behav`. It is a separate,
exhaustively verified module so the portable RTL carries no tool attributes.
The sweep checks the reported DSP count of every run against this table
(`mapping_ok` column). A mismatch is flagged, never silently accepted.

`tbw_k0_comp` and `tbw_k1_comp` have `C_K = 0` and are therefore the same
circuit as the corresponding `none` configuration. They are kept as a
run-to-run consistency check.

## 4. Implementation flow

`fpga/scripts/run_ooc.tcl`, one invocation per run:

```
read_verilog -sv <sources>
read_xdc bench_ooc.xdc            # create_clock on clk; HD.CLK_SRC BUFGCTRL_X0Y0
synth_design -mode out_of_context -flatten_hierarchy rebuilt -top bench_top \
             -part xc7a35tfgg484-2 -generic VARIANT=.. [-generic ...] [-max_dsp 0]
opt_design ; place_design ; phys_opt_design ; route_design      # default directives
report_utilization / report_timing_summary / report_timing / report_power / report_route_status
```

* **Out-of-context:** no I/O buffers are inserted and the ports are
  unconstrained, so only the internal register-to-register paths are timed.
  `HD.CLK_SRC` models a global clock buffer driving the block.
* **Default directives** and the default hierarchy setting (`rebuilt`) are used
  for every variant. Vivado may restructure the structural Baugh-Wooley tree,
  and that is part of what is measured.
* No retiming option is enabled.

## 5. Measurements

### 5.1 Utilization and power: common constraint

Pass 1 of every variant runs at the same clock period (**10.000 ns**). Slice
LUTs, slice registers, slices, CARRY4, DSP and BRAM are read from the
post-route `report_utilization`. LUT, FF, DSP and CARRY4 primitive counts are
also recorded from netlist queries as a cross-check.

Power comes from `report_power` on the same post-route design. It is a
**vectorless estimate** with Vivado's default switching activity, at 100 MHz.
It is not measured on the board. For a single 8x8 multiplier the dynamic power
is expected to be small next to the device static power. Power is reported
for completeness and is not used to rank variants unless the differences are
clearly larger than the estimation uncertainty.

### 5.2 Timing: Fmax search

Fmax is claimed only from a post-route run that meets timing:

1. Pass 1 (10.000 ns) gives the achieved period `T - WNS`.
2. Each next pass is constrained to the previous achieved period, rounded up
   to 0.01 ns. The constraint tightens after a passing run and loosens after
   a failing run.
3. The search stops when a passing run has less than 3% slack, when a period
   repeats, or after 4 runs.
4. **Fmax = 1 / (tightest constrained period with WNS >= 0 and no routing
   errors).**

The data-path delay and logic levels of the critical path are recorded for
pass 1 and for the best passing run. Every run is listed in
`results/fpga/fpga_passes.csv`.

## 6. Fairness notes and limitations

* **DSP register absorption.** For `exact_dsp`, Vivado can pull the wrapper
  registers into the DSP48E1 (AREG/BREG/MREG/PREG), so that variant may
  report zero fabric flip-flops. This is how a designer would use the DSP, and
  the latency (2 cycles) is the same, but the FF columns are not directly
  comparable.
* **Single instance.** One 8x8 multiplier is a small design, and placement
  effects can be a noticeable fraction of the result. Differences of a few
  LUTs or a few percent of Fmax should not be over-interpreted.
* **Two exact LUT references.** `exact_lut` (Vivado's own LUT mapping of `a*b`)
  and `exact_bw` (structural Baugh-Wooley) are both reported. The fair
  "cost of exactness" reference for `mul8s_tbw` is `tbw_k0_none`, which uses
  the same 9-row tree.
* **Approximate vs DSP.** The comparison with `exact_dsp` shows the LUT cost
  of not using a DSP slice. It is not evidence that LUT multipliers beat DSPs.
  The device has 90 DSP48E1 slices, and LUT multipliers matter when those run
  out.

## 7. Running the sweep (owner's machine)

```bash
source /tools/Xilinx/Vivado/2024.1/settings64.sh    # adjust to the install path
git pull && git checkout claude/determined-sagan-44ug5z
make fpga FPGA_JOBS=2                  # or: python3 fpga/scripts/run_sweep.py --jobs 2
```

* Standard library Python >= 3.9 only, so no virtual environment is needed.
* `FPGA_JOBS` parallel Vivado processes, each limited to 2 threads. Allow
  about 2-3 GB RAM per job.
* Subset: `python3 fpga/scripts/run_sweep.py --only 'exact_|tbw_k4_'`.
* `--dry-run` prints the Vivado commands without running them.
* The script exits non-zero and lists every variant with an issue: failed
  run, timing never met, unexpected DSP mapping, or incomplete report parsing.

## 8. What is committed

| Path | Content |
|---|---|
| `results/fpga/fpga_results.csv` | One row per variant (utilization, power, Fmax, status) |
| `results/fpga/fpga_passes.csv` | Every Vivado run of the Fmax search |
| `results/fpga/run_manifest.json` | Vivado version, part, settings, git commit, host |
| `results/fpga/reports/<variant>/` | Pass-1 utilization and power reports, plus the critical path and timing summary of the best passing run |
| `results/fpga/fpga_summary.md`, `results/fpga/figures/` | Generated by `make fpga-summary` |

Raw run directories (`build/fpga/`) are not committed.

## 9. Flow testing without Vivado

`tests/test_fpga_flow.py` runs the real `run_sweep.py` and `run_ooc.tcl`
against a mock Vivado (`tests/fpga_mock/`, stub commands under `tclsh`).
This checks Tcl syntax, argument and generic forwarding, `-max_dsp` handling,
report parsing, the Fmax search and the summary script in CI. The mock
produces synthetic numbers, which are never published.
