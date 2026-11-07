# MiniTcl educativo 1.1 — analizador descendente recursivo + SLY

Lexer manual y parser descendente recursivo para scripts MiniTcl; lexer
`sly.Lexer` y parser LALR(1) `sly.Parser` para las expresiones de `expr` y
de las condiciones de `if`, `while` y `for`. Se produce el AST; no se
ejecuta nada.

## Estructura

| Ruta | Contenido |
|---|---|
| `minitcl/model.py` | AST, `Token`, `ParseError` (línea, columna, esperado, encontrado, apertura), `TokenCursor` |
| `minitcl/script_lexer.py` | Lexer manual contextual |
| `minitcl/script_parser.py` | `ScriptParser`, `parse_minitcl`, `read_substitution` |
| `minitcl/expr_lexer.py` | `ExprLexer(sly.Lexer)` |
| `minitcl/expr_parser.py` | `ExprParser(sly.Parser)`, `parse_minitcl_expr` |
| `minitcl/list_reader.py` | `parse_list`, `format_list` |
| `minitcl/command_analyzer.py` | Validación de comandos y reanálisis de cuerpos y condiciones |
| `tests/` | Pruebas `pytest` |
| `examples/` | Programas de aceptación (sección 15) |
| `MiniTcl_Analizador_Descendente_Recursivo_Completado.ipynb` | Cuaderno completado con respuestas |
| `MiniTcl_Railroad.ebnf` | Gramática para https://www.bottlecaps.de/rr/ui |

## Uso

```bash
pip install -r requirements.txt
python -m pytest -q
python analyze_examples.py        # añada -v para imprimir el AST
```

```python
from minitcl import parse_minitcl, parse_minitcl_expr, analyze_source
script = parse_minitcl('puts "Hola $nombre"')
expr = parse_minitcl_expr("2 ** -3")
result = analyze_source(open("examples/factorial.tcl").read(), "factorial.tcl")
```
