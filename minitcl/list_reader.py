"""Lector y formateador de listas MiniTcl (sección 7).

El contenido de una lista no es un script: ``$x``, ``[comando]`` y ``;``
son datos. El salto de línea separa elementos igual que un espacio.

    list_value = { LIST_WS }, [ element, { LIST_WS, element } ], { LIST_WS } ;
    element    = LIST_BRACED | LIST_QUOTED | LIST_BARE ;

Contrato: ``parse_list(format_list(values)) == values``.
"""
from __future__ import annotations

from .model import ParseError, Span
from .script_lexer import decode_escape

LIST_WS = " \t\n"


def parse_list(text: str, *, base_offset: int = 0, source_name: str = "<list>") -> list[str]:
    def span(a, b):
        return Span(base_offset + a, base_offset + b, source_name)

    def err(message, a, b=None, **kw):
        return ParseError(message, span(a, b if b is not None else a + 1),
                          stage="validation", **kw)

    items: list[str] = []
    pos = 0
    n = len(text)
    while True:
        while pos < n and text[pos] in LIST_WS:
            pos += 1
        if pos >= n:
            return items
        c = text[pos]
        if c == "{":                                  # LIST_BRACED
            start, depth, i = pos, 0, pos
            while i < n:
                ch = text[i]
                if ch == "\\" and i + 1 < n:
                    i += 2
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            else:
                raise err("Falta '}' en elemento de lista", n, n, expected="}",
                          found="EOF", opening=span(start, start + 1))
            items.append(text[start + 1:i])
            pos = i + 1
            grouped = True
        elif c == '"':                                # LIST_QUOTED
            start, i, chars = pos, pos + 1, []
            while i < n and text[i] != '"':
                if text[i] == "\\":
                    ch, i = decode_escape(text, i, base_offset, source_name, "validation")
                    chars.append(ch)
                else:
                    chars.append(text[i])
                    i += 1
            if i >= n:
                raise err("Faltan comillas de cierre en elemento de lista", n, n,
                          expected='"', found="EOF", opening=span(start, start + 1))
            items.append("".join(chars))
            pos = i + 1
            grouped = True
        else:                                         # LIST_BARE
            chars = []
            while pos < n and text[pos] not in LIST_WS:
                ch = text[pos]
                if ch == "\\":
                    ch, pos = decode_escape(text, pos, base_offset, source_name, "validation")
                    chars.append(ch)
                    continue
                if ch in '{}"':
                    raise err(f"'{ch}' no escapado en elemento de lista no agrupado", pos,
                              expected="texto o escape", found=ch)
                chars.append(ch)
                pos += 1
            items.append("".join(chars))
            grouped = False
        if grouped and pos < n and text[pos] not in LIST_WS:
            raise err("Texto después de un elemento agrupado de lista", pos,
                      expected="blanco o fin", found=text[pos])


def _brace_safe(value: str) -> bool:
    """¿Puede escribirse ``value`` entre llaves y leerse sin cambios?"""
    depth, i = 0, 0
    while i < len(value):
        ch = value[i]
        if ch == "\\":
            if i + 1 >= len(value):
                return False          # barra final escaparía la llave de cierre
            i += 2
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


_BARE_ESCAPES = {"\\": "\\\\", "{": "\\{", "}": "\\}", '"': '\\"', " ": "\\ ",
                 "\t": "\\t", "\n": "\\n", "\r": "\\r"}


def format_element(value: str) -> str:
    if value == "":
        return "{}"
    if not any(ch in value for ch in ' \t\n\r{}"\\'):
        return value
    if _brace_safe(value):
        return "{" + value + "}"
    return "".join(_BARE_ESCAPES.get(ch, ch) for ch in value)


def format_list(values) -> str:
    """Serializa ``values`` sin usar ``' '.join`` ingenuo."""
    return " ".join(format_element(v) for v in values)
