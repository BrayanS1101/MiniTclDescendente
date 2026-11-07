set datos [list 4 8 15 16 23 42]
set suma 0
foreach dato $datos {
    set suma [expr {$suma + $dato}]
}
set promedio [expr {$suma / [llength $datos]}]
puts "Promedio: $promedio"
