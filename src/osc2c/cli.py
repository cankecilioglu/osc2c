"""Command line entry point: `osc2c ast|check|bt|run ...`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from osc2c.backend import CompilationError, compile_scenario
from osc2c.frontend.ast import CompilationUnit, ImportDecl
from osc2c.frontend.parser import ParseError, parse_file
from osc2c.semantics import SemanticModel, analyze


def _cmd_ast(args: argparse.Namespace) -> int:
    try:
        unit = parse_file(args.path)
    except ParseError as error:
        print(error, file=sys.stderr)
        return 1
    except OSError as error:
        print(f"{args.path}: {error}", file=sys.stderr)
        return 1
    json.dump(unit.to_dict(include_spans=args.spans), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _load_unit(
    path: Path,
    seen: dict[Path, CompilationUnit],
    units: list[CompilationUnit],
    missing: list[ImportDecl],
) -> CompilationUnit:
    resolved = path.resolve()
    if resolved in seen:
        return seen[resolved]
    unit = parse_file(path)
    seen[resolved] = unit
    for import_decl in unit.imports:
        if not import_decl.is_path:
            continue
        target = (path.parent / import_decl.reference).resolve()
        if not target.exists():
            missing.append(import_decl)
            continue
        _load_unit(target, seen, units, missing)
    units.append(unit)
    return unit


def _analyze_path(
    path: Path,
    stdlib: list[str],
) -> tuple[SemanticModel, Path, list[ImportDecl]]:
    units: list[CompilationUnit] = []
    missing: list[ImportDecl] = []
    seen: dict[Path, CompilationUnit] = {}
    for stdlib_path in stdlib:
        _load_unit(Path(stdlib_path), seen, units, missing)
    main_unit = _load_unit(path, seen, units, missing)
    extras = [unit for unit in units if unit is not main_unit]
    model = analyze(main_unit, extras, builtin_stdlib=not stdlib)
    for import_decl in missing:
        model.diagnostics.warning(
            "W0101",
            f"imported file '{import_decl.reference}' was not found",
            import_decl.span,
        )
    return model, path, missing


def _cmd_check(args: argparse.Namespace) -> int:
    main_path = Path(args.path)
    try:
        model, main_path, _ = _analyze_path(main_path, args.stdlib)
    except ParseError as error:
        print(error, file=sys.stderr)
        return 1
    except OSError as error:
        print(f"{args.path}: {error}", file=sys.stderr)
        return 1

    for diagnostic in model.diagnostics.sorted():
        print(diagnostic.format(), file=sys.stderr)
    if args.dump_symbols:
        json.dump(
            model.symbol_table(include_builtin=args.include_builtins),
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")

    failed = model.diagnostics.has_errors or (
        args.strict and bool(model.diagnostics.warnings)
    )
    if not failed and not model.diagnostics.items and not args.dump_symbols:
        print(f"{main_path}: ok")
    return 1 if failed else 0


def _compile_from_args(args: argparse.Namespace, adapter=None):
    try:
        model, _, _ = _analyze_path(Path(args.path), args.stdlib)
    except ParseError as error:
        print(error, file=sys.stderr)
        return None
    except OSError as error:
        print(f"{args.path}: {error}", file=sys.stderr)
        return None
    for diagnostic in model.diagnostics.sorted():
        print(diagnostic.format(), file=sys.stderr)
    if model.diagnostics.has_errors:
        return None
    try:
        return compile_scenario(model, adapter=adapter, scenario_name=args.scenario)
    except CompilationError as error:
        print(f"{args.path}: {error}", file=sys.stderr)
        return None


def _cmd_bt(args: argparse.Namespace) -> int:
    compiled = _compile_from_args(args)
    if compiled is None:
        return 1
    for warning in compiled.warnings:
        print(f"{args.path}: warning: {warning}", file=sys.stderr)
    json.dump(compiled.to_dict(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _make_adapter(args: argparse.Namespace):
    if not args.carla:
        return None
    from osc2c.adapters.carla import CarlaAdapter

    fixed_delta = args.fixed_delta if args.fixed_delta is not None else args.dt
    adapter = CarlaAdapter(
        host=args.host,
        port=args.port,
        map_name=args.map,
        spawn_index=args.spawn_index,
        fixed_delta_seconds=fixed_delta,
    )
    print(
        f"CARLA {adapter.client.get_server_version()} "
        f"({adapter.map.name}) at {args.host}:{args.port}",
        file=sys.stderr,
    )
    return adapter


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        adapter = _make_adapter(args)
    except Exception as error:
        print(f"CARLA connection failed: {error}", file=sys.stderr)
        return 1
    try:
        compiled = _compile_from_args(args, adapter=adapter)
        if compiled is None:
            return 1
        for warning in compiled.warnings:
            print(f"{args.path}: warning: {warning}", file=sys.stderr)
        result = compiled.run(max_ticks=args.ticks, dt=args.dt)
        if args.trace:
            for record in result.trace:
                print(f"{record.time:6.2f}s  {record.name}", file=sys.stderr)
        json.dump(result.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if result.succeeded else 1
    finally:
        if adapter is not None:
            adapter.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="osc2c", description="OpenSCENARIO 2.1 to CARLA compiler")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ast_cmd = subparsers.add_parser("ast", help="print the typed AST as JSON")
    ast_cmd.add_argument("path", type=Path)
    ast_cmd.add_argument("--spans", action="store_true", help="include source spans")
    ast_cmd.set_defaults(func=_cmd_ast)

    check_cmd = subparsers.add_parser("check", help="run semantic analysis and print diagnostics")
    check_cmd.add_argument("path", type=Path)
    check_cmd.add_argument(
        "--stdlib",
        action="append",
        default=[],
        metavar="FILE",
        help="additional OSC file with standard-library declarations (repeatable)",
    )
    check_cmd.add_argument("--strict", action="store_true", help="treat warnings as errors")
    check_cmd.add_argument("--dump-symbols", action="store_true", help="print the symbol table as JSON")
    check_cmd.add_argument(
        "--include-builtins",
        action="store_true",
        help="include built-in stdlib symbols in --dump-symbols",
    )
    check_cmd.set_defaults(func=_cmd_check)

    bt_cmd = subparsers.add_parser("bt", help="compile a scenario to a behavior-tree snapshot")
    bt_cmd.add_argument("path", type=Path)
    bt_cmd.add_argument("--scenario", help="scenario declaration to compile")
    bt_cmd.add_argument(
        "--stdlib",
        action="append",
        default=[],
        metavar="FILE",
        help="additional OSC file with standard-library declarations (repeatable)",
    )
    bt_cmd.set_defaults(func=_cmd_bt)

    run_cmd = subparsers.add_parser(
        "run", help="run a scenario against the mock or CARLA adapter"
    )
    run_cmd.add_argument("path", type=Path)
    run_cmd.add_argument("--scenario", help="scenario declaration to run")
    run_cmd.add_argument("--ticks", type=int, default=200, help="maximum ticks")
    run_cmd.add_argument("--dt", type=float, default=0.1, help="seconds per tick")
    run_cmd.add_argument("--trace", action="store_true", help="print emitted events to stderr")
    run_cmd.add_argument(
        "--stdlib",
        action="append",
        default=[],
        metavar="FILE",
        help="additional OSC file with standard-library declarations (repeatable)",
    )
    run_cmd.add_argument(
        "--carla",
        action="store_true",
        help="run against a live CARLA server instead of the mock adapter",
    )
    run_cmd.add_argument("--host", default="127.0.0.1", help="CARLA host")
    run_cmd.add_argument("--port", type=int, default=2000, help="CARLA RPC port")
    run_cmd.add_argument("--map", help="CARLA map to load (e.g. Town10HD_Opt)")
    run_cmd.add_argument(
        "--spawn-index", type=int, default=0, help="first map spawn point to try"
    )
    run_cmd.add_argument(
        "--fixed-delta",
        type=float,
        default=None,
        help="CARLA fixed delta seconds (defaults to --dt)",
    )
    run_cmd.set_defaults(func=_cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
