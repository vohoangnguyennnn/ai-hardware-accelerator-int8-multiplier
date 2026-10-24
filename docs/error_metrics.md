# Error Metrics

Implementation: `models/metrics.py`. Results: `results/error_metrics.csv`,
produced by `make results`.

## Definitions

For every operand pair `(A, B)`, the error is
`e(A, B) = P~(A, B) - P(A, B)`, where `P` is the exact product. Unless stated
otherwise, all averages are taken over the full input space: N = 65,536 pairs,
each pair weighted equally (uniform operand distribution).

| Metric | Definition | Notes |
|---|---|---|
| ER (error rate) | `#{e != 0} / N` | Counts every non-zero error, however small |
| MAE (mean absolute error, also called MED) | `(1/N) sum abs(e)` | In LSBs of the 16-bit product |
| NMED (normalised MED) | `MAE / 16384` | Normalised by `max abs(P) = (-128)^2 = 2^14`. Literature on unsigned multipliers often normalises by `(2^n - 1)^2` instead, so compare values with care |
| MRED (mean relative error distance) | `mean over P != 0 of abs(e) / abs(P)` | 511 pairs have `P = 0` (`A = 0` or `B = 0`), where relative error is undefined. They are **excluded** from MRED |
| Bias (mean signed error) | `(1/N) sum e` | Negative means systematic under-estimation |
| MSE (mean squared error) | `(1/N) sum e^2` | Weights large errors more heavily; relevant for accumulated noise |

Pairs with `P = 0` are reported separately as `n_zero_exact` (always 511) and
`n_zero_exact_wrong` (how many of them return a non-zero result). This
replaces the information MRED cannot express.

Worst-case error (WCE) is intentionally not part of the reported metric set.

## Breakdown by operand sign

`results/error_by_quadrant.csv` repeats MAE, bias and MRED for the subsets
`a>0,b>0`, `a>0,b<0`, `a<0,b>0`, `a<0,b<0` and "zero operand". This shows
whether the approximation treats signs differently.

## Reproducibility

All metrics come from the bit-accurate model, which the RTL matches exactly
for every configuration. The computation is deterministic. `make check-results`
regenerates the CSV files and fails if they differ from the committed copies.
