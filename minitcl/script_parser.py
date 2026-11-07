"""Parser descendente recursivo de scripts MiniTcl (secciones 4, 10 y 11).

Gramática (EBNF) sobre los tokens de ``script_lexer``::

    program      = script, EOF ;
    script       = { WS | SEP }, [ command, { command_gap, command } ], { WS | SEP } ;
    command_gap  = { WS }, SEP, { WS | SEP } ;
    command      = word, { WS, word } ;
    word         = BRACED | quoted_word | bare_word ;
    quoted_word  = QOPEN, { part }, QCLOSE ;
    bare_word    = part, { part } ;
    part         = TEXT | VAR | substitution ;
    substitution = LBRACKET, script, RBRACKET ;

Cada no terminal es un método. Las decisiones se toman mirando un único
token (predicción LL(1) sobre tokens):

* FIRST(word) = {BRACED, QOPEN, TEXT, VAR, LBRACKET}
* FIRST(part) = {TEXT, VAR, LBRACKET}
* tras QOPEN, un QCLOSE inmediato da una palabra vacía;
* tras WS en un comando, se lee otra palabra solo si el token está en
  FIRST(word); si no, el espacio era final;
* tras LBRACKET, un RBRACKET inmediato da un script vacío.
"""
from __future__ import annotations

from .model import (Command, CommandSubstitution, Literal, ParseError, Part, Script,
                    Span, TokenCursor, Variable, Word, cover, normalize_newlines)
from .script_lexer import ScriptLexer


class ScriptParser(TokenCursor):
    WORD_START = {"TEXT", "VAR", "BRACED", "QOPEN", "LBRACKET"}
    PART_START = {"TEXT", "VAR", "LBRACKET"}

    def parse(self) -> Script:
        result = self.parse_script(stop="EOF")
        self.expect("EOF")
        return result

    def parse_script(self, stop="EOF") -> Script:
        start = self.current.span
        commands = []
        self.skip("WS", "SEP")
        while self.current.kind != stop:
            if self.current.kind == "EOF":
                raise ParseError(f"Falta {stop}", self.current.span,
                                 expected=stop, found="EOF")
            if self.current.kind == "RBRACKET":
                raise self.misplaced_close()
            commands.append(self.parse_command())
            if self.current.kind == stop:
                break
            if self.current.kind == "RBRACKET":
                raise self.misplaced_close()
            self.expect("SEP")
            self.skip("WS", "SEP")
        end = commands[-1].span if commands else self.current.span
        if not commands:
            # Script vacío: span de longitud cero en la posición actual.
            start = Span(self.current.span.start, self.current.span.start,
                         self.current.span.source)
            end = start
        return Script(commands=tuple(commands), span=cover(start, end))

    def misplaced_close(self) -> ParseError:
        return ParseError("Cierre ']' fuera de una sustitución de comando",
                          self.current.span, expected="palabra, separador o EOF",
                          found="RBRACKET")

    def parse_command(self) -> Command:
        words = [self.parse_word()]
        while self.accept("WS"):
            if self.current.kind not in self.WORD_START:
                break      # espacio final: no empieza otra palabra
            words.append(self.parse_word())
        return Command(words=tuple(words), span=cover(words[0].span, words[-1].span))

    # word = BRACED | quoted_word | bare_word
    def parse_word(self) -> Word:
        kind = self.current.kind
        if kind == "BRACED":
            return self.parse_braced_word()
        if kind == "QOPEN":
            return self.parse_quoted_word()
        if kind in self.PART_START:
            return self.parse_bare_word()
        raise ParseError(f"Se esperaba una palabra; se encontró {kind}",
                         self.current.span, expected="palabra", found=kind)

    # bare_word = part, { part }
    def parse_bare_word(self) -> Word:
        parts = [self.parse_part()]
        while self.current.kind in self.PART_START:
            parts.append(self.parse_part())
        return Word(parts=tuple(parts), mode="bare",
                    span=cover(parts[0].span, parts[-1].span))

    # quoted_word = QOPEN, { part }, QCLOSE
    def parse_quoted_word(self) -> Word:
        opening = self.expect("QOPEN")
        parts = []
        while self.current.kind in self.PART_START:
            parts.append(self.parse_part())
        if self.current.kind != "QCLOSE":
            raise ParseError("Faltan comillas de cierre", self.current.span,
                             expected="QCLOSE", found=self.current.kind,
                             opening=opening.span)
        closing = self.expect("QCLOSE")
        if self.current.kind not in ("WS", "SEP", "RBRACKET", "EOF"):
            raise ParseError("Texto después de cerrar una palabra entre comillas",
                             self.current.span, expected="WS, SEP, ] o EOF",
                             found=self.current.kind)
        return Word(parts=tuple(parts), mode="quoted",
                    span=cover(opening.span, closing.span))

    # BRACED produce un único Literal con el contenido sin interpretar
    def parse_braced_word(self) -> Word:
        token = self.expect("BRACED")
        inner = Span(token.span.start + 1, token.span.end - 1, token.span.source)
        literal = Literal(text=token.value, span=inner)
        if self.current.kind not in ("WS", "SEP", "RBRACKET", "EOF"):
            raise ParseError("Texto después de cerrar una palabra entre llaves",
                             self.current.span, expected="WS, SEP, ] o EOF",
                             found=self.current.kind)
        return Word(parts=(literal,), mode="braced", span=token.span)

    # part = TEXT | VAR | substitution
    def parse_part(self) -> Part:
        kind = self.current.kind
        if kind == "TEXT":
            token = self.expect("TEXT")
            return Literal(text=token.value, span=token.span)
        if kind == "VAR":
            token = self.expect("VAR")
            return Variable(name=token.value, index=token.index, span=token.span)
        if kind == "LBRACKET":
            return self.parse_substitution()
        raise ParseError(f"Se esperaba TEXT, VAR o '['; se encontró {kind}",
                         self.current.span, expected="parte de palabra", found=kind)

    # substitution = LBRACKET, script, RBRACKET
    def parse_substitution(self) -> CommandSubstitution:
        opening = self.expect("LBRACKET")
        script = self.parse_script(stop="RBRACKET")
        if self.current.kind != "RBRACKET":
            raise ParseError("Falta ']' que cierre la sustitución", self.current.span,
                             expected="RBRACKET", found=self.current.kind,
                             opening=opening.span)
        closing = self.expect("RBRACKET")
        return CommandSubstitution(script=script, span=cover(opening.span, closing.span))


def parse_minitcl(source: str, source_name: str = "<input>", *, base_offset: int = 0,
                  full_source: str | None = None) -> Script:
    """Fachada: lexer manual + parser descendente recursivo.

    ``base_offset`` permite reanalizar el interior de una palabra ``BRACED``
    conservando los offsets de la fuente completa (``full_source``), que se
    usa para calcular línea y columna de los diagnósticos.
    """
    text = normalize_newlines(source)
    try:
        tokens = ScriptLexer(text, source_name, base_offset).tokenize()
        return ScriptParser(tokens).parse()
    except ParseError as err:
        if full_source is not None:
            err.attach_source(normalize_newlines(full_source))
        elif base_offset == 0:
            err.attach_source(text)
        raise


def read_substitution(text: str, opening_index: int, base_offset: int,
                      source_name: str) -> tuple[Script, int]:
    """Callback para ``ExprLexer``: lee ``[ ... ]`` balanceado desde ``opening_index``.

    Devuelve el ``Script`` interior y el índice local inmediatamente
    posterior al ``]``. Respeta llaves, comillas y anidamiento porque usa el
    mismo lexer contextual que los scripts.
    """
    lexer = ScriptLexer(text, source_name, base_offset)
    tokens = lexer.tokenize_substitution(opening_index)
    parser = ScriptParser(tokens)
    node = parser.parse_substitution()
    parser.expect("EOF")
    return node.script, lexer.pos
