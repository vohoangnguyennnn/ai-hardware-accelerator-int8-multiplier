// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Vo Hoang Nguyen
//
// mul8s_bw - Structural exact signed INT8 multiplier (modified Baugh-Wooley).
//
// Datapath:
//   bw_ppgen8 : 8 partial-product rows (AND/NAND + correction constants)
//   L1..L4    : row-level 3:2 carry-save reduction, 8 -> 6 -> 4 -> 3 -> 2
//   CPA       : one 16-bit carry-propagate adder (maps to the FPGA carry chain)
// All arithmetic is modulo 2^16; the 16-bit result is the exact product.
//
// Interface identical to mul8s_behav: combinational, latency 0.

module mul8s_bw (
    input  logic signed [7:0]  a,
    input  logic signed [7:0]  b,
    output logic signed [15:0] p
);

  localparam int unsigned PW = 16;

  logic [8*PW-1:0] rows;

  bw_ppgen8 u_ppgen (
      .a   (a),
      .b   (b),
      .rows(rows)
  );

  logic [PW-1:0] r0, r1, r2, r3, r4, r5, r6, r7;
  assign {r7, r6, r5, r4, r3, r2, r1, r0} = rows;

  // ---------------------------------------------------------------------------
  // Level 1: 8 -> 6 rows
  // ---------------------------------------------------------------------------
  logic [PW-1:0] l1_s0, l1_c0, l1_s1, l1_c1;

  csa3to2 #(.WIDTH(PW)) u_l1_0 (.x(r0), .y(r1), .z(r2), .sum(l1_s0), .carry(l1_c0));
  csa3to2 #(.WIDTH(PW)) u_l1_1 (.x(r3), .y(r4), .z(r5), .sum(l1_s1), .carry(l1_c1));

  // ---------------------------------------------------------------------------
  // Level 2: 6 -> 4 rows  {l1_s0, l1_c0, l1_s1, l1_c1, r6, r7}
  // ---------------------------------------------------------------------------
  logic [PW-1:0] l2_s0, l2_c0, l2_s1, l2_c1;

  csa3to2 #(.WIDTH(PW)) u_l2_0 (.x(l1_s0), .y(l1_c0),   .z(l1_s1),   .sum(l2_s0), .carry(l2_c0));
  csa3to2 #(.WIDTH(PW)) u_l2_1 (.x(l1_c1), .y(r6),      .z(r7),      .sum(l2_s1), .carry(l2_c1));

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
  // Final carry-propagate addition. Written as '+' on purpose so the FPGA
  // tool maps it onto the dedicated carry chain (CARRY4 on 7-series).
  // ---------------------------------------------------------------------------
  assign p = $signed(l4_s + l4_c);

endmodule
