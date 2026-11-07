import pytest

from minitcl import ParseError, analyze_source, parse_minitcl, parse_minitcl_expr


def test_line_column_and_snippet():
    with pytest.raises(ParseError) as info:
        parse_minitcl("set a 1\nputs {abc", "prueba.tcl")
    err = info.value
    assert err.span.source == "prueba.tcl"
    assert err.expected == "}" and err.found == "EOF"
    assert err.opening is not None
    assert (err.opening.start, err.opening.end) == (13, 14)
    assert "prueba.tcl:2:" in str(err)
    assert "apertura en línea 2, columna 6" in err.report()


def test_error_inside_body_points_to_full_source():
    source = "proc f {} {\n    set x [expr {1 +}]\n}"
    with pytest.raises(ParseError) as info:
        analyze_source(source, "f.tcl")
    err = info.value
    assert err.stage == "expr"
    assert err.line == 2
    assert "f.tcl:2:" in str(err)


def test_error_inside_condition_column():
    source = "while {$i <} {incr i}"
    with pytest.raises(ParseError) as info:
        analyze_source(source)
    assert (info.value.line, info.value.column) == (1, 12)


def test_expr_error_has_expected_and_found():
    with pytest.raises(ParseError) as info:
        parse_minitcl_expr("2 3")
    assert info.value.found == "NUMBER" and info.value.expected


def test_parse_error_is_raised_not_generic():
    # Las fachadas solo deben lanzar ParseError para entradas incorrectas.
    for bad in ["puts ]", "puts {", "puts $"]:
        with pytest.raises(ParseError):
            parse_minitcl(bad)
