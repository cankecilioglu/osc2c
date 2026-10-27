"""Capability coverage matrix aligned with paper Table 2.

Each row records what the reimplementation actually supports, the evidence
that backs the claim, and (for partial/unsupported rows) what is missing.
`validate_matrix` is used by the test suite so the matrix cannot silently rot.
"""

from __future__ import annotations

import ast as py_ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]

SUPPORTED = "supported"
PARTIAL = "partial"
UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Capability:
    category: str
    capability: str
    status: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


MATRIX: tuple[Capability, ...] = (
    # ---------------------------------------------------------- action framework
    Capability(
        "Action framework",
        "Action lifecycle",
        SUPPORTED,
        ("tests/test_backend.py::test_sync_scenario_completes_and_emits_event",),
        "py_trees SUCCESS/RUNNING/FAILURE is mapped to scenario state",
    ),
    Capability(
        "Action framework",
        "Actor binding",
        SUPPORTED,
        ("tests/test_backend.py::test_keep_constraints_bind_actor_attributes",),
        "keep(it.name == ...) and role_name binding",
    ),
    Capability(
        "Action framework",
        "Composition",
        SUPPORTED,
        ("tests/test_backend.py::test_serial_parallel_and_one_of_mapping",),
        "serial / parallel / one_of",
    ),
    Capability(
        "Action framework",
        "Duration handling",
        PARTIAL,
        (
            "scenarios/dev/stage3_parallel.osc",
            "tests/test_backend.py::test_parallel_waits_for_slowest_branch",
        ),
        "wait elapsed() is supported; no automatic parallel timeout wrapper",
    ),
    # --------------------------------------------------------------- movement
    Capability(
        "Movement",
        "Drive",
        SUPPORTED,
        (
            "scenarios/dev/stage3_sync.osc",
            "tests/test_carla.py::test_adapter_spawns_and_moves",
        ),
        "durative target-speed behaviour on both adapters",
    ),
    Capability(
        "Movement",
        "Walk",
        PARTIAL,
        ("tests/test_backend.py::test_pedestrian_walk_moves_actor",),
        "pedestrian walk works on the mock adapter; CarlaAdapter spawns vehicles and environment only",
    ),
    Capability(
        "Movement",
        "Speed control",
        PARTIAL,
        (
            "src/osc2c/backend/method_registry.py",
            "src/osc2c/adapters/carla.py",
        ),
        "instant setpoint on mock; proportional throttle/brake on CARLA, no integral term",
    ),
    Capability(
        "Movement",
        "Acceleration control",
        UNSUPPORTED,
        note="no acceleration behaviour or acceleration modifier is mapped",
    ),
    Capability(
        "Movement",
        "Stationary",
        SUPPORTED,
        ("scenarios/carla/cut_in.osc",),
        "target speed 0 plus brake at initialisation",
    ),
    # -------------------------------------------------------- position & path
    Capability(
        "Position & path",
        "Assign position (absolute)",
        SUPPORTED,
        (
            "scenarios/dev/placement_modes.osc",
            "tests/test_carla.py::test_cut_in_scenario_runs_on_carla",
        ),
        "x/y/z or OpenDRIVE lane placement",
    ),
    Capability(
        "Position & path",
        "Assign orientation",
        PARTIAL,
        ("src/osc2c/adapters/carla.py",),
        "heading/yaw is supported; pitch and roll are not exposed",
    ),
    Capability(
        "Position & path",
        "Follow path",
        UNSUPPORTED,
        note="no spline/path routing; vehicles follow the current lane",
    ),
    Capability(
        "Position & path",
        "Follow trajectory",
        UNSUPPORTED,
        note="no time-parameterised trajectory tracking",
    ),
    Capability(
        "Position & path",
        "Time gap",
        UNSUPPORTED,
        note="no time-gap or TTC query; only spatial queries exist",
    ),
    Capability(
        "Position & path",
        "Space gap",
        SUPPORTED,
        ("tests/test_backend.py::test_sync_scenario_completes_and_emits_event",),
        "position.ahead_of() and position.euclidean()",
    ),
    Capability(
        "Position & path",
        "Headway",
        PARTIAL,
        ("scenarios/carla/cut_in.osc",),
        "relative spatial headway via vector projection; no time headway",
    ),
    # ------------------------------------------------------------- environment
    Capability(
        "Environment",
        "Weather control",
        UNSUPPORTED,
        note="adapter saves/restores weather but no OSC behaviour changes it",
    ),
    Capability(
        "Environment",
        "Traffic signals",
        UNSUPPORTED,
        note="traffic lights are not read or controlled",
    ),
    Capability(
        "Environment",
        "Road conditions",
        UNSUPPORTED,
        note="no surface/friction changes",
    ),
    Capability(
        "Environment",
        "Celestial position",
        SUPPORTED,
        ("scenarios/dev/environment_lights.osc",),
        "azimuth/elevation are applied to the adapter environment state",
    ),
    # --------------------------------------------------------------- modifiers
    Capability(
        "Modifiers",
        "Speed modifier",
        SUPPORTED,
        ("scenarios/dev/lane_change_speed.osc",),
        "speed(speed:, at:)",
    ),
    Capability(
        "Modifiers",
        "Acceleration modifier",
        UNSUPPORTED,
        note="not declared in the fallback standard library",
    ),
    Capability(
        "Modifiers",
        "Position modifier",
        SUPPORTED,
        ("scenarios/dev/placement_modes.osc",),
        "distance + ahead_of/behind and absolute x/y/z",
    ),
    Capability(
        "Modifiers",
        "Lateral modifier",
        SUPPORTED,
        ("scenarios/carla/cut_in.osc",),
        "lane(side:, side_of:) maps to OpenDRIVE lane offsets",
    ),
    Capability(
        "Modifiers",
        "Physical movement",
        PARTIAL,
        ("src/osc2c/adapters/carla.py",),
        "engine physics while driving; teleport for placement; no physics toggle",
    ),
    Capability(
        "Modifiers",
        "Temporal modifiers",
        SUPPORTED,
        ("tests/test_backend.py::test_elapsed_accepts_milliseconds",),
        "elapsed() with SI time values",
    ),
    Capability(
        "Modifiers",
        "Relative modifiers",
        SUPPORTED,
        ("scenarios/dev/placement_modes.osc",),
        "ahead_of / behind / side_of",
    ),
    Capability(
        "Modifiers",
        "Orientation modifiers",
        PARTIAL,
        ("src/osc2c/backend/method_registry.py",),
        "h (yaw) is accepted; no pitch/roll modifiers",
    ),
    # ------------------------------------------------------- coordinate systems
    Capability(
        "Coordinate systems",
        "Global frame (x-y-z)",
        SUPPORTED,
        ("scenarios/dev/placement_modes.osc",),
        "absolute Cartesian placement",
    ),
    Capability(
        "Coordinate systems",
        "Relative coordinates",
        SUPPORTED,
        ("scenarios/dev/placement_modes.osc",),
        "actor-relative distance and lane offset",
    ),
    Capability(
        "Coordinate systems",
        "Road frame (s-t)",
        PARTIAL,
        ("src/osc2c/adapters/mock.py",),
        "mock exposes s/lane; CARLA keeps waypoint s internally but does not expose t",
    ),
    Capability(
        "Coordinate systems",
        "Route-based (s-t)",
        UNSUPPORTED,
        note="no route construction or route-relative queries",
    ),
    # --------------------------------------------------- scenario composition
    Capability(
        "Scenario composition",
        "Serial execution",
        SUPPORTED,
        ("tests/test_backend.py::test_serial_parallel_and_one_of_mapping",),
        "Sequence(memory=True)",
    ),
    Capability(
        "Scenario composition",
        "Parallel execution",
        SUPPORTED,
        ("tests/test_backend.py::test_parallel_waits_for_slowest_branch",),
        "Parallel(SuccessOnAll)",
    ),
    Capability(
        "Scenario composition",
        "Event-driven execution",
        SUPPORTED,
        (
            "scenarios/dev/event_handshake.osc",
            "tests/test_backend.py::test_latched_event_satisfies_later_wait",
        ),
        "latched blackboard events",
    ),
    Capability(
        "Scenario composition",
        "Conditional triggers",
        SUPPORTED,
        ("scenarios/dev/stage3_fall.osc",),
        "elapsed, rise, fall and @event",
    ),
    Capability(
        "Scenario composition",
        "Custom behaviour",
        PARTIAL,
        ("tests/test_backend.py::test_user_defined_actor_method_is_evaluated",),
        "user expression methods and action bodies; no action inheritance merging",
    ),
    Capability(
        "Scenario composition",
        "Custom actions",
        SUPPORTED,
        (
            "scenarios/dev/action_calls.osc",
            "tests/test_backend.py::test_action_call_accepts_actor_parameter_and_defaults",
        ),
        "action bodies compile to scoped subtrees with positional/named arguments and defaults",
    ),
    Capability(
        "Scenario composition",
        "Conflict resolution",
        PARTIAL,
        ("tests/test_backend.py::test_serial_parallel_and_one_of_mapping",),
        "one_of first-success arbitration; no priority or conflict policies",
    ),
    Capability(
        "Scenario composition",
        "Semantic validation",
        SUPPORTED,
        ("tests/test_semantics.py",),
        "scopes, types, units and stable diagnostic codes",
    ),
    Capability(
        "Scenario composition",
        "one_of",
        SUPPORTED,
        ("tests/test_backend.py::test_serial_parallel_and_one_of_mapping",),
        "Parallel(SuccessOnOne)",
    ),
    Capability(
        "Scenario composition",
        "rise",
        SUPPORTED,
        ("tests/test_backend.py::test_rise_does_not_fire_on_an_already_true_condition",),
        "edge detection",
    ),
    Capability(
        "Scenario composition",
        "fall",
        SUPPORTED,
        ("tests/test_backend.py::test_fall_edge_fires_after_speed_drops",),
        "edge detection",
    ),
)


def _evidence_problem(reference: str) -> str | None:
    path_text, _, symbol = reference.partition("::")
    path = ROOT / path_text
    if not path.exists():
        return f"missing evidence path '{path_text}'"
    if not symbol:
        return None
    if path.suffix != ".py":
        return f"evidence symbol '{symbol}' needs a Python file"
    try:
        tree = py_ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as error:
        return f"cannot parse evidence file '{path_text}': {error}"
    name = symbol.split("[", 1)[0]
    for node in tree.body:
        if isinstance(node, (py_ast.FunctionDef, py_ast.AsyncFunctionDef, py_ast.ClassDef)):
            if node.name == name:
                return None
    return f"missing evidence symbol '{symbol}' in '{path_text}'"


def validate_matrix(matrix: Iterable[Capability] = MATRIX) -> list[str]:
    problems: list[str] = []
    valid = {SUPPORTED, PARTIAL, UNSUPPORTED}
    seen: set[tuple[str, str]] = set()
    for row in matrix:
        label = f"{row.category}/{row.capability}"
        key = (row.category, row.capability)
        if key in seen:
            problems.append(f"{label}: duplicate capability row")
        seen.add(key)
        if row.status not in valid:
            problems.append(f"{label}: invalid status '{row.status}'")
        if row.status == UNSUPPORTED and not row.note:
            problems.append(f"{label}: unsupported row needs a reason")
        if row.status != UNSUPPORTED and not row.evidence:
            problems.append(f"{label}: supported row needs evidence")
        for reference in row.evidence:
            problem = _evidence_problem(reference)
            if problem is not None:
                problems.append(f"{label}: {problem}")
    return problems


def summary(matrix: Iterable[Capability] = MATRIX) -> dict[str, object]:
    rows = list(matrix)
    counts = {
        status: sum(row.status == status for row in rows)
        for status in (SUPPORTED, PARTIAL, UNSUPPORTED)
    }
    total = len(rows)
    return {
        "total": total,
        **counts,
        "supported_ratio": round(counts[SUPPORTED] / total, 4) if total else 0.0,
        "weighted_ratio": round(
            (counts[SUPPORTED] + 0.5 * counts[PARTIAL]) / total, 4
        )
        if total
        else 0.0,
    }


def to_markdown(matrix: Iterable[Capability] = MATRIX) -> str:
    rows = list(matrix)
    stats = summary(rows)
    lines = [
        "| Category | Capability | Status | Evidence | Note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        evidence = "<br>".join(f"`{item}`" for item in row.evidence) or "—"
        note = row.note or "—"
        lines.append(
            f"| {row.category} | {row.capability} | {row.status} | "
            f"{evidence} | {note} |"
        )
    lines.append("")
    lines.append(
        f"Total {stats['total']}: {stats['supported']} supported, "
        f"{stats['partial']} partial, {stats['unsupported']} unsupported "
        f"(strict {stats['supported_ratio']:.0%}, "
        f"weighted {stats['weighted_ratio']:.0%})."
    )
    return "\n".join(lines)
