"""Parsing entry point: source text -> CompilationUnit."""

from __future__ import annotations

from pathlib import Path

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from osc2c.frontend.ast import CompilationUnit
from osc2c.frontend.generated.openscenario2Lexer import openscenario2Lexer
from osc2c.frontend.generated.openscenario2Parser import openscenario2Parser
from osc2c.frontend.transformer import AstTransformer


class ParseError(Exception):
    def __init__(self, source: str, errors: list[str]) -> None:
        self.source = source
        self.errors = list(errors)
        super().__init__(f"{source}: {self.errors[0]}" if self.errors else f"{source}: parse error")


class _CollectingListener(ErrorListener):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e) -> None:
        self.errors.append(f"line {line}:{column} {msg}")


def parse(text: str, source: str = "<string>") -> CompilationUnit:
    listener = _CollectingListener()

    lexer = openscenario2Lexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(listener)

    parser = openscenario2Parser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(listener)

    tree = parser.osc_file()
    if listener.errors:
        raise ParseError(source, listener.errors)
    return AstTransformer(source).visit(tree)


def parse_file(path: str | Path) -> CompilationUnit:
    file = Path(path)
    return parse(file.read_text(encoding="utf-8"), source=file.name)
