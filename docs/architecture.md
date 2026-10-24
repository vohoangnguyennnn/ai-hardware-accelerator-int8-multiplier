# Microarchitecture

## 1. Behavioral baseline: `mul8s_behav`

`assign p = a * b;` with both operands declared `signed`. In SystemVerilog the
expression is signed only if *every* operand is signed, and it is evaluated at
the width of the left-hand side (16 bits) after sign extension. Losing
signedness on one operand, for example through a part-select, a concatenation
or `$unsigned()`, silently turns it into an unsigned multiply. The mutation
check `behav_unsigned` confirms the testbench catches this.

The RTL carries no mapping attributes. Whether the multiply becomes a
DSP48E1 or LUT logic is a decision of the FPGA flow (v0.3.0), so the same
source serves both the "exact DSP" and the "exact LUT" baselines.

## 2. Modified Baugh-Wooley: `mul8s_bw`

### 2.1 Derivation

For W = 8 bit two's complement operands:

```
A = -a7*2^7 + sum_{i=0..6} a_i*2^i          B = -b7*2^7 + sum_{j=0..6} b_j*2^j

A*B =   sum_{i<7, j<7} a_i b_j 2^(i+j)      (positive)
      + a7 b7 2^14                          (positive)
      - sum_{j<7}      a7 b_j 2^(7+j)       (negative)
      - sum_{i<7}      a_i b7 2^(7+i)       (negative)
```

Each negative term is rewritten with `-x*2^k = (1 - x)*2^k - 2^k = ~x*2^k - 2^k`.
Applied to both negative sums (7 terms each, columns 7..13):

```
- sum_{k<7} x_k 2^(7+k) = sum_{k<7} ~x_k 2^(7+k) - (2^14 - 2^7)
```

The two sums contribute the constant `-2*(2^14 - 2^7) = -2^15 + 2^8`. Modulo
2^16, `-2^15 == +2^15`, which gives the modified Baugh-Wooley form:

```
P == sum_{i<7,j<7} a_i b_j 2^(i+j) + a7 b7 2^14
   + sum_{k<7} ( ~(a7 b_k) + ~(a_k b7) ) 2^(7+k)
   + 2^8 + 2^15                                   (mod 2^16)
```

Because the exact product always fits in 16 signed bits (see
[spec.md](spec.md)), the result modulo 2^16 *is* the exact product.
`models/bw_model.py` implements this matrix bit by bit, and
`tests/test_models.py` checks it against Python integer multiplication for
all 65,536 pairs.

### 2.2 Partial-product matrix

64 partial-product bits (50 AND, 14 NAND) and two constant ones. The
constants sit in otherwise empty positions, so the matrix needs only
eight rows:

```
col:   15  14  13  12  11  10   9   8   7   6   5   4   3   2   1   0
R0                                  1 n70 p60 p50 p40 p30 p20 p10 p00
R1                                n71 p61 p51 p41 p31 p21 p11 p01
R2                            n72 p62 p52 p42 p32 p22 p12 p02
R3                        n73 p63 p53 p43 p33 p23 p13 p03
R4                    n74 p64 p54 p44 p34 p24 p14 p04
R5                n75 p65 p55 p45 p35 p25 p15 p05
R6            n76 p66 p56 p46 p36 p26 p16 p06
R7      1 p77 n67 n57 n47 n37 n27 n17 n07

p_ij = a_i & b_j        n_ij = ~(a_i & b_j)
```

Row `j` holds `a_i b_j` at column `i + j`. A term is inverted exactly when one
of `i`, `j` equals 7. The highest column holding partial products is 7
(eight bits), and column 8 also has eight bits once its constant is included,
so a Wallace or Dadda reduction needs four 3:2 levels (8 -> 6 -> 4 -> 3 -> 2).

RTL mapping (`rtl/bw_ppgen8.sv`): one generate loop produces the `pp` bits,
choosing AND or NAND per position from the same `(i == 7) != (j == 7)` rule.
Each row is shifted to column `j`, and the constants are ORed into rows 0
and 7. These are empty positions, so OR is the same as addition here.

### 2.3 Reduction tree

The reduction works on whole rows. `rtl/csa3to2.sv` is a row of full adders:
`sum = x ^ y ^ z`, and `carry = maj(x, y, z) << 1`. Constant-zero
input bits reduce a full adder to a half adder or a wire during synthesis.

| Level | Carry-save additions | Rows passed through | Rows out |
|---|---|---|---|
| L1 | `{r0, r1, r2}`, `{r3, r4, r5}` | `r6`, `r7` | 6 |
| L2 | `{l1_s0, l1_c0, l1_s1}`, `{l1_c1, r6, r7}` | none | 4 |
| L3 | `{l2_s0, l2_c0, l2_s1}` | `l2_c1` | 3 |
| L4 | `{l3_s, l3_c, l2_c1}` | none | 2 |
| CPA | `p = l4_s + l4_c` | | |

Every CSA drops the carry out of bit 15. That carry has weight 2^16 and
vanishes modulo 2^16, so dropping it is exact. The `csa_unshifted_carry`
and `tree_row_dup` mutants confirm the testbench is sensitive to errors
in this tree.

A bit-level Dadda tree can use fewer adder cells than this row-level tree.
The row-level form was chosen because it is easy to review, and because
truncation only needs partial-product bits forced to zero, with no rewiring
(see [approximation.md](approximation.md)).

### 2.4 Final carry-propagate adder

The two remaining rows are added with a single `+`. This is a deliberate
mapping choice. On 7-series devices, Vivado implements a two-operand adder
on the dedicated CARRY4 chain, which is faster than an adder built from
explicit full-adder cells in LUTs.

### 2.5 Expected FPGA behaviour (to be measured in v0.3.0)

* The combinational path is the AND/NAND generation, four carry-save levels
  and a carry chain of about 14 active bits. The partial-product gates can
  merge into the first LUT level.
* A LUT6 can implement a full adder, or a 3:2 cell together with neighbouring
  logic. Vivado flattens and re-optimizes the tree, so the final netlist need
  not mirror this structure.
* Whether `mul8s_bw` uses more or fewer LUTs than Vivado's own LUT mapping
  of `mul8s_behav` is an open question for v0.3.0. Neither outcome is assumed.

## 3. References

1. C. R. Baugh and B. A. Wooley, "A two's complement parallel array
   multiplication algorithm," *IEEE Trans. Computers*, vol. C-22, no. 12,
   pp. 1045-1047, Dec. 1973.
2. C. S. Wallace, "A suggestion for a fast multiplier," *IEEE Trans.
   Electronic Computers*, vol. EC-13, no. 1, pp. 14-17, Feb. 1964.
3. L. Dadda, "Some schemes for parallel multipliers," *Alta Frequenza*,
   vol. 34, pp. 349-356, 1965.
4. B. Parhami, *Computer Arithmetic: Algorithms and Hardware Designs*,
   2nd ed. Oxford University Press, 2010.
5. AMD/Xilinx, *7 Series FPGAs Configurable Logic Block User Guide* (UG474).
