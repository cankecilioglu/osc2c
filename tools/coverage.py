"""Print the Table 2 coverage matrix as Markdown and/or JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from osc2c.coverage import MATRIX, summary, to_markdown, validate_matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="coverage", description=__doc__)
    parser.add_argument("--json", type=Path, help="write the matrix as JSON")
    parser.add_argument("--markdown", type=Path, help="write the Markdown table")
    args = parser.parse_args(argv)

    problems = validate_matrix()
    if problems:
        for problem in problems:
            print(f"coverage: {problem}")
        return 1

    markdown = to_markdown()
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(markdown + "\n", encoding="utf-8", newline="\n")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": summary(MATRIX),
            "rows": [
                {
                    "category": row.category,
                    "capability": row.capability,
                    "status": row.status,
                    "evidence": list(row.evidence),
                    "note": row.note,
                }
                for row in MATRIX
            ],
        }
        args.json.write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
