"""Compiler diagnostics with stable codes and source locations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from osc2c.frontend.ast import Span


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    span: Span | None
    severity: Severity = Severity.ERROR

    def format(self) -> str:
        if self.span is None:
            return f"{self.severity.value}[{self.code}]: {self.message}"
        return (
            f"{self.span.source}:{self.span.line}:{self.span.column}: "
            f"{self.severity.value}[{self.code}]: {self.message}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "span": self.span.to_dict() if self.span else None,
        }


class Diagnostics:
    """Ordered diagnostic bag. Order follows the traversal that produced them."""

    def __init__(self) -> None:
        self.items: list[Diagnostic] = []

    def add(
        self,
        code: str,
        message: str,
        span: Span | None,
        severity: Severity = Severity.ERROR,
    ) -> Diagnostic:
        diagnostic = Diagnostic(code, message, span, severity)
        self.items.append(diagnostic)
        return diagnostic

    def error(self, code: str, message: str, span: Span | None) -> Diagnostic:
        return self.add(code, message, span, Severity.ERROR)

    def warning(self, code: str, message: str, span: Span | None) -> Diagnostic:
        return self.add(code, message, span, Severity.WARNING)

    def extend(self, other: "Diagnostics") -> None:
        self.items.extend(other.items)

    @property
    def errors(self) -> list[Diagnostic]:
        return [item for item in self.items if item.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [item for item in self.items if item.severity is Severity.WARNING]

    @property
    def has_errors(self) -> bool:
        return any(item.severity is Severity.ERROR for item in self.items)

    def sorted(self) -> list[Diagnostic]:
        return sorted(
            self.items,
            key=lambda item: (
                item.span.source if item.span else "",
                item.span.line if item.span else 0,
                item.span.column if item.span else 0,
                item.code,
            ),
        )

    def __iter__(self):
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)
