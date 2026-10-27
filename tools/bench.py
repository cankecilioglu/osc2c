"""Run mock/CARLA validation measurements and write JSON/Markdown output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from osc2c.validation import render_summary, run_carla_suite, run_mock_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bench", description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("mock", "carla", "all"),
        default="mock",
        help="which suite to run (default: mock)",
    )
    parser.add_argument("--repeat", type=int, default=20, help="mock repetitions")
    parser.add_argument(
        "--compile-repeat", type=int, default=10, help="compile repetitions per scenario"
    )
    parser.add_argument(
        "--carla-repeat", type=int, default=20, help="CARLA cut-in repetitions"
    )
    parser.add_argument("--dt", type=float, default=0.1, help="mock step seconds")
    parser.add_argument(
        "--carla-dt", type=float, default=0.05, help="CARLA fixed delta seconds"
    )
    parser.add_argument("--ticks", type=int, default=500, help="maximum ticks")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--map", dest="map_name", default="Town10HD_Opt")
    parser.add_argument("--spawn-index", type=int, default=20)
    parser.add_argument("--json", type=Path, help="write the full result JSON here")
    parser.add_argument("--markdown", type=Path, help="write a summary table here")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result: dict[str, object] = {}
    if args.mode in {"mock", "all"}:
        result["mock"] = run_mock_suite(
            repeat=args.repeat,
            compile_repeat=args.compile_repeat,
            dt=args.dt,
            max_ticks=args.ticks,
        )
    if args.mode in {"carla", "all"}:
        try:
            result["carla"] = run_carla_suite(
                repeat=args.carla_repeat,
                host=args.host,
                port=args.port,
                map_name=args.map_name,
                spawn_index=args.spawn_index,
                dt=args.carla_dt,
                max_ticks=args.ticks,
            )
        except Exception as error:  # noqa: BLE001 - report connection failures
            print(f"CARLA measurement failed: {error}", file=sys.stderr)
            return 2

    text = json.dumps(result, indent=2)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8", newline="\n")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(
            render_summary(result), encoding="utf-8", newline="\n"
        )
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
