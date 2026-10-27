"""Semantic middle-end tests: symbol resolution, units, types, diagnostics."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from osc2c.cli import main
from osc2c.frontend import ast
from osc2c.frontend.parser import parse, parse_file
from osc2c.semantics import (
    CompositeTypeInfo,
    PhysicalTypeInfo,
    Severity,
    SymbolKind,
    analyze,
    describe_type,
)
from osc2c.semantics.types import dimension

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios" / "dev"


def _analyze(source: str, name: str = "test.osc"):
    return analyze(parse(source, name))


def _codes(model) -> list[str]:
    return [diagnostic.code for diagnostic in model.diagnostics]


def _errors(model) -> list[str]:
    return [diagnostic.code for diagnostic in model.diagnostics.errors]


def _node(model, node_type, predicate=None):
    for node in model.unit.walk():
        if isinstance(node, node_type) and (predicate is None or predicate(node)):
            return node
    raise AssertionError(f"no {node_type.__name__} matched")


@pytest.mark.parametrize("path", sorted(SCENARIOS.glob("*.osc")), ids=lambda path: path.name)
def test_dev_scenarios_have_no_semantic_errors(path: Path) -> None:
    model = analyze(parse_file(path))
    assert _errors(model) == []


def test_smoke4_symbol_and_unit_annotations() -> None:
    model = analyze(parse_file(SCENARIOS / "smoke4.osc"))
    scenario = model.namespaces[""].lookup_local("s").type
    assert isinstance(scenario, CompositeTypeInfo)

    assert describe_type(scenario.fields["v_hero"].type) == "speed"
    assert describe_type(scenario.fields["v_npc_fast"].type) == "speed"
    assert describe_type(scenario.fields["lag"].type) == "length"
    assert describe_type(scenario.fields["safety_gap"].type) == "length"
    assert describe_type(scenario.fields["hero"].type) == "vehicle"

    literal = _node(
        model, ast.PhysicalLiteral, lambda node: node.value == 35.0 and node.unit == "kph"
    )
    unit = model.unit_of(literal)
    assert unit is not None and unit.name == "kph"
    assert unit.to_si(35.0) == pytest.approx(35.0 * 1000 / 3600)

    addition = _node(
        model,
        ast.BinaryOp,
        lambda node: node.op == "+" and node.span.line == 9,
    )
    assert describe_type(model.type_of(addition)) == "speed"

    start = _node(model, ast.Identifier, lambda node: node.parts == ["start"])
    symbol = model.symbol_at(start)
    assert symbol is not None and symbol.kind is SymbolKind.ENUM_MEMBER
    assert symbol.enum is not None and symbol.enum.name == "direction"

    speed_ref = _node(model, ast.NamedType, lambda node: node.name == "speed")
    assert model.type_ref_of(speed_ref) is not None


def test_every_expression_is_annotated() -> None:
    for path in sorted(SCENARIOS.glob("*.osc")):
        model = analyze(parse_file(path))
        expressions = [node for node in model.unit.walk() if isinstance(node, ast.Expr)]
        missing = [node for node in expressions if id(node) not in model.expr_types]
        assert missing == [], f"{path.name} has unannotated expressions: {missing}"


def test_unit_registry_and_conversions() -> None:
    model = analyze(parse("scenario s:\n    do serial:\n        wait elapsed(1s)\n", "units.osc"))
    units = model.namespaces["stdtypes"]
    kph = units.lookup_local("kph").unit
    deg = units.lookup_local("deg").unit
    assert kph is not None and kph.to_si(36.0) == pytest.approx(10.0)
    assert deg is not None and deg.to_si(180.0) == pytest.approx(math.pi)


def test_compound_units_resolve_and_convert() -> None:
    model = analyze(parse_file(SCENARIOS / "compound_units.osc"))
    assert _errors(model) == []
    scenario = model.namespaces[""].lookup_local("compound_units").type
    assert describe_type(scenario.fields["direct_speed"].type) == "speed"
    assert describe_type(scenario.fields["road_speed"].type) == "speed"
    assert describe_type(scenario.fields["deceleration"].type) == "acceleration"
    assert describe_type(scenario.fields["cadence"].type) == "frequency"

    units = {
        node.unit: model.unit_of(node)
        for node in model.unit.walk()
        if isinstance(node, ast.PhysicalLiteral)
    }
    assert units["m/s"].to_si(1.0) == pytest.approx(1.0)
    assert units["km/h"].to_si(1.0) == pytest.approx(1000 / 3600)
    assert units["m/s^2"].to_si(1.0) == pytest.approx(1.0)
    assert units["m/s^2"].physical.dimension == dimension(m=1, s=-2)
    assert units["s^-1"].physical.dimension == dimension(s=-1)


def test_offset_unit_is_rejected_in_compound_unit() -> None:
    model = _analyze(
        "type temp is SI(K: 1)\n"
        "unit celsius of temp is SI(K: 1, factor: 1, offset: 273.15)\n"
        "scenario s:\n"
        "    var t : temp = 1 celsius/K\n"
        "    do serial:\n"
        "        wait elapsed(100 ms)\n"
    )
    assert _errors(model) == ["E0203"]
    assert any("offset" in item.message for item in model.diagnostics.errors)


def test_unknown_compound_unit_is_reported() -> None:
    path = SCENARIOS.parent / "diagnostics" / "unknown_compound_unit.osc"
    model = analyze(parse_file(path))
    observed = [
        (diagnostic.span.line, diagnostic.code, diagnostic.message)
        for diagnostic in model.diagnostics.errors
        if diagnostic.span is not None
    ]
    assert observed == [(5, "E0203", "unknown unit 'parsec'")]


def test_same_dimension_units_are_compatible() -> None:
    model = _analyze(
        "scenario s:\n"
        "    var combined : speed = 10 kph + 5 mph\n"
        "    do serial:\n"
        "        wait elapsed(1s)\n"
    )
    assert _errors(model) == []
    scenario = model.namespaces[""].lookup_local("s").type
    assert describe_type(scenario.fields["combined"].type) == "speed"


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (
            "scenario s:\n    var x : nonsense\n    do serial:\n        wait elapsed(1s)\n",
            "E0201",
        ),
        (
            "scenario s:\n    var x : speed = nope\n    do serial:\n        wait elapsed(1s)\n",
            "E0402",
        ),
        (
            "scenario s:\n    var x : speed = 5 m\n    do serial:\n        wait elapsed(1s)\n",
            "E0401",
        ),
        (
            "scenario s:\n    var x : speed\n    var x : speed\n"
            "    do serial:\n        wait elapsed(1s)\n",
            "E0101",
        ),
        (
            "scenario s:\n    var x : speed = 10 furlongs\n"
            "    do serial:\n        wait elapsed(1s)\n",
            "E0203",
        ),
    ],
)
def test_basic_semantic_errors(source: str, code: str) -> None:
    model = _analyze(source)
    assert code in _errors(model)


def test_enum_members_and_unknown_members() -> None:
    model = _analyze(
        "enum color: [red, green]\n"
        "scenario s:\n"
        "    var c : color = color!red\n"
        "    do serial:\n"
        "        wait elapsed(1s)\n"
    )
    assert _errors(model) == []

    model = _analyze(
        "enum color: [red, green]\n"
        "scenario s:\n"
        "    var c : color = color!pink\n"
        "    do serial:\n"
        "        wait elapsed(1s)\n"
    )
    assert "E0404" in _errors(model)


def test_duplicate_enum_member() -> None:
    model = _analyze("enum color: [red, red]\n")
    assert "E0102" in _errors(model)


def test_ambiguous_enum_member() -> None:
    model = _analyze(
        "enum a: [start]\n"
        "enum b: [start]\n"
        "scenario s:\n"
        "    hero : vehicle\n"
        "    do serial:\n"
        "        hero.assign_position() with:\n"
        "            lane(1, at: start)\n"
    )
    assert "E0404" in _errors(model)


def test_inheritance_cycle_and_kind_mismatch() -> None:
    cycle = _analyze(
        "actor a inherits b:\n    var x : int\n"
        "actor b inherits a:\n    var y : int\n"
        "scenario s:\n    do serial:\n        wait elapsed(1s)\n"
    )
    assert "E0301" in _errors(cycle)

    mismatch = _analyze(
        "struct p:\n    x : float\n"
        "actor a inherits p:\n    var y : int\n"
        "scenario s:\n    do serial:\n        wait elapsed(1s)\n"
    )
    assert "E0302" in _errors(mismatch)


def test_inherited_fields_and_enum_extension() -> None:
    model = _analyze(
        "namespace demo\n"
        "type distance is SI(m: 1)\n"
        "unit km of distance is SI(m: 1, factor: 1000)\n"
        "enum color: [red, green]\n"
        "extend color: [blue]\n"
        "actor base:\n"
        "    var x : speed\n"
        "actor child inherits base:\n"
        "    var y : speed\n"
        "scenario s:\n"
        "    c : child\n"
        "    var z : speed = c.x + 1 kph\n"
        "    do serial:\n"
        "        wait elapsed(1s)\n"
    )
    assert _errors(model) == []
    demo = model.namespaces["demo"]
    child = demo.lookup_local("child").type
    assert isinstance(child, CompositeTypeInfo)
    assert child.base is not None and child.base.name == "base"
    assert "x" in child.base.fields and "y" in child.fields

    field = _node(model, ast.FieldAccess, lambda node: node.field == "x")
    assert describe_type(model.type_of(field)) == "speed"
    color = demo.lookup_local("color").type
    assert color.members == {"red": 0, "green": 1, "blue": 2}


def test_argument_errors() -> None:
    missing = _analyze(
        "scenario s:\n"
        "    e : environment\n"
        "    do serial:\n"
        "        e.assign_celestial_position(azimuth: 1deg)\n"
    )
    assert "E0405" in _errors(missing)

    unknown = _analyze(
        "scenario s:\n"
        "    e : environment\n"
        "    do serial:\n"
        "        e.assign_celestial_position(azimuth: 1deg, elevation: 2deg, nope: 3deg)\n"
    )
    assert "E0406" in _errors(unknown)

    mismatch = _analyze(
        "scenario s:\n"
        "    e : environment\n"
        "    do serial:\n"
        "        e.assign_celestial_position(azimuth: 5 m, elevation: 2deg)\n"
    )
    assert "E0401" in _errors(mismatch)


def test_action_call_arguments_are_checked() -> None:
    missing = _analyze(
        "action wait_for:\n"
        "    span : time\n"
        "    do serial:\n"
        "        wait elapsed(span)\n"
        "scenario caller:\n"
        "    do serial:\n"
        "        call wait_for()\n"
    )
    assert "E0405" in _errors(missing)

    unknown = _analyze(
        "action wait_for:\n"
        "    span : time\n"
        "    do serial:\n"
        "        wait elapsed(span)\n"
        "scenario caller:\n"
        "    do serial:\n"
        "        call wait_for(period: 1 s)\n"
    )
    assert "E0406" in _errors(unknown)

    defaulted = _analyze(
        "action wait_for:\n"
        "    span : time = 100 ms\n"
        "    do serial:\n"
        "        wait elapsed(span)\n"
        "scenario caller:\n"
        "    do serial:\n"
        "        call wait_for()\n"
    )
    assert _errors(defaulted) == []


@pytest.mark.parametrize(
    "source",
    [
        "scenario s:\n    hero : vehicle with:\n        keep(5 m)\n"
        "    do serial:\n        wait elapsed(1s)\n",
        "scenario s:\n    do serial:\n        wait elapsed(5 m)\n",
        "scenario s:\n    var v : speed = 1kph\n    do serial:\n        wait v\n",
    ],
)
def test_boolean_and_duration_requirements(source: str) -> None:
    model = _analyze(source)
    assert "E0407" in _errors(model)


def test_struct_member_error_but_actor_member_warning() -> None:
    struct_model = _analyze(
        "struct p:\n    x : float\n"
        "scenario s:\n    var q : p\n    var z : float = q.y\n"
        "    do serial:\n        wait elapsed(1s)\n"
    )
    assert "E0403" in _errors(struct_model)

    actor_model = _analyze(
        "actor my_vehicle:\n    var x : speed\n"
        "scenario s:\n    v : my_vehicle\n    var z : length = v.unknown\n"
        "    do serial:\n        wait elapsed(1s)\n"
    )
    assert _errors(actor_model) == []
    assert "W0103" in _codes(actor_model)


def test_unknown_method_on_struct_is_an_error() -> None:
    model = _analyze(
        "struct p:\n    x : float\n"
        "scenario s:\n    var q : p\n    do serial:\n        q.wiggle()\n"
    )
    assert "E0403" in _errors(model)


def test_qualified_names_and_ambiguous_namespaces() -> None:
    qualified = _analyze(
        "namespace lib\n"
        "type foo is SI(m: 1)\n"
        "namespace demo\n"
        "scenario s:\n"
        "    var x : lib::foo = 1 m\n"
        "    do serial:\n        wait elapsed(1s)\n"
    )
    assert _errors(qualified) == []

    ambiguous = _analyze(
        "namespace a\n"
        "type foo is SI(m: 1)\n"
        "namespace b\n"
        "type foo is SI(m: 1)\n"
        "namespace demo use a, b\n"
        "scenario s:\n"
        "    var x : foo\n"
        "    do serial:\n        wait elapsed(1s)\n"
    )
    assert "E0206" in _errors(ambiguous)


def test_unknown_namespace_is_reported() -> None:
    model = _analyze(
        "use no.such\nscenario s:\n    do serial:\n        wait elapsed(1s)\n"
    )
    assert "E0205" in _errors(model)


def test_symbol_table_and_determinism() -> None:
    first = analyze(parse_file(SCENARIOS / "grammar_tour.osc"))
    second = analyze(parse_file(SCENARIOS / "grammar_tour.osc"))
    signature = lambda model: [
        (item.code, item.severity.value, item.span.line, item.span.column, item.message)
        for item in model.diagnostics
    ]
    assert signature(first) == signature(second)

    table = first.symbol_table()
    assert "demo" in table
    assert any(symbol["name"] == "cut_in" for symbol in table["demo"])
    assert any(symbol["name"] == "hero" for symbol in table["demo::cut_in"])


def test_cli_check_clean_and_strict(tmp_path: Path, capsys) -> None:
    clean = SCENARIOS / "smoke_use.osc"
    assert main(["check", str(clean)]) == 0
    captured = capsys.readouterr()
    assert "ok" in captured.out
    assert captured.err == ""

    strict = SCENARIOS / "grammar_tour.osc"
    assert main(["check", str(strict), "--strict"]) == 1
    captured = capsys.readouterr()
    assert "W0102" in captured.err


def test_cli_reports_semantic_errors(tmp_path: Path, capsys) -> None:
    path = tmp_path / "bad.osc"
    path.write_text(
        "scenario s:\n    var x : nonsense\n    do serial:\n        wait elapsed(1s)\n",
        encoding="utf-8",
    )
    assert main(["check", str(path)]) == 1
    captured = capsys.readouterr()
    assert "E0201" in captured.err


def test_cli_missing_import_warning(capsys) -> None:
    assert main(["check", str(SCENARIOS / "smoke.osc")]) == 0
    captured = capsys.readouterr()
    assert "W0101" in captured.err


def test_cli_loads_relative_imports(tmp_path: Path, capsys) -> None:
    (tmp_path / "lib.osc").write_text(
        "type my_length is SI(m: 1)\n"
        "unit myl of my_length is SI(m: 1, factor: 2)\n",
        encoding="utf-8",
    )
    main_file = tmp_path / "main.osc"
    main_file.write_text(
        'import "lib.osc"\n'
        "use stdtypes\n"
        "scenario s:\n"
        "    var d : my_length = 2 myl\n"
        "    do serial:\n"
        "        wait elapsed(1s)\n",
        encoding="utf-8",
    )
    assert main(["check", str(main_file)]) == 0
    captured = capsys.readouterr()
    assert "E0201" not in captured.err


def test_cli_stdlib_option(tmp_path: Path, capsys) -> None:
    stdlib_file = tmp_path / "library.osc"
    stdlib_file.write_text(
        "namespace stdtypes\n"
        "type my_length is SI(m: 1)\n"
        "unit myl of my_length is SI(m: 1, factor: 2)\n"
        "type time is SI(s: 1)\n"
        "unit s of time is SI(s: 1, factor: 1)\n",
        encoding="utf-8",
    )
    main_file = tmp_path / "main.osc"
    main_file.write_text(
        "use stdtypes\n"
        "scenario s:\n"
        "    var d : my_length = 2 myl\n"
        "    do serial:\n"
        "        wait elapsed(1s)\n",
        encoding="utf-8",
    )
    assert main(["check", str(main_file)]) == 1
    capsys.readouterr()
    assert main(["check", str(main_file), "--stdlib", str(stdlib_file)]) == 0
    captured = capsys.readouterr()
    assert "E0201" not in captured.err


def test_cli_dump_symbols_is_valid_json(capsys) -> None:
    assert main(["check", str(SCENARIOS / "smoke_use.osc"), "--dump-symbols"]) == 0
    captured = capsys.readouterr()
    table = json.loads(captured.out)
    assert "<global>" in table
    assert any(symbol["name"] == "s" for symbol in table["<global>"])


def test_cli_ast_missing_file(tmp_path: Path, capsys) -> None:
    missing = tmp_path / "missing.osc"
    assert main(["ast", str(missing)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert str(missing) in captured.err
    assert "Traceback" not in captured.err


def test_model_does_not_leak_into_carla() -> None:
    """The middle-end must stay importable without CARLA (architecture invariant)."""
    source = (Path(__file__).resolve().parents[1] / "src" / "osc2c" / "semantics").glob("*.py")
    for path in source:
        text = path.read_text(encoding="utf-8")
        assert "import carla" not in text


def test_enum_member_reference_copies_the_value() -> None:
    model = _analyze("enum size: [small = 3, medium = small, large]\n")
    enum = model.namespaces[""].lookup_local("size").type
    assert enum.members == {"small": 3, "medium": 3, "large": 4}


def test_unknown_enum_member_reference_is_reported() -> None:
    model = _analyze("enum size: [small, medium = missing]\n")
    assert "E0103" in _errors(model)


def test_range_declarator_resolves_to_a_range_type() -> None:
    model = _analyze(
        "use stdtypes\n"
        "scenario s:\n"
        "    gap : range of length = range(0 m, 10 m)\n"
        "    do serial:\n"
        "        emit DONE\n"
    )
    scenario = model.namespaces[""].lookup_local("s").type
    assert describe_type(scenario.fields["gap"].type) == "range of length"
    assert _errors(model) == []


def test_primitive_type_extension_is_reported_as_unexecuted() -> None:
    model = _analyze("extend int:\n    def twice() -> int is undefined\n")
    assert "W0106" in _codes(model)


def test_field_may_share_a_name_with_a_type() -> None:
    model = _analyze("struct position\nstruct wrapper:\n    position: position\n")
    assert _errors(model) == []
    wrapper = model.namespaces[""].lookup_local("wrapper").type
    assert describe_type(wrapper.fields["position"].type) == "position"


def test_modifier_and_type_may_share_a_name() -> None:
    model = _analyze("struct lane\nmodifier lane\n")
    assert _errors(model) == []


ROOT = Path(__file__).resolve().parents[1]
ASAM_STANDARD = ROOT / "external" / "asam" / "standard.osc"


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_asam_standard_library_has_no_diagnostics(capsys) -> None:
    assert main(["check", str(ASAM_STANDARD)]) == 0
    assert capsys.readouterr().err == ""


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_scenario_compiles_against_the_real_standard_library(capsys) -> None:
    scenario = ROOT / "scenarios" / "asam" / "asam_stdlib.osc"
    assert main(["check", str(scenario), "--stdlib", str(ASAM_STANDARD)]) == 0
    errors = [line for line in capsys.readouterr().err.splitlines() if "error" in line]
    assert errors == []


def _write_scenario(path: Path, body: str) -> Path:
    path.write_text(
        "use stdtypes\nuse std\n\nscenario s:\n    hero : vehicle\n\n"
        f"    do serial:\n        {body}\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_qualified_action_binds_to_the_actor(tmp_path: Path, capsys) -> None:
    scenario = _write_scenario(tmp_path / "call.osc", "hero.drive()")
    assert main(["check", str(scenario), "--stdlib", str(ASAM_STANDARD)]) == 0
    captured = capsys.readouterr()
    assert "unknown behavior" not in captured.err


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_qualified_action_checks_argument_types(tmp_path: Path, capsys) -> None:
    scenario = _write_scenario(tmp_path / "bad.osc", "hero.change_speed(target: 5)")
    assert main(["check", str(scenario), "--stdlib", str(ASAM_STANDARD)]) == 1
    assert "argument 'target' expects speed" in capsys.readouterr().err


def test_action_body_it_refers_to_the_receiver_actor() -> None:
    model = _analyze(
        "actor cruiser inherits vehicle\n"
        "action cruiser.cruise:\n"
        "    do serial:\n"
        "        it.drive() with:\n"
        "            speed(5 mps)\n"
        "scenario s:\n"
        "    c : cruiser\n"
        "    do serial:\n"
        "        c.cruise()\n"
    )
    assert _errors(model) == []
    assert "W0105" not in _codes(model)


@pytest.mark.skipif(
    not ASAM_STANDARD.exists(), reason="ASAM package not present under external/asam"
)
def test_standard_library_modifier_arguments_are_optional(
    tmp_path: Path, capsys
) -> None:
    scenario = _write_scenario(
        tmp_path / "modifier.osc", "hero.drive() with:\n            speed(10 mps)"
    )
    assert main(["check", str(scenario), "--stdlib", str(ASAM_STANDARD)]) == 0
    assert capsys.readouterr().err == ""
