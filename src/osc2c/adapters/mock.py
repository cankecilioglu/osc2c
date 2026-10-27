"""Deterministic simulator stub.

The mock keeps a one-dimensional road parametrisation so topological checks
(`ahead_of`) stay meaningful without CARLA: `s` grows along the lane, lane
indices change laterally. Actors move at their target speed every step.
"""

from __future__ import annotations

import math

from osc2c.adapters import ActorState


class MockAdapter:
    def __init__(self) -> None:
        self.actors: dict[str, ActorState] = {}
        self.time = 0.0
        self.azimuth = 0.0
        self.elevation = 0.0
        self.light_history: list[tuple[str, str]] = []
        self.lane_history: list[tuple[str, int]] = []

    # ----------------------------------------------------------- lifecycle

    def reset(self) -> None:
        self.actors.clear()
        self.time = 0.0
        self.azimuth = 0.0
        self.elevation = 0.0
        self.light_history.clear()
        self.lane_history.clear()

    def spawn(self, name: str, type_name: str) -> ActorState:
        state = ActorState(
            name=name,
            type_name=type_name,
            s=float(len(self.actors) * 20.0),
            x=float(len(self.actors) * 20.0),
        )
        self.actors[name] = state
        return state

    def actor(self, name: str) -> ActorState | None:
        return self.actors.get(name)

    def _require(self, name: str) -> ActorState:
        state = self.actors.get(name)
        if state is None:
            raise KeyError(f"unknown actor '{name}'")
        return state

    # ------------------------------------------------------------- motion

    def set_speed(self, name: str, speed: float) -> None:
        self._require(name).speed = float(speed)

    def speed(self, name: str) -> float:
        return self._require(name).speed

    def position(self, name: str) -> tuple[float, float, float]:
        state = self._require(name)
        return (state.x, state.y, state.z)

    def assign_position(
        self,
        name: str,
        *,
        s: float | None = None,
        lane: int | None = None,
        speed: float | None = None,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        heading: float | None = None,
        reference: str | None = None,
        distance: float | None = None,
        lane_offset: int | None = None,
    ) -> None:
        state = self._require(name)
        reference_state = self._require(reference) if reference is not None else None
        if s is not None:
            state.s = float(s)
            state.x = float(s)
        elif reference_state is not None and (
            distance is not None or lane_offset is not None
        ):
            state.s = reference_state.s + (
                float(distance) if distance is not None else 0.0
            )
            state.x = state.s
        if lane is not None:
            state.lane = int(lane)
        if lane_offset is not None:
            base = reference_state.lane if reference_state is not None else state.lane
            state.lane = base + int(lane_offset)
        if speed is not None:
            state.speed = float(speed)
        if x is not None:
            state.x = float(x)
        if y is not None:
            state.y = float(y)
        if z is not None:
            state.z = float(z)
        if heading is not None:
            state.heading = float(heading)

    def change_lane(self, name: str, lanes: int, side: str) -> None:
        state = self._require(name)
        direction = 1 if side == "right" else -1
        state.lane += int(lanes) * direction
        self.lane_history.append((name, state.lane))

    def lane_change_complete(self, name: str) -> bool:
        self._require(name)
        return True

    def set_lights(self, name: str, mode: str) -> None:
        self._require(name).lights = mode
        self.light_history.append((name, mode))

    def set_celestial_position(self, azimuth: float, elevation: float) -> None:
        self.azimuth = float(azimuth)
        self.elevation = float(elevation)

    # ------------------------------------------------------------ queries

    def ahead_of(self, name: str, other: str) -> float:
        return self._require(name).s - self._require(other).s

    def euclidean(self, name: str, other: str) -> float:
        first = self._require(name)
        second = self._require(other)
        return math.dist(
            (first.x, first.y, first.z),
            (second.x, second.y, second.z),
        )

    # --------------------------------------------------------------- step

    def step(self, dt: float) -> None:
        self.time += float(dt)
        for state in self.actors.values():
            if state.type_name in ("vehicle", "pedestrian") and state.speed:
                state.s += state.speed * dt
                state.x = state.s
