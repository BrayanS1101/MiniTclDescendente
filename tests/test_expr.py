import pytest
from sly import Lexer, Parser

from helpers import expr_shape
from minitcl import ExprLexer, ExprParser, ParseError, parse_minitcl_expr
from minitcl.model import SubstitutionExpr


def test_sly_inheritance():
    assert issubclass(ExprLexer, Lexer)
    assert issubclass(ExprParser, Parser)


def test_lalr_table_has_no_conflicts():
    table = ExprParser._lrtable
    assert table.sr_conflicts == [] and table.rr_conflicts == []


@pytest.mark.parametrize("source,shape", [
    ("42", 42),
    ("2 + 3 * 4", ("+", 2, ("*", 3, 4))),
    ("10 - 3 - 2", ("-", ("-", 10, 3), 2)),
    ("2 ** 3 ** 2", ("**", 2, ("**", 3, 2))),
    ("-2 ** 2", ("-", ("**", 2, 2))),
    ("2 ** -3", ("**", 2, ("-", 3))),
    ("8 / 2 * 3", ("*", ("/", 8, 2), 3)),
    ("-(4 + 1)", ("-", ("+", 4, 1))),
    ("(2 + 3) * 4", ("*", ("+", 2, 3), 4)),
    ("!$a || $b && $c", ("||", ("!", "$a"), ("&&", "$b", "$c"))),
    ("1 < 2 < 3", ("<", ("<", 1, 2), 3)),
    ("$a == 1 != 0", ("!=", ("==", "$a", 1), 0)),
    ('"a b" eq "c"', ("eq", "a b", "c")),
    ('$s ne "x"', ("ne", "$s", "x")),
    ("7 % 3 >= 1 <= 2", ("<=", (">=", ("%", 7, 3), 1), 2)),
    ("1.5e2 + .5", ("+", 150.0, 0.5)),
    ("true && off", ("&&", True, False)),
    ("+-1", ("+", ("-", 1))),
    ("$a(3) + ${b}", ("+", "$a(3)", "$b")),
])
def test_expression_shapes(source, shape):
    assert expr_shape(parse_minitcl_expr(source)) == shape


def test_logical_and_of_comparisons():
    node = parse_minitcl_expr("$x != 0 && 10 / $x > 1")
    assert expr_shape(node) == ("&&", ("!=", "$x", 0), (">", ("/", 10, "$x"), 1))


def test_command_substitution_is_not_executed():
    node = parse_minitcl_expr("0 && [error inesperado]")
    assert node.operator == "&&"
    assert isinstance(node.right, SubstitutionExpr)
    words = node.right.script.commands[0].words
    assert [w.parts[0].text for w in words] == ["error", "inesperado"]


def test_nested_substitution_with_braces_and_brackets():
    node = parse_minitcl_expr("$n * [factorial [expr {$n - 1}]]")
    sub = node.right
    inner = sub.script.commands[0].words[1].parts[0].script.commands[0]
    assert inner.words[1].mode == "braced" and inner.words[1].parts[0].text == "$n - 1"


def test_substitution_respects_braces_with_closing_bracket():
    node = parse_minitcl_expr("[puts {]}] + 1")
    assert node.operator == "+"
    assert node.left.script.commands[0].words[1].parts[0].text == "]"


def test_spans_with_base_offset():
    node = parse_minitcl_expr("$x + 3", base_offset=10, source_name="f.tcl")
    assert (node.span.start, node.span.end, node.span.source) == (10, 16, "f.tcl")
    assert (node.right.span.start, node.right.span.end) == (15, 16)


def test_substitution_spans_absolute():
    node = parse_minitcl_expr("1 + [set y]", base_offset=100)
    assert node.right.span.start == 104
    assert node.right.script.commands[0].span.start == 105


def test_multiline_expression():
    assert expr_shape(parse_minitcl_expr("1 +\n 2")) == ("+", 1, 2)


@pytest.mark.parametrize("source", [
    "2 + ", "2 3", "", "( 1", "1 )", "foo", "$", '"a$b"', '"a[b]"', '"sin', "1 ^ 2",
    "[set x", "2 ** ", "== 1",
])
def test_expression_errors(source):
    with pytest.raises(ParseError) as info:
        parse_minitcl_expr(source)
    assert info.value.stage in ("expr", "lexer", "syntax")
