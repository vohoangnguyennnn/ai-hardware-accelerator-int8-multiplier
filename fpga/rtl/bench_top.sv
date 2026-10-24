// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Vo Hoang Nguyen
//
// bench_top - FPGA benchmark wrapper: input registers -> multiplier -> output
// register, so that every variant is measured as the same register-to-register
// path under the same clock constraint (docs/fpga_methodology.md).
//
//   VARIANT 0 : mul8s_behav (exact, behavioral; LUT runs use -max_dsp 0)
//   VARIANT 1 : mul8s_dsp   (exact, DSP48E1 requested)
//   VARIANT 2 : mul8s_bw    (exact, structural Baugh-Wooley)
//   VARIANT 3 : mul8s_tbw   (approximate; TRUNC_COLS / COMP_EN / ZERO_GATE)
//
// Latency: 2 clock cycles from a_in/b_in to p_out. Throughput: one product
// per cycle. Data registers have no reset (none is needed for a benchmark
// datapath, and a reset would add unrelated logic). Parameters are plain
// integers so that Vivado's synth_design -generic can set them directly.

module bench_top #(
    parameter int VARIANT    = 2,
    parameter int TRUNC_COLS = 0,
    parameter int COMP_EN    = 0,
    parameter int ZERO_GATE  = 0
) (
    input  logic               clk,
    input  logic signed [7:0]  a_in,
    input  logic signed [7:0]  b_in,
    output logic signed [15:0] p_out
);

  localparam int VAR_BEHAV = 0;
  localparam int VAR_DSP   = 1;
  localparam int VAR_BW    = 2;
  localparam int VAR_TBW   = 3;

  logic signed [7:0]  a_q, b_q;
  logic signed [15:0] p_d, p_q;

  always_ff @(posedge clk) begin
    a_q <= a_in;
    b_q <= b_in;
    p_q <= p_d;
  end

  assign p_out = p_q;

  if (VARIANT == VAR_BEHAV) begin : g_behav
    mul8s_behav u_mul (.a(a_q), .b(b_q), .p(p_d));
  end else if (VARIANT == VAR_DSP) begin : g_dsp
    mul8s_dsp u_mul (.a(a_q), .b(b_q), .p(p_d));
  end else if (VARIANT == VAR_BW) begin : g_bw
    mul8s_bw u_mul (.a(a_q), .b(b_q), .p(p_d));
  end else if (VARIANT == VAR_TBW) begin : g_tbw
    mul8s_tbw #(
        .TRUNC_COLS(TRUNC_COLS),
        .COMP_EN   (COMP_EN != 0),
        .ZERO_GATE (ZERO_GATE != 0)
    ) u_mul (
        .a(a_q),
        .b(b_q),
        .p(p_d)
    );
  end else begin : g_bad_variant
    $error("bench_top: unsupported VARIANT=%0d", VARIANT);
  end

endmodule
