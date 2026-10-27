from pathlib import Path

import pytest
from antlr4 import CommonTokenStream, FileStream

from osc2c.frontend.generated.openscenario2Lexer import openscenario2Lexer
from osc2c.frontend.generated.openscenario2Parser import openscenario2Parser

SCENARIOS = Path(__file__).resolve().parents[1] / "scenarios" / "dev"


def parse_errors(path: Path) -> int:
    lexer = openscenario2Lexer(FileStream(str(path), encoding="utf-8"))
    parser = openscenario2Parser(CommonTokenStream(lexer))
    parser.osc_file()
    return parser.getNumberOfSyntaxErrors()


@pytest.mark.parametrize(
    "name",
    ["smoke.osc", "smoke2.osc", "smoke3.osc", "smoke_use.osc", "smoke4.osc"],
)
def test_dev_scenarios_parse(name: str) -> None:
    assert parse_errors(SCENARIOS / name) == 0
