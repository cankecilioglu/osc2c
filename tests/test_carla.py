from __future__ import annotations

from pathlib import Path

import pytest
from py_trees import common

carla = pytest.importorskip("carla")

from osc2c.adapters.carla import CarlaAdapter
from osc2c.backend import compile_scenario
from osc2c.frontend.parser import parse_file
from osc2c.semantics import analyze

ROOT = Path(__file__).resolve().parents[1]
CUT_IN = ROOT / "scenarios" / "carla" / "cut_in.osc"

pytestmark = pytest.mark.carla


@pytest.fixture
def adapter():
    try:
        instance = CarlaAdapter(
            spawn_index=20, fixed_delta_seconds=0.05, timeout=30.0
        )
    except Exception as error:  # noqa: BLE001 - turn connection failures into skips
        pytest.skip(f"CARLA server unavailable: {error}")
    try:
        yield instance
    finally:
        instance.close()


def _lateral(adapter: CarlaAdapter, name: str, other: str) -> float:
    transform = adapter._vehicle(name).get_transform()
    right = transform.get_right_vector()
    location = adapter._vehicle(other).get_transform().location
    return (
        (location.x - transform.location.x) * right.x
        + (location.y - transform.location.y) * right.y
    )


def _heading_gap(adapter: CarlaAdapter, name: str, other: str) -> float:
    first = adapter._vehicle(name).get_transform().rotation.yaw
    second = adapter._vehicle(other).get_transform().rotation.yaw
    return abs((second - first + 180.0) % 360.0 - 180.0)


def test_adapter_spawns_and_moves(adapter: CarlaAdapter) -> None:
    state = adapter.spawn("hero", "vehicle")
    assert state.type_name == "vehicle"
    assert adapter.actor("hero") is not None

    adapter.set_speed("hero", 8.0)
    for _ in range(40):
        adapter.step(0.05)

    assert adapter.speed("hero") > 0.5
    x, y, z = adapter.position("hero")
    assert (x, y, z) != (0.0, 0.0, 0.0)


def test_cut_in_scenario_runs_on_carla(adapter: CarlaAdapter) -> None:
    model = analyze(parse_file(CUT_IN))
    compiled = compile_scenario(model, adapter=adapter)

    hero_start = adapter.actor("hero")
    npc_start = adapter.actor("npc")
    assert hero_start is not None and npc_start is not None
    assert adapter.ahead_of("hero", "npc") < 0.0
    initial_lateral = _lateral(adapter, "hero", "npc")
    assert initial_lateral < -2.0

    status = compiled.tick()
    ticks = 1
    cut_in: tuple[float, float, float] | None = None
    while status == common.Status.RUNNING and ticks < 300:
        compiled.context.step(0.05)
        status = compiled.tick()
        ticks += 1
        if cut_in is None and any(
            record.name == "CUT_IN" for record in compiled.context.blackboard.trace
        ):
            # Lane ids are road-local, so validate the manoeuvre geometrically
            # at the event instead of comparing ids after further junctions.
            cut_in = (
                _lateral(adapter, "hero", "npc"),
                _heading_gap(adapter, "hero", "npc"),
                adapter.ahead_of("hero", "npc"),
            )

    assert status == common.Status.SUCCESS, compiled.context.blackboard.trace
    assert cut_in is not None
    lateral, heading_gap, ahead = cut_in
    assert abs(lateral) < 2.2
    assert heading_gap < 30.0
    assert ahead < 0.0
    assert abs(lateral) < abs(initial_lateral) - 1.0

    hero = adapter.actor("hero")
    npc = adapter.actor("npc")
    assert hero.lights == "high_beam"
    assert npc.speed < 12.0


def test_close_destroys_actors_and_restores_settings() -> None:
    try:
        adapter = CarlaAdapter(
            spawn_index=20, fixed_delta_seconds=0.05, timeout=30.0
        )
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"CARLA server unavailable: {error}")
    original = adapter._settings
    world = adapter.world

    def hero_count() -> int:
        return sum(
            1
            for actor in world.get_actors().filter("vehicle.*")
            if actor.attributes.get("role_name") == "test_close_hero"
        )

    try:
        adapter.spawn("test_close_hero", "vehicle")
        assert hero_count() == 1
    finally:
        adapter.close()

    assert hero_count() == 0
    settings = world.get_settings()
    assert settings.synchronous_mode == original.synchronous_mode
    assert settings.fixed_delta_seconds == original.fixed_delta_seconds
