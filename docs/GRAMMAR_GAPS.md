# Grammar 2.1 Gap Analysis — 26 October 2026

This document records which language constructs of the OpenSCENARIO grammar used
by the project are accepted end to end, which are only recognized syntactically
and rejected at the semantic or runtime layer, and which 2.1 areas are not yet
covered. The goal is not to assert complete language conformance; it is to make
every gap traceable through observable output, a diagnostic code, or a test.

## 1. Scope and method

The review was carried out across three sources:

1. **Vendored grammar:** [`grammar/openscenario2.g4`](../grammar/openscenario2.g4)
   (333 lines). The MPL-2.0 notice in the file header is preserved; the generated
   parser is regenerated with `scripts/generate_parser.py` using ANTLR 4.13.2.
2. **Small source probes:** Each construct was passed through the `parse` →
   `analyze` → `compile` → `run` chain. Diagnostic codes and runtime results
   were taken directly from these outputs; they were not inferred.
3. **Existing tests:** the golden, positive and negative tests in
   [`tests/test_frontend_ast.py`](../tests/test_frontend_ast.py),
   [`tests/test_semantics.py`](../tests/test_semantics.py) and
   [`tests/test_backend.py`](../tests/test_backend.py).

**Update (27 October 2026):** the ASAM 2.2.0 package (`grammar.ebnf`, `types.osc`,
`domain.osc`, `standard.osc`) is now available locally under `external/asam/`, and
all of it has been parsed and semantically checked. Although the package header
permits distribution, the files are kept under `.gitignore`. The EBNF ↔ project
grammar comparison, the gaps that were closed and the remaining deviations are
recorded in a separate document: [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md).
The coverage assessments in this document still hold; only statements that rested
on the "no official library" assumption have been updated below.

## 2. Summary

| Layer | Status |
|---|---|
| Syntax (lexer/parser) | About 70 AST nodes; declarations, expressions, events and most compositions are parsed |
| Semantic middle-end | Scope, type, SI unit, enum, inheritance and argument checking work |
| Runtime / BT | `serial`, `parallel`, `one_of`, `wait`, `emit`, `until`, durative driving and placement work |
| Official standard library | The 2.2.0 package is available under `external/asam/`; it loads with `--stdlib` and passes without diagnostics. It is not tracked in the repository; if `external/` is absent, the built-in subset takes over |
| Coverage matrix | 43 rows: 24 supported, 10 partial, 9 unsupported (strict 56%, weighted 67%) |

Test count: **169 without CARLA + 3 CARLA = 172**. This number includes tests for
the newly added `until`, `sample`, `remove_default`, `cover/record`, user
modifier, `=>`, action call (body, argument, actor parameter, nested call,
recursion), qualified action (binding, body execution, parameter/`it`,
recursion), standard modifier propagation in qualified actions (reaching the
body, nested override, receiver isolation, position), user-defined modifier
expansion (direct behavior, action body, sequence, nesting, loop, `at: start`),
compound unit (positive, negative and runtime)
and the real ASAM library (enum alias, `range of`, primitive `extend`,
library action execution and `--stdlib` CLI run).

## 3. End-to-end supported language

The following constructs are parsed and semantically checked. The executable
constructs listed in the table are implemented by the current backend in at
least one adapter; user-defined `modifier` bodies are applied by flattening them
into standard applications, but in action inheritance only the body of the
nearest base is taken. Such partially supported constructs are also listed
separately in section 5.

| Area | Supported constructs | Evidence |
|---|---|---|
| Preamble | `import "file"`, `use a.b, c.d`, `namespace`, `export` | `test_cli_loads_relative_imports`, `test_qualified_names_and_ambiguous_namespaces` |
| Declarations | `type`, `unit`, `enum`, `extend enum`, `struct`, `actor`, `scenario`, `action`, `modifier`, `global`, `def` | `scenarios/dev/grammar_tour.osc`, `test_inherited_fields_and_enum_extension` |
| Inheritance | Actor/struct type fields, methods and enum extensions | `test_inheritance_cycle_and_kind_mismatch`, `test_inherited_fields_and_enum_extension` |
| Types | `int`, `uint`, `float`, `bool`, `string`, `list of T`, physical types | `test_unit_registry_and_conversions` |
| Units | SI dimensions, custom `type`/`unit`, `factor` and `offset` | `test_inherited_fields_and_enum_extension`; `m`, `km`, `mph`, `kph`, `mps`, `deg`, `ms` |
| Compound units | `m/s`, `km/h`, `m/s^2`; `/` and `^`, SI dimension and factor derivation | `scenarios/dev/compound_units.osc`, `test_compound_units_resolve_and_convert`, `test_compound_unit_literals_evaluate_to_si` |
| Expressions | Arithmetic, comparison, `and`/`or`/`not`, `=>`, ternary operator, `in`, list, range, field/element access, `.as(...)`, `.is(...)` | `test_implication_is_evaluated`; verified with the ternary operator and a cast probe |
| Composition | `serial`, `parallel`, `one_of`, labeled statement | `test_serial_parallel_and_one_of_mapping` |
| Action calls | `call action(...)`, positional/named argument, default, actor parameter, nested call | `scenarios/dev/action_calls.osc`, `test_action_call_binds_arguments`, `test_nested_action_calls_restore_the_caller_scope` |
| Behavior | `drive`, `walk`, `change_speed`, `change_lane`, `assign_position`, `set_lights`, `assign_celestial_position` | `test_pedestrian_walk_moves_actor`, `test_cut_in_scenario_runs_on_carla` |
| Modifiers | `speed`, `lane`, `position` | `scenarios/dev/lane_change_speed.osc`, `placement_modes.osc` |
| Events | `elapsed`, `rise`, `fall`, `@event`, `emit`, edge detection | `test_rise_does_not_fire_on_an_already_true_condition`, `test_fall_edge_fires_after_speed_drops` |
| Termination | Terminating durative behavior with `until` | `test_until_terminates_durative_behaviour` |
| Constraints | `keep(it.<field> == value)` | `test_keep_constraints_bind_actor_attributes` |
| Start | `at: start` placements, three placement modes | `tests/test_carla.py`, `placement_modes.osc` |

`until` is defined as an event specification inside `behavior_with_declaration`
(under `with:`); it is not a standalone `do` command
([grammar/openscenario2.g4:230](../grammar/openscenario2.g4#L230)). The backend
implements it by combining the durative behavior and a `WaitLeaf` in a
`Parallel(SuccessOnOne)`
([src/osc2c/backend/compiler.py:391](../src/osc2c/backend/compiler.py#L391)).

## 4. Grammar accepts, semantic layer rejects

Constructs in this group are syntactically valid; however, because type/unit
resolution fails or the relevant symbol cannot be found, a stable diagnostic
code is produced. Error-level diagnostics stop compilation; warnings let
compilation continue.

| Usage | Observed result | Reason |
|---|---|---|
| `var v : speed = 1 m/parsec` | `E0203 unknown unit 'parsec'` | The compound unit expression is parsed; each component is resolved as a unit in scope |
| `var t : temp = 1 celsius/K` | `E0203 unit 'celsius' has an offset ...` | Units with an offset are not suitable for multiplicative conversion in a compound unit |
| `box : stationary_object` | `E0201 unknown type 'stationary_object'` | No definition in the built-in fallback standard library ([stdlib.py](../src/osc2c/semantics/stdlib.py)) |
| `m : map` | `E0201 unknown type 'map'` | Same reason; there is no map type or road semantics |
| `rate_profile(linear: 1 mps)` | `W0104 unknown modifier 'rate_profile'` | There is no modifier definition in the fallback library; the speed profile is also absent in the backend |
| `object_distance(hero, other)` | `E0402 unknown method or behavior` | There is no method in the fallback library; the current API is `position.ahead_of()` / `position.euclidean()` |
| `var xs : list of int = range(1, 3)` | `E0401 initial value expects list of int, got range of int` | A range type is not assignable to a list; the runtime can expand a range into a list, but the type system does not accept it |
| `!cond`, `a && b` | Parse/token error | The canonical spelling is `not`, `and`, `or`; `!` is only used in `enum!member` |

**Measurement with the real 2.2.0 library (27 October 2026):** `stationary_object`
and `map` now resolve; the only remaining diagnostic is the undefined event in
the scenario (`W0102`). `rate_profile` is not a modifier but a parameter typed
`dynamic_profile` (`domain.osc:1155`), so the call form yields `E0404`.
`object_distance` is a `def` defined on `physical_object` (`domain.osc:358`);
because it cannot be called unqualified in a scenario body it yields `E0402` —
this is not a library gap but a limit of the call context. Compound units
(`m/s`, `m/s^2`) are supported in the grammar, the semantic layer and the
runtime; the remaining limits are listed in section 6.

## 5. Grammar and semantic layer accept, backend does not implement

These constructs compile; however, their runtime effects are missing or absent.
To prevent silent swallowing, a compile warning is produced wherever possible.

| Construct | Current behavior | Gap |
|---|---|---|
| `greet()` (targetless behavior call) | `CompilationError: behaviour 'greet' has no target` | The semantic layer resolves the scenario/action symbol; the backend does not compile a targetless call; `call greet()` works |
| `call hero.drive()` | Compiles; driving does not start, `CallLeaf` evaluates the expression and gets `None` | The distinction between a method call and a behavior call is not clear; `drive` is a behavior, not an expression method |
| User-defined modifier (`modifier fast of vehicle: speed(...)`) | Compiles; its body is flattened and applied to standard applications | Only `ModifierApplication` members are expanded; other members such as `keep`/`on` are skipped with a warning, and cycles are detected |
| `on @event:` | `UnsupportedLeaf` → `FAILURE`, written to the `unsupported` list | Event-driven branching is absent in the backend ([compiler.py:541](../src/osc2c/backend/compiler.py#L541)) |
| `cover(...)`, `record(...)` | Compiles; no records are produced | A warning is added; there is no coverage/trace recording integration |
| `sample(expr, @event, default)` | The default value is used for the variable | Warning: sampling is not evaluated; only `default` is assigned ([context.py:117](../src/osc2c/runtime/context.py#L117)) |
| `remove_default(...)` | Ignored | It now produces a warning including nested cases; default removal is not implemented |
| `wait every(200 ms)` | Succeeds once | The periodic event is not re-triggered; `WaitLeaf` resets its start time but completes only once |
| `scenario child inherits base` | The child scenario's own `do` body runs; fields are inherited | The base scenario's `do`/`on` behaviors are not merged (the probe produced only `CHILD`) |
| Unsupported behavior (`fly()`) | Compile warning + `FAILURE` leaf | Intentional and noisy behavior |
| Unsupported `keep` form | Compile warning; the constraint is validated but not applied | Only `keep(it.<field> == value)` is applied |
| Unknown light mode | `ValueError` | Explicit error instead of silent `NONE` |

## 6. Lexer and syntax formatting constraints

The following are not errors but the language's current spelling rules; they
must be known when writing scenarios:

- **Indentation is significant.** Blocks are formed with `:` + `INDENT`/`DEDENT`;
  spellings missing the colon such as `do serial` cannot be parsed.
- **Compound units are written with `/` and `^`.** `m/s`, `km/h`, `m/s^2` and
  negative exponents (`m/s^-2`) are supported
  ([lines 321-322](../grammar/openscenario2.g4#L321)). Operators apply from left
  to right. `*` is not supported as a compound unit multiplier; `kg*m/s^2`
  cannot be parsed, so a defined alias (such as `N`) or a separate
  multiplication expression must be used instead.
- **A unit expression can be confused with multiplication/division.** The
  spelling `1 m / x` is parsed as a unit expression even when `x` is a variable,
  and yields `E0203` if `x` is not a unit. To divide a length by a variable, use
  the spelling `(1 m) / x`.
- **`namespace` does not take a colon.** The correct spelling is `namespace demo`;
  the incorrect spelling `namespace demo:` gives a parse error.
- **`action` and `modifier` bodies differ.** The `action a:` body takes scenario
  members and behavior specifications; the `modifier m of vehicle:` body takes
  scenario members and `on` directives, and does not take a standalone `do`
  ([lines 123-132](../grammar/openscenario2.g4#L123)).
- **Only a single `::` is supported.** `prefixed_identifier` is in the form of a
  namespace prefix + local name; `std::stdtypes::speed` cannot be written
  directly. Solution: `use stdtypes` + short name, or `--stdlib`.
- **`export` and `import` resolution is limited.** Relative file imports are
  loaded recursively; namespace imports do not load files, they only create a
  visibility record.
- **`enum` members can be written as bare names**; syntactically they look the
  same as a variable name. The distinction is made during semantic resolution;
  if the same name exists in two enums, an `E0404` ambiguity results.

## 7. Official standard library and built-in fallback

There are two modes:

- **Real library:** `--stdlib external/asam/standard.osc`. The CLI loads the
  `standard.osc` → `domain.osc` → `types.osc` import chain recursively; 154
  `std` + 112 `stdtypes` symbols are resolved in total and no diagnostics are
  produced. The built-in subset is automatically disabled.
- **Built-in fallback:** if `--stdlib` is not given, the subset in
  [`src/osc2c/semantics/stdlib.py`](../src/osc2c/semantics/stdlib.py) is
  installed. This mode lets tests and scenarios run even without the
  repository's `external/`.

The contents of the built-in subset:

- Physical types: `length`, `distance`, `speed`, `acceleration`, `time`,
  `angle`, `mass`, `temperature`, `electric_current`, `amount_of_substance`,
  `luminous_intensity`, `frequency`, `force`, `energy`.
- Units: `m`, `km`, `cm`, `mm`, `s`, `ms`, `min`, `h`, `rad`, `deg`,
  `mps`, `kph`, `mph`, `kg`, `g`, `K`, `A`, `mol`, `cd`.
- Actors: `traffic_participant`, `vehicle`, `pedestrian`, `environment`.
- Structs/methods: `position` (`ahead_of`), vehicle (`drive`,
  `assign_position`), pedestrian (`walk`), environment (`assign_celestial_position`).
- Modifiers: `speed`, `lane`, `position`; enums: `direction`, `side`.

Results:

- Undefined external events produce a `W0102` warning, undefined external
  methods a `W0105` warning. These are not errors. When the real `domain.osc` is
  loaded, `W0102` remains only for events the scenario itself does not define.
- Names such as `stationary_object` and `map` are not in the built-in subset
  (`E0201`); they resolve in the real library. For `rate_profile` and
  `object_distance`, the observed `E0404`/`E0402` are not a library deficiency
  but a limit of call form/context (section 4).
- `--stdlib` was validated against the real 2.2.0 package:
  `osc2c check external/asam/standard.osc` → `ok` (exit 0) and
  `scenarios/asam/asam_stdlib.osc` → only `W0102` (exit 0). Details and the
  three closed syntax gaps: [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md).
- **Qualified behaviors bind and execute:** 48 declarations such as
  `action vehicle.drive` are added to the target actor's method table;
  `hero.drive()` and `hero.assign_position()` resolve without diagnostics, and
  base actor actions are visible through inheritance. The backend compiles user
  actions that have a body and binds `it` to the target actor; it lowers
  body-less library actions to the simulator registry (`move`, `assign_speed`,
  `keep_speed`, `remain_stationary` were added in this pass). An action with no
  mapping still produces a warning + `FAILURE`. In library actions and standard
  modifiers, a missing argument is not counted as an error (mandatory/optional
  information exists only in comments); the name and type of a provided
  argument are checked. Details:
  [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) §6.
- Because `external/asam/` is under `.gitignore`, tests that depend on the real
  library are skipped with `skipif` in another clone.

## 8. Fixed in this pass

1. **`until` implemented.** Durative behavior is terminated with
   `Parallel(SuccessOnOne)`; the `until elapsed(500 ms)` test verifies that
   driving stops at 5 m ([test_backend.py:218](../tests/test_backend.py#L218)).
2. **`sample(...)` is no longer silent.** The default value is used and a
   compile warning is produced.
3. **`remove_default` warning deepened.** It is now reported not only at the
   scenario top level but also in nested `with:` blocks.
4. **`cover`/`record` are reported.** These constructs, which the backend does
   not implement, became compile warnings. User-defined modifiers are now
   applied; see item 15.
5. **Action bodies compiled.** `call action(...)` now runs the `do`/`on` tree of
   the action declaration as a scoped subtree. Arguments are bound positionally
   or by name at call time, missing parameters come from the default, and
   `var`s inside the action are re-established on every call. Scope is restored
   at the end of the call; nested calls do not disturb the caller's locals. A
   missing argument yields `E0405`, an unknown named argument `E0406`, and
   self-recursion a compile error
   ([compiler.py:447](../src/osc2c/backend/compiler.py#L447),
   [behaviors.py:53](../src/osc2c/backend/behaviors.py#L53)).
6. **Logical implication (`=>`) implemented at runtime.** Previously a valid
   expression crashed compilation with `EvaluationError`
   ([context.py:470](../src/osc2c/runtime/context.py#L470)).
7. **Coverage matrix and evidence validation** had been strengthened in the
   previous audit; no new row was added to the matrix in this pass.
8. **Compound units implemented.** `unit_expression` and `unit_term` rules were
   added to the grammar; `m/s`, `km/h` and `m/s^2` are parsed. The semantic
   layer resolves the components and derives the SI dimension and factor; the
   runtime converts the value to SI. An unknown component is rejected with
   `E0203`, and a component with an offset again with `E0203`
   ([builder.py:1460](../src/osc2c/semantics/builder.py#L1460)).
9. **An enum member can reference another member.** `enum-member-value` now
   accepts `uint-literal | hex-uint-literal | enum-value-reference`. The
   `truck = heavy_truck` alias in `domain.osc` is thus parsed and its value
   copied; an unknown reference yields `E0103`
   ([builder.py:518](../src/osc2c/semantics/builder.py#L518)).
10. **`range of` declaration.** Nested range types such as `list of range of int`
    are parsed and resolved as `RangeTypeInfo`
    ([builder.py:1576](../src/osc2c/semantics/builder.py#L1576)).
11. **Primitive `extend`.** The `extend float:` form is parsed; methods are
    registered but reported with `W0106` because they are not executed.
12. **The real library loads without diagnostics.** `types.osc`, `domain.osc` and
    `standard.osc` are parsed and resolved together; details in
    [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md).
13. **Qualified actions bind to the actor.** `_attach_qualified_actions` adds
    `action A.b` declarations to the `A.methods` table. The library's 48
    qualified actions now resolve in calls such as `hero.drive()`, and base
    actor actions are visible through inheritance. Argument types continue to be
    checked; because the library actions write the mandatory/optional
    distinction only in comments, a missing argument does not produce `E0405`
    ([builder.py:904](../src/osc2c/semantics/builder.py#L904)).
14. **Bound actions execute in the backend.** `action A.b` declarations with a
    body are compiled into the behavior tree; parameters, local `var`s and `it`
    (the target actor) are bound at call time, and the base action's `do` body
    is inherited
    ([compiler.py:307](../src/osc2c/backend/compiler.py#L307),
    [behaviors.py:53](../src/osc2c/backend/behaviors.py#L53)). Body-less library
    actions lower to their counterparts in the registry; `move`,
    `assign_speed`, `keep_speed` and `remain_stationary` were added in this pass
    ([method_registry.py:122](../src/osc2c/backend/method_registry.py#L122)).
    An action with no mapping (such as `follow_trajectory`) still produces a
    warning + `FAILURE`. Standard library modifier parameters are also treated
    as optional, so that `hero.drive() with: speed(10 mps)` works with the real
    library ([builder.py:185](../src/osc2c/semantics/builder.py#L185)).
15. **Standard modifiers are propagated into the qualified action body.** In a
    call such as `c.cruise() with: speed(5 mps)`, the modifier is evaluated at
    call time and kept as an ambient modifier for the duration of the
    `ActionScope`; built-in behaviors with the `it` receiver in the body
    (`drive`, `assign_position`, ...) inherit the value. If an inner `with:`
    overrides the same name, the inner value wins, and the value does not leak
    into a call made on a different actor
    ([compiler.py:373](../src/osc2c/backend/compiler.py#L373),
    [behaviors.py:88](../src/osc2c/backend/behaviors.py#L88),
    [method_registry.py:78](../src/osc2c/backend/method_registry.py#L78)).
    User-defined modifiers are also flattened at compile time by
    `backend/modifiers.py`; standard applications in the body are transferred
    to direct behaviors, qualified action bodies and the `at: start` promotion.
    Cycles and unsupported body members are reported with a warning
    ([modifiers.py](../src/osc2c/backend/modifiers.py)).

## 9. Remaining work and priority

| Priority | Work | Reason / next step |
|---|---|---|
| — (closed) | Mechanical diff against the ASAM 2.2.0 grammar and library | Done: 165 EBNF / 154 parser rules compared, three gaps closed — [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) |
| — (closed) | Bind qualified behavior names to the target type | `_attach_qualified_actions` adds 48 library actions to the actor's method table; `hero.drive()` now resolves — [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) §6 |
| — (closed) | Execute bound actions in the backend | Actions with bodies are compiled, `it` is bound to the target actor; `move`, `assign_speed`, `keep_speed`, `remain_stationary` were added to the registry; an action with no mapping gives a warning + `FAILURE` — [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) §6.1 |
| P1 | Should `external/asam/` be admitted to the repository? | The license permits distribution; if the decision is made, `NOTICE` is updated and the `skipif` tests run in every clone — [`GRAMMAR_DIFF_2.2.md`](GRAMMAR_DIFF_2.2.md) §8 |
| P1 | Merging behaviors in scenario inheritance | Base `do`/`on` members must be carried into the child scenario; fields are already inherited |
| — (closed) | User-defined modifier expansion | Body applications are flattened at compile time; applied on the direct behavior, qualified action and `at: start` paths; cycles and unsupported members are warned — [`STAGES.md`](STAGES.md) §Stage 5.7 |
| — (closed) | `with:` modifiers applied to an action with a body | Standard `speed`/`lane`/`position` modifiers are propagated to `it` behaviors in the body; an inner modifier overrides the outer one. User-defined modifier expansion was also completed in Stage 5.7 — [`STAGES.md`](STAGES.md) §Stage 5.7 |
| P2 | `at: start` in bound actions | Start placement is currently pre-applied only for names in the registry |
| P2 | `on` directives | Event-driven branches must be connected to the BT; currently a noisy `FAILURE` |
| P2 | `every` periodicity | Event semantics that re-trigger on each period; currently one-shot |
| P2 | `cover`/`record` integration | Coverage measurement and trace recording; currently only a warning |
| P2 | Compound units containing `*` (`kg*m/s^2`) | If `*` is added to the grammar, ambiguity arises with the `1 m * x` multiplication; a disambiguation rule or a defined alias is needed |
| P3 | Distinguishing behavior calls with `call` | The method/behavior distinction in expressions such as `call hero.drive()` must be clarified |
| P3 | `range` → `list` assignability | Range/list compatibility in the type system, or an explicit conversion |
| P3 | Actor-typed local variables inside an action | Bodies are inherited from the base action, but actor-typed local variables declared inside an action are not spawned |
| P3 | `call scenario(...)` | A scenario call only produces a warning; there is no nested scenario execution |

## 10. Reproduction

```bash
cd osc2c
.venv\Scripts\python.exe -m pytest -q -m "not carla"
.venv\Scripts\python.exe -m pytest -q -m carla
.venv\Scripts\python.exe -m compileall -q src

# Compound unit: valid scenario and intentional error
.venv\Scripts\osc2c.exe check scenarios\dev\compound_units.osc
.venv\Scripts\osc2c.exe check scenarios\diagnostics\unknown_compound_unit.osc

# Action calls: parameter, default and actor binding
.venv\Scripts\osc2c.exe check scenarios\dev\action_calls.osc
.venv\Scripts\osc2c.exe run scenarios\dev\action_calls.osc --ticks 50

# with: modifier propagation in a qualified action (speed + position into the body)
.venv\Scripts\osc2c.exe check scenarios\dev\qualified_action_modifiers.osc
.venv\Scripts\osc2c.exe run scenarios\dev\qualified_action_modifiers.osc --ticks 30

# Real ASAM 2.2.0 library (skipped if external/asam is absent)
.venv\Scripts\osc2c.exe check external\asam\standard.osc
.venv\Scripts\osc2c.exe check scenarios\asam\asam_stdlib.osc --stdlib external\asam\standard.osc

# Regenerating the grammar (MPL-2.0 notice preserved; JDK 17 or 21 required)
.venv\Scripts\python.exe scripts\generate_parser.py
```

Expected: **169 non-CARLA + 3 CARLA tests** green. `check` outputs:

```text
scenarios\dev\compound_units.osc: ok
unknown_compound_unit.osc:5:20: error[E0203]: unknown unit 'parsec'
```

`action_calls.osc` produces two `W0102` warnings (`READY`, `DONE` are not defined
as external events); these are not errors. `run` output:

```text
status: SUCCESS, ticks: 3, time: 0.2
events: READY, DONE
hero: s = 0.5 m, speed = 5 m/s
```

`qualified_action_modifiers.osc` produces `W0102` only for `DONE`; the body of
`c.cruise()` receives `speed(5 mps)` from outside, and the body of `c.place()`
receives `position(x: 10 m)`. `run` output:

```text
status: SUCCESS, ticks: 6, time: 0.5
events: DONE
c: speed = 5 m/s
```

Real library outputs:

```text
external\asam\standard.osc: ok

asam_stdlib.osc:17:8: warning[W0102]: unknown event 'DONE'; external domain definition not loaded
```

Real library tests: `test_asam_standard_library_parses`,
`test_asam_standard_library_has_no_diagnostics`,
`test_scenario_compiles_against_the_real_standard_library`,
`test_qualified_action_binds_to_the_actor`,
`test_qualified_action_checks_argument_types`.
New syntax tests: `test_enum_member_value_may_reference_another_member`,
`test_enum_member_reference_copies_the_value`,
`test_unknown_enum_member_reference_is_reported`,
`test_range_type_declarators_parse`,
`test_range_declarator_resolves_to_a_range_type`,
`test_primitive_type_extension_parses`,
`test_primitive_type_extension_is_reported_as_unexecuted`,
`test_field_may_share_a_name_with_a_type`,
`test_modifier_and_type_may_share_a_name`.

Compound unit tests: `test_compound_unit_literals_are_parsed`,
`test_compound_units_resolve_and_convert`,
`test_compound_unit_literals_evaluate_to_si`,
`test_unknown_compound_unit_is_reported`,
`test_offset_unit_is_rejected_in_compound_unit`.

Action tests: `test_action_call_executes_body`,
`test_action_call_binds_arguments`, `test_action_call_accepts_actor_parameter_and_defaults`,
`test_nested_action_calls_restore_the_caller_scope`,
`test_recursive_action_call_is_rejected`, `test_action_call_arguments_are_checked`.

The other diagnostics in the tables of sections 4 and 5 can also be reproduced
with the same `parse → analyze → compile` chain.

## 11. Related documents

- [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) — scope and schedule
- [`docs/SCOPE_AUDIT.md`](SCOPE_AUDIT.md) — audit of the Must/Should items
- [`docs/VALIDATION.md`](VALIDATION.md) — measurement and determinism report
- [`docs/STAGES.md`](STAGES.md) — stage-by-stage learning path
