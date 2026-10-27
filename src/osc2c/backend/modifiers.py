"""Expansion of user-defined modifiers into standard modifier applications.

A user-defined modifier such as `modifier fast of vehicle: speed(10 mps)`
carries no runtime behaviour of its own. The backend flattens its body into
the standard applications the method registry already understands. Expansion
is compile-time only: the resulting AST nodes keep their original argument
expressions and are evaluated when the behaviour is invoked.
"""

from __future__ import annotations

from osc2c.frontend import ast
from osc2c.semantics import stdlib
from osc2c.semantics.builder import SemanticModel
from osc2c.semantics.types import CompositeTypeInfo

STANDARD_NAMESPACES = {stdlib.STANDARD_NS, stdlib.STDTYPES_NS}


def modifier_composite(
    model: SemanticModel,
    application: ast.ModifierApplication,
) -> CompositeTypeInfo | None:
    symbol = model.resolved.get(id(application))
    composite = symbol.type if symbol is not None else None
    if isinstance(composite, CompositeTypeInfo) and composite.kind == "modifier":
        return composite
    return None


def expand_behavior_with(
    model: SemanticModel,
    with_clause: ast.BehaviorWith | None,
) -> tuple[list[ast.ModifierApplication], list[str]]:
    """Applications from a `with:` clause with user-defined modifiers flattened."""
    if with_clause is None:
        return [], []
    applications = [
        member
        for member in with_clause.members
        if isinstance(member, ast.ModifierApplication)
    ]
    return expand_modifier_applications(model, applications)


def expand_modifier_applications(
    model: SemanticModel,
    applications: list[ast.ModifierApplication],
    *,
    _stack: tuple[int, ...] = (),
) -> tuple[list[ast.ModifierApplication], list[str]]:
    """Flatten user-defined modifiers, preserving textual order.

    Later applications override earlier ones by name in the registry, so
    returning the body applications in source order keeps OSC2's
    last-application-wins rule. Standard applications pass through unchanged.
    """
    expanded: list[ast.ModifierApplication] = []
    warnings: list[str] = []
    for application in applications:
        composite = modifier_composite(model, application)
        if composite is None:
            span = application.span
            warnings.append(
                f"modifier '{application.name}' at {span.source}:{span.line} "
                "could not be resolved and is not applied"
            )
            continue
        if composite.builtin or composite.namespace in STANDARD_NAMESPACES:
            expanded.append(application)
            continue
        declaration = composite.node
        if not isinstance(declaration, ast.ModifierDecl):
            span = application.span
            warnings.append(
                f"user-defined modifier '{composite.name}' at "
                f"{span.source}:{span.line} has no expandable declaration and "
                "is not applied"
            )
            continue
        if id(composite) in _stack:
            span = application.span
            warnings.append(
                f"cyclic user-defined modifier '{application.name}' at "
                f"{span.source}:{span.line}; expansion stopped"
            )
            continue

        body: list[ast.ModifierApplication] = []
        for member in declaration.members:
            if isinstance(member, ast.ModifierApplication):
                if member.target is not None:
                    warnings.append(
                        f"modifier application '{member.name}' with an explicit "
                        f"target inside modifier '{composite.name}' at "
                        f"{declaration.span.source}:{declaration.span.line} "
                        "cannot be expanded and is ignored"
                    )
                    continue
                body.append(member)
            else:
                warnings.append(
                    f"modifier '{composite.name}' at "
                    f"{declaration.span.source}:{declaration.span.line} contains "
                    f"{type(member).__name__}, which cannot be expanded and is ignored"
                )
        if not body:
            if not declaration.members:
                warnings.append(
                    f"user-defined modifier '{composite.name}' at "
                    f"{declaration.span.source}:{declaration.span.line} contains "
                    "no applicable modifier applications and is not applied"
                )
            continue

        nested, nested_warnings = expand_modifier_applications(
            model,
            body,
            _stack=_stack + (id(composite),),
        )
        expanded.extend(nested)
        warnings.extend(nested_warnings)
    return expanded, warnings
