// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Vo Hoang Nguyen
//
// mul8s_dsp - Exact signed INT8 multiplier, DSP-mapped FPGA baseline.
//
// Same arithmetic as rtl/mul8s_behav.sv. The only difference is the
// Vivado USE_DSP attribute, which requests a DSP48E1 instead of leaving the
// choice to the synthesis heuristics. It lives under fpga/ because it is a
// tool-specific mapping variant, not part of the portable IP. It is verified
// exhaustively like every other variant (make sim-mul8s_dsp).

(* use_dsp = "yes" *)
module mul8s_dsp (
    input  logic signed [7:0]  a,
    input  logic signed [7:0]  b,
    output logic signed [15:0] p
);

  assign p = a * b;

endmodule
