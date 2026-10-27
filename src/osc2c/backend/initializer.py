"""Applies `at: start` placement actions before the first tick.

OSC2 marks actions that must happen at scenario start with the `at: start`
modifier. Running them through the behaviour tree would place actors one tick
late, so they are invoked once during compilation and replaced by success
leaves.
"""

from __future__ import annotations

from osc2c.backend.method_registry import (
    MethodRegistry,
    UnsupportedMethod,
    modifier_values,
)
from osc2c.backend.modifiers import expand_behavior_with
from osc2c.frontend import ast
from osc2c.runtime.context import ActorProxy, ExecutionContext


class InitializationError(RuntimeError):
    pass


# Durative behaviours (`drive`, `walk`) are deliberately not hoisted: their
# speed modifier must stay under the behaviour tree's control.
HOISTED_BEHAVIOURS = {
    "assign_position",
    "assign_speed",
    "change_lane",
    "change_speed",
    "set_lights",
    "assign_celestial_position",
}


class ScenarioInitializer:
    def __init__(self, context: ExecutionContext, registry: MethodRegistry) -> None:
        self.context = context
        self.registry = registry

    def apply(self, declaration: ast.ScenarioDecl) -> None:
        for member in declaration.members:
            if isinstance(member, ast.DoDirective):
                self._walk(member.member)

    def _walk(self, node: ast.Node) -> None:
        if isinstance(node, ast.Composition):
            for member in node.members:
                self._walk(member)
        elif isinstance(node, ast.LabeledStatement):
            self._walk(node.statement)
        elif isinstance(node, ast.BehaviorInvocation):
            self._apply(node)

    def _apply(self, node: ast.BehaviorInvocation) -> None:
        if node.target is None or node.name not in HOISTED_BEHAVIOURS:
            return
        if not self.registry.supports(node.name):
            return
        applications, expansion_warnings = expand_behavior_with(
            self.context.model, node.with_clause
        )
        if not _has_start_modifier(applications):
            return
        self.context.ignored_features.extend(expansion_warnings)
        target = self.context.evaluate(node.target)
        if not isinstance(target, ActorProxy):
            return
        try:
            self.registry.invoke(
                node.name,
                target,
                node.args,
                None,
                self.context,
                modifiers=modifier_values(applications, self.context),
            )
        except UnsupportedMethod:
            return
        except Exception as error:
            span = node.span
            raise InitializationError(
                f"at: start action '{node.name}' failed at "
                f"{span.source}:{span.line}: {error}"
            ) from error
        self.context.initialized_actions.add(id(node))


def _has_start_modifier(applications: list[ast.ModifierApplication]) -> bool:
    for member in applications:
        for argument in member.args:
            if not isinstance(argument, ast.NamedArg) or argument.name != "at":
                continue
            if _is_start(argument.value):
                return True
    return False


def _is_start(expression: ast.Expr) -> bool:
    if isinstance(expression, ast.Identifier):
        return expression.parts == ["start"]
    if isinstance(expression, ast.EnumValueRef):
        return expression.member == "start"
    if isinstance(expression, ast.IntLiteral):
        return expression.value == 0
    return False
