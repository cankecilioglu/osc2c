"""Semantic middle-end: definition pass + resolution pass.

The builder follows the paper's ModelBuilder architecture:

1. Definition pass -- walk the AST and populate namespaces, type scopes and
   members. No expression is evaluated here.
2. Resolution pass -- bind type references, resolve inheritance, check units,
   arguments, assignments and conditions, and annotate the AST through the
   `SemanticModel` maps (`expr_types`, `type_refs`, `resolved`, `units`).

The AST itself stays immutable; annotations live on the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator, Sequence

from osc2c.frontend import ast
from osc2c.semantics import stdlib
from osc2c.semantics.diagnostics import Diagnostics, Severity
from osc2c.semantics.scope import (
    COMPOSITE_KINDS,
    TYPE_KINDS,
    VALUE_KINDS,
    Scope,
    Symbol,
    SymbolKind,
)
from osc2c.semantics.types import (
    BOOL,
    ERROR,
    FLOAT,
    INT,
    PRIMITIVES,
    STRING,
    UNKNOWN,
    CompositeTypeInfo,
    EnumTypeInfo,
    FunctionTypeInfo,
    ListTypeInfo,
    ParameterInfo,
    PhysicalTypeInfo,
    PrimitiveTypeInfo,
    RangeTypeInfo,
    TypeInfo,
    UnitInfo,
    UnknownTypeInfo,
    common_type,
    composite_member,
    describe_type,
    dimension,
    dimension_add,
    dimension_label,
    dimension_sub,
    is_assignable,
    is_numeric,
    is_unknown,
    promote_numeric,
)

TIME_DIMENSION = dimension(s=1)

_UNIT_TERM_RE = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)?)"
    r"(?:\^(?P<exponent>[+-]?\d+))?"
)

_KIND_LABELS = {
    SymbolKind.PHYSICAL_TYPE: "a physical type",
    SymbolKind.UNIT: "a unit",
    SymbolKind.ENUM: "an enum",
    SymbolKind.ENUM_MEMBER: "an enum member",
    SymbolKind.STRUCT: "a struct",
    SymbolKind.ACTOR: "an actor",
    SymbolKind.SCENARIO: "a scenario",
    SymbolKind.ACTION: "an action",
    SymbolKind.MODIFIER: "a modifier",
    SymbolKind.FIELD: "a field",
    SymbolKind.PARAMETER: "a parameter",
    SymbolKind.VARIABLE: "a variable",
    SymbolKind.GLOBAL_PARAMETER: "a global parameter",
    SymbolKind.EVENT: "an event",
    SymbolKind.METHOD: "a method",
}

_INHERIT_COMPAT = {
    "struct": {"struct"},
    "actor": {"actor"},
    "scenario": {"scenario", "action"},
    "action": {"scenario", "action"},
    "modifier": {"modifier"},
}

_INDEX_KINDS = {SymbolKind.PHYSICAL_TYPE, SymbolKind.ENUM, SymbolKind.STRUCT, SymbolKind.ACTOR}


@dataclass
class SemanticModel:
    unit: ast.CompilationUnit | None
    root: Scope
    namespaces: dict[str, Scope] = field(default_factory=dict)
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
    expr_types: dict[int, TypeInfo | None] = field(default_factory=dict)
    type_refs: dict[int, TypeInfo | None] = field(default_factory=dict)
    resolved: dict[int, Symbol] = field(default_factory=dict)
    unit_literals: dict[int, UnitInfo] = field(default_factory=dict)
    composites: list[CompositeTypeInfo] = field(default_factory=list)

    def namespace(self, path: str) -> Scope:
        scope = self.namespaces.get(path)
        if scope is None:
            scope = Scope(path.rpartition("::")[2] or "", parent=self.root)
            self.namespaces[path] = scope
        return scope

    def type_of(self, node: ast.Node) -> TypeInfo | None:
        return self.expr_types.get(id(node))

    def type_ref_of(self, node: ast.TypeRef) -> TypeInfo | None:
        return self.type_refs.get(id(node))

    def symbol_at(self, node: ast.Node) -> Symbol | None:
        return self.resolved.get(id(node))

    def unit_of(self, node: ast.Node) -> UnitInfo | None:
        return self.unit_literals.get(id(node))

    def symbol_table(self, include_builtin: bool = False) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for path in sorted(self.namespaces):
            symbols = [
                symbol.to_dict()
                for symbol in self.namespaces[path].iter_symbols(include_builtin)
            ]
            if symbols:
                result[path or "<global>"] = symbols
        for composite in sorted(self.composites, key=lambda item: item.qualified_name):
            if composite.builtin and not include_builtin:
                continue
            if composite.scope is None:
                continue
            symbols = [
                symbol.to_dict()
                for symbol in composite.scope.iter_symbols(include_builtin)
            ]
            if symbols:
                result[composite.qualified_name] = symbols
        return result


@dataclass
class _Context:
    scope: Scope
    namespace: str
    current_type: CompositeTypeInfo | None = None
    it_type: TypeInfo | None = None


def _declares_standard_namespace(
    unit: ast.CompilationUnit, extras: Sequence[ast.CompilationUnit]
) -> bool:
    """True when the real ASAM library is part of the unit set."""
    standard = {stdlib.STDTYPES_NS, stdlib.STANDARD_NS}
    for candidate in (unit, *extras):
        for declaration in candidate.declarations:
            if isinstance(declaration, ast.NamespaceDecl):
                name = declaration.name.strip().replace(".", "::")
                if name in standard:
                    return True
    return False


def _parameter_has_default(declaration: ast.ParameterDecl) -> bool:
    """`keep(default ...)` supplies a default even without an `= value` initializer."""
    if declaration.default is not None:
        return True
    return any(
        isinstance(constraint, ast.KeepConstraint) and constraint.qualifier == "default"
        for constraint in declaration.constraints
    )


def _optional_signature(signature: FunctionTypeInfo | None) -> FunctionTypeInfo | None:
    """Standard-library parameters are optional; only comments say otherwise."""
    if signature is None:
        return None
    return FunctionTypeInfo(
        tuple(
            ParameterInfo(param.name, param.type, has_default=True)
            for param in signature.params
        ),
        signature.result,
    )


class ModelBuilder:
    def __init__(self, *, builtin_stdlib: bool = True) -> None:
        root = Scope("")
        self.model = SemanticModel(None, root)
        self.model.namespaces[""] = root
        self._pending_units: list[tuple[Symbol, ast.UnitDecl]] = []
        self._pending_extensions: list[tuple[ast.Node, str]] = []
        self._pending_uses: list[tuple[str, ast.Span, Scope]] = []
        self._member_decls: dict[int, list[ast.Node]] = {}
        self._global_params: list[tuple[ast.ParameterDecl, str]] = []
        self._behavior_nodes: list[tuple[CompositeTypeInfo, ast.Node]] = []
        self._exports: list[tuple[ast.ExportDecl, str]] = []
        self._implicit_actor_fields: dict[str, Symbol] = {}
        self._builtin_types: dict[str, TypeInfo] = {}
        self._builtin_modifiers: dict[str, Symbol] = {}
        self._use_builtin_stdlib = builtin_stdlib
        self._builtins_installed = False

    # ------------------------------------------------------------- public API

    def analyze(
        self,
        unit: ast.CompilationUnit,
        extra_units: Sequence[ast.CompilationUnit] = (),
    ) -> SemanticModel:
        self.model.unit = unit
        if self._use_builtin_stdlib and not _declares_standard_namespace(
            unit, extra_units
        ):
            self._install_builtins()
        for extra in extra_units:
            self._declare_unit(extra)
        self._declare_unit(unit)
        self._validate_uses()
        self._resolve_units()
        self._resolve_inheritance()
        self._resolve_extensions()
        self._resolve_signatures()
        self._validate_inheritance_conditions()
        self._check_exports()
        self._check_bodies()
        return self.model

    # --------------------------------------------------------------- builtins

    def _install_builtins(self) -> None:
        if self._builtins_installed:
            return
        self._builtins_installed = True
        types_scope = self.model.namespace(stdlib.STDTYPES_NS)
        standard_scope = self.model.namespace(stdlib.STANDARD_NS)
        standard_scope.add_use(stdlib.STDTYPES_NS)

        for name, dim in stdlib.PHYSICAL_TYPES.items():
            physical = PhysicalTypeInfo(name, dim)
            self._builtin_types[name] = physical
            symbol = Symbol(
                name,
                SymbolKind.PHYSICAL_TYPE,
                type=physical,
                namespace=types_scope.path,
                builtin=True,
            )
            types_scope.define(symbol)

        for name, (type_name, factor, offset) in stdlib.UNITS.items():
            physical = self._builtin_types[type_name]
            assert isinstance(physical, PhysicalTypeInfo)
            unit = UnitInfo(name, physical, factor, offset)
            symbol = Symbol(
                name,
                SymbolKind.UNIT,
                type=physical,
                unit=unit,
                namespace=types_scope.path,
                builtin=True,
            )
            types_scope.define(symbol)

        for name, members in stdlib.ENUMS.items():
            enum = EnumTypeInfo(name, namespace=types_scope.path, builtin=True)
            for index, member in enumerate(members):
                enum.members[member] = index
                enum.member_symbols[member] = Symbol(
                    member,
                    SymbolKind.ENUM_MEMBER,
                    type=enum,
                    enum=enum,
                    enum_value=index,
                    namespace=types_scope.path,
                    builtin=True,
                )
            self._builtin_types[name] = enum
            types_scope.define(
                Symbol(
                    name,
                    SymbolKind.ENUM,
                    type=enum,
                    namespace=types_scope.path,
                    builtin=True,
                )
            )

        shells: dict[str, CompositeTypeInfo] = {}
        for definition in stdlib.COMPOSITES:
            composite = CompositeTypeInfo(
                definition["name"],
                definition["kind"],
                namespace=standard_scope.path,
                base_name=definition.get("base"),
                builtin=True,
            )
            composite.scope = Scope(
                composite.name,
                parent=standard_scope,
                kind="type",
                owner=composite,
            )
            shells[composite.name] = composite
            self._builtin_types[composite.name] = composite
            kind = {
                "struct": SymbolKind.STRUCT,
                "actor": SymbolKind.ACTOR,
            }[composite.kind]
            standard_scope.define(
                Symbol(
                    composite.name,
                    kind,
                    type=composite,
                    namespace=standard_scope.path,
                    builtin=True,
                )
            )
            self.model.composites.append(composite)

        for composite in shells.values():
            if composite.base_name:
                composite.base = shells.get(composite.base_name)

        for definition in stdlib.COMPOSITES:
            composite = shells[definition["name"]]
            for name, type_name in definition.get("fields", {}).items():
                symbol = Symbol(
                    name,
                    SymbolKind.FIELD,
                    type=self._builtin_type(type_name),
                    namespace=composite.namespace,
                    builtin=True,
                )
                composite.scope.define(symbol)
                composite.fields[name] = symbol
            for name, method in definition.get("methods", {}).items():
                params = tuple(
                    ParameterInfo(param, self._builtin_type(type_name), has_default)
                    for param, type_name, has_default in method["params"]
                )
                signature = FunctionTypeInfo(
                    params,
                    self._builtin_type(method["result"]) if method["result"] else None,
                )
                symbol = Symbol(
                    name,
                    SymbolKind.METHOD,
                    type=signature,
                    namespace=composite.namespace,
                    builtin=True,
                )
                composite.scope.define(symbol)
                composite.methods[name] = symbol

        for name, (target, params) in stdlib.MODIFIERS.items():
            modifier = CompositeTypeInfo(
                name,
                "modifier",
                namespace=standard_scope.path,
                target_actor=target,
                builtin=True,
            )
            modifier.scope = Scope(name, parent=standard_scope, kind="type", owner=modifier)
            parsed = tuple(
                ParameterInfo(param, self._builtin_type(type_name), has_default)
                for param, type_name, has_default in params
            )
            modifier.signature = FunctionTypeInfo(parsed, None)
            for param in parsed:
                symbol = Symbol(
                    param.name,
                    SymbolKind.PARAMETER,
                    type=param.type,
                    namespace=standard_scope.path,
                    builtin=True,
                )
                modifier.scope.define(symbol)
                modifier.fields[param.name] = symbol
            self._builtin_types.setdefault(name, modifier)
            self.model.composites.append(modifier)
            modifier_symbol = Symbol(
                name,
                SymbolKind.MODIFIER,
                type=modifier,
                namespace=standard_scope.path,
                builtin=True,
            )
            if standard_scope.lookup_local(name) is None:
                standard_scope.define(modifier_symbol)
            else:
                # A modifier and a type may share a name (e.g. `position`).
                # Keep the type in the namespace and expose the modifier to
                # modifier resolution only.
                self._builtin_modifiers[name] = modifier_symbol

        for name, type_name in stdlib.IMPLICIT_ACTOR_FIELDS.items():
            self._implicit_actor_fields[name] = Symbol(
                name,
                SymbolKind.FIELD,
                type=self._builtin_type(type_name),
                builtin=True,
            )

    def _builtin_type(self, name: str | None) -> TypeInfo | None:
        if name is None:
            return None
        if name in PRIMITIVES:
            return PRIMITIVES[name]
        if name in self._builtin_types:
            return self._builtin_types[name]
        raise KeyError(f"unknown builtin type {name!r}")

    # ---------------------------------------------------------- definition pass

    def _declare_unit(self, unit: ast.CompilationUnit) -> None:
        current_namespace = ""
        for use in unit.uses:
            for reference in use.namespaces:
                self._register_use(reference, use.span, self.model.root)
        for declaration in unit.declarations:
            if isinstance(declaration, ast.NamespaceDecl):
                current_namespace = self._normalize_namespace(declaration.name)
                scope = self.model.namespace(current_namespace)
                for reference in declaration.uses:
                    self._register_use(reference, declaration.span, scope)
                continue
            if isinstance(declaration, ast.ExportDecl):
                self._exports.append((declaration, current_namespace))
                continue
            self._declare(declaration, current_namespace)

    def _normalize_namespace(self, name: str) -> str:
        name = name.strip().replace(".", "::").strip(":")
        return "" if name == "null" else name

    def _register_use(self, reference: str, span: ast.Span, scope: Scope) -> None:
        path = self._normalize_namespace(reference)
        scope.add_use(path)
        self._pending_uses.append((path, span, scope))

    def _validate_uses(self) -> None:
        for path, span, _scope in self._pending_uses:
            if path not in self.model.namespaces:
                self.model.diagnostics.error(
                    "E0205", f"unknown namespace '{path}' in use statement", span
                )

    def _split_name(self, name: str, default_namespace: str) -> tuple[str, str]:
        name = name.strip()
        if name.startswith("::"):
            return "", name[2:]
        if "::" in name:
            namespace, _, local = name.rpartition("::")
            return namespace, local
        return default_namespace, name

    def _declare(self, declaration: ast.Node, namespace: str) -> None:
        if isinstance(declaration, ast.PhysicalTypeDecl):
            self._declare_physical_type(declaration, namespace)
        elif isinstance(declaration, ast.UnitDecl):
            self._declare_unit_symbol(declaration, namespace)
        elif isinstance(declaration, ast.EnumDecl):
            self._declare_enum(declaration, namespace)
        elif isinstance(declaration, (ast.StructDecl, ast.ActorDecl, ast.ScenarioDecl, ast.ActionDecl)):
            self._declare_composite(declaration, namespace)
        elif isinstance(declaration, ast.ModifierDecl):
            self._declare_modifier(declaration, namespace)
        elif isinstance(
            declaration,
            (
                ast.EnumExtensionDecl,
                ast.StructuredExtensionDecl,
                ast.PrimitiveExtensionDecl,
            ),
        ):
            self._pending_extensions.append((declaration, namespace))
        elif isinstance(declaration, ast.ParameterDecl):
            self._declare_global_parameter(declaration, namespace)

    def _declare_physical_type(self, declaration: ast.PhysicalTypeDecl, namespace: str) -> None:
        target_namespace, name = self._split_name(declaration.name, namespace)
        scope = self.model.namespace(target_namespace)
        exponents = {item.unit: item.exponent for item in declaration.base.exponents}
        physical = PhysicalTypeInfo(name, dimension(**exponents))
        symbol = Symbol(
            name,
            SymbolKind.PHYSICAL_TYPE,
            type=physical,
            node=declaration,
            namespace=target_namespace,
        )
        existing = scope.define(symbol)
        if existing is not None:
            self._duplicate(existing, declaration.span)

    def _declare_unit_symbol(self, declaration: ast.UnitDecl, namespace: str) -> None:
        target_namespace, name = self._split_name(declaration.name, namespace)
        scope = self.model.namespace(target_namespace)
        symbol = Symbol(
            name,
            SymbolKind.UNIT,
            node=declaration,
            namespace=target_namespace,
        )
        existing = scope.define(symbol)
        if existing is not None:
            self._duplicate(existing, declaration.span)
            return
        self._pending_units.append((symbol, declaration))

    def _declare_enum(self, declaration: ast.EnumDecl, namespace: str) -> None:
        target_namespace, name = self._split_name(declaration.name, namespace)
        scope = self.model.namespace(target_namespace)
        enum = EnumTypeInfo(name, namespace=target_namespace, node=declaration)
        symbol = Symbol(
            name,
            SymbolKind.ENUM,
            type=enum,
            node=declaration,
            namespace=target_namespace,
        )
        existing = scope.define(symbol)
        if existing is not None:
            self._duplicate(existing, declaration.span)
            return
        self._add_enum_members(enum, declaration.members, target_namespace)

    def _add_enum_members(
        self, enum: EnumTypeInfo, members: Sequence[ast.EnumMember], namespace: str
    ) -> None:
        next_value = max(enum.members.values(), default=-1) + 1
        references: list[ast.EnumMember] = []
        for member in members:
            if member.name in enum.members:
                self.model.diagnostics.error(
                    "E0102",
                    f"duplicate enum member '{member.name}' in '{enum.name}'",
                    member.span,
                )
                continue
            if isinstance(member.value, ast.EnumValueRef):
                references.append(member)
                continue
            value = next_value if member.value is None else member.value
            self._define_enum_member(enum, member, value, namespace)
            next_value = max(next_value, value + 1)
        for member in references:
            reference = member.value
            assert isinstance(reference, ast.EnumValueRef)
            target_name = reference.member
            target_enum = reference.enum
            if target_enum is not None:
                target_name = target_enum.rsplit("::", 1)[-1].rsplit(".", 1)[-1]
            if target_name not in enum.members:
                self.model.diagnostics.error(
                    "E0103",
                    f"enum member '{member.name}' references unknown member "
                    f"'{reference.member}' of '{enum.name}'",
                    member.span,
                )
                continue
            self._define_enum_member(
                enum, member, enum.members[target_name], namespace
            )
            next_value = max(next_value, enum.members[member.name] + 1)

    def _define_enum_member(
        self,
        enum: EnumTypeInfo,
        member: ast.EnumMember,
        value: int,
        namespace: str,
    ) -> None:
        enum.members[member.name] = value
        enum.member_symbols[member.name] = Symbol(
            member.name,
            SymbolKind.ENUM_MEMBER,
            type=enum,
            enum=enum,
            enum_value=value,
            node=member,
            namespace=namespace,
        )

    def _declare_composite(
        self,
        declaration: ast.StructDecl | ast.ActorDecl | ast.ScenarioDecl | ast.ActionDecl,
        namespace: str,
    ) -> None:
        target_namespace, name = self._split_name(declaration.name, namespace)
        scope = self.model.namespace(target_namespace)
        kind = {
            ast.StructDecl: "struct",
            ast.ActorDecl: "actor",
            ast.ScenarioDecl: "scenario",
            ast.ActionDecl: "action",
        }[type(declaration)]
        base_name = declaration.inherits.name if declaration.inherits else None
        if kind == "actor" and base_name is None and self._builtins_installed:
            base_name = f"{stdlib.STANDARD_NS}::traffic_participant"
        composite = CompositeTypeInfo(
            name,
            kind,
            namespace=target_namespace,
            base_name=base_name,
            node=declaration,
        )
        composite.scope = Scope(name, parent=scope, kind="type", owner=composite)
        symbol = Symbol(
            name,
            map_kind[kind],
            type=composite,
            node=declaration,
            namespace=target_namespace,
        )
        existing = scope.define(symbol)
        if existing is not None:
            self._duplicate(existing, declaration.span)
            return
        self.model.composites.append(composite)
        self._member_decls[id(composite)] = []
        self._declare_members(declaration.members, composite, namespace)

    def _declare_modifier(self, declaration: ast.ModifierDecl, namespace: str) -> None:
        target_namespace = namespace
        name = declaration.name
        if "::" in name:
            target_namespace, name = self._split_name(name, namespace)
        scope = self.model.namespace(target_namespace)
        composite = CompositeTypeInfo(
            name,
            "modifier",
            namespace=target_namespace,
            target_actor=declaration.actor,
            of_behavior=declaration.of,
            node=declaration,
        )
        composite.scope = Scope(name, parent=scope, kind="type", owner=composite)
        symbol = Symbol(
            name,
            SymbolKind.MODIFIER,
            type=composite,
            node=declaration,
            namespace=target_namespace,
        )
        existing = scope.define(symbol)
        if existing is not None:
            self._duplicate(existing, declaration.span)
            return
        self.model.composites.append(composite)
        self._member_decls[id(composite)] = []
        self._declare_members(declaration.members, composite, target_namespace)

    def _declare_global_parameter(self, declaration: ast.ParameterDecl, namespace: str) -> None:
        scope = self.model.namespace(namespace)
        for name in declaration.names:
            symbol = Symbol(
                name,
                SymbolKind.GLOBAL_PARAMETER,
                node=declaration,
                namespace=namespace,
            )
            existing = scope.define(symbol)
            if existing is not None:
                self._duplicate(existing, declaration.span)
        self._global_params.append((declaration, namespace))

    def _declare_members(
        self, members: Sequence[ast.Node], owner: CompositeTypeInfo, namespace: str
    ) -> None:
        declarations = self._member_decls.setdefault(id(owner), [])
        assert owner.scope is not None
        for member in members:
            if isinstance(member, (ast.ParameterDecl, ast.VariableDecl)):
                declarations.append(member)
                kind = (
                    SymbolKind.PARAMETER
                    if isinstance(member, ast.ParameterDecl)
                    else SymbolKind.VARIABLE
                )
                for name in member.names:
                    symbol = Symbol(
                        name,
                        kind,
                        node=member,
                        namespace=namespace,
                    )
                    existing = owner.scope.define(symbol)
                    if existing is not None:
                        self._duplicate(existing, member.span)
                        continue
                    owner.fields[name] = symbol
                continue
            if isinstance(member, ast.EventDecl):
                declarations.append(member)
                symbol = Symbol(
                    member.name,
                    SymbolKind.EVENT,
                    node=member,
                    namespace=namespace,
                )
                existing = owner.scope.define(symbol)
                if existing is not None:
                    self._duplicate(existing, member.span)
                else:
                    owner.events[member.name] = symbol
                continue
            if isinstance(member, ast.MethodDecl):
                declarations.append(member)
                symbol = Symbol(
                    member.name,
                    SymbolKind.METHOD,
                    node=member,
                    namespace=namespace,
                )
                existing = owner.scope.define(symbol)
                if existing is not None:
                    self._duplicate(existing, member.span)
                else:
                    owner.methods[member.name] = symbol
                continue
            if isinstance(member, ast.CoverageDecl):
                declarations.append(member)
                continue
            if isinstance(member, ast.ModifierApplication):
                declarations.append(member)
                continue
            if isinstance(member, (ast.OnDirective, ast.DoDirective)):
                self._behavior_nodes.append((owner, member))

    def _duplicate(self, existing: Symbol, span: ast.Span) -> None:
        self.model.diagnostics.error(
            "E0101",
            f"duplicate definition of '{existing.name}'",
            span,
        )

    # ---------------------------------------------------------- resolution pass

    def _resolve_units(self) -> None:
        for symbol, declaration in self._pending_units:
            context = _Context(self.model.namespace(symbol.namespace), symbol.namespace)
            physical = self._resolve_symbol(
                declaration.type_name,
                context,
                {SymbolKind.PHYSICAL_TYPE},
                declaration.span,
                code="E0201",
                what="physical type",
                expected_label="physical type",
            )
            if physical is None:
                continue
            assert isinstance(physical.type, PhysicalTypeInfo)
            factor = 1.0 if declaration.spec.factor is None else float(declaration.spec.factor)
            offset = 0.0 if declaration.spec.offset is None else float(declaration.spec.offset)
            if factor == 0.0:
                self.model.diagnostics.error(
                    "E0204", f"unit '{symbol.name}' has a zero conversion factor", declaration.span
                )
                continue
            symbol.unit = UnitInfo(symbol.name, physical.type, factor, offset)
            symbol.type = physical.type

    def _resolve_inheritance(self) -> None:
        state: dict[int, int] = {}

        def visit(composite: CompositeTypeInfo) -> bool:
            if composite.builtin:
                return True
            status = state.get(id(composite))
            if status == 1:
                self.model.diagnostics.error(
                    "E0301",
                    f"inheritance cycle involving '{composite.qualified_name}'",
                    composite.node.span if composite.node else None,
                )
                return False
            if status == 2:
                return True
            state[id(composite)] = 1
            ok = True
            if composite.base_name:
                self._resolve_base(composite)
                if composite.base is not None:
                    if composite.base is composite or not visit(composite.base):
                        composite.base = None
                        ok = False
            state[id(composite)] = 2
            return ok

        for composite in self.model.composites:
            visit(composite)

    def _resolve_base(self, composite: CompositeTypeInfo) -> None:
        context = _Context(composite.scope, composite.namespace) if composite.scope else _Context(
            self.model.root, composite.namespace
        )
        span = composite.node.span if composite.node else None
        symbol = self._resolve_symbol(
            composite.base_name or "",
            context,
            COMPOSITE_KINDS,
            span,
            code="E0201",
            what="base type",
            expected_label="type",
        )
        if symbol is None or not isinstance(symbol.type, CompositeTypeInfo):
            return
        base = symbol.type
        allowed = _INHERIT_COMPAT.get(composite.kind, set())
        if base.kind not in allowed:
            self.model.diagnostics.error(
                "E0302",
                f"{composite.kind} '{composite.name}' cannot inherit from "
                f"{base.kind} '{base.qualified_name}'",
                span,
            )
            return
        composite.base = base

    def _resolve_extensions(self) -> None:
        for declaration, namespace in self._pending_extensions:
            context = _Context(self.model.namespace(namespace), namespace)
            if isinstance(declaration, ast.EnumExtensionDecl):
                symbol = self._resolve_symbol(
                    declaration.name,
                    context,
                    {SymbolKind.ENUM},
                    declaration.span,
                    code="E0201",
                    what="enum",
                    expected_label="enum",
                )
                if symbol is not None and isinstance(symbol.type, EnumTypeInfo):
                    self._add_enum_members(symbol.type, declaration.members, namespace)
                continue
            if isinstance(declaration, ast.StructuredExtensionDecl):
                symbol = self._resolve_symbol(
                    declaration.name,
                    context,
                    COMPOSITE_KINDS,
                    declaration.span,
                    code="E0201",
                    what="type",
                    expected_label="type",
                )
                if symbol is None or not isinstance(symbol.type, CompositeTypeInfo):
                    continue
                self._declare_members(declaration.members, symbol.type, namespace)
                continue
            if isinstance(declaration, ast.PrimitiveExtensionDecl):
                self.model.diagnostics.warning(
                    "W0106",
                    f"methods extended on primitive type '{declaration.name}' "
                    "are not executed",
                    declaration.span,
                )

    def _resolve_signatures(self) -> None:
        for declaration, namespace in self._global_params:
            context = _Context(self.model.namespace(namespace), namespace)
            resolved = self._resolve_type_ref(declaration.type, context)
            for name in declaration.names:
                symbol = context.scope.lookup_local(name)
                if symbol is not None:
                    symbol.type = resolved
            if declaration.default is not None:
                self._check_assignable(
                    declaration.default, resolved, context, "default value"
                )
            self._check_constraints(
                declaration.constraints, context, resolved, "parameter constraint"
            )

        for composite in self.model.composites:
            declarations = self._member_decls.get(id(composite), [])
            if composite.builtin and not declarations:
                continue
            assert composite.scope is not None
            context = _Context(
                composite.scope,
                composite.namespace,
                current_type=composite,
                it_type=composite,
            )
            for declaration in declarations:
                if isinstance(declaration, (ast.ParameterDecl, ast.VariableDecl)):
                    self._resolve_field_declaration(declaration, composite, context)
                elif isinstance(declaration, ast.EventDecl):
                    self._resolve_event_declaration(declaration, composite, context)
                elif isinstance(declaration, ast.MethodDecl):
                    self._resolve_method_declaration(declaration, composite, context)
                elif isinstance(declaration, ast.CoverageDecl):
                    for arg in declaration.args:
                        self._infer_arg(arg, context)
                elif isinstance(declaration, ast.ModifierApplication):
                    self._check_modifier_application(declaration, context)
            composite.signature = self._signature_from_fields(composite)
            if composite.namespace in (stdlib.STANDARD_NS, stdlib.STDTYPES_NS):
                composite.signature = _optional_signature(composite.signature)
            self._validate_modifier_target(composite)
        self._attach_qualified_actions()

    def _qualified_action_owner(
        self, composite: CompositeTypeInfo
    ) -> tuple[CompositeTypeInfo, str] | None:
        """The actor a dotted `action Actor.behavior` declaration belongs to."""
        if composite.kind != "action" or "." not in composite.name:
            return None
        owner_name, _, local_name = composite.name.rpartition(".")
        namespace = self.model.namespaces.get(composite.namespace)
        owner = namespace.lookup_local(owner_name) if namespace is not None else None
        target = owner.type if owner is not None else None
        if not isinstance(target, CompositeTypeInfo) or target.kind not in (
            "actor",
            "struct",
        ):
            return None
        return target, local_name

    def _attach_qualified_actions(self) -> None:
        """Expose `action actor.behavior` declarations as methods on the actor."""
        for composite in self.model.composites:
            resolved = self._qualified_action_owner(composite)
            if resolved is None:
                continue
            target, local_name = resolved
            method = target.methods.get(local_name)
            if method is None:
                method = Symbol(
                    local_name,
                    SymbolKind.METHOD,
                    node=composite.node,
                    namespace=composite.namespace,
                )
                target.methods[local_name] = method
            signature = _optional_signature(composite.signature)
            method.type = signature

    def _resolve_field_declaration(
        self,
        declaration: ast.ParameterDecl | ast.VariableDecl,
        owner: CompositeTypeInfo,
        context: _Context,
    ) -> None:
        resolved = self._resolve_type_ref(declaration.type, context)
        for name in declaration.names:
            symbol = owner.fields.get(name)
            if symbol is not None:
                symbol.type = resolved
        default = (
            declaration.default
            if isinstance(declaration, ast.ParameterDecl)
            else declaration.value
        )
        if default is not None:
            self._check_assignable(default, resolved, context, "initial value")
        if isinstance(declaration, ast.VariableDecl) and declaration.sample is not None:
            sample = declaration.sample
            self._check_assignable(sample.value, resolved, context, "sample value")
            self._check_event_spec(sample.event, context)
            if sample.default is not None:
                self._check_assignable(sample.default, resolved, context, "sample default")
        if isinstance(declaration, ast.ParameterDecl) and declaration.constraints:
            self._check_constraints(
                declaration.constraints, context, resolved, "field constraint"
            )

    def _resolve_event_declaration(
        self, declaration: ast.EventDecl, owner: CompositeTypeInfo, context: _Context
    ) -> None:
        params, call_scope = self._resolve_parameters(declaration.parameters, context)
        call_context = _Context(
            call_scope,
            context.namespace,
            current_type=owner,
            it_type=owner,
        )
        symbol = owner.events.get(declaration.name)
        if symbol is not None:
            symbol.type = FunctionTypeInfo(params, None)
        if declaration.specification is not None:
            self._check_event_spec(declaration.specification, call_context)

    def _resolve_method_declaration(
        self, declaration: ast.MethodDecl, owner: CompositeTypeInfo, context: _Context
    ) -> None:
        params, call_scope = self._resolve_parameters(declaration.parameters, context)
        result = (
            self._resolve_type_ref(declaration.return_type, context)
            if declaration.return_type is not None
            else None
        )
        signature = FunctionTypeInfo(params, result)
        symbol = owner.methods.get(declaration.name)
        if symbol is not None:
            symbol.type = signature
        call_context = _Context(
            call_scope,
            context.namespace,
            current_type=owner,
            it_type=owner,
        )
        implementation = declaration.implementation
        if implementation.mode == "expression" and implementation.expression is not None:
            actual = self._infer(implementation.expression, call_context)
            if not is_assignable(actual, result):
                self.model.diagnostics.error(
                    "E0401",
                    f"method '{declaration.name}' returns {describe_type(actual)}, "
                    f"expected {describe_type(result)}",
                    implementation.expression.span,
                )
        elif implementation.mode == "external":
            for arg in implementation.args or []:
                self._infer_arg(arg, call_context)

    def _resolve_parameters(
        self,
        specifications: Sequence[ast.ArgSpec] | None,
        context: _Context,
    ) -> tuple[tuple[ParameterInfo, ...], Scope]:
        scope = Scope("<call>", parent=context.scope, kind="call")
        params: list[ParameterInfo] = []
        seen: set[str] = set()
        for specification in specifications or []:
            if specification.name in seen:
                self.model.diagnostics.error(
                    "E0101",
                    f"duplicate parameter '{specification.name}'",
                    specification.span,
                )
                continue
            seen.add(specification.name)
            type_info = self._resolve_type_ref(specification.type, context)
            symbol = Symbol(
                specification.name,
                SymbolKind.PARAMETER,
                type=type_info,
                node=specification,
                namespace=context.namespace,
            )
            scope.define(symbol)
            params.append(
                ParameterInfo(
                    specification.name,
                    type_info,
                    has_default=specification.default is not None,
                )
            )
        call_context = _Context(
            scope,
            context.namespace,
            current_type=context.current_type,
            it_type=context.it_type,
        )
        for specification in specifications or []:
            if specification.default is None:
                continue
            symbol = scope.lookup_local(specification.name)
            self._check_assignable(
                specification.default,
                symbol.type if symbol is not None else None,
                call_context,
                f"default for parameter '{specification.name}'",
            )
        return tuple(params), scope

    def _signature_from_fields(self, composite: CompositeTypeInfo) -> FunctionTypeInfo:
        params = []
        for symbol in composite.fields.values():
            if symbol.kind is not SymbolKind.PARAMETER:
                continue
            if not isinstance(symbol.node, ast.ParameterDecl):
                continue
            params.append(
                ParameterInfo(
                    symbol.name,
                    symbol.type,
                    has_default=_parameter_has_default(symbol.node),
                )
            )
        return FunctionTypeInfo(tuple(params), None)

    def _validate_modifier_target(self, composite: CompositeTypeInfo) -> None:
        if composite.kind != "modifier" or not composite.target_actor:
            return
        context = _Context(
            composite.scope or self.model.root,
            composite.namespace,
        )
        symbol = self._resolve_symbol(
            composite.target_actor,
            context,
            {SymbolKind.ACTOR},
            composite.node.span if composite.node else None,
            code="E0302",
            what="target actor",
            expected_label="actor",
        )
        if symbol is None:
            return
        if composite.of_behavior:
            behavior = self._resolve_symbol(
                composite.of_behavior,
                context,
                {SymbolKind.SCENARIO, SymbolKind.ACTION},
                composite.node.span if composite.node else None,
                code="E0302",
                what="target behavior",
                expected_label="scenario or action",
            )
            if behavior is None:
                return

    def _validate_inheritance_conditions(self) -> None:
        for composite in self.model.composites:
            node = composite.node
            if node is None or not hasattr(node, "inherits"):
                continue
            inherits = node.inherits
            if inherits is None or composite.base is None:
                continue
            if inherits.field is None:
                continue
            field = composite_member(composite.base, inherits.field, "fields")
            if field is None:
                self.model.diagnostics.error(
                    "E0303",
                    f"inherited type '{composite.base.name}' has no field '{inherits.field}'",
                    inherits.span,
                )
                continue
            if inherits.condition is not None:
                context = _Context(
                    composite.scope or self.model.root,
                    composite.namespace,
                    current_type=composite,
                    it_type=composite,
                )
                self._check_assignable(
                    inherits.condition,
                    field.type,
                    context,
                    f"inheritance condition on '{inherits.field}'",
                )

    def _check_exports(self) -> None:
        for declaration, namespace in self._exports:
            for specification in declaration.specifications:
                if specification.wildcard:
                    path = self._normalize_namespace(specification.name)
                    if path and path not in self.model.namespaces:
                        self.model.diagnostics.error(
                            "E0205",
                            f"unknown namespace '{path}' in export",
                            specification.span,
                        )
                    continue
                context = _Context(self.model.namespace(namespace), namespace)
                self._resolve_symbol(
                    specification.name,
                    context,
                    None,
                    specification.span,
                    code="E0402",
                    what="exported symbol",
                )

    # ---------------------------------------------------------------- values

    def _check_bodies(self) -> None:
        for owner, node in self._behavior_nodes:
            assert owner.scope is not None
            it_type = owner
            if owner.kind == "action":
                # Inside `action actor.behavior`, `it` is the actor that
                # receives the action, not the action declaration itself.
                resolved = self._qualified_action_owner(owner)
                if resolved is not None:
                    it_type = resolved[0]
            context = _Context(
                owner.scope,
                owner.namespace,
                current_type=owner,
                it_type=it_type,
            )
            self._check_statement(node, context)

    def _check_statement(self, node: ast.Node, context: _Context) -> None:
        if isinstance(node, ast.DoDirective):
            self._check_statement(node.member, context)
        elif isinstance(node, ast.OnDirective):
            self._check_event_spec(node.specification, context)
            for member in node.members:
                self._check_statement(member, context)
        elif isinstance(node, ast.LabeledStatement):
            self._check_statement(node.statement, context)
        elif isinstance(node, ast.Composition):
            for arg in node.args:
                self._infer_arg(arg, context)
            if node.with_clause is not None:
                self._check_behavior_with(node.with_clause, context)
            for member in node.members:
                self._check_statement(member, context)
        elif isinstance(node, ast.BehaviorInvocation):
            self._check_behavior_invocation(node, context)
        elif isinstance(node, ast.WaitDirective):
            self._check_event_spec(node.specification, context)
        elif isinstance(node, ast.EmitDirective):
            self._check_emit(node, context)
        elif isinstance(node, ast.CallDirective):
            self._infer(node.invocation, context)
        elif isinstance(node, ast.ModifierApplication):
            self._check_modifier_application(node, context)
        elif isinstance(node, ast.KeepConstraint):
            self._check_bool(node.expr, context, "keep constraint")
        elif isinstance(node, ast.UntilDirective):
            self._check_event_spec(node.specification, context)
        elif isinstance(node, ast.Expr):
            self._infer(node, context)

    def _check_behavior_with(self, declaration: ast.BehaviorWith, context: _Context) -> None:
        for member in declaration.members:
            self._check_statement(member, context)

    def _check_behavior_invocation(
        self, node: ast.BehaviorInvocation, context: _Context
    ) -> None:
        target_type = self._infer(node.target, context) if node.target is not None else None
        name = node.name.rpartition("::")[2]
        if target_type is not None:
            if isinstance(target_type, CompositeTypeInfo):
                method = self._lookup_member(target_type, name, ("methods",))
                if method is not None:
                    self.model.resolved[id(node)] = method
                    self._check_args(
                        node.args,
                        method.type if isinstance(method.type, FunctionTypeInfo) else None,
                        node.span,
                        context,
                        f"call to '{name}'",
                    )
                else:
                    if target_type.kind in ("actor", "scenario", "action"):
                        self.model.diagnostics.warning(
                            "W0105",
                            f"unknown behavior or method '{name}' on "
                            f"{describe_type(target_type)}; external domain definition not loaded",
                            node.span,
                        )
                    else:
                        self.model.diagnostics.error(
                            "E0403",
                            f"{target_type.kind} '{target_type.name}' has no method '{name}'",
                            node.span,
                        )
                    for arg in node.args:
                        self._infer_arg(arg, context)
                if node.with_clause is not None:
                    with_context = _Context(
                        context.scope,
                        context.namespace,
                        current_type=context.current_type,
                        it_type=target_type,
                    )
                    self._check_behavior_with(node.with_clause, with_context)
                return
            if is_unknown(target_type):
                for arg in node.args:
                    self._infer_arg(arg, context)
                if node.with_clause is not None:
                    self._check_behavior_with(node.with_clause, context)
                return
            self.model.diagnostics.error(
                "E0408",
                f"cannot invoke behavior on {describe_type(target_type)}",
                node.span,
            )
            for arg in node.args:
                self._infer_arg(arg, context)
            return

        symbol = self._resolve_symbol(
            node.name,
            context,
            {SymbolKind.SCENARIO, SymbolKind.ACTION},
            node.span,
            code="E0404",
            what="behavior",
            expected_label="scenario or action",
        )
        if symbol is not None:
            self.model.resolved[id(node)] = symbol
            signature = (
                symbol.type.signature
                if isinstance(symbol.type, CompositeTypeInfo)
                else None
            )
            self._check_args(node.args, signature, node.span, context, f"call to '{name}'")
        else:
            for arg in node.args:
                self._infer_arg(arg, context)
        if node.with_clause is not None:
            self._check_behavior_with(node.with_clause, context)

    def _check_emit(self, node: ast.EmitDirective, context: _Context) -> None:
        name = node.name.rpartition("::")[2]
        symbol = context.scope.lookup(name)
        if symbol is None or symbol.kind is not SymbolKind.EVENT:
            symbol = (
                self._lookup_member(context.current_type, name, ("events",))
                if context.current_type is not None
                else None
            )
        if symbol is None:
            self.model.diagnostics.warning(
                "W0102",
                f"unknown event '{name}'; external domain definition not loaded",
                node.span,
            )
            for arg in node.args or []:
                self._infer_arg(arg, context)
            return
        self.model.resolved[id(node)] = symbol
        signature = symbol.type if isinstance(symbol.type, FunctionTypeInfo) else None
        self._check_args(node.args or [], signature, node.span, context, f"emit '{name}'")

    def _check_event_spec(self, specification: ast.EventSpec | None, context: _Context) -> None:
        if specification is None:
            return
        if specification.reference is not None:
            reference = specification.reference
            target_type = context.current_type
            if reference.path is not None:
                inferred = self._infer(reference.path, context)
                if isinstance(inferred, CompositeTypeInfo):
                    target_type = inferred
            name = reference.name.rpartition("::")[2]
            symbol = (
                self._lookup_member(target_type, name, ("events",))
                if target_type is not None
                else None
            )
            if symbol is None:
                self.model.diagnostics.warning(
                    "W0102",
                    f"unknown event '@{name}'; external domain definition not loaded",
                    reference.span,
                )
            else:
                self.model.resolved[id(reference)] = symbol
        if specification.condition is not None:
            self._check_condition(specification.condition, context)

    def _check_condition(self, condition: ast.Condition, context: _Context) -> None:
        if isinstance(condition, (ast.BoolCond, ast.RiseCond, ast.FallCond)):
            self._check_bool(condition.expr, context, "event condition")
            return
        if isinstance(condition, ast.ElapsedCond):
            self._check_duration(condition.expr, context, "elapsed condition")
            return
        if isinstance(condition, ast.EveryCond):
            self._check_duration(condition.expr, context, "every condition")
            if condition.offset is not None:
                self._check_duration(condition.offset, context, "every offset")

    def _check_modifier_application(
        self, node: ast.ModifierApplication, context: _Context
    ) -> None:
        target_type = self._infer(node.target, context) if node.target is not None else None
        symbol = self._resolve_symbol(
            node.name,
            context,
            {SymbolKind.MODIFIER},
            node.span,
            code="W0104",
            what="modifier",
            expected_label="modifier",
            severity=Severity.WARNING,
        )
        if symbol is None or not isinstance(symbol.type, CompositeTypeInfo):
            for arg in node.args:
                self._infer_arg(arg, context)
            return
        self.model.resolved[id(node)] = symbol
        modifier = symbol.type
        if target_type is not None and modifier.target_actor:
            if not self._derives_from(target_type, modifier.target_actor):
                self.model.diagnostics.warning(
                    "W0104",
                    f"modifier '{modifier.name}' targets '{modifier.target_actor}' "
                    f"but is applied to {describe_type(target_type)}",
                    node.span,
                )
        signature = modifier.signature or self._signature_from_fields(modifier)
        self._check_args(node.args, signature, node.span, context, f"modifier '{modifier.name}'")

    def _derives_from(self, value: TypeInfo, actor_name: str) -> bool:
        if not isinstance(value, CompositeTypeInfo):
            return False
        current: CompositeTypeInfo | None = value
        while current is not None:
            if current.name == actor_name:
                return True
            current = current.base
        return False

    # ----------------------------------------------------------- expressions

    def _infer(self, expression: ast.Expr | None, context: _Context) -> TypeInfo | None:
        if expression is None:
            return None
        handler = getattr(self, f"_infer_{type(expression).__name__}", None)
        result = handler(expression, context) if handler is not None else UNKNOWN
        self.model.expr_types[id(expression)] = result
        return result

    def _in_action_body(self, context: _Context) -> bool:
        current = context.current_type
        return current is not None and current.kind == "action"

    def _is_free_identifier(self, expression: ast.Expr, context: _Context) -> bool:        return (
            isinstance(expression, ast.Identifier)
            and len(expression.parts) == 1
            and context.scope.lookup(expression.parts[0]) is None
        )

    def _infer_with_hint(
        self,
        expression: ast.Expr,
        expected: TypeInfo | None,
        context: _Context,
    ) -> TypeInfo:
        """Infers with an enum type hint for bare member names.

        `keep(default it == other)` resolves `other` through the enum type of
        `it`; several enums in the standard library share member names.
        """
        if (
            isinstance(expected, EnumTypeInfo)
            and isinstance(expression, ast.Identifier)
            and len(expression.parts) == 1
            and context.scope.lookup(expression.parts[0]) is None
        ):
            member = expected.member_symbols.get(expression.parts[0])
            if member is not None:
                self.model.resolved[id(expression)] = member
                self.model.expr_types[id(expression)] = expected
                return expected
        return self._infer(expression, context)

    def _infer_IntLiteral(self, expression: ast.IntLiteral, context: _Context) -> TypeInfo:
        return INT

    def _infer_FloatLiteral(self, expression: ast.FloatLiteral, context: _Context) -> TypeInfo:
        return FLOAT

    def _infer_PhysicalLiteral(
        self, expression: ast.PhysicalLiteral, context: _Context
    ) -> TypeInfo:
        raw_unit = expression.unit.strip()
        terms = self._unit_terms(raw_unit)
        if terms is not None:
            if not terms:
                self.model.diagnostics.error(
                    "E0203",
                    f"malformed compound unit '{raw_unit}'",
                    expression.span,
                )
                return ERROR
            return self._infer_compound_unit(expression, terms, context)
        symbol = self._resolve_symbol(
            raw_unit,
            context,
            {SymbolKind.UNIT},
            expression.span,
            code="E0203",
            what="unit",
            expected_label="unit",
        )
        if symbol is None or symbol.unit is None:
            return ERROR
        self.model.unit_literals[id(expression)] = symbol.unit
        return symbol.unit.physical

    def _unit_terms(self, text: str) -> list[tuple[str, int]] | None:
        """Split `m/s^2` into [("m", 1), ("s", -2)]; None for a plain unit."""
        compact = "".join(text.split())
        if not any(mark in compact for mark in "*/^"):
            return None
        terms: list[tuple[str, int]] = []
        position = 0
        sign = 1
        expect_term = True
        while position < len(compact):
            if not expect_term:
                if compact[position] not in "*/":
                    return []
                sign = -1 if compact[position] == "/" else 1
                position += 1
                expect_term = True
                continue
            match = _UNIT_TERM_RE.match(compact, position)
            if match is None:
                return []
            terms.append((match.group("name"), int(match.group("exponent") or 1) * sign))
            position = match.end()
            expect_term = False
        if expect_term or not terms:
            return []
        return terms

    def _infer_compound_unit(
        self,
        expression: ast.PhysicalLiteral,
        terms: list[tuple[str, int]],
        context: _Context,
    ) -> TypeInfo:
        dimension_value = dimension()
        factor = 1.0
        for name, exponent in terms:
            symbol = self._resolve_symbol(
                name,
                context,
                {SymbolKind.UNIT},
                expression.span,
                code="E0203",
                what="unit",
                expected_label="unit",
            )
            if symbol is None or symbol.unit is None:
                return ERROR
            unit = symbol.unit
            if unit.offset:
                self.model.diagnostics.error(
                    "E0203",
                    f"unit '{name}' has an offset and cannot be used in a compound unit",
                    expression.span,
                )
                return ERROR
            dimension_value = tuple(
                current + exponent * component
                for current, component in zip(dimension_value, unit.physical.dimension)
            )
            factor *= unit.factor**exponent
        physical = self._physical_type_for_dimension(dimension_value)
        self.model.unit_literals[id(expression)] = UnitInfo(
            expression.unit.strip(), physical, factor
        )
        return physical

    def _physical_type_for_dimension(self, value: tuple[int, ...]) -> PhysicalTypeInfo:
        for candidate in self._builtin_types.values():
            if isinstance(candidate, PhysicalTypeInfo) and candidate.dimension == value:
                return candidate
        return PhysicalTypeInfo(dimension_label(value), value)

    def _infer_BoolLiteral(self, expression: ast.BoolLiteral, context: _Context) -> TypeInfo:
        return BOOL

    def _infer_StringLiteral(self, expression: ast.StringLiteral, context: _Context) -> TypeInfo:
        return STRING

    def _infer_EnumValueRef(
        self, expression: ast.EnumValueRef, context: _Context
    ) -> TypeInfo:
        if expression.enum is not None:
            symbol = self._resolve_symbol(
                expression.enum,
                context,
                {SymbolKind.ENUM},
                expression.span,
                code="E0201",
                what="enum",
                expected_label="enum",
            )
            if symbol is None or not isinstance(symbol.type, EnumTypeInfo):
                return ERROR
            enum = symbol.type
            if expression.member not in enum.members:
                self.model.diagnostics.error(
                    "E0404",
                    f"enum '{enum.name}' has no member '{expression.member}'",
                    expression.span,
                )
                return ERROR
            member = enum.member_symbols[expression.member]
            self.model.resolved[id(expression)] = member
            return enum
        member = self._resolve_enum_member(expression.member, context, expression.span)
        if member is None or member.enum is None:
            return ERROR
        self.model.resolved[id(expression)] = member
        return member.enum

    def _infer_ListLiteral(self, expression: ast.ListLiteral, context: _Context) -> TypeInfo:
        if not expression.elements:
            return ListTypeInfo(UNKNOWN)
        element_type: TypeInfo | None = None
        for element in expression.elements:
            actual = self._infer(element, context)
            if element_type is None:
                element_type = actual
            else:
                merged = common_type(element_type, actual)
                if merged is ERROR:
                    self.model.diagnostics.error(
                        "E0408",
                        f"list elements have incompatible types "
                        f"{describe_type(element_type)} and {describe_type(actual)}",
                        element.span,
                    )
                else:
                    element_type = merged
        return ListTypeInfo(element_type or UNKNOWN)

    def _infer_RangeLiteral(self, expression: ast.RangeLiteral, context: _Context) -> TypeInfo:
        start = self._infer(expression.start, context)
        end = self._infer(expression.end, context)
        merged = common_type(start, end)
        if merged is ERROR:
            self.model.diagnostics.error(
                "E0408",
                f"range bounds have incompatible types "
                f"{describe_type(start)} and {describe_type(end)}",
                expression.span,
            )
            return ERROR
        return RangeTypeInfo(merged or UNKNOWN)

    def _infer_Identifier(self, expression: ast.Identifier, context: _Context) -> TypeInfo:
        if not expression.parts:
            return ERROR
        first = expression.parts[0]
        symbol = self._resolve_symbol(
            first,
            context,
            VALUE_KINDS,
            expression.span,
            code="E0402",
            what="identifier",
            report=False,
        )
        if symbol is None and len(expression.parts) == 1:
            members = self._enum_member_candidates(first, context)
            if len(members) == 1:
                symbol = members[0]
            elif len(members) > 1:
                names = ", ".join(sorted({member.enum.name for member in members if member.enum}))
                self.model.diagnostics.error(
                    "E0404", f"ambiguous enum member '{first}' (defined in {names})", expression.span
                )
                return ERROR
        if symbol is None:
            if first == "actor" and self._in_action_body(context):
                return UNKNOWN
            self.model.diagnostics.error(
                "E0402", f"unknown identifier '{'.'.join(expression.parts)}'", expression.span
            )
            return ERROR
        value_type = symbol.type
        final_symbol = symbol
        for part in expression.parts[1:]:
            value_type, member = self._member_type(
                value_type, part, expression.span, context, report=True
            )
            if member is not None:
                final_symbol = member
        self.model.resolved[id(expression)] = final_symbol
        return value_type if value_type is not None else UNKNOWN

    def _infer_ItExpr(self, expression: ast.ItExpr, context: _Context) -> TypeInfo:
        if context.it_type is None:
            self.model.diagnostics.error(
                "E0409", "'it' is not valid outside an actor or scenario", expression.span
            )
            return ERROR
        return context.it_type

    def _infer_FieldAccess(self, expression: ast.FieldAccess, context: _Context) -> TypeInfo:
        target_type = self._infer(expression.target, context)
        value_type, symbol = self._member_type(
            target_type, expression.field, expression.span, context, report=True
        )
        if symbol is not None:
            self.model.resolved[id(expression)] = symbol
        return value_type if value_type is not None else UNKNOWN

    def _infer_Cast(self, expression: ast.Cast, context: _Context) -> TypeInfo:
        self._infer(expression.target, context)
        return self._resolve_type_ref(expression.type, context)

    def _infer_TypeTest(self, expression: ast.TypeTest, context: _Context) -> TypeInfo:
        self._infer(expression.target, context)
        self._resolve_type_ref(expression.type, context)
        return BOOL

    def _infer_ElementAccess(
        self, expression: ast.ElementAccess, context: _Context
    ) -> TypeInfo:
        target = self._infer(expression.target, context)
        index = self._infer(expression.index, context)
        if not is_unknown(index) and not is_numeric(index):
            self.model.diagnostics.error(
                "E0408", f"element index must be numeric, got {describe_type(index)}", expression.index.span
            )
        if isinstance(target, (ListTypeInfo, RangeTypeInfo)):
            return target.element
        if isinstance(target, PrimitiveTypeInfo) and target.name == "string":
            return STRING
        if is_unknown(target):
            return UNKNOWN
        self.model.diagnostics.error(
            "E0408", f"cannot index {describe_type(target)}", expression.target.span
        )
        return ERROR

    def _infer_Call(self, expression: ast.Call, context: _Context) -> TypeInfo:
        target = expression.target
        if isinstance(target, ast.FieldAccess):
            receiver_type = self._infer(target.target, context)
            name = target.field
            if isinstance(receiver_type, CompositeTypeInfo):
                method = self._lookup_member(receiver_type, name, ("methods",))
                if method is None:
                    if receiver_type.kind in ("actor", "scenario", "action"):
                        self.model.diagnostics.warning(
                            "W0105",
                            f"unknown method '{name}' on {describe_type(receiver_type)}; "
                            "external domain definition not loaded",
                            expression.span,
                        )
                        for arg in expression.args:
                            self._infer_arg(arg, context)
                        return UNKNOWN
                    self.model.diagnostics.error(
                        "E0403",
                        f"{receiver_type.kind} '{receiver_type.name}' has no method '{name}'",
                        expression.span,
                    )
                    for arg in expression.args:
                        self._infer_arg(arg, context)
                    return ERROR
                self.model.resolved[id(expression)] = method
                self.model.resolved[id(target)] = method
                signature = method.type if isinstance(method.type, FunctionTypeInfo) else None
                if signature is not None:
                    self.model.expr_types[id(target)] = signature
                self._check_args(
                    expression.args, signature, expression.span, context, f"call to '{name}'"
                )
                return signature.result if signature is not None else UNKNOWN
            if is_unknown(receiver_type):
                for arg in expression.args:
                    self._infer_arg(arg, context)
                return UNKNOWN
            self.model.diagnostics.error(
                "E0408",
                f"cannot call method '{name}' on {describe_type(receiver_type)}",
                expression.span,
            )
            for arg in expression.args:
                self._infer_arg(arg, context)
            return ERROR

        if isinstance(target, ast.Identifier):
            name = target.parts[-1] if target.parts else ""
            symbol = self._lookup_member(context.current_type, name, ("methods",))
            if symbol is None:
                symbol = self._resolve_symbol(
                    target.parts[0] if target.parts else name,
                    context,
                    {SymbolKind.METHOD, SymbolKind.SCENARIO, SymbolKind.ACTION},
                    expression.span,
                    code="E0402",
                    what="method or behavior",
                    report=False,
                )
            if symbol is not None:
                self.model.resolved[id(expression)] = symbol
                if symbol.type is not None:
                    self.model.expr_types[id(expression.target)] = symbol.type
                if (
                    isinstance(symbol.type, CompositeTypeInfo)
                    and symbol.type.kind == "action"
                ):
                    self._check_args(
                        expression.args,
                        symbol.type.signature,
                        expression.span,
                        context,
                        f"call to '{name}'",
                    )
                    return UNKNOWN
                signature = symbol.type if isinstance(symbol.type, FunctionTypeInfo) else None
                self._check_args(
                    expression.args, signature, expression.span, context, f"call to '{name}'"
                )
                return signature.result if signature is not None else UNKNOWN
            self.model.diagnostics.error(
                "E0402", f"unknown method or behavior '{name}'", expression.span
            )
            for arg in expression.args:
                self._infer_arg(arg, context)
            return ERROR

        self._infer(target, context)
        for arg in expression.args:
            self._infer_arg(arg, context)
        return UNKNOWN

    def _infer_UnaryOp(self, expression: ast.UnaryOp, context: _Context) -> TypeInfo:
        operand = self._infer(expression.operand, context)
        if expression.op == "not":
            if not is_unknown(operand) and not is_assignable(operand, BOOL):
                self.model.diagnostics.error(
                    "E0408", f"'not' expects bool, got {describe_type(operand)}", expression.span
                )
            return BOOL
        if expression.op == "-":
            if is_numeric(operand) or isinstance(operand, PhysicalTypeInfo) or is_unknown(operand):
                return operand
            self.model.diagnostics.error(
                "E0408", f"unary '-' expects a number, got {describe_type(operand)}", expression.span
            )
            return ERROR
        return UNKNOWN

    def _infer_BinaryOp(self, expression: ast.BinaryOp, context: _Context) -> TypeInfo:
        if expression.op in ("==", "!="):
            left_free = self._is_free_identifier(expression.left, context)
            right_free = self._is_free_identifier(expression.right, context)
            if left_free and not right_free:
                right = self._infer(expression.right, context)
                left = self._infer_with_hint(expression.left, right, context)
            elif right_free and not left_free:
                left = self._infer(expression.left, context)
                right = self._infer_with_hint(expression.right, left, context)
            else:
                left = self._infer(expression.left, context)
                right = self._infer(expression.right, context)
        else:
            left = self._infer(expression.left, context)
            right = self._infer(expression.right, context)
        operator = expression.op

        if operator in ("and", "or", "=>"):
            for side, operand in (("left", left), ("right", right)):
                if not is_unknown(operand) and not is_assignable(operand, BOOL):
                    self.model.diagnostics.error(
                        "E0407",
                        f"'{operator}' expects bool on the {side}, got {describe_type(operand)}",
                        expression.span,
                    )
            return BOOL

        if operator in ("==", "!="):
            if not self._comparable(left, right) and not is_unknown(left) and not is_unknown(right):
                self.model.diagnostics.error(
                    "E0408",
                    f"cannot compare {describe_type(left)} with {describe_type(right)}",
                    expression.span,
                )
            return BOOL

        if operator in ("<", "<=", ">", ">="):
            compatible = (
                (is_numeric(left) and is_numeric(right))
                or (
                    isinstance(left, PhysicalTypeInfo)
                    and isinstance(right, PhysicalTypeInfo)
                    and left.dimension == right.dimension
                )
                or is_unknown(left)
                or is_unknown(right)
            )
            if not compatible:
                self.model.diagnostics.error(
                    "E0408",
                    f"cannot order {describe_type(left)} and {describe_type(right)}",
                    expression.span,
                )
            return BOOL

        if operator == "in":
            if isinstance(right, (ListTypeInfo, RangeTypeInfo)):
                if not is_assignable(left, right.element):
                    self.model.diagnostics.error(
                        "E0408",
                        f"{describe_type(left)} is not a member of "
                        f"{describe_type(right)}",
                        expression.span,
                    )
            elif not is_unknown(right):
                self.model.diagnostics.error(
                    "E0408", f"'in' expects a list or range, got {describe_type(right)}", expression.span
                )
            return BOOL

        if is_unknown(left) or is_unknown(right):
            return UNKNOWN

        if operator in ("+", "-"):
            if is_numeric(left) and is_numeric(right):
                return promote_numeric(left, right)
            if isinstance(left, PhysicalTypeInfo) and isinstance(right, PhysicalTypeInfo):
                if left.dimension == right.dimension:
                    return left if left.name else right
                self.model.diagnostics.error(
                    "E0401",
                    f"unit mismatch: cannot use {dimension_label(left.dimension)} "
                    f"and {dimension_label(right.dimension)}",
                    expression.span,
                )
                return ERROR
            self.model.diagnostics.error(
                "E0408",
                f"operator '{operator}' cannot combine {describe_type(left)} "
                f"and {describe_type(right)}",
                expression.span,
            )
            return ERROR

        if operator == "*":
            if isinstance(left, PhysicalTypeInfo) and isinstance(right, PhysicalTypeInfo):
                return PhysicalTypeInfo(
                    f"{describe_type(left)}*{describe_type(right)}",
                    dimension_add(left.dimension, right.dimension),
                )
            if isinstance(left, PhysicalTypeInfo) and is_numeric(right):
                return left
            if is_numeric(left) and isinstance(right, PhysicalTypeInfo):
                return right
            if is_numeric(left) and is_numeric(right):
                return promote_numeric(left, right)
            self.model.diagnostics.error(
                "E0408",
                f"operator '*' cannot combine {describe_type(left)} and {describe_type(right)}",
                expression.span,
            )
            return ERROR

        if operator == "/":
            if is_numeric(left) and is_numeric(right):
                return FLOAT
            if isinstance(left, PhysicalTypeInfo) and is_numeric(right):
                return left
            if is_numeric(left) and isinstance(right, PhysicalTypeInfo):
                return PhysicalTypeInfo(
                    f"1/{describe_type(right)}",
                    dimension_sub((0,) * len(right.dimension), right.dimension),
                )
            if isinstance(left, PhysicalTypeInfo) and isinstance(right, PhysicalTypeInfo):
                return PhysicalTypeInfo(
                    f"{describe_type(left)}/{describe_type(right)}",
                    dimension_sub(left.dimension, right.dimension),
                )
            self.model.diagnostics.error(
                "E0408",
                f"operator '/' cannot combine {describe_type(left)} and {describe_type(right)}",
                expression.span,
            )
            return ERROR

        if operator == "%":
            if is_numeric(left) and is_numeric(right):
                return promote_numeric(left, right)
            self.model.diagnostics.error(
                "E0408",
                f"operator '%' expects numbers, got {describe_type(left)} "
                f"and {describe_type(right)}",
                expression.span,
            )
            return ERROR
        return UNKNOWN

    def _infer_TernaryOp(self, expression: ast.TernaryOp, context: _Context) -> TypeInfo:
        self._check_bool(expression.condition, context, "ternary condition")
        then_type = self._infer(expression.then, context)
        otherwise_type = self._infer(expression.otherwise, context)
        merged = common_type(then_type, otherwise_type)
        if merged is ERROR:
            self.model.diagnostics.error(
                "E0401",
                f"ternary branches have incompatible types "
                f"{describe_type(then_type)} and {describe_type(otherwise_type)}",
                expression.span,
            )
            return ERROR
        return merged or UNKNOWN

    # ------------------------------------------------------------- helpers

    def _comparable(self, left: TypeInfo | None, right: TypeInfo | None) -> bool:
        if is_unknown(left) or is_unknown(right):
            return True
        if left is right or left == right:
            return True
        if is_numeric(left) and is_numeric(right):
            return True
        if isinstance(left, PhysicalTypeInfo) and isinstance(right, PhysicalTypeInfo):
            return left.dimension == right.dimension
        return False

    def _member_type(
        self,
        target: TypeInfo | None,
        name: str,
        span: ast.Span,
        context: _Context,
        report: bool,
    ) -> tuple[TypeInfo | None, Symbol | None]:
        if isinstance(target, CompositeTypeInfo):
            symbol = self._lookup_member(target, name, ("fields",))
            if symbol is not None:
                return symbol.type, symbol
            method = self._lookup_member(target, name, ("methods",))
            if method is not None:
                if report:
                    self.model.diagnostics.error(
                        "E0403", f"method '{name}' must be called with '()'", span
                    )
                return ERROR, None
            if report:
                if target.kind in ("actor", "scenario", "action"):
                    self.model.diagnostics.warning(
                        "W0103",
                        f"unknown member '{name}' on {target.name}; "
                        "external domain definition not loaded",
                        span,
                    )
                else:
                    self.model.diagnostics.error(
                        "E0403", f"{target.kind} '{target.name}' has no field '{name}'", span
                    )
            return UNKNOWN, None
        if is_unknown(target):
            return UNKNOWN, None
        if report:
            self.model.diagnostics.error(
                "E0403", f"type {describe_type(target)} has no field '{name}'", span
            )
        return ERROR, None

    def _lookup_member(
        self, target: CompositeTypeInfo | None, name: str, attributes: tuple[str, ...]
    ) -> Symbol | None:
        if target is None:
            return None
        current: CompositeTypeInfo | None = target
        while current is not None:
            for attribute in attributes:
                table = getattr(current, attribute)
                if name in table:
                    return table[name]
            current = current.base
        if target.kind == "actor" and "fields" in attributes:
            return self._implicit_actor_fields.get(name)
        return None

    def _infer_arg(self, arg: ast.Arg, context: _Context) -> TypeInfo | None:
        if isinstance(arg, (ast.PositionalArg, ast.NamedArg)):
            return self._infer(arg.value, context)
        return None

    def _check_args(
        self,
        args: Sequence[ast.Arg],
        signature: FunctionTypeInfo | None,
        span: ast.Span,
        context: _Context,
        label: str,
    ) -> None:
        if signature is None:
            for arg in args:
                self._infer_arg(arg, context)
            return
        params = signature.params
        assigned: dict[int, ast.Arg] = {}
        positional_index = 0
        for arg in args:
            if isinstance(arg, ast.PositionalArg):
                if positional_index >= len(params):
                    self.model.diagnostics.error(
                        "E0405",
                        f"{label} accepts {len(params)} argument(s), got more",
                        arg.span,
                    )
                    self._infer_arg(arg, context)
                    continue
                assigned[positional_index] = arg
                positional_index += 1
                continue
            if isinstance(arg, ast.NamedArg):
                index = next(
                    (i for i, param in enumerate(params) if param.name == arg.name), None
                )
                if index is None:
                    self.model.diagnostics.error(
                        "E0406", f"{label} has no argument named '{arg.name}'", arg.span
                    )
                    self._infer_arg(arg, context)
                    continue
                if index in assigned:
                    self.model.diagnostics.error(
                        "E0406", f"{label} argument '{arg.name}' given more than once", arg.span
                    )
                    self._infer_arg(arg, context)
                    continue
                assigned[index] = arg
                continue
        for index, param in enumerate(params):
            arg = assigned.get(index)
            if arg is None:
                if not param.has_default:
                    self.model.diagnostics.error(
                        "E0405", f"{label} is missing argument '{param.name}'", span
                    )
                continue
            self._check_assignable(
                arg.value, param.type, context, f"argument '{param.name}'"
            )

    def _resolve_type_ref(self, reference: ast.TypeRef, context: _Context) -> TypeInfo:
        if isinstance(reference, ast.PrimitiveType):
            type_info = PRIMITIVES.get(reference.name)
            if type_info is None:
                self.model.diagnostics.error(
                    "E0201", f"unknown primitive type '{reference.name}'", reference.span
                )
                type_info = ERROR
            self.model.type_refs[id(reference)] = type_info
            return type_info
        if isinstance(reference, ast.NamedType):
            symbol = self._resolve_symbol(
                reference.name,
                context,
                TYPE_KINDS,
                reference.span,
                code="E0201",
                what="type",
                expected_label="type",
            )
            type_info = symbol.type if symbol is not None else ERROR
            self.model.type_refs[id(reference)] = type_info
            return type_info if type_info is not None else ERROR
        if isinstance(reference, ast.ListType):
            element = self._resolve_type_ref(reference.element, context)
            type_info = ListTypeInfo(element)
            self.model.type_refs[id(reference)] = type_info
            return type_info
        if isinstance(reference, ast.RangeType):
            element = self._resolve_type_ref(reference.element, context)
            type_info = RangeTypeInfo(element)
            self.model.type_refs[id(reference)] = type_info
            return type_info
        return ERROR

    def _visible_enums(self, context: _Context) -> list[EnumTypeInfo]:
        enums: list[EnumTypeInfo] = []
        for scope in context.scope.chain():
            for symbol in scope.symbols.values():
                if symbol.kind is SymbolKind.ENUM and isinstance(symbol.type, EnumTypeInfo):
                    if symbol.type not in enums:
                        enums.append(symbol.type)
            for used in scope.uses:
                used_scope = self.model.namespaces.get(used)
                if used_scope is None:
                    continue
                for symbol in used_scope.symbols.values():
                    if symbol.kind is SymbolKind.ENUM and isinstance(symbol.type, EnumTypeInfo):
                        if symbol.type not in enums:
                            enums.append(symbol.type)
        for path in (stdlib.STDTYPES_NS, stdlib.STANDARD_NS):
            for symbol in self.model.namespaces[path].symbols.values():
                if symbol.kind is SymbolKind.ENUM and isinstance(symbol.type, EnumTypeInfo):
                    if symbol.type not in enums:
                        enums.append(symbol.type)
        return enums

    def _enum_member_candidates(self, name: str, context: _Context) -> list[Symbol]:
        return [
            enum.member_symbols[name]
            for enum in self._visible_enums(context)
            if name in enum.member_symbols
        ]

    def _resolve_enum_member(
        self,
        name: str,
        context: _Context,
        span: ast.Span,
        report: bool = True,
    ) -> Symbol | None:
        matches = self._enum_member_candidates(name, context)
        if len(matches) == 1:
            return matches[0]
        if not report:
            return None
        if not matches:
            self.model.diagnostics.error(
                "E0404", f"unknown enum member '{name}'", span
            )
        else:
            names = ", ".join(sorted({match.enum.name for match in matches if match.enum}))
            self.model.diagnostics.error(
                "E0404", f"ambiguous enum member '{name}' (defined in {names})", span
            )
        return None

    def _lookup_kind(
        self,
        name: str,
        context: _Context,
        expected: set[SymbolKind],
        *,
        include_uses: bool = True,
    ) -> Symbol | None:
        """Innermost visible symbol of an expected kind.

        A field may share its name with a type (`route: route`); value
        bindings must not hide the type when a type is being resolved.
        """
        name = name.strip()
        if name.startswith("::") or "::" in name:
            return None
        for scope in context.scope.chain():
            for symbol in scope.lookup_all(name):
                if symbol.kind in expected:
                    return symbol
        if not include_uses:
            return None
        for scope in context.scope.chain():
            for used in scope.uses:
                used_scope = self.model.namespaces.get(used)
                if used_scope is None:
                    continue
                symbol = used_scope.lookup_local(name)
                if symbol is not None and symbol.kind in expected:
                    return symbol
        for path in (stdlib.STDTYPES_NS, stdlib.STANDARD_NS):
            scope = self.model.namespaces.get(path)
            if scope is None:
                continue
            symbol = scope.lookup_local(name)
            if symbol is not None and symbol.kind in expected:
                return symbol
        return None

    def _find_candidates(self, name: str, context: _Context) -> list[Symbol]:
        name = name.strip()
        absolute = name.startswith("::")
        if absolute:
            name = name[2:]
        if "::" in name:
            paths = [name]
            if not absolute and context.namespace:
                relative = f"{context.namespace}::{name}"
                if relative != name:
                    paths.append(relative)
            candidates: list[Symbol] = []
            for path in paths:
                namespace, _, local = path.rpartition("::")
                scope = self.model.namespaces.get(namespace)
                if scope is not None:
                    symbol = scope.lookup_local(local)
                    if symbol is not None and symbol not in candidates:
                        candidates.append(symbol)
            return candidates

        local = context.scope.lookup(name)
        candidates: list[Symbol] = []
        kinds: set[SymbolKind] = set()
        if local is not None:
            candidates.append(local)
            kinds.add(local.kind)

        used_by_kind: dict[SymbolKind, list[Symbol]] = {}
        for scope in context.scope.chain():
            for used in scope.uses:
                used_scope = self.model.namespaces.get(used)
                if used_scope is None:
                    continue
                symbol = used_scope.lookup_local(name)
                if symbol is None or symbol.kind in kinds:
                    continue
                bucket = used_by_kind.setdefault(symbol.kind, [])
                if symbol not in bucket:
                    bucket.append(symbol)
        for kind, symbols in used_by_kind.items():
            kinds.add(kind)
            candidates.extend(symbols)

        for path in (stdlib.STDTYPES_NS, stdlib.STANDARD_NS):
            scope = self.model.namespaces.get(path)
            if scope is None:
                continue
            symbol = scope.lookup_local(name)
            if symbol is not None and symbol.kind not in kinds:
                candidates.append(symbol)
                kinds.add(symbol.kind)
        return candidates

    def _resolve_symbol(
        self,
        name: str,
        context: _Context,
        expected: set[SymbolKind] | None,
        span: ast.Span | None,
        *,
        code: str,
        what: str,
        expected_label: str | None = None,
        severity: Severity = Severity.ERROR,
        report: bool = True,
    ) -> Symbol | None:
        candidates = self._find_candidates(name, context)
        if expected is not None:
            lexical = self._lookup_kind(name, context, expected, include_uses=False)
            if lexical is not None:
                return lexical
            matching = [symbol for symbol in candidates if symbol.kind in expected]
        else:
            matching = candidates
        if len(matching) == 1:
            return matching[0]
        if len(matching) > 1:
            if report:
                names = ", ".join(sorted({symbol.qualified_name for symbol in matching}))
                self._report(
                    "E0206", f"ambiguous name '{name}': {names}", span, severity
                )
            return matching[0]
        if expected is not None:
            direct = self._lookup_kind(name, context, expected)
            if direct is not None:
                return direct
        if expected is not None and SymbolKind.MODIFIER in expected:
            modifier = self._builtin_modifiers.get(name)
            if modifier is not None:
                return modifier
        if not report:
            return None
        if candidates:
            actual = _KIND_LABELS.get(candidates[0].kind, candidates[0].kind.value)
            label = expected_label or "value"
            self._report(
                "E0202", f"'{name}' is {actual}, not {label}", span, severity
            )
            return None
        self._report(code, f"unknown {what} '{name}'", span, severity)
        return None

    def _report(
        self, code: str, message: str, span: ast.Span | None, severity: Severity
    ) -> None:
        if severity is Severity.WARNING:
            self.model.diagnostics.warning(code, message, span)
        else:
            self.model.diagnostics.error(code, message, span)

    def _check_assignable(
        self,
        expression: ast.Expr,
        expected: TypeInfo | None,
        context: _Context,
        what: str,
    ) -> None:
        actual = self._infer(expression, context)
        if not is_assignable(actual, expected):
            self.model.diagnostics.error(
                "E0401",
                f"{what} expects {describe_type(expected)}, got {describe_type(actual)}",
                expression.span,
            )

    def _check_bool(self, expression: ast.Expr, context: _Context, what: str) -> None:
        actual = self._infer(expression, context)
        if not is_unknown(actual) and not is_assignable(actual, BOOL):
            self.model.diagnostics.error(
                "E0407",
                f"{what} must be bool, got {describe_type(actual)}",
                expression.span,
            )

    def _check_duration(self, expression: ast.Expr, context: _Context, what: str) -> None:
        actual = self._infer(expression, context)
        if is_unknown(actual):
            return
        if isinstance(actual, PhysicalTypeInfo) and actual.dimension == TIME_DIMENSION:
            return
        self.model.diagnostics.error(
            "E0407",
            f"{what} must be a time duration, got {describe_type(actual)}",
            expression.span,
        )

    def _check_constraints(
        self,
        constraints: Sequence[ast.Node],
        context: _Context,
        declared_type: TypeInfo | None,
        what: str,
    ) -> None:
        constraint_context = _Context(
            context.scope,
            context.namespace,
            current_type=context.current_type,
            it_type=declared_type,
        )
        for constraint in constraints:
            if isinstance(constraint, ast.KeepConstraint):
                self._check_bool(constraint.expr, constraint_context, what)
            elif isinstance(constraint, ast.RemoveDefault):
                _ = self._infer(constraint.target, constraint_context)


def analyze(
    unit: ast.CompilationUnit,
    extra_units: Sequence[ast.CompilationUnit] = (),
    *,
    builtin_stdlib: bool = True,
) -> SemanticModel:
    return ModelBuilder(builtin_stdlib=builtin_stdlib).analyze(unit, extra_units)


# Explicit kind lookup kept outside the class for readability.
map_kind = {
    "struct": SymbolKind.STRUCT,
    "actor": SymbolKind.ACTOR,
    "scenario": SymbolKind.SCENARIO,
    "action": SymbolKind.ACTION,
}


