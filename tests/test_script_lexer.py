import pytest

from helpers import kinds
from minitcl import ParseError, tokenize_script


def test_word_boundaries_kept():
    assert kinds(tokenize_script("set x 10; puts hola")) == [
        "TEXT", "WS", "TEXT", "WS", "TEXT", "SEP", "WS", "TEXT", "WS", "TEXT", "EOF"]


def test_braced_value_and_span():
    toks = tokenize_script("puts {a {b} c}")
    braced = toks[2]
    assert braced.kind == "BRACED" and braced.value == "a {b} c"
    assert (braced.span.start, braced.span.end) == (5, 14)


def test_braced_keeps_escaped_braces():
    toks = tokenize_script(r"puts {a\{b\}c}")
    assert toks[2].value == r"a\{b\}c"


def test_brackets_and_quotes_are_text_inside_braces():
    toks = tokenize_script('puts {"] [x"}')
    assert toks[2].kind == "BRACED" and toks[2].value == '"] [x"'


def test_quoted_mode_semicolon_and_space_are_text():
    toks = tokenize_script('puts "a; b"')
    assert kinds(toks) == ["TEXT", "WS", "QOPEN", "TEXT", "QCLOSE", "EOF"]
    assert toks[3].value == "a; b"


def test_substitution_inside_quotes_restores_mode():
    toks = tokenize_script('puts "x [set y] z"')
    assert kinds(toks) == ["TEXT", "WS", "QOPEN", "TEXT", "LBRACKET", "TEXT", "WS",
                           "TEXT", "RBRACKET", "TEXT", "QCLOSE", "EOF"]
    assert toks[9].value == " z"


def test_variables():
    toks = tokenize_script("puts $a(3)${b}_c$d")
    var_tokens = [t for t in toks if t.kind == "VAR"]
    assert [(t.value, t.index) for t in var_tokens] == [("a", "3"), ("b", None), ("d", None)]


def test_escapes_decoded_outside_braces():
    toks = tokenize_script(r"puts a\ b\$c\n")
    assert toks[2].kind == "TEXT" and toks[2].value == "a b$c\n"


def test_comment_only_at_command_start():
    assert kinds(tokenize_script("# comentario")) == ["EOF"]
    assert kinds(tokenize_script("  # c\nputs x")) == ["WS", "SEP", "TEXT", "WS", "TEXT", "EOF"]
    toks = tokenize_script("puts a#b #dato")
    assert [t.value for t in toks if t.kind == "TEXT"] == ["puts", "a#b", "#dato"]


def test_comment_after_bracket_is_new_command_context():
    toks = tokenize_script("puts [# nada\nset x]")
    assert "TEXT" in kinds(toks) and toks[3].kind == "SEP"


def test_crlf_normalized():
    toks = tokenize_script("puts a\r\nputs b")
    assert toks[3].kind == "SEP" and toks[3].value == "\n"


@pytest.mark.parametrize("source", [
    "puts $a($i)", "puts $a()", "puts $", "puts ${}", r"puts \q", "puts a\\\nb",
    "puts {sin cierre", 'puts "sin cierre', "puts [set x 1",
    "puts {a}b", 'puts "a"b', "puts a{b", 'puts a"b',
])
def test_lexical_errors(source):
    with pytest.raises(ParseError) as info:
        tokenize_script(source)
    assert info.value.stage == "lexer"


def test_missing_brace_reports_opening():
    with pytest.raises(ParseError) as info:
        tokenize_script("puts {sin cierre")
    assert info.value.opening.start == 5
