"""Lexical scopes and the symbol table (Definition Pass output)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from osc2c.frontend.ast import Node
from osc2c.semantics.types import (
    CompositeTypeInfo,
    EnumTypeInfo,
    TypeInfo,
    UnitInfo,
    describe_type,
)


class SymbolKind(str, Enum):
    NAMESPACE = "namespace"
    PHYSICAL_TYPE = "physical_type"
    UNIT = "unit"
    ENUM = "enum"
    ENUM_MEMBER = "enum_member"
    STRUCT = "struct"
    ACTOR = "actor"
    SCENARIO = "scenario"
    ACTION = "action"
    MODIFIER = "modifier"
    FIELD = "field"
    PARAMETER = "parameter"
    VARIABLE = "variable"
    GLOBAL_PARAMETER = "global_parameter"
    EVENT = "event"
    METHOD = "method"


TYPE_KINDS = {
    SymbolKind.PHYSICAL_TYPE,
    SymbolKind.ENUM,
    SymbolKind.STRUCT,
    SymbolKind.ACTOR,
    SymbolKind.SCENARIO,
    SymbolKind.ACTION,
}
COMPOSITE_KINDS = {
    SymbolKind.STRUCT,
    SymbolKind.ACTOR,
    SymbolKind.SCENARIO,
    SymbolKind.ACTION,
    SymbolKind.MODIFIER,
}
VALUE_KINDS = {
    SymbolKind.FIELD,
    SymbolKind.PARAMETER,
    SymbolKind.VARIABLE,
    SymbolKind.GLOBAL_PARAMETER,
    SymbolKind.ENUM_MEMBER,
}


@dataclass(eq=False)
class Symbol:
    name: str
    kind: SymbolKind
    type: TypeInfo | None = None
    node: Node | None = None
    scope: "Scope | None" = None
    unit: UnitInfo | None = None
    enum: EnumTypeInfo | None = None
    enum_value: int | None = None
    namespace: str = ""
    builtin: bool = False

    @property
    def qualified_name(self) -> str:
        if self.kind is SymbolKind.ENUM_MEMBER and self.enum is not None:
            return f"{self.enum.name}!{self.name}"
        if self.scope is not None:
            return f"{self.scope.path}::{self.name}" if self.scope.path else self.name
        if self.namespace:
            return f"{self.namespace}::{self.name}"
        return self.name

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "type": describe_type(self.type),
            "qualified_name": self.qualified_name,
            "builtin": self.builtin,
            "line": self.node.span.line if self.node is not None else None,
        }


class Scope:
    """A lexical scope. Namespaces are flat scopes keyed by `a::b` paths."""

    def __init__(
        self,
        name: str,
        parent: "Scope | None" = None,
        kind: str = "namespace",
        owner: CompositeTypeInfo | None = None,
    ) -> None:
        self.name = name
        self.parent = parent
        self.kind = kind
        self.owner = owner
        self.symbols: dict[str, Symbol] = {}
        self.modifiers: dict[str, Symbol] = {}
        self.children: list[Scope] = []
        self.uses: list[str] = []
        self.path = f"{parent.path}::{name}" if parent and parent.path else name
        if parent is not None:
            parent.children.append(self)

    def define(self, symbol: Symbol) -> Symbol | None:
        """Insert a symbol. Returns the existing symbol on a duplicate."""
        store = self.modifiers if symbol.kind is SymbolKind.MODIFIER else self.symbols
        existing = store.get(symbol.name)
        if existing is not None:
            return existing
        symbol.scope = self
        store[symbol.name] = symbol
        return None

    def lookup_local(self, name: str) -> Symbol | None:
        symbol = self.symbols.get(name)
        if symbol is not None:
            return symbol
        return self.modifiers.get(name)

    def lookup_all(self, name: str) -> list[Symbol]:
        result: list[Symbol] = []
        symbol = self.symbols.get(name)
        if symbol is not None:
            result.append(symbol)
        modifier = self.modifiers.get(name)
        if modifier is not None:
            result.append(modifier)
        return result

    def lookup(self, name: str) -> Symbol | None:
        scope: Scope | None = self
        while scope is not None:
            symbol = scope.symbols.get(name)
            if symbol is None:
                symbol = scope.modifiers.get(name)
            if symbol is not None:
                return symbol
            scope = scope.parent
        return None

    def add_use(self, path: str) -> None:
        if path not in self.uses:
            self.uses.append(path)

    def chain(self) -> Iterator["Scope"]:
        scope: Scope | None = self
        while scope is not None:
            yield scope
            scope = scope.parent

    def iter_symbols(self, include_builtin: bool = True) -> Iterator[Symbol]:
        for store in (self.symbols, self.modifiers):
            for symbol in store.values():
                if include_builtin or not symbol.builtin:
                    yield symbol

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        total = len(self.symbols) + len(self.modifiers)
        return f"Scope({self.path or '<global>'!r}, {total} symbols)"
