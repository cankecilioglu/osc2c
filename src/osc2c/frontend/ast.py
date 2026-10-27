"""Typed AST for ASAM OpenSCENARIO 2.1.

Frontend invariant: these nodes carry syntax only. Nothing here resolves
names, checks types or converts units -- that is the middle-end's job.
Every node keeps a source span so later phases can report precise errors.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True)
class Span:
    source: str
    line: int
    column: int
    end_line: int
    end_column: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


def _encode(value: Any, include_spans: bool) -> Any:
    if isinstance(value, Node):
        return value.to_dict(include_spans=include_spans)
    if isinstance(value, (list, tuple)):
        return [_encode(item, include_spans) for item in value]
    return value


@dataclass(eq=False)
class Node:
    span: Span

    def to_dict(self, include_spans: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {"kind": type(self).__name__}
        for field in fields(self):
            if field.name == "span":
                continue
            result[field.name] = _encode(getattr(self, field.name), include_spans)
        if include_spans:
            result["span"] = self.span.to_dict()
        return result

    def walk(self):
        """Yield this node and every descendant, depth first, in field order."""
        stack = [self]
        while stack:
            node = stack.pop()
            yield node
            children: list[Node] = []
            for field in fields(node):
                if field.name == "span":
                    continue
                value = getattr(node, field.name)
                if isinstance(value, Node):
                    children.append(value)
                elif isinstance(value, (list, tuple)):
                    children.extend(item for item in value if isinstance(item, Node))
            stack.extend(reversed(children))


class Expr(Node):
    pass


class TypeRef(Node):
    pass


class Condition(Node):
    pass


class Arg(Node):
    pass


# ---------------------------------------------------------------- expressions


@dataclass(eq=False)
class IntLiteral(Expr):
    value: int


@dataclass(eq=False)
class FloatLiteral(Expr):
    value: float


@dataclass(eq=False)
class PhysicalLiteral(Expr):
    value: float
    unit: str


@dataclass(eq=False)
class BoolLiteral(Expr):
    value: bool


@dataclass(eq=False)
class StringLiteral(Expr):
    value: str


@dataclass(eq=False)
class EnumValueRef(Expr):
    enum: str | None
    member: str


@dataclass(eq=False)
class ListLiteral(Expr):
    elements: list[Expr]


@dataclass(eq=False)
class RangeLiteral(Expr):
    start: Expr
    end: Expr


@dataclass(eq=False)
class Identifier(Expr):
    parts: list[str]


@dataclass(eq=False)
class FieldAccess(Expr):
    target: Expr
    field: str


@dataclass(eq=False)
class Cast(Expr):
    target: Expr
    type: TypeRef


@dataclass(eq=False)
class TypeTest(Expr):
    target: Expr
    type: TypeRef


@dataclass(eq=False)
class ElementAccess(Expr):
    target: Expr
    index: Expr


@dataclass(eq=False)
class Call(Expr):
    target: Expr
    args: list[Arg]


@dataclass(eq=False)
class UnaryOp(Expr):
    op: str
    operand: Expr


@dataclass(eq=False)
class BinaryOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass(eq=False)
class TernaryOp(Expr):
    condition: Expr
    then: Expr
    otherwise: Expr


@dataclass(eq=False)
class ItExpr(Expr):
    pass


# ------------------------------------------------------------------ arguments


@dataclass(eq=False)
class PositionalArg(Arg):
    value: Expr


@dataclass(eq=False)
class NamedArg(Arg):
    name: str
    value: Expr


@dataclass(eq=False)
class ArgSpec(Node):
    name: str
    type: TypeRef
    default: Expr | None


# ---------------------------------------------------------------------- types


@dataclass(eq=False)
class PrimitiveType(TypeRef):
    name: str


@dataclass(eq=False)
class NamedType(TypeRef):
    name: str


@dataclass(eq=False)
class ListType(TypeRef):
    element: TypeRef


@dataclass(eq=False)
class RangeType(TypeRef):
    element: TypeRef


# ---------------------------------------------------------------------- units


@dataclass(eq=False)
class SiExponent(Node):
    unit: str
    exponent: int


@dataclass(eq=False)
class SiBaseSpec(Node):
    exponents: list[SiExponent]


@dataclass(eq=False)
class SiUnitSpec(Node):
    exponents: list[SiExponent]
    factor: float | None
    offset: float | None


# ------------------------------------------------------------------- prelude


@dataclass(eq=False)
class ImportDecl(Node):
    reference: str
    is_path: bool


@dataclass(eq=False)
class UseDecl(Node):
    namespaces: list[str]


@dataclass(eq=False)
class CompilationUnit(Node):
    imports: list[ImportDecl]
    uses: list[UseDecl]
    declarations: list[Node]


@dataclass(eq=False)
class NamespaceDecl(Node):
    name: str
    uses: list[str]


@dataclass(eq=False)
class ExportSpec(Node):
    name: str
    wildcard: bool


@dataclass(eq=False)
class ExportDecl(Node):
    specifications: list[ExportSpec]


# ------------------------------------------------------------- declarations


@dataclass(eq=False)
class InheritsSpec(Node):
    name: str
    field: str | None
    condition: Expr | None


@dataclass(eq=False)
class PhysicalTypeDecl(Node):
    name: str
    base: SiBaseSpec


@dataclass(eq=False)
class UnitDecl(Node):
    name: str
    type_name: str
    spec: SiUnitSpec


@dataclass(eq=False)
class EnumMember(Node):
    name: str
    value: int | EnumValueRef | None


@dataclass(eq=False)
class EnumDecl(Node):
    name: str
    members: list[EnumMember]


@dataclass(eq=False)
class EnumExtensionDecl(Node):
    name: str
    members: list[EnumMember]


@dataclass(eq=False)
class StructDecl(Node):
    name: str
    inherits: InheritsSpec | None
    members: list[Node]


@dataclass(eq=False)
class ActorDecl(Node):
    name: str
    inherits: InheritsSpec | None
    members: list[Node]


@dataclass(eq=False)
class ScenarioDecl(Node):
    name: str
    inherits: InheritsSpec | None
    members: list[Node]


@dataclass(eq=False)
class ActionDecl(Node):
    name: str
    inherits: InheritsSpec | None
    members: list[Node]


@dataclass(eq=False)
class ModifierDecl(Node):
    actor: str | None
    name: str
    of: str | None
    members: list[Node]


@dataclass(eq=False)
class StructuredExtensionDecl(Node):
    name: str
    members: list[Node]


@dataclass(eq=False)
class PrimitiveExtensionDecl(Node):
    name: str
    members: list[Node]


# ------------------------------------------------------------------- members


@dataclass(eq=False)
class ParameterDecl(Node):
    names: list[str]
    type: TypeRef
    default: Expr | None
    constraints: list[Node]


@dataclass(eq=False)
class VariableDecl(Node):
    names: list[str]
    type: TypeRef
    value: Expr | None
    sample: SampleExpr | None


@dataclass(eq=False)
class SampleExpr(Node):
    value: Expr
    event: EventSpec
    default: Expr | None


@dataclass(eq=False)
class EventReference(Node):
    path: Expr | None
    name: str


@dataclass(eq=False)
class EventSpec(Node):
    reference: EventReference | None
    field: str | None
    condition: Condition | None


@dataclass(eq=False)
class BoolCond(Condition):
    expr: Expr


@dataclass(eq=False)
class RiseCond(Condition):
    expr: Expr


@dataclass(eq=False)
class FallCond(Condition):
    expr: Expr


@dataclass(eq=False)
class ElapsedCond(Condition):
    expr: Expr


@dataclass(eq=False)
class EveryCond(Condition):
    expr: Expr
    offset: Expr | None


@dataclass(eq=False)
class EventDecl(Node):
    name: str
    parameters: list[ArgSpec] | None
    specification: EventSpec | None


@dataclass(eq=False)
class KeepConstraint(Node):
    qualifier: str | None
    expr: Expr


@dataclass(eq=False)
class RemoveDefault(Node):
    target: Expr


@dataclass(eq=False)
class MethodImpl(Node):
    mode: str
    expression: Expr | None
    external: str | None
    args: list[Arg] | None


@dataclass(eq=False)
class MethodDecl(Node):
    name: str
    parameters: list[ArgSpec] | None
    return_type: TypeRef | None
    implementation: MethodImpl


@dataclass(eq=False)
class CoverageDecl(Node):
    mode: str
    args: list[Arg]


@dataclass(eq=False)
class ModifierApplication(Node):
    target: Expr | None
    name: str
    args: list[Arg]


@dataclass(eq=False)
class OnDirective(Node):
    specification: EventSpec
    members: list[Node]


@dataclass(eq=False)
class DoDirective(Node):
    member: Node


@dataclass(eq=False)
class LabeledStatement(Node):
    label: str
    statement: Node


@dataclass(eq=False)
class Composition(Node):
    operator: str
    args: list[Arg]
    members: list[Node]
    with_clause: BehaviorWith | None


@dataclass(eq=False)
class BehaviorWith(Node):
    members: list[Node]


@dataclass(eq=False)
class BehaviorInvocation(Node):
    target: Expr | None
    name: str
    args: list[Arg]
    with_clause: BehaviorWith | None


@dataclass(eq=False)
class WaitDirective(Node):
    specification: EventSpec


@dataclass(eq=False)
class EmitDirective(Node):
    name: str
    args: list[Arg] | None


@dataclass(eq=False)
class CallDirective(Node):
    invocation: Expr


@dataclass(eq=False)
class UntilDirective(Node):
    specification: EventSpec
