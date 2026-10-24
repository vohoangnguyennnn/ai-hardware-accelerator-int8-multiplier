// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Vo Hoang Nguyen
//
// tb_bench_top - Clocked testbench for the FPGA benchmark wrapper.
//
// Streams all 65,536 operand pairs into fpga/rtl/bench_top.sv, one pair per
// clock, and checks p_out against the expected-value file exactly LATENCY
// cycles later. This verifies the wrapper that Vivado implements: variant
// selection, parameter forwarding, 2-cycle latency and full throughput.
//
// Parameters mirror bench_top. Run-time option: +VECTORS=<file>.

module tb_bench_top #(
    parameter int VARIANT    = 2,
    parameter int TRUNC_COLS = 0,
    parameter int COMP_EN    = 0,
    parameter int ZERO_GATE  = 0
);

  localparam int NUM_PAIRS    = 1 << 16;
  localparam int LATENCY      = 2;
  localparam int MAX_REPORTED = 16;

  logic               clk = 1'b0;
  logic signed [7:0]  a_in, b_in;
  logic signed [15:0] p_out;

  logic        [15:0] expected_mem[NUM_PAIRS];
  int                 n_checked;
  int                 n_failed;

  bench_top #(
      .VARIANT   (VARIANT),
      .TRUNC_COLS(TRUNC_COLS),
      .COMP_EN   (COMP_EN),
      .ZERO_GATE (ZERO_GATE)
  ) u_dut (
      .clk  (clk),
      .a_in (a_in),
      .b_in (b_in),
      .p_out(p_out)
  );

  always #5 clk <= ~clk;

  initial begin
    string vectors;
    int    fd;

    if (!$value$plusargs("VECTORS=%s", vectors)) $fatal(1, "TB error: +VECTORS=<file> is required");
    fd = $fopen(vectors, "r");
    if (fd == 0) $fatal(1, "TB error: cannot open vector file '%s'", vectors);
    $fclose(fd);
    $readmemh(vectors, expected_mem);
    $display("tb_bench_top: VARIANT=%0d TRUNC_COLS=%0d COMP_EN=%0d ZERO_GATE=%0d vectors=%s",
             VARIANT, TRUNC_COLS, COMP_EN, ZERO_GATE, vectors);

    a_in = '0;
    b_in = '0;
    // Cycle k drives pair k; its result must appear on p_out after cycle k + LATENCY.
    for (int k = 0; k < NUM_PAIRS + LATENCY; k++) begin
      if (k < NUM_PAIRS) begin
        a_in = k[15:8];
        b_in = k[7:0];
      end
      @(posedge clk);
      #1;
      if (k >= LATENCY - 1 && k - (LATENCY - 1) < NUM_PAIRS) begin
        int unsigned idx;
        idx = k - (LATENCY - 1);
        n_checked++;
        if (p_out !== expected_mem[idx]) begin
          n_failed++;
          if (n_failed <= MAX_REPORTED)
            $display("MISMATCH pair %0d: a=%0d b=%0d expected=0x%04h got=0x%04h",
                     idx, $signed(idx[15:8]), $signed(idx[7:0]), expected_mem[idx], p_out);
        end
      end
    end

    if (n_checked != NUM_PAIRS) $fatal(1, "TB error: checked %0d results, expected %0d", n_checked, NUM_PAIRS);
    if (n_failed == 0) begin
      $display("tb_bench_top: %0d/%0d results correct with %0d-cycle latency", NUM_PAIRS, NUM_PAIRS, LATENCY);
      $display("PASS: bench_top VARIANT=%0d", VARIANT);
      $finish;
    end else begin
      $fatal(1, "FAIL: bench_top VARIANT=%0d, %0d of %0d results mismatched", VARIANT, n_failed, n_checked);
    end
  end

endmodule
