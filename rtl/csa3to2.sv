// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Vo Hoang Nguyen
//
// csa3to2 - Row-level 3:2 carry-save adder (a row of full adders).
//
// Reduces three WIDTH-bit operands to a sum word and a carry word such that
//   x + y + z == sum + carry   (mod 2^WIDTH)
// The carry word is already weighted (shifted left by one). The carry out of
// bit WIDTH-1 is discarded: the multiplier datapath is defined modulo 2^16,
// see docs/architecture.md. Constant-zero input bits are pruned by synthesis.

module csa3to2 #(
    parameter int unsigned WIDTH = 16
) (
    input  logic [WIDTH-1:0] x,
    input  logic [WIDTH-1:0] y,
    input  logic [WIDTH-1:0] z,
    output logic [WIDTH-1:0] sum,
    output logic [WIDTH-1:0] carry
);

  logic [WIDTH-1:0] majority;

  assign sum      = x ^ y ^ z;
  assign majority = (x & y) | (x & z) | (y & z);

  // majority[WIDTH-1] has weight 2^WIDTH and is intentionally dropped.
  /* verilator lint_off UNUSEDSIGNAL */
  logic unused_carry_out;
  assign unused_carry_out = majority[WIDTH-1];
  /* verilator lint_on UNUSEDSIGNAL */

  assign carry = {majority[WIDTH-2:0], 1'b0};

endmodule
