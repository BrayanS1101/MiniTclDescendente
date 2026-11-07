"""Lexer manual de scripts MiniTcl (sección 3 del cuaderno).

El lexer es contextual: el significado de un carácter depende del modo en
que aparece.

* **modo script**: ``WS`` y ``SEP`` separan palabras y comandos; ``{`` y
  ``"`` agrupan solo al comienzo de una palabra; ``#`` abre un comentario
  solo donde podría empezar un comando.
* **modo comillas**: espacios, ``;`` y saltos de línea son texto; ``$`` y
  ``[`` siguen abriendo sustituciones.
* **modo sustitución**: al entrar en ``[`` empieza un nuevo contexto de
  comando (modo script anidado) que termina en el ``]`` correspondiente;
  al salir se restaura el modo anterior (script o comillas).
* **llaves**: se balancean contando profundidad; el contenido es literal.

Cada modo corresponde a un método; los cambios de contexto son llamadas
recursivas, de modo que la pila de llamadas de Python es la pila de modos.
"""
from __future__ import annotations

import re

from .model import ParseError, Span, Token, normalize_newlines

IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
INDEX_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-:")

ESCAPES = {
    "n": "\n", "t": "\t", "r": "\r", "\\": "\\", " ": " ", "$": "$",
    "[": "[", "]": "]", "{": "{", "}": "}", '"': '"', ";": ";", "#": "#",
}

HSPACE = " \t"
WORD_END = " \t;\n]"          # fin de una palabra no agrupada
AFTER_GROUP = " \t;\n]"       # lo único que puede seguir a una palabra agrupada


def decode_escape(text: str, pos: int, base: int, source: str,
                  stage: str = "lexer") -> tuple[str, int]:
    """Decodifica el escape que empieza en ``text[pos] == '\\'``.

    Devuelve el carácter producido y la posición siguiente. Comparte la
    tabla de escapes con el lexer de expresiones y el lector de listas.
    """
    if pos + 1 >= len(text):
        raise ParseError("Barra invertida al final de la fuente",
                         Span(base + pos, base + pos + 1, source),
                         expected="carácter escapado", found="EOF", stage=stage)
    nxt = text[pos + 1]
    if nxt == "\n":
        raise ParseError("La continuación barra + salto de línea está fuera del perfil",
                         Span(base + pos, base + pos + 2, source),
                         expected="escape admitido", found="\\<salto>", stage=stage)
    if nxt not in ESCAPES:
        raise ParseError(f"Escape desconocido '\\{nxt}'",
                         Span(base + pos, base + pos + 2, source),
                         expected="escape admitido", found=f"\\{nxt}", stage=stage)
    return ESCAPES[nxt], pos + 2


def scan_variable(text: str, pos: int, base: int, source: str,
                  stage: str = "lexer") -> tuple[str, str | None, int]:
    """Analiza ``$nombre``, ``$nombre(indice)`` o ``${nombre}`` desde ``pos``.

    Devuelve ``(nombre, indice, posicion_siguiente)``. Lo reutiliza el
    lexer de expresiones para que ambas herramientas acepten la misma
    sintaxis de variables.
    """
    start = pos
    pos += 1  # '$'
    if pos < len(text) and text[pos] == "{":
        close = text.find("}", pos + 1)
        name = text[pos + 1:close] if close >= 0 else ""
        if close < 0 or not IDENTIFIER_RE.fullmatch(name):
            raise ParseError("Variable '${...}' mal formada",
                             Span(base + start, base + (close + 1 if close >= 0 else len(text)), source),
                             expected="${identificador}", found=text[start:close + 1 if close >= 0 else len(text)],
                             stage=stage)
        return name, None, close + 1
    match = IDENTIFIER_RE.match(text, pos)
    if not match:
        found = text[pos] if pos < len(text) else "EOF"
        raise ParseError("'$' sin nombre de variable válido (use \\$ para un $ literal)",
                         Span(base + start, base + start + 1, source),
                         expected="identificador", found=found, stage=stage)
    name = match.group()
    pos = match.end()
    if pos < len(text) and text[pos] == "(":
        idx_start = pos + 1
        end = idx_start
        while end < len(text) and text[end] in INDEX_CHARS:
            end += 1
        if end >= len(text) or text[end] != ")":
            found = text[end] if end < len(text) else "EOF"
            raise ParseError("Índice de arreglo fuera del perfil: solo se admiten índices literales simples",
                             Span(base + start, base + min(end + 1, len(text)), source),
                             expected="carácter de índice o ')'", found=found, stage=stage)
        if end == idx_start:
            raise ParseError("Índice de arreglo vacío",
                             Span(base + start, base + end + 1, source),
                             expected="índice", found=")", stage=stage)
        return name, text[idx_start:end], end + 1
    return name, None, pos


class ScriptLexer:
    """Convierte una fuente MiniTcl en la secuencia de ``Token`` del contrato."""

    def __init__(self, source: str, source_name: str = "<input>", base_offset: int = 0):
        self.text = normalize_newlines(source)
        self.source_name = source_name
        self.base = base_offset
        self.pos = 0
        self.tokens: list[Token] = []

    # -- utilidades ---------------------------------------------------------
    def span(self, start: int, end: int) -> Span:
        return Span(self.base + start, self.base + end, self.source_name)

    def emit(self, kind: str, value: str, start: int, end: int, index: str | None = None):
        self.tokens.append(Token(kind, value, self.span(start, end), index))

    def error(self, message: str, start: int, end: int | None = None, **kw) -> ParseError:
        return ParseError(message, self.span(start, end if end is not None else start + 1),
                          stage="lexer", **kw)

    def peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.text[i] if i < len(self.text) else ""

    # -- punto de entrada ---------------------------------------------------
    def tokenize(self) -> list[Token]:
        self.lex_script(opening=None)
        self.emit("EOF", "", len(self.text), len(self.text))
        return self.tokens

    def tokenize_substitution(self, opening_index: int) -> list[Token]:
        """Tokens de ``[ ... ]`` desde ``opening_index`` (callback de SLY)."""
        self.pos = opening_index
        self.lex_bracket()
        end = self.pos
        self.emit("EOF", "", end, end)
        return self.tokens

    # -- modo script --------------------------------------------------------
    def lex_script(self, opening: Span | None):
        """Lee comandos hasta EOF (nivel exterior) o hasta ``]`` (anidado).

        En el nivel anidado no consume el ``]``: lo hace ``lex_bracket``.
        """
        at_command_start = True
        text = self.text
        while self.pos < len(text):
            c = text[self.pos]
            if c in HSPACE:
                start = self.pos
                while self.pos < len(text) and text[self.pos] in HSPACE:
                    self.pos += 1
                self.emit("WS", text[start:self.pos], start, self.pos)
            elif c in ";\n":
                self.emit("SEP", c, self.pos, self.pos + 1)
                self.pos += 1
                at_command_start = True
            elif c == "#" and at_command_start:
                # Comentario: termina antes del salto, que sigue separando.
                end = text.find("\n", self.pos)
                self.pos = len(text) if end < 0 else end
            elif c == "]":
                if opening is not None:
                    return
                # Cierre fuera de contexto: se emite y el parser lo rechaza.
                self.emit("RBRACKET", "]", self.pos, self.pos + 1)
                self.pos += 1
                at_command_start = False
            else:
                self.lex_word()
                at_command_start = False
        if opening is not None:
            raise ParseError("Falta ']' que cierre la sustitución de comando",
                             self.span(len(text), len(text)), expected="]", found="EOF",
                             opening=opening, stage="lexer")

    def lex_word(self):
        c = self.text[self.pos]
        if c == "{":
            self.lex_braced()
            self.check_after_group()
        elif c == '"':
            self.lex_quoted()
            self.check_after_group()
        else:
            self.lex_bare()

    def check_after_group(self):
        c = self.peek()
        if c and c not in AFTER_GROUP:
            raise self.error("Texto después de cerrar una palabra agrupada", self.pos,
                             expected="espacio, separador, ']' o fin", found=c)

    # -- llaves -------------------------------------------------------------
    def lex_braced(self):
        text = self.text
        start = self.pos
        depth = 0
        i = start
        while i < len(text):
            ch = text[i]
            if ch == "\\" and i + 1 < len(text):
                i += 2          # \{ y \} no cambian la profundidad
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    self.emit("BRACED", text[start + 1:i], start, i + 1)
                    self.pos = i + 1
                    return
            i += 1
        raise ParseError("Falta '}' que cierre la llave", self.span(len(text), len(text)),
                         expected="}", found="EOF", opening=self.span(start, start + 1),
                         stage="lexer")

    # -- comillas -----------------------------------------------------------
    def lex_quoted(self):
        text = self.text
        start = self.pos
        self.emit("QOPEN", '"', start, start + 1)
        self.pos += 1
        buf: list[str] = []
        buf_start = self.pos

        def flush():
            if buf:
                self.emit("TEXT", "".join(buf), buf_start, self.pos)
                buf.clear()

        while self.pos < len(text):
            c = text[self.pos]
            if c == '"':
                flush()
                self.emit("QCLOSE", '"', self.pos, self.pos + 1)
                self.pos += 1
                return
            if c == "$":
                flush()
                self.lex_variable()
                buf_start = self.pos
            elif c == "[":
                flush()
                self.lex_bracket()       # vuelve temporalmente al modo script
                buf_start = self.pos     # ... y se restaura el modo comillas
            elif c == "\\":
                if not buf:
                    buf_start = self.pos
                ch, self.pos = decode_escape(text, self.pos, self.base, self.source_name)
                buf.append(ch)
            else:
                if not buf:
                    buf_start = self.pos
                buf.append(c)
                self.pos += 1
        raise ParseError('Faltan comillas de cierre \'"\'', self.span(len(text), len(text)),
                         expected='"', found="EOF", opening=self.span(start, start + 1),
                         stage="lexer")

    # -- palabras no agrupadas ---------------------------------------------
    def lex_bare(self):
        text = self.text
        buf: list[str] = []
        buf_start = self.pos

        def flush():
            if buf:
                self.emit("TEXT", "".join(buf), buf_start, self.pos)
                buf.clear()

        while self.pos < len(text) and text[self.pos] not in WORD_END:
            c = text[self.pos]
            if c == "$":
                flush()
                self.lex_variable()
                buf_start = self.pos
            elif c == "[":
                flush()
                self.lex_bracket()
                buf_start = self.pos
            elif c == "\\":
                if not buf:
                    buf_start = self.pos
                ch, self.pos = decode_escape(text, self.pos, self.base, self.source_name)
                buf.append(ch)
            elif c in '{}"':
                raise self.error(f"'{c}' no escapado dentro de una palabra no agrupada",
                                 self.pos, expected="texto o escape", found=c)
            else:
                if not buf:
                    buf_start = self.pos
                buf.append(c)
                self.pos += 1
        flush()

    # -- sustituciones ------------------------------------------------------
    def lex_variable(self):
        start = self.pos
        name, index, end = scan_variable(self.text, start, self.base, self.source_name)
        self.emit("VAR", name, start, end, index)
        self.pos = end

    def lex_bracket(self):
        start = self.pos
        self.emit("LBRACKET", "[", start, start + 1)
        self.pos += 1
        self.lex_script(opening=self.span(start, start + 1))
        self.emit("RBRACKET", "]", self.pos, self.pos + 1)
        self.pos += 1


def tokenize_script(source: str, source_name: str = "<input>", base_offset: int = 0) -> list[Token]:
    return ScriptLexer(source, source_name, base_offset).tokenize()
