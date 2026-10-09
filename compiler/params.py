"""Function-level helpers shared by group compilation and inline expansion."""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

from .errors import GNCompileError
from .names import CONSTANTS, DECORATORS, namespace_member
from .tables import CONSTS
from .values import BOOL, GEO, INT, LIMITS, SUBTYPES, VEC

_BINOPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}


def param_default(dflt: ast.expr, aliases: set[str]):
    """Value of a parameter default: constant arithmetic over numbers, ``gn.Pi`` / ``gn.Tau`` / ``gn.E``,
    tuples and ``gn.tVec(...)`` -- e.g. ``gn.Pi / 4`` or ``gn.tVec(0, 0, 2 * gn.Pi)``."""
    if isinstance(dflt, ast.Call) and namespace_member(dflt.func, aliases) == "Param":
        inner = (
            dflt.args[0] if dflt.args else next((k.value for k in dflt.keywords if k.arg == "default"), None)
        )
        if inner is None:
            raise GNCompileError("this parameter's Param(...) has no default value", dflt)
        return param_default(inner, aliases)

    def ev(n: ast.expr):
        if isinstance(n, ast.Constant) and isinstance(n.value, (bool, int, float)):
            return n.value
        if isinstance(n, ast.Tuple):
            return tuple(ev(x) for x in n.elts)
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else +v
        if isinstance(n, ast.BinOp) and type(n.op) in _BINOPS:
            a, b = ev(n.left), ev(n.right)
            if isinstance(a, (tuple, bool)) or isinstance(b, (tuple, bool)):
                raise ValueError
            return _BINOPS[type(n.op)](a, b)
        if isinstance(n, ast.Call) and namespace_member(n.func, aliases) == "tVec" and not n.keywords:
            comps = [ev(a) for a in n.args]
            if len(comps) not in (1, 3):
                raise ValueError
            return tuple(float(c) for c in (comps * 3 if len(comps) == 1 else comps))
        const = namespace_member(n, aliases)
        if const in CONSTANTS:
            return CONSTS[CONSTANTS[const]]
        raise ValueError

    try:
        return ev(dflt)
    except (ValueError, ZeroDivisionError, TypeError, OverflowError):
        raise GNCompileError(
            "parameter defaults must be constants (numbers, gn.Pi, arithmetic, gn.tVec(...))", dflt
        ) from None


def function_kind(fdef: ast.FunctionDef, aliases: set[str], alias: str) -> str:
    """ "group" (default) or "inline" (``@gn.inline``); any other decorator is an error."""
    kind = "group"
    for d in fdef.decorator_list:
        target = d.func if isinstance(d, ast.Call) and not d.args and not d.keywords else d
        if namespace_member(target, aliases) in DECORATORS:
            kind = DECORATORS[namespace_member(target, aliases) or ""]
            continue
        raise GNCompileError(f"unsupported decorator @{ast.unparse(d)} (only @{alias}.inline)", d)
    return kind


PARAM_OPTIONS = ("default", "min", "max", "description", "subtype")


def parse_param(node: ast.expr, aliases: set[str], alias: str, T: str, pname: str) -> dict | None:
    """``gn.Param(default, min=, max=, description=, subtype=)`` as a parameter default -> metadata.

    Returns None when ``node`` is a plain default. Everything is checked against the socket type.
    """
    if not (isinstance(node, ast.Call) and namespace_member(node.func, aliases) == "Param"):
        return None
    where = node
    usage = f"{alias}.Param(default, min=..., max=..., description=..., subtype=...)"
    if len(node.args) > 1:
        raise GNCompileError(f"'{pname}': {usage} takes one positional argument (the default)", where)
    kw = {}
    for k in node.keywords:
        if k.arg not in PARAM_OPTIONS:
            raise GNCompileError(
                f"'{pname}': unknown Param option '{k.arg}' (options: {', '.join(PARAM_OPTIONS)})", where
            )
        kw[k.arg] = k.value
    if node.args and "default" in kw:
        raise GNCompileError(f"'{pname}': the default is given twice", where)
    dnode = node.args[0] if node.args else kw.get("default")
    meta: dict = {"default": None if dnode is None else param_default(dnode, aliases)}

    for key in ("min", "max"):
        if key not in kw:
            continue
        if T not in LIMITS:
            raise GNCompileError(
                f"'{pname}': {key} applies to float, int and vector parameters, not {T.lower()}", where
            )
        val = param_default(kw[key], aliases)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise GNCompileError(f"'{pname}': {key} must be a number", where)
        if T == INT and float(val) != int(val):
            raise GNCompileError(f"'{pname}': {key} of an int parameter must be a whole number", where)
        meta[key] = int(val) if T == INT else float(val)
    if "min" in meta and "max" in meta and meta["min"] > meta["max"]:
        raise GNCompileError(f"'{pname}': min {meta['min']} is greater than max {meta['max']}", where)

    if "description" in kw:
        d = kw["description"]
        if not (isinstance(d, ast.Constant) and isinstance(d.value, str)):
            raise GNCompileError(f"'{pname}': description must be a string literal", where)
        meta["description"] = d.value

    if "subtype" in kw:
        st = kw["subtype"]
        if not (isinstance(st, ast.Constant) and isinstance(st.value, str)):
            raise GNCompileError(f"'{pname}': subtype must be a string literal", where)
        if T not in SUBTYPES:
            raise GNCompileError(f"'{pname}': {T.lower()} parameters have no subtypes", where)
        sub = st.value.upper()
        if sub not in SUBTYPES[T]:
            raise GNCompileError(
                f"'{pname}': subtype '{st.value}' is not valid for {T.lower()} (options: {', '.join(SUBTYPES[T])})",
                where,
            )
        meta["subtype"] = sub

    dv = meta["default"]
    if dv is not None and T not in (BOOL, GEO) and ("min" in meta or "max" in meta):
        comps = list(dv) if isinstance(dv, (tuple, list)) else [dv] * (3 if T == VEC else 1)
        lo, hi = meta.get("min", float("-inf")), meta.get("max", float("inf"))
        if any(not (lo <= float(c) <= hi) for c in comps):
            raise GNCompileError(f"'{pname}': default {dv!r} lies outside [{lo}, {hi}]", where)
    return meta
