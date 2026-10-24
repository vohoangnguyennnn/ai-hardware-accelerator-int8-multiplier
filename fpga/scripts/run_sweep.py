#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Vivado out-of-context PPA sweep over every multiplier variant.

For each variant, fpga/scripts/run_ooc.tcl implements fpga/rtl/bench_top.sv
(registered inputs -> multiplier -> registered output):

  pass 1  at the common base period (default 10.000 ns). This pass provides
          utilization, power and the timing of a relaxed run, measured under
          identical constraints for every variant.
  pass 2+ at the period achieved in the previous pass (period - WNS, rounded
          up to 0.01 ns): tighter after a passing run, looser after a failing
          one. The search stops when a passing run has < 3% slack, when a
          period repeats, or after --max-passes runs. Fmax is reported only
          from the tightest run with WNS >= 0 and no routing errors.

Results:
  results/fpga/fpga_results.csv      one row per variant
  results/fpga/fpga_passes.csv       every Vivado run
  results/fpga/run_manifest.json     tool versions, part, git commit, settings
  results/fpga/reports/<variant>/    utilization/power (pass 1), critical path
                                     and timing summary (best passing run)
Raw runs: build/fpga/<variant>/pass<N>/

Requires Python >= 3.9 (standard library only) and vivado in PATH
(source <Vivado>/settings64.sh first).

Usage:
  python3 fpga/scripts/run_sweep.py --jobs 2
  python3 fpga/scripts/run_sweep.py --only 'exact_|tbw_k4_' --jobs 4
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TCL = ROOT / "fpga" / "scripts" / "run_ooc.tcl"
DEFAULT_PART = "xc7a35tfgg484-2"

SOURCES = [
    "rtl/mul8s_behav.sv",
    "fpga/rtl/mul8s_dsp.sv",
    "rtl/csa3to2.sv",
    "rtl/bw_ppgen8.sv",
    "rtl/mul8s_bw.sv",
    "rtl/mul8s_tbw.sv",
    "fpga/rtl/bench_top.sv",
]

TBW_MODES = ("none", "comp", "compzg")
# Stop the Fmax search once a passing run has less slack than this fraction of its period.
TIGHT_SLACK_FRACTION = 0.03

RESULT_FIELDS = [
    "variant", "rtl_module", "trunc_cols", "mode", "max_dsp",
    "slice_luts", "slice_registers", "slices", "carry4", "dsp", "bram_tiles",
    "lut_cells", "ff_cells", "dsp_cells",
    "base_period_ns", "base_wns_ns", "base_datapath_ns", "base_logic_levels",
    "power_dynamic_w", "power_static_w", "power_confidence",
    "best_met_period_ns", "fmax_mhz", "best_met_datapath_ns", "best_met_logic_levels",
    "passes", "mapping_ok", "status",
]

PASS_FIELDS = ["variant", "pass", "period_ns", "wns_ns", "whs_ns", "datapath_ns", "logic_levels",
               "slice_luts", "slice_registers", "dsp", "routing_errors", "met"]

COPY_FROM_BASE = ["utilization.rpt", "post_synth_utilization.rpt", "power.rpt", "route_status.rpt"]
COPY_FROM_BEST = ["critical_path.rpt", "timing_summary.rpt"]

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


@dataclass(frozen=True)
class Variant:
    name: str
    rtl_module: str
    variant_id: int
    max_dsp: int  # -1: no limit (DSP allowed), 0: LUT-only
    trunc_cols: str = ""
    mode: str = ""
    generics: tuple[str, ...] = ()


def all_variants() -> list[Variant]:
    variants = [
        Variant("exact_dsp", "mul8s_dsp", 1, -1),
        Variant("exact_lut", "mul8s_behav", 0, 0),
        Variant("exact_bw", "mul8s_bw", 2, 0),
    ]
    for k in range(8):
        for mode in TBW_MODES:
            comp = 1 if mode in ("comp", "compzg") else 0
            zg = 1 if mode == "compzg" else 0
            variants.append(Variant(
                f"tbw_k{k}_{mode}", "mul8s_tbw", 3, 0, str(k), mode,
                (f"TRUNC_COLS={k}", f"COMP_EN={comp}", f"ZERO_GATE={zg}"),
            ))
    return variants


@dataclass
class PassResult:
    index: int
    period: float
    metrics: dict[str, str]
    run_dir: Path

    @property
    def wns(self) -> float | None:
        return to_float(self.metrics.get("wns_ns"))

    @property
    def met(self) -> bool:
        errors = self.metrics.get("routing_errors", "NA")
        return self.wns is not None and self.wns >= 0 and errors == "0"


@dataclass
class VariantResult:
    variant: Variant
    passes: list[PassResult] = field(default_factory=list)
    error: str = ""


def to_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "", "NA") else None
    except ValueError:
        return None


def ceil_period(value: float) -> float:
    """Round a period up to the next 0.01 ns (avoids float noise like 4.2300000001)."""
    return math.ceil(round(value * 100, 6)) / 100


def read_metrics(path: Path) -> dict[str, str]:
    metrics = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            metrics[key.strip()] = value.strip()
    return metrics


def run_pass(args: argparse.Namespace, variant: Variant, index: int, period: float) -> PassResult:
    run_dir = Path(args.out).resolve() / variant.name / f"pass{index}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    tclargs = [
        f"part={args.part}", "top=bench_top", f"period={period:.3f}", f"outdir={run_dir}",
        f"threads={args.threads}", f"max_dsp={variant.max_dsp}",
        f"generic=VARIANT={variant.variant_id}",
        *[f"generic={g}" for g in variant.generics],
        *[f"src={ROOT / s}" for s in SOURCES],
    ]
    cmd = [args.vivado, "-mode", "batch", "-nojournal", "-notrace", "-log", str(run_dir / "vivado.log"),
           "-source", str(TCL), "-tclargs", *tclargs]
    if args.dry_run:
        log("DRY-RUN: " + " ".join(cmd))
        return PassResult(index, period, {}, run_dir)
    start = time.monotonic()
    proc = subprocess.run(cmd, cwd=run_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (run_dir / "stdout.log").write_text(proc.stdout)
    metrics_file = run_dir / "metrics.txt"
    if proc.returncode != 0 or not metrics_file.exists():
        raise RuntimeError(f"Vivado failed for {variant.name} pass {index} (exit {proc.returncode}); "
                           f"see {run_dir / 'vivado.log'}")
    result = PassResult(index, period, read_metrics(metrics_file), run_dir)
    log(f"  {variant.name:<16} pass {index}: period {period:.3f} ns, WNS {result.metrics.get('wns_ns')} ns, "
        f"LUTs {result.metrics.get('slice_luts')}, {'met' if result.met else 'NOT met'} "
        f"({time.monotonic() - start:.0f} s)")
    return result


def run_variant(args: argparse.Namespace, variant: Variant) -> VariantResult:
    result = VariantResult(variant)
    try:
        first = run_pass(args, variant, 1, args.base_period)
        result.passes.append(first)
        if args.dry_run:
            return result
        last = first
        for index in range(2, args.max_passes + 1):
            if last.wns is None:
                break
            # Next constraint = period achieved by the previous run: tighter after a
            # pass with slack, looser after a failing pass.
            target = ceil_period(last.period - last.wns)
            if any(p.period == target for p in result.passes):
                break  # converged: this period was already tried
            last = run_pass(args, variant, index, target)
            result.passes.append(last)
            if last.met and last.wns is not None and last.wns <= TIGHT_SLACK_FRACTION * last.period:
                break  # met with little slack left: close to the achievable period
    except Exception as exc:  # keep the sweep going; the failure is reported in the CSV
        result.error = str(exc)
        log(f"  {variant.name:<16} ERROR: {exc}")
    return result


def summarize(result: VariantResult) -> dict[str, str]:
    v = result.variant
    row = {key: "" for key in RESULT_FIELDS}
    row.update(variant=v.name, rtl_module=v.rtl_module, trunc_cols=v.trunc_cols, mode=v.mode,
               max_dsp=str(v.max_dsp), passes=str(len(result.passes)))
    if not result.passes:
        row["status"] = f"error: {result.error}"
        return row
    base = result.passes[0].metrics
    for key in ("slice_luts", "slice_registers", "slices", "carry4", "dsp", "bram_tiles",
                "lut_cells", "ff_cells", "dsp_cells", "power_dynamic_w", "power_static_w", "power_confidence"):
        row[key] = base.get(key, "")
    row.update(base_period_ns=f"{result.passes[0].period:.3f}", base_wns_ns=base.get("wns_ns", ""),
               base_datapath_ns=base.get("datapath_ns", ""), base_logic_levels=base.get("logic_levels", ""))
    met = [p for p in result.passes if p.met]
    if met:
        best = min(met, key=lambda p: p.period)
        row.update(best_met_period_ns=f"{best.period:.3f}", fmax_mhz=f"{1000.0 / best.period:.1f}",
                   best_met_datapath_ns=best.metrics.get("datapath_ns", ""),
                   best_met_logic_levels=best.metrics.get("logic_levels", ""))
    dsp = to_float(base.get("dsp"))
    expected_dsp = v.max_dsp != 0
    row["mapping_ok"] = "" if dsp is None else str((dsp > 0) == expected_dsp).lower()
    problems = []
    if result.error:
        problems.append(f"error: {result.error}")
    if not met:
        problems.append("timing not met in any pass")
    if row["mapping_ok"] == "false":
        problems.append("unexpected DSP mapping")
    if any(base.get(k, "NA") == "NA" for k in ("slice_luts", "dsp", "wns_ns")):
        problems.append("report parsing incomplete")
    row["status"] = "; ".join(problems) if problems else "ok"
    return row


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def copy_reports(result: VariantResult, results_dir: Path) -> None:
    if not result.passes:
        return
    dest = results_dir / "reports" / result.variant.name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    met = [p for p in result.passes if p.met]
    best = min(met, key=lambda p: p.period) if met else result.passes[-1]
    for name in COPY_FROM_BASE:
        src = result.passes[0].run_dir / name
        if src.exists():
            shutil.copy2(src, dest / name)
    for name in COPY_FROM_BEST:
        src = best.run_dir / name
        if src.exists():
            shutil.copy2(src, dest / f"{best.run_dir.name}_{name}")


def git_state() -> dict[str, str]:
    def git(*cmd: str) -> str:
        try:
            return subprocess.run(["git", *cmd], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "unknown"
    return {"commit": git("rev-parse", "HEAD"), "dirty": str(bool(git("status", "--porcelain", "--", "rtl", "fpga")))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    parser.add_argument("--vivado", default="vivado", help="Vivado executable (default: vivado in PATH)")
    parser.add_argument("--part", default=DEFAULT_PART)
    parser.add_argument("--base-period", type=float, default=10.0, help="common pass-1 clock period in ns")
    parser.add_argument("--max-passes", type=int, default=4, help="Vivado runs per variant, including pass 1")
    parser.add_argument("--jobs", type=int, default=2, help="parallel Vivado processes")
    parser.add_argument("--threads", type=int, default=2, help="general.maxThreads per Vivado process")
    parser.add_argument("--only", default="", help="regular expression selecting variant names")
    parser.add_argument("--out", default=str(ROOT / "build" / "fpga"), help="raw run directory")
    parser.add_argument("--results", default=str(ROOT / "results" / "fpga"), help="published results directory")
    parser.add_argument("--dry-run", action="store_true", help="print the Vivado commands only")
    args = parser.parse_args()

    variants = [v for v in all_variants() if re.search(args.only, v.name)]
    if not variants:
        parser.error(f"--only {args.only!r} matches no variant")
    vivado = shutil.which(args.vivado)
    if vivado is None and not args.dry_run:
        parser.error(f"'{args.vivado}' not found; run 'source <Vivado>/settings64.sh' or pass --vivado")
    # Vivado runs inside each run directory, so a relative path must be resolved now.
    args.vivado = str(Path(vivado).resolve()) if vivado else args.vivado

    log(f"run_sweep: {len(variants)} variants, part {args.part}, base period {args.base_period:.3f} ns, "
        f"{args.jobs} parallel jobs")
    started = datetime.now(timezone.utc)
    results: dict[str, VariantResult] = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(run_variant, args, v): v for v in variants}
        for future in as_completed(futures):
            res = future.result()
            results[res.variant.name] = res
    if args.dry_run:
        return 0

    ordered = [results[v.name] for v in variants]
    results_dir = Path(args.results)
    rows = [summarize(r) for r in ordered]
    write_csv(results_dir / "fpga_results.csv", RESULT_FIELDS, rows)
    pass_rows = []
    for r in ordered:
        for p in r.passes:
            pass_rows.append({"variant": r.variant.name, "pass": str(p.index), "period_ns": f"{p.period:.3f}",
                              **{k: p.metrics.get(k, "") for k in PASS_FIELDS[3:-1]}, "met": str(p.met).lower()})
    write_csv(results_dir / "fpga_passes.csv", PASS_FIELDS, pass_rows)
    for r in ordered:
        copy_reports(r, results_dir)

    versions = sorted({p.metrics.get("vivado_version", "") for r in ordered for p in r.passes} - {""})
    manifest = {
        "generated_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vivado_version": versions,
        "part": args.part,
        "base_period_ns": args.base_period,
        "max_passes": args.max_passes,
        "jobs": args.jobs,
        "threads_per_job": args.threads,
        "flow": "synth_design -mode out_of_context -flatten_hierarchy rebuilt; opt_design; place_design; "
                "phys_opt_design; route_design (default directives)",
        "git": git_state(),
        "host": {"system": platform.system(), "release": platform.release(), "python": platform.python_version(),
                 "cpu_count": os.cpu_count()},
        "variants": [v.name for v in variants],
    }
    (results_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    bad = [row for row in rows if row["status"] != "ok"]
    log(f"run_sweep: wrote {results_dir / 'fpga_results.csv'} ({len(rows)} variants, {len(bad)} with issues)")
    for row in bad:
        log(f"  ISSUE {row['variant']}: {row['status']}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
