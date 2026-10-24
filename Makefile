# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
#
# Open-source regression flow (Python models, Verilator, Icarus, Yosys).
# FPGA PPA runs use Vivado locally and are not part of this Makefile.
#
#   make test                       full regression (what CI runs)
#   make sim DUT=mul8s_bw           one exhaustive Verilator simulation
#   make sim-tbw_k4_comp            one approximate configuration
#   make results                    regenerate error metrics and figures
#   make help                       list targets

SHELL       := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

PYTHON    ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
VERILATOR ?= verilator
IVERILOG  ?= iverilog
VVP       ?= vvp
YOSYS     ?= yosys
BUILD     ?= build

# ---------------------------------------------------------------------------
# Exact variants: RTL sources, the reference model each must match, and
# whether the SystemVerilog '*' operator is a valid second oracle.
# ---------------------------------------------------------------------------
DUTS := mul8s_behav mul8s_bw

SRCS_mul8s_behav  := rtl/mul8s_behav.sv
MODEL_mul8s_behav := exact
EXACT_mul8s_behav := 1

SRCS_mul8s_bw  := rtl/csa3to2.sv rtl/bw_ppgen8.sv rtl/mul8s_bw.sv
MODEL_mul8s_bw := exact
EXACT_mul8s_bw := 1

# ---------------------------------------------------------------------------
# Approximate variant mul8s_tbw: every configuration tbw_k<K>_<mode>,
# K = 0..7, mode = none | comp | compzg (see models/approx_tbw.py).
# ---------------------------------------------------------------------------
SRCS_mul8s_tbw := rtl/csa3to2.sv rtl/bw_ppgen8.sv rtl/mul8s_tbw.sv
TBW_KS         := 0 1 2 3 4 5 6 7
TBW_MODES      := none comp compzg
TBW_CONFIGS    := $(foreach k,$(TBW_KS),$(foreach m,$(TBW_MODES),tbw_k$(k)_$(m)))
# Subset also run through Icarus and Yosys (exhaustive Verilator covers all).
TBW_SPOT       := tbw_k0_none tbw_k4_comp tbw_k4_compzg tbw_k7_compzg

# Parameter values of a configuration tag, e.g. $(call tbw_k,tbw_k4_comp) -> 4
tbw_k    = $(patsubst k%,%,$(word 2,$(subst _, ,$(1))))
tbw_comp = $(if $(filter comp compzg,$(word 3,$(subst _, ,$(1)))),1,0)
tbw_zg   = $(if $(filter compzg,$(word 3,$(subst _, ,$(1)))),1,0)
# Verilator -G needs sized literals for 'bit' parameters (shell-quoted).
vl_bit   = 1\'b$(1)

TB := verif/tb_mul8s.sv

# Per-run settings, overridable from the command line (used by the mutant runner)
DUT     ?= mul8s_bw
CFG     ?=
SRCS    ?= $(SRCS_$(DUT))
MODEL   ?= $(if $(CFG),$(CFG),$(MODEL_$(DUT)))
SIM_DIR ?= $(BUILD)/sim/$(if $(CFG),$(CFG),$(DUT))
VECTORS  = $(BUILD)/vectors/$(MODEL).hex

TBW_FLAGS = $(if $(CFG),-DTBW_PARAMS -GTRUNC_COLS=$(call tbw_k,$(CFG)) \
              -GCOMP_EN=$(call vl_bit,$(call tbw_comp,$(CFG))) \
              -GZERO_GATE=$(call vl_bit,$(call tbw_zg,$(CFG))))

EXTRA_VERILATOR_FLAGS ?=
VERILATOR_LINT_FLAGS  := --lint-only -Wall
VERILATOR_SIM_FLAGS    = --binary --timing --timescale 1ns/1ps -Wall --top-module tb_mul8s \
                         -DDUT=$(DUT) $(if $(EXACT_$(DUT)),-DEXACT_ORACLE) $(TBW_FLAGS) \
                         $(EXTRA_VERILATOR_FLAGS)

.PHONY: help test pytest lint sim sim-all sim-tbw icarus-all synth-check mutants \
        vectors results check-results clean
# Vector files are intermediate but must survive between sub-makes.
.SECONDARY:

help:
	@echo "Targets:"
	@echo "  test           full regression: pytest, lint, Verilator + Icarus sims,"
	@echo "                 Yosys synth check, mutants, results consistency"
	@echo "  pytest         Python reference-model tests"
	@echo "  lint           verilator -Wall lint (every DUT, every tbw configuration)"
	@echo "  sim            exhaustive Verilator simulation of DUT=<name> (default $(DUT))"
	@echo "  sim-all        exhaustive simulation of exact DUTs and all $(words $(TBW_CONFIGS)) tbw configurations"
	@echo "  sim-<tag>      one configuration, e.g. sim-mul8s_bw or sim-tbw_k4_comp"
	@echo "  icarus-all     exhaustive Icarus (4-state) simulation of exact DUTs + tbw spot configs"
	@echo "  synth-check    Yosys synth_xilinx (synthesizability gate, not PPA data)"
	@echo "  mutants        confirm the testbench detects injected RTL bugs"
	@echo "  results        regenerate results/error_metrics*.csv and results/figures/"
	@echo "  check-results  verify committed CSV results match the models"
	@echo "  clean          remove $(BUILD)/"

test: pytest lint sim-all icarus-all synth-check mutants check-results
	@echo "REGRESSION PASSED"

pytest:
	$(PYTHON) -m pytest

# --- Lint --------------------------------------------------------------------
lint: $(addprefix lint-,$(DUTS)) lint-tbw

lint-%:
	$(VERILATOR) $(VERILATOR_LINT_FLAGS) --top-module $* $(SRCS_$*)

lint-tbw:
	@for cfg in $(TBW_CONFIGS); do \
	  k=$${cfg#tbw_k}; k=$${k%%_*}; mode=$${cfg##*_}; \
	  comp=$$([[ $$mode == comp* ]] && echo 1 || echo 0); zg=$$([[ $$mode == compzg ]] && echo 1 || echo 0); \
	  $(VERILATOR) $(VERILATOR_LINT_FLAGS) --top-module mul8s_tbw \
	    -GTRUNC_COLS=$$k -GCOMP_EN="1'b$$comp" -GZERO_GATE="1'b$$zg" $(SRCS_mul8s_tbw) || exit 1; \
	done
	@echo "lint: mul8s_tbw clean for $(words $(TBW_CONFIGS)) configurations"

# --- Reference vectors -------------------------------------------------------
vectors: $(BUILD)/vectors/exact.hex $(addprefix $(BUILD)/vectors/,$(addsuffix .hex,$(TBW_CONFIGS)))

$(BUILD)/vectors/%.hex: models/gen_vectors.py models/golden.py models/bw_model.py models/approx_tbw.py
	$(PYTHON) -m models.gen_vectors --model $* --out $@

# --- Verilator simulation ----------------------------------------------------
sim: $(VECTORS)
	@mkdir -p $(SIM_DIR)
	$(VERILATOR) $(VERILATOR_SIM_FLAGS) -Mdir $(SIM_DIR)/obj $(SRCS) $(TB) > $(SIM_DIR)/build.log 2>&1 \
	  || { cat $(SIM_DIR)/build.log; exit 1; }
	$(SIM_DIR)/obj/Vtb_mul8s +VECTORS=$(VECTORS) | tee $(SIM_DIR)/sim.log

sim-all: $(addprefix sim-,$(DUTS)) sim-tbw

sim-tbw: $(addprefix sim-,$(TBW_CONFIGS))
	@echo "sim-tbw: $(words $(TBW_CONFIGS))/$(words $(TBW_CONFIGS)) mul8s_tbw configurations passed"

sim-tbw_%:
	$(MAKE) --no-print-directory sim DUT=mul8s_tbw CFG=tbw_$*

sim-mul8s_%:
	$(MAKE) --no-print-directory sim DUT=mul8s_$*

# --- Icarus simulation (independent 4-state simulator) -----------------------
icarus-all: $(addprefix icarus-,$(DUTS)) $(addprefix icarus-,$(TBW_SPOT))

icarus-mul8s_%: $(BUILD)/vectors/exact.hex
	@mkdir -p $(BUILD)/icarus
	$(IVERILOG) -g2012 -Wall -DDUT=mul8s_$* $(if $(EXACT_mul8s_$*),-DEXACT_ORACLE) -s tb_mul8s \
	  -o $(BUILD)/icarus/mul8s_$*.vvp $(SRCS_mul8s_$*) $(TB)
	$(VVP) -n $(BUILD)/icarus/mul8s_$*.vvp +VECTORS=$< | tee $(BUILD)/icarus/mul8s_$*.log
	@grep -q "^PASS: mul8s_$*" $(BUILD)/icarus/mul8s_$*.log

icarus-tbw_%: $(BUILD)/vectors/tbw_%.hex
	@mkdir -p $(BUILD)/icarus
	$(IVERILOG) -g2012 -Wall -DDUT=mul8s_tbw -DTBW_PARAMS -s tb_mul8s \
	  -Ptb_mul8s.TRUNC_COLS=$(call tbw_k,tbw_$*) -Ptb_mul8s.COMP_EN=$(call tbw_comp,tbw_$*) \
	  -Ptb_mul8s.ZERO_GATE=$(call tbw_zg,tbw_$*) \
	  -o $(BUILD)/icarus/tbw_$*.vvp $(SRCS_mul8s_tbw) $(TB)
	$(VVP) -n $(BUILD)/icarus/tbw_$*.vvp +VECTORS=$< | tee $(BUILD)/icarus/tbw_$*.log
	@grep -q "^PASS: mul8s_tbw" $(BUILD)/icarus/tbw_$*.log

# --- Yosys synthesizability check (resource numbers are NOT Vivado results) --
synth-check: $(addprefix synth-,$(DUTS)) $(addprefix synth-,$(TBW_SPOT))

synth-mul8s_%:
	@mkdir -p $(BUILD)/yosys
	$(YOSYS) -q -l $(BUILD)/yosys/mul8s_$*.log \
	  -p "read_verilog -sv $(SRCS_mul8s_$*); synth_xilinx -family xc7 -flatten -nodsp -top mul8s_$*; tee -o $(BUILD)/yosys/mul8s_$*.stat stat"
	@echo "synth-check: mul8s_$* synthesized"

synth-tbw_%:
	@mkdir -p $(BUILD)/yosys
	$(YOSYS) -q -l $(BUILD)/yosys/tbw_$*.log \
	  -p "read_verilog -sv $(SRCS_mul8s_tbw); \
	      chparam -set TRUNC_COLS $(call tbw_k,tbw_$*) -set COMP_EN $(call tbw_comp,tbw_$*) \
	              -set ZERO_GATE $(call tbw_zg,tbw_$*) mul8s_tbw; \
	      synth_xilinx -family xc7 -flatten -nodsp -top mul8s_tbw; tee -o $(BUILD)/yosys/tbw_$*.stat stat"
	@echo "synth-check: mul8s_tbw (tbw_$*) synthesized"

# --- Testbench self-check ----------------------------------------------------
mutants: $(BUILD)/vectors/exact.hex $(BUILD)/vectors/tbw_k4_compzg.hex
	$(PYTHON) verif/run_mutants.py

# --- Error characterisation --------------------------------------------------
results:
	$(PYTHON) scripts/error_analysis.py --out results

check-results:
	$(PYTHON) scripts/error_analysis.py --out $(BUILD)/results --no-figures
	@for f in error_metrics.csv error_by_quadrant.csv; do \
	  diff -u results/$$f $(BUILD)/results/$$f || { echo "results/$$f is stale: run 'make results'"; exit 1; }; \
	done
	@echo "check-results: committed CSV files match the models"

clean:
	rm -rf $(BUILD)
