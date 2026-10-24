# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
#
# Open-source regression flow (Python models, Verilator, Icarus, Yosys).
# FPGA PPA runs use Vivado locally and are not part of this Makefile.
#
#   make test                 full regression (what CI runs)
#   make sim DUT=mul8s_bw     one exhaustive Verilator simulation
#   make help                 list targets

SHELL       := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

PYTHON    ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
VERILATOR ?= verilator
IVERILOG  ?= iverilog
VVP       ?= vvp
YOSYS     ?= yosys
BUILD     ?= build

# ---------------------------------------------------------------------------
# Design variants: RTL sources, the reference model each must match, and
# whether the SystemVerilog '*' operator is a valid second oracle.
# ---------------------------------------------------------------------------
DUTS := mul8s_behav mul8s_bw

SRCS_mul8s_behav  := rtl/mul8s_behav.sv
MODEL_mul8s_behav := exact
EXACT_mul8s_behav := 1

SRCS_mul8s_bw  := rtl/csa3to2.sv rtl/bw_ppgen8.sv rtl/mul8s_bw.sv
MODEL_mul8s_bw := exact
EXACT_mul8s_bw := 1

TB := verif/tb_mul8s.sv

# Per-run settings, overridable from the command line (used by the mutant runner)
DUT     ?= mul8s_bw
SRCS    ?= $(SRCS_$(DUT))
MODEL   ?= $(MODEL_$(DUT))
SIM_DIR ?= $(BUILD)/sim/$(DUT)
VECTORS  = $(BUILD)/vectors/$(MODEL).hex

EXTRA_VERILATOR_FLAGS ?=
VERILATOR_LINT_FLAGS  := --lint-only -Wall
VERILATOR_SIM_FLAGS    = --binary --timing --timescale 1ns/1ps -Wall --top-module tb_mul8s \
                         -DDUT=$(DUT) $(if $(EXACT_$(DUT)),-DEXACT_ORACLE) $(EXTRA_VERILATOR_FLAGS)

.PHONY: help test pytest lint sim sim-all icarus-all synth-check mutants vectors clean
# Vector files are intermediate but must survive between sub-makes.
.SECONDARY:

help:
	@echo "Targets:"
	@echo "  test         pytest, lint, Verilator + Icarus sims, Yosys synth check, mutants"
	@echo "  pytest       Python reference-model tests"
	@echo "  lint         verilator -Wall lint of every DUT"
	@echo "  sim          exhaustive Verilator simulation of DUT=<name> (default $(DUT))"
	@echo "  sim-all      exhaustive Verilator simulation of: $(DUTS)"
	@echo "  icarus-all   exhaustive Icarus (4-state) simulation of every DUT"
	@echo "  synth-check  Yosys synth_xilinx of every DUT (synthesizability gate)"
	@echo "  mutants      confirm the testbench detects injected RTL bugs"
	@echo "  vectors      generate expected-result vector files"
	@echo "  clean        remove $(BUILD)/"

test: pytest lint sim-all icarus-all synth-check mutants
	@echo "REGRESSION PASSED"

pytest:
	$(PYTHON) -m pytest

# --- Lint --------------------------------------------------------------------
lint: $(addprefix lint-,$(DUTS))

lint-%:
	$(VERILATOR) $(VERILATOR_LINT_FLAGS) --top-module $* $(SRCS_$*)

# --- Reference vectors -------------------------------------------------------
vectors: $(BUILD)/vectors/exact.hex

$(BUILD)/vectors/%.hex: models/gen_vectors.py models/golden.py models/bw_model.py
	$(PYTHON) -m models.gen_vectors --model $* --out $@

# --- Verilator simulation ----------------------------------------------------
sim: $(VECTORS)
	@mkdir -p $(SIM_DIR)
	$(VERILATOR) $(VERILATOR_SIM_FLAGS) -Mdir $(SIM_DIR)/obj $(SRCS) $(TB) > $(SIM_DIR)/build.log 2>&1 \
	  || { cat $(SIM_DIR)/build.log; exit 1; }
	$(SIM_DIR)/obj/Vtb_mul8s +VECTORS=$(VECTORS) | tee $(SIM_DIR)/sim.log

sim-all: $(addprefix sim-,$(DUTS))

sim-%:
	$(MAKE) --no-print-directory sim DUT=$*

# --- Icarus simulation (independent 4-state simulator) -----------------------
icarus-all: $(addprefix icarus-,$(DUTS))

icarus-%: $(BUILD)/vectors/exact.hex
	@mkdir -p $(BUILD)/icarus
	$(IVERILOG) -g2012 -Wall -DDUT=$* $(if $(EXACT_$*),-DEXACT_ORACLE) -s tb_mul8s \
	  -o $(BUILD)/icarus/$*.vvp $(SRCS_$*) $(TB)
	$(VVP) -n $(BUILD)/icarus/$*.vvp +VECTORS=$(BUILD)/vectors/$(MODEL_$*).hex | tee $(BUILD)/icarus/$*.log
	@grep -q "^PASS: $*" $(BUILD)/icarus/$*.log

# --- Yosys synthesizability check (resource numbers are NOT Vivado results) --
synth-check: $(addprefix synth-,$(DUTS))

synth-%:
	@mkdir -p $(BUILD)/yosys
	$(YOSYS) -q -l $(BUILD)/yosys/$*.log \
	  -p "read_verilog -sv $(SRCS_$*); synth_xilinx -family xc7 -flatten -nodsp -top $*; tee -o $(BUILD)/yosys/$*.stat stat"
	@echo "synth-check: $* synthesized (Yosys proxy stats in $(BUILD)/yosys/$*.stat)"

# --- Testbench self-check ----------------------------------------------------
mutants: $(BUILD)/vectors/exact.hex
	$(PYTHON) verif/run_mutants.py

clean:
	rm -rf $(BUILD)
