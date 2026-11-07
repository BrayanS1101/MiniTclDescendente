"""Modelo del AST, tokens, cursor y error de análisis de MiniTcl.

Las clases se conservan con el mismo contrato que entrega el cuaderno
(sección 8 y 9). ``ParseError`` se amplía de forma compatible para
transportar el elemento esperado, el encontrado, la posición de apertura
de una agrupación sin cerrar y, cuando se conoce la fuente, la línea y la
columna del error.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from typing import Literal as Mode


# ---------------------------------------------------------------------------
# Posiciones
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Span:
    start: int
    end: int
    source: str = "<input>"


@dataclass(frozen=True, kw_only=True)
class Node:
    span: Span


# ---------------------------------------------------------------------------
# AST estructural de scripts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Literal(Node):
    text: str


@dataclass(frozen=True)
class Variable(Node):
    name: str
    index: str | None = None


@dataclass(frozen=True)
class CommandSubstitution(Node):
    script: Script


Part = Literal | Variable | CommandSubstitution


@dataclass(frozen=True)
class Word(Node):
    parts: tuple[Part, ...]
    mode: Mode["bare", "quoted", "braced"] = "bare"


@dataclass(frozen=True)
class Command(Node):
    words: tuple[Word, ...]


@dataclass(frozen=True)
class Script(Node):
    commands: tuple[Command, ...]


# ---------------------------------------------------------------------------
# AST de expresiones
# ---------------------------------------------------------------------------

@dataclass(frozen=True, kw_only=True)
class Expr(Node):
    pass


@dataclass(frozen=True)
class Constant(Expr):
    value: int | float | str | bool


@dataclass(frozen=True)
class VariableExpr(Expr):
    variable: Variable


@dataclass(frozen=True)
class SubstitutionExpr(Expr):
    script: Script


@dataclass(frozen=True)
class Unary(Expr):
    operator: str
    operand: Expr


@dataclass(frozen=True)
class Binary(Expr):
    operator: str
    left: Expr
    right: Expr


# ---------------------------------------------------------------------------
# Tokens, errores y cursor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    span: Span
    index: str | None = None


def line_column(text: str, offset: int) -> tuple[int, int]:
    """Línea y columna (desde 1) de ``offset`` en la fuente normalizada."""
    offset = max(0, min(offset, len(text)))
    line = text.count("\n", 0, offset) + 1
    line_start = text.rfind("\n", 0, offset) + 1
    return line, offset - line_start + 1


class ParseError(Exception):
    """Error de entrada MiniTcl (léxico, sintáctico o de validación).

    Compatible con la firma original ``ParseError(message, span)``.
    """

    def __init__(self, message: str, span: Span, *, expected: str | None = None,
                 found: str | None = None, opening: Span | None = None,
                 stage: str = "syntax"):
        self.message = message
        self.span = span
        self.expected = expected
        self.found = found
        self.opening = opening
        self.stage = stage          # "lexer", "syntax", "expr" o "validation"
        self.line: int | None = None
        self.column: int | None = None
        self.snippet: str | None = None
        super().__init__(self._headline())

    def _headline(self) -> str:
        where = f"{self.span.source}:"
        if self.line is not None:
            where += f"{self.line}:{self.column}"
        else:
            where += f"{self.span.start}"
        text = f"{where}: {self.message}"
        if self.expected is not None or self.found is not None:
            text += f" (esperado: {self.expected or '-'}; encontrado: {self.found or '-'})"
        return text

    def attach_source(self, text: str) -> "ParseError":
        """Calcula línea, columna y fragmento a partir de la fuente normalizada."""
        if self.line is not None:
            return self
        self.line, self.column = line_column(text, self.span.start)
        line_start = text.rfind("\n", 0, self.span.start) + 1
        line_end = text.find("\n", self.span.start)
        if line_end < 0:
            line_end = len(text)
        source_line = text[line_start:line_end]
        width = max(1, min(self.span.end, line_end) - self.span.start)
        caret = " " * (self.span.start - line_start) + "^" * width
        self.snippet = f"{source_line}\n{caret}"
        if self.opening is not None:
            open_line, open_col = line_column(text, self.opening.start)
            self.snippet += f"\n(apertura en línea {open_line}, columna {open_col})"
        self.args = (self._headline(),)
        return self

    def report(self) -> str:
        """Mensaje completo con fragmento, si se adjuntó la fuente."""
        return self._headline() + (f"\n{self.snippet}" if self.snippet else "")


class TokenCursor:
    def __init__(self, tokens):
        self.tokens = tuple(tokens)
        if not self.tokens or self.tokens[-1].kind != "EOF":
            raise ValueError("El lexer debe agregar EOF")
        self.position = 0

    @property
    def current(self):
        return self.tokens[self.position]

    def accept(self, kind):
        if self.current.kind != kind:
            return None
        token = self.current
        if kind != "EOF":
            self.position += 1
        return token

    def expect(self, kind):
        token = self.accept(kind)
        if token is None:
            raise ParseError(
                f"Se esperaba {kind}; se encontró {self.current.kind}",
                self.current.span, expected=kind, found=self.current.kind)
        return token

    def skip(self, *kinds):
        while self.current.kind in kinds and self.current.kind != "EOF":
            self.position += 1


def cover(first: Span, last: Span):
    if first.source != last.source:
        raise ValueError("No combinar posiciones de fuentes diferentes")
    return Span(first.start, last.end, first.source)


def normalize_newlines(text: str) -> str:
    """CRLF y CR se convierten en LF antes de cualquier análisis."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def show_ast(value, indent=0):
    """Impresión estructurada sin Graphviz ni dependencias externas."""
    prefix = " " * indent
    if is_dataclass(value):
        print(prefix + type(value).__name__)
        for field in fields(value):
            if field.name == "span":
                continue
            item = getattr(value, field.name)
            print(prefix + "  " + field.name + ":")
            show_ast(item, indent + 4)
    elif isinstance(value, tuple):
        for item in value:
            show_ast(item, indent)
    else:
        print(prefix + repr(value))
