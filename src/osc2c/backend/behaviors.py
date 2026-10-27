"""py_trees leaves for OSC2 runtime constructs."""

from __future__ import annotations

from typing import Any, Callable

import py_trees
from py_trees import common

from osc2c.frontend import ast
from osc2c.runtime.context import ExecutionContext


class ActionLeaf(py_trees.behaviour.Behaviour):
    """Runs an adapter command once, or every tick for durative actions."""

    def __init__(
        self,
        name: str,
        context: ExecutionContext,
        action: Callable[[], bool | None],
        recurring: bool = False,
    ) -> None:
        super().__init__(name)
        self.context = context
        self._action = action
        self._recurring = recurring
        self._done = False

    def initialise(self) -> None:
        self._done = False

    def update(self) -> common.Status:
        if self._done and not self._recurring:
            return common.Status.SUCCESS
        ongoing = bool(self._action())
        self._done = True
        if ongoing:
            return common.Status.RUNNING
        return common.Status.SUCCESS


class EmitLeaf(ActionLeaf):
    def __init__(self, name: str, event: str, context: ExecutionContext) -> None:
        super().__init__(name, context, lambda: context.emit(event))


class CallLeaf(ActionLeaf):
    def __init__(self, name: str, expression: ast.Expr, context: ExecutionContext) -> None:
        super().__init__(name, context, lambda: context.evaluate(expression))


class ActionScope(py_trees.behaviour.Behaviour):
    """Binds an action call's parameters and locals around its body."""

    def __init__(
        self,
        name: str,
        context: ExecutionContext,
        child: py_trees.behaviour.Behaviour,
        bindings: Callable[[], dict[str, Any]],
        it: Callable[[], Any] | None = None,
        modifiers: Callable[[], dict[str, tuple[list[Any], dict[str, Any]]]] | None = None,
    ) -> None:
        super().__init__(name)
        self.context = context
        self.child = child
        self._bindings = bindings
        self._it = it
        self._modifiers = modifiers
        self._bound: dict[str, Any] | None = None
        self._it_value: Any = None
        self._modifier_map: dict[str, tuple[list[Any], dict[str, Any]]] = {}
        self._status: common.Status | None = None

    def initialise(self) -> None:
        self._status = None
        self._bound = self._bindings()
        self._it_value = self._it() if self._it is not None else None
        self._modifier_map = self._modifiers() if self._modifiers is not None else {}

    def update(self) -> common.Status:
        if self._status not in (None, common.Status.RUNNING):
            return self._status
        assert self._bound is not None
        previous_locals = self.context.locals
        previous_it = self.context.it
        previous_modifiers = self.context.ambient_modifiers
        previous_actor = self.context.ambient_modifier_actor
        self.context.locals = self._bound
        if self._it is not None:
            self.context.it = self._it_value
            if previous_actor == self._it_value.name:
                merged = {**previous_modifiers, **self._modifier_map}
            else:
                merged = dict(self._modifier_map)
            self.context.ambient_modifiers = merged
            self.context.ambient_modifier_actor = self._it_value.name
        try:
            self.child.tick_once()
        finally:
            self.context.locals = previous_locals
            self.context.it = previous_it
            self.context.ambient_modifiers = previous_modifiers
            self.context.ambient_modifier_actor = previous_actor
        self._status = self.child.status
        return self._status

    def terminate(self, new_status: common.Status) -> None:
        self.child.stop(new_status)
        self._status = None if new_status == common.Status.INVALID else self._status


class WaitLeaf(py_trees.behaviour.Behaviour):
    """Waits for an event, a boolean condition, an edge or elapsed time."""

    def __init__(
        self,
        name: str,
        specification: ast.EventSpec,
        context: ExecutionContext,
    ) -> None:
        super().__init__(name)
        self.specification = specification
        self.context = context
        self._started: float | None = None
        self._previous: bool | None = None

    def initialise(self) -> None:
        self._started = None
        self._previous = None

    def update(self) -> common.Status:
        specification = self.specification
        if specification.reference is not None:
            name = self.context.resolve_event(specification.reference.name)
            if self.context.blackboard.raised(name):
                return common.Status.SUCCESS
            return common.Status.RUNNING
        condition = specification.condition
        if condition is None:
            return common.Status.SUCCESS
        if isinstance(condition, ast.ElapsedCond):
            if self._started is None:
                self._started = self.context.time
            duration = float(self.context.evaluate(condition.expr))
            if self.context.time - self._started >= duration:
                return common.Status.SUCCESS
            return common.Status.RUNNING
        if isinstance(condition, ast.EveryCond):
            if self._started is None:
                self._started = self.context.time
            period = float(self.context.evaluate(condition.expr))
            if period <= 0:
                return common.Status.SUCCESS
            return (
                common.Status.SUCCESS
                if self.context.time - self._started >= period
                else common.Status.RUNNING
            )
        current = bool(self.context.evaluate(condition.expr))
        if isinstance(condition, ast.BoolCond):
            return common.Status.SUCCESS if current else common.Status.RUNNING
        if self._previous is None:
            self._previous = current
            return common.Status.RUNNING
        previous = self._previous
        self._previous = current
        if isinstance(condition, ast.RiseCond) and current and not previous:
            return common.Status.SUCCESS
        if isinstance(condition, ast.FallCond) and previous and not current:
            return common.Status.SUCCESS
        return common.Status.RUNNING


class UnsupportedLeaf(py_trees.behaviour.Behaviour):
    def __init__(self, name: str, reason: str, context: ExecutionContext) -> None:
        super().__init__(name)
        self.reason = reason
        self.context = context

    def initialise(self) -> None:
        self.context.blackboard.values.setdefault("unsupported", []).append(self.reason)
        self.logger.warning(self.reason)

    def update(self) -> common.Status:
        return common.Status.FAILURE


def expression_text(expression: ast.Expr | None) -> str:
    if expression is None:
        return "<none>"
    if isinstance(expression, ast.IntLiteral):
        return str(expression.value)
    if isinstance(expression, ast.FloatLiteral):
        return str(expression.value)
    if isinstance(expression, ast.PhysicalLiteral):
        return f"{expression.value:g}{expression.unit}"
    if isinstance(expression, ast.BoolLiteral):
        return "true" if expression.value else "false"
    if isinstance(expression, ast.StringLiteral):
        return f'"{expression.value}"'
    if isinstance(expression, ast.Identifier):
        return "::".join(expression.parts)
    if isinstance(expression, ast.ItExpr):
        return "it"
    if isinstance(expression, ast.EnumValueRef):
        return f"{expression.enum}.{expression.member}" if expression.enum else expression.member
    if isinstance(expression, ast.FieldAccess):
        return f"{expression_text(expression.target)}.{expression.field}"
    if isinstance(expression, ast.UnaryOp):
        return f"{expression.op}{expression_text(expression.operand)}"
    if isinstance(expression, ast.BinaryOp):
        return f"{expression_text(expression.left)} {expression.op} {expression_text(expression.right)}"
    if isinstance(expression, ast.TernaryOp):
        return (
            f"{expression_text(expression.condition)} ? {expression_text(expression.then)} "
            f": {expression_text(expression.otherwise)}"
        )
    if isinstance(expression, ast.Call):
        arguments = ", ".join(_argument_text(item) for item in expression.args)
        return f"{expression_text(expression.target)}({arguments})"
    if isinstance(expression, ast.ListLiteral):
        return "[" + ", ".join(expression_text(item) for item in expression.elements) + "]"
    if isinstance(expression, ast.RangeLiteral):
        return f"[{expression_text(expression.start)}..{expression_text(expression.end)}]"
    if isinstance(expression, ast.ElementAccess):
        return f"{expression_text(expression.target)}[{expression_text(expression.index)}]"
    return type(expression).__name__


def _argument_text(argument: ast.Arg) -> str:
    if isinstance(argument, ast.NamedArg):
        return f"{argument.name}: {expression_text(argument.value)}"
    if isinstance(argument, ast.PositionalArg):
        return expression_text(argument.value)
    return type(argument).__name__


def condition_text(specification: ast.EventSpec) -> str:
    if specification.reference is not None:
        return f"@{specification.reference.name.lstrip('@')}"
    condition = specification.condition
    if condition is None:
        return "true"
    if isinstance(condition, ast.ElapsedCond):
        return f"elapsed({expression_text(condition.expr)})"
    if isinstance(condition, ast.RiseCond):
        return f"rise({expression_text(condition.expr)})"
    if isinstance(condition, ast.FallCond):
        return f"fall({expression_text(condition.expr)})"
    if isinstance(condition, ast.EveryCond):
        return f"every({expression_text(condition.expr)})"
    return expression_text(condition.expr)


def snapshot(node: py_trees.behaviour.Behaviour) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": type(node).__name__,
        "name": node.name,
    }
    children = getattr(node, "children", None)
    if children:
        result["children"] = [snapshot(child) for child in children]
    elif isinstance(node, ActionScope):
        result["child"] = snapshot(node.child)
    return result
