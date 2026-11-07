import pytest

from minitcl import ParseError, format_list, parse_list


@pytest.mark.parametrize("text,items", [
    ("", []),
    ("  a b\tc\nd  ", ["a", "b", "c", "d"]),
    ("{a b} c", ["a b", "c"]),
    ('"x y" {} ""', ["x y", "", ""]),
    ("$x [cmd] ;", ["$x", "[cmd]", ";"]),
    (r"a\ b \{", ["a b", "{"]),
    ("{a {b} c}", ["a {b} c"]),
])
def test_parse_list(text, items):
    assert parse_list(text) == items


@pytest.mark.parametrize("values", [
    [], ["a"], ["a b", "", "c"], ["{", "}", "}{", '"q"', "a\\b", "x\\"],
    ["con\nsalto", "tab\t", "{equilibrada}", "$v", "[c]", ";"],
])
def test_round_trip(values):
    assert parse_list(format_list(values)) == values


@pytest.mark.parametrize("text", ["{a", '"a', "{a}b", "a{b", 'a"b', r"\q"])
def test_list_errors(text):
    with pytest.raises(ParseError):
        parse_list(text)
