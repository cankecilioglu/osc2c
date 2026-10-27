"""Regenerate the Python ANTLR parser from grammar/openscenario2.g4."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAMMAR = ROOT / "grammar" / "openscenario2.g4"
OUTPUT = ROOT / "src" / "osc2c" / "frontend" / "generated"
JAR = ROOT / "tools" / "antlr-4.13.2-complete.jar"


def java_executable() -> str:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidate = Path(java_home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if candidate.exists():
            return str(candidate)
    return "java"


def main() -> None:
    if not JAR.exists():
        raise SystemExit(f"ANTLR jar not found: {JAR}")
    if not GRAMMAR.exists():
        raise SystemExit(f"Grammar not found: {GRAMMAR}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    command = [
        java_executable(),
        "-jar",
        str(JAR),
        "-Dlanguage=Python3",
        "-visitor",
        "-no-listener",
        "-o",
        str(OUTPUT),
        str(GRAMMAR),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    for pattern in ("*.interp", "*.tokens"):
        for generated in OUTPUT.glob(pattern):
            generated.unlink()
    print(f"Parser generated in {OUTPUT}")


if __name__ == "__main__":
    main()
