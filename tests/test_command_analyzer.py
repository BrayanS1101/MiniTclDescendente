import pytest

from helpers import expr_shape
from minitcl import ParseError, analyze_command, analyze_source, parse_minitcl
from minitcl.model import Binary, Script


def word(source, cmd=0, w=1):
    return parse_minitcl(source).commands[cmd].words[w]


def test_expr_argument_goes_to_sly():
    result = analyze_source("set r [expr {$x + 3}]")
    (expr,) = result.exprs.values()
    assert isinstance(expr, Binary) and expr_shape(expr) == ("+", "$x", 3)


def test_expr_offsets_inside_braced_word():
    source = "set r [expr {$x + 3}]"
    result = analyze_source(source)
    (word_node, expr), = result.exprs.items()
    assert expr.span.start == word_node.span.start + 1
    assert source[expr.span.start:expr.span.end] == "$x + 3"


def test_if_conditions_and_bodies():
    source = "if {$a} then {puts 1} elseif {$b} {puts 2} else {puts 3}"
    result = analyze_source(source)
    assert len(result.exprs) == 2 and len(result.bodies) == 3
    for w, body in result.bodies.items():
        assert isinstance(body, Script)
        assert source[body.span.start:body.span.end] == w.parts[0].text


def test_same_facade_for_expr_and_conditions(monkeypatch):
    import minitcl.command_analyzer as ca
    calls = []
    original = ca.parse_minitcl_expr

    def spy(*args, **kw):
        calls.append(args[0])
        return original(*args, **kw)

    monkeypatch.setattr(ca, "parse_minitcl_expr", spy)
    analyze_source("expr {1}; if {2} {}; while {3} {}; for {} {4} {} {}")
    assert calls == ["1", "2", "3", "4"]


def test_for_while_foreach_catch_proc_bodies():
    result = analyze_source(
        "for {set i 0} {$i < 3} {incr i} {puts $i}\n"
        "while {1} {break}\n"
        "foreach x {1 2} {continue}\n"
        "catch {error x} m\n"
        "proc f {a b} {return [expr {$a + $b}]}")
    assert len(result.bodies) == 3 + 1 + 1 + 1 + 1
    assert list(result.params.values()) == [("a", "b")]
    assert "f" in result.procedures


def test_data_blocks_not_reinterpreted():
    result = analyze_source("set m {if mal formado}; puts {[x}; list {a {b}}; dict create k {v w}")
    assert result.bodies == {} and result.exprs == {}


def test_structural_ast_preserved():
    script = parse_minitcl("while {1} {puts x}")
    result = analyze_source("while {1} {puts x}")
    assert result.script == script


def test_static_errors_reported_even_if_branch_not_taken():
    with pytest.raises(ParseError):
        analyze_source("if {0} {puts {sin}cierre}")


def test_nested_substitution_scripts_are_validated():
    with pytest.raises(ParseError) as info:
        analyze_source("puts [set a 1 2 3]")
    assert info.value.stage == "validation"


def test_call_to_later_procedure_is_ok():
    analyze_source("puts [doble 2]\nproc doble {x} {return [expr {$x * 2}]}")


def test_analyze_command_single():
    cmd = parse_minitcl("expr {1 + 2}").commands[0]
    result = analyze_command(cmd)
    assert len(result.exprs) == 1


# --- Matriz de la sección 16: errores de validación y de expresión ----------

@pytest.mark.parametrize("source,stage", [
    ("set x 1 2", "validation"),
    ("if {1} {puts si} else", "validation"),
    ("expr {2 + }", "expr"),
    ("expr {2 3}", "expr"),
    ("proc f {x x} {return $x}", "validation"),
    ("set accion puts; $accion hola", "validation"),
    ("expr $x", "validation"),
    ("while {1}", "validation"),
    ("break", "validation"),
    ("return 1", "validation"),
    ("proc set {} {}", "validation"),
    ("proc g {1x} {}", "validation"),
    ("set $x 1", "validation"),
    ("dict create a", "validation"),
    ("dict frob a b", "validation"),
    ("string length", "validation"),
    ("puts -x hola", "validation"),
    ("if {1} {puts a} foo", "validation"),
    ("for {set i 0} {$i <} {incr i} {}", "expr"),
    ("proc h {} {while {1} {proc k {} {break}}}", "validation"),
])
def test_validation_errors(source, stage):
    with pytest.raises(ParseError) as info:
        analyze_source(source)
    assert info.value.stage == stage
    assert info.value.line is not None and info.value.column is not None


def test_short_circuit_case_is_valid():
    result = analyze_source("expr {0 && [error inesperado]}")
    (expr,) = result.exprs.values()
    assert expr.operator == "&&"


def test_valid_misc():
    analyze_source("puts {if mal formado}")
    analyze_source("puts -nonewline hola")
    analyze_source("set a(3) 8; incr a(3); unset a(3); global x y")
    analyze_source("lappend l 1 2; lset l 0 9; lindex $l 0; llength $l")
    analyze_source("dict set d k v; dict get $d k; dict exists $d k")
    analyze_source("string compare a b; string toupper x; split a,b ,; join {a b} -")
