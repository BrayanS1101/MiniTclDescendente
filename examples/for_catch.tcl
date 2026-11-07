set tabla(3) 9
for {set i 0} {$i < 5} {incr i} {
    if {$i == 2} {continue}
    puts [expr {$i * $i}]
}
set codigo [catch {expr {10 / 0}} mensaje]
puts "$codigo: $mensaje"
puts $tabla(3)
