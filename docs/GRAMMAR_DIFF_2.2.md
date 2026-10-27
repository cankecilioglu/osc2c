# ASAM OpenSCENARIO DSL 2.2.0 EBNF ↔ Project Grammar Diff — 27 October 2026

This document compares, rule by rule, the `grammar.ebnf` in the 2.2.0 package
published by ASAM with the vendored grammar used by the project. The goal is not
a "full conformance" claim; it is to classify every difference, reduce the real
gaps to a closed list, and make the remaining deviations traceable by tests. The
previous version [`GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) describes the end-to-end
coverage of language constructs; this document focuses only on differences at
the **grammar level**.

## 1. Sources

| File | Location | Size |
|---|---|---|
| 2.2.0 EBNF grammar | `external/asam/grammar.ebnf` | 459 lines, 18.615 B |
| 2.2.0 type library | `external/asam/types.osc` | 114 declarations (`namespace stdtypes`) |
| 2.2.0 domain library | `external/asam/domain.osc` | 186 declarations (`namespace std`, import of `types.osc`) |
| 2.2.0 entry point | `external/asam/standard.osc` | 2 imports, 0 declarations |
| Project grammar | [`grammar/openscenario2.g4`](../grammar/openscenario2.g4) | 333 lines (MPL-2.0 notice preserved) |

The header of the ASAM files explicitly permits distribution:

> In alteration to the regular license terms, ASAM allows unrestricted
> distribution of this standard.

Nevertheless, `external/` is still in `.gitignore`; the files were not admitted
to the repository and were used only for local validation. This policy decision
is discussed in section 8.

## 2. Method

Rule names were extracted mechanically: `^name ::=` headers for EBNF, `^name:`
headers for ANTLR; the names were then lowercased and `-` → `_` normalized. The
`#label` alternatives in ANTLR are not counted as separate rules. Result:

```text
EBNF rule            : 165
Project parser rule  : 154
Project lexer rule   : 16   (total 170)
```

At the name level there are 16 EBNF-only and 5 project-only rules. All of them
are classified one by one in section 3; since a name difference alone does not
mean a behavior difference, the real evidence is the real-library run in
section 5.

## 3. Classification of name-level differences

### 3.1 The 16 rules present only in EBNF

| EBNF rule | Counterpart in the project | Class |
|---|---|---|
| `cast-exp`, `type-test-exp`, `element-access`, `function-application` | `#cast_exp_pe`, `#type_test_exp_pe`, `#element_access_pe`, `#function_application_pe` inside `postfix_exp` ([g4:271-276](../grammar/openscenario2.g4#L271)) | Same language, different organization (ANTLR label) |
| `sum` | `sum_exp` ([g4:262](../grammar/openscenario2.g4#L262)) | Rename |
| `non-structural-type-declarator`, `structural-type-declarator` | `non_aggregate_type_declarator` + `declared_type_name` ([g4:72-73](../grammar/openscenario2.g4#L72)) | Syntactic distinction moved to the semantic layer; superset |
| `physical-type-name` | `declared_type_name` → `qualified_identifier` ([g4:73](../grammar/openscenario2.g4#L73)) | Rename |
| `digit`, `hex-digit` | `fragment DIGIT`, `fragment HEX_DIGIT` ([g4:309-310](../grammar/openscenario2.g4#L309)) | Lexer fragment |
| `int-literal` | `INT_LITERAL` ([g4:308](../grammar/openscenario2.g4#L308)) | Lexer rule |
| `shortstring`, `longstring` | `SHORTSTRING`, `LONGSTRING` ([g4:296-297](../grammar/openscenario2.g4#L296)) | Lexer rule |
| `shortstring-elem`, `longstring-elem`, `string-escape-seq` | Inline within the lexer regex ([g4:296-297](../grammar/openscenario2.g4#L296)) | Escape sequences relaxed (section 4) |

### 3.2 The 5 rules present only in the project

| Project rule | Status in EBNF | Class |
|---|---|---|
| `declared_type_name` | `physical-type-name` + all structural names via `qualified-identifier` | Merge |
| `sum_exp` | `sum` | Rename |
| `unit_expression`, `unit_term` ([g4:321-322](../grammar/openscenario2.g4#L321)) | No equivalent; `physical-literal` takes a single `unit-name` ([EBNF:457](../external/asam/grammar.ebnf#L457)) | **Intentional superset** (compound units) |
| `use_statement` ([g4:43](../grammar/openscenario2.g4#L43)) | Removed in 2.2 ([EBNF:21](../external/asam/grammar.ebnf#L21)) | **Version difference** (2.1 target) |

Result of the name-level review: of the 21 name differences, only **four** are
behavioral — compound units, top-level `use`, relaxed string escapes, and
acceptance of all type declarations in the `.as()`/`.is()` target. The rest are
renames, inlining, or lexer detail.

## 4. Version difference: 2.1 target ↔ 2.2.0 package

The project targets OpenSCENARIO **2.1**; the official package obtainable is
**2.2.0**. Known differences between the two that affect the project:

1. **Top-level `use` removed.** In 2.2, `prelude-statement ::= import-statement`
   ([EBNF:21](../external/asam/grammar.ebnf#L21)); `use` lives only inside
   `namespace X use Y` ([EBNF:36](../external/asam/grammar.ebnf#L36)).
   For 2.1 conformance the project keeps the form
   `prelude_statement: import_statement | use_statement`
   ([g4:39-43](../grammar/openscenario2.g4#L39)).
2. **Namespace names changed.** The package uses `namespace stdtypes` and
   `namespace std` (`types.osc:17`, `domain.osc:19`); in the 2.1 documents the
   root names appear as `std::stdtypes` / `std::standard`. The project's
   built-in subset and tests use the 2.2 names
   ([stdlib.py](../src/osc2c/semantics/stdlib.py)).
3. **Enum values are unsigned.** 2.2:
   `enum-member-value ::= uint-literal | hex-uint-literal | enum-value-reference`
   ([EBNF:102](../external/asam/grammar.ebnf#L102)). The project also accepts
   `integer_literal` ([g4:104](../grammar/openscenario2.g4#L104)), that is, a
   superset for negative values.
4. **Qualified behavior names are dense in the real library.** `domain.osc`
   contains more than 100 `action <actor>.<name>` declarations
   (e.g. `action vehicle.drive`, `domain.osc:1246`). The grammar supports this;
   the remaining gap in the semantic layer is in section 6.

## 5. Three real gaps closed in this pass

While parsing the real 2.2.0 library, three syntax gaps surfaced and were
closed. All three were triggered by the same failure: at the moment
`domain.osc` stopped in the parser, all 186 declarations were lost.

| # | 2.2 rule | Before | Now | Evidence |
|---|---|---|---|---|
| 1 | `enum-member-value ::= uint-literal \| hex-uint-literal \| enum-value-reference` ([EBNF:99-104](../external/asam/grammar.ebnf#L99)) | `domain.osc:430: mismatched input 'heavy_truck' expecting INTEGER_LITERAL` (enum alias `truck = heavy_truck`) | `enum_value_reference` rule ([g4:106](../grammar/openscenario2.g4#L106)); AST `EnumValueRef` ([ast.py:118](../src/osc2c/frontend/ast.py#L118)); two-pass resolution + `E0103` ([builder.py:518](../src/osc2c/semantics/builder.py#L518)) | `test_enum_member_value_may_reference_another_member`, `test_enum_member_reference_copies_the_value`, `test_unknown_enum_member_reference_is_reported` |
| 2 | `range-type-declarator ::= 'range' 'of' numeric-type-declarator` ([EBNF:112](../external/asam/grammar.ebnf#L112)) | `list of range of int` could not be parsed | `aggregate_type_declarator`, `range_type_declarator`, `numeric_type_declarator` ([g4:75-80](../grammar/openscenario2.g4#L75)); AST `RangeType` ([ast.py:234](../src/osc2c/frontend/ast.py#L234)); `RangeTypeInfo` ([builder.py:1576](../src/osc2c/semantics/builder.py#L1576)) | `test_range_type_declarators_parse`, `test_range_declarator_resolves_to_a_range_type` |
| 3 | `primitive-type-extension ::= 'extend' primitive-type ':' NEWLINE INDENT method-declaration+ DEDENT` ([EBNF:162-172](../external/asam/grammar.ebnf#L162)) | `extend float:` could not be parsed | `type_extension` with three alternatives ([g4:134-136](../grammar/openscenario2.g4#L134)); AST `PrimitiveExtensionDecl` ([ast.py:381](../src/osc2c/frontend/ast.py#L381)); methods are registered, and because they are not executed they are reported with `W0106` ([builder.py:843](../src/osc2c/semantics/builder.py#L843)) | `test_primitive_type_extension_parses`, `test_primitive_type_extension_is_reported_as_unexecuted` |

In addition, two semantic errors that prevented the library from loading were
fixed (details and diagnostic codes in
[`GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) §8):

- **Field/type shadowing:** when field names shadowed types,
  `E0202 '<x>' is a parameter, not type` was produced; type-aware lexical
  lookup was added.
- **Unqualified enum member ambiguity:** `keep(default it == other)` produced
  `E0404`; resolution by the expected type (`_infer_with_hint`) was added.
- **`actor` context:** in action bodies, `keep(default it == actor)` produced
  `E0402`; `actor` is now accepted as opaque inside an action body.
- **Modifier/type name collision:** when `struct lane` and `modifier lane`
  shared the same name, `E0101` occurred; modifiers are now kept in a separate
  dictionary ([scope.py](../src/osc2c/semantics/scope.py)).
- **Built-in + real library collision:** when both were installed together, all
  symbols produced `E0101`; when the real library is detected the built-in
  subset is not installed and no implicit `traffic_participant` base is added
  to actors ([builder.py](../src/osc2c/semantics/builder.py)).

## 6. Binding qualified behavior names to the target type

The grammar accepts the `<actor>.<behavior>` form and `domain.osc` uses it in
48 declarations (`action vehicle.drive`, `action environment.air`, etc.).
Previously the semantic layer stored these declarations as a single-part name
in the `std` namespace, `vehicle.methods` stayed empty, and all calls got
`W0105 unknown behavior or method`:

```text
hero.drive()   -> W0105
hero.assign_position() -> W0105
```

In this pass, `_attach_qualified_actions` was added at the end of
`_resolve_signatures`
([builder.py:904](../src/osc2c/semantics/builder.py#L904)): an `action A.b`
declaration is bound to the `methods` table of actor `A` in the same namespace
under the name `b`. Since inheritance already goes through `_lookup_member`,
base behaviors such as `movable_object.change_speed` are also visible through
`vehicle`. Verified behavior:

```text
hero.drive()                        -> no diagnostics
hero.assign_position()              -> no diagnostics
hero.change_speed(target: 5)        -> E0401 argument 'target' expects speed, got int
hero.change_speed(target_speed: 5 mps) -> E0406 no argument named 'target_speed'
hero.fly_away()                     -> W0105 (correct: undefined)
```

**Deliberate limit:** in the 2.2 library, whether a parameter of an action is
mandatory or optional is written only in a comment line (`# Mandatory`,
`# Optional`); because the lexer discards comments, this information cannot be
read by machine. Therefore, in actions bound from the library and in standard
modifiers, a missing argument is not counted as an error; the name and type of
provided arguments are checked. In the user's own `action` declarations, the
existing strict checking (`E0405`) is preserved. The relaxation applies only to
the `std`/`stdtypes` namespaces
([builder.py:185](../src/osc2c/semantics/builder.py#L185)).

### 6.1 Execution in the backend

Binding is now not only semantic but also executable. Backend order:

1. If the method resolved on the target is an `action` declaration and the
   declaration (or its base) has a `do`/`on` body, the body is compiled into
   the behavior tree; parameters, local `var`s and `it` are bound at call time
   ([compiler.py:307](../src/osc2c/backend/compiler.py#L307)). `it` denotes the
   actor receiving the action; the semantic layer also types `it` as this actor
   in action bodies
   ([builder.py:1187](../src/osc2c/semantics/builder.py#L1187)).
2. Library actions without a body lower by name to the simulator registry.
   Alongside `drive`, `walk`, `change_speed`, `assign_position`,
   `change_lane`, `set_lights`, `assign_celestial_position`, `move`,
   `assign_speed`, `keep_speed` and `remain_stationary` were added in this pass
   ([method_registry.py:122](../src/osc2c/backend/method_registry.py#L122)).
3. An action with no mapping (`follow_trajectory`, `connect_trailer`, ...) is
   not silently swallowed: a compile warning and a `FAILURE` leaf are produced.
4. Standard `with:` modifiers applied to an action with a body are evaluated at
   call time and kept as ambient modifiers for the duration of the action body.
   Registry behaviors with the `it` receiver in the body (`drive`,
   `assign_position`, ...) inherit these values; if an inner `with:` overrides
   the same name the inner value wins, and a call made on a different actor is
   unaffected ([compiler.py:373](../src/osc2c/backend/compiler.py#L373),
   [behaviors.py:88](../src/osc2c/backend/behaviors.py#L88),
   [method_registry.py:78](../src/osc2c/backend/method_registry.py#L78)).
5. User-defined modifiers are flattened at compile time: standard applications
   in the body are transferred to direct behaviors, qualified action bodies and
   the `at: start` promotion. Source order is preserved (the last application
   wins), and cycles and unsupported body members are reported with a warning
   ([modifiers.py](../src/osc2c/backend/modifiers.py)). `until` expressions
   inside actions work.

Observed results (MockAdapter, 27 October 2026):

```text
action timer.hold + t.hold(span: 200 ms)          -> SUCCESS, 0.2 s
action cruiser.cruise: it.drive() with speed(5 mps) -> SUCCESS, speed 5 mps
c.cruise() with: speed(5 mps) (body: it.drive())   -> SUCCESS, speed 5 mps
c.cruise() with: speed(5 mps), inner speed(3 mps)  -> SUCCESS, speed 3 mps
c.escort(n) with: speed(5 mps) (it + n driving)    -> c 5 mps, n 0 mps
c.place() with: position(x: 10 m)                   -> SUCCESS, x 10 m
hero.drive() with: speed(10 mps) until elapsed(500 ms) -> SUCCESS, 5 m speed 10 mps
hero.assign_speed(speed: 5 mps)                   -> SUCCESS, speed 5 mps
hero.move() with: speed(4 mps) until elapsed(300 ms)   -> SUCCESS, 1.2 m speed 4 mps
hero.drive() with: fast() (fast -> speed(10 mps))  -> SUCCESS, speed 10 mps
c.boost() with: fast() (body: it.drive())          -> SUCCESS, speed 10 mps
hero.assign_position() with: start_fast() (at: start) -> SUCCESS, pre-applied, speed 5 mps
a() where a -> b -> a                              -> cycle warning, execution continues
hero.follow_trajectory()                          -> warning + FAILURE
```

Because `_action_stack` is also used for qualified actions, self-recursion
(`action looper.loop: it.loop()`) gives `CompilationError` at compile time.

## 7. Validation

When the real library is loaded by resolving the import chain (the CLI's
`_load_unit` behavior), the symbol tables are:

```text
stdtypes : 112 symbols
std      : 154 symbols
diagnostics : 0
```

CLI outputs:

```text
> osc2c check external\asam\standard.osc
external\asam\standard.osc: ok                      (exit 0)

> osc2c check scenarios\asam\asam_stdlib.osc --stdlib external\asam\standard.osc
asam_stdlib.osc:17:8: warning[W0102]: unknown event 'DONE'; external domain definition not loaded
                                                    (exit 0)

> osc2c bt scenarios\asam\asam_stdlib.osc --stdlib external\asam\standard.osc
  -> ActionLeaf hero.drive + ActionLeaf hero.assign_speed + EmitLeaf emit DONE
```

`scenarios/asam/asam_stdlib.osc` exercises the following against the real
library: `vehicle` inheritance, qualified action resolution and execution via
`hero.drive() with: speed(5 mps)` and `hero.assign_speed(speed: 0 mps)`,
`range of length`, `list of speed`, `list of range of int`, enum resolution by
type (`vehicle_category = car`) and inherited field reading via
`it.rear_overhang`. The only warning is the `DONE` event not defined in the
scenario; it is not an error.

Test status (27 October 2026):

```text
pytest -q -m "not carla"  ->  169 passed, 3 deselected
test_backend.py           ->   59 passed
test_semantics.py         ->   64 passed
test_frontend_ast.py      ->   27 passed
compileall + pip check    ->  clean
```

Tests that depend on the real library are skipped with `skipif` if
`external/asam/standard.osc` is absent; the repository stays green without
`external/`.

## 8. Decision: `external/asam/` stays out of the repository

The ASAM package header permits unrestricted distribution, but the project
does not redistribute the standard. `external/` is gitignored,
[`NOTICE`](../NOTICE) and [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)
state that the files are not included, and the real-library tests are skipped
when the files are absent.

Consequences: the results in section 7 are fully reproducible only on a machine
where the ASAM package has been placed under `external/asam/`; everything else
is reproducible from a clone.

## 9. Reproduction

```bash
cd osc2c
.venv\Scripts\python.exe -m pytest -q -m "not carla"
.venv\Scripts\osc2c.exe check external\asam\standard.osc
.venv\Scripts\osc2c.exe check scenarios\asam\asam_stdlib.osc --stdlib external\asam\standard.osc

# Re-extract the rule inventory (section 2)
.venv\Scripts\python.exe - <<'PY'
import re
from pathlib import Path
ebnf = Path("external/asam/grammar.ebnf").read_text(encoding="utf-8")
g4 = Path("grammar/openscenario2.g4").read_text(encoding="utf-8")
g4 = re.sub(r"//.*", "", g4)
rules = re.findall(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*\n?\s*:", g4, re.M)
print("EBNF:", len(re.findall(r"^([A-Za-z][A-Za-z0-9-]*)\s*::=", ebnf, re.M)),
      "| parser:", len([r for r in rules if not r.isupper()]),
      "| lexer:", len([r for r in rules if r.isupper()]))
PY
```

## 10. Related documents

- [`GRAMMAR_GAPS.md`](GRAMMAR_GAPS.md) — end-to-end coverage of language constructs
- [`STAGES.md`](STAGES.md) — stage-by-stage learning path
- [`SCOPE_AUDIT.md`](SCOPE_AUDIT.md) — audit of the Must/Should items
- [`VALIDATION.md`](VALIDATION.md) — measurement and determinism report
