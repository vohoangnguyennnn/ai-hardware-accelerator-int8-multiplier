# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Vo Hoang Nguyen
#
# run_ooc.tcl - One out-of-context Vivado run of fpga/rtl/bench_top.sv.
#
# Non-project batch flow: synth_design (OOC) -> opt_design -> place_design ->
# phys_opt_design -> route_design, then reports and a key=value metrics file.
# Normally invoked by fpga/scripts/run_sweep.py:
#
#   vivado -mode batch -nojournal -source run_ooc.tcl -tclargs \
#       part=xc7a35tfgg484-2 top=bench_top period=10.000 outdir=<dir> \
#       src=<file.sv> [src=...] [generic=NAME=VALUE ...] [max_dsp=0] [threads=2]
#
# Outputs in <outdir>: bench_ooc.xdc, post_synth_utilization.rpt,
# utilization.rpt, timing_summary.rpt, critical_path.rpt, power.rpt,
# route_status.rpt and metrics.txt.

proc parse_args {arglist} {
    set cfg [dict create srcs {} generics {} max_dsp -1 threads 2 clk_src BUFGCTRL_X0Y0]
    foreach arg $arglist {
        if {![regexp {^([a-z_]+)=(.*)$} $arg -> key value]} {
            error "run_ooc.tcl: bad argument '$arg' (expected key=value)"
        }
        switch -- $key {
            src     { dict lappend cfg srcs $value }
            generic { dict lappend cfg generics $value }
            default { dict set cfg $key $value }
        }
    }
    foreach required {part top period outdir} {
        if {![dict exists $cfg $required]} {
            error "run_ooc.tcl: missing argument $required=<value>"
        }
    }
    if {[llength [dict get $cfg srcs]] == 0} {
        error "run_ooc.tcl: no src=<file> given"
    }
    return $cfg
}

# First numeric cell of a report_utilization table row, e.g.
#   | Slice LUTs*             |   75 |     0 | ...
proc util_value {report label} {
    set pattern "^\\|\\s*[string map {( \\( ) \\)} $label]\\*?\\s*\\|\\s*(\[0-9.\]+)\\s*\\|"
    if {[regexp -line -- $pattern $report -> value]} {
        return $value
    }
    return NA
}

# Value cell of a report_power summary row, e.g.
#   | Dynamic (W)              | 0.004        |
proc power_value {report label} {
    set pattern "^\\|\\s*[string map {( \\( ) \\)} $label]\\s*\\|(\[^|\]*)\\|"
    if {[regexp -line -- $pattern $report -> value]} {
        return [string trim $value]
    }
    return NA
}

proc count_cells {filter} {
    return [llength [get_cells -hierarchical -quiet -filter $filter]]
}

proc path_property {path name} {
    if {[llength $path] == 0} {
        return NA
    }
    return [get_property $name $path]
}

# ---------------------------------------------------------------------------
set cfg [parse_args $::argv]
set outdir [file normalize [dict get $cfg outdir]]
file mkdir $outdir
set_param general.maxThreads [dict get $cfg threads]

# Per-run constraints: one clock on the register-to-register benchmark path.
# HD.CLK_SRC models a global clock buffer driving the out-of-context block.
set xdc [file join $outdir bench_ooc.xdc]
set fh [open $xdc w]
puts $fh "create_clock -name clk -period [dict get $cfg period] \[get_ports clk\]"
puts $fh "set_property HD.CLK_SRC [dict get $cfg clk_src] \[get_ports clk\]"
close $fh

foreach src [dict get $cfg srcs] {
    read_verilog -sv $src
}
read_xdc $xdc

set synth_opts [list -top [dict get $cfg top] -part [dict get $cfg part] \
                     -mode out_of_context -flatten_hierarchy rebuilt]
foreach generic [dict get $cfg generics] {
    lappend synth_opts -generic $generic
}
if {[dict get $cfg max_dsp] >= 0} {
    lappend synth_opts -max_dsp [dict get $cfg max_dsp]
}
synth_design {*}$synth_opts
report_utilization -file [file join $outdir post_synth_utilization.rpt]

opt_design
place_design
phys_opt_design
route_design

# ---------------------------------------------------------------------------
# Reports (kept as evidence) and machine-readable metrics
# ---------------------------------------------------------------------------
set util_rpt  [report_utilization -return_string]
set power_rpt [report_power -return_string]
set route_rpt [report_route_status -return_string]
foreach {name text} [list utilization.rpt $util_rpt power.rpt $power_rpt route_status.rpt $route_rpt] {
    set fh [open [file join $outdir $name] w]
    puts $fh $text
    close $fh
}
report_timing_summary -max_paths 5 -file [file join $outdir timing_summary.rpt]
report_timing -delay_type max -max_paths 1 -path_type full -input_pins \
    -file [file join $outdir critical_path.rpt]

set setup_path [get_timing_paths -delay_type max -max_paths 1 -nworst 1]
set hold_path  [get_timing_paths -delay_type min -max_paths 1 -nworst 1]

set routing_errors NA
regexp -- {nets with routing errors[^0-9]*([0-9]+)} $route_rpt -> routing_errors

set metrics [list \
    vivado_version   [version -short] \
    part             [dict get $cfg part] \
    top              [dict get $cfg top] \
    generics         [join [dict get $cfg generics] " "] \
    max_dsp          [dict get $cfg max_dsp] \
    period_ns        [dict get $cfg period] \
    slice_luts       [util_value $util_rpt "Slice LUTs"] \
    slice_registers  [util_value $util_rpt "Slice Registers"] \
    slices           [util_value $util_rpt "Slice"] \
    carry4           [util_value $util_rpt "CARRY4"] \
    dsp              [util_value $util_rpt "DSPs"] \
    bram_tiles       [util_value $util_rpt "Block RAM Tile"] \
    lut_cells        [count_cells {REF_NAME =~ LUT*}] \
    ff_cells         [count_cells {REF_NAME =~ FD*}] \
    dsp_cells        [count_cells {REF_NAME =~ DSP48*}] \
    carry4_cells     [count_cells {REF_NAME == CARRY4}] \
    wns_ns           [path_property $setup_path SLACK] \
    whs_ns           [path_property $hold_path SLACK] \
    datapath_ns      [path_property $setup_path DATAPATH_DELAY] \
    logic_levels     [path_property $setup_path LOGIC_LEVELS] \
    path_start       [path_property $setup_path STARTPOINT_PIN] \
    path_end         [path_property $setup_path ENDPOINT_PIN] \
    routing_errors   $routing_errors \
    power_total_w    [power_value $power_rpt "Total On-Chip Power (W)"] \
    power_dynamic_w  [power_value $power_rpt "Dynamic (W)"] \
    power_static_w   [power_value $power_rpt "Device Static (W)"] \
    power_confidence [power_value $power_rpt "Confidence Level"] \
]

set fh [open [file join $outdir metrics.txt] w]
foreach {key value} $metrics {
    puts $fh "$key=$value"
}
close $fh
puts "run_ooc.tcl: done, metrics in [file join $outdir metrics.txt]"
