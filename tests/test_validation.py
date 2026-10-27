from __future__ import annotations

import math

import pytest

from osc2c.adapters.mock import MockAdapter
from osc2c.backend import compile_scenario
from osc2c.coverage import (
    MATRIX,
    PARTIAL,
    SUPPORTED,
    UNSUPPORTED,
    Capability,
    summary,
    to_markdown,
    validate_matrix,
)
from osc2c.frontend.parser import parse_file
from osc2c.semantics import analyze
from osc2c.validation import SCENARIOS, measure_compile, run_mock, run_mock_suite

EXPECTED_STATUS = {spec.id: "SUCCESS" for spec in SCENARIOS}


@pytest.mark.parametrize("spec", SCENARIOS, ids=lambda spec: spec.id)
def test_validation_scenarios_complete_on_mock(spec) -> None:
    run = run_mock(spec, max_ticks=500)
    assert run["status"] == EXPECTED_STATUS[spec.id]
    assert run["events"] == list(spec.expected_events)
    assert run["unsupported"] == []
    assert run["ticks"] > 0
    assert set(run["final_actors"]) >= {"hero"}


def test_cut_in_outcome() -> None:
    run = run_mock(SCENARIOS[0])
    hero = run["final_actors"]["hero"]
    npc = run["final_actors"]["npc"]
    assert hero[1] == npc[1]
    assert hero[2] == pytest.approx(0.0)
    assert hero[3] == "high_beam"
    assert npc[2] == pytest.approx(6.0)
    assert run["event_times"] == [{"name": "CUT_IN", "time": 2.0}]


def test_lane_change_and_speed_outcome() -> None:
    run = run_mock(SCENARIOS[1])
    hero = run["final_actors"]["hero"]
    npc = run["final_actors"]["npc"]
    assert hero[1] == 0
    assert hero[2] == pytest.approx(14.0)
    assert npc[2] == pytest.approx(10.0)


def test_event_handshake_order_and_timing() -> None:
    run = run_mock(SCENARIOS[2])
    times = {item["name"]: item["time"] for item in run["event_times"]}
    assert times == {"PING": 0.2, "PONG": 0.2, "DONE": 0.3}


def test_placement_modes_are_applied_before_the_body() -> None:
    run = run_mock(SCENARIOS[3])
    hero = run["final_actors"]["hero"]
    npc = run["final_actors"]["npc"]
    follower = run["final_actors"]["follower"]
    assert hero[4:7] == [100.0, 5.0, 0.0]
    assert npc[0] == pytest.approx(20.0)
    assert npc[1] == 0
    assert follower[0] == pytest.approx(-8.0)
    assert follower[1] == 1


def test_environment_and_lights_outcome() -> None:
    adapter = MockAdapter()
    compiled = compile_scenario(
        analyze(parse_file(SCENARIOS[4].path)), adapter=adapter
    )
    result = compiled.run(max_ticks=100)
    assert result.succeeded
    assert adapter.azimuth == pytest.approx(3 * math.pi / 2)
    assert adapter.elevation == pytest.approx(math.radians(12))
    run = run_mock(SCENARIOS[4])
    hero = run["final_actors"]["hero"]
    assert hero[3] == "high_beam"
    assert hero[2] == pytest.approx(30 * 1000 / 3600, rel=1e-5)


def test_twenty_mock_runs_are_byte_for_byte_deterministic() -> None:
    suite = run_mock_suite(repeat=20, compile_repeat=1)
    assert len(suite["scenarios"]) == len(SCENARIOS)
    for item in suite["scenarios"]:
        assert item["status"] == "SUCCESS", item["id"]
        assert item["events_match"], item["id"]
        assert item["deterministic"], item["id"]
        assert item["unique_hashes"] == 1, item["id"]


def test_compile_benchmark_reports_all_phases() -> None:
    stats = measure_compile(SCENARIOS[0].path, repeat=2)
    for phase in ("parse", "analyze", "compile", "total"):
        assert stats[phase]["count"] == 2
        assert stats[phase]["median"] >= 0.0
    assert stats["ast_nodes"] > 0
    assert stats["bt_nodes"] > 0
    assert stats["total"]["median"] >= stats["parse"]["median"]


def test_coverage_matrix_is_valid_and_complete() -> None:
    assert validate_matrix() == []
    stats = summary(MATRIX)
    assert stats["total"] == len(MATRIX)
    assert stats["supported"] + stats["partial"] + stats["unsupported"] == len(MATRIX)
    assert stats["supported"] == sum(row.status == SUPPORTED for row in MATRIX)
    assert stats["partial"] == sum(row.status == PARTIAL for row in MATRIX)
    assert stats["unsupported"] == sum(row.status == UNSUPPORTED for row in MATRIX)
    assert 0.0 < stats["weighted_ratio"] <= 1.0
    text = to_markdown()
    assert "| Category | Capability | Status |" in text
    assert f"Total {len(MATRIX)}:" in text


def test_coverage_matrix_rejects_duplicate_rows_and_bad_evidence() -> None:
    duplicates = (
        Capability("Demo", "Row", UNSUPPORTED, note="first"),
        Capability("Demo", "Row", UNSUPPORTED, note="second"),
    )
    assert any("duplicate capability row" in item for item in validate_matrix(duplicates))

    bad_symbol = (
        Capability(
            "Demo",
            "Row",
            SUPPORTED,
            ("tests/test_backend.py::test_this_function_does_not_exist",),
        ),
    )
    problems = validate_matrix(bad_symbol)
    assert any("missing evidence symbol" in item for item in problems)

    bad_path = (
        Capability("Demo", "Row", SUPPORTED, ("tests/missing_file.py",)),
    )
    assert any("missing evidence path" in item for item in validate_matrix(bad_path))
