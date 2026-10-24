// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Vo Hoang Nguyen
//
// bw_ppgen8 - Modified Baugh-Wooley partial-product generator, 8x8 signed.
//
// Produces eight 16-bit row words whose sum modulo 2^16 equals a * b.
// Row j carries p_ij = a[i] & b[j] at column i+j (i = 0..7), where the
// terms with exactly one sign bit (i == 7 xor j == 7) are inverted (NAND).
// The Baugh-Wooley correction constant 2^8 + 2^15 is placed in otherwise
// empty slots: row 0 column 8 and row 7 column 15.
// Row j is returned in rows[16*j +: 16] (flat bus for tool portability).
// Derivation: docs/architecture.md, section "Modified Baugh-Wooley".

module bw_ppgen8 (
    input  logic [7:0]   a,
    input  logic [7:0]   b,
    output logic [127:0] rows
);

  localparam int W  = 8;
  localparam int PW = 2 * W;
  // -2 * (2^(2W-2) - 2^(W-1)) == 2^(2W-1) + 2^W  (mod 2^(2W))
  localparam int CORR_COL_LO = W;       // 2^8
  localparam int CORR_COL_HI = PW - 1;  // 2^15
  localparam logic [PW-1:0] CORR_ROW0 = PW'(1) << CORR_COL_LO;
  localparam logic [PW-1:0] CORR_ROW7 = PW'(1) << CORR_COL_HI;

  // pp[W*j + i] = a_i * b_j (inverted where its weight is negative)
  logic [W*W-1:0] pp;

  for (genvar j = 0; j < W; j++) begin : g_row
    for (genvar i = 0; i < W; i++) begin : g_col
      if ((i == W - 1) != (j == W - 1)) begin : g_nand
        assign pp[W*j+i] = ~(a[i] & b[j]);  // negatively weighted term
      end else begin : g_and
        assign pp[W*j+i] = a[i] & b[j];
      end
    end

    // Align row j to column j.
    logic [PW-1:0] placed;
    assign placed = PW'(pp[W*j +: W]) << j;

    if (j == 0) begin : g_corr_lo
      assign rows[PW*j +: PW] = placed | CORR_ROW0;
    end else if (j == W - 1) begin : g_corr_hi
      assign rows[PW*j +: PW] = placed | CORR_ROW7;
    end else begin : g_plain
      assign rows[PW*j +: PW] = placed;
    end
  end

endmodule
