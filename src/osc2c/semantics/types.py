"""Semantic types for the OSC 2.1 middle-end.

The frontend AST is purely syntactic. This module defines the resolved
type universe: primitives, physical types with SI dimensions, enums,
composite actor/struct/behavior types, lists and callable signatures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from osc2c.frontend.ast import Node
    from osc2c.semantics.scope import Scope, Symbol


BASE_UNITS = ("kg", "m", "s", "A", "K", "mol", "cd", "rad")
Dimension = tuple[int, ...]


def dimension(**exponents: int) -> Dimension:
    """Build an SI dimension tuple from named exponents, e.g. m=1, s=-1."""
    unknown = set(exponents) - set(BASE_UNITS)
    if unknown:
        raise ValueError(f"unknown SI base unit(s): {sorted(unknown)}")
    return tuple(int(exponents.get(unit, 0)) for unit in BASE_UNITS)


def dimension_add(left: Dimension, right: Dimension) -> Dimension:
    return tuple(a + b for a, b in zip(left, right))


def dimension_sub(left: Dimension, right: Dimension) -> Dimension:
    return tuple(a - b for a, b in zip(left, right))


def dimension_label(value: Dimension) -> str:
    parts = []
    for unit, exponent in zip(BASE_UNITS, value):
        if exponent == 0:
            continue
        parts.append(unit if exponent == 1 else f"{unit}^{exponent}")
    return "1" if not parts else "*".join(parts)


class TypeInfo:
    """Base class for every resolved type."""


@dataclass(frozen=True)
class PrimitiveTypeInfo(TypeInfo):
    name: str


@dataclass(frozen=True)
class PhysicalTypeInfo(TypeInfo):
    name: str
    dimension: Dimension

    def compatible(self, other: TypeInfo) -> bool:
        return isinstance(other, PhysicalTypeInfo) and self.dimension == other.dimension


INT = PrimitiveTypeInfo("int")
UINT = PrimitiveTypeInfo("uint")
FLOAT = PrimitiveTypeInfo("float")
BOOL = PrimitiveTypeInfo("bool")
STRING = PrimitiveTypeInfo("string")
PRIMITIVES = {item.name: item for item in (INT, UINT, FLOAT, BOOL, STRING)}


@dataclass(frozen=True)
class UnitInfo:
    name: str
    physical: PhysicalTypeInfo
    factor: float = 1.0
    offset: float = 0.0

    def to_si(self, value: float) -> float:
        return value * self.factor + self.offset

    def from_si(self, value: float) -> float:
        return (value - self.offset) / self.factor


@dataclass(frozen=True)
class ListTypeInfo(TypeInfo):
    element: TypeInfo


@dataclass(frozen=True)
class RangeTypeInfo(TypeInfo):
    element: TypeInfo


@dataclass(frozen=True)
class ErrorTypeInfo(TypeInfo):
    """Recovery marker: an error was already reported."""


@dataclass(frozen=True)
class UnknownTypeInfo(TypeInfo):
    """Permissive marker for external domain members not loaded yet."""

    reason: str = ""


ERROR = ErrorTypeInfo()
UNKNOWN = UnknownTypeInfo()


@dataclass(eq=False)
class EnumTypeInfo(TypeInfo):
    name: str
    namespace: str = ""
    members: dict[str, int] = field(default_factory=dict)
    member_symbols: dict[str, "Symbol"] = field(default_factory=dict)
    node: "Node | None" = None
    builtin: bool = False


@dataclass(frozen=True)
class ParameterInfo:
    name: str
    type: TypeInfo | None
    has_default: bool = False


@dataclass(frozen=True)
class FunctionTypeInfo(TypeInfo):
    params: tuple[ParameterInfo, ...] = ()
    result: TypeInfo | None = None


@dataclass(eq=False)
class CompositeTypeInfo(TypeInfo):
    """Struct, actor, scenario, action or modifier definition."""

    name: str
    kind: str
    namespace: str = ""
    base_name: str | None = None
    base: "CompositeTypeInfo | None" = None
    target_actor: str | None = None
    of_behavior: str | None = None
    fields: dict[str, "Symbol"] = field(default_factory=dict)
    methods: dict[str, "Symbol"] = field(default_factory=dict)
    events: dict[str, "Symbol"] = field(default_factory=dict)
    modifiers: dict[str, "Symbol"] = field(default_factory=dict)
    signature: FunctionTypeInfo | None = None
    scope: "Scope | None" = None
    node: "Node | None" = None
    builtin: bool = False

    @property
    def qualified_name(self) -> str:
        return f"{self.namespace}::{self.name}" if self.namespace else self.name


def describe_type(value: TypeInfo | None) -> str:
    if value is None:
        return "void"
    if isinstance(value, PrimitiveTypeInfo):
        return value.name
    if isinstance(value, PhysicalTypeInfo):
        return value.name or dimension_label(value.dimension)
    if isinstance(value, (EnumTypeInfo, CompositeTypeInfo)):
        return value.name
    if isinstance(value, ListTypeInfo):
        return f"list of {describe_type(value.element)}"
    if isinstance(value, RangeTypeInfo):
        return f"range of {describe_type(value.element)}"
    if isinstance(value, FunctionTypeInfo):
        params = ", ".join(
            f"{item.name}: {describe_type(item.type)}" for item in value.params
        )
        return f"({params}) -> {describe_type(value.result)}"
    if isinstance(value, ErrorTypeInfo):
        return "<error>"
    if isinstance(value, UnknownTypeInfo):
        return "<unknown>"
    return str(value)


def is_numeric(value: TypeInfo | None) -> bool:
    return isinstance(value, PrimitiveTypeInfo) and value.name in ("int", "uint", "float")


def is_unknown(value: TypeInfo | None) -> bool:
    return isinstance(value, (ErrorTypeInfo, UnknownTypeInfo))


def is_assignable(actual: TypeInfo | None, expected: TypeInfo | None) -> bool:
    """Conservative assignment compatibility; returns True on recovery types."""
    if is_unknown(actual) or is_unknown(expected):
        return True
    if expected is None:
        return actual is None
    if actual is None:
        return False
    if actual is expected or actual == expected:
        return True
    if isinstance(actual, PhysicalTypeInfo) and isinstance(expected, PhysicalTypeInfo):
        return actual.dimension == expected.dimension
    if isinstance(actual, PrimitiveTypeInfo) and isinstance(expected, PrimitiveTypeInfo):
        return expected.name == "float" and actual.name in ("int", "uint")
    if isinstance(actual, ListTypeInfo) and isinstance(expected, ListTypeInfo):
        return is_assignable(actual.element, expected.element)
    if isinstance(actual, CompositeTypeInfo) and isinstance(expected, CompositeTypeInfo):
        current: CompositeTypeInfo | None = actual
        while current is not None:
            if current is expected:
                return True
            current = current.base
    return False


def common_type(left: TypeInfo | None, right: TypeInfo | None) -> TypeInfo | None:
    if is_unknown(left):
        return right
    if is_unknown(right):
        return left
    if left is right or left == right:
        return left
    if is_numeric(left) and is_numeric(right):
        if describe_type(left) == "float" or describe_type(right) == "float":
            return FLOAT
        return INT
    if isinstance(left, PhysicalTypeInfo) and isinstance(right, PhysicalTypeInfo):
        if left.dimension == right.dimension:
            return left if left.name else right
    return ERROR


def promote_numeric(left: TypeInfo, right: TypeInfo) -> TypeInfo:
    if describe_type(left) == "float" or describe_type(right) == "float":
        return FLOAT
    return INT


def composite_member(value: CompositeTypeInfo, name: str, attribute: str) -> "Symbol | None":
    current: CompositeTypeInfo | None = value
    while current is not None:
        table = getattr(current, attribute)
        if name in table:
            return table[name]
        current = current.base
    return None


def iter_composite_chain(value: CompositeTypeInfo) -> Any:
    current: CompositeTypeInfo | None = value
    while current is not None:
        yield current
        current = current.base
