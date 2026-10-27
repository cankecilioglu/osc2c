"""Runtime expression evaluation and scenario state.

Values are kept in SI units: physical literals are converted with the
`UnitInfo` resolved by the middle-end, so `35 kph` and `9.72 m/s` compare
equal without the simulator knowing about units.
"""

from __future__ import annotations

from typing import Any

from osc2c.adapters import ActorState, SimAdapter
from osc2c.frontend import ast
from osc2c.runtime.blackboard import Blackboard
from osc2c.semantics.scope import SymbolKind
from osc2c.semantics.stdlib import UNITS
from osc2c.semantics.types import CompositeTypeInfo, composite_member
from osc2c.semantics.builder import SemanticModel


class EvaluationError(RuntimeError):
    pass


class ActorProxy:
    def __init__(self, context: ExecutionContext, name: str) -> None:
        self._context = context
        self.name = name

    @property
    def state(self) -> ActorState:
        state = self._context.adapter.actor(self.name)
        if state is None:
            raise EvaluationError(f"actor '{self.name}' does not exist")
        return state

    @property
    def position(self) -> PositionProxy:
        return PositionProxy(self._context, self.name)

    def __repr__(self) -> str:
        return f"ActorProxy({self.name!r})"


class PositionProxy:
    def __init__(self, context: ExecutionContext, name: str) -> None:
        self._context = context
        self.name = name

    @property
    def x(self) -> float:
        return self._context.adapter.position(self.name)[0]

    @property
    def y(self) -> float:
        return self._context.adapter.position(self.name)[1]

    @property
    def z(self) -> float:
        return self._context.adapter.position(self.name)[2]

    def ahead_of(self, other: ActorProxy | str) -> float:
        return self._context.adapter.ahead_of(self.name, _actor_name(other))

    def euclidean(self, other: ActorProxy | str) -> float:
        return self._context.adapter.euclidean(self.name, _actor_name(other))


def _actor_name(value: Any) -> str:
    if isinstance(value, ActorProxy):
        return value.name
    if isinstance(value, str):
        return value
    raise EvaluationError(f"expected an actor, got {value!r}")


class ExecutionContext:
    """Scenario-local state plus recursive AST expression evaluation."""

    def __init__(
        self,
        model: SemanticModel,
        adapter: SimAdapter,
        scenario: CompositeTypeInfo,
    ) -> None:
        self.model = model
        self.adapter = adapter
        self.scenario = scenario
        self.blackboard = Blackboard()
        self.fields: dict[str, Any] = {}
        self.locals: dict[str, Any] | None = None
        self.it: Any = None
        self.ambient_modifiers: dict[str, tuple[list[Any], dict[str, Any]]] = {}
        self.ambient_modifier_actor: str | None = None
        self.time = 0.0
        self.actor_types: dict[str, CompositeTypeInfo] = {}
        self.event_aliases: dict[str, str] = {}
        self.initialized_actions: set[int] = set()
        self.ignored_constraints: list[str] = []
        self.ignored_features: list[str] = []
        self._initialise()

    # -------------------------------------------------------- initial state

    def _initialise(self) -> None:
        assert self.scenario.scope is not None
        declarations = [
            (name, symbol)
            for name, symbol in self.scenario.fields.items()
            if symbol.node is not None
        ]
        for name, symbol in declarations:
            declaration = symbol.node
            if isinstance(declaration, ast.ParameterDecl):
                self._initialise_parameter(name, symbol, declaration)
            elif isinstance(declaration, ast.VariableDecl):
                if declaration.sample is not None:
                    span = declaration.span
                    self.ignored_features.append(
                        f"sample(...) on '{name}' at {span.source}:{span.line} is "
                        "not evaluated; the sample default value is used"
                    )
                    default = declaration.sample.default
                    self.fields[name] = (
                        self.evaluate(default) if default is not None else None
                    )
                else:
                    self.fields[name] = (
                        self.evaluate(declaration.value)
                        if declaration.value is not None
                        else None
                    )
        for declaration in self.scenario.scope.iter_symbols():
            node = declaration.node
            if isinstance(node, ast.EventDecl) and node.specification is not None:
                reference = node.specification.reference
                if reference is not None:
                    self.event_aliases[node.name] = reference.name.lstrip("@")

    def _initialise_parameter(self, name: str, symbol, declaration: ast.ParameterDecl) -> None:
        type_info = symbol.type
        if isinstance(type_info, CompositeTypeInfo) and type_info.kind == "actor":
            actor = self.adapter.spawn(name, type_info.name)
            actor.attributes.setdefault("name", name)
            self.actor_types[name] = type_info
            proxy = ActorProxy(self, name)
            self.fields[name] = proxy
            self._initialise_actor_fields(proxy, type_info)
            for constraint in declaration.constraints:
                self._apply_keep(proxy, constraint)
            return
        if declaration.default is not None:
            self.fields[name] = self.evaluate(declaration.default)
        else:
            self.fields[name] = None

    def _initialise_actor_fields(
        self,
        actor: ActorProxy,
        type_info: CompositeTypeInfo,
    ) -> None:
        for field, symbol in type_info.fields.items():
            declaration = symbol.node
            if not isinstance(declaration, ast.VariableDecl):
                continue
            if field in actor.state.attributes:
                continue
            previous_it = self.it
            self.it = actor
            try:
                actor.state.attributes[field] = (
                    self.evaluate(declaration.value)
                    if declaration.value is not None
                    else None
                )
            finally:
                self.it = previous_it
        for event in type_info.events.values():
            node = event.node
            if isinstance(node, ast.EventDecl) and node.specification is not None:
                reference = node.specification.reference
                if reference is not None:
                    self.event_aliases.setdefault(
                        node.name, reference.name.lstrip("@")
                    )

    def _apply_keep(self, actor: ActorProxy, constraint: ast.Node) -> None:
        if not isinstance(constraint, ast.KeepConstraint):
            return
        expression = constraint.expr
        if not (
            isinstance(expression, ast.BinaryOp)
            and expression.op == "=="
            and isinstance(expression.left, ast.FieldAccess)
            and isinstance(expression.left.target, ast.ItExpr)
        ):
            span = constraint.span
            self.ignored_constraints.append(
                f"keep constraint at {span.source}:{span.line} is validated but not "
                "enforced; only keep(it.<field> == value) is applied"
            )
            return
        field = expression.left.field
        previous_it = self.it
        self.it = actor
        try:
            value = self.evaluate(expression.right)
        finally:
            self.it = previous_it
        if field == "speed":
            self.adapter.set_speed(actor.name, float(value))
        elif field == "position":
            return
        else:
            actor.state.attributes[field] = value

    # ------------------------------------------------------------ advancing

    def step(self, dt: float) -> None:
        self.adapter.step(dt)
        self.time += float(dt)

    def emit(self, name: str, payload: Any = None) -> None:
        self.blackboard.emit(self.resolve_event(name), self.time, payload)

    def resolve_event(self, name: str) -> str:
        key = name.lstrip("@")
        return self.event_aliases.get(key, key)

    # ------------------------------------------------------------ evaluation

    def evaluate(self, expression: ast.Expr | None) -> Any:
        if expression is None:
            return None
        handler = getattr(self, f"_eval_{type(expression).__name__}", None)
        if handler is None:
            raise EvaluationError(
                f"cannot evaluate {type(expression).__name__} at "
                f"{expression.span.source}:{expression.span.line}"
            )
        return handler(expression)

    def _eval_IntLiteral(self, expression: ast.IntLiteral) -> int:
        return expression.value

    def _eval_FloatLiteral(self, expression: ast.FloatLiteral) -> float:
        return expression.value

    def _eval_PhysicalLiteral(self, expression: ast.PhysicalLiteral) -> float:
        unit = self.model.unit_of(expression)
        if unit is not None:
            return unit.to_si(expression.value)
        raw = UNITS.get(expression.unit)
        if raw is None:
            raise EvaluationError(f"unknown unit '{expression.unit}'")
        return expression.value * raw[1] + raw[2]

    def _eval_BoolLiteral(self, expression: ast.BoolLiteral) -> bool:
        return expression.value

    def _eval_StringLiteral(self, expression: ast.StringLiteral) -> str:
        return expression.value

    def _eval_EnumValueRef(self, expression: ast.EnumValueRef) -> Any:
        symbol = self.model.symbol_at(expression)
        if symbol is not None and symbol.enum_value is not None:
            return symbol.enum_value
        builtin = {"start": 0, "end": 1}
        if expression.member in builtin:
            return builtin[expression.member]
        return expression.member

    def _eval_ListLiteral(self, expression: ast.ListLiteral) -> list[Any]:
        return [self.evaluate(item) for item in expression.elements]

    def _eval_RangeLiteral(self, expression: ast.RangeLiteral) -> list[Any]:
        start = self.evaluate(expression.start)
        end = self.evaluate(expression.end)
        if isinstance(start, int) and isinstance(end, int):
            step = 1 if end >= start else -1
            return list(range(start, end + step, step))
        if isinstance(start, float) and isinstance(end, float):
            return [start, end]
        raise EvaluationError("range bounds must be numeric")

    def _eval_Identifier(self, expression: ast.Identifier) -> Any:
        parts = expression.parts
        if len(parts) == 1:
            name = parts[0]
            if self.locals is not None and name in self.locals:
                return self.locals[name]
            if name in self.fields:
                return self.fields[name]
            symbol = self.model.symbol_at(expression)
            if symbol is not None and symbol.kind is SymbolKind.ENUM_MEMBER:
                return symbol.enum_value
            if symbol is not None and symbol.kind is SymbolKind.GLOBAL_PARAMETER:
                node = symbol.node
                if isinstance(node, ast.ParameterDecl) and node.default is not None:
                    return self.evaluate(node.default)
            if name in {"start", "end"}:
                return 0 if name == "start" else 1
            if name in {"left", "right", "auto", "high_beam", "off"}:
                return name
            raise EvaluationError(f"unknown identifier '{name}'")
        joined = "::".join(parts)
        if joined in self.fields:
            return self.fields[joined]
        return self._eval_Identifier(ast.Identifier(expression.span, [parts[-1]]))

    def _eval_ItExpr(self, expression: ast.ItExpr) -> Any:
        if self.it is None:
            raise EvaluationError("'it' is not bound in this context")
        return self.it

    def _eval_FieldAccess(self, expression: ast.FieldAccess) -> Any:
        target = self.evaluate(expression.target)
        field = expression.field
        if isinstance(target, ActorProxy):
            if field == "position":
                return target.position
            if field == "name":
                return target.state.attributes.get("name", target.name)
            if field == "speed":
                return self.adapter.speed(target.name)
            if field in {"s", "lane", "x", "y", "z", "heading", "lights", "type_name"}:
                return getattr(target.state, field)
            if field in target.state.attributes:
                return target.state.attributes[field]
            raise EvaluationError(f"actor '{target.name}' has no member '{field}'")
        if isinstance(target, PositionProxy):
            if field in {"x", "y", "z"}:
                return getattr(target, field)
            state = self.adapter.actor(target.name)
            if state is not None and field in {"s", "lane", "heading"}:
                return getattr(state, field)
            raise EvaluationError(f"position has no member '{field}'")
        if isinstance(target, dict):
            return target.get(field)
        if hasattr(target, field):
            return getattr(target, field)
        raise EvaluationError(f"cannot read member '{field}'")

    def _eval_Cast(self, expression: ast.Cast) -> Any:
        value = self.evaluate(expression.target)
        type_info = self.model.type_ref_of(expression.type)
        name = getattr(type_info, "name", None)
        if name in {"float", "length", "speed", "time", "angle", "distance"}:
            return float(value)
        if name in {"int", "uint"}:
            return int(value)
        if name == "bool":
            return bool(value)
        if name == "string":
            return str(value)
        return value

    def _eval_TypeTest(self, expression: ast.TypeTest) -> bool:
        value = self.evaluate(expression.target)
        type_info = self.model.type_ref_of(expression.type)
        name = getattr(type_info, "name", None)
        return type(getattr(value, "state", value)).__name__.lower() == str(name).lower()

    def _eval_ElementAccess(self, expression: ast.ElementAccess) -> Any:
        target = self.evaluate(expression.target)
        index = self.evaluate(expression.index)
        return target[index]

    def _eval_Call(self, expression: ast.Call) -> Any:
        positional, named = self._evaluate_args(expression.args)
        if isinstance(expression.target, ast.FieldAccess):
            receiver = self.evaluate(expression.target.target)
            return self._call_method(receiver, expression.target.field, positional, named)
        if isinstance(expression.target, ast.Identifier):
            name = "::".join(expression.target.parts)
            return self._call_method(self.scenario, name, positional, named)
        raise EvaluationError("unsupported call target")

    def _evaluate_args(self, args: list[ast.Arg]) -> tuple[list[Any], dict[str, Any]]:
        positional: list[Any] = []
        named: dict[str, Any] = {}
        for arg in args:
            if isinstance(arg, ast.PositionalArg):
                positional.append(self.evaluate(arg.value))
            elif isinstance(arg, ast.NamedArg):
                named[arg.name] = self.evaluate(arg.value)
            else:
                raise EvaluationError(f"unsupported argument {type(arg).__name__}")
        return positional, named

    def call(self, receiver: Any, method: str, *arguments: Any) -> Any:
        return self._call_method(receiver, method, list(arguments), {})

    def _call_method(
        self,
        receiver: Any,
        method: str,
        positional: list[Any],
        named: dict[str, Any],
    ) -> Any:
        if isinstance(receiver, PositionProxy):
            value = named.get("other", positional[0] if positional else None)
            if method == "ahead_of":
                return receiver.ahead_of(value)
            if method == "euclidean":
                return receiver.euclidean(value)
            raise EvaluationError(f"unknown position method '{method}'")

        if isinstance(receiver, ActorProxy):
            composite = self.actor_types.get(receiver.name)
            symbol = (
                composite_member(composite, method, "methods")
                if composite is not None
                else None
            )
            if symbol is not None and isinstance(symbol.node, ast.MethodDecl):
                return self._call_user_method(symbol.node, receiver, positional, named)
            return None

        if isinstance(receiver, CompositeTypeInfo):
            symbol = composite_member(receiver, method, "methods")
            if symbol is not None and isinstance(symbol.node, ast.MethodDecl):
                return self._call_user_method(symbol.node, receiver, positional, named)
            return None

        raise EvaluationError(f"unknown receiver for method '{method}'")

    def _call_user_method(
        self,
        declaration: ast.MethodDecl,
        receiver: Any,
        positional: list[Any],
        named: dict[str, Any],
    ) -> Any:
        implementation = declaration.implementation
        if implementation.mode != "expression" or implementation.expression is None:
            return None
        parameters = [
            item.name
            for item in (declaration.parameters or [])
        ]
        bound = dict(named)
        for index, value in enumerate(positional):
            if index < len(parameters):
                bound[parameters[index]] = value
        previous_it = self.it
        previous_locals = self.locals
        self.it = receiver if isinstance(receiver, ActorProxy) else None
        self.locals = bound
        try:
            return self.evaluate(implementation.expression)
        finally:
            self.it = previous_it
            self.locals = previous_locals

    def _eval_UnaryOp(self, expression: ast.UnaryOp) -> Any:
        value = self.evaluate(expression.operand)
        if expression.op == "-":
            return -value
        if expression.op == "+":
            return +value
        if expression.op in {"not", "!"}:
            return not value
        raise EvaluationError(f"unknown unary operator '{expression.op}'")

    def _eval_BinaryOp(self, expression: ast.BinaryOp) -> Any:
        op = expression.op
        if op in {"and", "&&"}:
            return bool(self.evaluate(expression.left)) and bool(self.evaluate(expression.right))
        if op in {"or", "||"}:
            return bool(self.evaluate(expression.left)) or bool(self.evaluate(expression.right))
        if op == "=>":
            return (not bool(self.evaluate(expression.left))) or bool(
                self.evaluate(expression.right)
            )
        left = self.evaluate(expression.left)
        right = self.evaluate(expression.right)
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise EvaluationError("division by zero")
            return left / right
        if op == "%":
            return left % right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        if op == "in":
            return left in right
        raise EvaluationError(f"unknown binary operator '{op}'")

    def _eval_TernaryOp(self, expression: ast.TernaryOp) -> Any:
        branch = expression.then if self.evaluate(expression.condition) else expression.otherwise
        return self.evaluate(branch)
