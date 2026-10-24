// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Vo Hoang Nguyen
//
// mul8s_behav - Behavioral exact signed INT8 multiplier.
//
// Arithmetic and synthesis baseline. The multiplication is left to the
// synthesis tool; DSP vs. LUT mapping is selected by the FPGA flow, not here.
//
// Interface (shared by every mul8s_* variant):
//   a, b : signed two's complement, [-128, 127]
//   p    : full-precision signed product, [-16256, 16384]; no overflow
// Purely combinational, latency 0, no clock or reset.

module mul8s_behav (
    input  logic signed [7:0]  a,
    input  logic signed [7:0]  b,
    output logic signed [15:0] p
);

  // Both operands are signed, so the expression is signed and evaluated at
  // the 16-bit width of the left-hand side (operands sign-extended first).
  assign p = a * b;

endmodule
