# Arithmetic and Interface Specification

This document is the single source of truth for the arithmetic behaviour and
interfaces of the multiplier IP.

## 1. Arithmetic

| Property | Value |
|---|---|
| Operand representation | Two's complement, signed |
| Operand width | 8 bits (`a`, `b`), range [-128, 127] |
| Product width | 16 bits (`p`), two's complement |
| Exact product range | [-16256, 16384] |
| Overflow | Not possible; `p` holds the full mathematical product |
| Unsigned / mixed-sign operands | Not supported (possible later extension) |

The extremes are `(-128) x 127 = -16256` and `(-128) x (-128) = 16384 = 0x4000`.
16384 lies outside the 15-bit signed range [-16384, 16383], so 16 bits is the
minimum product width. For every other operand pair `p[15] == p[14]`; this
property is checked by `tests/test_models.py`. Narrowing the product to
15 bits would therefore be wrong for exactly one input pair.

Some INT8 quantization schemes restrict operands to the symmetric range
[-127, 127]. This IP does not rely on that: -128 is fully supported.

## 2. Interface

All multiplier variants share one port list, so they are interchangeable in
the testbench and in the FPGA benchmark wrapper.

| Port | Direction | Type | Description |
|---|---|---|---|
| `a` | input | `logic signed [7:0]` | Multiplicand |
| `b` | input | `logic signed [7:0]` | Multiplier |
| `p` | output | `logic signed [15:0]` | Product |

Timing: purely combinational, latency 0, no clock and no reset. Registered or
pipelined wrappers, if added, are separate modules that document their own
latency, throughput and reset behaviour.

## 3. Variants

| Module | Arithmetic | Architecture | Status |
|---|---|---|---|
| `mul8s_behav` | Exact | Behavioral `a * b`; mapping chosen by the FPGA flow | Implemented (v0.1.0) |
| `mul8s_bw` | Exact | Structural modified Baugh-Wooley, row-level carry-save tree, single CPA | Implemented (v0.1.0) |
| `mul8s_tbw` | Approximate | Truncated Baugh-Wooley, parameters `TRUNC_COLS`, `COMP_EN`, `ZERO_GATE` | Implemented (v0.2.0) |

## 4. Approximation semantics

`mul8s_tbw` removes the partial-product bits of the `K` least-significant
columns of the Baugh-Wooley matrix and optionally compensates the resulting
bias. The bit-accurate definition, which the RTL must match exactly, is:

```
P~(A, B) = A*B - L_K(A, B) + C_K,     L_K = sum_{i+j<K} a_i b_j 2^(i+j)
C_K      = COMP_EN ? round(((K-1) 2^K + 1) / 4) : 0
if ZERO_GATE and (A == 0 or B == 0):  P~ = 0
```

| Parameter | Type | Range | Default |
|---|---|---|---|
| `TRUNC_COLS` (K) | `int` | 0..7; out-of-range values are rejected at elaboration | 4 |
| `COMP_EN` | `bit` | 0/1 | 1 |
| `ZERO_GATE` | `bit` | 0/1 | 1 |

* `K = 0` is bit-identical to the exact product for every `COMP_EN` /
  `ZERO_GATE` setting.
* `K <= 7` guarantees that only unsigned AND terms are removed, so the
  Baugh-Wooley signed correction stays intact. Column 7 holds `~(a7 b0)`
  and `~(a0 b7)`.
* The result always lies within the 16-bit signed range (checked by the
  model), so no wrap-around occurs.
* With `COMP_EN = 1` and `ZERO_GATE = 0`, a zero operand returns `C_K`
  rather than 0.
* The approximation is intentional and specified by `models/approx_tbw.py`.
  Any RTL deviation from that model is a functional bug.

Derivation, hardware mapping and measured behaviour:
[approximation.md](approximation.md).

## 5. Error metrics

ER, MAE, NMED (normalised by 2^14), MRED (over pairs with `P != 0`), bias
and MSE, computed exhaustively over all 65,536 pairs. Worst-case error is
intentionally not reported. Definitions and conventions:
[error_metrics.md](error_metrics.md).

## 6. FPGA target

| Item | Value | Source |
|---|---|---|
| Board | MicroPhase A7-Lite 35T | Project owner |
| Device | XC7A35T-2FGG484 (Artix-7, speed grade -2) | Chip marking, confirmed by project owner |
| Vivado part string | `xc7a35tfgg484-2` | Derived from the device marking above |
| DSP48E1 slices | 90 | MicroPhase A7-Lite reference manual |
| Board clock | 50 MHz oscillator, pin J19 | MicroPhase A7-Lite reference manual |
| Toolchain | AMD Vivado 2024.1 | Project owner |

The vendor manual lists the part both as `XC7A35T-2FGG484` and as
`XC7A35T-2FGG484L`. The marking on the board used in this project reads
`XC7A35T-2FGG484`, so the standard -2 speed grade (not the low-voltage -2L
grade) is the target for all timing results.
PPA measurements are out-of-context Vivado runs with registered inputs and
outputs, as defined in [fpga_methodology.md](fpga_methodology.md).
