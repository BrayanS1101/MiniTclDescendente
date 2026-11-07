"""Analiza (sin ejecutar) los programas de aceptación de la sección 15."""
import sys
from pathlib import Path

from minitcl import ParseError, analyze_source, show_ast

files = sys.argv[1:] or sorted(str(p) for p in Path("examples").glob("*.tcl"))
status = 0
for name in files:
    source = Path(name).read_text(encoding="utf-8")
    try:
        result = analyze_source(source, name)
    except ParseError as err:
        print(err.report())
        status = 1
        continue
    print(f"== {name}: {len(result.script.commands)} comandos, "
          f"{len(result.bodies)} cuerpos y {len(result.exprs)} expresiones reanalizados")
    if "-v" in sys.argv:
        show_ast(result.script)
sys.exit(status)
