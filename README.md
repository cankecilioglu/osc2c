# OSC2C — OpenSCENARIO 2.1 → CARLA Compiler

OSC2C is an open-source compiler that translates the ASAM OpenSCENARIO 2.1 DSL into py_trees behavior trees that run in the CARLA simulator. It is an independent, paper-based reimplementation of the architecture described in *Compiling OpenSCENARIO 2.1 for Scenario-Based Testing in CARLA* (arXiv:2604.16452). The paper does not publish its implementation; every component in this repository was built from scratch and is validated against executable scenarios.

**Author:** Can Kecilioglu  
**Repository:** https://github.com/cankecilioglu/osc2c  
**Paper:** *Compiling OpenSCENARIO 2.1 for Scenario-Based Testing in CARLA* — Thoshitha Gamage, Lasanthi Gamage (arXiv:2604.16452, April 2026)  
**Status:** Stages 0 (environment), 1 (lexer/parser/AST), 2 (semantics), 3 (runtime + behavior trees), 4 (CARLA adapter + cut-in), 5 (validation + measurement) and 5.7 (user-defined modifier expansion) are complete.  
**Target:** thesis submission by 31 January 2027 (Stage 6).

The Python package and the CLI are both named `osc2c`.

## Quick start

```bash
git clone https://github.com/cankecilioglu/osc2c.git
cd osc2c
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash; use `.venv/bin/activate` on Linux/macOS
pip install -e .
pytest -q
osc2c ast scenarios/dev/smoke4.osc
osc2c check scenarios/dev/smoke4.osc
osc2c bt scenarios/dev/stage3_sync.osc
osc2c run scenarios/dev/stage3_sync.osc --ticks 200 --trace

# cut-in on the real simulator while the CARLA server is running
osc2c run scenarios/carla/cut_in.osc --carla --map Town10HD_Opt --spawn-index 20 --ticks 300 --trace
pytest -m carla -q

# validation and measurement without CARLA
python tools/bench.py --mode mock --repeat 20 --compile-repeat 20 \
  --json docs/measurements/mock.json --markdown docs/measurements/mock.md
python tools/coverage.py --markdown docs/measurements/coverage.md
```

`osc2c check` resolves the symbol table, types and units, and reports errors with stable codes (`E0401`, `E0301`, ...). `--strict` turns warnings into errors, `--dump-symbols` prints the symbol table as JSON, and `--stdlib FILE` loads an external ASAM type library.

`osc2c bt` prints the compiled behavior tree as JSON. `osc2c run` executes the same tree on the deterministic `MockAdapter` and reports events and actor state.

The ASAM 2.2.0 package (`grammar.ebnf`, `types.osc`, `domain.osc`, `standard.osc`) is kept locally under `external/asam/`, which is excluded from version control. `--stdlib external/asam/standard.osc` loads the real library through its import chain; without it, the built-in `stdtypes` / `std` subset in `semantics/stdlib.py` is used. Tests that depend on the real library are skipped when the files are absent.

## Behavior-tree mapping

| OSC2 | py_trees | Note |
| --- | --- | --- |
| `serial` | `Sequence(memory=True)` | sequential; a successful child is not re-run |
| `parallel` | `Parallel(SuccessOnAll)` | succeeds when every branch has finished |
| `one_of` | `Parallel(SuccessOnOne)` | not `Selector`, so the running branch is not left open |
| `drive` / `walk` | durative leaf | applies the target speed every tick and stays `RUNNING` |
| `wait elapsed/rise/fall/@event` | condition leaf | `rise`/`fall` detect real edges |
| `emit` | blackboard event | events are latched |

A durative `drive` never finishes by itself inside a `serial`; it must be terminated by `one_of` or a `wait`. This matches the phase structure of Listing 2 in the paper.

User-defined modifiers are flattened into standard applications at compile time: `modifier fast of vehicle: speed(10 mps)` behaves like `speed(10 mps)` in `hero.drive() with: fast()`. The same expansion applies to qualified action bodies and to `at: start` hoisting; source order is preserved, and cycles or unsupported body members are reported as warnings (`src/osc2c/backend/modifiers.py`).

## Running on CARLA

Everything runs on the `MockAdapter` without a CARLA server unless `--carla` is supplied. With the real simulator:

- The adapter enables synchronous mode and a fixed `fixed_delta_seconds`, restores the previous settings/weather on shutdown, and destroys the actors it created.
- Actors are matched by `role_name`. Map spawn points are ranked by a long forward view in the same-direction left lane, and `--spawn-index` selects the starting point in that order; occupied spawn points are skipped.
- `assign_position` supports relative `ahead_of`/`behind` plus `distance`, and `lane(side_of:)` combinations. `at: start` actions are applied once during compilation and replaced by a successful leaf in the tree.
- `change_lane` completes when both the target lane id and proximity to the lane center (0.7 m) are satisfied; it is not used alone because the road id changes at junctions.
- Supported vehicle blueprints are `tesla.model3` and `lincoln.mkz_2017`; the default map is the server's current map.

`scenarios/carla/cut_in.osc` drives the hero at a constant 12 m/s while forcing the NPC in the left lane to change into the right lane after 2 s; the hero brakes after the `CUT_IN` event. It runs for 41 ticks (4.0 s) on the mock and is validated geometrically on CARLA (`tests/test_carla.py`).

## Validation and measurement

`docs/VALIDATION.md` contains the mock results for five scenarios, 20-repetition determinism tests, compile/tick latencies, CARLA cut-in KPIs, and the coverage matrix prepared for Table 2 of the paper. Raw data is stored under `docs/measurements/`.

- **Determinism:** the same scenario, settings and step size produce the same SHA-256 trace hash from tick-by-tick actor state. The mock is bitwise deterministic for 5/5 scenarios. On CARLA, behavior and geometry are identical across 20/20 repeated runs; the trace hash is usually identical, but physics noise (for example a 6×10⁻⁶ m/s speed difference) can change it, so "always the same hash" is not claimed for CARLA.
- **Coverage:** 43 capability rows → 24 supported, 10 partial, 9 unsupported (strict 56%, weighted 67%). Every row is tied to a runnable evidence file.
- **Cost:** on CARLA the tick median is 5.45 ms; the full loop of the compiler-free baseline is 5.38 ms. Compile steady-state is about 130 ms (parser-dominated).

`tools/bench.py` runs the mock/CARLA measurements, `tools/coverage.py` builds the coverage matrix, and `tools/baseline_carla.py` runs the compiler-free control group.

## Project layout

```text
grammar/                     OSC 2.1 ANTLR grammar (MPL-2.0 derivative)
tools/                       ANTLR 4.13.2 jar
src/osc2c/frontend/          parser, AST, transformer
src/osc2c/semantics/         symbol table, types, units
src/osc2c/backend/           behavior-tree generation, MethodRegistry
src/osc2c/runtime/           ExecutionContext, events, atomic behaviors
src/osc2c/adapters/          SimAdapter, CarlaAdapter, MockAdapter
src/osc2c/validation.py      determinism, latency and KPI harness
src/osc2c/coverage.py        evidence-backed capability matrix
scenarios/                   .osc scenarios (dev/ for mock, carla/ for the real server)
tests/                       unit + golden + end-to-end + validation tests
tools/                       ANTLR jar, bench, coverage, CARLA baseline
docs/                        stages, validation report, measurements
external/                    CARLA installation (not tracked)
```

## Documentation

- [PROJECT_PLAN.md](PROJECT_PLAN.md) — scope, 14-week schedule, risks
- [ENVIRONMENT.md](ENVIRONMENT.md) — installed tools and paths
- [docs/STAGES.md](docs/STAGES.md) — learning path and stages
- [docs/VALIDATION.md](docs/VALIDATION.md) — Stage 5 validation and measurement report
- [docs/SCOPE_AUDIT.md](docs/SCOPE_AUDIT.md) — planned vs. actual scope and deferrals
- [docs/GRAMMAR_GAPS.md](docs/GRAMMAR_GAPS.md) — support/gap tables by language construct
- [docs/GRAMMAR_DIFF_2.2.md](docs/GRAMMAR_DIFF_2.2.md) — ASAM 2.2.0 EBNF ↔ project grammar comparison
- [docs/measurements/](docs/measurements/) — raw JSON/Markdown measurements

## Citation

If you use OSC2C in academic work, please cite the paper it reimplements:

```bibtex
@misc{gamage2026osc2carla,
  title         = {Compiling OpenSCENARIO 2.1 for Scenario-Based Testing in CARLA},
  author        = {Gamage, Thoshitha and Gamage, Lasanthi},
  year          = {2026},
  eprint        = {2604.16452},
  archivePrefix = {arXiv},
  url           = {https://arxiv.org/abs/2604.16452}
}
```

A machine-readable citation is available in [CITATION.cff](CITATION.cff).

## License

The original code and documentation in this repository are licensed under the **MIT License**. Copyright (c) 2026 Can Kecilioglu. See [LICENSE](LICENSE).

Third-party components keep their own licenses:

- `grammar/openscenario2.g4` and the generated parser files are distributed under the **Mozilla Public License 2.0 (MPL-2.0)**. They are derived from the PMSF py-osc2 grammar; see [NOTICE](NOTICE) and [LICENSES/MPL-2.0.txt](LICENSES/MPL-2.0.txt).
- `tools/antlr-4.13.2-complete.jar` is distributed under the **BSD-3-Clause** license.
- Runtime dependencies (`antlr4-python3-runtime`, `py_trees`, `numpy`) are installed from PyPI and are not vendored.

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for details.

The ASAM OpenSCENARIO 2.2.0 standard files under `external/asam/` are **not redistributed** by this repository; users must obtain them under the terms of the ASAM license. The CARLA simulator and the referenced paper are likewise not redistributed.
