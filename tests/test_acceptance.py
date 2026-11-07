"""Programas de aceptación de la sección 15: producen AST sin ejecutarse."""
from pathlib import Path

import pytest

from helpers import expr_shape
from minitcl import analyze_source
from minitcl.model import CommandSubstitution, SubstitutionExpr

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize("name,commands,bodies,exprs", [
    ("factorial.tcl", 2, 2, 3),
    ("estadisticas.tcl", 5, 1, 2),
    ("histograma.tcl", 3, 3, 2),
    ("for_catch.tcl", 5, 5, 4),
])
def test_acceptance_programs(name, commands, bodies, exprs):
    source = (EXAMPLES / name).read_text(encoding="utf-8")
    result = analyze_source(source, name)
    assert len(result.script.commands) == commands
    assert len(result.bodies) == bodies
    assert len(result.exprs) == exprs
    for word, body in result.bodies.items():
        assert source[body.span.start:body.span.end].strip() == word.parts[0].text.strip()


def test_factorial_structure():
    source = (EXAMPLES / "factorial.tcl").read_text(encoding="utf-8")
    result = analyze_source(source, "factorial.tcl")
    proc = result.script.commands[0]
    assert [w.mode for w in proc.words] == ["bare", "bare", "braced", "braced"]
    assert result.params[proc.words[2]] == ("n",)
    body = result.bodies[proc.words[3]]
    if_cmd, return_cmd = body.commands
    assert expr_shape(result.exprs[if_cmd.words[1]]) == ("<=", "$n", 1)
    sub = return_cmd.words[1].parts[0]
    assert isinstance(sub, CommandSubstitution)
    expr_word = sub.script.commands[0].words[1]
    outer = result.exprs[expr_word]
    assert outer.operator == "*" and isinstance(outer.right, SubstitutionExpr)


def test_for_catch_continue_and_array():
    source = (EXAMPLES / "for_catch.tcl").read_text(encoding="utf-8")
    result = analyze_source(source, "for_catch.tcl")
    set_cmd = result.script.commands[0]
    assert set_cmd.words[1].parts[0].text == "tabla(3)"
    last = result.script.commands[-1].words[1].parts[0]
    assert (last.name, last.index) == ("tabla", "3")
    shapes = sorted(map(str, (expr_shape(e) for e in result.exprs.values())))
    assert str(("/", 10, 0)) in shapes
