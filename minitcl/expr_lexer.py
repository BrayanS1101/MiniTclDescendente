"""Lexer de expresiones de ``expr`` con ``sly.Lexer`` (sección 5).

Los patrones largos se definen antes que los cortos (``**`` antes de
``*``, ``<=`` antes de ``<``, ``==``/``!=`` antes de ``!``). ``eq``, ``ne``
y los booleanos se reconocen como palabras completas. ``[`` delega la
lectura balanceada al analizador manual mediante el callback
``read_substitution`` y produce un único token ``CMD_SUBST`` cuyo valor es
un ``Script``.

Los tokens con contenido (``NUMBER``, ``BOOL``, ``VAR``, ``STRING``,
``CMD_SUBST``) llevan como ``value`` un par ``(dato, Span)`` con el span
absoluto, ya desplazado por ``base_offset``.
"""
from __future__ import annotations

from sly import Lexer

from .model import ParseError, Span, Variable
from .script_lexer import decode_escape, scan_variable

BOOL_WORDS = {"true": True, "false": False, "yes": True, "no": False,
              "on": True, "off": False}


class ExprLexer(Lexer):
    tokens = {OR, AND, EQ, NE, STREQ, STRNE, LE, GE, LT, GT,          # noqa: F821
              POWER, PLUS, MINUS, TIMES, DIVIDE, MOD, NOT,              # noqa: F821
              LPAREN, RPAREN, NUMBER, BOOL, VAR, STRING, CMD_SUBST}     # noqa: F821
    ignore = " \t\r"

    # Operadores: largos antes que cortos.
    OR = r"\|\|"
    AND = r"&&"
    EQ = r"=="
    NE = r"!="
    LE = r"<="
    GE = r">="
    LT = r"<"
    GT = r">"
    POWER = r"\*\*"
    TIMES = r"\*"
    PLUS = r"\+"
    MINUS = r"-"
    DIVIDE = r"/"
    MOD = r"%"
    NOT = r"!"
    LPAREN = r"\("
    RPAREN = r"\)"

    def __init__(self, base_offset=0, source_name="<expr>", read_substitution=None):
        self.base_offset = base_offset
        self.source_name = source_name
        self.read_substitution = read_substitution

    def _span(self, start, end):
        return Span(self.base_offset + start, self.base_offset + end, self.source_name)

    @_(r"(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
    def NUMBER(self, t):
        raw = t.value
        value = float(raw) if any(c in raw for c in ".eE") else int(raw)
        t.value = (value, self._span(t.index, t.end))
        return t

    # Palabras completas: eq, ne y booleanos. Cualquier otra es error.
    @_(r"[A-Za-z_][A-Za-z0-9_]*")
    def BOOL(self, t):
        word = t.value
        if word == "eq":
            t.type = "STREQ"
        elif word == "ne":
            t.type = "STRNE"
        elif word in BOOL_WORDS:
            t.value = (BOOL_WORDS[word], self._span(t.index, t.end))
        else:
            raise ParseError(f"Palabra desnuda '{word}' no admitida en expr "
                             "(sin funciones ni cadenas sin comillas)",
                             self._span(t.index, t.end), expected="operando",
                             found=word, stage="expr")
        return t

    @_(r"\$")
    def VAR(self, t):
        name, index, end = scan_variable(self.text, t.index, self.base_offset,
                                         self.source_name, stage="expr")
        span = self._span(t.index, end)
        t.value = (Variable(name=name, index=index, span=span), span)
        self.index = t.end = end
        return t

    @_(r'"')
    def STRING(self, t):
        text = self.text
        pos = t.index + 1
        chars = []
        while pos < len(text):
            c = text[pos]
            if c == '"':
                end = pos + 1
                t.value = ("".join(chars), self._span(t.index, end))
                self.lineno += text.count("\n", t.index, end)
                self.index = t.end = end
                return t
            if c == "\\":
                ch, pos = decode_escape(text, pos, self.base_offset, self.source_name, "expr")
                chars.append(ch)
                continue
            if c in "$[":
                raise ParseError(f"'{c}' no escapado dentro de una cadena de expr "
                                 "(sin interpolación en este perfil)",
                                 self._span(pos, pos + 1), expected="carácter literal",
                                 found=c, stage="expr")
            chars.append(c)
            pos += 1
        raise ParseError('Cadena sin comillas de cierre en expr', self._span(len(text), len(text)),
                         expected='"', found="EOF", opening=self._span(t.index, t.index + 1),
                         stage="expr")

    @_(r"\[")
    def CMD_SUBST(self, t):
        if self.read_substitution is None:
            raise ParseError("Sustitución de comando sin callback read_substitution",
                             self._span(t.index, t.index + 1), stage="expr")
        script, end = self.read_substitution(self.text, t.index, self.base_offset,
                                             self.source_name)
        t.value = (script, self._span(t.index, end))
        self.lineno += self.text.count("\n", t.index, end)
        self.index = t.end = end
        return t

    @_(r"\n+")
    def ignore_newline(self, t):
        self.lineno += len(t.value)

    def error(self, t):
        position = self.base_offset + t.index
        raise ParseError(f"Carácter inválido en expr: {t.value[0]!r}",
                         Span(position, position + 1, self.source_name),
                         expected="operador u operando", found=t.value[0], stage="expr")
