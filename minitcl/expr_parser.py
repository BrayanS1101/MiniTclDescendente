"""Parser LALR(1) de expresiones con ``sly.Parser`` (sección 5).

La gramática es por niveles; los binarios usan recursividad izquierda
(asociación a la izquierda) y la potencia ``power : primary POWER unary``
asocia a la derecha y deja a los unarios por encima de ``**`` como
operando izquierdo: ``-2 ** 2 = -(2 ** 2)`` y ``2 ** -3 = 2 ** (-3)``.
No se usa tabla ``precedence``: los niveles ya la definen, y la tabla
generada no tiene conflictos.

Las acciones solo construyen nodos del AST; nunca evalúan.
"""
from __future__ import annotations

from sly import Parser

from .expr_lexer import ExprLexer
from .model import (Binary, Constant, Expr, ParseError, Span, SubstitutionExpr, Unary,
                    VariableExpr, cover, normalize_newlines)
from .script_parser import read_substitution


class ExprParser(Parser):
    tokens = ExprLexer.tokens
    start = "expression"

    def __init__(self, text="", base_offset=0, source_name="<expr>"):
        self.text = text
        self.base_offset = base_offset
        self.source_name = source_name

    def _binary(self, op, left, right):
        return Binary(operator=op, left=left, right=right, span=cover(left.span, right.span))

    def _unary(self, op, index, operand):
        start = Span(self.base_offset + index, self.base_offset + index + 1, self.source_name)
        return Unary(operator=op, operand=operand, span=cover(start, operand.span))

    # expression = logical_or
    @_("logical_or")
    def expression(self, p):
        return p.logical_or

    # logical_or = logical_or "||" logical_and | logical_and
    @_("logical_or OR logical_and")
    def logical_or(self, p):
        return self._binary("||", p.logical_or, p.logical_and)

    @_("logical_and")
    def logical_or(self, p):  # noqa: F811
        return p.logical_and

    # logical_and = logical_and "&&" equality | equality
    @_("logical_and AND equality")
    def logical_and(self, p):
        return self._binary("&&", p.logical_and, p.equality)

    @_("equality")
    def logical_and(self, p):  # noqa: F811
        return p.equality

    # equality = equality ("==" | "!=" | "eq" | "ne") relational | relational
    @_("equality EQ relational", "equality NE relational",
       "equality STREQ relational", "equality STRNE relational")
    def equality(self, p):
        return self._binary(p[1], p.equality, p.relational)

    @_("relational")
    def equality(self, p):  # noqa: F811
        return p.relational

    # relational = relational ("<" | "<=" | ">" | ">=") additive | additive
    @_("relational LT additive", "relational LE additive",
       "relational GT additive", "relational GE additive")
    def relational(self, p):
        return self._binary(p[1], p.relational, p.additive)

    @_("additive")
    def relational(self, p):  # noqa: F811
        return p.additive

    # additive = additive ("+" | "-") multiplicative | multiplicative
    @_("additive PLUS multiplicative", "additive MINUS multiplicative")
    def additive(self, p):
        return self._binary(p[1], p.additive, p.multiplicative)

    @_("multiplicative")
    def additive(self, p):  # noqa: F811
        return p.multiplicative

    # multiplicative = multiplicative ("*" | "/" | "%") unary | unary
    @_("multiplicative TIMES unary", "multiplicative DIVIDE unary",
       "multiplicative MOD unary")
    def multiplicative(self, p):
        return self._binary(p[1], p.multiplicative, p.unary)

    @_("unary")
    def multiplicative(self, p):  # noqa: F811
        return p.unary

    # unary = ("+" | "-" | "!") unary | power
    @_("PLUS unary", "MINUS unary", "NOT unary")
    def unary(self, p):
        return self._unary(p[0], p.index, p.unary)

    @_("power")
    def unary(self, p):  # noqa: F811
        return p.power

    # power = primary "**" unary | primary
    @_("primary POWER unary")
    def power(self, p):
        return self._binary("**", p.primary, p.unary)

    @_("primary")
    def power(self, p):  # noqa: F811
        return p.primary

    # primary = NUMBER | BOOL | VAR | STRING | "(" expression ")" | CMD_SUBST
    @_("NUMBER", "BOOL", "STRING")
    def primary(self, p):
        value, span = p[0]
        return Constant(value=value, span=span)

    @_("VAR")
    def primary(self, p):  # noqa: F811
        variable, span = p.VAR
        return VariableExpr(variable=variable, span=span)

    @_("CMD_SUBST")
    def primary(self, p):  # noqa: F811
        script, span = p.CMD_SUBST
        return SubstitutionExpr(script=script, span=span)

    @_("LPAREN expression RPAREN")
    def primary(self, p):  # noqa: F811
        return p.expression        # los paréntesis no generan nodo propio

    def error(self, token):
        if token is None:
            position = self.base_offset + len(self.text)
            raise ParseError("Fin inesperado de expresión",
                             Span(position, position, self.source_name),
                             expected="operando", found="fin", stage="expr")
        position = self.base_offset + token.index
        end = getattr(token, "end", token.index + 1) or token.index + 1
        raise ParseError(f"Token inesperado en expr: {token.type}",
                         Span(position, self.base_offset + end, self.source_name),
                         expected="operador u operando", found=token.type, stage="expr")


def parse_minitcl_expr(source: str, *, base_offset=0, source_name="<expr>",
                       full_source: str | None = None) -> Expr:
    """Fachada única para ``expr`` y las condiciones de ``if``/``while``/``for``.

    Recibe solo el contenido literal (sin ``expr`` ni las llaves). Crea
    instancias nuevas de lexer y parser en cada llamada para que una
    sustitución anidada no sobrescriba un análisis en curso.
    """
    text = normalize_newlines(source)
    lexer = ExprLexer(base_offset=base_offset, source_name=source_name,
                      read_substitution=read_substitution)
    parser = ExprParser(text=text, base_offset=base_offset, source_name=source_name)
    try:
        result = parser.parse(lexer.tokenize(text))
        if result is None:   # SLY devuelve None para una entrada vacía
            raise ParseError("Expresión vacía", Span(base_offset, base_offset, source_name),
                             expected="expresión", found="fin", stage="expr")
        return result
    except ParseError as err:
        if full_source is not None:
            err.attach_source(normalize_newlines(full_source))
        elif base_offset == 0:
            err.attach_source(text)
        raise
