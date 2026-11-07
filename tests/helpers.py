from minitcl.model import (Binary, Constant, SubstitutionExpr, Unary, VariableExpr)


def expr_shape(node):
    """Proyección para comparar estructura sin depender de offsets."""
    if isinstance(node, Constant):
        return node.value
    if isinstance(node, VariableExpr):
        v = node.variable
        return "$" + v.name + (f"({v.index})" if v.index is not None else "")
    if isinstance(node, SubstitutionExpr):
        return ("[]", tuple(tuple(w.parts[0].text if len(w.parts) == 1 and hasattr(w.parts[0], "text")
                                  else w.mode for w in c.words)
                            for c in node.script.commands))
    if isinstance(node, Unary):
        return (node.operator, expr_shape(node.operand))
    if isinstance(node, Binary):
        return (node.operator, expr_shape(node.left), expr_shape(node.right))
    raise TypeError(type(node).__name__)


def kinds(tokens):
    return [t.kind for t in tokens]


def part_types(word):
    return [type(p).__name__ for p in word.parts]
