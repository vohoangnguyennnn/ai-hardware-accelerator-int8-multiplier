# SPDX-License-Identifier: Apache-2.0
# Stub Vivado Tcl commands with a simple synthetic delay/area model, so the
# real fpga/scripts/run_ooc.tcl can be executed end to end under tclsh.
# Model: datapath delay (ns) and LUT count depend on the bench_top generics.
# These numbers are fake and only exercise the flow; they are never results.

set script [lindex $argv 0]
set argv [lrange $argv 1 end]

proc mock_arg {key default} {
    foreach a $::argv {
        if {[string match "${key}=*" $a]} { return [string range $a [string length $key]+1 end] }
    }
    return $default
}
proc mock_generic {name default} {
    foreach a $::argv {
        if {[regexp "^generic=${name}=(.*)$" $a -> v]} { return $v }
    }
    return $default
}

set ::mock_variant [mock_generic VARIANT 2]
set ::mock_k [mock_generic TRUNC_COLS 0]
set ::mock_period [mock_arg period 10.0]
# Synthetic model: the DSP variant is fast and LUT-free; truncation removes LUTs.
switch -- $::mock_variant {
    1 { set ::mock_dp 2.40; set ::mock_luts 0;   set ::mock_dsp 1; set ::mock_ff 0 }
    0 { set ::mock_dp 5.10; set ::mock_luts 70;  set ::mock_dsp 0; set ::mock_ff 32 }
    2 { set ::mock_dp 5.60; set ::mock_luts 90;  set ::mock_dsp 0; set ::mock_ff 32 }
    default {
        set ::mock_dp [expr {5.60 - 0.25 * $::mock_k}]
        set ::mock_luts [expr {90 - 6 * $::mock_k}]
        set ::mock_dsp 0; set ::mock_ff 32
    }
}
# Tighter constraints make the mock tool "work harder" (models real behaviour).
if {$::mock_period < 6.0} { set ::mock_dp [expr {$::mock_dp * 0.97}] }

proc mock_write_or_return {args text} {
    set i [lsearch $args -file]
    if {$i >= 0} {
        set fh [open [lindex $args $i+1] w]; puts $fh $text; close $fh; return ""
    }
    return $text
}
proc version {args} { return "2024.1-mock" }
proc set_param {args} {}
proc read_verilog {args} { if {![file exists [lindex $args end]]} { error "mock: missing source [lindex $args end]" } }
proc read_xdc {args} {}
proc synth_design {args} {
    # Record the options so tests can check -generic / -max_dsp forwarding.
    set fh [open [file join [mock_arg outdir .] mock_synth_args.txt] w]
    puts $fh $args
    close $fh
}
proc opt_design {args} {}
proc place_design {args} {}
proc phys_opt_design {args} {}
proc route_design {args} {}
proc report_timing_summary {args} { mock_write_or_return $args "mock timing summary" }
proc report_timing {args} { mock_write_or_return $args "mock critical path" }
proc report_utilization {args} {
    set t "1. Slice Logic\n+-------------------------+------+-------+------------+-----------+-------+\n"
    append t [format "| Slice LUTs              | %4d |     0 |          0 |     20800 |  0.00 |\n" $::mock_luts]
    append t [format "| Slice Registers         | %4d |     0 |          0 |     41600 |  0.00 |\n" $::mock_ff]
    append t [format "| Slice                   | %4d |     0 |          0 |      8150 |  0.00 |\n" [expr {($::mock_luts + 3) / 4}]]
    append t [format "| Block RAM Tile          | %4d |     0 |          0 |        50 |  0.00 |\n" 0]
    append t [format "| DSPs                    | %4d |     0 |          0 |        90 |  0.00 |\n" $::mock_dsp]
    append t [format "| CARRY4                  | %4d |        CarryLogic |\n" [expr {$::mock_dsp ? 0 : 4}]]
    mock_write_or_return $args $t
}
proc report_power {args} {
    mock_write_or_return $args "| Total On-Chip Power (W)  | 0.072        |\n| Dynamic (W)              | 0.003        |\n| Device Static (W)        | 0.069        |\n| Confidence Level         | Low          |"
}
proc report_route_status {args} {
    mock_write_or_return $args "# of nets with routing errors.......... :           0 :"
}
proc get_cells {args} {
    set filter [lindex $args [expr {[lsearch $args -filter] + 1}]]
    switch -glob -- $filter {
        *LUT*    { set n $::mock_luts }
        *FD*     { set n $::mock_ff }
        *DSP48*  { set n $::mock_dsp }
        *CARRY4* { set n [expr {$::mock_dsp ? 0 : 4}] }
        default  { set n 0 }
    }
    set cells {}
    for {set i 0} {$i < $n} {incr i} { lappend cells cell$i }
    return $cells
}
proc get_timing_paths {args} {
    return [expr {[lsearch $args min] >= 0 ? "path_min" : "path_max"}]
}
proc get_property {name obj} {
    switch -- "$obj/$name" {
        path_max/SLACK          { return [format %.3f [expr {$::mock_period - $::mock_dp}]] }
        path_max/DATAPATH_DELAY { return [format %.3f $::mock_dp] }
        path_max/LOGIC_LEVELS   { return 7 }
        path_max/STARTPOINT_PIN { return "a_q_reg\[3\]/C" }
        path_max/ENDPOINT_PIN   { return "p_q_reg\[15\]/D" }
        path_min/SLACK          { return 0.120 }
        default { error "mock get_property: unsupported $name of $obj" }
    }
}

source $script
