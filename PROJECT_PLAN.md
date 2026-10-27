# Capstone Project Plan — OSC2C: OpenSCENARIO 2.1 → CARLA Compiler

**Version:** 1.0
**Date:** 26 October 2026
**Target:** A working, tested, open-source implementation of the paper by 31 January 2027; thesis period from February 2027.

---

## 0. Executive summary

The paper describes a three-stage compiler that translates the ASAM OpenSCENARIO 2.1 DSL into py_trees behavior trees executable in the CARLA simulator:

1. **Frontend:** lexing/parsing with ANTLR4 → typed AST
2. **Middle-end:** symbol table, scope resolution, type/unit validation
3. **Backend/runtime:** py_trees generation, MethodRegistry, ExecutionContext, CARLA adapter

The paper's code and grammar have not been published. The project is therefore a **from-scratch, open-source and reproducible** reconstruction of the described architecture. The goal by the end of January is to run a selected subset of the paper's Table 2 capability matrix and the cut-in scenario from Listings 1–3 end to end.

**Core strategy:** leave CARLA for last; develop and test the bulk of the compiler with a `MockAdapter`, without a simulator. That way, installation/performance risk cannot block the project.

---

## 1. What does "open-source reconstruction" mean?

The paper only describes the architecture; it provides no code. "Open-source reconstruction" means the following:

- Writing the described system **with your own code**.
- Making the code **something others can download and run**, together with the README, license, tests and setup steps.
- Using existing open-source components (py-osc2 grammar, py_trees, CARLA) and attributing them.
- Choosing a license for your own code (MIT).
- Not "copying", but delivering a **transparent, reproducible and measurable** implementation.

The value for the thesis: presenting a working, validated and reproducible implementation of a method for which no code exists in the literature. The repository may stay **private** until thesis submission and be made public afterwards.

---

## 2. Scope

### 2.1 Until the end of January — Must (mandatory)

> **Implementation status (26 October 2026):** This list is the January target; the scope actually
> delivered at the end of Stage 5 and the deliberate deferrals are tracked item by item in
> [`docs/SCOPE_AUDIT.md`](docs/SCOPE_AUDIT.md). The Grammar 2.1 gap analysis was completed in
> [`docs/GRAMMAR_GAPS.md`](docs/GRAMMAR_GAPS.md). Deferrals are not silently ignored: when used,
> they produce a semantic error or an `unsupported` warning.

**Language / frontend**
- `import`, `use`, `scenario`
- Actor definitions: `vehicle`, `environment` (`stationary_object` and `map`
  deferred — see scope audit)
- `keep(...)` constraints (actor field equality)
- `var` and physical units: `kph`, `mph`, `m/s`, `m`, `s`, `deg`, `rad`
- `with` blocks and modifiers: `at`, `side`, `side_of`, `behind`,
  `distance`, `speed`, `lane`, `position` (`rate_profile` deferred)
- Composition: `do serial`, `do parallel`, `serial`, `parallel`, `one_of`
- Events: `wait`, `rise`, `fall`, `elapsed`, `emit`, `@event`
- Error messages with source locations

**Semantics**
- Global and nested scopes (namespace, struct, actor, method)
- Two-pass resolution: definition pass + resolution pass
- Inheritance: `vehicle` → `traffic_participant`
- Physical type system and unit conversion
- `stdtypes` / `domain.osc` fallback resolution
- Positive and negative tests (undefined symbol, type error, unit error, invalid modifier)

**Runtime / backend**
- Expression evaluator and unit conversions
- Actor lookup cache (O(1))
- Distinction between `ahead_of` (topological/OpenDRIVE) and `object_distance(direction: euclidean)`
- Event blackboard, `rise`/`fall` edge detection
- py_trees: `Sequence`, `Parallel`, `Selector` (`SuccessOnOne`); automatic
  timeout wrappers deferred (manual `wait elapsed(...)` can be used)
- MethodRegistry and atomic behaviors:
  - `drive` / waypoint following
  - `change_speed` (proportional speed control; PID deferred)
  - `change_lane` (OpenDRIVE lane offsets)
  - `assign_position` (lane / relative / absolute)
  - `set_lights`
  - `assign_celestial_position`
- `ScenarioInitializer`: 3 placement modes (default map, relative topological, absolute Cartesian)
- `role_name` mapping

**CARLA**
- Synchronous mode, fixed `fixed_delta_seconds`
- Actor spawn/teleport
- Running the Listing 1–3 cut-in scenario
- Demo video (at submission stage)

**Validation**
- 5 scenarios end to end on the mock backend
- 1 scenario (cut-in) in CARLA
- Determinism over 20 repetitions (trace hash)
- Compile-time and per-tick latency measurement
- Table 2 coverage matrix (supported / partial / unsupported + test link)

#### 2.1.1 Frontend reality (26 October verification)

The installed py-osc2 0.1.0 grammar is at the OSC 2.0 level. Verified state:

- **Working:** `scenario`, `vehicle`, `keep`, `var`, `at:`, `side_of`, `one_of`, `serial/parallel`, `rise/fall`, `emit`, `wait @event`, `with` blocks.
- **Gap:** A file-level `use std.stdtypes` (in the grammar it exists only inside a namespace).
- **Discrepancy:** A spaced physical literal such as `35 kph` does not match as a single token; `35kph` works. Which spelling to use in the sources will be clarified.
- **Spike result (26 October):** The grammar was extended on an MPL-2.0 basis; top-level `use` and spaced physical literal rules were added and regenerated with ANTLR 4.13.2. Paper-style nested `serial/parallel`, `emit`, `wait elapsed` and expressions with units parse with 0 errors. The py-osc2 dependency was removed; the grammar was vendored into the project (with an MPL-2.0 notice). The remaining 2.1 gaps were scanned in W2; the result is in [`docs/GRAMMAR_GAPS.md`](docs/GRAMMAR_GAPS.md). Compound units (`m/s`, `km/h`, `m/s^2`) were added to the grammar, the semantic layer and the runtime.

### 2.2 Should (if time permits)

- Weather (rain, fog), traffic lights
- `follow_path`, `follow_trajectory`
- Time gap / space gap / headway
- Orientation modifiers
- Comparison with a hand-written CARLA script
- ScenarioRunner comparison (optional)

### 2.3 Out of scope until the end of January

- Full OSC 2.1 ontology
- Pedestrian intent, intersection right of way
- Probabilistic weather
- ROS 2 integration
- Scenario generation with an LLM
- C++ optimization

These items are reported explicitly with an "unsupported" diagnostic; they are not silently ignored.

### 2.4 Thesis period (February–June 2027)

- Scope expansion: pedestrians, intersections, KPI computation
- Full evaluation and thesis writing
- Optional extension: LLM → OSC 2.1 → CARLA pipeline
- Optional: paper/workshop submission

---

## 3. Architecture

```text
.osc2 source
    │
    ▼
[Frontend]  ANTLR4 parser + ASTTransformer
    │        → typed AST, source locations
    ▼
[Middle-end]  SymbolTable + Resolver + TypeSystem
    │        → annotated AST + GlobalScope
    ▼
[Backend]  BehaviorTreeBuilder + MethodRegistry
    │        → py_trees behavior tree
    ▼
[Runtime]  ExecutionContext + event blackboard
    │
    ├── MockAdapter   (test/CI, no simulator)
    └── CarlaAdapter  (demo/measurement)
```

Repository skeleton:

```text
osc2c/
├─ QODER.md
├─ README.md
├─ LICENSE
├─ NOTICE
├─ THIRD_PARTY_NOTICES.md
├─ CITATION.cff
├─ LICENSES/MPL-2.0.txt
├─ grammar/openscenario2.g4        # py-osc2 (MPL-2.0) reference
├─ external/asam/                   # ASAM 2.2.0 files (gitignored, not redistributed)
├─ src/osc2c/
│  ├─ frontend/    parser, ast, transformer
│  ├─ semantics/   symbols, types, units, resolver
│  ├─ backend/     bt_builder, registry, initializer
│  ├─ runtime/     context, events, atomic_behaviors
│  └─ adapters/    base.py, carla.py, mock.py
├─ scenarios/
├─ tests/           unit + golden + e2e
└─ tools/           bench.py, coverage.py
```

---

## 4. 14-week schedule (26 October 2026 – 31 January 2027)

| Week | Date | Focus | Output / gate |
|---|---|---|---|
| W1 | 26 Oct – 1 Nov | Plan, environment, repo, parse spike | Python/Java/CARLA installed; Listing 1 parsed and AST dumped (G0) |
| W2 | 2 – 8 Nov | Grammar gap analysis; top-level `use` and physical literal rules; AST nodes | Extended grammar; Listings 1–3 parse; gap analysis in `docs/GRAMMAR_GAPS.md` |
| W3 | 9 – 15 Nov | ASTTransformer, diagnostics, golden tests | 10 parser tests; G1: all listings parse |
| W4 | 16 – 22 Nov | Symbol table, scopes, definition pass | Symbol table tests |
| W5 | 23 – 29 Nov | Resolution pass, inheritance, type/unit system, stdtypes | Type/unit resolution working |
| W6 | 30 Nov – 6 Dec | Expression evaluator, unit conversions, negative tests | G2: listings semantically valid; 15 negative tests |
| W7 | 7 – 13 Dec | BT builder, event blackboard, edge detection, mock skeleton | BT composites tested |
| W8 | 14 – 20 Dec | Mock atomic behaviors + Listings 1–3 end to end | G3: mock e2e green; trace assertions |
| W9 | 21 – 27 Dec | Holiday / exams / buffer / CARLA installation attempts | CARLA smoke test |
| W10 | 28 Dec – 3 Jan | New Year / buffer / documentation | Optional early CARLA adapter |
| W11 | 4 – 10 Jan | CARLA adapter, initializer, 3 placement modes, role_name | G4a: actors in the correct position |
| W12 | 11 – 17 Jan | CARLA atomic behaviors, cut-in scenario, camera | G4b: cut-in runs in CARLA |
| W13 | 18 – 24 Jan | 5-scenario validation, determinism, benchmark, baseline | Measurement report draft |
| W14 | 25 – 31 Jan | Freeze, README/license/CI, demo video, v0.1 tag | G5: submission package + demo |

**Buffer:** W9–W10 are a two-week buffer. If exams/holidays cause slippage, the "Could" items and the ScenarioRunner comparison are dropped; cut-in + mock validation are retained.

**Go/No-Go:** If mock e2e is not working at the end of W8, the scope is narrowed: only cut-in is shown in CARLA, and the Should items of Table 2 are left to the thesis period.

---

## 5. Validation plan

### 5.1 Test layers

1. **Parser tests:** Valid/invalid `.osc` files, error location and message.
2. **Golden AST tests:** AST JSON snapshots; regression capture.
3. **Semantic tests:** Undefined symbol, type mismatch, unit mismatch, invalid modifier, inheritance.
4. **Golden BT tests:** JSON dump of the generated py_trees structure.
5. **Mock e2e:** 5 scenarios; event order, position/speed assertions.
6. **CARLA e2e:** Cut-in scenario; 20 repetitions; determinism via trace hash.
7. **Performance:** Compile time (per scenario), per-tick latency (ms), memory.
8. **Coverage:** Table 2 matrix; each cell has a test link or an "unsupported" rationale.

### 5.2 Scenario set

| ID | Scenario | Purpose |
|---|---|---|
| S1 | `cut_in_evasive.osc` | The paper's Listings 1–3; multi-actor event synchronization |
| S2 | `lane_change_speed.osc` | `change_lane` + PID speed profile |
| S3 | `event_handshake.osc` | `emit` / `wait @event`; two actors |
| S4 | `placement_modes.osc` | Default / relative / absolute placement |
| S5 | `environment_lights.osc` | Dusk, lights, weather |
| N1 | `semantic_errors/` | Negative diagnostic tests |

### 5.3 Measurements

- **Determinism:** The hashes of the tick-based position/speed traces must be identical across 20 repetitions (fixed dt, fixed seed, synchronous mode).
- **Performance:** Comparison with a hand-written CARLA Python script; ScenarioRunner comparison if time permits.
- **KPI:** Number of collisions, minimum distance, minimum TTC, scenario completion.
- **Coverage:** What percentage of Table 2 is supported; the list of unsupported items.

---

## 6. Deliverables

| ID | Deliverable | Date |
|---|---|---|
| D1 | This plan | 26 Oct 2026 |
| D2 | Environment + repo skeleton + `QODER.md` | W1 |
| D3 | Frontend (extended 2.1 grammar) + parser tests | W3 |
| D4 | Semantic resolver + negative tests | W6 |
| D5 | BT + mock runtime + Listings 1–3 e2e | W8 |
| D6 | CARLA adapter + cut-in demo | W12 |
| D7 | Validation report + benchmark | W13 |
| D8 | v0.1 open-source release candidate + demo video + thesis handover document | W14 |

---

## 7. Open source and license plan

- **Own code:** MIT. Copyright (c) 2026 Can Kecilioglu. The full MIT text is in the [`LICENSE`](LICENSE) file at the repository root.
- **Third-party grammar/parser:** the vendored py-osc2 grammar and the generated ANTLR parser files remain MPL-2.0; see [`NOTICE`](NOTICE) for the per-file list and the record of modifications, and [`LICENSES/MPL-2.0.txt`](LICENSES/MPL-2.0.txt) for the full license text.
- **Other third parties:** the ANTLR tool jar (BSD-3-Clause) and the Python runtime dependencies (`antlr4-python3-runtime`, `py_trees`, `numpy`, all BSD-3-Clause) are listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). None of the runtime dependencies are vendored.
- **ASAM `types.osc` / `domain.osc`:** Not redistributed. The files are kept locally under `external/asam/`, which is gitignored; users download the package from ASAM and bind it with `osc2c check|bt|run --stdlib <file>` (see [`docs/GRAMMAR_DIFF_2.2.md`](docs/GRAMMAR_DIFF_2.2.md) §8).
- **CARLA:** Subject to its own license; no binaries are placed in the repository.
- **Citation:** If you use this compiler, please cite the paper it reproduces; see [`CITATION.cff`](CITATION.cff) and the `## Citation` section of the README.
- **Publication:** The repository may stay private during development until thesis submission, and be made public afterwards together with the `v0.1` tag.
- **Attribution:** The paper, py-osc2, CARLA, py_trees, ASAM OpenSCENARIO 2.1.

---

## 8. Risks and mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| CARLA installation/AMD performance | High | Mock-first; `-quality-level=Low`, low resolution, off-screen; Linux/cloud if necessary |
| Scope creep | High | Must/Should/Could; Table 2 subset; "unsupported" diagnostic |
| py-osc2 grammar at the 2.0 level | Low (closed) | Mechanical diff against ASAM 2.2.0 `grammar.ebnf` (165 EBNF / 154 parser rules); three gaps closed. Details: `docs/GRAMMAR_DIFF_2.2.md` |
| Access to ASAM standard files | Low | The 2.2.0 package is available under `external/asam/` and loads without diagnostics via `--stdlib`; the built-in subset remains active even without access |
| Unit/event semantic bugs | Medium | Golden tests; paper examples; negative tests |
| Time (exams/holidays) | Medium | W9–W10 buffer; W8 go/no-go |
| Publication timing | Low/Medium | Private development; published after thesis submission |
| Thesis originality | Medium | Validation + reproducibility + mock backend + (optional) LLM extension |

---

## 9. Open questions

1. When should the repository be made public?
2. Which OSC 2.1 capabilities/scenarios are the priority?
3. Will the ASAM standard files and their license be made available?
4. What are the submission/demo format and the acceptance criteria?
5. Is a ScenarioRunner comparison expected?
6. Should integration with external scenario-authoring tools be considered, or is CARLA-only support sufficient?

---

## 10. Environment setup (as performed)

1. Python 3.12.15 (uv standalone; the system 3.15 is not used)
2. JDK 17 (for the ANTLR tool)
3. CARLA 0.9.16 Windows package (`C:\CARLA_0.9.16`)
4. Git + VS Code/Qoder
5. Project venv: `python -m venv .venv`
6. `pip install -e ".[dev]"` (dependencies: `antlr4-python3-runtime`, `py-trees`, `pytest`, `pytest-cov`)
7. Verification:
   - `python -c "import carla; print(carla.__version__)"`
   - `osc2c --help`
   - Opening `Town10HD_Opt` with `CarlaUE4.exe`
8. CARLA performance settings: low quality, 1280×720, fixed `fixed_delta_seconds=0.05`

Details and version verification: [`ENVIRONMENT.md`](ENVIRONMENT.md).

---

## 11. Definition of success

**Minimum success (end of January):**
- The cut-in scenario runs in CARLA.
- 5 scenarios pass on the mock backend.
- Determinism is proven over 20 repetitions.
- Table 2 coverage matrix and validation report are ready.
- The repository is deliverable with README, license and tests.

**Target success:**
- The above + 2 Should scenarios + comparison against a hand-written CARLA baseline + public v0.1.

**Extension (thesis period):**
- LLM → OSC 2.1 → CARLA pipeline, KPI-based automatic evaluation, paper.
