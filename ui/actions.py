"""Compile actions shared by operators and the file watcher."""

from __future__ import annotations

import os

import bpy

from ..compiler import GNCompileError, gn_compile


class CompileResult:
    def __init__(self, ok: bool, message: str, lineno: int | None = None):
        self.ok = ok
        self.message = message
        self.lineno = lineno


def compile_source(src: str, origin: str) -> CompileResult:
    """Compile ``src`` and describe the outcome; ``origin`` names the source in messages."""
    try:
        groups = gn_compile(src)
    except GNCompileError as ex:
        _print_error(origin, ex.lineno, ex.msg)
        return CompileResult(False, f"{os.path.basename(origin)}:{ex.lineno or '?'}: {ex.msg}", ex.lineno)
    except SyntaxError as ex:
        _print_error(origin, ex.lineno, f"SyntaxError: {ex.msg}")
        return CompileResult(
            False,
            f"{os.path.basename(origin)}:{ex.lineno or '?'}: SyntaxError: {ex.msg}",
            ex.lineno,
        )
    names = ", ".join(g.name for g in groups) or "(no groups)"
    inlined = _inline_names(src)
    return CompileResult(
        True,
        f"Compiled: {names}" + (f" (inline: {', '.join(inlined)})" if inlined else ""),
    )


def _inline_names(src: str) -> list[str]:
    import ast

    out = []
    for n in ast.parse(src).body:
        if isinstance(n, ast.FunctionDef) and any(
            ast.unparse(d).removesuffix("()").endswith(".inline") for d in n.decorator_list
        ):
            out.append(n.name)
    return out


def compile_path(path: str) -> CompileResult:
    path = bpy.path.abspath(path)
    if not path or not os.path.isfile(path):
        return CompileResult(False, f"File not found: {path or '(no file set)'}")
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    return compile_source(src, path)


def set_status(scene: bpy.types.Scene, result: CompileResult) -> None:
    settings = scene.py2gn
    settings.status = result.message
    settings.status_error = not result.ok
    wm = bpy.context.window_manager
    if wm is None:
        return
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type in {"TEXT_EDITOR", "NODE_EDITOR"}:
                area.tag_redraw()


def _print_error(origin: str, lineno: int | None, msg: str) -> None:
    # "path:line: message" is clickable in VS Code's terminal / most IDEs
    print(f"py2gn: {origin}:{lineno or 1}: error: {msg}")
