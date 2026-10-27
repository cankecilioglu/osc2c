"""Validation and measurement harness.

The harness is deliberately separate from the compiler: it drives the same
public entry points as the CLI, records wall-clock timings, and hashes
tick-by-tick actor state so repeated runs can be compared. CARLA is imported
lazily, only when a CARLA measurement is requested.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from osc2c.adapters import SimAdapter
from osc2c.adapters.mock import MockAdapter
from osc2c.backend import compile_scenario
from osc2c.frontend.parser import parse_file
from osc2c.semantics import analyze

ROOT = Path(__file__).resolve().parents[2]
DEV = ROOT / "scenarios" / "dev"
CARLA = ROOT / "scenarios" / "carla"


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    path: Path
    scenario: str | None
    expected_events: tuple[str, ...]
    description: str


SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        "S1_cut_in",
        CARLA / "cut_in.osc",
        None,
        ("CUT_IN",),
        "hero cruise + NPC lane change + hero brake",
    ),
    ScenarioSpec(
        "S2_lane_change_speed",
        DEV / "lane_change_speed.osc",
        None,
        ("LANE_CHANGED", "DONE"),
        "lane change and target-speed change",
    ),
    ScenarioSpec(
        "S3_event_handshake",
        DEV / "event_handshake.osc",
        None,
        ("PING", "PONG", "DONE"),
        "event handshake between two parallel branches",
    ),
    ScenarioSpec(
        "S4_placement_modes",
        DEV / "placement_modes.osc",
        None,
        ("PLACED",),
        "absolute, relative-ahead and relative-behind placement",
    ),
    ScenarioSpec(
        "S5_environment_lights",
        DEV / "environment_lights.osc",
        None,
        ("NIGHT_MODE",),
        "celestial position, lights and speed change",
    ),
)

CARLA_CUT_IN = SCENARIOS[0]


def _ms(nanoseconds: int) -> float:
    return nanoseconds / 1_000_000.0


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def latency_stats(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 4) if values else 0.0,
        "min": round(min(values), 4) if values else 0.0,
        "median": round(percentile(values, 0.5), 4),
        "p95": round(percentile(values, 0.95), 4),
        "max": round(max(values), 4) if values else 0.0,
    }


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sample(adapter: SimAdapter) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for name, state in sorted(adapter.actors.items()):
        x, y, z = adapter.position(name)
        result[name] = [
            round(state.s, 6),
            int(state.lane),
            round(state.speed, 6),
            state.lights,
            round(x, 6),
            round(y, 6),
            round(z, 6),
        ]
    return result


def _count_tree(node: dict[str, Any]) -> int:
    return 1 + sum(_count_tree(child) for child in node.get("children", []))


def measure_compile(
    path: Path,
    scenario: str | None = None,
    repeat: int = 10,
) -> dict[str, Any]:
    parse_ms: list[float] = []
    analyze_ms: list[float] = []
    compile_ms: list[float] = []
    total_ms: list[float] = []
    nodes = 0
    tree_nodes = 0
    for _ in range(repeat):
        started = time.perf_counter_ns()
        unit = parse_file(path)
        parsed = time.perf_counter_ns()
        model = analyze(unit)
        analyzed = time.perf_counter_ns()
        compiled = compile_scenario(
            model, adapter=MockAdapter(), scenario_name=scenario
        )
        compiled_at = time.perf_counter_ns()
        parse_ms.append(_ms(parsed - started))
        analyze_ms.append(_ms(analyzed - parsed))
        compile_ms.append(_ms(compiled_at - analyzed))
        total_ms.append(_ms(compiled_at - started))
        nodes = sum(1 for _ in unit.walk())
        tree_nodes = _count_tree(compiled.to_dict())
    return {
        "repeat": repeat,
        "parse": latency_stats(parse_ms),
        "analyze": latency_stats(analyze_ms),
        "compile": latency_stats(compile_ms),
        "total": latency_stats(total_ms),
        "ast_nodes": nodes,
        "bt_nodes": tree_nodes,
    }


def run_mock(
    spec: ScenarioSpec,
    *,
    dt: float = 0.1,
    max_ticks: int = 500,
) -> dict[str, Any]:
    from py_trees import common

    adapter = MockAdapter()
    unit = parse_file(spec.path)
    model = analyze(unit)
    compiled = compile_scenario(
        model, adapter=adapter, scenario_name=spec.scenario
    )
    samples = [_sample(adapter)]
    tick_ms: list[float] = []
    status = compiled.tick()
    ticks = 1
    while status == common.Status.RUNNING and ticks < max_ticks:
        started = time.perf_counter_ns()
        compiled.context.step(dt)
        status = compiled.tick()
        tick_ms.append(_ms(time.perf_counter_ns() - started))
        samples.append(_sample(adapter))
        ticks += 1
    events = [record.name for record in compiled.context.blackboard.trace]
    event_times = [
        {"name": record.name, "time": round(record.time, 6)}
        for record in compiled.context.blackboard.trace
    ]
    payload = {
        "ticks": ticks,
        "time": round(compiled.context.time, 6),
        "status": status.name,
        "events": events,
        "samples": samples,
    }
    return {
        "status": status.name,
        "ticks": ticks,
        "sim_time": round(compiled.context.time, 6),
        "events": events,
        "event_times": event_times,
        "unsupported": list(compiled.context.blackboard.values.get("unsupported", [])),
        "trace_hash": _hash(payload),
        "tick_latency": latency_stats(tick_ms),
        "final_actors": samples[-1],
    }


def run_mock_suite(
    *,
    repeat: int = 20,
    compile_repeat: int = 10,
    dt: float = 0.1,
    max_ticks: int = 500,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for spec in SCENARIOS:
        runs = [
            run_mock(spec, dt=dt, max_ticks=max_ticks) for _ in range(repeat)
        ]
        hashes = {run["trace_hash"] for run in runs}
        signatures = {
            (run["status"], tuple(run["events"]), run["ticks"]) for run in runs
        }
        first = runs[0]
        results.append(
            {
                "id": spec.id,
                "path": str(spec.path.relative_to(ROOT)),
                "description": spec.description,
                "status": first["status"],
                "ticks": first["ticks"],
                "sim_time": first["sim_time"],
                "events": first["events"],
                "expected_events": list(spec.expected_events),
                "events_match": tuple(first["events"]) == spec.expected_events,
                "unsupported": first["unsupported"],
                "final_actors": first["final_actors"],
                "repeat": repeat,
                "unique_hashes": len(hashes),
                "deterministic": len(hashes) == 1 and len(signatures) == 1,
                "trace_hash": first["trace_hash"],
                "tick_latency": first["tick_latency"],
                "compile": measure_compile(
                    spec.path, spec.scenario, repeat=compile_repeat
                ),
            }
        )
    return {
        "mode": "mock",
        "repeat": repeat,
        "compile_repeat": compile_repeat,
        "scenarios": results,
    }


# --------------------------------------------------------------------- CARLA


def _carla_lateral(adapter: Any, name: str, other: str) -> float:
    transform = adapter._vehicle(name).get_transform()
    right = transform.get_right_vector()
    location = adapter._vehicle(other).get_transform().location
    return (
        (location.x - transform.location.x) * right.x
        + (location.y - transform.location.y) * right.y
    )


def _carla_heading_gap(adapter: Any, name: str, other: str) -> float:
    first = adapter._vehicle(name).get_transform().rotation.yaw
    second = adapter._vehicle(other).get_transform().rotation.yaw
    return abs((second - first + 180.0) % 360.0 - 180.0)


def _carla_sample(adapter: Any, names: list[str]) -> dict[str, list[float]]:
    sample: dict[str, list[float]] = {}
    for name in sorted(names):
        transform = adapter._vehicle(name).get_transform()
        state = adapter.actors[name]
        sample[name] = [
            round(transform.location.x, 6),
            round(transform.location.y, 6),
            round(transform.location.z, 6),
            round(transform.rotation.yaw, 6),
            round(state.speed, 6),
            float(state.lane),
        ]
    return sample


def run_carla_cut_in_once(
    *,
    host: str = "127.0.0.1",
    port: int = 2000,
    map_name: str | None = "Town10HD_Opt",
    spawn_index: int = 20,
    dt: float = 0.05,
    max_ticks: int = 400,
) -> dict[str, Any]:
    from py_trees import common

    from osc2c.adapters.carla import CarlaAdapter

    adapter = CarlaAdapter(
        host=host,
        port=port,
        map_name=map_name,
        spawn_index=spawn_index,
        fixed_delta_seconds=dt,
        timeout=30.0,
    )
    try:
        started = time.perf_counter_ns()
        unit = parse_file(CARLA_CUT_IN.path)
        parsed = time.perf_counter_ns()
        model = analyze(unit)
        analyzed = time.perf_counter_ns()
        compiled = compile_scenario(model, adapter=adapter)
        compiled_at = time.perf_counter_ns()

        initial = {
            "lateral": round(_carla_lateral(adapter, "hero", "npc"), 6),
            "ahead": round(adapter.ahead_of("hero", "npc"), 6),
        }
        names = ["hero", "npc"]
        samples = [_carla_sample(adapter, names)]
        tick_ms: list[float] = []
        status = compiled.tick()
        ticks = 1
        cut_in: dict[str, float] | None = None
        min_distance = math.inf
        min_ttc = math.inf
        collision = False
        while status == common.Status.RUNNING and ticks < max_ticks:
            started_tick = time.perf_counter_ns()
            compiled.context.step(dt)
            status = compiled.tick()
            tick_ms.append(_ms(time.perf_counter_ns() - started_tick))
            sample = _carla_sample(adapter, names)
            samples.append(sample)
            ticks += 1

            hero_sample = sample["hero"]
            npc_sample = sample["npc"]
            distance = math.dist(hero_sample[:3], npc_sample[:3])
            min_distance = min(min_distance, distance)
            collision = collision or distance < 2.0
            ahead = adapter.ahead_of("hero", "npc")
            closing = hero_sample[4] - npc_sample[4]
            if ahead < 0.0 and closing > 1e-6:
                min_ttc = min(min_ttc, (-ahead) / closing)

            if cut_in is None and any(
                record.name == "CUT_IN"
                for record in compiled.context.blackboard.trace
            ):
                cut_in = {
                    "time": round(compiled.context.time, 6),
                    "lateral": round(_carla_lateral(adapter, "hero", "npc"), 6),
                    "heading_gap": round(
                        _carla_heading_gap(adapter, "hero", "npc"), 6
                    ),
                    "ahead": round(adapter.ahead_of("hero", "npc"), 6),
                }
        events = [record.name for record in compiled.context.blackboard.trace]
        payload = {
            "ticks": ticks,
            "time": round(compiled.context.time, 6),
            "status": status.name,
            "events": events,
            "samples": samples,
        }
        hero = adapter.actors["hero"]
        npc = adapter.actors["npc"]
        result = {
            "status": status.name,
            "ticks": ticks,
            "sim_time": round(compiled.context.time, 6),
            "events": events,
            "initial": initial,
            "cut_in": cut_in,
            "trace_hash": _hash(payload),
            "tick_latency": latency_stats(tick_ms),
            "compile": {
                "parse_ms": round(_ms(parsed - started), 4),
                "analyze_ms": round(_ms(analyzed - parsed), 4),
                "compile_ms": round(_ms(compiled_at - analyzed), 4),
                "total_ms": round(_ms(compiled_at - started), 4),
            },
            "final": {
                "hero_speed": round(hero.speed, 6),
                "hero_lights": hero.lights,
                "npc_speed": round(npc.speed, 6),
            },
            "min_distance": round(min_distance, 6)
            if math.isfinite(min_distance)
            else None,
            "min_ttc": round(min_ttc, 6) if math.isfinite(min_ttc) else None,
            "collision": collision,
        }
        if cut_in is not None:
            result["geometry_ok"] = bool(
                abs(cut_in["lateral"]) < 2.2
                and cut_in["heading_gap"] < 30.0
                and cut_in["ahead"] < 0.0
                and abs(cut_in["lateral"]) < abs(initial["lateral"]) - 1.0
            )
        else:
            result["geometry_ok"] = False
        return result
    finally:
        adapter.close()


def run_carla_suite(
    *,
    repeat: int = 20,
    host: str = "127.0.0.1",
    port: int = 2000,
    map_name: str | None = "Town10HD_Opt",
    spawn_index: int = 20,
    dt: float = 0.05,
    max_ticks: int = 400,
) -> dict[str, Any]:
    runs = [
        run_carla_cut_in_once(
            host=host,
            port=port,
            map_name=map_name,
            spawn_index=spawn_index,
            dt=dt,
            max_ticks=max_ticks,
        )
        for _ in range(repeat)
    ]
    hashes = {run["trace_hash"] for run in runs}
    cut_ins = [run["cut_in"] for run in runs if run["cut_in"] is not None]
    tick_values: list[float] = []
    for run in runs:
        tick_values.append(run["tick_latency"]["median"])
    compile_values = [run["compile"]["compile_ms"] for run in runs]
    return {
        "mode": "carla",
        "repeat": repeat,
        "scenario": str(CARLA_CUT_IN.path.relative_to(ROOT)),
        "successes": sum(run["status"] == "SUCCESS" for run in runs),
        "cut_in_detected": len(cut_ins),
        "geometry_ok": sum(run["geometry_ok"] for run in runs),
        "unique_hashes": len(hashes),
        "deterministic": len(hashes) == 1,
        "trace_hash": runs[0]["trace_hash"],
        "cut_in_time": latency_stats([item["time"] for item in cut_ins]),
        "lateral_abs": latency_stats(
            [abs(item["lateral"]) for item in cut_ins]
        ),
        "heading_gap": latency_stats(
            [item["heading_gap"] for item in cut_ins]
        ),
        "ahead": latency_stats([item["ahead"] for item in cut_ins]),
        "initial_lateral": latency_stats(
            [run["initial"]["lateral"] for run in runs]
        ),
        "min_distance": latency_stats(
            [run["min_distance"] for run in runs if run["min_distance"] is not None]
        ),
        "min_ttc": latency_stats(
            [run["min_ttc"] for run in runs if run["min_ttc"] is not None]
        ),
        "collisions": sum(run["collision"] for run in runs),
        "ticks": latency_stats([float(run["ticks"]) for run in runs]),
        "tick_latency_median_ms": latency_stats(tick_values),
        "compile_latency_ms": latency_stats(compile_values),
        "runs": runs,
    }


def render_summary(result: dict[str, Any]) -> str:
    lines: list[str] = []
    mock = result.get("mock")
    if mock:
        lines.append("## Mock suite")
        lines.append("")
        lines.append(
            "| ID | Status | Events | Ticks | Deterministic | "
            "Compile median (ms) | Tick p95 (ms) |"
        )
        lines.append("| --- | --- | --- | ---: | --- | ---: | ---: |")
        for item in mock["scenarios"]:
            lines.append(
                "| {id} | {status} | {events} | {ticks} | {det} | "
                "{compile:.2f} | {tick:.3f} |".format(
                    id=item["id"],
                    status=item["status"],
                    events=", ".join(item["events"]),
                    ticks=item["ticks"],
                    det="yes" if item["deterministic"] else "NO",
                    compile=item["compile"]["total"]["median"],
                    tick=item["tick_latency"]["p95"],
                )
            )
        lines.append("")
    carla = result.get("carla")
    if carla:
        lines.append("## CARLA cut-in")
        lines.append("")
        lines.append(f"- Runs: {carla['repeat']}")
        lines.append(
            f"- Success: {carla['successes']}/{carla['repeat']}, "
            f"CUT_IN detected: {carla['cut_in_detected']}/{carla['repeat']}, "
            f"geometry ok: {carla['geometry_ok']}/{carla['repeat']}"
        )
        lines.append(
            f"- Unique trace hashes: {carla['unique_hashes']} "
            f"({'deterministic' if carla['deterministic'] else 'not deterministic'})"
        )
        lines.append(
            f"- CUT_IN time: median {carla['cut_in_time']['median']:.2f} s "
            f"(p95 {carla['cut_in_time']['p95']:.2f} s)"
        )
        lines.append(
            f"- |lateral| at event: median "
            f"{carla['lateral_abs']['median']:.3f} m, "
            f"max {carla['lateral_abs']['max']:.3f} m"
        )
        lines.append(
            f"- Min distance: {carla['min_distance']['median']:.2f} m; "
            f"min TTC: {carla['min_ttc']['median']:.2f} s; "
            f"collisions: {carla['collisions']}"
        )
        lines.append(
            f"- Tick latency: median {carla['tick_latency_median_ms']['median']:.2f} ms, "
            f"p95 {carla['tick_latency_median_ms']['p95']:.2f} ms"
        )
        lines.append(
            f"- Compile latency: median {carla['compile_latency_ms']['median']:.2f} ms"
        )
        lines.append("")
    return "\n".join(lines)

