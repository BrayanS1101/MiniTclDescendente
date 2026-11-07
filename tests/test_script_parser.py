import pytest

from helpers import part_types
from minitcl import ParseError, ScriptParser, parse_minitcl
from minitcl.model import CommandSubstitution, Span, Token


# --- Pruebas del material suministrado en el cuaderno -----------------------

def test_skeleton_empty_and_trailing_space():
    assert ScriptParser([Token("EOF", "", Span(0, 0))]).parse().commands == ()
    trailing = [Token("TEXT", "puts", Span(0, 4)), Token("WS", " ", Span(4, 5)),
                Token("EOF", "", Span(5, 5))]
    assert len(ScriptParser(trailing).parse().commands[0].words) == 1


def test_skeleton_outer_close_rejected():
    with pytest.raises(ParseError):
        ScriptParser([Token("RBRACKET", "]", Span(0, 1)), Token("EOF", "", Span(1, 1))]).parse()


def test_notebook_student_tests():
    script = parse_minitcl('puts "Hola $nombre"; set x {a b}')
    assert len(script.commands) == 2
    assert len(script.commands[0].words) == 2
    greeting = script.commands[0].words[1]
    assert greeting.mode == "quoted"
    assert part_types(greeting) == ["Literal", "Variable"]
    block = script.commands[1].words[2]
    assert block.mode == "braced" and block.parts[0].text == "a b"


# --- Matriz de la sección 16: casos estructuralmente válidos ----------------

def test_empty_arguments_different_modes():
    q = parse_minitcl('puts ""').commands[0].words
    b = parse_minitcl("puts {}").commands[0].words
    assert len(q) == 2 and q[1].mode == "quoted" and q[1].parts == ()
    assert len(b) == 2 and b[1].mode == "braced" and b[1].parts[0].text == ""


def test_multi_part_word():
    words = parse_minitcl("set x hola_${nombre}_fin").commands[0].words
    assert len(words) == 3
    assert part_types(words[2]) == ["Literal", "Variable", "Literal"]
    assert [getattr(p, "text", getattr(p, "name", None)) for p in words[2].parts] == \
        ["hola_", "nombre", "_fin"]


def test_substitution_with_two_commands():
    words = parse_minitcl("puts [set x 1; set x]").commands[0].words
    sub = words[1].parts[0]
    assert isinstance(sub, CommandSubstitution) and len(sub.script.commands) == 2


def test_nested_substitutions():
    words = parse_minitcl("puts [list [set x] y]").commands[0].words
    inner = words[1].parts[0].script.commands[0]
    assert len(inner.words) == 3
    assert isinstance(inner.words[1].parts[0], CommandSubstitution)


def test_braced_literal_without_commands():
    w = parse_minitcl("puts {a {b} c}").commands[0].words[1]
    assert w.mode == "braced" and w.parts[0].text == "a {b} c"


def test_braced_keeps_backslashes():
    w = parse_minitcl(r"puts {a\{b\}c}").commands[0].words[1]
    assert w.parts[0].text == r"a\{b\}c"


@pytest.mark.parametrize("source,text", [("puts a#b", "a#b"), ("puts #dato", "#dato")])
def test_hash_inside_argument(source, text):
    words = parse_minitcl(source).commands[0].words
    assert len(words) == 2 and words[1].parts[0].text == text


def test_comment_is_empty_script():
    assert parse_minitcl("# comentario").commands == ()


def test_semicolon_inside_quotes():
    script = parse_minitcl('puts "a; b"')
    assert len(script.commands) == 1
    assert script.commands[0].words[1].parts[0].text == "a; b"


def test_array_reference():
    var = parse_minitcl("puts $a(3)").commands[0].words[1].parts[0]
    assert (var.name, var.index) == ("a", "3")


def test_if_inside_braces_is_text():
    w = parse_minitcl("puts {if mal formado}").commands[0].words[1]
    assert w.mode == "braced" and w.parts[0].text == "if mal formado"


def test_set_with_braced_variable_is_literal():
    w = parse_minitcl("set x {$y}").commands[0].words[2]
    assert part_types(w) == ["Literal"] and w.parts[0].text == "$y"


def test_spans():
    script = parse_minitcl("set x {a b}")
    word = script.commands[0].words[2]
    assert (word.span.start, word.span.end) == (6, 11)
    assert (word.parts[0].span.start, word.parts[0].span.end) == (7, 10)
    assert (script.span.start, script.span.end) == (0, 11)


def test_empty_substitution():
    sub = parse_minitcl("puts []").commands[0].words[1].parts[0]
    assert sub.script.commands == ()


def test_separators_and_blank_lines():
    script = parse_minitcl("\n\n  set a 1 ;;\n\tset b 2  \n")
    assert len(script.commands) == 2


# --- Matriz de la sección 16: errores estructurales ------------------------

@pytest.mark.parametrize("source", [
    "puts $a($i)", "puts {sin cierre", 'puts "sin cierre', "puts [set x 1",
    "puts {a}b", 'puts "a"b', "puts ]", "]", "puts [a]]",
])
def test_structural_errors(source):
    with pytest.raises(ParseError):
        parse_minitcl(source)


def test_close_outside_context_message():
    with pytest.raises(ParseError) as info:
        parse_minitcl("puts ]")
    assert "fuera" in info.value.message and info.value.found == "RBRACKET"


@pytest.mark.parametrize("source", [
    "set x 1 2", "if {1} {puts si} else", "expr {2 + }", "expr {2 3}",
    "expr {0 && [error inesperado]}", "proc f {x x} {return $x}",
    "set accion puts; $accion hola",
])
def test_structurally_valid_cases(source):
    parse_minitcl(source)    # el error, si existe, aparece en una etapa posterior
