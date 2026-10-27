"""OSC2 composition -> py_trees behavior tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import py_trees
from py_trees import common

from osc2c.adapters import ActorState, SimAdapter
from osc2c.adapters.mock import MockAdapter
from osc2c.backend.behaviors import (
    ActionLeaf,
    ActionScope,
    CallLeaf,
    EmitLeaf,
    UnsupportedLeaf,
    WaitLeaf,
    condition_text,
    expression_text,
    snapshot,
)
from osc2c.backend.initializer import InitializationError, ScenarioInitializer
from osc2c.backend.method_registry import BuiltinMethods, MethodRegistry, modifier_values
from osc2c.backend.modifiers import expand_behavior_with
from osc2c.frontend import ast
from osc2c.runtime.blackboard import EventRecord
from osc2c.runtime.context import ActorProxy, EvaluationError, ExecutionContext
from osc2c.semantics.builder import SemanticModel
from osc2c.semantics.scope import SymbolKind
from osc2c.semantics.types import CompositeTypeInfo, iter_composite_chain


class CompilationError(RuntimeError):
    pass


def _behavior_members(composite: CompositeTypeInfo) -> list[ast.Node]:
    """Executable members from the action itself or its nearest base."""
    for candidate in iter_composite_chain(composite):
        node = candidate.node
        if not isinstance(node, ast.ActionDecl):
            continue
        members = [
            member
            for member in node.members
            if isinstance(member, (ast.DoDirective, ast.OnDirective))
        ]
        if members:
            return members
    return []


def _action_parameters(
    composite: CompositeTypeInfo,
) -> list[tuple[str, ast.ParameterDecl]]:
    parameters: list[tuple[str, ast.ParameterDecl]] = []
    seen: set[str] = set()
    for candidate in iter_composite_chain(composite):
        for symbol in candidate.fields.values():
            if symbol.kind is not SymbolKind.PARAMETER or symbol.name in seen:
                continue
            if isinstance(symbol.node, ast.ParameterDecl):
                seen.add(symbol.name)
                parameters.append((symbol.name, symbol.node))
    return parameters


def _action_variables(composite: CompositeTypeInfo) -> list[ast.VariableDecl]:
    variables: list[ast.VariableDecl] = []
    seen: set[str] = set()
    for candidate in iter_composite_chain(composite):
        for symbol in candidate.fields.values():
            if symbol.kind is not SymbolKind.VARIABLE or symbol.name in seen:
                continue
            if isinstance(symbol.node, ast.VariableDecl):
                seen.add(symbol.name)
                variables.append(symbol.node)
    return variables


def _ignored_feature_warnings(model: SemanticModel) -> list[str]:
    """Report constructs the middle-end accepts but the backend does not apply."""
    warnings: list[str] = []
    for node in model.unit.walk():
        span = node.span
        if isinstance(node, ast.RemoveDefault):
            warnings.append(
                f"remove_default(...) at {span.source}:{span.line} is not "
                "applied by the runtime"
            )
        elif isinstance(node, ast.CoverageDecl):
            warnings.append(
                f"{node.mode}(...) at {span.source}:{span.line} is parsed but "
                "not recorded by the runtime"
            )
        elif isinstance(node, ast.CallDirective):
            symbol = model.resolved.get(id(node.invocation))
            target = symbol.type if symbol is not None else None
            if (
                isinstance(target, CompositeTypeInfo)
                and target.kind == "scenario"
                and not target.builtin
            ):
                warnings.append(
                    f"call to scenario '{target.name}' at "
                    f"{span.source}:{span.line} is type-checked but not executed "
                    "by the runtime"
                )
    return warnings


@dataclass
class RunResult:
    status: common.Status
    ticks: int
    time: float
    trace: list[EventRecord]
    actors: dict[str, ActorState]
    unsupported: list[str] = field(default_factory=list)

    @property
    def succeeded(self) -> bool:
        return self.status == common.Status.SUCCESS

    def to_dict(self) -> dict:
        return {
            "status": self.status.name,
            "ticks": self.ticks,
            "time": round(self.time, 6),
            "events": [record.name for record in self.trace],
            "actors": {
                name: {
                    "type": state.type_name,
                    "s": round(state.s, 6),
                    "lane": state.lane,
                    "speed": round(state.speed, 6),
                    "lights": state.lights,
                }
                for name, state in sorted(self.actors.items())
            },
            "unsupported": self.unsupported,
        }


@dataclass
class CompiledScenario:
    root: py_trees.behaviour.Behaviour
    context: ExecutionContext
    adapter: SimAdapter
    warnings: list[str] = field(default_factory=list)

    def tick(self) -> common.Status:
        for _ in self.root.tick():
            pass
        return self.root.status

    def advance(self, dt: float = 0.1) -> None:
        self.context.step(dt)

    def run(self, max_ticks: int = 1000, dt: float = 0.1) -> RunResult:
        status = self.tick()
        ticks = 1
        while status == common.Status.RUNNING and ticks < max_ticks:
            self.context.step(dt)
            status = self.tick()
            ticks += 1
        return RunResult(
            status=status,
            ticks=ticks,
            time=self.context.time,
            trace=list(self.context.blackboard.trace),
            actors=dict(self.adapter.actors),
            unsupported=list(self.context.blackboard.values.get("unsupported", [])),
        )

    def to_dict(self) -> dict:
        return snapshot(self.root)


class _Builder:
    def __init__(
        self,
        context: ExecutionContext,
        registry: MethodRegistry,
        warnings: list[str],
    ) -> None:
        self.context = context
        self.registry = registry
        self.warnings = warnings
        self._action_stack: list[int] = []

    def build(self, node: ast.Node) -> py_trees.behaviour.Behaviour:
        handler = getattr(self, f"_build_{type(node).__name__}", None)
        if handler is None:
            raise CompilationError(
                f"cannot compile {type(node).__name__} at "
                f"{node.span.source}:{node.span.line}"
            )
        return handler(node)

    def _build_DoDirective(self, node: ast.DoDirective) -> py_trees.behaviour.Behaviour:
        return self.build(node.member)

    def _build_LabeledStatement(self, node: ast.LabeledStatement) -> py_trees.behaviour.Behaviour:
        return self.build(node.statement)

    def _build_Composition(self, node: ast.Composition) -> py_trees.behaviour.Behaviour:
        children = [self.build(member) for member in node.members]
        if node.operator == "serial":
            return py_trees.composites.Sequence("serial", memory=True, children=children)
        if node.operator == "parallel":
            return py_trees.composites.Parallel(
                "parallel",
                policy=common.ParallelPolicy.SuccessOnAll(),
                children=children,
            )
        if node.operator == "one_of":
            # Selector would never tick alternatives after a RUNNING child;
            # SuccessOnOne runs all branches and lets the first success win.
            return py_trees.composites.Parallel(
                "one_of",
                policy=common.ParallelPolicy.SuccessOnOne(),
                children=children,
            )
        raise CompilationError(
            f"unsupported composition operator '{node.operator}' at "
            f"{node.span.source}:{node.span.line}"
        )

    def _build_BehaviorInvocation(
        self, node: ast.BehaviorInvocation
    ) -> py_trees.behaviour.Behaviour:
        if node.target is None:
            raise CompilationError(
                f"behaviour '{node.name}' has no target at "
                f"{node.span.source}:{node.span.line}"
            )
        target_text = expression_text(node.target)
        name = f"{target_text}.{node.name}"
        if id(node) in self.context.initialized_actions:
            return py_trees.behaviours.Success(name)
        applications, expansion_warnings = expand_behavior_with(
            self.context.model, node.with_clause
        )
        self.warnings.extend(expansion_warnings)
        action = self._attached_action(node)
        if action is not None:
            members = _behavior_members(action)
            if members:
                return self._apply_until(
                    node,
                    self._build_attached_action(node, action, members, applications),
                )
        if not self.registry.supports(node.name):
            reason = f"unsupported behaviour '{node.name}' on '{target_text}'"
            self.warnings.append(reason)
            return UnsupportedLeaf(name, reason, self.context)

        def invoke() -> bool:
            target = self.context.evaluate(node.target)
            if not isinstance(target, ActorProxy):
                raise EvaluationError(
                    f"behaviour '{node.name}' target is not an actor at "
                    f"{node.span.source}:{node.span.line}"
                )
            inherited = (
                self.context.ambient_modifiers
                if target.name == self.context.ambient_modifier_actor
                else None
            )
            return self.registry.invoke(
                node.name,
                target,
                node.args,
                None,
                self.context,
                inherited,
                modifiers=modifier_values(applications, self.context),
            )

        behavior = ActionLeaf(
            name,
            self.context,
            invoke,
            recurring=node.name
            in {"drive", "walk", "move", "keep_speed", "remain_stationary", "change_lane"},
        )
        return self._apply_until(node, behavior)

    def _attached_action(
        self, node: ast.BehaviorInvocation
    ) -> CompositeTypeInfo | None:
        """The action declaration behind a resolved `actor.behavior` method."""
        symbol = self.context.model.resolved.get(id(node))
        if symbol is None or symbol.kind is not SymbolKind.METHOD:
            return None
        declaration = symbol.node
        if not isinstance(declaration, ast.ActionDecl) or "." not in declaration.name:
            return None
        for composite in self.context.model.composites:
            if composite.kind == "action" and composite.node is declaration:
                return composite
        return None

    def _build_attached_action(
        self,
        node: ast.BehaviorInvocation,
        action: CompositeTypeInfo,
        members: list[ast.Node],
        applications: list[ast.ModifierApplication],
    ) -> py_trees.behaviour.Behaviour:
        if id(action) in self._action_stack:
            raise CompilationError(
                f"recursive action call '{action.name}' at "
                f"{node.span.source}:{node.span.line} is not supported"
            )
        self._action_stack.append(id(action))
        try:
            children = [self.build(member) for member in members]
        finally:
            self._action_stack.pop()
        child = (
            children[0]
            if len(children) == 1
            else py_trees.composites.Sequence(
                f"{action.name} body", memory=True, children=children
            )
        )
        bound_target: dict[str, Any] = {}

        def it() -> ActorProxy:
            # Filled by the bindings callable, which ActionScope runs first.
            return bound_target["actor"]

        return ActionScope(
            f"{expression_text(node.target)}.{node.name}",
            self.context,
            child,
            lambda: self._attached_bindings(
                node, action, bound_target, applications
            ),
            it=it,
            modifiers=lambda: bound_target["modifiers"],
        )

    def _attached_bindings(
        self,
        node: ast.BehaviorInvocation,
        action: CompositeTypeInfo,
        bound_target: dict[str, Any],
        applications: list[ast.ModifierApplication],
    ) -> dict[str, Any]:
        target = self.context.evaluate(node.target)
        if not isinstance(target, ActorProxy):
            raise EvaluationError(
                f"behaviour '{node.name}' target is not an actor at "
                f"{node.span.source}:{node.span.line}"
            )
        bound_target["actor"] = target
        bound = self._bind_action(
            _action_parameters(action),
            _action_variables(action),
            node.args,
            it=target,
        )
        bound_target["modifiers"] = self._attached_modifiers(
            target, bound, applications
        )
        return bound

    def _attached_modifiers(
        self,
        target: ActorProxy,
        bound: dict[str, Any],
        applications: list[ast.ModifierApplication],
    ) -> dict[str, tuple[list[Any], dict[str, Any]]]:
        if not applications:
            return {}
        previous_locals = self.context.locals
        previous_it = self.context.it
        self.context.locals = bound
        self.context.it = target
        try:
            return modifier_values(applications, self.context)
        finally:
            self.context.locals = previous_locals
            self.context.it = previous_it

    def _apply_until(
        self,
        node: ast.BehaviorInvocation,
        behavior: py_trees.behaviour.Behaviour,
    ) -> py_trees.behaviour.Behaviour:
        if node.with_clause is None:
            return behavior
        untils = [
            member
            for member in node.with_clause.members
            if isinstance(member, ast.UntilDirective)
        ]
        if not untils:
            return behavior
        children = [behavior]
        for directive in untils:
            children.append(
                WaitLeaf(
                    f"{behavior.name} until {condition_text(directive.specification)}",
                    directive.specification,
                    self.context,
                )
            )
        return py_trees.composites.Parallel(
            f"{behavior.name} until",
            policy=common.ParallelPolicy.SuccessOnOne(),
            children=children,
        )

    def _build_WaitDirective(self, node: ast.WaitDirective) -> py_trees.behaviour.Behaviour:
        return WaitLeaf(
            f"wait {condition_text(node.specification)}",
            node.specification,
            self.context,
        )

    def _build_EmitDirective(self, node: ast.EmitDirective) -> py_trees.behaviour.Behaviour:
        return EmitLeaf(f"emit {node.name}", node.name, self.context)

    def _build_CallDirective(self, node: ast.CallDirective) -> py_trees.behaviour.Behaviour:
        symbol = self.context.model.resolved.get(id(node.invocation))
        target = symbol.type if symbol is not None else None
        if (
            isinstance(node.invocation, ast.Call)
            and isinstance(target, CompositeTypeInfo)
            and target.kind == "action"
            and not target.builtin
            and isinstance(target.node, ast.ActionDecl)
        ):
            return self._build_action_call(node.invocation, target)
        return CallLeaf(
            f"call {expression_text(node.invocation)}",
            node.invocation,
            self.context,
        )

    def _build_action_call(
        self,
        call: ast.Call,
        action: CompositeTypeInfo,
    ) -> py_trees.behaviour.Behaviour:
        if id(action) in self._action_stack:
            raise CompilationError(
                f"recursive action call '{action.name}' at "
                f"{call.span.source}:{call.span.line} is not supported"
            )
        name = f"call {action.name}"
        behaviors = _behavior_members(action)
        if not behaviors:
            return py_trees.behaviours.Success(name)
        self._action_stack.append(id(action))
        try:
            children = [self.build(member) for member in behaviors]
        finally:
            self._action_stack.pop()
        child = (
            children[0]
            if len(children) == 1
            else py_trees.composites.Sequence(
                f"{action.name} body", memory=True, children=children
            )
        )
        return ActionScope(
            name,
            self.context,
            child,
            lambda: self._action_bindings(action, call),
        )

    def _action_bindings(
        self,
        action: CompositeTypeInfo,
        call: ast.Call,
    ) -> dict[str, Any]:
        return self._bind_action(
            _action_parameters(action),
            _action_variables(action),
            call.args,
        )

    def _bind_action(
        self,
        parameters: list[tuple[str, ast.ParameterDecl]],
        variables: list[ast.VariableDecl],
        arguments: list[ast.Arg],
        *,
        it: ActorProxy | None = None,
    ) -> dict[str, Any]:
        positional = [
            argument.value
            for argument in arguments
            if isinstance(argument, ast.PositionalArg)
        ]
        named = {
            argument.name: argument.value
            for argument in arguments
            if isinstance(argument, ast.NamedArg)
        }
        bound: dict[str, Any] = {}
        for index, (name, parameter) in enumerate(parameters):
            if index < len(positional):
                bound[name] = self.context.evaluate(positional[index])
            elif name in named:
                bound[name] = self.context.evaluate(named[name])

        previous_locals = self.context.locals
        previous_it = self.context.it
        self.context.locals = bound
        if it is not None:
            self.context.it = it
        try:
            for name, parameter in parameters:
                if name not in bound:
                    bound[name] = (
                        self.context.evaluate(parameter.default)
                        if parameter.default is not None
                        else None
                    )
            for variable in variables:
                if variable.sample is not None:
                    value = self.context.evaluate(variable.sample.default)
                else:
                    value = self.context.evaluate(variable.value)
                for name in variable.names:
                    bound[name] = value
        finally:
            self.context.locals = previous_locals
            self.context.it = previous_it
        return bound

    def _build_OnDirective(self, node: ast.OnDirective) -> py_trees.behaviour.Behaviour:
        reason = "on-directives are not supported by the stage-3 backend"
        self.warnings.append(reason)
        return UnsupportedLeaf("on", reason, self.context)


def compile_scenario(
    model: SemanticModel,
    adapter: SimAdapter | None = None,
    scenario_name: str | None = None,
    registry: MethodRegistry | None = None,
) -> CompiledScenario:
    errors = model.diagnostics.errors
    if errors:
        first = errors[0]
        raise CompilationError(
            f"semantic analysis failed ({len(errors)} error(s)); first: {first.format()}"
        )
    scenarios = [
        item
        for item in model.composites
        if item.kind == "scenario" and not item.builtin
    ]
    if not scenarios:
        raise CompilationError("no scenario declaration found")
    if scenario_name is None:
        scenario = scenarios[0]
    else:
        matches = [
            item
            for item in scenarios
            if item.name == scenario_name or item.qualified_name == scenario_name
        ]
        if not matches:
            available = ", ".join(item.qualified_name for item in scenarios)
            raise CompilationError(
                f"unknown scenario '{scenario_name}' (available: {available})"
            )
        scenario = matches[0]

    adapter = adapter or MockAdapter()
    context = ExecutionContext(model, adapter, scenario)
    methods = registry or BuiltinMethods().registry

    declaration = scenario.node
    assert isinstance(declaration, ast.ScenarioDecl)
    try:
        ScenarioInitializer(context, methods).apply(declaration)
    except InitializationError as error:
        raise CompilationError(str(error)) from error

    warnings: list[str] = list(context.ignored_constraints) + list(
        context.ignored_features
    )
    warnings.extend(_ignored_feature_warnings(model))

    builder = _Builder(context, methods, warnings)
    behaviors = [
        member
        for member in declaration.members
        if isinstance(member, (ast.DoDirective, ast.OnDirective))
    ]
    if not behaviors:
        root: py_trees.behaviour.Behaviour = py_trees.behaviours.Success("empty")
    else:
        children = [builder.build(item) for item in behaviors]
        root = (
            children[0]
            if len(children) == 1
            else py_trees.composites.Sequence("do", memory=True, children=children)
        )
    return CompiledScenario(root, context, adapter, warnings)


def scenario_type(model: SemanticModel, name: str | None = None) -> CompositeTypeInfo:
    scenarios = [
        item for item in model.composites if item.kind == "scenario" and not item.builtin
    ]
    if name is None:
        if not scenarios:
            raise CompilationError("no scenario declaration found")
        return scenarios[0]
    for item in scenarios:
        if item.name == name or item.qualified_name == name:
            return item
    raise CompilationError(f"unknown scenario '{name}'")
