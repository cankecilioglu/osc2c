"""Hand-written CARLA baseline for the cut-in manoeuvre.

This script deliberately imports only `carla` (plus the standard library): it
is the control group for the compiler-driven adapter. It spawns two vehicles,
drives them with a simple proportional speed controller and a pure-pursuit
steering target, performs the NPC lane change after 2 s, and brakes the hero
after 3.2 s. Timings and geometry can be compared with `tools/bench.py`.

Run with a CARLA server on port 2000:

    python tools/baseline_carla.py --repeat 5 --json baseline.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import carla

DT = 0.05
CRUISE = 12.0
LANE_CHANGE_AT = 2.0
BRAKE_AT = 3.2
END_AT = 5.0


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "median": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return {
        "count": len(values),
        "median": round(statistics.median(values), 3),
        "p95": round(ordered[index], 3),
        "max": round(max(values), 3),
    }


def _speed(vehicle: carla.Vehicle) -> float:
    velocity = vehicle.get_velocity()
    return math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)


def _left_lane_score(world_map: carla.Map, waypoint: carla.Waypoint) -> int:
    score = 0
    current = waypoint
    for distance in (0.0, 20.0, 40.0):
        if distance:
            candidates = current.next(distance)
            if not candidates:
                break
            current = candidates[0]
        left = current.get_left_lane()
        if (
            left is None
            or left.lane_type != carla.LaneType.Driving
            or left.road_id != current.road_id
        ):
            break
        score += 1
    return score


def _steer_to(
    vehicle: carla.Vehicle,
    target_waypoint: carla.Waypoint,
    lookahead: float,
) -> float:
    candidates = target_waypoint.next(lookahead)
    ahead = candidates[0] if candidates else target_waypoint
    transform = vehicle.get_transform()
    local = transform.inverse_transform(ahead.transform.location)
    return max(-0.8, min(0.8, math.atan2(local.y, local.x)))


def _control(
    world_map: carla.Map,
    vehicle: carla.Vehicle,
    target_speed: float,
    target_lane: carla.Waypoint | None = None,
) -> carla.VehicleControl:
    speed = _speed(vehicle)
    transform = vehicle.get_transform()
    waypoint = world_map.get_waypoint(transform.location)
    lane = target_lane if target_lane is not None else waypoint
    lookahead = max(4.0, min(11.0, speed))
    steer = _steer_to(vehicle, lane, lookahead)
    error = target_speed - speed
    throttle = max(0.0, min(1.0, error / max(target_speed, 1.0)))
    brake = 0.8 if error < -0.5 else 0.0
    return carla.VehicleControl(
        throttle=throttle,
        steer=steer,
        brake=brake,
        hand_brake=False,
        reverse=False,
        manual_gear_shift=False,
        gear=0,
    )


def _lateral(hero: carla.Vehicle, other: carla.Vehicle) -> float:
    transform = hero.get_transform()
    right = transform.get_right_vector()
    location = other.get_transform().location
    return (
        (location.x - transform.location.x) * right.x
        + (location.y - transform.location.y) * right.y
    )


def _heading_gap(hero: carla.Vehicle, other: carla.Vehicle) -> float:
    first = hero.get_transform().rotation.yaw
    second = other.get_transform().rotation.yaw
    return abs((second - first + 180.0) % 360.0 - 180.0)


def _ahead(hero: carla.Vehicle, other: carla.Vehicle) -> float:
    forward = hero.get_transform().get_forward_vector()
    delta = hero.get_transform().location - other.get_transform().location
    return delta.x * forward.x + delta.y * forward.y


def run_once(
    host: str,
    port: int,
    map_name: str,
    spawn_index: int,
    ticks: int,
) -> dict[str, Any]:
    client = carla.Client(host, port)
    client.set_timeout(30.0)
    current = client.get_world().get_map().name
    wanted = map_name if map_name.startswith("Carla/Maps/") else f"Carla/Maps/{map_name}"
    if current != wanted:
        client.load_world(map_name)
    world = client.get_world()
    world_map = world.get_map()
    settings = world.get_settings()
    weather = world.get_weather()
    sync = world.get_settings()
    sync.synchronous_mode = True
    sync.fixed_delta_seconds = DT
    world.apply_settings(sync)

    library = world.get_blueprint_library()
    hero_blueprint = library.find("vehicle.tesla.model3")
    npc_blueprint = library.find("vehicle.lincoln.mkz_2017")
    hero_blueprint.set_attribute("role_name", "baseline_hero")
    npc_blueprint.set_attribute("role_name", "baseline_npc")
    spawn_points = world_map.get_spawn_points()
    hero = None
    npc = None
    try:
        for index in range(spawn_index, min(len(spawn_points), spawn_index + 50)):
            waypoint = world_map.get_waypoint(spawn_points[index].location)
            if _left_lane_score(world_map, waypoint) < 2:
                continue
            hero = world.try_spawn_actor(hero_blueprint, spawn_points[index])
            if hero is not None:
                break
        if hero is None:
            raise RuntimeError("baseline found no spawn point with a left lane")
        world.tick()
        hero.set_autopilot(False)
        hero.apply_control(carla.VehicleControl(brake=1.0))

        hero_waypoint = world_map.get_waypoint(hero.get_transform().location)
        left = hero_waypoint.get_left_lane()
        if left is None:
            raise RuntimeError("baseline hero has no left lane after spawning")
        candidates = left.next(12.0)
        target = candidates[0] if candidates else left
        spawn = target.transform
        spawn.location.z += 0.2
        npc = world.try_spawn_actor(npc_blueprint, spawn)
        if npc is None:
            raise RuntimeError("baseline could not spawn the NPC")
        world.tick()
        npc.set_autopilot(False)
        npc.apply_control(carla.VehicleControl(brake=1.0))

        initial = {
            "lateral": round(_lateral(hero, npc), 3),
            "ahead": round(_ahead(hero, npc), 3),
        }
        start_lane_id = world_map.get_waypoint(npc.get_transform().location).lane_id
        tick_ms: list[float] = []
        loop_ms: list[float] = []
        change_started: float | None = None
        target_lane_id: int | None = None
        lane_changed_at: float | None = None
        geometry: dict[str, float] | None = None
        collision = False
        min_distance = math.inf
        min_ttc = math.inf

        for tick in range(ticks):
            now = tick * DT
            if now >= LANE_CHANGE_AT and change_started is None:
                change_started = now
                waypoint = world_map.get_waypoint(npc.get_transform().location)
                right = waypoint.get_right_lane()
                if (
                    right is not None
                    and right.lane_type == carla.LaneType.Driving
                    and right.lane_id != start_lane_id
                ):
                    target_lane_id = right.lane_id

            loop_started = time.perf_counter_ns()
            hero_target = CRUISE if now < BRAKE_AT else 0.0
            npc_target = CRUISE
            hero.apply_control(_control(world_map, hero, hero_target))

            npc_lane = None
            if change_started is not None and lane_changed_at is None:
                waypoint = world_map.get_waypoint(npc.get_transform().location)
                right = waypoint.get_right_lane()
                if right is not None and right.lane_type == carla.LaneType.Driving:
                    npc_lane = right
            npc.apply_control(
                _control(world_map, npc, npc_target, target_lane=npc_lane)
            )
            loop_before_tick = time.perf_counter_ns()
            world.tick()
            loop_after_tick = time.perf_counter_ns()
            tick_ms.append((loop_after_tick - loop_before_tick) / 1e6)
            loop_ms.append((loop_after_tick - loop_started) / 1e6)

            if lane_changed_at is None and target_lane_id is not None:
                waypoint = world_map.get_waypoint(npc.get_transform().location)
                if waypoint.lane_id == target_lane_id:
                    center = waypoint.transform.location
                    location = npc.get_transform().location
                    offset = math.hypot(
                        location.x - center.x, location.y - center.y
                    )
                    if offset < 0.7:
                        lane_changed_at = now + DT
                        geometry = {
                            "time": round(lane_changed_at, 3),
                            "lateral": round(_lateral(hero, npc), 3),
                            "heading_gap": round(_heading_gap(hero, npc), 3),
                            "ahead": round(_ahead(hero, npc), 3),
                        }
            distance = hero.get_transform().location.distance(
                npc.get_transform().location
            )
            min_distance = min(min_distance, distance)
            collision = collision or distance < 2.0
            ahead = _ahead(hero, npc)
            closing = _speed(hero) - _speed(npc)
            if ahead < 0.0 and closing > 1e-6:
                min_ttc = min(min_ttc, (-ahead) / closing)
            if now + DT >= END_AT:
                break

        return {
            "status": "SUCCESS" if geometry is not None and not collision else "FAILURE",
            "ticks": tick + 1,
            "sim_time": round((tick + 1) * DT, 3),
            "initial": initial,
            "geometry": geometry,
            "collision": collision,
            "min_distance": round(min_distance, 3)
            if math.isfinite(min_distance)
            else None,
            "min_ttc": round(min_ttc, 3) if math.isfinite(min_ttc) else None,
            "hero_speed": round(_speed(hero), 3),
            "npc_speed": round(_speed(npc), 3),
            "tick_latency_ms": _stats(tick_ms),
            "loop_latency_ms": _stats(loop_ms),
        }
    finally:
        for actor in (npc, hero):
            if actor is not None:
                try:
                    actor.destroy()
                except RuntimeError:
                    pass
        try:
            world.tick()
        except RuntimeError:
            pass
        try:
            world.apply_settings(settings)
            world.set_weather(weather)
        except RuntimeError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="baseline_carla", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--map", dest="map_name", default="Town10HD_Opt")
    parser.add_argument("--spawn-index", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--json", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runs = [
        run_once(args.host, args.port, args.map_name, args.spawn_index, args.ticks)
        for _ in range(args.repeat)
    ]
    successes = sum(run["status"] == "SUCCESS" for run in runs)
    geometries = [run["geometry"] for run in runs if run["geometry"] is not None]
    result = {
        "mode": "carla-baseline",
        "repeat": args.repeat,
        "successes": successes,
        "geometry_ok": successes,
        "collisions": sum(run["collision"] for run in runs),
        "min_distance": _stats(
            [run["min_distance"] for run in runs if run["min_distance"] is not None]
        ),
        "min_ttc": _stats(
            [run["min_ttc"] for run in runs if run["min_ttc"] is not None]
        ),
        "tick_latency_ms": _stats(
            [run["tick_latency_ms"]["median"] for run in runs]
        ),
        "loop_latency_ms": _stats(
            [run["loop_latency_ms"]["median"] for run in runs]
        ),
        "geometry": {
            "time": _stats([item["time"] for item in geometries]),
            "lateral_abs": _stats([abs(item["lateral"]) for item in geometries]),
            "heading_gap": _stats([item["heading_gap"] for item in geometries]),
            "ahead": _stats([item["ahead"] for item in geometries]),
        },
        "runs": runs,
    }
    text = json.dumps(result, indent=2)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    return 0 if successes == args.repeat else 1


if __name__ == "__main__":
    raise SystemExit(main())
