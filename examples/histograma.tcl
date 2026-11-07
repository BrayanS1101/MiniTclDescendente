set conteo [dict create]
foreach palabra [split {sol luna sol mar luna sol}] {
    if {[dict exists $conteo $palabra]} {
        dict set conteo $palabra [expr {[dict get $conteo $palabra] + 1}]
    } else {
        dict set conteo $palabra 1
    }
}
puts [dict get $conteo sol]
