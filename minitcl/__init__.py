"""MiniTcl educativo 1.1: lexer manual + parser descendente recursivo de
scripts, y lexer/parser SLY (LALR(1)) para expresiones."""
from .model import *  # noqa: F401,F403
from .model import ParseError, show_ast
from .script_lexer import ScriptLexer, tokenize_script
from .script_parser import ScriptParser, parse_minitcl, read_substitution
from .expr_lexer import ExprLexer
from .expr_parser import ExprParser, parse_minitcl_expr
from .list_reader import parse_list, format_list
from .command_analyzer import (AnalysisResult, analyze_command, analyze_script,
                               analyze_source)

__all__ = [
    "ParseError", "show_ast", "ScriptLexer", "tokenize_script", "ScriptParser",
    "parse_minitcl", "read_substitution", "ExprLexer", "ExprParser",
    "parse_minitcl_expr", "parse_list", "format_list", "AnalysisResult",
    "analyze_command", "analyze_script", "analyze_source",
]
