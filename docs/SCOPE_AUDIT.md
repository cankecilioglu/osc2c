# Scope Audit — 26 October 2026

This document compares the Must/Should items in `PROJECT_PLAN.md` with the code,
tests and measurements actually delivered at the end of Stage 5. The aim is not
to hide gaps but to make each item's status, evidence and rationale for
deliberate deferral traceable.

## 1. Audit method

- `PROJECT_PLAN.md`, `ENVIRONMENT.md`, `README.md`, `QODER.md`, `docs/STAGES.md`
  and `docs/VALIDATION.md` were read end to end.
- An inventory was produced of the frontend, semantics, backend, runtime, adapters,
  validation and coverage modules under `src/osc2c/`, plus `tools/` and `tests/`.
- `pytest -q -m "not carla"`, `pytest -q -m carla`, `pip check` and
  `python -m compileall` were run.
- How deferred constructs appear to the user was exercised with small sources
  (the diagnostic codes in the table below are taken from actual output).

Conclusion: the Stage 5 submission is in working order; apart from the "deferred"
items below, the plan's Must scope is met. Deferred items are not silently
swallowed; they produce a diagnostic or a compile warning.

## 2. Must items

| Area | Item | Status | Evidence / note |
|---|---|---|---|
| Frontend | `import`, `use`, `scenario` | Done | Parser + CLI; local ASAM files are bound with `--stdlib` |
| Frontend | `vehicle`, `environment` actors | Done | Mock and CARLA adapters |
| Frontend | `stationary_object`, `map` | Deferred | If used, `E0201 unknown type`; requires separate spawn/road semantics |
| Frontend | `keep(...)` | Partial | `keep(it.<field> == value)` is enforced; other boolean keeps are validated, not enforced, and produce a compile warning |
| Frontend | `var`, physical units | Done | `kph`, `mph`, `m/s`, `m`, `s`, `deg`, `rad`; converted to SI |
| Frontend | `with` modifiers | Partial | `speed`, `lane`, `position` work; `rate_profile` → `W0104` |
| Frontend | `serial`, `parallel`, `one_of` | Done | Golden BT tests |
| Frontend | `wait`, `rise`, `fall`, `elapsed`, `emit`, `@event` | Done | Blackboard and edge detection tests |
| Frontend | Diagnostics with source locations | Done | `E01xx`–`E04xx`, `W010x` codes |
| Semantics | Nested scopes, two passes | Done | `semantics/builder.py`; symbol table tests |
| Semantics | Inheritance | Done | `vehicle → traffic_participant` |
| Semantics | Physical type/unit system | Done | `PhysicalTypeInfo`, `UnitInfo` |
| Semantics | `stdtypes` / `domain.osc` fallback | Done | Minimal built-in stdlib + `--stdlib` |
| Semantics | Positive/negative tests | Done | `tests/test_semantics.py` |
| Backend | Expression evaluator | Done | `runtime/context.py`; with SI units |
| Backend | Actor lookup | Done | Adapter dictionaries O(1) |
| Backend | `ahead_of` / Euclidean distance | Partial | `position.ahead_of()`, `position.euclidean()`; the ASAM name `object_distance(direction: euclidean)` is absent → `E0402` |
| Backend | `rise` / `fall` / event blackboard | Done | `runtime/blackboard.py`, `WaitLeaf` |
| Backend | py_trees `Sequence`, `Parallel`, `SuccessOnOne` | Done | `backend/compiler.py` |
| Backend | Automatic timeout wrappers | Deferred | `wait elapsed(...)` can be used manually in the scenario |
| Backend | `drive` / lane following | Partial | Follows the lane center; no explicit waypoint/path API |
| Backend | `change_speed` | Partial | Proportional throttle/brake; no PID |
| Backend | `change_lane` | Done | OpenDRIVE lane offsets; completion measurement in CARLA |
| Backend | `assign_position` | Done | Lane, relative and absolute modes |
| Backend | `set_lights` | Done | An unknown mode now raises `ValueError` |
| Backend | `assign_celestial_position` | Done | Azimuth/elevation applied by the adapter |
| Backend | `ScenarioInitializer` three placement modes | Done | `at: start` actions at compile time |
| Backend | `role_name` mapping | Done | CARLA blueprint attribute |
| CARLA | Synchronous mode, fixed step | Done | `fixed_delta_seconds` |
| CARLA | Vehicle spawn/teleport | Done | `CarlaAdapter`; pedestrian/static object deferred |
| CARLA | Cut-in scenario | Done | 20/20 runs, geometry and KPI test |
| CARLA | Demo video | Submission stage | Outside code scope |
| Validation | 5 scenarios mock e2e | Done | `tests/test_validation.py` |
| Validation | 1 scenario CARLA e2e | Done | `tests/test_carla.py`, `@pytest.mark.carla` |
| Validation | Determinism over 20 repetitions | Done | SHA-256 trace hash, single hash |
| Validation | Compile/tick measurement | Done | `src/osc2c/validation.py`, `tools/bench.py` |
| Validation | Table 2 coverage matrix | Done | 43 rows, evidence-validated |

## 3. Should items

| Item | Status | Note |
|---|---|---|
| Weather, traffic lights | Not done | The adapter saves/restores weather; no OSC behavior |
| `follow_path`, `follow_trajectory` | Not done | `unsupported` in the coverage matrix |
| Time gap / space gap / headway | Partial | Spatial `ahead_of` and projection exist; no time gap |
| Orientation modifiers | Partial | Yaw only (`h`); no pitch/roll |
| Hand-written CARLA baseline | Done | `tools/baseline_carla.py`, results in `docs/measurements/` |
| ScenarioRunner comparison | Deferred | Thesis-period option |

## 4. Deliverable (D8) items

| Item | Status | Note |
|---|---|---|
| README, installation, validation report | Done | This repository |
| Tests and reproducible measurements | Done | 169 non-CARLA + 3 CARLA tests |
| `LICENSE` | Done | MIT license present (Copyright (c) 2026 Can Kecilioglu) |
| CI (GitHub Actions) | Pending | At submission stage |
| Demo video | Pending | At submission stage |
| Public `v0.1` tag | Pending | After publication |

## 5. How deferred items appear to the user

A deferred construct is not silently ignored:

| Usage | Result |
|---|---|
| `box : stationary_object` | `E0201 unknown type 'stationary_object'` |
| `m : map` | `E0201 unknown type 'map'` |
| `rate_profile()` alongside `speed(...)` | `W0104 unknown modifier 'rate_profile'` |
| `object_distance(...)` | `E0402 unknown method or behavior` |
| Unsupported behavior (e.g. `fly()`) | Compile warning + `FAILED` leaf, `unsupported` list at run time |
| Unsupported `keep` form | Compile warning; the constraint is validated but not enforced |

Note: this table describes the built-in subset mode. When the real ASAM
2.2.0 library is loaded with `--stdlib`, `stationary_object` and `map` resolve;
the `rate_profile`/`object_distance` errors then stem from the call form and
context (see [`GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) §4).

## 6. Fixed in this audit

1. **The coverage matrix was made honest.** The combined "Move / drive / walk"
   row was split into `Drive` (supported) and `Walk` (partial); pedestrian
   `walk` behavior was tested in the mock adapter
   (`test_pedestrian_walk_moves_actor`). Because pedestrians are not spawned in
   CARLA, the row is now `partial`.
2. **Matrix validation was strengthened.** `validate_matrix()` now also rejects
   duplicate rows and non-existent test functions; evidence is now tied to the
   actual test symbol, not just a file path.
3. **The CLI error path was fixed.** `osc2c ast nonexistent.osc` now returns `1`
   without a traceback and prints a clean error message.
4. **The unused `numpy` dependency was removed**; `requires-python` was set
   to 3.12.
5. **`.gitignore` was completed:** `*.egg-info/`, `stdlib/`, `.coverage.*`,
   `coverage.xml`.
6. **The CARLA adapter was made consistent.** The old "stage 4" message was
   removed; an unknown light mode no longer silently becomes `NONE` but raises
   `ValueError`.
7. **Unsupported `keep` forms are reported.** Constraints that are validated but
   not enforced become compile warnings.
8. **Documentation was synchronized.** The 42/23/10/9, 55%/67% and 103-test
   values in README, QODER, STAGES, VALIDATION and PROJECT_PLAN were replaced
   with current results; references to Python 3.11, `py-osc2`, `numpy`,
   `Town06`, `osc2parser` and `scripts/fetch_stdlib.py` in the plan were
   corrected.

## 7. Verification

```bash
./.venv/Scripts/python.exe -m pytest -q -m "not carla"
./.venv/Scripts/python.exe -m pytest -q -m carla
./.venv/Scripts/python.exe tools/coverage.py --json docs/measurements/coverage.json --markdown docs/measurements/coverage.md
./.venv/Scripts/python.exe -m pip check
```

Expected:

- 169 non-CARLA tests + 3 CARLA tests green.
- Coverage matrix: 43 rows, 24 supported, 10 partial, 9 unsupported
  (strict 56%, weighted 67%), `validate_matrix()` empty list.
- `pip check`: no broken dependencies.

CARLA tests run only while the server is up; the default package does not
require a server.

## 8. Remaining risks and next steps

1. **The grammar gap analysis is complete** (plan task W2); details are in
   [`docs/GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) and
   [`docs/GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md). A mechanical diff against
   the ASAM 2.2.0 grammar and library was performed; three syntax gaps were
   closed. Remaining limits: compound units containing `*` (`kg*m/s^2`) and
   binding of dotted behavior names to the target type (`hero.drive()` →
   `W0105`).
2. **Action bodies are compiled.** `call action(...)` now works with
   parameter/scope management; positional/named arguments, defaults and actor
   parameters are bound. Remaining limits: body merging in action inheritance,
   spawning actor-typed local variables and `call scenario(...)`.
3. **Pedestrian and static object support** is absent in CARLA. The mock
   supports pedestrian `walk`; the CARLA side is left to the thesis period.
4. **PID speed control and timeout wrappers** are missing; the existing
   proportional control and manual `wait elapsed(...)` are sufficient.
5. **CI and the demo video** will be completed at the submission stage; they are
   outside code scope.
6. **Measurements cover a single machine and a single map** (`Town10HD_Opt`); no
   determinism claim is made for other hardware or maps.
