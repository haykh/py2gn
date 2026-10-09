"""Compile errors."""

from __future__ import annotations


class GNCompileError(Exception):
    """A compile error; ``lineno`` is the 1-based source line when known."""

    def __init__(self, msg: str, node: object = None, lineno: int | None = None):
        self.lineno: int | None = lineno if lineno is not None else getattr(node, "lineno", None)
        self.msg = msg
        super().__init__(f"line {self.lineno}: {msg}" if self.lineno else msg)
