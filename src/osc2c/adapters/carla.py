"""CARLA 0.9.x adapter.

Only this module imports the `carla` package. The adapter owns a synchronous
world, keeps vehicles in their lane with a pure-pursuit steering target, and
restores the server settings/weather on close so repeated runs do not leak
state into the user's simulator session.

`assign_position` follows the mock's conventions:

* `reference` + `distance` places the actor `distance` metres ahead of the
  reference along its lane (negative = behind).
* `lane_offset` is signed: positive is right, negative is left.
* an absolute `lane` is mapped to `lane - 1` lanes right of the current lane,
  because the mock's default lane is 1 and CARLA lane ids are map-specific.
* `s` without a reference advances the actor along its current lane.
"""

from __future__ import annotations

import math
from typing import Any

from osc2c.adapters import ActorState


class CarlaAdapter:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2000,
        map_name: str | None = None,
        spawn_index: int = 0,
        fixed_delta_seconds: float = 0.05,
        timeout: float = 10.0,
    ) -> None:
        import carla

        self._carla = carla
        self.client = carla.Client(host, port)
        self.client.set_timeout(timeout)
        if map_name:
            wanted = map_name
            if not wanted.startswith("Carla/Maps/"):
                wanted = f"Carla/Maps/{wanted}"
            current = self.client.get_world().get_map().name
            if current != wanted:
                self.client.load_world(map_name)

        self.world = self.client.get_world()
        self.map = self.world.get_map()
        self._settings = self.world.get_settings()
        self._weather = self.world.get_weather()

        settings = self.world.get_settings()
        settings.synchronous_mode = True
        settings.fixed_delta_seconds = float(fixed_delta_seconds)
        self.world.apply_settings(settings)

        self.fixed_delta_seconds = float(fixed_delta_seconds)
        self.actors: dict[str, ActorState] = {}
        self.time = 0.0
        self.azimuth = 0.0
        self.elevation = 0.0
        self.light_history: list[tuple[str, str]] = []
        self.lane_history: list[tuple[str, int]] = []

        self._vehicles: dict[str, Any] = {}
        self._targets: dict[str, float] = {}
        self._lane_changes: dict[str, dict[str, Any]] = {}
        self._light_modes: dict[str, str] = {}
        self._spawn_index = max(0, int(spawn_index))
        self._used_spawns: set[int] = set()
        self._blueprint_id = self._choose_model()
        self._closed = False
        self._spawn_points = self.map.get_spawn_points()
        self._spawn_order = self._build_spawn_order()

    # ----------------------------------------------------------- lifecycle

    def _choose_model(self) -> str:
        library = self.world.get_blueprint_library()
        for candidate in ("vehicle.tesla.model3", "vehicle.lincoln.mkz_2017"):
            found = library.filter(candidate)
            if len(found):
                return candidate
        vehicles = library.filter("vehicle.*")
        if not len(vehicles):
            raise RuntimeError("CARLA blueprint library exposes no vehicles")
        return vehicles[0].id

    def _build_spawn_order(self) -> list[int]:
        """Prefers spawn points with a long same-direction left lane.

        Lane-change scenarios need parallel driving lanes, so points where the
        left lane survives for at least 60 m are tried first. The map order
        remains the fallback for single-lane maps.
        """
        ranked: list[tuple[int, int]] = []
        for index, transform in enumerate(self._spawn_points):
            waypoint = self.map.get_waypoint(transform.location)
            ranked.append((index, self._left_lane_horizon(waypoint)))
        ranked.sort(key=lambda item: (-item[1], item[0]))
        order = [index for index, _ in ranked]
        start = self._spawn_index
        return [i for i in order if i >= start] + [i for i in order if i < start]

    def _left_lane_horizon(self, waypoint: Any) -> int:
        score = 0
        for distance in (0.0, 20.0, 40.0, 60.0):
            if waypoint is None:
                break
            if distance:
                candidates = waypoint.next(distance)
                if not candidates:
                    break
                current = candidates[0]
            else:
                current = waypoint
            left = current.get_left_lane()
            if (
                left is None
                or left.lane_type != self._carla.LaneType.Driving
                or left.road_id != current.road_id
            ):
                break
            delta = abs(
                (left.transform.rotation.yaw - current.transform.rotation.yaw + 180.0)
                % 360.0
                - 180.0
            )
            if delta >= 30.0:
                break
            score += 1
        return score

    def spawn(self, name: str, type_name: str) -> ActorState:
        if type_name == "environment":
            state = ActorState(name=name, type_name=type_name)
            state.attributes["name"] = name
            self.actors[name] = state
            return state
        if type_name != "vehicle":
            raise NotImplementedError(
                f"CarlaAdapter cannot spawn '{type_name}' actors; only vehicles "
                "and environment are supported"
            )
        if not self._spawn_points:
            raise RuntimeError("CARLA map exposes no spawn points")

        library = self.world.get_blueprint_library()
        blueprint = library.find(self._blueprint_id)
        if blueprint.has_attribute("role_name"):
            blueprint.set_attribute("role_name", name)

        vehicle = None
        for index in self._spawn_order:
            if index in self._used_spawns:
                continue
            vehicle = self.world.try_spawn_actor(
                blueprint, self._spawn_points[index]
            )
            if vehicle is not None:
                self._used_spawns.add(index)
                break
        if vehicle is None:
            raise RuntimeError(f"could not spawn CARLA vehicle '{name}'")

        # In synchronous mode spawns and transforms are committed by a tick.
        self.world.tick()
        vehicle.set_autopilot(False)
        control = self._carla.VehicleControl(throttle=0.0, brake=1.0)
        vehicle.apply_control(control)
        self._vehicles[name] = vehicle
        self._targets[name] = 0.0
        self._light_modes[name] = "off"

        transform = vehicle.get_transform()
        waypoint = self.map.get_waypoint(transform.location)
        state = ActorState(
            name=name,
            type_name=type_name,
            s=waypoint.s if waypoint is not None else 0.0,
            lane=waypoint.lane_id if waypoint is not None else 1,
            x=transform.location.x,
            y=transform.location.y,
            z=transform.location.z,
            heading=math.radians(transform.rotation.yaw),
            attributes={"name": name, "model": self._blueprint_id},
        )
        self.actors[name] = state
        self._refresh(name)
        return state

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        destroyed = False
        for vehicle in self._vehicles.values():
            try:
                vehicle.destroy()
                destroyed = True
            except RuntimeError:
                pass
        self._vehicles.clear()
        self.actors.clear()
        try:
            if destroyed:
                # Destructions are committed by a tick in synchronous mode.
                self.world.tick()
            self.world.apply_settings(self._settings)
            self.world.set_weather(self._weather)
        except RuntimeError:
            pass

    def reset(self) -> None:
        self.close()

    def _vehicle(self, name: str) -> Any:
        vehicle = self._vehicles.get(name)
        if vehicle is None:
            raise KeyError(f"actor '{name}' is not a CARLA vehicle")
        return vehicle

    def _refresh(self, name: str) -> ActorState:
        state = self.actors[name]
        vehicle = self._vehicles.get(name)
        if vehicle is None:
            return state
        transform = vehicle.get_transform()
        velocity = vehicle.get_velocity()
        waypoint = self.map.get_waypoint(transform.location)
        state.x = transform.location.x
        state.y = transform.location.y
        state.z = transform.location.z
        state.heading = math.radians(transform.rotation.yaw)
        state.speed = math.sqrt(
            velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z
        )
        if waypoint is not None:
            state.s = waypoint.s
            state.lane = waypoint.lane_id
        state.lights = self._light_modes.get(name, "off")
        return state

    # ------------------------------------------------------------- motion

    def set_speed(self, name: str, speed: float) -> None:
        self._vehicle(name)
        self._targets[name] = max(0.0, float(speed))

    def speed(self, name: str) -> float:
        return self._refresh(name).speed

    def position(self, name: str) -> tuple[float, float, float]:
        self._refresh(name)
        state = self.actors[name]
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
        vehicle = self._vehicle(name)
        transform = vehicle.get_transform()
        rotation = transform.rotation

        if x is not None or y is not None or z is not None:
            location = self._carla.Location(
                x=transform.location.x if x is None else float(x),
                y=transform.location.y if y is None else float(y),
                z=transform.location.z if z is None else float(z),
            )
        else:
            waypoint = self._base_waypoint(
                name, reference=reference, distance=distance, s=s
            )
            if lane_offset is not None:
                waypoint = self._shift(waypoint, int(lane_offset))
            elif lane is not None:
                waypoint = self._shift(waypoint, int(lane) - 1)
            location = self._carla.Location(
                x=waypoint.transform.location.x,
                y=waypoint.transform.location.y,
                z=waypoint.transform.location.z + 0.3,
            )
            rotation = waypoint.transform.rotation

        if heading is not None:
            rotation = self._carla.Rotation(
                pitch=rotation.pitch,
                yaw=math.degrees(float(heading)),
                roll=rotation.roll,
            )

        vehicle.set_transform(self._carla.Transform(location, rotation))
        vehicle.set_target_velocity(self._carla.Vector3D(0.0, 0.0, 0.0))
        vehicle.set_target_angular_velocity(self._carla.Vector3D(0.0, 0.0, 0.0))
        vehicle.apply_control(self._carla.VehicleControl(throttle=0.0, brake=1.0))
        if speed is not None:
            self._targets[name] = max(0.0, float(speed))
        self.world.tick()
        self._refresh(name)

    def _base_waypoint(
        self,
        name: str,
        *,
        reference: str | None,
        distance: float | None,
        s: float | None,
    ) -> Any:
        if reference is not None:
            reference_vehicle = self._vehicle(reference)
            base = self.map.get_waypoint(reference_vehicle.get_transform().location)
            if distance is not None:
                base = self._advance(base, float(distance))
            return base
        base = self.map.get_waypoint(self._vehicle(name).get_transform().location)
        if s is not None:
            base = self._advance(base, float(s))
        return base

    def _advance(self, waypoint: Any, distance: float) -> Any:
        if abs(distance) < 1e-6:
            return waypoint
        if distance > 0:
            candidates = waypoint.next(float(distance))
        else:
            candidates = waypoint.previous(float(-distance))
        return candidates[0] if candidates else waypoint

    def _shift(self, waypoint: Any, offset: int) -> Any:
        offset = int(offset)
        if offset == 0:
            return waypoint
        current = waypoint
        for _ in range(abs(offset)):
            neighbour = (
                current.get_right_lane() if offset > 0 else current.get_left_lane()
            )
            if (
                neighbour is None
                or neighbour.road_id != current.road_id
                or neighbour.lane_type != self._carla.LaneType.Driving
            ):
                break
            current = neighbour
        return current

    def change_lane(self, name: str, lanes: int, side: str) -> None:
        self._vehicle(name)
        if name in self._lane_changes:
            return
        waypoint = self.map.get_waypoint(
            self._vehicle(name).get_transform().location
        )
        direction = 1 if side == "right" else -1
        lanes = max(1, int(lanes))
        target = self._shift(waypoint, direction * lanes)
        entry: dict[str, Any] = {
            "started": self.time,
            "lanes": lanes,
            "direction": direction,
            "target_road": target.road_id,
            "target_lane": target.lane_id,
            "start_lane": waypoint.lane_id,
        }
        if target.lane_id == waypoint.lane_id and target.road_id == waypoint.road_id:
            entry["done"] = True
        self._lane_changes[name] = entry
        self.lane_history.append((name, target.lane_id))

    def lane_change_complete(self, name: str) -> bool:
        change = self._lane_changes.get(name)
        if change is None:
            return True
        if change.get("done"):
            self._lane_changes.pop(name, None)
            return True
        self._refresh(name)
        waypoint = self.map.get_waypoint(
            self._vehicle(name).get_transform().location
        )
        elapsed = self.time - change["started"]
        if elapsed >= 6.0:
            self._lane_changes.pop(name, None)
            return True
        # Road ids change at junctions even when the lane itself continues,
        # so completion is based on the lane index alone. The lane id flips as
        # soon as the centre crosses the marking, though; wait until the car
        # has actually settled in the target lane.
        if (
            elapsed >= 0.4
            and waypoint is not None
            and waypoint.lane_id == change["target_lane"]
        ):
            location = self._vehicle(name).get_transform().location
            lane_center = waypoint.transform.location
            offset = math.hypot(
                location.x - lane_center.x, location.y - lane_center.y
            )
            if offset < 0.7:
                self._lane_changes.pop(name, None)
                return True
        return False

    def set_lights(self, name: str, mode: str) -> None:
        vehicle = self._vehicle(name)
        states = self._carla.VehicleLightState
        flags = {
            "off": states.NONE,
            "auto": states.LowBeam,
            "low_beam": states.LowBeam,
            "high_beam": states.HighBeam,
            "position": states.Position,
            "fog": states.Fog,
            "brake": states.Brake,
        }.get(str(mode), states.NONE)
        vehicle.set_light_state(states(flags))
        self._light_modes[name] = str(mode)
        self.light_history.append((name, str(mode)))

    def set_celestial_position(self, azimuth: float, elevation: float) -> None:
        self.azimuth = float(azimuth)
        self.elevation = float(elevation)
        weather = self.world.get_weather()
        weather.sun_azimuth_angle = math.degrees(float(azimuth))
        weather.sun_altitude_angle = math.degrees(float(elevation))
        self.world.set_weather(weather)

    # ------------------------------------------------------------ queries

    def actor(self, name: str) -> ActorState | None:
        if name not in self.actors:
            return None
        return self._refresh(name)

    def ahead_of(self, name: str, other: str) -> float:
        # `waypoint.s` is not monotonic with the driving direction on every
        # CARLA road, so project the separation onto the actor's heading.
        first = self._vehicle(name).get_transform()
        second = self._vehicle(other).get_transform()
        forward = first.get_forward_vector()
        dx = first.location.x - second.location.x
        dy = first.location.y - second.location.y
        return dx * forward.x + dy * forward.y

    def euclidean(self, name: str, other: str) -> float:
        first = self._vehicle(name).get_transform().location
        second = self._vehicle(other).get_transform().location
        return first.distance(second)

    # --------------------------------------------------------------- step

    def step(self, dt: float) -> None:
        if self._closed:
            return
        for name, vehicle in list(self._vehicles.items()):
            self._drive(name, vehicle)
        self.world.tick()
        self.time += float(dt) if dt else self.fixed_delta_seconds
        for name in list(self._vehicles):
            self._refresh(name)

    def _drive(self, name: str, vehicle: Any) -> None:
        transform = vehicle.get_transform()
        velocity = vehicle.get_velocity()
        speed = math.sqrt(
            velocity.x * velocity.x + velocity.y * velocity.y + velocity.z * velocity.z
        )
        target = self._targets.get(name, 0.0)
        error = target - speed
        if target <= 0.05:
            throttle, brake = 0.0, 1.0
        elif error > 0.0:
            throttle, brake = min(0.85, 0.03 * target + 0.15 * error), 0.0
        elif error > -0.7:
            throttle, brake = max(0.0, 0.03 * target), 0.0
        else:
            throttle, brake = 0.0, min(0.8, -0.15 * error)

        # A fresh control object is required: in 0.9.16 `get_control()`
        # exposes uninitialised fields (reverse/gear) before the first tick.
        control = self._carla.VehicleControl(
            throttle=throttle,
            steer=self._steer(name, transform, speed),
            brake=brake,
            hand_brake=False,
            reverse=False,
            manual_gear_shift=False,
            gear=0,
        )
        vehicle.apply_control(control)

    def _steer(self, name: str, transform: Any, speed: float) -> float:
        waypoint = self.map.get_waypoint(transform.location)
        change = self._lane_changes.get(name)
        if change is not None and not change.get("done"):
            # Aim at the target lane a short distance ahead. Using the long
            # lane-keeping lookahead here makes the shift too gentle and the
            # adjoining lane can disappear across a junction.
            target_lane = self._shift(
                waypoint, change["direction"] * change["lanes"]
            )
            lookahead = max(4.0, min(8.0, speed * 0.6))
            candidates = target_lane.next(lookahead)
            ahead = candidates[0] if candidates else target_lane
        else:
            lookahead = max(5.0, min(11.0, speed))
            candidates = waypoint.next(lookahead)
            ahead = candidates[0] if candidates else waypoint
        local = transform.inverse_transform(ahead.transform.location)
        steer = math.atan2(local.y, local.x)
        return max(-0.8, min(0.8, steer))
