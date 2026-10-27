"""Maps OSC2 domain methods to simulator operations.

The registry is the only place that knows which OSC2 action names exist.
`drive` and `walk` are durative (they keep the branch running); the rest
complete as soon as the adapter accepts the command.
"""

from __future__ import annotations

from typing import Any, Callable

from osc2c.frontend import ast
from osc2c.runtime.context import ActorProxy, ExecutionContext, _actor_name


class UnsupportedMethod(KeyError):
    pass


LIGHT_MODES = frozenset(
    {"off", "auto", "low_beam", "high_beam", "position", "fog", "brake"}
)


class MethodRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., bool]] = {}

    def register(self, *names: str):
        def decorator(function: Callable[..., bool]) -> Callable[..., bool]:
            for name in names:
                self._handlers[name] = function
            return function

        return decorator

    def supports(self, name: str) -> bool:
        return name in self._handlers

    def invoke(
        self,
        name: str,
        target: ActorProxy,
        arguments: list[ast.Arg],
        with_clause: ast.BehaviorWith | None,
        context: ExecutionContext,
        inherited_modifiers: dict[str, tuple[list[Any], dict[str, Any]]] | None = None,
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]] | None = None,
    ) -> bool:
        """Run a method; return True when the behaviour should stay RUNNING."""
        handler = self._handlers.get(name)
        if handler is None:
            raise UnsupportedMethod(name)
        positional, named = _arguments(arguments, context)
        own = _modifiers(with_clause, context) if modifiers is None else modifiers
        combined = dict(inherited_modifiers or {})
        combined.update(own)
        actor = context.adapter.actor(target.name)
        if actor is None:
            raise RuntimeError(f"actor '{target.name}' is not spawned")
        return handler(context, target.name, positional, named, combined)


def _arguments(
    arguments: list[ast.Arg],
    context: ExecutionContext,
) -> tuple[list[Any], dict[str, Any]]:
    positional: list[Any] = []
    named: dict[str, Any] = {}
    for argument in arguments:
        if isinstance(argument, ast.PositionalArg):
            positional.append(context.evaluate(argument.value))
        elif isinstance(argument, ast.NamedArg):
            named[argument.name] = context.evaluate(argument.value)
    return positional, named


def modifier_values(
    applications: list[ast.ModifierApplication],
    context: ExecutionContext,
) -> dict[str, tuple[list[Any], dict[str, Any]]]:
    """Evaluate modifier applications into the registry's argument shape."""
    result: dict[str, tuple[list[Any], dict[str, Any]]] = {}
    for member in applications:
        result[member.name] = _arguments(member.args, context)
    return result


def _modifiers(
    with_clause: ast.BehaviorWith | None,
    context: ExecutionContext,
) -> dict[str, tuple[list[Any], dict[str, Any]]]:
    if with_clause is None:
        return {}
    return modifier_values(
        [
            member
            for member in with_clause.members
            if isinstance(member, ast.ModifierApplication)
        ],
        context,
    )


def _first(
    positional: list[Any],
    named: dict[str, Any],
    key: str,
) -> Any:
    if key in named:
        return named[key]
    if positional:
        return positional[0]
    raise ValueError(f"missing argument '{key}'")


class BuiltinMethods:
    """Default domain mapping shared by every adapter."""

    def __init__(self) -> None:
        self.registry = MethodRegistry()
        self.registry.register("drive", "walk")(self._drive)
        self.registry.register("move")(self._move)
        self.registry.register("change_speed")(self._change_speed)
        self.registry.register("assign_speed")(self._assign_speed)
        self.registry.register("keep_speed")(self._keep_speed)
        self.registry.register("remain_stationary")(self._remain_stationary)
        self.registry.register("assign_position")(self._assign_position)
        self.registry.register("change_lane")(self._change_lane)
        self.registry.register("set_lights")(self._set_lights)
        self.registry.register("assign_celestial_position")(self._celestial)

    def _drive(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        if "speed" in modifiers:
            values, keys = modifiers["speed"]
            context.adapter.set_speed(actor, float(_first(values, keys, "speed")))
        elif "speed" in named:
            context.adapter.set_speed(actor, float(named["speed"]))
        return True

    def _change_speed(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        target = named.get("target")
        if target is None and positional:
            target = positional[0]
        if target is None and "speed" in modifiers:
            values, keys = modifiers["speed"]
            target = _first(values, keys, "speed")
        if target is None:
            raise ValueError("change_speed requires a target speed")
        context.adapter.set_speed(actor, float(target))
        return False

    def _assign_speed(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        target = named.get("speed")
        if target is None and positional:
            target = positional[0]
        if target is None and "speed" in modifiers:
            values, keys = modifiers["speed"]
            target = _first(values, keys, "speed")
        if target is None:
            raise ValueError("assign_speed requires a speed")
        context.adapter.set_speed(actor, float(target))
        return False

    def _keep_speed(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        return True

    def _remain_stationary(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        context.adapter.set_speed(actor, 0.0)
        return True

    def _move(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        if any(key in modifiers for key in ("lane", "position")):
            self._assign_position(context, actor, positional, named, modifiers)
        elif "speed" in modifiers:
            values, keys = modifiers["speed"]
            context.adapter.set_speed(actor, float(_first(values, keys, "speed")))
        return True

    def _assign_position(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        adapter = context.adapter
        update: dict[str, Any] = {}
        if "lane" in modifiers:
            values, keys = modifiers["lane"]
            side = keys.get("side")
            if side is not None:
                count = int(_first(values, keys, "lane")) if values or "lane" in keys else 1
                sign = 1 if side in {"right", 1} else -1
                update["lane_offset"] = sign * count
                if "side_of" in keys:
                    update["reference"] = _actor_name(keys["side_of"])
            else:
                update["lane"] = int(_first(values, keys, "lane"))
        if "speed" in modifiers:
            values, keys = modifiers["speed"]
            update["speed"] = float(_first(values, keys, "speed"))
        if "position" in modifiers:
            values, keys = modifiers["position"]
            distance = keys.get("distance", values[0] if values else None)
            behind = keys.get("behind")
            ahead = keys.get("ahead_of")
            if distance is not None and behind is not None:
                update["reference"] = _actor_name(behind)
                update["distance"] = -float(distance)
            elif distance is not None and ahead is not None:
                update["reference"] = _actor_name(ahead)
                update["distance"] = float(distance)
            elif distance is not None:
                update["s"] = float(distance)
            for key in ("x", "y", "z", "h"):
                if key in keys:
                    update["heading" if key == "h" else key] = float(keys[key])
        for key in ("x", "y", "z"):
            if key in named:
                update[key] = float(named[key])
        if "lane" in named:
            update["lane"] = int(named["lane"])
        adapter.assign_position(actor, **update)
        return False

    def _change_lane(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        lanes = int(named.get("num_of_lanes", positional[0] if positional else 1))
        side = named.get("side", "right")
        if isinstance(side, int):
            side = "start" if side == 0 else "end"
        context.adapter.change_lane(actor, lanes, "right" if side in {"right", "end"} else "left")
        return not context.adapter.lane_change_complete(actor)

    def _set_lights(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        mode = named.get("mode", positional[0] if positional else "auto")
        mode = str(mode)
        if mode not in LIGHT_MODES:
            options = ", ".join(sorted(LIGHT_MODES))
            raise ValueError(f"unsupported light mode '{mode}' (expected {options})")
        context.adapter.set_lights(actor, mode)
        return False

    def _celestial(
        self,
        context: ExecutionContext,
        actor: str,
        positional: list[Any],
        named: dict[str, Any],
        modifiers: dict[str, tuple[list[Any], dict[str, Any]]],
    ) -> bool:
        azimuth = named.get("azimuth", positional[0] if positional else 0.0)
        elevation = named.get("elevation", positional[1] if len(positional) > 1 else 0.0)
        context.adapter.set_celestial_position(float(azimuth), float(elevation))
        return False
