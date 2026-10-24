# Arithmetic and Interface Specification

This document is the single source of truth for the arithmetic behaviour and
interfaces of the multiplier IP. Items marked **Planned** are specified
direction only and are not yet implemented.

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
| `mul8s_tbw` | Approximate | Truncated Baugh-Wooley | **Planned** (v0.2.0) |

## 4. Approximation semantics (Planned, v0.2.0)

The planned approximate variant removes the partial-product bits of the
`K` least-significant columns of the Baugh-Wooley matrix
(see [architecture.md](architecture.md)):

```
P~(A, B) = ( sum over i+j >= K of w_ij * pp_ij  +  2^8  +  2^15  +  C ) mod 2^16
```

* `K = TRUNC_COLS`, restricted to `0 <= K <= 7`. Column 7 holds the inverted
  terms `~(a7 b0)` and `~(a0 b7)`, which are part of the signed correction; a
  Python pre-study showed that truncating it (`K = 8`) makes `0 x B` non-zero
  even without compensation.
* `K = 0` must be bit-identical to the exact multiplier.
* The compensation constant `C` and an optional zero-operand gate are under
  investigation. A constant `C != 0` makes `0 x B = C`, which matters for
  sparse (ReLU, zero-padded) CNN data. The selected option will be justified
  with measured error metrics and FPGA results.
* The approximation is intentional and specified by a bit-accurate model.
  Any RTL deviation from that model is a functional bug.

## 5. Error metrics (Planned, v0.2.0)

With `e(A, B) = P~(A, B) - P(A, B)` over all 65,536 pairs (uniform inputs):

| Metric | Definition |
|---|---|
| ER | fraction of pairs with `e != 0` |
| MAE | mean of `abs(e)` |
| NMED | MAE / 16384, normalised by the largest exact magnitude `max abs(P)` |
| MRED | mean of `abs(e) / abs(P)` over pairs with `P != 0` (511 pairs with `P = 0` are excluded and reported separately) |
| Bias | mean of `e` |
| MSE | mean of `e^2` |

Worst-case error (WCE) is intentionally not part of the reported metric set.

## 6. FPGA target

| Item | Value | Source |
|---|---|---|
| Board | MicroPhase A7-Lite 35T | Project owner |
| Device | XC7A35T-2FGG484 (Artix-7, speed grade -2) | MicroPhase A7-Lite reference manual |
| Vivado part string | `xc7a35tfgg484-2` | Derived from the device marking above |
| DSP48E1 slices | 90 | MicroPhase A7-Lite reference manual |
| Board clock | 50 MHz oscillator, pin J19 | MicroPhase A7-Lite reference manual |
| Toolchain | AMD Vivado 2024.1 | Project owner |

The vendor manual also lists the part as `XC7A35T-2FGG484L`, with an extra suffix.
Confirm the part against the marking on the chip before the v0.3.0 runs.
PPA measurements are planned as out-of-context runs with registered inputs
and outputs; the methodology will be documented in `docs/fpga_methodology.md`
(v0.3.0).
