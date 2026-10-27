"""Semantic middle-end: scopes, types, units and diagnostics."""

from osc2c.semantics.builder import ModelBuilder, SemanticModel, analyze
from osc2c.semantics.diagnostics import Diagnostic, Diagnostics, Severity
from osc2c.semantics.scope import Scope, Symbol, SymbolKind
from osc2c.semantics.types import (
    BOOL,
    FLOAT,
    INT,
    STRING,
    UINT,
    CompositeTypeInfo,
    EnumTypeInfo,
    FunctionTypeInfo,
    ListTypeInfo,
    ParameterInfo,
    PhysicalTypeInfo,
    PrimitiveTypeInfo,
    TypeInfo,
    UnitInfo,
    describe_type,
    dimension,
    is_assignable,
)

__all__ = [
    "BOOL",
    "FLOAT",
    "INT",
    "STRING",
    "UINT",
    "CompositeTypeInfo",
    "Diagnostic",
    "Diagnostics",
    "EnumTypeInfo",
    "FunctionTypeInfo",
    "ListTypeInfo",
    "ModelBuilder",
    "ParameterInfo",
    "PhysicalTypeInfo",
    "PrimitiveTypeInfo",
    "Scope",
    "SemanticModel",
    "Severity",
    "Symbol",
    "SymbolKind",
    "TypeInfo",
    "UnitInfo",
    "analyze",
    "describe_type",
    "dimension",
    "is_assignable",
]
