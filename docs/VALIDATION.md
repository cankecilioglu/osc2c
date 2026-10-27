# Stage 5 — Validation and Measurement Report

This report shows, with measurable evidence, how far the OSC2 → CARLA compiler
meets the claims in the paper. It seeks answers to three questions:

1. **Does it work correctly?** Do the scenarios produce the expected events, and
   are the geometric conditions satisfied?
2. **Is it reproducible?** Does the same input produce the same trace?
3. **What does it cost?** How different are compilation and tick latency
   compared with a hand-written CARLA control group?

The measurements were taken on 2026-10-26 on a single machine. Raw data is under
[`docs/measurements/`](measurements/).

## 1. Measurement environment

| Component | Value |
| --- | --- |
| Python | 3.12 (venv) |
| CARLA | 0.9.16, `Town10HD_Opt` |
| Simulation step | 0.05 s (CARLA), 0.1 s (mock) |
| Spawn index | 20 (in the list sorted by left-lane visibility) |
| Connection | `127.0.0.1:2000`, synchronous mode |
| Trace repetition | 20 (mock and CARLA), 20 compile repetitions (mock) |

The CARLA measurement connects to the same server process in succession; `close()`
destroys the actors after every run and restores the settings/weather values.

## 2. Scenario set and mock results

Five scenarios were run on `MockAdapter` without CARLA. Each scenario was
repeated 20 times.

| ID | Scenario | Status | Tick | Duration | Events | Trace hash (first 12) |
| --- | --- | --- | ---: | ---: | --- | --- |
| S1 | `scenarios/carla/cut_in.osc` | SUCCESS | 41 | 4.0 s | `CUT_IN` | `4c0cdd1fccd7` |
| S2 | `scenarios/dev/lane_change_speed.osc` | SUCCESS | 13 | 1.2 s | `LANE_CHANGED`, `DONE` | `a7f99db0c475` |
| S3 | `scenarios/dev/event_handshake.osc` | SUCCESS | 4 | 0.3 s | `PING`, `PONG`, `DONE` | `8ce2b96b79bf` |
| S4 | `scenarios/dev/placement_modes.osc` | SUCCESS | 3 | 0.2 s | `PLACED` | `4671bbc0b97b` |
| S5 | `scenarios/dev/environment_lights.osc` | SUCCESS | 13 | 1.2 s | `NIGHT_MODE` | `0de7509b017e` |

In every scenario the expected event set matched exactly; the unsupported
construct (`unsupported`) list stayed empty. This also shows that the "no silent
ignoring" policy works: if there had been an unsupported node, it would have
appeared as a compile warning and a `FAILED` leaf.

Features covered by the scenarios:

- **S1:** durative `drive`, `one_of`, `change_lane`, event, brake, light.
- **S2:** lane change + `speed(at:)` modifier.
- **S3:** `emit` / `wait @event` handshake between two parallel branches.
- **S4:** absolute `x/y/z`, relative `ahead_of` + `distance`, `behind` placement.
- **S5:** sun angle, automatic/high beam, and speed change.

## 3. Determinism

### Method

On every tick, the actors' `s`, lane, speed, light, and `x/y/z` values are rounded
to 6 decimal places and written into an ordered JSON structure. The SHA-256 digest
of the whole tick sequence is the **trace hash**. For the same scenario, the
hashes of 20 runs are compared.

### Results

| Environment | Scenario | Runs | Unique hashes | Result |
| --- | --- | ---: | ---: | --- |
| Mock | 5 scenarios | 20 × 5 | 1 (per scenario) | deterministic |
| CARLA | cut-in | 20 | 1 | deterministic |

CARLA hash:
`afaf910cd26b9c675f048d368ff177dce6a1132309df22031e836474a3f9c79b`

This result shows that synchronous mode + fixed `fixed_delta_seconds` + the same
spawn point produce the same physics steps. Core determinism of the physics
engine is not guaranteed; the determinism observed here holds under the same
machine, the same server, and the same version.

### 2026-10-27 reproduction note

The measurements were repeated independently on the same machine; raw evidence is
under [`docs/measurements/2026-10-27/`](measurements/2026-10-27/).

| Measurement | 2026-10-26 | 2026-10-27 | Assessment |
| --- | --- | --- | --- |
| Mock trace hashes (5 scenarios) | 5 fixed hashes | exactly the same | reproduced |
| Mock compile times | 2.63–75.19 ms | 2.61–90.25 ms | depends on machine load, varies |
| CARLA success | 20/20 | 20/20 + 20/20 (two sessions) | reproduced |
| CARLA geometry | 20/20 | 20/20 + 20/20 | reproduced |
| CARLA unique hash | 1 | 1st session **2**, 2nd session 1 | partially reproduced |

In the first CARLA session, 19 of the 20 runs produced the `afaf910c...` hash and
1 produced `8d185e5f...`. The only difference between the two traces was the
`hero_speed` value in one tick: `2.96676` m/s instead of `2.966754` (about
`6 × 10⁻⁶`). All runs passed `SUCCESS`, `CUT_IN`, and the geometry checks 20/20;
the KPIs remained the same at the reported sensitivity. In the second session,
20/20 runs produced the same hash.

**Conclusion:** Bit-level trace determinism was reproduced for the mock. For
CARLA, behavioral and geometric determinism were reproduced, but bit-level trace
hash determinism is not guaranteed. In the thesis these two claims must be kept
apart: "same behavior" is supported, "always the same hash" is not supported for
CARLA.

## 4. Mock performance

Median of 20 compile repetitions:

| ID | Parse (ms) | Analysis (ms) | BT compilation (ms) | Total (ms) | Tick p95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| S1 | 74.69 | 0.30 | 0.19 | 75.19 | 0.0191 |
| S2 | 58.63 | 0.35 | 0.14 | 59.06 | 0.0241 |
| S3 | 2.34 | 0.19 | 0.08 | 2.63 | 0.0296 |
| S4 | 29.36 | 0.34 | 0.11 | 29.77 | 0.0132 |
| S5 | 70.76 | 0.23 | 0.11 | 71.13 | 0.0126 |

**Comment:** Time is dominated by the parser. ANTLR's adaptive prediction
varies markedly with file content in physical-literal and indentation decisions:
S3, of the same order of magnitude, parses in 2.34 ms while S1 takes 74.69 ms.
Analysis and BT generation account for less than 1% of the total. Runtime tick
latency is on the order of 0.01–0.03 ms; not a bottleneck for the mock.

This is a **performance finding** that should be reported: compilation time
depends much more on the parser's ambiguity resolution than on scenario size. In
the future it could be improved with left-factoring / precedence tuning or a
two-stage lexer; in this project, correctness and determinism were prioritized.

## 5. CARLA cut-in results (20 runs)

| Metric | Value |
| --- | --- |
| Success | 20/20 |
| `CUT_IN` detection | 20/20 |
| Geometry check | 20/20 |
| Unique trace hash | 1 |
| Tick count | 108 (all runs) |
| Simulation duration | 5.35 s |
| `CUT_IN` time | 3.25 s (median, p95, min, max identical) |
| \|lateral\| deviation at event | 1.2978 m |
| Heading difference at event | 6.7218° |
| `ahead_of` at event | −12.1548 m (still ahead) |
| Initial lateral deviation | −3.5 m (one lane to the left) |
| Minimum distance | 11.938 m |
| Minimum TTC | 24.4897 s |
| Collision | 0 |
| Tick latency (median) | 5.4528 ms |
| Tick latency (p95) | 5.4997 ms |

**Geometry check** requires two conditions: at the `CUT_IN` moment |lateral
deviation| < 2.2 m (the vehicle is in the target lane) and `ahead_of` negative
(the NPC is still ahead of the hero). Both were satisfied in 20/20 runs.

### Compilation time

| Stage | Median | Note |
| --- | ---: | --- |
| Parse | 113.2 ms | first run 344.2 ms |
| Analysis | 0.40 ms | stable |
| BT compilation | 15.95 ms | first run 4032.9 ms |
| Total | 129.8 ms | first run 4377.5 ms |

The 4.03 s BT compilation spike in the first CARLA run is a one-time cost of the
first use of the CARLA Python client and the blueprint library; in the following
19 runs, BT compilation is in the 15.3–26.0 ms range. The reported
"steady-state" value is therefore 129.8 ms; the mean (217.3 ms) is pulled up by
the first run.

## 6. Comparison with a hand-written CARLA baseline

`tools/baseline_carla.py` is an independent control group that does not use the
compiler: it drives two vehicles at the same map and spawn point directly through
the CARLA API, applies pure-pursuit steering and proportional speed control,
changes the NPC's lane after 2 s, and brakes the hero after 3.2 s. Five runs were
taken.

| Metric | Compiler (20 runs) | Baseline (5 runs) |
| --- | ---: | ---: |
| Success | 20/20 | 5/5 |
| `CUT_IN` time | 3.25 s | 4.25 s |
| \|lateral\| deviation | 1.298 m | 1.701 m |
| Heading difference | 6.72° | 7.17° |
| `ahead_of` | −12.155 m | −11.478 m |
| Minimum distance | 11.938 m | 8.272 m |
| Minimum TTC | 24.49 s | 4.43 s |
| Collision | 0 | 0 |
| Tick latency (median) | 5.453 ms | 5.249 ms |
| Full cycle (median) | — | 5.375 ms |

**Comment:**

- The compiler's tick cost is very close to the baseline's full cycle (engine
  tick + control computation): 5.453 ms versus 5.375 ms, a difference of about
  **1.4%**. Against a raw engine tick the difference is 3.9%; this is the cost of
  BT ticking and expression evaluation, on the order of 0.2 ms.
- The compiler completes the cut-in earlier (3.25 s) and reports a smaller
  lateral/heading deviation at the event. This is not a claim of "better driving":
  the two implementations' speed profiles, lane-change trigger, and completion
  criterion are not exactly the same. The baseline is a **measurement control**
  against the behavior produced by the compiler, not an algorithmic equivalent.
- The minimum distance and TTC difference is large for the same reason: the
  baseline keeps the hero at constant speed for longer, while the compiler applies
  the brake earlier after the event.

## 7. Coverage matrix (paper Table 2)

The marks in Table 2 of the paper could not be extracted reliably from the PDF
(no `pdftoppm` in the environment). Instead, an explicit matrix was built that
maps each row to **running evidence**:
[`docs/measurements/coverage.md`](measurements/coverage.md).

| Category | Supported | Partial | Unsupported |
| --- | ---: | ---: | ---: |
| Action framework | 3 | 1 | 0 |
| Movement | 2 | 2 | 1 |
| Position & path | 2 | 2 | 3 |
| Environment | 1 | 0 | 3 |
| Modifiers | 5 | 2 | 1 |
| Coordinate systems | 2 | 1 | 1 |
| Scenario composition | 9 | 2 | 0 |
| **Total (43)** | **24** | **10** | **9** |

- Strict ratio (only `supported`): **56%**
- Weighted ratio (`supported` = 1, `partial` = 0.5): **67%**

Every row has a status, an evidence file/test, and a rationale. `tools/coverage.py`
validates the matrix: it reports an invalid status, a non-existent evidence path,
a non-existent test function, a duplicate row, or an `unsupported` row without a
rationale.

**Main unsupported items:** acceleration control/modifier, route and trajectory
following, time gap, traffic lights, weather/road condition, physical driving mode
switch. These are not silently ignored; if used, a compile warning and a `FAILED`
leaf are produced.

## 8. Test status

| Suite | Command | Result |
| --- | --- | --- |
| Without CARLA | `pytest -q -m "not carla"` | 169 passed |
| CARLA | `pytest -q -m carla` | 3 passed |
| Total | `pytest -q` | 172 (3 marked CARLA) |

These numbers are after the 27 October 2026 grammar/stdlib transition, the
qualified action execution fix, modifier propagation into the action body, and
user-defined modifier expansion; the Stage 5 measurements below were taken with
an earlier version and the measurement values have not changed.

Added in Stage 5:

- 4 new scenarios (S2–S5) + golden AST files.
- `src/osc2c/validation.py`: trace hash, determinism, compile/tick measurement,
  KPIs (minimum distance, TTC, collision), and a Markdown summary.
- `src/osc2c/coverage.py` + `tools/coverage.py`: a 43-row evidence-backed matrix.
- `tools/bench.py`: `--mode mock|carla|all`, JSON/Markdown output.
- `tools/baseline_carla.py`: control group without the compiler.
- `tests/test_validation.py`: 14 tests — scenario results, events, geometry,
  determinism, compilation stages, and coverage matrix validation.

## 9. Reproduction

```bash
cd osc2c
.venv\Scripts\activate

# Mock: 5 scenarios × 20 repetitions + 20 compile repetitions
python tools/bench.py --mode mock --repeat 20 --compile-repeat 20 \
  --json docs/measurements/mock.json --markdown docs/measurements/mock.md

# CARLA: 20 cut-in runs (the server must be running)
python tools/bench.py --mode carla --carla-repeat 20 \
  --json docs/measurements/carla.json --markdown docs/measurements/carla.md

# Control group: 5 runs without the compiler
python tools/baseline_carla.py --repeat 5 \
  --json docs/measurements/baseline_carla.json

# Coverage matrix
python tools/coverage.py --json docs/measurements/coverage.json \
  --markdown docs/measurements/coverage.md
```

If no CARLA server is available, only the mock and coverage commands run; the
CARLA commands stop with a connection error. The default test suite does not
require CARLA.

## 10. Limitations and validity threats

1. **Single map, single spawn point.** All CARLA measurements were taken on
   `Town10HD_Opt` at spawn point 20. Behavior was not validated on other
   map/junction/lane layouts.
2. **Single machine, same CARLA process.** Determinism was observed on the same
   version and hardware; it was not retested under different physics steps,
   server versions, or concurrent load.
3. **Baseline is simplified.** The hand-written control group is not an exact
   equivalent of the behavior produced by the compiler; the aim is not absolute
   performance but comparing the order of magnitude of the cost of two approaches
   doing the same job.
4. **First-run warm-up effect.** In CARLA the first compilation takes 4.03 s;
   averages are therefore misleading. The report uses median and steady-state
   values.
5. **Parser cost is content-dependent.** Mock compile times vary between
   2.6–75.2 ms; this stems from ANTLR adaptive prediction behavior in
   physical-literal and indentation decisions. Giving a single fixed value for
   compilation time would be wrong.
6. **ASAM standard files are absent.** `types.osc` / `domain.osc` are not in the
   repository for licensing reasons; the built-in subset is used. This explains
   some of the `unsupported` rows in the coverage matrix.
7. **The coverage matrix is not an exact copy of the paper's marks.** Instead of
   the marks that could not be extracted from the PDF, running evidence and a
   rationale were recorded; this makes the comparison more auditable but not
   identical to the paper's table.
8. **The KPIs are specific to the single cut-in scenario.** The minimum
   distance/TTC thresholds cannot be generalized to other scenarios; the harness
   must be redefined for each scenario.

## 11. Questions Stage 5 answers

- **What does "deterministic" mean?** Given the same scenario, the same adapter
  settings, and the same simulation step, the tick-by-tick actor state produces
  the same SHA-256 digest. Absolute determinism of the physics engine is not
  claimed.
- **Which metric measures what?** Compilation time measures the cost of the
  language frontend (parser-dominated); tick latency measures the real-time cost
  of the runtime + adapter; the trace hash measures reproducibility; the KPIs
  measure the correctness of the scenario behavior.
- **What does silent ignoring break?** The scenario looks "successful" but the
  maneuver that was meant to be tested was never applied; this produces false
  confidence. That is why an unsupported node surfaces as a warning + `FAILED`
  leaf.
