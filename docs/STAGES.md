# Project Stages and Learning Path

This document summarizes which concept we used and why while building the project, and what you should learn at each stage. So that you can answer "why did you do it this way?" at the thesis defense, ask yourself the questions at the end of each stage.

## Stage 0 — Environment and skeleton (completed)

**Concept:** Reproducible development environment, virtual environment (venv), dependency pinning, version control.

**Done:**
- Python 3.12 venv (CARLA 0.9.16 works with this version; the system's 3.15 stays separate).
- JDK 17 + ANTLR 4.13.2.
- Grammar spike: top-level `use`, spaced and compound physical literals (`m/s`, `m/s^2`).
- First parser tests with `pytest`.

**Output:** `pytest -q` green; project on the Desktop.

**Test yourself:**
- Why can CARLA not be used with Python 3.15?
- Why do we regenerate the parser when we change the grammar?
- What does `venv` isolate?

## Stage 1 — Frontend: lexer, parser, AST (completed)

**Concept:** Token, lexer, parser, parse tree, AST, visitor, indentation-sensitive language, source location.

**Done:**
- `frontend/ast.py`: ~70 typed nodes, each node with a `Span` (file, line, column).
- `frontend/transformer.py`: a Visitor that converts the ANTLR parse tree into the AST.
- `frontend/parser.py`: the entry point that collects syntax errors and raises them as `ParseError`.
- `osc2c ast <file>` CLI; `tests/golden/ast/*.json` snapshots.
- Grammar fix: `enum_member_value` now uses `integer_literal` (the lexer never produced `UINT_LITERAL`).

**Pitfall learned:** the `enum_value_reference` rule inside `primary_exp` also matched bare names such as `v_hero`. This distinction cannot be made in syntax; the transformer turns a bare name into an `Identifier` and leaves the decision about enum membership to the semantic stage.

**Output:** `osc2c ast scenarios/dev/smoke4.osc` JSON AST; at the end of Stage 1, 16 tests green (today 169 mock/validation + 3 CARLA).

**Test yourself:**
- What is the difference between a parse tree and an AST?
- Why is `use` a parser rule rather than a lexer rule?
- Why are `INDENT`/`DEDENT` necessary in an indentation-sensitive language?
- Why does a golden test compare the *entire* AST; what do you miss by checking only a few fields?

## Stage 2 — Semantics: symbol table, types, units (completed)

**Concept:** Scope, symbol table, two-pass resolution, type system, physical units, inheritance.

**Done:**
- `semantics/types.py`: primitives, physical types with an 8-tuple SI dimension, unit conversion (`to_si`/`from_si`), list/range, enum, composite (struct/actor/scenario/action/modifier), function type; assignability (dimension match, `int`→`float`, subtype via the inheritance chain).
- `semantics/scope.py`: `Symbol`/`Scope`, `SymbolKind`; namespaces are held in a flat scope under the key `a::b`.
- `semantics/stdlib.py`: the built-in subset used when ASAM files are absent — `length`, `speed`, `time`, `angle`, `mass`; `m/km/cm/mm`, `s/ms/min/h`, `rad/deg`, `kph/mph/mps`; `traffic_participant`/`vehicle`/`pedestrian`/`environment`, `position`, `speed`/`lane` modifiers.
- `semantics/builder.py`: `ModelBuilder` runs two passes — **definition** (types, units, enums, composites, modifiers, parameters, members) and **resolution** (unit coefficients, inheritance, extensions, signatures, expression types, bodies, call arguments). Every node is annotated under the key `id(node)`.
- In built-in subset mode, actors without an explicit base derive from `std::traffic_participant`; this gives them the `name`/`position` fields and compatibility with the built-in methods. When the real ASAM library is loaded, the bases are written explicitly in the file (`vehicle → traffic_participant → movable_object → physical_object → osc_actor`).
- `semantics/diagnostics.py`: diagnostics with stable codes, promotion of warnings to errors with `--strict`.
- `osc2c check` CLI: `--strict`, `--stdlib FILE`, `--dump-symbols`, `--include-builtins`; relative `import` chains are loaded recursively.
- Tests: six development scenarios clean; negative/positive tests for unit conversion, inheritance cycle, type mismatch, ambiguous name, argument errors, and symbol table determinism.

**Pitfalls learned:**
- `prefixed_identifier` supports only a single `::`; `std::stdtypes::speed` cannot be written directly. Workaround: `use stdtypes` + short name, or an external definition via `--stdlib`. Rather than extending the grammar, the existing language rule was followed.
- A bare enum member (`start`) and a variable name look the same in syntax; the distinction is made in the resolution pass, over the visible enums. If the same name exists in more than one enum, the ambiguity error `E0404` is reported.
- "Undefined method" is not an error on every composite: an actor/scenario/action may call external fields (`W0105`), a struct may not (`E0403`). This policy prevents false positives while still catching typos.

**Output:** Annotated AST + diagnostics with stable codes; `osc2c check` clean across all development scenarios (only the intentional `W0102`/`W0105` warnings); `pytest -q` 52 tests green.

**Test yourself:**
- Why are two passes needed? What breaks in a single pass?
  → Forward references (an actor referring to a type defined later) and mutual inheritance cannot be resolved in a single pass; moreover, bodies can only be checked once all signatures are known.
- Where is the `vehicle` → `traffic_participant` inheritance resolved?
  → In the resolution pass, in `_resolve_inheritance`; the chain is checked by walking upward inside `is_assignable`.
- Are `35 kph` and `9.72 m/s` the same thing; who guarantees it?
  → Yes, the same dimension (length/time). `UnitInfo.to_si` applies the coefficient; equality is guaranteed by the dimension comparison in `is_assignable`/`common_type`.

## Stage 3 — Runtime and behavior trees (completed)

**Concept:** Behavior tree (BT), composite (sequence/parallel/selector), blackboard, event, edge detection (`rise`/`fall`), durative action, tick loop.

**Done:**
- `runtime/context.py`: `ExecutionContext`; binds scenario parameters to the actor, applies `keep(it.name == ...)` constraints, evaluates variables in order with SI units, and calls user methods (through `it`).
- `runtime/blackboard.py`: events and shared state; events are latched, so a later `wait @event` is satisfied immediately.
- `adapters/__init__.py`: `SimAdapter` protocol and `ActorState`; the CARLA dependency is still confined to `adapters/carla.py`.
- `adapters/mock.py`: deterministic single-lane road model; motion along `s`, lane change, light and sun angle; `ahead_of` topological difference.
- `backend/behaviors.py`: `ActionLeaf`, `WaitLeaf`, `EmitLeaf`, `CallLeaf`, `UnsupportedLeaf`; `elapsed`/`rise`/`fall`/`@event` conditions.
- `backend/method_registry.py`: `drive`, `walk`, `change_speed`, `assign_position`, `change_lane`, `set_lights`, `assign_celestial_position` mappings; `position`/`lane` modifiers.
- `backend/compiler.py`: `serial` → `Sequence(memory=True)`, `parallel` → `Parallel(SuccessOnAll)`, `one_of` → `Parallel(SuccessOnOne)`; `CompiledScenario.run()` tick loop and `RunResult`.
- `osc2c bt` (tree JSON) and `osc2c run` (mock run, `--ticks`, `--dt`, `--trace`); `tests/golden/bt/*.json` snapshots.
- New scenarios: `stage3_sync.osc` (one_of + rise + emit + elapsed + event), `stage3_parallel.osc`, `stage3_fall.osc`, `stage3_unsupported.osc`.

**Pitfalls learned:**
- `Selector` is the wrong tool for `one_of`: if the first child is `RUNNING` it never ticks the later alternatives; the `drive` + `wait` race in the paper deadlocks. `Parallel(SuccessOnOne)` ticks all branches and awards the first success.
- `rise`/`fall` is not the question "is it true right now?"; the first observation only records the previous state, and triggering happens on the next change. A condition that is already true at the start does not produce a `rise`.
- `drive` is a durative behavior and stays `RUNNING`; on its own it does not finish the scenario inside a `serial`. It must be terminated with `one_of`, `wait`, or a timeout.
- An unsupported behavior is not skipped silently: a compile warning is emitted and a leaf that produces `FAILURE` is created in the tree.

**Output:** `osc2c run scenarios/dev/stage3_sync.osc` → `SUCCESS`, 22 ticks, `SYNCHRONIZED` event, `high_beam`; `stage3_parallel` synchronizes two branches in 0.5 s; `stage3_fall` catches the falling edge; `pytest -q` 81 tests green. Not all of Listings 1–3: the composition and event core from Listings 2/3 runs on the mock; `map`, `stationary_object`, and real CARLA placement come in Stage 4.

**Test yourself:**
- Why does `one_of` use a "first success" policy?
  → The alternatives start simultaneously; whichever finishes first is selected by the scenario. `Selector` is ordered and gets stuck on a `RUNNING` branch.
- Why does the difference between `rise` and `fall` matter in event triggering?
  → `rise` waits for a false→true transition, `fall` for a true→false one; looking only at the instantaneous value leads to a trigger on every tick for a condition that stays true.
- How would event synchronization be done without a blackboard; what is the disadvantage?
  → It would require a shared variable/global flag or a direct object reference; this couples actors to each other and creates race conditions such as missed or double-consumed events.
- Why does a durative `drive` not finish on its own inside a `serial`?
  → It keeps maintaining the target speed and returns `RUNNING`; the sequence does not advance unless a termination condition is added.

## Stage 4 — CARLA adapter (completed)

**Concept:** Simulator API, synchronous mode, actor/spawn, OpenDRIVE, waypoint, pure pursuit, initial placement.

**Done:**
- `SimAdapter` extended: `assign_position(reference, distance, lane_offset)` and `lane_change_complete(name)`. The mock adapter applies relative position and lane offset under the same contract.
- `backend/initializer.py`: `ScenarioInitializer` applies `at: start` actions **once during compilation** (`assign_position`, `change_lane`, `change_speed`, `set_lights`, `assign_celestial_position`). In the tree these nodes are replaced by a `Success` leaf; `drive`/`walk` are not executed at the start because they are durative behaviors.
- `method_registry.py`: `position(distance:, ahead_of:/behind:)`, `lane(side:, side_of:, num_of_lanes:)` and absolute `lane` mappings; `change_lane` now waits for the adapter's `lane_change_complete` response.
- `adapters/carla.py` (the only `carla` import):
  - synchronous mode + fixed delta; restoration of settings/weather and actor cleanup on shutdown.
  - `role_name` mapping; `tesla.model3` / `lincoln.mkz_2017` blueprints.
  - Spawn points are sorted by the same-direction view of the left lane at 0/20/40/60 m; `--spawn-index` offsets within this ordering and occupied points are skipped.
  - `assign_position`: relative distance, lane offset, and absolute lane; after placement speeds are zeroed and the brake is applied.
  - `drive`: pure-pursuit steering on every tick + throttle/brake according to the target speed; short lookahead during `change_lane`.
  - `change_lane`: target lane id + approach to the lane center within 0.7 m + at least 0.4 s; 6 s timeout.
- CLI: `osc2c run ... --carla --host --port --map --spawn-index --fixed-delta`.
- `scenarios/carla/cut_in.osc`: hero at 12 m/s, NPC 12 m ahead in the left lane; after 2 s a lane change to the right, the `CUT_IN` event, then hero braking and NPC deceleration.
- `tests/test_carla.py` (`@pytest.mark.carla`): spawn/motion, cut-in geometry, `close()` cleanup, and settings restoration.

**Pitfalls learned:**
- In CARLA, `waypoint.s` does not increase in the direction of travel on every road; for `ahead_of` a projection onto the forward vector was used: `dot(p1 - p2, forward(p1))`.
- In synchronous mode, `try_spawn_actor` and `set_transform` are applied only with `world.tick()`; the adapter ticks after spawn/teleport. `close()` likewise finalizes destruction with a tick.
- `get_control()` returns some fields (notably `reverse`/`gear`) uninitialized; the vehicle started reversing. A fresh `VehicleControl(reverse=False, manual_gear_shift=False, gear=0)` was constructed on every tick.
- Lane ids are road-local and change at junctions; the completion check relies not only on the road id but on the target lane id + proximity to the lane center.
- On a lane change, a long lookahead made the vehicle miss the target lane; the lookahead was shortened to 4–8 m during the maneuver, while 5–11 m is used in normal driving.
- Single-lane/short spawn points make the cut-in impossible; spawn selection was populated by sorting according to left-lane visibility.

**Output:** Cut-in `SUCCESS` in CARLA; at the start the NPC is one lane to the left (~3.5 m) and 12 m ahead, and at the `CUT_IN` moment it is in the same lane (|lateral| < 2.2 m), with a small heading difference and still ahead. `pytest -q -m "not carla"` 82 tests, `pytest -q -m carla` 3 tests green.

**Test yourself:**
- Why do `ahead_of` (topological/projection) and Euclidean distance differ?
  → Euclidean distance is straight-line distance; in a cut-in it grows as the vehicle moves sideways. The projection answers "how far ahead is it along my forward axis?" and stays stable during a lane change.
- How does synchronous mode contribute to determinism?
  → The simulation advances only on a `tick()` call and each step uses a fixed `fixed_delta_seconds`; thus the same input sequence produces the same state sequence (except for the core determinism of the physics engine).
- What is the difference between pure pursuit and PID?
  → Pure pursuit traces a geometric arc to a forward target point; PID accumulates past error and requires gain tuning. In this project the target point is produced by `waypoint.next()`, so pure pursuit was simpler and more stable.
- Why are `at: start` actions applied during compilation, and why do they appear as `Success` in the tree?
  → They establish the scenario's initial conditions; re-running them on every tick would continuously teleport the vehicle. Applying them once and marking them as successful leaves in the tree lets the `serial` flow advance as expected.

## Stage 5 — Validation and measurement (completed)

**Concept:** Golden test, determinism, trace hash, benchmark, baseline comparison, coverage matrix, validity threat.

**Done:**
- Five-scenario validation set: CARLA cut-in (S1) + `lane_change_speed`, `event_handshake`, `placement_modes`, `environment_lights` (S2–S5). All deterministic on `MockAdapter`.
- `src/osc2c/validation.py`: samples actor state on every tick and produces a SHA-256 trace hash; measures compilation stages (parse/analysis/BT) and tick latency; computes minimum distance, TTC, collision and geometry KPIs for the cut-in.
- `tools/bench.py`: `--mode mock|carla|all`, repetition counts, JSON/Markdown output.
- `src/osc2c/coverage.py` + `tools/coverage.py`: a 43-row evidence-backed coverage matrix based on Table 2 of the paper (status + evidence path + rationale); `validate_matrix()` checks consistency, duplicate rows, and invalid test evidence.
- `tools/baseline_carla.py`: a control group driven directly through the CARLA API without using the compiler.
- `tests/test_validation.py`: 14 tests for scenario results, events, cut-in geometry, 20-repetition determinism, compilation stages, and the coverage matrix.
- Report: `docs/VALIDATION.md`; raw data in `docs/measurements/`.

**Pitfalls learned:**
- "Deterministic" cannot be measured without a definition. What is meant here: the same scenario + the same adapter settings + the same fixed step gives the same hash for the tick-by-tick actor state. It is not claimed that the physics engine will produce the same result on different machines.
- Every tick's full actor state must enter the hash; hashing only the final state mistakes two runs that diverge along the way but end in the same place for "the same".
- In CARLA the first run includes warm-up: BT compilation takes ~4 s the first time, then ~16 ms. The mean alone is misleading; median + steady-state should be reported.
- Compilation time depends much more on the parser's ambiguity resolution than on scenario size (2.6–75.2 ms). Reporting a single "compile time" value would be wrong.
- The baseline must be compared with its **full cycle** (tick + control computation), not with a raw engine tick; otherwise apples and oranges are compared. The baseline is also not an algorithmic equivalent, only a cost control.
- The marks in Table 2 could not be extracted from the PDF; instead of guessing the marks, our own matrix was built that ties each row to running evidence.

**Output:**
- Mock: 5/5 SUCCESS, a single hash across 20 repetitions of each scenario; compile median 2.63–75.19 ms (parser dominant), tick p95 ≤ 0.03 ms.
- CARLA: 20/20 SUCCESS, 20/20 geometry, a single hash (`afaf910c…`); `CUT_IN` 3.25 s, |lateral| 1.298 m, minimum distance 11.938 m, TTC 24.49 s, 0 collisions; tick median 5.45 ms.
- Baseline: 5/5 SUCCESS; full cycle 5.38 ms — a ~1.4% difference from the compiler tick. The baseline completes the cut-in in 4.25 s (different speed profile/trigger).
- Coverage: 43 rows → 24 supported, 10 partial, 9 unsupported (strict 56%, weighted 67%).
- `pytest -q -m "not carla"` 169 tests, `pytest -q -m carla` 3 tests green.

**Test yourself:**
- What exactly do we mean by "deterministic"?
  → That the tick sequence produces the same trace hash under the same input and the same simulation settings. Scope: same machine, same CARLA version, same map/spawn, synchronous mode + fixed delta. Absolute determinism of the physics engine is a separate claim and is not proven here.
- Which metric measures the compiler's success, and which measures the runtime's?
  → Compilation time and the coverage matrix measure the compiler's success (language coverage + frontend cost); tick latency, the KPIs, and event timing measure the runtime/adapter's success. The trace hash shows the reproducibility of both together.
- What kinds of errors arise if an unsupported construct is silently ignored?
  → The scenario looks like "SUCCESS" but the maneuver that was meant to be tested never ran; the result gives false confidence and the error is only noticed in the field. That is why an unsupported node surfaces as a compile warning + `FAILED` leaf.
- Why do we report a distribution rather than a single compile time?
  → The parser's adaptive prediction is content-sensitive; no performance claim can be made without looking at median, p95, and min/max together. In addition, the warm-up effect of the first CARLA run skews the mean.

## Stage 5.5 — Real ASAM 2.2.0 library and grammar differences (completed)

**Concept:** Normative source, informative EBNF, version difference, mechanical diff, superset, gap closed by diagnostics.

**Done:**
- The ASAM 2.2.0 package was placed under `external/asam/`: `grammar.ebnf`, `types.osc`, `domain.osc`, `standard.osc`. The license header permits distribution; the files are nevertheless covered by `.gitignore`.
- A rule inventory of `grammar.ebnf` ↔ `openscenario2.g4` was extracted: 165 EBNF, 154 parser + 16 lexer rules. Only three of the 21 name differences are behavioral.
- Three real gaps were closed: an enum member referencing another member (`truck = heavy_truck`), the `range of` declaration, primitive `extend`.
- Semantic errors blocking the library from loading were fixed (field/type shadowing, enum resolution by type, modifier/type name collision, built-in + real library collision).
- With `--stdlib external/asam/standard.osc`, the chain `standard.osc → domain.osc → types.osc` loads without diagnostics: 154 `std` + 112 `stdtypes` symbols.

**Pitfalls learned:**
- The EBNF is "informative"; the normative artifact is the document. Still, rule names and alternatives are the cheapest tool for showing where the implementation deviates.
- A name difference is not a behavior difference: `sum`/`sum_exp` or `cast-exp`/`#cast_exp_pe` describe the same language. To decide, the real file must be parsed.
- The project is deliberately a superset: 2.2's `physical-literal` takes only a single `unit-name`, while the project accepts `m/s`, `m/s^2`; although top-level `use` was removed in 2.2, it is retained for the 2.1 target.
- The number of diagnostics alone is not a measure of success: while the library yields "0 diagnostics", dotted `action vehicle.drive` declarations are not bound to the target type and `hero.drive()` gets `W0105`. A silent gap is more dangerous than a noisy error.

**Output:** `osc2c check external/asam/standard.osc` → `ok`; `scenarios/asam/asam_stdlib.osc` passes against the real library with only `W0102`. Details: [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md).

**Test yourself:**
- What is the difference between an informative EBNF and a normative specification; against which one is conformance claimed?
- Why is `m/s` support a "superset" rather than a "gap"? What is the risk of a superset?
- Which semantic gap remains invisible while the library passes without diagnostics? How would you make it visible?

## Stage 5.6 — Executing qualified actions in the backend (completed)

**Concept:** Dispatch order, qualified action (`Actor.behavior`), binding, `it` context, ambient modifier, registry mapping, noisy error instead of silent failure.

**Done:**
- Resolution of `X.behavior(...)` was made four-step: an action promoted with `at: start` → a user-defined body (including inherited `do`/`on`) → the method registry (library action under its local name) → if unmapped, a warning + `FAILED` leaf.
- `ActionScope` (`backend/behaviors.py:53`) binds the target actor as `it`; during a tick, `context.it`, `context.locals`, and ambient modifiers are temporarily changed and restored with `finally`.
- `_behavior_members` finds the nearest body in the inheritance chain (`compiler.py:39`); parameter, default, and local variable binding was unified with action calls through `_bind_action` (`compiler.py:491`). `_build_attached_action` (`compiler.py:307`) carries recursion protection.
- The semantic layer types `it` as the receiver actor inside a dotted action body (`builder.py:1187`, `_qualified_action_owner`); so `it.drive()` no longer gets `W0105`.
- Standard library parameters are optional only in comments; `std`/`stdtypes` signatures were relaxed with `_optional_signature` (`builder.py:185`), so valid `speed(10 mps)` calls no longer produce `E0405`.
- `move`, `assign_speed`, `keep_speed`, `remain_stationary` were added to the registry (`method_registry.py:122`); `drive`/`walk` were already mapped.
- Standard `with:` modifiers applied to a qualified action that has a body are evaluated at call time (`compiler.py:373`, `method_registry.py:78`) and carried as ambient modifiers for the duration of the `ActionScope`. Registry behaviors with an `it` receiver in the body inherit these values; if an inner `with:` overrides the same name, the inner value wins, and no value leaks to a call on a different actor (`behaviors.py:88`).
- User-defined modifiers were not expanded at this stage; each was reported with a "user-defined and not applied" warning. This gap was closed in Stage 5.7.

**Pitfalls learned:**
- "Semantically validated" does not mean executed: the library with 0 diagnostics did not run the `hero.drive()` call.
- `it` must be correct both at the type level and at runtime; fixing only one moves the error from one layer to another.
- The required/optional distinction in the library is written only in comments; the strict signature rejected valid calls. The relaxation was limited to the standard namespaces.
- The distinction between a qualified action and an unsupported behavior is readable from the tree: `ActionLeaf` (registry) vs. `UnsupportedLeaf` (unmapped).
- If an action calls itself, a compile-time error should be produced instead of a silent infinite loop.
- "Validated" does not mean the modifier was applied. A modifier should be carried into the action body only through the receiver `it` and only for standard names; otherwise silent side effects such as changing another actor's speed arise.
- If an outer modifier conflicts with an inner one, the inner one must win: the nearest `with:` block is more specific.

**Output:** `timer.hold(0.2 s)` → 0.2 s; `it.drive() with: speed(5 mps)` → target actor at 5 mps; `drive with speed(5 m/s)` → 5 m of travel; `assign_speed` one-shot; `move` durative (1.2 m); `c.cruise() with: speed(5 mps)` → `it.drive()` in the body at 5 mps; an inner `speed(3 mps)` overrides the outer one; while `it` + another actor drive in parallel, only `it` is at 5 mps; `c.place() with: position(x: 10 m)` → x 10 m; unmapped `follow_trajectory` still `FAILED`. `scenarios/dev/qualified_action_modifiers.osc` → `SUCCESS`, 0.5 s, speed 5 m/s. `scenarios/asam/asam_stdlib.osc --stdlib` only `W0102`; the `osc2c bt` output shows `ActionLeaf` for `hero.drive` and `hero.assign_speed`. `pytest -q -m "not carla"` → 169 tests (backend 59, semantics 64, frontend 27).

**Test yourself:**
- What order is followed when resolving an action call, and why this order?
  → First `at: start` actions, which run once and become `Success` in the tree, then the user-defined body, then the registry. A user definition shadows the library mapping; an unmapped name does not pass silently.
- Why must `it` be bound at runtime, not only in the semantic layer?
  → The semantic layer checks the type of the `it.drive()` call; if the runtime does not supply the actual actor proxy, the call goes to the wrong vehicle or crashes.
- Why is an externally supplied `with: speed(5 mps)` applied only to behaviors with an `it` receiver, not to every behavior in the body?
  → A modifier is a physical constraint of the actor that receives the action. If the body drives another actor, the same speed constraint does not belong to it; otherwise the side effect spreads silently.
- If inner and outer modifiers share the same name, which should win; why?
  → The inner one wins; the nearer scope is considered more specific. The outer value only serves as a default for fields not specified inside.
- Why do we assume standard library parameters are optional; what is the risk?
  → The distinction exists only in doc comments, with no structural information. The risk is that omitting a genuinely required parameter is not caught at compile time; hence the relaxation is limited to the standard namespaces.
- Why is silently ignoring an unmapped library action dangerous?
  → The scenario looks like `SUCCESS` but the maneuver meant to be tested never ran.

## Stage 5.7 — User-defined modifier expansion (completed)

**Concept:** Macro expansion, flattening, textual precedence, cycle detection, separation of compile-time and runtime evaluation.

In OSC2, `modifier fast of vehicle: speed(10 mps)` is not a runtime object but a **rewrite rule**: wherever `fast()` is written it must behave as if `speed(10 mps)` had been written. Until this stage the semantic layer resolved the `fast()` call, but the backend silently swallowed it because it did not recognize it (it only emitted a warning). Stage 5.7 closes this gap.

**Done:**
- `src/osc2c/backend/modifiers.py` was added. `expand_behavior_with(model, with_clause)` takes the applications in a `with:` block; it recursively flattens a user-defined modifier body into standard `speed`/`lane`/`position` applications.
- Expansion happens **at compile time**; arguments are evaluated **at call time**. This way expressions in the body can see runtime context such as `it` and action locals.
- Order is preserved: applications inside `with:` and modifier bodies are flattened in source order; in the registry dictionary the last application overrides the previous one. `speed(5 mps)` then `fast()` → 10 mps; the reverse → 5 mps.
- Cycle detection is done by `CompositeTypeInfo` identity, not by modifier name (`_stack`). An `a → b → a` chain produces a warning and stops expansion; there is no infinite recursion.
- Only `ModifierApplication` members are expanded. If the body contains another member such as `keep(...)` or `on`, it is not skipped silently; a warning is produced. Body applications with an explicit target (`actor.modifier(...)`) are likewise skipped safely and warned about.
- `compiler.py` computes the expansion once per behavior call. A direct registry call receives the evaluated modifier dictionary via `modifiers=`; for a qualified action with a body the same list is carried into `ActionScope` and passed to the `it` behaviors in the body as ambient modifiers.
- `method_registry.py` gained an optional `modifiers` parameter: if a ready dictionary is supplied it is not re-parsed; own values overwrite inherited values.
- `initializer.py` also uses the expansion: `at: start` inside a user-defined modifier body ensures the behavior is promoted before the first tick.
- `_ignored_feature_warnings` no longer produces a blanket warning for every user modifier; only cases that cannot be expanded (unresolvable name, cycle, unsupported body member) are reported.

**Pitfalls learned:**
- "Resolved semantically" and "applied at runtime" are not the same thing. `model.resolved[id(app)]` only gives the symbol; turning it into a standard application is the backend's job.
- Converting the application list to a dictionary too early during expansion produces a precedence error. Ordered list first, then the dictionary; this preserves the "last writer wins" rule.
- Detecting cycles by name is wrong: the same name may denote different modifiers in different namespaces. Identity (`id(composite)`) must be used.
- Silently discarding unsupported members in the body contradicts the project's "no silent swallowing" policy. Even with partial expansion, every skipped member must be warned about.
- Performing the expansion at both compile time and runtime duplicates warnings. `_Builder` performs the expansion once, and `registry.invoke` only does the evaluation.

**Output:**
- `pytest -q -m "not carla"` → **169 passed**, 3 deselected (backend 59, semantics 64, frontend 27).
- Direct behavior: `hero.drive() with: fast()` → speed 10 m/s.
- Qualified action body: `c.boost() with: fast()` → `it.drive()` in the body at 10 m/s.
- Order: `speed(5)` + `fast()` → 10; nested `very_fast → fast` → 10.
- Cycle: `a → b → a` → `cyclic user-defined modifier 'a'` warning, the scenario still runs.
- `at: start`: `assign_position() with: start_fast()` → the action is applied before the first tick (`initialized_actions` populated), speed 5 m/s.
- The old "user-defined and not applied" warning was removed; `cover(...)`/`record(...)` warnings are unchanged.

**Test yourself:**
- Why is a user-defined modifier flattened at compile time rather than at runtime?
  → Because the language semantics is a rewrite rule; at runtime the body would have to be re-interpreted on every tick, and precedence/cycle errors would be noticed late. Compile-time flattening reduces it to the standard applications the registry already knows; argument evaluation, however, remains at call time.
- Why does `speed(5)` then `fast()` give 10, and the reverse 5?
  → Because expansion preserves source order and the last key wins in the dictionary update. This is the natural consequence of OSC2's "a later application is more specific/overrides" behavior.
- What is the difference between detecting a cycle by name versus by identity?
  → The same short name may resolve to different definitions in different namespaces; a name-based check produces false positives/negatives. Identity tracks the actual declaration node.
- Why is the expansion done during compilation rather than inside `ActionScope`?
  → `ActionScope` runs on every tick, whereas expansion is a static transformation of the AST. Doing it once while building the tree is both faster and deduplicates warnings. `ActionScope` only carries the evaluated values.

## Stage 6 — Thesis

**Concept:** Research question, contribution, limitation, threats, reproducibility.

**To do:**
- Organize the results around RQ1–RQ3.
- Clarify the contribution: open-source reproduction + mock backend + measurement.
- Write the limitations honestly (coverage, performance, standard files).
- Demo and defense rehearsal.

**Test yourself:**
- What is the difference between "I rewrote the paper" and "I validated and measured the paper"?
- In what single sentence is the thesis's original contribution described?
- Which result, had it been absent, would have made the project count as a failure?
