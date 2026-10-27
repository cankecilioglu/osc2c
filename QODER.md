# QODER.md

## Project

Project name: **OSC2C** — OpenSCENARIO 2.1 → CARLA compiler (repository: https://github.com/cankecilioglu/osc2c).
A compiler that translates the OpenSCENARIO 2.1 DSL into py_trees behavior trees running in CARLA.
Paper: *Compiling OpenSCENARIO 2.1 for Scenario-Based Testing in CARLA* (arXiv:2604.16452).
This is a reproduction of the paper; it is not an official ASAM/CARLA product.

Status: Stage 0 (environment), Stage 1 (lexer/parser/typed AST), Stage 2 (symbol table, types, units), Stage 3 (runtime + behavior trees), Stage 4 (CARLA adapter + cut-in) and Stage 5 (validation + measurement) complete. Next: thesis (Stage 6).

## Commands

```bash
# at the project root
.venv/Scripts/activate

# fast tests (CARLA not required)
pytest -q

# tests that require CARLA only
pytest -m carla -q

# regenerate the grammar
python scripts/generate_parser.py

# dump the typed AST as JSON
osc2c ast scenarios/dev/smoke4.osc
osc2c ast scenarios/dev/smoke4.osc --spans

# semantic check (symbol table, type, unit)
osc2c check scenarios/dev/smoke4.osc
osc2c check scenarios/dev/smoke4.osc --strict
osc2c check scenarios/dev/smoke4.osc --dump-symbols
osc2c check scenarios/dev/smoke4.osc --stdlib path/to/types.osc

# behavior tree and mock run
osc2c bt scenarios/dev/stage3_sync.osc
osc2c run scenarios/dev/stage3_sync.osc --ticks 200 --dt 0.1 --trace

# cut-in on a real CARLA server (the server must be listening on port 2000)
osc2c run scenarios/carla/cut_in.osc --carla --map Town10HD_Opt --spawn-index 20 --ticks 300 --trace

# validation/measurement (without CARLA)
python tools/bench.py --mode mock --repeat 20 --compile-repeat 20 \
  --json docs/measurements/mock.json --markdown docs/measurements/mock.md
python tools/coverage.py --json docs/measurements/coverage.json \
  --markdown docs/measurements/coverage.md

# CARLA cut-in measurement with 20 repetitions (the server must be running)
python tools/bench.py --mode carla --carla-repeat 20 \
  --json docs/measurements/carla.json --markdown docs/measurements/carla.md

# control group without the compiler
python tools/baseline_carla.py --repeat 5 --json docs/measurements/baseline_carla.json

# refresh the golden ASTs after an intentional change
# (Git Bash) UPDATE_GOLDEN=1 pytest -q
```

On Windows, `python` may resolve to the Store alias; use `.venv\Scripts\python.exe` inside the venv.

## Semantic layer

- Two passes: **definition** (register everything in its scope) → **resolution** (bind types, resolve inheritance, check bodies).
- Physical types are represented by an 8-tuple of SI dimensions; unit compatibility is checked by dimension equality.
- ASAM `types.osc` / `domain.osc` are not in the repository. `semantics/stdlib.py` provides a built-in subset; with `--stdlib` an external file takes precedence.
- Diagnostic codes are stable: `E01xx` definition, `E02xx` type/expression, `E03xx` inheritance/extension, `E04xx` name/call, `W01xx` warning.
- Warning policy: an undefined method on an actor/scenario/action is `W0105` (it may be an external field); the same situation on a struct is `E0403` (a hard error).

## Backend and runtime

- `serial` → `Sequence(memory=True)`, `parallel` → `Parallel(SuccessOnAll)`, `one_of` → `Parallel(SuccessOnOne)`.
- `Selector` is not used for `one_of`: `Selector` stops at the first `RUNNING` child and never ticks the remaining alternatives; the `drive` + `wait` race in the paper only works with `SuccessOnOne`.
- `drive`/`walk` are durative behaviors and return `RUNNING`; the other atomic actions return `SUCCESS` once the command is accepted.
- Events are latched on the blackboard; `rise`/`fall` only record the first observation and trigger on the next change.
- Expressions are evaluated in SI units; `UnitInfo.to_si` is the single conversion point.
- `MockAdapter` is the default simulator; `osc2c bt`/`run` do not require CARLA.
- Unsupported behavior is not silently ignored: compiler warning + `UnsupportedLeaf` (FAILURE).

## CARLA adapter

- `ScenarioInitializer` applies the `at: start` actions (`assign_position`, `change_lane`, `change_speed`, `set_lights`, `assign_celestial_position`) once at compile time; in the tree these nodes become `Success`. `drive`/`walk` are not executed at start.
- The adapter uses synchronous mode + fixed delta; because spawn/teleport are only processed by `world.tick()`, the adapter ticks at those points.
- Spawn points are ordered by `_left_lane_horizon` (0/20/40/60 m of left-lane visibility); `--spawn-index` shifts the starting point in that order, and occupied points are skipped.
- `ahead_of` is computed by projection onto the forward vector, not from the `waypoint.s` difference; on some roads `s` decreases along the direction of travel.
- `change_lane` completes with the target lane ID + approach to within 0.7 m of the lane center + at least 0.4 s; it times out at 6 s. Because the road ID changes at junctions, it is not used on its own.
- Steering is produced every tick by pure pursuit toward the `waypoint.next()` target; a short lookahead distance is used during lane changes. `VehicleControl` is built from scratch every tick (`reverse=False`), because `get_control()` returns some fields uninitialized.
- `close()` destroys the actors, ticks, and then restores settings/weather; it is idempotent.

## Validation and measurement

- `src/osc2c/validation.py` uses the compiler's **public entry points** (the same path as the CLI); there are no private shortcuts for measurement.
- Trace hash: at every tick the actors' `s`, lane, speed, lights and `x/y/z` values are rounded to 6 decimals, written to ordered JSON and hashed with SHA-256. The hashes of the 20 repetitions are compared.
- KPIs: minimum Euclidean distance, minimum TTC, collision count, the lateral/heading/`ahead_of` values at the cut-in moment, and the geometry threshold.
- `src/osc2c/coverage.py` keeps 43 capability rows with status + evidence path + rationale; `validate_matrix()` rejects an invalid status, a non-existent evidence path/test function, and a duplicate row.
- `tools/bench.py`, `tools/coverage.py` and `tools/baseline_carla.py` are outside the package; the baseline imports `carla` directly, an exception that preserves the rule only for `src/osc2c/adapters/carla.py`.
- Results (2026-10-26): mock 5/5 SUCCESS with a single hash per scenario; CARLA 20/20 SUCCESS, 20/20 geometry, single hash; tick median 5.45 ms, baseline full loop 5.38 ms; coverage 24 supported / 10 partial / 9 unsupported.
- The first CARLA run shows ~4 s of compilation due to warm-up; the report uses the median/steady state. Details: `docs/VALIDATION.md`.

## Architectural invariants

- **The frontend knows nothing about semantics.** The parser produces syntax only; type/scope resolution happens in the middle-end.
- **The middle-end annotates the AST.** The symbol table, types and units are resolved here; there is no CARLA import.
- **The CARLA import lives only in `src/osc2c/adapters/carla.py`.** Other modules use the `SimAdapter` interface.
- **The mock adapter is the backbone of the tests.** Tests that run without CARLA are the default; CARLA tests use `@pytest.mark.carla`.
- **The generated parser is never edited by hand.** `src/osc2c/frontend/generated/` is ANTLR output; changes are made in `grammar/openscenario2.g4`.
- **For every new OSC2 construct:** a positive parse test + a negative semantic test + (if applicable) a golden BT test.

## Grammar and license

- `grammar/openscenario2.g4` is derived from the PMSF py-osc2 grammar (MPL-2.0).
- Additions: top-level `use`, physical literals with a space (`35 kph`), compound unit expressions (`m/s`, `m/s^2`), and a fix for `enum_member_value`.
- The grammar and the generated parser are under MPL-2.0; details are in the `NOTICE` file.
- The ASAM 2.2.0 package is kept locally under `external/asam/` and is covered by `.gitignore`; although redistribution is permitted, it was not added to the repository. Tests are skipped with `skipif` when the files are absent.

## Tests and completeness

- Tests must be green with `pytest -q` (169 mock/validation tests); CARLA tests are in a separate marker (3 tests, `pytest -m carla -q`; 172 total).
- CARLA tests are `skip`ped when no server is present; the default suite does not require a server.
- Golden AST/BT files represent the actual output; they are updated when a change is intentional.
- A new feature = code + test + documentation. A feature without a test is not considered done.

## Learning

- `docs/STAGES.md`: stage-by-stage concepts, outputs, and self-test questions.
- `docs/VALIDATION.md`: Stage 5 measurement results, method, limitations.
- `docs/SCOPE_AUDIT.md`: planned vs. actual scope comparison, deferred items, and audit corrections.
- `docs/GRAMMAR_GAPS.md`: per-construct support/gap tables and the remaining prioritized work.
- `docs/GRAMMAR_DIFF_2.2.md`: ASAM 2.2.0 EBNF ↔ project grammar comparison, closed gaps, and remaining semantic limits.
- `PROJECT_PLAN.md`: schedule, scope and risks.
- `ENVIRONMENT.md`: installed tools, paths and setup commands.
