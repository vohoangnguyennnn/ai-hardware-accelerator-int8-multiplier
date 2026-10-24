// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Vo Hoang Nguyen
//
// mul8s_tbw - Approximate signed INT8 multiplier: truncated Baugh-Wooley.
//
// Arithmetic (bit-accurate model: models/approx_tbw.py):
//   p = A*B - L_K(A, B) + C,   L_K = sum_{i+j<K} a_i b_j 2^(i+j)
//   C = COMP_EN ? round(((K-1) 2^K + 1) / 4) : 0     (mean of L_K, uniform inputs)
//   ZERO_GATE: p = 0 whenever a == 0 or b == 0
// with K = TRUNC_COLS in [0, 7]. K = 0 is the exact product.
//
// Datapath:
//   bw_ppgen8 #(K) : 8 partial-product rows, low K columns removed
//   row 8          : compensation constant C (all-zero when COMP_EN = 0)
//   L1..L4         : row-level 3:2 carry-save reduction, 9 -> 6 -> 4 -> 3 -> 2
//   CPA            : one 16-bit carry-propagate adder
//   zero gate      : optional output forcing (ZERO_GATE = 1)
//
// Interface identical to mul8s_behav / mul8s_bw: combinational, latency 0.
// Note: the 9-row tree differs from the 8-row tree of mul8s_bw, so the
// like-for-like exact reference for hardware comparisons is mul8s_tbw with
// TRUNC_COLS = 0 and COMP_EN = 0.

// Defaults: a mid-range operating point that keeps 0 * x = 0. Final
// recommended settings depend on the FPGA results (v0.3.0).
module mul8s_tbw #(
    parameter int TRUNC_COLS = 4,
    parameter bit COMP_EN    = 1'b1,
    parameter bit ZERO_GATE  = 1'b1
) (
    input  logic signed [7:0]  a,
    input  logic signed [7:0]  b,
    output logic signed [15:0] p
);

  localparam int PW = 16;
  // Rounded mean of the removed bits; integer form of round(((K-1) 2^K + 1) / 4).
  localparam int COMP_VALUE = (COMP_EN && TRUNC_COLS > 0) ? (((TRUNC_COLS - 1) << TRUNC_COLS) + 3) / 4 : 0;
  localparam logic [PW-1:0] COMP_ROW = PW'(COMP_VALUE);

  logic [8*PW-1:0] rows;

  bw_ppgen8 #(
      .TRUNC_COLS(TRUNC_COLS)
  ) u_ppgen (
      .a   (a),
      .b   (b),
      .rows(rows)
  );

  logic [PW-1:0] r0, r1, r2, r3, r4, r5, r6, r7, r8;
  assign {r7, r6, r5, r4, r3, r2, r1, r0} = rows;
  assign r8 = COMP_ROW;

  // ---------------------------------------------------------------------------
  // Level 1: 9 -> 6 rows
  // ---------------------------------------------------------------------------
  logic [PW-1:0] l1_s0, l1_c0, l1_s1, l1_c1, l1_s2, l1_c2;

  csa3to2 #(.WIDTH(PW)) u_l1_0 (.x(r0), .y(r1), .z(r2), .sum(l1_s0), .carry(l1_c0));
  csa3to2 #(.WIDTH(PW)) u_l1_1 (.x(r3), .y(r4), .z(r5), .sum(l1_s1), .carry(l1_c1));
  csa3to2 #(.WIDTH(PW)) u_l1_2 (.x(r6), .y(r7), .z(r8), .sum(l1_s2), .carry(l1_c2));

  // ---------------------------------------------------------------------------
  // Level 2: 6 -> 4 rows
  // ---------------------------------------------------------------------------
  logic [PW-1:0] l2_s0, l2_c0, l2_s1, l2_c1;

  csa3to2 #(.WIDTH(PW)) u_l2_0 (.x(l1_s0), .y(l1_c0), .z(l1_s1), .sum(l2_s0), .carry(l2_c0));
  csa3to2 #(.WIDTH(PW)) u_l2_1 (.x(l1_c1), .y(l1_s2), .z(l1_c2), .sum(l2_s1), .carry(l2_c1));

  // ---------------------------------------------------------------------------
  // Level 3: 4 -> 3 rows  {l2_s0, l2_c0, l2_s1, l2_c1}
  // ---------------------------------------------------------------------------
  logic [PW-1:0] l3_s, l3_c;

  csa3to2 #(.WIDTH(PW)) u_l3 (.x(l2_s0), .y(l2_c0), .z(l2_s1), .sum(l3_s), .carry(l3_c));

  // ---------------------------------------------------------------------------
  // Level 4: 3 -> 2 rows  {l3_s, l3_c, l2_c1}
  // ---------------------------------------------------------------------------
  logic [PW-1:0] l4_s, l4_c;

  csa3to2 #(.WIDTH(PW)) u_l4 (.x(l3_s), .y(l3_c), .z(l2_c1), .sum(l4_s), .carry(l4_c));

  // ---------------------------------------------------------------------------
  // Final carry-propagate addition (maps to the FPGA carry chain)
  // ---------------------------------------------------------------------------
  logic [PW-1:0] sum;
  assign sum = l4_s + l4_c;

  // ---------------------------------------------------------------------------
  // Optional zero gate: restores 0 * x = 0, which the compensation constant
  // otherwise breaks (p would equal C for every zero operand).
  // ---------------------------------------------------------------------------
  if (ZERO_GATE) begin : g_zero_gate
    logic zero_operand;
    assign zero_operand = (a == '0) || (b == '0);
    assign p = zero_operand ? '0 : $signed(sum);
  end else begin : g_no_zero_gate
    assign p = $signed(sum);
  end

endmodule
