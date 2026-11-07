"""Validación de comandos y reanálisis de cuerpos estáticos (secciones 6 y 13).

Esta pasada se ejecuta **después** del análisis estructural. Conserva el
AST original y construye vistas adicionales:

* ``bodies``: palabra ``BRACED`` → ``Script`` (parser manual descendente).
* ``exprs``: palabra ``BRACED`` → ``Expr`` (fachada SLY ``parse_minitcl_expr``).
* ``params``: palabra de parámetros de ``proc`` → nombres.

Comprueba aridad, formas de los incorporados y el perfil estático del
curso. No ejecuta nada: no consulta variables ni llama procedimientos.
Se detiene en el primer error (``ParseError``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .expr_parser import parse_minitcl_expr
from .list_reader import parse_list
from .model import (Command, CommandSubstitution, Expr, Literal, ParseError, Script,
                    SubstitutionExpr, Unary, Binary, Word, normalize_newlines)
from .script_parser import parse_minitcl

IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\([A-Za-z0-9_.:\-]+\))?")

BUILTINS = {
    "set", "unset", "incr", "append", "puts", "expr", "if", "while", "for",
    "foreach", "proc", "return", "break", "continue", "global", "catch", "error",
    "list", "llength", "lindex", "lappend", "lset", "dict", "string", "split", "join",
}


@dataclass
class Context:
    in_proc: bool = False
    in_loop: bool = False


@dataclass
class AnalysisResult:
    script: Script                                   # AST estructural intacto
    bodies: dict[Word, Script] = field(default_factory=dict)
    exprs: dict[Word, Expr] = field(default_factory=dict)
    params: dict[Word, tuple[str, ...]] = field(default_factory=dict)
    procedures: dict[str, Command] = field(default_factory=dict)

    def body(self, word: Word) -> Script:
        return self.bodies[word]

    def expr(self, word: Word) -> Expr:
        return self.exprs[word]


def literal_text(word: Word) -> str | None:
    """Texto de una palabra sin sustituciones; ``None`` si es calculada."""
    if all(isinstance(p, Literal) for p in word.parts):
        return "".join(p.text for p in word.parts)
    return None


class CommandAnalyzer:
    def __init__(self, result: AnalysisResult, source: str | None = None):
        self.result = result
        self.source = normalize_newlines(source) if source is not None else None

    # -- utilidades ---------------------------------------------------------
    def fail(self, message, node, *, expected=None, found=None):
        err = ParseError(message, node.span, expected=expected, found=found,
                         stage="validation")
        if self.source is not None:
            err.attach_source(self.source)
        return err

    def arity(self, cmd: Command, name: str, low: int, high: int | None, usage: str):
        count = len(cmd.words) - 1
        if count < low or (high is not None and count > high):
            raise self.fail(f"Aridad inválida en '{name}': se recibieron {count} argumentos",
                            cmd, expected=usage, found=f"{count} argumentos")

    def require_name(self, word: Word, what="nombre de variable"):
        text = literal_text(word)
        if text is None or not NAME.fullmatch(text):
            raise self.fail(f"Se esperaba {what} literal (sin '$')", word,
                            expected="identificador o a(indice)", found=text or "palabra calculada")
        return text

    def require_identifier(self, word: Word, what="identificador"):
        text = literal_text(word)
        if text is None or not IDENTIFIER.fullmatch(text):
            raise self.fail(f"Se esperaba {what}", word, expected="identificador",
                            found=text or "palabra calculada")
        return text

    def require_braced(self, word: Word, what: str):
        if word.mode != "braced":
            raise self.fail(f"Perfil estático: {what} debe escribirse entre llaves", word,
                            expected=f"{what} entre llaves", found=f"palabra {word.mode}")
        return word.parts[0]

    # -- reanálisis ---------------------------------------------------------
    def body(self, word: Word, ctx: Context) -> Script:
        literal = self.require_braced(word, "el cuerpo")
        script = parse_minitcl(literal.text, literal.span.source,
                               base_offset=literal.span.start, full_source=self.source)
        self.result.bodies[word] = script
        self.visit_script(script, ctx)
        return script

    def test(self, word: Word, ctx: Context) -> Expr:
        literal = self.require_braced(word, "la expresión")
        expr = parse_minitcl_expr(literal.text, base_offset=literal.span.start,
                                  source_name=literal.span.source, full_source=self.source)
        self.result.exprs[word] = expr
        self.visit_expr(expr, ctx)
        return expr

    def visit_expr(self, expr: Expr, ctx: Context):
        if isinstance(expr, SubstitutionExpr):
            self.visit_script(expr.script, ctx)
        elif isinstance(expr, Unary):
            self.visit_expr(expr.operand, ctx)
        elif isinstance(expr, Binary):
            self.visit_expr(expr.left, ctx)
            self.visit_expr(expr.right, ctx)

    def visit_words(self, cmd: Command, ctx: Context):
        """Visita los scripts de los corchetes ya producidos estructuralmente."""
        for word in cmd.words:
            for part in word.parts:
                if isinstance(part, CommandSubstitution):
                    self.visit_script(part.script, ctx)

    def visit_script(self, script: Script, ctx: Context):
        for cmd in script.commands:
            self.analyze(cmd, ctx)

    # -- formas de comandos --------------------------------------------------
    def analyze(self, cmd: Command, ctx: Context):
        self.visit_words(cmd, ctx)
        name = literal_text(cmd.words[0])
        if name is None:
            raise self.fail("Nombre de comando calculado: válido estructuralmente pero "
                            "fuera del perfil estático", cmd.words[0],
                            expected="nombre literal", found="palabra calculada")
        handler = getattr(self, f"cmd_{name}", None)
        if handler is not None and name in BUILTINS:
            handler(cmd, ctx)
        # Cualquier otro nombre es call_cmd: un procedimiento definido antes
        # o después; no es error sintáctico.

    def cmd_set(self, cmd, ctx):
        self.arity(cmd, "set", 1, 2, "set nombre ?valor?")
        self.require_name(cmd.words[1])

    def cmd_unset(self, cmd, ctx):
        self.arity(cmd, "unset", 1, 1, "unset nombre")
        self.require_name(cmd.words[1])

    def cmd_incr(self, cmd, ctx):
        self.arity(cmd, "incr", 1, 2, "incr nombre ?incremento?")
        self.require_name(cmd.words[1])

    def cmd_append(self, cmd, ctx):
        self.arity(cmd, "append", 2, None, "append nombre valor ?valor ...?")
        self.require_name(cmd.words[1])

    def cmd_puts(self, cmd, ctx):
        self.arity(cmd, "puts", 1, 2, "puts ?-nonewline? texto")
        if len(cmd.words) == 3 and literal_text(cmd.words[1]) != "-nonewline":
            raise self.fail("Opción desconocida de puts", cmd.words[1],
                            expected="-nonewline", found=literal_text(cmd.words[1]))

    def cmd_expr(self, cmd, ctx):
        self.arity(cmd, "expr", 1, 1, "expr {expresión}")
        self.test(cmd.words[1], ctx)

    def cmd_if(self, cmd, ctx):
        words = cmd.words
        i = 1

        def need(kind):
            if i >= len(words):
                raise self.fail(f"Forma incompleta de 'if': falta {kind}", cmd,
                                expected=kind, found="fin del comando")
            return words[i]

        self.test(need("condición"), ctx); i += 1
        if i < len(words) and literal_text(words[i]) == "then":
            i += 1
        self.body(need("cuerpo"), ctx); i += 1
        while i < len(words) and literal_text(words[i]) == "elseif":
            i += 1
            self.test(need("condición de elseif"), ctx); i += 1
            if i < len(words) and literal_text(words[i]) == "then":
                i += 1
            self.body(need("cuerpo de elseif"), ctx); i += 1
        if i < len(words) and literal_text(words[i]) == "else":
            i += 1
            self.body(need("cuerpo de else"), ctx); i += 1
        if i < len(words):
            raise self.fail("Argumento inesperado en 'if'", words[i],
                            expected="elseif, else o fin", found=literal_text(words[i]))

    def cmd_while(self, cmd, ctx):
        self.arity(cmd, "while", 2, 2, "while {test} {cuerpo}")
        self.test(cmd.words[1], ctx)
        self.body(cmd.words[2], Context(ctx.in_proc, True))

    def cmd_for(self, cmd, ctx):
        self.arity(cmd, "for", 4, 4, "for {inicio} {test} {paso} {cuerpo}")
        self.body(cmd.words[1], ctx)
        self.test(cmd.words[2], ctx)
        self.body(cmd.words[3], ctx)
        self.body(cmd.words[4], Context(ctx.in_proc, True))

    def cmd_foreach(self, cmd, ctx):
        self.arity(cmd, "foreach", 3, 3, "foreach variable lista {cuerpo}")
        self.require_identifier(cmd.words[1], "variable de foreach")
        self.body(cmd.words[3], Context(ctx.in_proc, True))

    def cmd_proc(self, cmd, ctx):
        self.arity(cmd, "proc", 3, 3, "proc nombre {parámetros} {cuerpo}")
        name = self.require_identifier(cmd.words[1], "nombre de procedimiento")
        if name in BUILTINS:
            raise self.fail(f"No se puede redefinir el incorporado '{name}'", cmd.words[1],
                            expected="nombre nuevo", found=name)
        params_word = cmd.words[2]
        literal = self.require_braced(params_word, "la lista de parámetros")
        names = parse_list(literal.text, base_offset=literal.span.start,
                           source_name=literal.span.source)
        seen = set()
        for param in names:
            if not IDENTIFIER.fullmatch(param):
                raise self.fail(f"Parámetro inválido '{param}'", params_word,
                                expected="identificador", found=param)
            if param in seen:
                raise self.fail(f"Parámetro duplicado '{param}'", params_word,
                                expected="nombres únicos", found=param)
            seen.add(param)
        self.result.params[params_word] = tuple(names)
        self.result.procedures[name] = cmd
        self.body(cmd.words[3], Context(in_proc=True, in_loop=False))

    def cmd_return(self, cmd, ctx):
        self.arity(cmd, "return", 0, 1, "return ?valor?")
        if not ctx.in_proc:
            raise self.fail("'return' solo es válido dentro de un procedimiento", cmd)

    def cmd_break(self, cmd, ctx):
        self.arity(cmd, "break", 0, 0, "break")
        if not ctx.in_loop:
            raise self.fail("'break' requiere un ciclo en el procedimiento actual", cmd)

    def cmd_continue(self, cmd, ctx):
        self.arity(cmd, "continue", 0, 0, "continue")
        if not ctx.in_loop:
            raise self.fail("'continue' requiere un ciclo en el procedimiento actual", cmd)

    def cmd_global(self, cmd, ctx):
        self.arity(cmd, "global", 1, None, "global nombre ?nombre ...?")
        for word in cmd.words[1:]:
            self.require_identifier(word, "nombre global")

    def cmd_catch(self, cmd, ctx):
        self.arity(cmd, "catch", 1, 2, "catch {cuerpo} ?variable?")
        self.body(cmd.words[1], ctx)
        if len(cmd.words) == 3:
            self.require_identifier(cmd.words[2], "variable de catch")

    def cmd_error(self, cmd, ctx):
        self.arity(cmd, "error", 1, 1, "error mensaje")

    # -- biblioteca de datos ------------------------------------------------
    def cmd_list(self, cmd, ctx):
        pass

    def cmd_llength(self, cmd, ctx):
        self.arity(cmd, "llength", 1, 1, "llength lista")

    def cmd_lindex(self, cmd, ctx):
        self.arity(cmd, "lindex", 2, 2, "lindex lista indice")

    def cmd_lappend(self, cmd, ctx):
        self.arity(cmd, "lappend", 1, None, "lappend nombre ?valor ...?")
        self.require_name(cmd.words[1])

    def cmd_lset(self, cmd, ctx):
        self.arity(cmd, "lset", 3, 3, "lset nombre indice valor")
        self.require_name(cmd.words[1])

    def cmd_dict(self, cmd, ctx):
        self.arity(cmd, "dict", 1, None, "dict subcomando ...")
        sub = literal_text(cmd.words[1])
        count = len(cmd.words) - 2
        if sub == "create":
            if count % 2:
                raise self.fail("'dict create' exige un número par de argumentos", cmd,
                                expected="pares clave valor", found=f"{count} argumentos")
        elif sub in ("get", "exists"):
            if count != 2:
                raise self.fail(f"Aridad inválida en 'dict {sub}'", cmd,
                                expected=f"dict {sub} diccionario clave", found=f"{count} argumentos")
        elif sub == "set":
            if count != 3:
                raise self.fail("Aridad inválida en 'dict set'", cmd,
                                expected="dict set nombre clave valor", found=f"{count} argumentos")
            self.require_name(cmd.words[2])
        else:
            raise self.fail("Subcomando de dict desconocido", cmd.words[1],
                            expected="create, get, exists o set", found=sub or "palabra calculada")

    def cmd_string(self, cmd, ctx):
        self.arity(cmd, "string", 1, None, "string subcomando ...")
        sub = literal_text(cmd.words[1])
        count = len(cmd.words) - 2
        expected = {"length": 1, "tolower": 1, "toupper": 1, "compare": 2}
        if sub not in expected:
            raise self.fail("Subcomando de string desconocido", cmd.words[1],
                            expected="length, tolower, toupper o compare",
                            found=sub or "palabra calculada")
        if count != expected[sub]:
            raise self.fail(f"Aridad inválida en 'string {sub}'", cmd,
                            expected=f"{expected[sub]} argumentos", found=f"{count} argumentos")

    def cmd_split(self, cmd, ctx):
        self.arity(cmd, "split", 1, 2, "split texto ?separadores?")

    def cmd_join(self, cmd, ctx):
        self.arity(cmd, "join", 1, 2, "join lista ?separador?")


def analyze_command(command: Command, *, source: str | None = None,
                    context: Context | None = None,
                    result: AnalysisResult | None = None) -> AnalysisResult:
    """Valida un comando y reanaliza sus cuerpos y condiciones estáticos."""
    if result is None:
        result = AnalysisResult(script=Script(commands=(command,), span=command.span))
    CommandAnalyzer(result, source).analyze(command, context or Context())
    return result


def analyze_script(script: Script, *, source: str | None = None) -> AnalysisResult:
    result = AnalysisResult(script=script)
    CommandAnalyzer(result, source).visit_script(script, Context())
    return result


def analyze_source(source: str, source_name: str = "<input>") -> AnalysisResult:
    """Análisis completo: estructural + validación + cuerpos y expresiones."""
    script = parse_minitcl(source, source_name)
    return analyze_script(script, source=source)
