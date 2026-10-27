from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from osc2c.frontend import ast
from osc2c.frontend.parser import ParseError, parse, parse_file

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = sorted((ROOT / "scenarios" / "dev").glob("*.osc"))
GOLDEN = ROOT / "tests" / "golden" / "ast"
UPDATE = os.environ.get("UPDATE_GOLDEN") == "1"


def scenario_of(unit: ast.CompilationUnit) -> ast.ScenarioDecl:
    return next(decl for decl in unit.declarations if isinstance(decl, ast.ScenarioDecl))


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda path: path.name)
def test_ast_matches_golden(path: Path) -> None:
    dump = json.dumps(parse_file(path).to_dict(), indent=2) + "\n"
    golden = GOLDEN / f"{path.stem}.json"
    if UPDATE:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(dump, encoding="utf-8", newline="\n")
    assert golden.is_file(), f"missing golden file: {golden} (run UPDATE_GOLDEN=1 pytest)"
    assert dump == golden.read_text(encoding="utf-8")


def test_smoke4_structure() -> None:
    unit = parse_file(ROOT / "scenarios" / "dev" / "smoke4.osc")
    assert unit.imports == []
    assert unit.uses[0].namespaces == ["stdtypes"]

    scenario = scenario_of(unit)
    variables = {
        member.names[0]: member
        for member in scenario.members
        if isinstance(member, ast.VariableDecl)
    }
    assert set(variables) == {"v_hero", "v_npc_fast", "lag", "safety_gap"}

    hero_speed = variables["v_hero"].value
    assert isinstance(hero_speed, ast.PhysicalLiteral)
    assert (hero_speed.value, hero_speed.unit) == (35.0, "kph")

    npc_speed = variables["v_npc_fast"].value
    assert isinstance(npc_speed, ast.BinaryOp) and npc_speed.op == "+"
    assert isinstance(npc_speed.right, ast.PhysicalLiteral)
    assert (npc_speed.right.value, npc_speed.right.unit) == (12.42, "mph")

    do = next(member for member in scenario.members if isinstance(member, ast.DoDirective))
    serial = do.member
    assert isinstance(serial, ast.Composition)
    assert serial.operator == "serial"
    assert [type(member).__name__ for member in serial.members] == [
        "BehaviorInvocation",
        "BehaviorInvocation",
        "Composition",
        "EmitDirective",
        "WaitDirective",
    ]

    parallel = serial.members[2]
    assert parallel.operator == "parallel"
    wait = parallel.members[1]
    condition = wait.specification.condition
    assert isinstance(condition, ast.FallCond)
    assert isinstance(condition.expr, ast.BinaryOp) and condition.expr.op == ">"
    call = condition.expr.left
    assert isinstance(call, ast.Call)
    assert isinstance(call.target, ast.FieldAccess) and call.target.field == "ahead_of"
    assert isinstance(call.target.target, ast.FieldAccess)
    assert call.target.target.field == "position"

    assert isinstance(serial.members[4].specification.condition, ast.ElapsedCond)


def test_compound_unit_literals_are_parsed() -> None:
    unit = parse(
        "scenario s:\n"
        "    var v : speed = 1 m/s\n"
        "    var w : speed = 1 km/h\n"
        "    var a : acceleration = 1 m/s^2\n"
        "    var f : frequency = 10kph/s\n"
        "    do serial:\n"
        "        wait elapsed(100 ms)\n"
    )
    literals = [
        node
        for node in unit.walk()
        if isinstance(node, ast.PhysicalLiteral) and any(mark in node.unit for mark in "*/^")
    ]
    assert [(literal.value, literal.unit) for literal in literals] == [
        (1.0, "m/s"),
        (1.0, "km/h"),
        (1.0, "m/s^2"),
        (10.0, "kph/s"),
    ]


def test_grammar_tour_declarations() -> None:
    unit = parse_file(ROOT / "scenarios" / "dev" / "grammar_tour.osc")
    kinds = [type(decl).__name__ for decl in unit.declarations]
    assert kinds == [
        "NamespaceDecl",
        "PhysicalTypeDecl",
        "UnitDecl",
        "EnumDecl",
        "StructDecl",
        "ActorDecl",
        "ScenarioDecl",
    ]

    physical = unit.declarations[1]
    assert physical.name == "distance"
    assert [(exp.unit, exp.exponent) for exp in physical.base.exponents] == [("m", 1)]

    unit_decl = unit.declarations[2]
    assert (unit_decl.name, unit_decl.type_name) == ("km", "distance")
    assert unit_decl.spec.factor == 1000.0

    enum = unit.declarations[3]
    assert [(member.name, member.value) for member in enum.members] == [
        ("red", None),
        ("green", 1),
        ("blue", 2),
    ]

    actor = unit.declarations[5]
    event = next(member for member in actor.members if isinstance(member, ast.EventDecl))
    assert event.specification.reference.name == "horn"

    method = next(member for member in actor.members if isinstance(member, ast.MethodDecl))
    assert method.name == "is_fast"
    assert isinstance(method.return_type, ast.PrimitiveType)
    assert method.return_type.name == "bool"
    assert method.implementation.mode == "expression"


def test_spans_track_source_positions() -> None:
    unit = parse_file(ROOT / "scenarios" / "dev" / "smoke4.osc")
    scenario = scenario_of(unit)
    assert (scenario.span.line, scenario.span.column) == (3, 0)

    it_expr = next(node for node in scenario.walk() if isinstance(node, ast.ItExpr))
    assert (it_expr.span.line, it_expr.span.column) == (5, 13)

    dumped = unit.to_dict(include_spans=True)
    assert dumped["span"]["source"] == "smoke4.osc"


def test_ast_dump_is_deterministic() -> None:
    path = ROOT / "scenarios" / "dev" / "grammar_tour.osc"
    first = json.dumps(parse_file(path).to_dict(), indent=2)
    second = json.dumps(parse_file(path).to_dict(), indent=2)
    assert first == second


def test_syntax_error_reports_line() -> None:
    with pytest.raises(ParseError) as info:
        parse("scenario s:\n    hero : vehicle\n    do serial\n", source="broken.osc")
    assert "line 4" in str(info.value)


def test_enum_member_value_may_reference_another_member() -> None:
    unit = parse("enum size: [small, medium = small, huge = 0x10]\n")
    members = unit.declarations[0].members
    assert isinstance(members[1].value, ast.EnumValueRef)
    assert members[1].value.member == "small"
    assert members[2].value == 16


def test_range_type_declarators_parse() -> None:
    unit = parse(
        "struct holder:\n"
        "    span: range of length\n"
        "    grid: list of range of uint\n"
    )
    fields = unit.declarations[0].members
    assert isinstance(fields[0].type, ast.RangeType)
    assert isinstance(fields[1].type, ast.ListType)
    assert isinstance(fields[1].type.element, ast.RangeType)
    assert fields[1].type.element.element.name == "uint"


def test_primitive_type_extension_parses() -> None:
    unit = parse("extend int:\n    def twice() -> int is undefined\n")
    extension = unit.declarations[0]
    assert isinstance(extension, ast.PrimitiveExtensionDecl)
    assert extension.name == "int"
    assert len(extension.members) == 1


ASAM_STANDARD = ROOT / "external" / "asam" / "standard.osc"


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_asam_standard_library_parses() -> None:
    unit = parse_file(ASAM_STANDARD)
    assert [declaration.reference for declaration in unit.imports] == [
        "types.osc",
        "domain.osc",
    ]
    for name in ("types.osc", "domain.osc"):
        declaration = parse_file(ASAM_STANDARD.parent / name)
        assert declaration.declarations
