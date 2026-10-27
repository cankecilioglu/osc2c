# 2026-10-27 — Independent reproduction session

This folder holds the evidence for reproducing the mock and CARLA measurements
from the 2026-10-26 `docs/VALIDATION.md` report on the same machine. The goal is
not to produce a new result but to audit whether the earlier results still
hold.

## Files in the folder

| File | Content |
| --- | --- |
| `mock.json`, `mock.md` | 2026-10-27 mock run (5 scenarios × 20 repetitions, 20 compile repetitions) |
| `coverage.json`, `coverage.md` | 2026-10-27 coverage matrix validation |
| `carla.json`, `carla.md` | CARLA **second** session (B); 20/20 identical hash |
| `console.log` | Full console log of both CARLA sessions (A and B) |

> Important: `carla.json` and `carla.md` are the output of the second session
> (B). The evidence that the first session (A) produced 2 unique hashes exists
> only in `console.log`. The detailed numbers are therefore recorded below and
> in the `console.log` lines.

## 1. Mock run

Command:

```powershell
python tools/bench.py --mode mock --repeat 20 --compile-repeat 20 `
  --json docs/measurements/mock.json --markdown docs/measurements/mock.md
```

Result: 5/5 scenarios `SUCCESS`, the expected event sets matched exactly, the
`unsupported` lists were empty, and `unique_hashes = 1` for every scenario.

The trace hashes are **exactly the same** as in the 2026-10-26 report:

| ID | Trace hash (first 12) | Value in the report |
| --- | --- | --- |
| S1 | `4c0cdd1fccd7` | same |
| S2 | `a7f99db0c475` | same |
| S3 | `8ce2b96b79bf` | same |
| S4 | `4671bbc0b97b` | same |
| S5 | `0de7509b017e` | same |

The timing values are not exactly the same; this is expected:

| ID | Compile median (26 October) | Compile median (27 October) |
| --- | ---: | ---: |
| S1 | 75.19 ms | 90.25 ms |
| S2 | 59.06 ms | 56.88 ms |
| S3 | 2.63 ms | 2.61 ms |
| S4 | 29.77 ms | 29.33 ms |
| S5 | 71.13 ms | 67.61 ms |

Comment: the trace hash measures the determinism of the language and execution
semantics; wall-clock durations depend on machine load and on the parser's
adaptive prediction. The claim of "determinism" therefore holds only for the
trace, not for the durations.

## 2. CARLA session A — 20 runs, 2 unique hashes

Result: 20/20 `SUCCESS`, 20/20 `CUT_IN`, 20/20 geometry checks, 0 collisions.

| Field | Value |
| --- | --- |
| Unique hashes | **2** |
| Dominant hash | `afaf910cd26b9c675f048d368ff177dce6a1132309df22031e836474a3f9c79b` (19 runs) |
| Outlier hash | `8d185e5f4e22e6644f22b084c4db1f7f09f86995401145dedcb52affb7da16da` (1 run) |
| `CUT_IN` time | 3.25 s (all runs) |
| \|lateral\| deviation at the event | 1.2978 m |
| Heading difference at the event | 6.7218° |
| `ahead_of` at the event | −12.1548 m |
| Minimum distance | 11.938 m |
| Minimum TTC | 24.4897 s |
| Tick count | 108 |

The only difference between the two hashes is the `hero_speed` value recorded
in one tick of the outlier run:

- 19 runs: `2.966754` m/s
- 1 run: `2.96676` m/s
- Difference: approximately `6 × 10⁻⁶` m/s

Because this difference entered the trace rounded to 6 decimal places, it
changed the hash. The KPIs stayed the same at the reported precision (4
decimals) and all runs succeeded. So this is not a behavior/geometry error but
floating-point and physics-engine noise.

## 3. CARLA session B — 20 runs, 1 unique hash

The same command was run a second time:

```powershell
python tools/bench.py --mode carla --carla-repeat 20 `
  --json docs/measurements/carla.json --markdown docs/measurements/carla.md
```

Result: 20/20 `SUCCESS`, 20/20 `CUT_IN`, 20/20 geometry checks, 0 collisions,
**1 unique hash**: `afaf910cd26b...` (identical to the dominant hash of session
A). All KPIs are the same as in session A.

## 4. Conclusion

- On the mock side, **exact trace determinism** was reproduced.
- On the CARLA side, **behavioral and geometric determinism** was reproduced:
  20/20 success, the same event time, the same KPIs.
- In CARLA, **bit-level trace hash determinism is not guaranteed**: in one of
  the two sessions, 1 of the 20 runs produced a separate hash due to a speed
  difference of 6e-6 m/s. This is consistent with the warning in
  `docs/VALIDATION.md` §3 that "core determinism of the physics engine is not
  guaranteed".
- The thesis should therefore separate two statements:
  1. "The same scenario produces the same behavior and geometry" — supported 20/20.
  2. "The same scenario always produces the same trace hash" — not supported
     for CARLA; supported for the mock.
