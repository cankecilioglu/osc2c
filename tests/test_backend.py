from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from py_trees import common

from osc2c.adapters.mock import MockAdapter
from osc2c.backend import CompilationError, compile_scenario
from osc2c.backend.behaviors import snapshot
from osc2c.frontend.parser import parse, parse_file
from osc2c.semantics import analyze

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "scenarios" / "dev"
GOLDEN = ROOT / "tests" / "golden" / "bt"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def compile_file(name: str, *, adapter=None, scenario: str | None = None):
    unit = parse_file(SCENARIOS / name)
    model = analyze(unit)
    assert not model.diagnostics.has_errors, [item.format() for item in model.diagnostics]
    return compile_scenario(model, adapter=adapter, scenario_name=scenario)


def compile_source(source: str, *, adapter=None):
    unit = parse(source, source="<test>.osc")
    model = analyze(unit)
    assert not model.diagnostics.has_errors, [item.format() for item in model.diagnostics]
    return compile_scenario(model, adapter=adapter)


# --------------------------------------------------------------- compilation


def test_serial_parallel_and_one_of_mapping() -> None:
    compiled = compile_file("stage3_parallel.osc")
    assert compiled.root.name == "serial"
    parallel = compiled.root.children[0]
    assert parallel.name == "parallel"
    assert isinstance(parallel.policy, common.ParallelPolicy.SuccessOnAll)

    sync = compile_file("stage3_sync.osc")
    one_of = sync.root.children[2]
    assert one_of.name == "one_of"
    assert isinstance(one_of.policy, common.ParallelPolicy.SuccessOnOne)


def test_compound_unit_literals_evaluate_to_si() -> None:
    compiled = compile_source(
        "scenario compound:\n"
        "    var direct : speed = 1 m/s\n"
        "    var road : speed = 1 km/h\n"
        "    var brake : acceleration = 1 m/s^2\n"
        "    do serial:\n"
        "        wait elapsed(100 ms)\n"
    )
    assert compiled.context.fields["direct"] == pytest.approx(1.0)
    assert compiled.context.fields["road"] == pytest.approx(1000 / 3600)
    assert compiled.context.fields["brake"] == pytest.approx(1.0)


def test_tree_snapshot_is_deterministic() -> None:
    first = compile_file("stage3_sync.osc").to_dict()
    second = compile_file("stage3_sync.osc").to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.parametrize(
    "stem", ["stage3_sync", "stage3_parallel", "stage3_fall", "smoke4", "action_calls"]
)
def test_bt_matches_golden(stem: str) -> None:
    dump = json.dumps(compile_file(f"{stem}.osc").to_dict(), indent=2) + "\n"
    golden = GOLDEN / f"{stem}.json"
    if UPDATE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(dump, encoding="utf-8", newline="\n")
    assert golden.is_file(), f"missing golden file: {golden} (run UPDATE_GOLDEN=1 pytest)"
    assert dump == golden.read_text(encoding="utf-8")


def test_unsupported_behaviour_is_reported_not_ignored() -> None:
    compiled = compile_file("stage3_unsupported.osc")
    assert compiled.warnings
    result = compiled.run(max_ticks=5)
    assert result.status == common.Status.FAILURE
    assert "unsupported behaviour 'fly' on 'hero'" in result.unsupported


def test_semantic_errors_block_compilation() -> None:
    unit = parse(
        "scenario broken:\n    hero : vehicle\n    do serial:\n        hero.fly()\n",
        source="broken.osc",
    )
    model = analyze(unit)
    model.diagnostics.error("E0999", "forced", unit.declarations[0].span)
    with pytest.raises(CompilationError):
        compile_scenario(model)


# -------------------------------------------------------------------- runtime


def test_sync_scenario_completes_and_emits_event() -> None:
    adapter = MockAdapter()
    compiled = compile_file("stage3_sync.osc", adapter=adapter)
    result = compiled.run(max_ticks=200, dt=0.1)

    assert result.status == common.Status.SUCCESS
    assert [record.name for record in result.trace] == ["SYNCHRONIZED"]
    assert result.ticks == 22
    assert result.time == pytest.approx(2.1)
    assert adapter.actors["hero"].speed == pytest.approx(10.0)
    assert adapter.actors["hero"].lights == "high_beam"
    assert adapter.actors["npc"].speed == pytest.approx(0.0)
    assert adapter.actors["npc"].s == pytest.approx(20.0)


def test_relative_placement_runs_before_behaviour() -> None:
    adapter = MockAdapter()
    compiled = compile_file("stage3_sync.osc", adapter=adapter)
    compiled.tick()
    assert adapter.actors["hero"].s == pytest.approx(0.0)
    assert adapter.actors["npc"].s == pytest.approx(20.0)
    assert adapter.actors["npc"].lane == 1


def test_parallel_waits_for_slowest_branch() -> None:
    compiled = compile_file("stage3_parallel.osc")
    result = compiled.run(max_ticks=100, dt=0.1)
    assert result.status == common.Status.SUCCESS
    assert result.time == pytest.approx(0.5)
    assert [record.name for record in result.trace] == ["TICK", "DONE"]
    assert result.trace[0].time == pytest.approx(0.2)


def test_fall_edge_fires_after_speed_drops() -> None:
    compiled = compile_file("stage3_fall.osc")
    result = compiled.run(max_ticks=100, dt=0.1)
    assert result.status == common.Status.SUCCESS
    assert [record.name for record in result.trace] == ["STOPPED"]
    assert result.time == pytest.approx(0.2)


def test_rise_does_not_fire_on_an_already_true_condition() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "scenario edge:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        wait rise(hero.speed > 0 mps)\n",
        adapter=adapter,
    )
    adapter.set_speed("hero", 5.0)
    compiled.advance(0.1)
    assert compiled.tick() == common.Status.RUNNING
    adapter.set_speed("hero", 0.0)
    compiled.advance(0.1)
    assert compiled.tick() == common.Status.RUNNING
    adapter.set_speed("hero", 5.0)
    compiled.advance(0.1)
    assert compiled.tick() == common.Status.SUCCESS


def test_latched_event_satisfies_later_wait() -> None:
    compiled = compile_source(
        "scenario events:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        emit GO\n"
        "        wait @GO\n"
        "        emit DONE\n",
    )
    result = compiled.run(max_ticks=10)
    assert result.status == common.Status.SUCCESS
    assert [record.name for record in result.trace] == ["GO", "DONE"]


def test_variables_are_evaluated_in_si_units() -> None:
    compiled = compile_file("smoke4.osc")
    assert compiled.context.fields["v_hero"] == pytest.approx(9.722222, rel=1e-6)
    assert compiled.context.fields["v_npc_fast"] == pytest.approx(15.274, rel=1e-3)
    assert compiled.context.fields["safety_gap"] == pytest.approx(15.0)


def test_keep_constraints_bind_actor_attributes() -> None:
    compiled = compile_file("smoke.osc")
    hero = compiled.adapter.actors["hero"]
    assert hero.attributes["name"] == "hero"
    assert hero.attributes["model"] == "vehicle.tesla.model3"


def test_unsupported_keep_shape_is_reported() -> None:
    compiled = compile_source(
        "scenario constrained:\n"
        "    hero : vehicle with:\n"
        "        keep(it.speed > 3 mps)\n"
        "    do serial:\n"
        "        wait elapsed(100 ms)\n"
    )
    assert any("keep constraint" in warning for warning in compiled.warnings)


def test_unknown_light_mode_fails_loudly() -> None:
    compiled = compile_source(
        "scenario lights:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        '        hero.set_lights(mode: "laser")\n'
    )
    with pytest.raises(ValueError, match="unsupported light mode"):
        compiled.tick()


def test_until_terminates_durative_behaviour() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "scenario until_loop:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        hero.drive() with:\n"
        "            speed(10 mps)\n"
        "            until elapsed(500 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=100, dt=0.1)
    assert result.status == common.Status.SUCCESS
    assert [record.name for record in result.trace] == ["DONE"]
    assert adapter.actors["hero"].s == pytest.approx(5.0)


def test_sample_variable_uses_default_and_warns() -> None:
    compiled = compile_source(
        "scenario sampled:\n"
        "    hero : vehicle\n"
        "    var v : speed = sample(10 mps, @tick, 3 mps)\n"
        "    do serial:\n"
        "        wait elapsed(100 ms)\n"
    )
    assert compiled.context.fields["v"] == pytest.approx(3.0)
    assert any("sample(...)" in warning for warning in compiled.warnings)


def test_remove_default_is_reported() -> None:
    compiled = compile_source(
        "scenario defaults:\n"
        "    hero : vehicle\n"
        "    var v : speed = 10 mps\n"
        "    remove_default(v)\n"
        "    do serial:\n"
        "        wait elapsed(100 ms)\n"
    )
    assert any("remove_default" in warning for warning in compiled.warnings)


def test_nested_remove_default_is_reported() -> None:
    compiled = compile_source(
        "struct defaults:\n"
        "    x : length = 1 m\n"
        "scenario nested:\n"
        "    q : defaults with:\n"
        "        remove_default(x)\n"
        "    do serial:\n"
        "        wait elapsed(100 ms)\n"
    )
    assert any("remove_default" in warning for warning in compiled.warnings)


def test_cover_record_and_user_modifier_are_reported() -> None:
    compiled = compile_source(
        "modifier fast of vehicle:\n"
        "    speed(10 mps)\n"
        "scenario recorded:\n"
        "    hero : vehicle\n"
        "    cover(hero.speed)\n"
        "    record(hero.speed)\n"
        "    do serial:\n"
        "        hero.drive() with:\n"
        "            fast()\n"
        "        wait elapsed(100 ms)\n"
    )
    assert any("cover(...)" in warning for warning in compiled.warnings)
    assert any("record(...)" in warning for warning in compiled.warnings)
    assert not any("user-defined modifier" in warning for warning in compiled.warnings)


def test_implication_is_evaluated() -> None:
    compiled = compile_source(
        "scenario logic:\n"
        "    var a : bool = false => true\n"
        "    var b : bool = true => false\n"
        "    do serial:\n"
        "        wait elapsed(100 ms)\n"
    )
    assert compiled.context.fields["a"] is True
    assert compiled.context.fields["b"] is False


def test_action_call_executes_body() -> None:
    compiled = compile_source(
        "namespace lib\n"
        "action greet:\n"
        "    do serial:\n"
        "        emit HELLO\n"
        "scenario caller:\n"
        "    do serial:\n"
        "        call greet()\n"
        "        emit DONE\n"
    )
    assert not any("call to action" in warning for warning in compiled.warnings)
    result = compiled.run(max_ticks=5)
    assert result.succeeded
    assert [record.name for record in result.trace] == ["HELLO", "DONE"]


@pytest.mark.parametrize("arguments", ["150 ms", "span: 150 ms"])
def test_action_call_binds_arguments(arguments: str) -> None:
    compiled = compile_source(
        "namespace lib\n"
        "action wait_for:\n"
        "    span : time\n"
        "    do serial:\n"
        "        wait elapsed(span)\n"
        "scenario caller:\n"
        "    do serial:\n"
        f"        call wait_for({arguments})\n"
        "        emit DONE\n"
    )
    result = compiled.run(max_ticks=20, dt=0.1)
    assert result.succeeded
    assert result.time == pytest.approx(0.2)
    assert [record.name for record in result.trace] == ["DONE"]


def test_action_call_accepts_actor_parameter_and_defaults() -> None:
    adapter = MockAdapter()
    compiled = compile_file("action_calls.osc", adapter=adapter)
    result = compiled.run(max_ticks=20, dt=0.1)
    assert result.succeeded
    assert result.time == pytest.approx(0.2)
    assert [record.name for record in result.trace] == ["READY", "DONE"]
    assert adapter.actors["hero"].speed == pytest.approx(5.0)
    assert adapter.actors["hero"].s == pytest.approx(0.5)


def test_nested_action_calls_restore_the_caller_scope() -> None:
    compiled = compile_source(
        "namespace lib\n"
        "action pause:\n"
        "    span : time = 50 ms\n"
        "    do serial:\n"
        "        wait elapsed(span)\n"
        "action outer:\n"
        "    span : time = 100 ms\n"
        "    do serial:\n"
        "        call pause()\n"
        "        wait elapsed(span)\n"
        "scenario nested:\n"
        "    do serial:\n"
        "        call outer()\n"
        "        emit DONE\n"
    )
    result = compiled.run(max_ticks=20, dt=0.1)
    assert result.succeeded
    assert result.time == pytest.approx(0.2)
    assert [record.name for record in result.trace] == ["DONE"]


def test_recursive_action_call_is_rejected() -> None:
    unit = parse(
        "namespace lib\n"
        "action loop:\n"
        "    do serial:\n"
        "        call loop()\n"
        "scenario caller:\n"
        "    do serial:\n"
        "        call loop()\n",
        source="<test>.osc",
    )
    model = analyze(unit)
    assert not model.diagnostics.has_errors
    with pytest.raises(CompilationError, match="recursive action"):
        compile_scenario(model)


# ------------------------------------------------- qualified actions (2.1)


def test_qualified_action_body_executes() -> None:
    compiled = compile_source(
        "actor messenger\n"
        "action messenger.announce:\n"
        "    do serial:\n"
        "        emit READY\n"
        "scenario s:\n"
        "    m : messenger\n"
        "    do serial:\n"
        "        m.announce()\n"
        "        emit DONE\n"
    )
    result = compiled.run(max_ticks=5)
    assert result.succeeded
    assert [record.name for record in result.trace] == ["READY", "DONE"]
    assert not any("unsupported behaviour" in warning for warning in compiled.warnings)


@pytest.mark.parametrize("arguments, expected", [("", 0.1), ("span: 200 ms", 0.2)])
def test_qualified_action_binds_arguments_and_defaults(
    arguments: str, expected: float
) -> None:
    compiled = compile_source(
        "actor timer\n"
        "action timer.hold:\n"
        "    span : time = 100 ms\n"
        "    do serial:\n"
        "        wait elapsed(span)\n"
        "scenario s:\n"
        "    t : timer\n"
        "    do serial:\n"
        f"        t.hold({arguments})\n"
        "        emit DONE\n"
    )
    result = compiled.run(max_ticks=30)
    assert result.succeeded
    assert result.time == pytest.approx(expected)
    assert [record.name for record in result.trace] == ["DONE"]


def test_qualified_action_binds_it_to_the_target_actor() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "actor cruiser inherits vehicle\n"
        "action cruiser.cruise:\n"
        "    do serial:\n"
        "        it.drive() with:\n"
        "            speed(5 mps)\n"
        "            until elapsed(300 ms)\n"
        "scenario s:\n"
        "    c : cruiser\n"
        "    do serial:\n"
        "        c.cruise()\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert result.time == pytest.approx(0.3)
    assert adapter.actors["c"].speed == pytest.approx(5.0)


def test_user_defined_modifier_expands_on_direct_behavior() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "modifier fast of vehicle:\n"
        "    speed(10 mps)\n"
        "scenario s:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        hero.drive() with:\n"
        "            fast()\n"
        "            until elapsed(300 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert adapter.actors["hero"].speed == pytest.approx(10.0)
    assert not any("user-defined" in warning for warning in compiled.warnings)


def test_user_defined_modifier_expands_for_start_behavior() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "modifier start_fast of vehicle:\n"
        "    speed(5 mps, at: start)\n"
        "scenario s:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        hero.assign_position() with:\n"
        "            start_fast()\n"
        "        wait elapsed(100 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    assert compiled.context.initialized_actions
    result = compiled.run(max_ticks=5)
    assert result.succeeded
    assert adapter.actors["hero"].speed == pytest.approx(5.0)


def test_user_defined_modifier_reaches_attached_action_body() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "modifier fast of vehicle:\n"
        "    speed(10 mps)\n"
        "actor cruiser inherits vehicle\n"
        "action cruiser.boost:\n"
        "    do serial:\n"
        "        it.drive()\n"
        "        wait elapsed(100 ms)\n"
        "scenario s:\n"
        "    c : cruiser\n"
        "    do serial:\n"
        "        c.boost() with:\n"
        "            fast()\n"
        "            until elapsed(300 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert adapter.actors["c"].speed == pytest.approx(10.0)
    assert not any("user-defined" in warning for warning in compiled.warnings)


def test_user_defined_modifier_expansion_keeps_textual_order() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "modifier fast of vehicle:\n"
        "    speed(10 mps)\n"
        "scenario s:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        hero.drive() with:\n"
        "            speed(5 mps)\n"
        "            fast()\n"
        "            until elapsed(300 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert adapter.actors["hero"].speed == pytest.approx(10.0)


def test_nested_user_defined_modifier_expands() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "modifier fast of vehicle:\n"
        "    speed(10 mps)\n"
        "modifier very_fast of vehicle:\n"
        "    fast()\n"
        "scenario s:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        hero.drive() with:\n"
        "            very_fast()\n"
        "            until elapsed(300 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert adapter.actors["hero"].speed == pytest.approx(10.0)


def test_cyclic_user_defined_modifier_is_reported() -> None:
    compiled = compile_source(
        "modifier a of vehicle:\n"
        "    b()\n"
        "modifier b of vehicle:\n"
        "    a()\n"
        "scenario s:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        hero.drive() with:\n"
        "            a()\n"
        "            until elapsed(100 ms)\n"
        "        emit DONE\n"
    )
    assert any(
        "cyclic" in warning and "'a'" in warning for warning in compiled.warnings
    )
    assert compiled.run(max_ticks=5).succeeded


def test_qualified_action_standard_modifier_reaches_body() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "actor cruiser inherits vehicle\n"
        "action cruiser.cruise:\n"
        "    do serial:\n"
        "        it.drive()\n"
        "        wait elapsed(100 ms)\n"
        "scenario s:\n"
        "    c : cruiser\n"
        "    do serial:\n"
        "        c.cruise() with:\n"
        "            speed(5 mps)\n"
        "            until elapsed(300 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert adapter.actors["c"].speed == pytest.approx(5.0)
    assert not any("not applied" in warning for warning in compiled.warnings)


def test_qualified_action_inner_modifier_overrides_outer() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "actor cruiser inherits vehicle\n"
        "action cruiser.cruise:\n"
        "    do serial:\n"
        "        it.drive() with:\n"
        "            speed(3 mps)\n"
        "        wait elapsed(100 ms)\n"
        "scenario s:\n"
        "    c : cruiser\n"
        "    do serial:\n"
        "        c.cruise() with:\n"
        "            speed(5 mps)\n"
        "            until elapsed(300 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert adapter.actors["c"].speed == pytest.approx(3.0)


def test_qualified_action_modifier_applies_only_to_receiver() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "actor cruiser inherits vehicle\n"
        "action cruiser.escort:\n"
        "    other : cruiser\n"
        "    do parallel:\n"
        "        it.drive()\n"
        "        other.drive()\n"
        "scenario s:\n"
        "    c : cruiser\n"
        "    n : cruiser\n"
        "    do serial:\n"
        "        c.escort(n) with:\n"
        "            speed(5 mps)\n"
        "            until elapsed(300 ms)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert adapter.actors["c"].speed == pytest.approx(5.0)
    assert adapter.actors["n"].speed == pytest.approx(0.0)


def test_qualified_action_position_modifier_reaches_body() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "actor cruiser inherits vehicle\n"
        "action cruiser.place:\n"
        "    do serial:\n"
        "        it.assign_position()\n"
        "        wait elapsed(100 ms)\n"
        "scenario s:\n"
        "    c : cruiser\n"
        "    do serial:\n"
        "        c.place() with:\n"
        "            position(x: 10 m)\n"
        "        emit DONE\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=10)
    assert result.succeeded
    assert adapter.actors["c"].x == pytest.approx(10.0)


def test_recursive_qualified_action_is_rejected() -> None:
    unit = parse(
        "actor looper\n"
        "action looper.loop:\n"
        "    do serial:\n"
        "        it.loop()\n"
        "scenario s:\n"
        "    l : looper\n"
        "    do serial:\n"
        "        l.loop()\n",
        source="<test>.osc",
    )
    model = analyze(unit)
    assert not model.diagnostics.has_errors
    with pytest.raises(CompilationError, match="recursive action"):
        compile_scenario(model)


def test_elapsed_accepts_milliseconds() -> None:
    compiled = compile_source(
        "scenario timing:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        wait elapsed(500 ms)\n",
    )
    result = compiled.run(max_ticks=100, dt=0.1)
    assert result.status == common.Status.SUCCESS
    assert result.time == pytest.approx(0.5)


def test_mock_adapter_motion_and_lane_change() -> None:
    adapter = MockAdapter()
    adapter.spawn("hero", "vehicle")
    adapter.set_speed("hero", 10.0)
    adapter.step(0.5)
    assert adapter.actor("hero").s == pytest.approx(5.0)
    adapter.change_lane("hero", 1, "right")
    assert adapter.actor("hero").lane == 2
    adapter.change_lane("hero", 1, "left")
    assert adapter.actor("hero").lane == 1


def test_pedestrian_walk_moves_actor() -> None:
    adapter = MockAdapter()
    compiled = compile_source(
        "scenario walking:\n"
        "    ped : pedestrian\n"
        "    do serial:\n"
        "        one_of:\n"
        "            ped.walk() with:\n"
        "                speed(1.2 mps)\n"
        "            wait elapsed(500 ms)\n"
        "        emit WALKED\n",
        adapter=adapter,
    )
    result = compiled.run(max_ticks=100, dt=0.1)
    assert result.status == common.Status.SUCCESS
    assert [record.name for record in result.trace] == ["WALKED"]
    assert adapter.actors["ped"].type_name == "pedestrian"
    assert adapter.actors["ped"].speed == pytest.approx(1.2)
    assert adapter.actors["ped"].s == pytest.approx(0.6)


def test_snapshot_contains_only_tree_structure() -> None:
    compiled = compile_file("stage3_parallel.osc")
    data = snapshot(compiled.root)
    assert data["type"] == "Sequence"
    assert data["children"][0]["type"] == "Parallel"
    assert all(set(child) <= {"type", "name", "children"} for child in data["children"])


def test_user_defined_actor_method_is_evaluated() -> None:
    compiled = compile_source(
        "actor custom_vehicle:\n"
        "    var target_speed : speed = 10 kph\n"
        "    def is_fast() -> bool is expression it.target_speed > 30 kph\n"
        "\n"
        "scenario methods:\n"
        "    hero : custom_vehicle\n"
        "    do serial:\n"
        "        wait hero.is_fast()\n"
        "        emit FAST\n",
    )
    hero = compiled.context.fields["hero"]
    assert compiled.context.call(hero, "is_fast") is False
    hero.state.attributes["target_speed"] = 40.0 * (1000.0 / 3600.0)
    result = compiled.run(max_ticks=5)
    assert result.status == common.Status.SUCCESS
    assert [record.name for record in result.trace] == ["FAST"]


def test_runtime_layers_do_not_import_carla() -> None:
    package = ROOT / "src" / "osc2c"
    for folder in ("backend", "runtime", "semantics", "adapters", "frontend"):
        for path in (package / folder).rglob("*.py"):
            if path.name == "carla.py":
                continue
            source = path.read_text(encoding="utf-8")
            assert "import carla" not in source, path


# ------------------------------------------------- standard-library actions

ASAM_STANDARD = ROOT / "external" / "asam" / "standard.osc"


def _compile_with_stdlib(tmp_path: Path, source: str):
    from osc2c.cli import _analyze_path

    path = tmp_path / "scenario.osc"
    path.write_text(source, encoding="utf-8")
    model, _, _ = _analyze_path(path, [str(ASAM_STANDARD)])
    assert not model.diagnostics.has_errors, [
        item.format() for item in model.diagnostics
    ]
    return compile_scenario(model, adapter=MockAdapter())


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_library_drive_accepts_a_standard_speed_modifier(tmp_path: Path) -> None:
    compiled = _compile_with_stdlib(
        tmp_path,
        "use stdtypes\n"
        "use std\n"
        "\n"
        "scenario lib_drive:\n"
        "    hero : vehicle\n"
        "\n"
        "    do serial:\n"
        "        hero.drive() with:\n"
        "            speed(10 mps)\n"
        "            until elapsed(500 ms)\n"
        "        emit DONE\n",
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert compiled.adapter.actors["hero"].speed == pytest.approx(10.0)
    assert compiled.adapter.actors["hero"].s == pytest.approx(5.0)


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_library_assign_speed_sets_speed_once(tmp_path: Path) -> None:
    compiled = _compile_with_stdlib(
        tmp_path,
        "use stdtypes\n"
        "use std\n"
        "\n"
        "scenario lib_speed:\n"
        "    hero : vehicle\n"
        "\n"
        "    do serial:\n"
        "        hero.assign_speed(speed: 5 mps)\n"
        "        wait elapsed(100 ms)\n"
        "        emit DONE\n",
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert compiled.adapter.actors["hero"].speed == pytest.approx(5.0)
    assert compiled.adapter.actors["hero"].s == pytest.approx(0.5)


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_library_move_is_durative(tmp_path: Path) -> None:
    compiled = _compile_with_stdlib(
        tmp_path,
        "use stdtypes\n"
        "use std\n"
        "\n"
        "scenario lib_move:\n"
        "    hero : vehicle\n"
        "\n"
        "    do serial:\n"
        "        hero.move() with:\n"
        "            speed(4 mps)\n"
        "            until elapsed(300 ms)\n"
        "        emit DONE\n",
    )
    result = compiled.run(max_ticks=20)
    assert result.succeeded
    assert result.time == pytest.approx(0.3)
    assert compiled.adapter.actors["hero"].speed == pytest.approx(4.0)
    assert compiled.adapter.actors["hero"].s == pytest.approx(1.2)


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_unmapped_library_action_fails_loudly(tmp_path: Path) -> None:
    compiled = _compile_with_stdlib(
        tmp_path,
        "use stdtypes\n"
        "use std\n"
        "\n"
        "scenario lib_unmapped:\n"
        "    hero : vehicle\n"
        "\n"
        "    do serial:\n"
        "        hero.follow_trajectory()\n",
    )
    result = compiled.run(max_ticks=5)
    assert result.status == common.Status.FAILURE
    assert any(
        "unsupported behaviour 'follow_trajectory' on 'hero'" in reason
        for reason in result.unsupported
    )


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_cli_run_executes_a_library_action(tmp_path: Path, capsys) -> None:
    from osc2c.cli import main

    path = tmp_path / "cli.osc"
    path.write_text(
        "use stdtypes\n"
        "use std\n"
        "\n"
        "scenario cli_drive:\n"
        "    hero : vehicle\n"
        "\n"
        "    do serial:\n"
        "        hero.drive() with:\n"
        "            speed(10 mps)\n"
        "            until elapsed(500 ms)\n"
        "        emit DONE\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "run",
                str(path),
                "--stdlib",
                str(ASAM_STANDARD),
                "--ticks",
                "20",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "SUCCESS"
    assert result["actors"]["hero"]["speed"] == pytest.approx(10.0)


# ------------------------------------------------------------------------ CLI


def test_cli_bt_and_run(capsys) -> None:
    from osc2c.cli import main

    assert main(["bt", str(SCENARIOS / "stage3_parallel.osc")]) == 0
    tree = json.loads(capsys.readouterr().out)
    assert tree["name"] == "serial"

    assert (
        main(["run", str(SCENARIOS / "stage3_parallel.osc"), "--ticks", "50", "--dt", "0.1"])
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "SUCCESS"
    assert result["events"] == ["TICK", "DONE"]
