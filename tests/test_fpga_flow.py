# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
"""Tests for the Vivado sweep driver, using a mock Vivado (tests/fpga_mock).

The mock runs the real fpga/scripts/run_ooc.tcl under tclsh with stub Vivado
commands, so Tcl syntax, argument passing, report parsing and the Fmax search
are exercised without Vivado. Mock numbers are synthetic and never published.
"""

import csv
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from models import approx_tbw

ROOT = Path(__file__).resolve().parents[1]
MOCK_VIVADO = ROOT / "tests" / "fpga_mock" / "vivado"

spec = importlib.util.spec_from_file_location("run_sweep", ROOT / "fpga" / "scripts" / "run_sweep.py")
run_sweep = importlib.util.module_from_spec(spec)
sys.modules["run_sweep"] = run_sweep
spec.loader.exec_module(run_sweep)

needs_tclsh = pytest.mark.skipif(shutil.which("tclsh") is None, reason="tclsh not installed")


def test_variant_list():
    variants = run_sweep.all_variants()
    names = [v.name for v in variants]
    assert len(names) == len(set(names)) == 3 + 24
    assert {v.name for v in variants if v.rtl_module == "mul8s_tbw"} == {c.name for c in approx_tbw.all_configs()}
    assert [v.max_dsp for v in variants if v.name == "exact_dsp"] == [-1]
    assert all(v.max_dsp == 0 for v in variants if v.name != "exact_dsp")


@pytest.mark.parametrize("value,expected", [(4.2, 4.2), (4.201, 4.21), (4.2301, 4.24), (4.2300000001, 4.23), (5.0, 5.0)])
def test_ceil_period(value, expected):
    assert run_sweep.ceil_period(value) == pytest.approx(expected)


def _pass(index, period, wns, luts="50", dsp="0", routing="0"):
    metrics = {"wns_ns": str(wns), "slice_luts": luts, "dsp": dsp, "routing_errors": routing,
               "datapath_ns": "4.0", "logic_levels": "6"}
    return run_sweep.PassResult(index, period, metrics, Path("/nonexistent"))


def test_summarize_reports_tightest_passing_run():
    variant = run_sweep.all_variants()[1]  # exact_lut
    result = run_sweep.VariantResult(variant, [_pass(1, 10.0, 5.0), _pass(2, 5.0, -0.2), _pass(3, 5.2, 0.01)])
    row = run_sweep.summarize(result)
    assert row["best_met_period_ns"] == "5.200"
    assert row["fmax_mhz"] == "192.3"
    assert row["status"] == "ok"
    assert row["mapping_ok"] == "true"


def test_summarize_flags_problems():
    variant = run_sweep.all_variants()[1]  # exact_lut must not use a DSP
    result = run_sweep.VariantResult(variant, [_pass(1, 10.0, -1.0, dsp="1"), _pass(2, 11.0, 0.5, routing="3")])
    row = run_sweep.summarize(result)
    assert row["fmax_mhz"] == ""
    assert "timing not met" in row["status"]
    assert "unexpected DSP mapping" in row["status"]


@needs_tclsh
def test_mock_sweep_end_to_end(tmp_path):
    out, results = tmp_path / "runs", tmp_path / "results"
    cmd = [sys.executable, str(ROOT / "fpga" / "scripts" / "run_sweep.py"), "--vivado", str(MOCK_VIVADO),
           "--only", "^(exact_.*|tbw_k4_compzg)$", "--jobs", "2", "--out", str(out), "--results", str(results)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    rows = {r["variant"]: r for r in csv.DictReader((results / "fpga_results.csv").open())}
    assert set(rows) == {"exact_dsp", "exact_lut", "exact_bw", "tbw_k4_compzg"}
    for name, row in rows.items():
        assert row["status"] == "ok", (name, row["status"])
        assert float(row["fmax_mhz"]) == pytest.approx(1000 / float(row["best_met_period_ns"]), abs=0.05)
        assert float(row["best_met_period_ns"]) < float(row["base_period_ns"])
        assert (results / "reports" / name / "utilization.rpt").exists()
    assert rows["exact_dsp"]["dsp"] == "1" and rows["exact_lut"]["dsp"] == "0"

    # Generics and the DSP limit reach synth_design unchanged.
    def synth_args(name):
        return (out / name / "pass1" / "mock_synth_args.txt").read_text()
    assert "-mode out_of_context" in synth_args("exact_lut")
    assert "-max_dsp 0" in synth_args("exact_lut")
    assert "-max_dsp" not in synth_args("exact_dsp")
    tbw = synth_args("tbw_k4_compzg")
    for generic in ("VARIANT=3", "TRUNC_COLS=4", "COMP_EN=1", "ZERO_GATE=1"):
        assert f"-generic {generic}" in tbw
    xdc = (out / "exact_bw" / "pass1" / "bench_ooc.xdc").read_text()
    assert "create_clock -name clk -period 10.000" in xdc

    manifest = json.loads((results / "run_manifest.json").read_text())
    assert manifest["part"] == "xc7a35tfgg484-2"
    assert manifest["vivado_version"] == ["2024.1-mock"]
    passes = list(csv.DictReader((results / "fpga_passes.csv").open()))
    assert {p["variant"] for p in passes} == set(rows)

    # The summary script consumes the sweep output without errors.
    summary = tmp_path / "summary"
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "fpga_summary.py"),
                           "--fpga-csv", str(results / "fpga_results.csv"), "--out", str(summary)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    table = (summary / "fpga_summary.md").read_text()
    assert "| exact_dsp |" in table and "| tbw_k4_compzg |" in table
    assert (summary / "figures" / "luts_vs_mae.png").exists()
    assert (summary / "figures" / "fmax_vs_k.png").exists()
