# Environment Setup — 26 October 2026

## Project root

```text
C:\Users\canke\Desktop\osc2-carla
```

## Machine

- Windows 11 Pro (build 26300)
- AMD Radeon RX 7700 XT (12 GB), 32 GB RAM, ~156 GB free disk
- AMD driver: 32.0.32015.7029 (2026-10-18)

## Installed components

| Component | Version | Location |
|---|---|---|
| Python (project) | 3.12.15 (uv standalone) | `C:\Users\canke\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe` |
| Python (old) | 3.11.9 | `C:\Users\canke\AppData\Local\Programs\Python\Python311\python.exe` |
| Python (system) | 3.15 | `C:\Users\canke\AppData\Local\Python\pythoncore-3.15-64\python.exe` |
| Project venv | 3.12.15 | `.venv\` (backup of the old venv: `.venv311.bak\`) |
| JDK (Temurin) | 17.0.20.1 | `C:\Users\canke\tools\jdk17\jdk-17.0.20.1+1` |
| JDK (Microsoft, backup) | 21.0.13 | `C:\Program Files\Microsoft\jdk-21.0.13.21-hotspot` |
| ANTLR tool | 4.13.2 | `tools\antlr-4.13.2-complete.jar` |
| CARLA | 0.9.16 | `external\CARLA_0.9.16` |

Python dependencies are pinned in `requirements.txt` and `pyproject.toml`.

## Python environment

```bash
cd C:\Users\canke\Desktop\osc2-carla
.venv\Scripts\activate
pytest -q
osc2c ast scenarios/dev/smoke4.osc
```

On Windows, the `python` command may resolve to the Store alias; use `.venv\Scripts\python.exe` inside the venv.

### Why Python 3.12 was installed with uv

CARLA 0.9.16 only publishes `cp312` wheels, so the project could not stay on 3.11. The Windows Python 3.12 installer package required administrator privileges (UAC), so the silent installation stalled. CPython 3.12 was installed with `uv` as a standalone build that does not require administrator privileges:

```powershell
.venv\Scripts\python.exe -m pip install uv
.venv\Scripts\python.exe -m uv python install 3.12
.venv\Scripts\python.exe -m uv python find 3.12
```

Then the venv was recreated:

```powershell
mv .venv .venv311.bak
& "C:\Users\canke\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe" -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m pip install external\CARLA_0.9.16\PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl
```

## ANTLR grammar generation

```bash
python scripts/generate_parser.py
```

If `java` is not on PATH, set `JAVA_HOME`:

```powershell
$env:JAVA_HOME = "C:\Users\canke\tools\jdk17\jdk-17.0.20.1+1"
.venv\Scripts\python.exe scripts\generate_parser.py
```

The same command with Git Bash:

```bash
JAVA_HOME="C:/Users/canke/tools/jdk17/jdk-17.0.20.1+1" .venv/Scripts/python.exe scripts/generate_parser.py
```

## Frontend spike result

- The py-osc2 0.1.0 grammar was at the OSC 2.0 level; top-level `use` and physical units with a space were not supported.
- The grammar was extended on an MPL-2.0 basis:
  - `use_statement` for `use std.stdtypes`
  - `physical_literal` parser rule for `35 kph`
  - `enum_member_value` → `integer_literal` (the lexer never produced `UINT_LITERAL`/`HEX_UINT_LITERAL`)
  - compound units via `unit_expression` / `unit_term` (`m/s`, `km/h`, `m/s^2`, `m/s^-2`)
- Regenerated with ANTLR 4.13.2.
- Paper-style nested `serial/parallel`, `emit`, `wait elapsed` and expressions with units parse with **0 errors**.
- The py-osc2 package was removed because of its runtime 4.7.1 dependency; the grammar was vendored into the project (with the MPL-2.0 `NOTICE`).

## CARLA

- Package: `C:\Users\canke\Downloads\CARLA_0.9.16.zip` (7.8 GB)
- Target: `external\CARLA_0.9.16` (ignored by git)
- Extraction:

```bash
C:\Windows\System32\tar.exe -xf C:\Users\canke\Downloads\CARLA_0.9.16.zip ^
  -C C:\Users\canke\Desktop\osc2-carla\external\CARLA_0.9.16
```

- Python wheel: `PythonAPI\carla\dist\carla-0.9.16-cp312-cp312-win_amd64.whl` (installed into the venv)
- Starting the server (visible window):

```bash
external\CARLA_0.9.16\CarlaUE4.exe -quality-level=Low -ResX=1280 -ResY=720 -windowed
```

- Starting the server (headless, for tests):

```bash
external\CARLA_0.9.16\CarlaUE4.exe -RenderOffScreen -quality-level=Low -nosound
```

- Connection test (with the server running):

```bash
.venv\Scripts\python.exe -c "import carla; c=carla.Client('127.0.0.1',2000); c.set_timeout(10); print(c.get_server_version(), c.get_world().get_map().name)"
```

- **Verified (2026-10-26):** `carla 0.9.16`, map `Carla/Maps/Town10HD_Opt`, 23 actors. The `carla` module has no `__version__` attribute; the version is obtained from the server via `get_server_version()`.

## Known notes

- The project venv is now 3.12.15; Python 3.15 and 3.11 remain on the system separately and do not interfere with the project.
- `.venv311.bak\` is kept for rollback; it can be deleted if not needed.
- The ASAM 2.2.0 package (`grammar.ebnf`, `types.osc`, `domain.osc`, `standard.osc`) is kept locally under `external/asam/`; `external/` is covered by `.gitignore`. The real library is loaded with `--stdlib external/asam/standard.osc`; tests that depend on the real library are skipped with `skipif` when the files are absent.
