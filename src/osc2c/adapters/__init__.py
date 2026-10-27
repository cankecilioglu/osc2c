"""Simulator boundary.

Everything above this package talks to `SimAdapter`; only `carla.py` may
import CARLA. The mock adapter is the default for tests and for the
simulator-free golden runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ActorState:
    name: str
    type_name: str
    s: float = 0.0
    lane: int = 1
    speed: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    heading: float = 0.0
    lights: str = "off"
    attributes: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class SimAdapter(Protocol):
    """Minimal simulation surface used by the OSC2 runtime."""

    def spawn(self, name: str, type_name: str) -> ActorState: ...

    def actor(self, name: str) -> ActorState | None: ...

    def set_speed(self, name: str, speed: float) -> None: ...

    def speed(self, name: str) -> float: ...

    def position(self, name: str) -> tuple[float, float, float]: ...

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
    ) -> None: ...

    def change_lane(self, name: str, lanes: int, side: str) -> None: ...

    def lane_change_complete(self, name: str) -> bool: ...

    def set_lights(self, name: str, mode: str) -> None: ...

    def set_celestial_position(self, azimuth: float, elevation: float) -> None: ...

    def ahead_of(self, name: str, other: str) -> float: ...

    def euclidean(self, name: str, other: str) -> float: ...

    def step(self, dt: float) -> None: ...
