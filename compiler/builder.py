"""Emits Geometry Nodes for expressions and statements of one function."""

from __future__ import annotations

import ast
import contextlib
import math
import operator
from collections.abc import Callable
from typing import Any, cast

import bpy

from . import names as pubnames
from .analysis import depends_on_field
from .errors import GNCompileError
from .params import param_default
from .tables import (
    BIN_F,
    BIN_V,
    BINARY_F,
    BINARY_V,
    CMP,
    COMPONENT_DOMAINS,
    COMPONENTS,
    CONSTS,
    DOMAIN_SIZE,
    DOMAINS,
    FIELD_DATA_TYPE,
    FIELDS,
    FOLD,
    GEO_ALIASES,
    GEO_FUNCS,
    GEO_OPS,
    GEO_REQUIRED,
    K_ENUM,
    K_GEO,
    K_MENU,
    K_PROP,
    K_STR,
    K_VAL,
    STAT_ORDER,
    STATS,
    TUPLE_FIELDS,
    UNARY_F,
    UNARY_V,
)
from .values import (
    BOOL,
    FLOAT,
    FROM_SOCKTYPE,
    GEO,
    INT,
    VEC,
    Closure,
    NamedVals,
    Val,
    annot_type,
    cval,
    output_name,
)

# suggested local names for the outputs of zero-argument multi-output nodes (messages only)
TUPLE_USAGE = {
    "spline_parameter": "factor, length, index",
    "edge_vertices": "v1, v2, p1, p2",
    "scene_time": "seconds, frame",
}


_CMP_OPS: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}


class Builder:
    def __init__(
        self,
        ng,
        funcs,
        src,
        aliases: set[str] | None = None,
        inlines: dict | None = None,
    ):
        self.ng, self.funcs, self.src = ng, funcs, src
        self.inlines: dict[str, ast.FunctionDef] = inlines or {}  # @gn.inline functions of the file
        self.inline_stack: list[str] = []
        self.star_names: list[str] = []  # hidden names for `*args` expansion
        self.call_env: dict | None = None  # scope of the call being compiled (compile-time strings)
        self.repeat_frozen: list[set[int]] = []  # ids of compile-time lists that must not change in a zone
        self.repeat_locals: set[str] = set()  # names only assigned inside gn.Repeat bodies (for hints)
        self.aliases = aliases or {pubnames.DEFAULT_ALIAS}
        # alias used in messages: `gn` if the file uses it, else the first one
        self.alias = pubnames.DEFAULT_ALIAS if pubnames.DEFAULT_ALIAS in self.aliases else min(self.aliases)
        self.col = {}
        self.max_depth = 0
        self.sep_cache = {}
        self.field_cache = {}
        self.attr_cache = {}
        self.const_cache: dict = {}  # (type, const) -> materialized Val
        self.cur_line = None
        self.out_names: list[str] | None = None  # set by `return outputs(...)`
        self.node_line = {}

    # ------------------------------------------------------------- namespace
    def pub(self, internal: str) -> str:
        """Public spelling of an internal built-in name, for messages: gn.SetPosition"""
        return f"{self.alias}.{pubnames.PUBLIC_OF.get(internal, internal)}"

    def member(self, node) -> str | None:
        """``gn.X`` -> "X" (public name) when ``node`` is a namespace access."""
        return pubnames.namespace_member(node, self.aliases)

    def _undefined(self, what: str, name: str, where) -> GNCompileError:
        """Unknown bare name: hint at the namespace (old spelling) or at the file's own alias."""
        hint = pubnames.suggest(name, self.alias) if name not in pubnames.PUBLIC else ""
        if name in self.repeat_locals:
            hint = (
                " -- it is only assigned inside a gn.Repeat loop; give it a value before the loop "
                "to carry it through the iterations and out of the loop"
            )
        if not hint and name in (pubnames.DEFAULT_ALIAS, "lang", "py2gn") and name not in self.aliases:
            hint = f" -- this file imports py2gn.lang as {self.alias}"
        elif not hint and name in pubnames.PUBLIC:
            hint = f" -- built-ins are reached through the namespace: {self.alias}.{name}"
        return GNCompileError(f"undefined {what} '{name}'{hint}", where)

    def _unknown_member(self, pub: str, where):
        hint = (
            pubnames.suggest(pub, self.alias)
            if pub not in pubnames.OLD_NAMES
            else f" -- {self.alias}.{pubnames.OLD_NAMES[pub]}?"
        )
        return GNCompileError(f"{self.alias} has no '{pub}'{hint}", where)

    # node creation + layout (column = longest path from inputs)
    def node(self, idname, depth, **props):
        n = self.ng.nodes.new(idname)
        self.node_line[n.name] = self.cur_line
        for k, v in props.items():
            setattr(n, k, v)
        row = self.col.get(depth, 0)
        self.col[depth] = row + 1
        n.location = (depth * 200.0, -row * 170.0)
        n.hide = False
        self.max_depth = max(self.max_depth, depth)
        return n

    def feed(self, sock, v, where=None):
        v = self.single(v, where)
        if (v.type == GEO) != (sock.type == "GEOMETRY"):
            if v.type == GEO:
                raise GNCompileError(f"geometry used where a value is expected ('{sock.name}')", where)
            raise GNCompileError(f"'{sock.name}' expects geometry, got a {v.type.lower()}", where)
        if not v.is_const:
            self.ng.links.new(v.sock, sock)
            return
        c = v.const
        if isinstance(c, tuple) and sock.type in ("VALUE", "INT", "BOOLEAN"):
            raise GNCompileError("vector constant used where a scalar is expected", where)
        if sock.hide_value or sock.type not in ("VALUE", "INT", "BOOLEAN", "VECTOR"):
            # Sockets without a value widget may ignore their stored value: some evaluate an
            # implicit field when unlinked (Extrude Mesh > Offset = normal, Set Position >
            # Position = position). Blender's API doesn't tell them apart from plain hidden
            # defaults (Selection), so constants for any of them go through a linked node.
            # Other socket types (Rotation, ...) take a linked value via implicit conversion
            # (a vector becomes an Euler rotation).
            self.ng.links.new(self.materialize(v).sock, sock)
            return
        if sock.type == "VECTOR":
            sock.default_value = c if isinstance(c, tuple) else (float(c),) * 3
        elif isinstance(c, tuple):
            raise GNCompileError("vector constant used where a scalar is expected", where)
        elif sock.type == "VALUE":
            sock.default_value = float(c)
        elif sock.type == "INT":
            sock.default_value = int(c)
        elif sock.type == "BOOLEAN":
            sock.default_value = bool(c)

    @staticmethod
    def single(v, where=None):
        """A single value is required here: explain tuples (several node outputs) instead of crashing."""
        if isinstance(v, NamedVals):
            names = ", ".join(v.names)
            raise GNCompileError(
                f"{v.label}() returns several outputs ({names}): unpack them or pick one, e.g. .{v.names[0]}",
                where,
            )
        if isinstance(v, tuple):
            raise GNCompileError(f"expected a single value, got a tuple of {len(v)}", where)
        if isinstance(v, list):
            raise GNCompileError(
                f"expected a single value, got a list of {len(v)} (compile-time only)", where
            )
        if isinstance(v, str):
            raise GNCompileError(
                f"expected a value, got the string {v!r} (strings are compile-time only)", where
            )
        if isinstance(v, Closure):
            raise GNCompileError(f"expected a value, got the function {v.name}() (call it)", where)
        return v

    @staticmethod
    def depth(*vals):
        return 1 + max((v.depth for v in vals), default=0)

    # --- primitive emitters
    def math(self, op, *args, where=None):
        if all(a.is_const and not isinstance(a.const, tuple) for a in args) and op in FOLD:
            try:
                return Val(FLOAT, const=float(FOLD[op](*[float(a.const) for a in args])))
            except (ValueError, ZeroDivisionError, OverflowError):
                pass
        for a in args:
            if a.type == VEC:
                raise GNCompileError(f"{op.lower()} expects scalars, got a vector", where)
        d = self.depth(*args)
        n = self.node("ShaderNodeMath", d, operation=op)
        for i, a in enumerate(args):
            self.feed(n.inputs[i], a, where)
        return Val(FLOAT, sock=n.outputs[0], depth=d, node=n)

    def vmath(self, op, *args, scale=None, scalar_out=False, where=None):
        d = self.depth(*args, *([scale] if scale else []))
        n = self.node("ShaderNodeVectorMath", d, operation=op)
        for i, a in enumerate(args):
            self.feed(n.inputs[i], a, where)
        if scale is not None:
            self.feed(n.inputs[3], scale, where)
        if scalar_out:
            return Val(FLOAT, sock=n.outputs[1], depth=d, node=n)
        return Val(VEC, sock=n.outputs[0], depth=d, node=n)

    def boolmath(self, op, *args, where=None):
        args = tuple(self.single(a, where) for a in args)
        if all(a.is_const for a in args):
            a = [bool(x.const) for x in args]
            return Val(
                BOOL,
                const={
                    "AND": lambda: a[0] and a[1],
                    "OR": lambda: a[0] or a[1],
                    "NOT": lambda: not a[0],
                    "XOR": lambda: a[0] != a[1],
                    "XNOR": lambda: a[0] == a[1],
                }[op](),
            )
        d = self.depth(*args)
        n = self.node("FunctionNodeBooleanMath", d, operation=op)
        for i, a in enumerate(args):
            self.feed(n.inputs[i], a, where)
        return Val(BOOL, sock=n.outputs[0], depth=d, node=n)

    def compare(self, op, a, b, where=None):
        a, b = self.single(a, where), self.single(b, where)
        if a.type == BOOL and b.type == BOOL and op in ("EQUAL", "NOT_EQUAL"):
            return self.boolmath("XNOR" if op == "EQUAL" else "XOR", a, b, where=where)
        if a.is_const and b.is_const and not isinstance(a.const, tuple) and not isinstance(b.const, tuple):
            x, y = float(a.const), float(b.const)
            return Val(
                BOOL,
                const={
                    "LESS_THAN": x < y,
                    "GREATER_THAN": x > y,
                    "LESS_EQUAL": x <= y,
                    "GREATER_EQUAL": x >= y,
                    "EQUAL": x == y,
                    "NOT_EQUAL": x != y,
                }[op],
            )
        dt = VEC if VEC in (a.type, b.type) else (INT if a.type == b.type == INT else FLOAT)
        d = self.depth(a, b)
        n = self.node("FunctionNodeCompare", d, data_type=dt, operation=op)
        self.feed(n.inputs[0], a, where)
        self.feed(n.inputs[1], b, where)
        return Val(BOOL, sock=n.outputs[0], depth=d, node=n)

    def switch(self, c, f, t, where=None):
        c, f, t = self.single(c, where), self.single(f, where), self.single(t, where)
        if c.is_const:
            return t if c.const else f
        if GEO in (f.type, t.type) and depends_on_field(c.sock):
            raise GNCompileError(
                "a geometry if/else needs a single-value condition (one choice for the whole "
                "geometry), but this condition is a field (depends on position/index/an "
                "attribute...). Use a selection= argument for per-element choices.",
                where,
            )
        if f.type == t.type:
            T = f.type
        elif VEC in (f.type, t.type):
            T = VEC
        else:
            T = FLOAT
        d = self.depth(c, f, t)
        n = self.node(
            "GeometryNodeSwitch",
            d,
            input_type={
                FLOAT: "FLOAT",
                INT: "INT",
                BOOL: "BOOLEAN",
                VEC: "VECTOR",
                GEO: "GEOMETRY",
            }[T],
        )
        self.feed(n.inputs["Switch"], c, where)
        self.feed(n.inputs["False"], f, where)
        self.feed(n.inputs["True"], t, where)
        return Val(T, sock=n.outputs[0], depth=d, node=n)

    def combine(self, x, y, z, where=None):
        if x.is_const and y.is_const and z.is_const:
            return cval((x.const, y.const, z.const))
        d = self.depth(x, y, z)
        n = self.node("ShaderNodeCombineXYZ", d)
        for i, a in enumerate((x, y, z)):
            self.feed(n.inputs[i], a, where)
        return Val(VEC, sock=n.outputs[0], depth=d, node=n)

    def component(self, v, axis, where=None):
        i = "xyz".index(axis)
        if v.is_const:
            c = v.const
            return Val(FLOAT, const=c[i] if isinstance(c, tuple) else c)
        if v.type != VEC:
            raise GNCompileError(f".{axis} on a non-vector", where)
        key = v.sock.as_pointer()
        n = self.sep_cache.get(key)
        if n is None:
            n = self.node("ShaderNodeSeparateXYZ", v.depth + 1)
            self.feed(n.inputs[0], v, where)
            self.sep_cache[key] = n
        return Val(FLOAT, sock=n.outputs[i], depth=v.depth + 1, node=n)

    def materialize(self, v):
        """Turn a constant into a node output (group outputs, hidden-value sockets).

        One node per distinct constant and type, reused across the function.
        """
        if not v.is_const:
            return v
        key = (v.type, v.const)
        cached = self.const_cache.get(key)
        if cached is not None:
            return cached
        if v.type == VEC:
            n = self.node("ShaderNodeCombineXYZ", 1)
            self.feed(n.inputs[0], Val(FLOAT, const=v.const[0]))
            self.feed(n.inputs[1], Val(FLOAT, const=v.const[1]))
            self.feed(n.inputs[2], Val(FLOAT, const=v.const[2]))
        elif v.type == BOOL:
            n = self.node("FunctionNodeInputBool", 1)
            n.boolean = bool(v.const)
        else:
            n = self.node("ShaderNodeValue", 1)
            n.outputs[0].default_value = float(v.const)
        out = Val(v.type, sock=n.outputs[0], depth=1, node=n)
        self.const_cache[key] = out
        return out

    # --- arithmetic dispatch
    def binop(self, op, a, b, where=None):
        a, b = self.single(a, where), self.single(b, where)
        if isinstance(op, ast.MatMult):
            return self.vmath("DOT_PRODUCT", a, b, scalar_out=True, where=where)
        if isinstance(op, ast.FloorDiv):
            q = self.binop(ast.Div(), a, b, where)
            return (
                self.vmath("FLOOR", q, where=where) if q.type == VEC else self.math("FLOOR", q, where=where)
            )
        if VEC not in (a.type, b.type):
            o = BIN_F.get(type(op))
            if o is None:
                raise GNCompileError(f"operator {type(op).__name__} not supported on scalars", where)
            return self.math(o, a, b, where=where)
        # vector path
        if isinstance(op, ast.Mod):  # floored modulo, Python semantics: a - b*floor(a/b)
            q = self.vmath("FLOOR", self.vmath("DIVIDE", a, b, where=where), where=where)
            return self.vmath("SUBTRACT", a, self.vmath("MULTIPLY", b, q, where=where), where=where)
        if isinstance(op, ast.Mult) and a.type != b.type:
            vecv, s = (a, b) if a.type == VEC else (b, a)
            return self.vmath("SCALE", vecv, scale=s, where=where)
        if isinstance(op, ast.Div) and a.type == VEC and b.type != VEC:
            return self.vmath(
                "SCALE",
                a,
                scale=self.math("DIVIDE", cval(1.0), b, where=where),
                where=where,
            )
        o = BIN_V.get(type(op))
        if o is None:
            raise GNCompileError(f"operator {type(op).__name__} not supported on vectors", where)
        return self.vmath(o, a, b, where=where)

    def neg(self, a, where=None):
        a = self.single(a, where)
        if a.is_const:
            c = a.const
            return Val(a.type, const=tuple(-x for x in c) if isinstance(c, tuple) else -c)
        if a.type == VEC:
            return self.vmath("SCALE", a, scale=cval(-1.0), where=where)
        return self.math("MULTIPLY", a, cval(-1.0), where=where)

    def group_call(self, g, args, kwargs, where):
        if g == self.ng:
            raise GNCompileError("recursion is not supported (node groups cannot call themselves)", where)
        d = self.depth(*args, *kwargs.values())
        n = self.node("GeometryNodeGroup", d)
        n.node_tree = g
        ins = [s for s in n.inputs if s.type in FROM_SOCKTYPE]
        if len(args) > len(ins):
            raise GNCompileError(f"{g.name}() takes {len(ins)} arguments, got {len(args)}", where)
        for s, a in zip(ins, args):
            self.feed(s, a, where)
        for k, a in kwargs.items():
            s = next((s for s in ins if s.name == k), None)
            if s is None:
                raise GNCompileError(f"{g.name}() has no input '{k}'", where)
            self.feed(s, a, where)
        outs = [
            Val(FROM_SOCKTYPE[s.type], sock=s, depth=d, node=n) for s in n.outputs if s.type in FROM_SOCKTYPE
        ]
        return outs[0] if len(outs) == 1 else tuple(outs)

    # --- expressions
    def expr(self, e, env):
        if isinstance(e, ast.Constant):
            if isinstance(e.value, (bool, int, float)):
                return cval(e.value)
            if isinstance(e.value, str):
                return e.value  # compile-time string
            raise GNCompileError(f"unsupported constant {e.value!r}", e)
        # ---- compile-time Python: lists, comprehensions, f-strings, indexing, lambdas
        if isinstance(e, ast.List):
            out = []
            for x in e.elts:
                if isinstance(x, ast.Starred):
                    out.extend(self.sequence(self.expr(x.value, env), x))
                else:
                    out.append(self.expr(x, env))
            return out
        if isinstance(e, (ast.ListComp, ast.GeneratorExp)):
            return self.comprehension(e, env)
        if isinstance(e, ast.JoinedStr):
            return self.fstring(e, env)
        if isinstance(e, ast.Subscript):
            return self.subscript(e, env)
        if isinstance(e, ast.Lambda):
            return Closure(e, env, "<lambda>")
        if isinstance(e, ast.Name):
            if e.id in env:
                return env[e.id]
            raise self._undefined("name", e.id, e)
        if isinstance(e, ast.Tuple):
            return tuple(self.expr(x, env) for x in e.elts)
        if isinstance(e, ast.BinOp):
            left, right = self.expr(e.left, env), self.expr(e.right, env)
            if isinstance(left, (list, str)) or isinstance(right, (list, str)):
                return self.compile_time_binop(e.op, left, right, e)
            return self.binop(e.op, left, right, e)
        if isinstance(e, ast.UnaryOp):
            a = self.expr(e.operand, env)
            if isinstance(e.op, ast.USub):
                return self.neg(a, e)
            if isinstance(e.op, ast.UAdd):
                return a
            if isinstance(e.op, ast.Not):
                return self.boolmath("NOT", a, where=e)
            raise GNCompileError("unsupported unary operator", e)
        if isinstance(e, ast.BoolOp):
            vals = [self.expr(x, env) for x in e.values]
            op = "AND" if isinstance(e.op, ast.And) else "OR"
            acc = vals[0]
            for v in vals[1:]:
                acc = self.boolmath(op, acc, v, where=e)
            return acc
        if isinstance(e, ast.Compare):
            vals = [self.expr(o, env) for o in (e.left, *e.comparators)]  # each operand once
            membership = any(isinstance(op, (ast.In, ast.NotIn, ast.Is, ast.IsNot)) for op in e.ops)
            if membership or any(isinstance(v, (str, list)) for v in vals):
                # strings / lists / `in`: decided while compiling
                py = [self.py_value(v, e, "comparison operand") for v in vals]
                return cval(all(_CMP_OPS[type(op)](py[i], py[i + 1]) for i, op in enumerate(e.ops)))
            acc = None
            for i, op in enumerate(e.ops):
                opname = CMP.get(type(op))
                if opname is None:
                    raise GNCompileError(f"comparison {type(op).__name__} not supported", e)
                r = self.compare(opname, vals[i], vals[i + 1], e)
                acc = r if acc is None else self.boolmath("AND", acc, r, where=e)
            return acc
        if isinstance(e, ast.IfExp):
            c = self.expr(e.test, env)
            if not isinstance(c, Val):
                c = cval(bool(self.py_value(c, e, "condition")))
            if c.is_const:  # don't even build the dead branch
                return self.expr(e.body if c.const else e.orelse, env)
            return self.switch(c, self.expr(e.orelse, env), self.expr(e.body, env), e)
        if isinstance(e, ast.Attribute):
            pub = self.member(e)
            if pub is not None:
                if pub in pubnames.FIELDS:
                    return self.field(pubnames.FIELDS[pub])
                if pub in pubnames.CONSTANTS:
                    return cval(CONSTS[pubnames.CONSTANTS[pub]])
                if pub in pubnames.CALLABLE:
                    raise GNCompileError(f"{self.alias}.{pub} is a function: call it", e)
                if pub in pubnames.TYPES:
                    raise GNCompileError(f"{self.alias}.{pub} is a type: use it as an annotation", e)
                if pub in pubnames.DECORATORS:
                    raise GNCompileError(
                        f"{self.alias}.{pub} is a decorator: put @{self.alias}.{pub} above a def",
                        e,
                    )
                raise self._unknown_member(pub, e)
            base = self.expr(e.value, env)
            if isinstance(base, NamedVals):
                if e.attr in base.names:
                    return base[base.names.index(e.attr)]
                raise GNCompileError(
                    f"{base.label}() has no output '{e.attr}' (outputs: {', '.join(base.names)})",
                    e,
                )
            if e.attr in ("x", "y", "z"):
                return self.component(self.single(base, e), e.attr, e)
            raise GNCompileError(f"unsupported attribute .{e.attr}", e)
        if isinstance(e, ast.Call):
            return self.call(e, env)
        raise GNCompileError(f"unsupported expression {type(e).__name__}", e)

    def field(self, name):
        idname, out, T = FIELDS[name]
        n = self.field_cache.get(idname)
        if n is None:
            n = self.node(idname, 0)
            self.field_cache[idname] = n
        return Val(T, sock=n.outputs[out], depth=0, node=None)

    def named_attr(self, fn, e):
        """attr("name", type=float)  /  attr_exists("name")"""
        pos = list(e.args)
        kw = {k.arg: k.value for k in e.keywords}
        name_node = pos.pop(0) if pos else kw.pop("name", None)
        type_node = pos.pop(0) if pos else kw.pop("type", None)
        if pos or kw or name_node is None or (fn == "attr_exists" and type_node is not None):
            raise GNCompileError(
                f"usage: {self.pub('attr')}('name', type={self.alias}.tFloat)"
                if fn == "attr"
                else f"usage: {self.pub('attr_exists')}('name')",
                e,
            )
        name = self._literal_str(name_node, "attribute name", e)
        if fn == "attr_exists":
            # reuse any Named Attribute node already reading this name; Exists does not depend on type
            n = next((n for (nm, _), n in self.attr_cache.items() if nm == name), None)
            if n is None:
                n = self._attr_node(name, FLOAT)
            return Val(BOOL, sock=n.outputs["Exists"], depth=0, node=None)
        T = FLOAT if type_node is None else annot_type(type_node, e, self.aliases)
        if T == GEO:
            raise GNCompileError(f"attributes cannot have type {self.alias}.tGeometry", e)
        n = self._attr_node(name, T)
        return Val(T, sock=n.outputs["Attribute"], depth=0, node=None)

    def _attr_node(self, name, T):
        key = (name, T)
        n = self.attr_cache.get(key)
        if n is None:
            n = self.node("GeometryNodeInputNamedAttribute", 0, data_type=FIELD_DATA_TYPE[T])
            n.inputs["Name"].default_value = name
            n.label = f'attr "{name}"'
            self.attr_cache[key] = n
        return n

    def field_eval(self, fn, e, env):
        """at_index(value, index, domain="POINT")  /  on_domain(value, domain="POINT")"""
        nfixed = 2 if fn == "at_index" else 1
        pos = list(e.args)
        kw = {k.arg: k.value for k in e.keywords}
        dom_node = kw.pop("domain", None)
        if len(pos) == nfixed + 1 and dom_node is None:
            dom_node = pos.pop()
        if fn == "at_index" and "index" in kw and len(pos) == 1:
            pos.append(kw.pop("index"))
        if "value" in kw and not pos:
            pos.insert(0, kw.pop("value"))
        if kw or len(pos) != nfixed:
            sig = (
                f"{self.pub('at_index')}(value, index, domain='POINT')"
                if fn == "at_index"
                else f"{self.pub('on_domain')}(value, domain='POINT')"
            )
            raise GNCompileError(f"usage: {sig}", e)
        domain = "POINT"
        if dom_node is not None:
            if not (
                isinstance(dom_node, ast.Constant)
                and isinstance(dom_node.value, str)
                and dom_node.value.upper() in DOMAINS
            ):
                raise GNCompileError(
                    f"domain must be one of {', '.join(DOMAINS)} (as a string literal)",
                    e,
                )
            domain = dom_node.value.upper()
        v = self.expr(pos[0], env)
        if isinstance(v, tuple):
            raise GNCompileError(f"{self.pub(fn)}() value must be a single value, not a tuple", e)
        if v.type == GEO:
            raise GNCompileError(f"{self.pub(fn)}() cannot be applied to geometry", e)
        if v.is_const:
            return v  # a constant is the same at every index / on every domain
        args = [v]
        idx = None
        if fn == "at_index":
            idx = self.expr(pos[1], env)
            args.append(idx)
        d = self.depth(*args)
        n = self.node(
            "GeometryNodeFieldAtIndex" if fn == "at_index" else "GeometryNodeFieldOnDomain",
            d,
            data_type=FIELD_DATA_TYPE[v.type],
            domain=domain,
        )
        self.feed(n.inputs["Value"], v, e)
        if idx is not None:
            self.feed(n.inputs["Index"], idx, e)
        return Val(v.type, sock=n.outputs["Value"], depth=d, node=n)

    def _literal_str(self, a, what, e):
        """A string argument: a literal, or any string known at compile time (f-strings, variables)."""
        if isinstance(a, ast.Constant) and isinstance(a.value, str) and a.value:
            return a.value
        if self.call_env is not None and not isinstance(a, ast.Constant):
            v = self.expr(a, self.call_env)
            if isinstance(v, str) and v:
                return v
        raise GNCompileError(f"{what} must be a string literal or a string known at compile time", e)

    def geo_call(self, fn, e, env):
        fn = GEO_ALIASES.get(fn, fn)
        if fn == "join":
            if e.keywords or not e.args:
                raise GNCompileError(f"usage: {self.pub('join')}(geo_a, geo_b, ...)", e)
            vs = [self.expr(a, env) for a in e.args]
            for v in vs:
                if isinstance(v, tuple) or v.type != GEO:
                    raise GNCompileError(f"{self.pub('join')}() arguments must be geometry", e)
            if len(vs) == 1:
                return vs[0]
            d = self.depth(*vs)
            n = self.node("GeometryNodeJoinGeometry", d)
            for v in vs:  # Join's multi-input lists the most recently added link first
                self.ng.links.new(v.sock, n.inputs[0])
            self._order_multi_input(n.inputs[0], [v.sock for v in vs])
            return Val(GEO, sock=n.outputs[0], depth=d, node=n)

        if fn in ("domain_size", "attr_stat"):
            return self._geo_query(fn, e, env)

        if fn == "mesh_boolean":
            return self._mesh_boolean(e, env)

        if fn == "index_switch":
            return self._index_switch(e, env)

        if fn == "capture":
            kw = {k.arg: k.value for k in e.keywords}
            dom = kw.pop("domain", None)
            if kw or len(e.args) < 2:
                raise GNCompileError(
                    f"usage: geo, f1, f2, ... = {self.pub('capture')}(geo, value1, value2, ..., domain='POINT')",
                    e,
                )
            domain = "POINT" if dom is None else self._literal_str(dom, "domain", e).upper()
            if domain not in DOMAINS:
                raise GNCompileError(f"domain must be one of {', '.join(DOMAINS)}", e)
            g = self.expr(e.args[0], env)
            if isinstance(g, tuple) or g.type != GEO:
                raise GNCompileError(f"{self.pub('capture')}() first argument must be geometry", e)
            vals = [self.expr(a, env) for a in e.args[1:]]
            for v in vals:
                if isinstance(v, tuple) or v.type == GEO:
                    raise GNCompileError(
                        f"{self.pub('capture')}() values must be single non-geometry values",
                        e,
                    )
            d = self.depth(g, *vals)
            n = self.node("GeometryNodeCaptureAttribute", d, domain=domain)
            self.feed(n.inputs[0], g, e)
            outs = [Val(GEO, sock=n.outputs[0], depth=d, node=n)]
            for i, (a, v) in enumerate(zip(e.args[1:], vals)):
                nm = a.id if isinstance(a, ast.Name) else f"Value{i}"
                n.capture_items.new(
                    {FLOAT: "FLOAT", INT: "INT", BOOL: "BOOLEAN", VEC: "VECTOR"}[v.type],
                    nm,
                )
                self.feed(n.inputs[2 + i], v, e)
                outs.append(Val(v.type, sock=n.outputs[2 + i], depth=d, node=n))
            return tuple(outs)

        idname, params, outs, auto = GEO_OPS[fn]
        names = [p[0] for p in params]
        bound = {}
        if len(e.args) > len(params):
            raise GNCompileError(
                f"{self.pub(fn)}() takes at most {len(params)} arguments ({', '.join(names)})",
                e,
            )
        for p, a in zip(params, e.args):
            bound[p[0]] = a
        for k in e.keywords:
            if k.arg not in names:
                raise GNCompileError(
                    f"{self.pub(fn)}() has no parameter '{k.arg}' (parameters: {', '.join(names)})",
                    e,
                )
            if k.arg in bound:
                raise GNCompileError(f"{self.pub(fn)}() got '{k.arg}' twice", e)
            bound[k.arg] = k.value
        first_required = {names[0]} if params[0][1] == K_GEO else set()  # e.g. MeshCircle needs no input
        missing = (first_required | GEO_REQUIRED.get(fn, set())) - set(bound)
        if missing:
            raise GNCompileError(
                f"{self.pub(fn)}() missing required argument(s): {', '.join(sorted(missing))}",
                e,
            )

        vals = {}
        for kw, kind, target in params:
            if kw not in bound:
                continue
            a = bound[kw]
            if kind in (K_GEO, K_VAL):
                v = self.single(self.expr(a, env), e)
                if kind == K_GEO and v.type != GEO:
                    raise GNCompileError(f"{self.pub(fn)}(): '{kw}' must be geometry", e)
                if kind == K_VAL and v.type == GEO:
                    raise GNCompileError(f"{self.pub(fn)}(): '{kw}' must be a value, not geometry", e)
                vals[kw] = v
            elif kind == K_STR:
                vals[kw] = self._literal_str(a, f"{self.pub(fn)}(): '{kw}'", e)
            elif kind == K_PROP:  # a node property: fixed when the graph is built
                vals[kw] = bool(self.py_value(self.expr(a, env), e, f"'{kw}' option"))
            elif kind == K_MENU:
                menu = cast("dict[str, str]", target[1])
                val = self._literal_str(a, f"{self.pub(fn)}(): '{kw}'", e).upper()
                if val not in menu:
                    raise GNCompileError(f"{self.pub(fn)}(): '{kw}' must be one of {', '.join(menu)}", e)
                vals[kw] = menu[val]
            else:
                val = self._literal_str(a, f"{self.pub(fn)}(): '{kw}'", e).upper()
                if val not in target[1]:
                    raise GNCompileError(
                        f"{self.pub(fn)}(): '{kw}' must be one of {', '.join(target[1])}",
                        e,
                    )
                vals[kw] = val

        d = self.depth(*[v for v in vals.values() if isinstance(v, Val)])
        n = self.node(idname, d)
        for kw, kind, target in params:  # enums first: they change socket layout
            if kind == K_ENUM and kw in vals:
                setattr(n, target[0], vals[kw])
        if auto:
            n.data_type = FIELD_DATA_TYPE[vals[auto].type]
        for kw, kind, target in params:
            if kw not in vals or kind == K_ENUM:
                continue
            if kind == K_PROP:
                setattr(n, cast("str", target), vals[kw])
                continue
            if kind == K_MENU:
                n.inputs[target[0]].default_value = vals[kw]
                continue
            sock = n.inputs[target]
            if kind == K_STR:
                sock.default_value = vals[kw]
            else:
                self.feed(sock, vals[kw], e)
        res = [Val(FROM_SOCKTYPE[n.outputs[o].type], sock=n.outputs[o], depth=d, node=n) for o in outs]
        return res[0] if len(res) == 1 else NamedVals(res, [output_name(o) for o in outs], self.pub(fn))

    def _bind(self, fn, e, names):
        bound = {}
        if len(e.args) > len(names):
            raise GNCompileError(
                f"{self.pub(fn)}() takes at most {len(names)} arguments ({', '.join(names)})",
                e,
            )
        for nm, a in zip(names, e.args):
            bound[nm] = a
        for k in e.keywords:
            if k.arg not in names:
                raise GNCompileError(
                    f"{self.pub(fn)}() has no parameter '{k.arg}' (parameters: {', '.join(names)})",
                    e,
                )
            if k.arg in bound:
                raise GNCompileError(f"{self.pub(fn)}() got '{k.arg}' twice", e)
            bound[k.arg] = k.value
        return bound

    def _geo_arg(self, a, fn, e, env):
        g = self.expr(a, env)
        if isinstance(g, tuple) or g.type != GEO:
            raise GNCompileError(f"{self.pub(fn)}() first argument must be geometry", e)
        return g

    def _geo_query(self, fn, e, env):
        if fn == "domain_size":
            # domain_size(geo, domain="POINT", component=<inferred>) -> int (single value)
            b = self._bind(fn, e, ["geometry", "domain", "component"])
            if "geometry" not in b:
                raise GNCompileError(
                    f"usage: {self.pub('domain_size')}(geo, domain='POINT', component='MESH')",
                    e,
                )
            g = self._geo_arg(b["geometry"], fn, e, env)
            domain = self._literal_str(b["domain"], "domain", e).upper() if "domain" in b else "POINT"
            if domain not in DOMAIN_SIZE:
                raise GNCompileError(f"domain must be one of {', '.join(DOMAIN_SIZE)}", e)
            comp, out = DOMAIN_SIZE[domain]
            if "component" in b:
                comp = self._literal_str(b["component"], "component", e).upper()
                if comp not in COMPONENTS:
                    raise GNCompileError(f"component must be one of {', '.join(COMPONENTS)}", e)
            d = self.depth(g)
            if domain not in COMPONENT_DOMAINS[comp]:
                raise GNCompileError(
                    f"component {comp} has no {domain} domain (available: {', '.join(COMPONENT_DOMAINS[comp])})",
                    e,
                )
            n = self.node("GeometryNodeAttributeDomainSize", d, component=comp)
            self.feed(n.inputs["Geometry"], g, e)
            return Val(INT, sock=n.outputs[out], depth=d, node=n)

        # attr_stat(geo, value, stat=<all>, domain="POINT", selection=True) -> single value, or 8-tuple
        b = self._bind(fn, e, ["geometry", "value", "stat", "domain", "selection"])
        if "geometry" not in b or "value" not in b:
            raise GNCompileError(
                f"usage: {self.pub('attr_stat')}(geo, value, stat='mean', domain='POINT', selection=...)",
                e,
            )
        g = self._geo_arg(b["geometry"], fn, e, env)
        v = self.expr(b["value"], env)
        if isinstance(v, tuple) or v.type == GEO:
            raise GNCompileError(f"{self.pub('attr_stat')}() value must be a scalar or vector field", e)
        stat = None
        if "stat" in b:
            sname = self._literal_str(b["stat"], "stat", e).lower()
            if sname not in STATS:
                raise GNCompileError(f"stat must be one of {', '.join(STATS)}", e)
            stat = STATS[sname]
        domain = self._literal_str(b["domain"], "domain", e).upper() if "domain" in b else "POINT"
        if domain not in DOMAINS:
            raise GNCompileError(f"domain must be one of {', '.join(DOMAINS)}", e)
        sel = None
        if "selection" in b:
            sel = self.expr(b["selection"], env)
            if isinstance(sel, tuple) or sel.type == GEO:
                raise GNCompileError("selection must be a bool field", e)
        T = VEC if v.type == VEC else FLOAT  # Attribute Statistic works on float or vector
        d = self.depth(g, v, *([sel] if sel else []))
        n = self.node(
            "GeometryNodeAttributeStatistic",
            d,
            data_type="FLOAT_VECTOR" if T == VEC else "FLOAT",
            domain=domain,
        )
        self.feed(n.inputs["Geometry"], g, e)
        self.feed(n.inputs["Attribute"], v, e)
        if sel is not None:
            self.feed(n.inputs["Selection"], sel, e)
        if stat:
            return Val(T, sock=n.outputs[stat], depth=d, node=n)
        return tuple(Val(T, sock=n.outputs[o], depth=d, node=n) for o in STAT_ORDER)

    def _index_switch(self, e, env):
        """IndexSwitch(index, v0, v1, ...): v[index]; the item type follows the values."""
        if e.keywords or len(e.args) < 2:
            raise GNCompileError(f"usage: {self.pub('index_switch')}(index, value0, value1, ...)", e)
        idx = self.single(self.expr(e.args[0], env), e)
        if idx.type == GEO:
            raise GNCompileError(
                f"{self.pub('index_switch')}(): the index must be a number, not geometry",
                e,
            )
        vals = [self.single(self.expr(a, env), e) for a in e.args[1:]]
        geo = [v.type == GEO for v in vals]
        if any(geo) and not all(geo):
            raise GNCompileError(
                f"{self.pub('index_switch')}(): values must be all geometry or all non-geometry",
                e,
            )
        types = {v.type for v in vals}
        T = GEO if all(geo) else VEC if VEC in types else (types.pop() if len(types) == 1 else FLOAT)
        if idx.is_const and 0 <= int(idx.const) < len(vals):
            return vals[int(idx.const)]  # known index: no node needed
        if T == GEO and not idx.is_const and depends_on_field(idx.sock):
            raise GNCompileError(
                f"{self.pub('index_switch')}() over geometry needs a single-value index (one choice for the whole "
                "geometry), but this index is a field",
                e,
            )
        d = self.depth(idx, *vals)
        n = self.node(
            "GeometryNodeIndexSwitch",
            d,
            data_type={
                FLOAT: "FLOAT",
                INT: "INT",
                BOOL: "BOOLEAN",
                VEC: "VECTOR",
                GEO: "GEOMETRY",
            }[T],
        )
        items = n.index_switch_items
        while len(items) < len(vals):
            items.new()
        while len(items) > len(vals):
            items.remove(items[len(items) - 1])
        self.feed(n.inputs["Index"], idx, e)
        item_socks = [s for s in n.inputs if s.identifier.startswith("Item_")]
        for sock, v in zip(item_socks, vals):
            self.feed(sock, v, e)
        return Val(T, sock=n.outputs[0], depth=d, node=n)

    def _mesh_boolean(self, e, env):
        """MeshBoolean(*meshes, operation, solver, self_intersection, hole_tolerant)

        DIFFERENCE: the first mesh minus all the others; UNION / INTERSECT: all meshes together.
        Returns the mesh; EXACT and MANIFOLD also return the intersecting-edges field
        (Blender only creates that output for them): ``mesh, edges = ...``.
        """
        usage = (
            f"usage: mesh = {self.pub('mesh_boolean')}(a, b, ..., operation='DIFFERENCE', "
            "solver='FLOAT', self_intersection=False, hole_tolerant=False)"
        )
        kw = {k.arg: k.value for k in e.keywords}
        unknown = set(kw) - {
            "operation",
            "solver",
            "self_intersection",
            "hole_tolerant",
        }
        if unknown or None in kw:
            raise GNCompileError(f"{usage} (unknown argument: {', '.join(sorted(map(str, unknown)))})", e)
        if not e.args:
            raise GNCompileError(usage, e)
        meshes = [self.expr(a, env) for a in e.args]
        for v in meshes:
            if isinstance(v, tuple) or v.type != GEO:
                raise GNCompileError(f"{self.pub('mesh_boolean')}() meshes must be geometry", e)

        def option(name, choices, default):
            if name not in kw:
                return default
            val = self._literal_str(kw[name], name, e).upper()
            if val not in choices:
                raise GNCompileError(
                    f"{self.pub('mesh_boolean')}(): '{name}' must be one of {', '.join(choices)}",
                    e,
                )
            return val

        op = option("operation", ("INTERSECT", "UNION", "DIFFERENCE"), "DIFFERENCE")
        solver = option("solver", ("EXACT", "FLOAT", "MANIFOLD"), "FLOAT")
        flags = {}
        for name, sock_name in (
            ("self_intersection", "Self Intersection"),
            ("hole_tolerant", "Hole Tolerant"),
        ):
            if name in kw:
                if solver != "EXACT":
                    raise GNCompileError(
                        f"{self.pub('mesh_boolean')}(): '{name}' only applies to solver='EXACT' "
                        f"(Blender ignores it for {solver})",
                        e,
                    )
                v = self.expr(kw[name], env)
                if isinstance(v, tuple) or v.type == GEO:
                    raise GNCompileError(f"{self.pub('mesh_boolean')}(): '{name}' must be a bool", e)
                flags[sock_name] = v

        d = self.depth(*meshes, *flags.values())
        n = self.node("GeometryNodeMeshBoolean", d, operation=op, solver=solver)
        if op == "DIFFERENCE":
            self.feed(n.inputs["Mesh 1"], meshes[0], e)
            rest = meshes[1:]
        else:
            rest = meshes
        mesh2 = next(s for s in n.inputs if s.identifier == "Mesh 2")
        for v in rest:
            self.ng.links.new(v.sock, mesh2)
        self._order_multi_input(mesh2, [v.sock for v in rest])
        for sock_name, v in flags.items():
            self.feed(n.inputs[sock_name], v, e)
        mesh = Val(GEO, sock=n.outputs["Mesh"], depth=d, node=n)
        edges = n.outputs.get("Intersecting Edges")
        if solver == "FLOAT" or edges is None:
            return mesh
        return NamedVals(
            [mesh, Val(BOOL, sock=edges, depth=d, node=n)],
            ["Mesh", "IntersectingEdges"],
            self.pub("mesh_boolean"),
        )

    def _order_multi_input(self, sock, sources):
        """Make the multi-input order match `sources` (top-to-bottom = argument order)."""
        with contextlib.suppress(AttributeError, KeyError, RuntimeError):
            links = {l.from_socket.as_pointer(): l for l in sock.links}
            want = [links[s.as_pointer()] for s in sources]
            for i in range(len(want)):
                for j in range(len(want) - 1 - i):
                    a, b = want[j], want[j + 1]
                    if a.multi_input_sort_id < b.multi_input_sort_id:  # higher id = higher in the list
                        a.swap_multi_input_sort_id(b)

    # ------------------------------------------------- compile-time Python layer
    def py_value(self, v, where, what="value"):
        """A Python value known at compile time: numbers/bools from constants, strings, lists."""
        if isinstance(v, Val):
            if not v.is_const or isinstance(v.const, tuple):
                raise GNCompileError(
                    f"this {what} must be known at compile time, but it is computed by nodes "
                    "(fields and node results only exist when Geometry Nodes evaluates)",
                    where,
                )
            c = v.const
            return c if isinstance(c, bool) else (int(c) if float(c).is_integer() else c)
        return v

    def sequence(self, v, where):
        if isinstance(v, (list, tuple, str)):
            return list(v)
        raise GNCompileError(
            "expected a list/tuple known at compile time; to loop inside Geometry Nodes instead "
            f"(one Repeat zone, count computed by nodes), use `for i in {self.pub('repeat')}(n):`",
            where,
        )

    def iterate(self, node, env):
        """Items of a for-loop / comprehension iterable, all known at compile time."""
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id not in env:
            fn = node.func.id
            if fn in ("range", "enumerate", "zip", "reversed"):
                return self.py_builtin(fn, node, env)
        return self.sequence(self.expr(node, env), node)

    def py_builtin(self, fn, e, env):
        """Python builtins evaluated at compile time: range, enumerate, zip, reversed, len, list, tuple, str."""
        if e.keywords and not (fn == "enumerate" and [k.arg for k in e.keywords] == ["start"]):
            raise GNCompileError(f"{fn}() keyword arguments are not supported here", e)
        args = [self.expr(a, env) for a in e.args]
        if fn == "range":
            nums = [self.py_value(a, e, "range() bound") for a in args]
            if not all(isinstance(n, int) and not isinstance(n, bool) for n in nums):
                raise GNCompileError("range() bounds must be integers known at compile time", e)
            rng = range(*nums)
            if len(rng) > 4096:
                raise GNCompileError("loop too long to unroll (> 4096 iterations)", e)
            return [cval(float(i)) for i in rng]
        if fn == "enumerate":
            start = self.py_value(self.expr(e.keywords[0].value, env), e) if e.keywords else 0
            if len(args) == 2:
                start = self.py_value(args[1], e)
            return [(cval(float(start + i)), item) for i, item in enumerate(self.sequence(args[0], e))]
        if fn == "zip":
            return [tuple(t) for t in zip(*[self.sequence(a, e) for a in args])]
        if fn == "reversed":
            return list(reversed(self.sequence(args[0], e)))
        if fn == "len":
            return cval(float(len(self.sequence(args[0], e))))
        if fn in ("list", "tuple"):
            seq = self.sequence(args[0], e) if args else []
            return seq if fn == "list" else tuple(seq)
        if fn == "str":
            return self.format_value(args[0], "", e)
        raise GNCompileError(f"unsupported builtin {fn}()", e)

    def format_value(self, v, spec, where):
        value = self.py_value(v, where, "f-string part")
        if isinstance(value, (list, tuple, Closure)):
            raise GNCompileError("only numbers and strings can be formatted into a string", where)
        return format(value, spec)

    def fstring(self, e, env):
        parts = []
        for part in e.values:
            if isinstance(part, ast.Constant):
                parts.append(str(part.value))
            elif isinstance(part, ast.FormattedValue):
                spec = self.fstring(part.format_spec, env) if part.format_spec is not None else ""
                parts.append(self.format_value(self.expr(part.value, env), spec, part))
            else:
                raise GNCompileError("unsupported f-string part", e)
        return "".join(parts)

    def subscript(self, e, env):
        base = self.expr(e.value, env)
        if not isinstance(base, (list, tuple, str)):
            raise GNCompileError(
                "only compile-time lists/tuples can be indexed; for per-element lookups use "
                f"{self.alias}.EvaluateAtIndex or {self.alias}.IndexSwitch",
                e,
            )
        if isinstance(e.slice, ast.Slice):
            bounds = [
                None if b is None else self.py_value(self.expr(b, env), e, "slice bound")
                for b in (e.slice.lower, e.slice.upper, e.slice.step)
            ]
            return base[slice(*bounds)]
        i = self.py_value(self.expr(e.slice, env), e, "index")
        if not isinstance(i, int) or isinstance(i, bool):
            raise GNCompileError("list indices must be integers", e)
        try:
            return base[i]
        except IndexError:
            raise GNCompileError(f"index {i} out of range (length {len(base)})", e) from None

    def comprehension(self, e, env):
        out: list = []

        def rec(gens, scope):
            if not gens:
                out.append(self.expr(e.elt, scope))
                return
            g = gens[0]
            for item in self.iterate(g.iter, scope):
                inner = dict(scope)  # comprehensions have their own scope
                for k, x in self.assign(g.target, item, e):
                    inner[k] = x
                if all(bool(self.py_value(self.expr(c, inner), c, "condition")) for c in g.ifs):
                    rec(gens[1:], inner)

        rec(e.generators, env)
        return out

    def compile_time_binop(self, op, a, b, where):
        if isinstance(op, ast.Add) and type(a) is type(b) and isinstance(a, (list, str)):
            return a + b
        if isinstance(op, ast.Mult) and isinstance(a, (list, str)):
            n = self.py_value(b, where, "repeat count")
            if isinstance(n, int):
                return a * n
        raise GNCompileError("unsupported operation on compile-time lists/strings", where)

    def expand_starred(self, e, env):
        """``f(*seq)`` -> ``f(seq[0], seq[1], ...)``: items are bound to hidden names in ``env``."""
        if not any(isinstance(a, ast.Starred) for a in e.args):
            return e
        args = []
        for a in e.args:
            if not isinstance(a, ast.Starred):
                args.append(a)
                continue
            for item in self.sequence(self.expr(a.value, env), a):
                name = f"__py2gn_star{len(self.star_names)}"
                self.star_names.append(name)
                env[name] = item
                args.append(ast.copy_location(ast.Name(id=name, ctx=ast.Load()), a))
        return ast.copy_location(ast.Call(func=e.func, args=args, keywords=e.keywords), e)

    def repeat_loop(self, s: ast.For, env: dict) -> None:
        """``for i in gn.Repeat(n): body`` -> one Repeat zone.

        Variables assigned in the body that exist before the loop become the zone's items (loop
        state: fields, values or geometry) and hold the final values afterwards. Everything else
        assigned in the body is local to it. The body may read anything from outside the loop.
        """
        call = s.iter
        assert isinstance(call, ast.Call)
        if len(call.args) != 1 or call.keywords:
            raise GNCompileError(f"usage: for i in {self.pub('repeat')}(iterations):", s)
        if not (isinstance(s.target, ast.Name)):
            raise GNCompileError(
                f"the target of a {self.pub('repeat')} loop is the iteration index: one name", s
            )
        count = self.single(self.expr(call.args[0], env), s)
        if count.type == GEO:
            raise GNCompileError(f"{self.pub('repeat')}(): the iteration count must be a number", s)
        if not count.is_const and depends_on_field(count.sock):
            raise GNCompileError(
                f"{self.pub('repeat')}(): the iteration count must be a single value, but it is a field "
                "(it depends on position/index/an attribute...)",
                s,
            )

        # names assigned in the body (not inside nested functions / comprehensions)
        assigned: list[str] = []

        def collect(node):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.Lambda, ast.ListComp, ast.GeneratorExp)):
                    if isinstance(child, ast.FunctionDef) and child.name not in assigned:
                        assigned.append(child.name)
                    continue
                if (
                    isinstance(child, ast.Name)
                    and isinstance(child.ctx, ast.Store)
                    and child.id not in assigned
                ):
                    assigned.append(child.id)
                collect(child)

        for stmt in s.body:
            collect(stmt)
        index_name = s.target.id
        carried = [n for n in assigned if n in env and n != index_name]
        for n in carried:
            if not isinstance(env[n], Val):
                raise GNCompileError(
                    f"'{n}' holds a compile-time value (list/string/function/tuple); it can't change inside a "
                    f"{self.pub('repeat')} loop because the body is built once",
                    s,
                )
        self.repeat_locals.update(n for n in assigned if n not in env)

        sock_type = {FLOAT: "FLOAT", INT: "INT", BOOL: "BOOLEAN", VEC: "VECTOR", GEO: "GEOMETRY"}
        inits = [env[n] for n in carried]
        d0 = self.depth(count, *inits)
        ri = self.node("GeometryNodeRepeatInput", d0)
        ro = self.node("GeometryNodeRepeatOutput", d0 + 1)
        ri.pair_with_output(ro)
        ro.repeat_items.clear()
        for n, v in zip(carried, inits):
            ro.repeat_items.new(sock_type[v.type], n)
        ri.label = ro.label = f"{index_name} in {self.pub('repeat')}"
        self.feed(ri.inputs["Iterations"], count, s)
        for k, v in enumerate(inits):
            self.feed(ri.inputs[1 + k], v, s)

        body_env = dict(env)
        for k, (n, v) in enumerate(zip(carried, inits)):
            body_env[n] = Val(v.type, sock=ri.outputs[1 + k], depth=d0, node=ri)
        if index_name != "_":
            body_env[index_name] = Val(INT, sock=ri.outputs["Iteration"], depth=d0, node=ri)

        frozen = {id(x) for x in env.values() if isinstance(x, list)}
        self.repeat_frozen.append(frozen)
        try:
            self.block(s.body, body_env, False)
        finally:
            self.repeat_frozen.pop()

        finals = []
        for k, (n, v) in enumerate(zip(carried, inits)):
            f = self.single(body_env[n], s)
            if (f.type == GEO) != (v.type == GEO) or (v.type in (FLOAT, INT, BOOL) and f.type == VEC):
                raise GNCompileError(
                    f"'{n}' changes type inside the loop ({v.type.lower()} before, {f.type.lower()} after one "
                    f"iteration); give it a value of the final type before the loop",
                    s,
                )
            self.feed(ro.inputs[k], f, s)
            finals.append(f)
        d1 = max([d0, *(f.depth for f in finals)]) + 1
        ro.location = (d1 * 200.0, ro.location[1])
        for k, (n, v) in enumerate(zip(carried, inits)):
            env[n] = Val(v.type, sock=ro.outputs[k], depth=d1, node=ro)

    def call(self, e, env):
        saved = self.call_env
        self.call_env = env
        try:
            return self._call(self.expand_starred(e, env), env)
        finally:
            self.call_env = saved

    def _call(self, e, env):
        if isinstance(e.func, ast.Attribute) and self.member(e.func) is None:
            base_name = pubnames.dotted(e.func.value)
            if base_name is None or base_name.split(".")[0] in env:
                base = self.expr(e.func.value, env)
                if isinstance(base, list) and e.func.attr in ("append", "extend") and not e.keywords:
                    if len(e.args) != 1:
                        raise GNCompileError(f"list.{e.func.attr}() takes one argument", e)
                    if any(id(base) in frozen for frozen in self.repeat_frozen):
                        raise GNCompileError(
                            "a list from outside a gn.Repeat loop can't change inside it: the body is built "
                            "once (use an unrolled `for` over range(...) instead)",
                            e,
                        )
                    item = self.expr(e.args[0], env)
                    if e.func.attr == "append":
                        base.append(item)
                    else:
                        base.extend(self.sequence(item, e))
                    return None
        if isinstance(e.func, ast.Name):
            # bare name: yours -- a local helper (nested def / lambda), a function of this file,
            # a node group of the .blend -- or one of Python's compile-time builtins
            fn = e.func.id
            if fn in env:
                target = env[fn]
                if isinstance(target, Closure):
                    return self.inline_call(target.node, e, env, captured=target.env, name=target.name)
                raise GNCompileError(f"'{fn}' is not a function", e)
            if fn in self.inlines:
                return self.inline_call(self.inlines[fn], e, env)
            g = self.funcs.get(fn)
            if g is None:
                cand = bpy.data.node_groups.get(fn)
                if cand is not None and cand.bl_idname == "GeometryNodeTree":
                    g = cand
            if g is not None:
                args = [self.expr(a, env) for a in e.args]
                kwargs = {k.arg: self.expr(k.value, env) for k in e.keywords}
                return self.group_call(g, args, kwargs, e)
            if fn in ("len", "range", "enumerate", "zip", "reversed", "list", "tuple", "str"):
                return self.py_builtin(fn, e, env)
            if fn in ("float", "int", "bool"):  # Python casts stay bare
                return self.builtin_call(fn, e, env)
            raise self._undefined("function", fn, e)
        pub = self.member(e.func)
        if pub is None:
            base = pubnames.dotted(e.func.value) if isinstance(e.func, ast.Attribute) else None
            if base is not None and base.split(".")[0] not in env:
                raise self._undefined("name", base.split(".")[0], e)
            raise GNCompileError(
                f"only calls to your own functions / node groups or to {self.alias}.<Name>(...) are supported",
                e,
            )
        internal = pubnames.CALLABLE.get(pub)
        if internal is None:
            if pub in pubnames.VALUES:
                raise GNCompileError(f"{self.alias}.{pub} is a value, not a function", e)
            if pub in pubnames.TYPES:
                raise GNCompileError(f"{self.alias}.{pub} cannot be called", e)
            if pub in pubnames.DECORATORS:
                raise GNCompileError(
                    f"{self.alias}.{pub} is a decorator: put @{self.alias}.{pub} above a def",
                    e,
                )
            raise self._unknown_member(pub, e)
        return self.builtin_call(internal, e, env)

    def inline_call(self, fdef, e: ast.Call, env, captured: dict | None = None, name: str | None = None):
        """Expand an ``@gn.inline`` function at this call: no node group, its nodes go here.

        Arguments are evaluated in the caller and bound in a fresh scope. Parameters without
        an annotation accept any value (inline functions can be generic); ``gn.tVec``
        promotes scalars like a vector socket would, ``gn.tGeometry`` must get geometry.
        """
        name = name or fdef.name
        if name in self.inline_stack:
            chain = " -> ".join([*self.inline_stack, name])
            raise GNCompileError(f"recursive inline call: {chain}", e)
        a = fdef.args
        if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
            raise GNCompileError("only plain positional parameters are supported", fdef)
        params = [p.arg for p in a.args]
        if len(e.args) > len(params):
            raise GNCompileError(f"{name}() takes {len(params)} arguments, got {len(e.args)}", e)
        bound = dict(zip(params, e.args))
        for k in e.keywords:
            if k.arg is None or k.arg not in params:
                raise GNCompileError(
                    f"{name}() has no parameter '{k.arg}' (parameters: {', '.join(params)})",
                    e,
                )
            if k.arg in bound:
                raise GNCompileError(f"{name}() got '{k.arg}' twice", e)
            bound[k.arg] = k.value
        defaults = dict(zip(params[len(params) - len(a.defaults) :], a.defaults))

        local = dict(captured) if captured is not None else {}  # closures see their enclosing scope
        for p in a.args:
            if p.arg in bound:
                v = self.expr(bound[p.arg], env)  # caller's scope
            elif p.arg in defaults:
                v = cval(param_default(defaults[p.arg], self.aliases))
            else:
                raise GNCompileError(f"{name}() missing argument '{p.arg}'", e)
            T = None if p.annotation is None else annot_type(p.annotation, p, self.aliases)
            if T is not None:  # annotated: a single node value; unannotated: anything (lists, strings...)
                v = self.single(v, e)
            if T == GEO and v.type != GEO:
                raise GNCompileError(f"{name}(): '{p.arg}' expects geometry, got a {v.type.lower()}", e)
            if T is not None and T != GEO and v.type == GEO:
                raise GNCompileError(f"{name}(): '{p.arg}' expects a value, got geometry", e)
            if T == VEC and v.type != VEC:  # like an implicit scalar -> vector socket conversion
                v = cval((float(v.const),) * 3) if v.is_const else self.combine(v, v, v, e)
            local[p.arg] = v

        saved_out, saved_line = self.out_names, self.cur_line
        self.inline_stack.append(name)
        try:
            if isinstance(fdef, ast.Lambda):
                value = self.expr(fdef.body, local)
            else:
                ret = self.block(fdef.body, local, True)
                if ret is None:
                    raise GNCompileError(f"{name}() has no return statement", fdef)
                value = ret[1]
        except GNCompileError as ex:
            if "called at line" in ex.msg:  # keep the innermost call site
                raise
            kind = "inline " if captured is None else ""
            raise GNCompileError(
                f"{ex.msg} (in {kind}{name}(), called at line {e.lineno})", lineno=ex.lineno
            ) from None
        finally:
            self.inline_stack.pop()
            self.out_names, self.cur_line = saved_out, saved_line
        return value

    def builtin_call(self, fn, e, env):
        """Built-in by internal name (see names.py for the public spelling)."""
        if fn in ("at_index", "on_domain"):
            return self.field_eval(fn, e, env)
        if fn in ("attr", "attr_exists"):
            return self.named_attr(fn, e)
        if fn in GEO_FUNCS:
            return self.geo_call(fn, e, env)
        if fn in TUPLE_FIELDS:
            fields = TUPLE_FIELDS[fn]
            if e.args or e.keywords:
                raise GNCompileError(f"usage: {TUPLE_USAGE[fn]} = {self.pub(fn)}()", e)
            return tuple(self.field(f) for f in fields)
        if fn == "repeat":
            raise GNCompileError(
                f"{self.pub(fn)}(n) is only valid as a loop: `for i in {self.pub(fn)}(n):`", e
            )
        if fn == "param":
            raise GNCompileError(
                f"{self.pub(fn)}(...) is only allowed as a parameter default: `x: float = {self.pub(fn)}(1.0, min=0)`",
                e,
            )
        if fn == "outputs":
            raise GNCompileError(
                f"{self.pub(fn)}(...) is only allowed as `return {self.pub(fn)}(name=value, ...)` "
                "or as the return annotation",
                e,
            )
        args = [self.single(self.expr(a, env), e) for a in e.args]
        kwargs = {k.arg: self.expr(k.value, env) for k in e.keywords}
        n = len(args)
        isv = any(a.type == VEC for a in args)
        if kwargs:
            raise GNCompileError(f"{self.pub(fn)}() does not take keyword arguments", e)

        if fn in ("vec", "Vector", "vec3"):
            if n == 1:
                return self.combine(args[0], args[0], args[0], e)
            if n != 3:
                raise GNCompileError(f"{self.alias}.tVec() takes 1 or 3 arguments", e)
            return self.combine(*args, where=e)
        if fn == "float":
            return args[0]
        if fn == "int":
            return self.math("TRUNC", args[0], where=e)
        if fn == "bool":
            return self.compare("NOT_EQUAL", args[0], cval(0.0), e)
        if fn == "length":
            return self.vmath("LENGTH", args[0], scalar_out=True, where=e)
        if fn == "dot":
            return self.vmath("DOT_PRODUCT", *args, scalar_out=True, where=e)
        if fn == "distance":
            return self.vmath("DISTANCE", *args, scalar_out=True, where=e)
        if fn == "log":
            base = args[1] if n > 1 else cval(math.e)
            return self.math("LOGARITHM", args[0], base, where=e)
        if fn in ("lerp", "mix"):
            if n != 3:
                raise GNCompileError(f"{self.pub(fn)}(a, b, t) takes 3 arguments", e)
            a, b, t = args
            return self.binop(
                ast.Add(),
                a,
                self.binop(ast.Mult(), self.binop(ast.Sub(), b, a, e), t, e),
                e,
            )
        if fn == "clamp":
            x = args[0]
            lo = args[1] if n > 1 else cval(0.0)
            hi = args[2] if n > 2 else cval(1.0)
            if isv:
                return self.vmath("MAXIMUM", self.vmath("MINIMUM", x, hi, where=e), lo, where=e)
            if all(a.is_const for a in (x, lo, hi)):
                return cval(min(max(x.const, lo.const), hi.const))
            d = self.depth(x, lo, hi)
            node = self.node("ShaderNodeClamp", d)
            for i, a in enumerate((x, lo, hi)):
                self.feed(node.inputs[i], a, e)
            return Val(FLOAT, sock=node.outputs[0], depth=d, node=node)
        if fn == "wrap":  # wrap(x, lo, hi)
            if n != 3:
                raise GNCompileError(f"{self.pub('wrap')}(x, lo, hi) takes 3 arguments", e)
            if isv:
                return self.vmath("WRAP", args[0], args[2], args[1], where=e)
            return self.math("WRAP", args[0], args[2], args[1], where=e)
        if fn in ("min", "max") and n > 2:  # variadic
            acc = args[0]
            for a in args[1:]:
                acc = self.call_builtin2(fn, acc, a, e)
            return acc
        if n == 1:
            if isv:
                if fn in UNARY_V:
                    return self.vmath(UNARY_V[fn], args[0], where=e)
            elif fn in UNARY_F:
                return self.math(UNARY_F[fn], args[0], where=e)
            if fn == "normalize" and not isv:
                raise GNCompileError(f"{self.pub('normalize')}() expects a vector", e)
        if n == 2 and (fn in BINARY_F or fn in BINARY_V):
            return self.call_builtin2(fn, args[0], args[1], e)
        raise GNCompileError(f"unknown function or wrong arity: {self.pub(fn)}({n} args)", e)

    def call_builtin2(self, fn, a, b, e):
        if VEC in (a.type, b.type):
            if fn not in BINARY_V:
                raise GNCompileError(f"{self.pub(fn)}() is not supported for vectors", e)
            return self.vmath(BINARY_V[fn], a, b, where=e)
        if fn not in BINARY_F or BINARY_F[fn] is None:
            raise GNCompileError(f"{self.pub(fn)}() is not supported for scalars", e)
        return self.math(BINARY_F[fn], a, b, where=e)

    # --- statements
    def assign(self, target, v, where):
        if isinstance(target, ast.Name):
            if isinstance(v, Val) and v.node is not None and not v.node.label:
                v.node.label = target.id
            env_set = target.id
            return [(env_set, v)]
        if isinstance(target, (ast.Tuple, ast.List)):
            if not isinstance(v, (tuple, list)) or len(v) != len(target.elts):
                raise GNCompileError("tuple unpacking size mismatch", where)
            out = []
            for t, x in zip(target.elts, v):
                out += self.assign(t, x, where)
            return out
        raise GNCompileError("only assignment to names / tuples of names is supported", where)

    def block(self, stmts, env, allow_return):
        ret = None
        for i, s in enumerate(stmts):
            self.cur_line = getattr(s, "lineno", self.cur_line)
            if ret is not None:
                raise GNCompileError("code after return", s)
            if (
                isinstance(s, ast.Expr)
                and isinstance(s.value, ast.Constant)
                and isinstance(s.value.value, str)
            ):
                continue  # docstring / comment string
            if isinstance(s, ast.Expr):
                result = self.expr(s.value, env)
                if result is not None:  # e.g. `gn.SetPosition(mesh, ...)` without `mesh = `
                    raise GNCompileError(
                        "the result of this expression is discarded; assign it (e.g. `mesh = ...`)", s
                    )
                continue  # list.append / list.extend
            if isinstance(s, ast.FunctionDef):  # local helper: expanded inline wherever it is called
                if s.decorator_list:
                    raise GNCompileError("decorators are not supported on nested functions", s)
                env[s.name] = Closure(s, env, s.name)
                continue
            if isinstance(s, (ast.Break, ast.Continue)):
                raise GNCompileError(
                    f"`{type(s).__name__.lower()}` is not supported (loops are unrolled); "
                    "filter the sequence instead, e.g. with a comprehension",
                    s,
                )
            if isinstance(s, ast.Pass):
                continue
            if isinstance(s, (ast.Assign, ast.AnnAssign)):
                targets = s.targets if isinstance(s, ast.Assign) else [s.target]
                v = self.expr(s.value, env)
                for t in targets:
                    for k, x in self.assign(t, v, s):
                        env[k] = x
                continue
            if isinstance(s, ast.AugAssign):
                if not isinstance(s.target, ast.Name):
                    raise GNCompileError("augmented assignment only to names", s)
                cur = self.expr(s.target, env)
                env[s.target.id] = self.binop(s.op, cur, self.expr(s.value, env), s)
                continue
            if isinstance(s, ast.If):
                c = self.expr(s.test, env)
                if not isinstance(c, Val):  # strings / lists: truthiness is known while compiling
                    c = cval(bool(self.py_value(c, s, "condition")))
                if c.is_const:
                    self.block(s.body if c.const else s.orelse, env, False)
                    continue
                env_t, env_f = dict(env), dict(env)
                self.block(s.body, env_t, False)
                self.block(s.orelse, env_f, False)
                for k in set(env_t) | set(env_f):
                    a, b = env_t.get(k), env_f.get(k)
                    if a is b:
                        env[k] = a
                    elif a is None or b is None:
                        env.pop(k, None)  # defined in one branch only -> not visible after the if
                    elif not (isinstance(a, Val) and isinstance(b, Val)):
                        raise GNCompileError(
                            f"'{k}' holds a compile-time value (list/string/function/tuple) that differs "
                            "between the branches of an if whose condition is computed by nodes",
                            s,
                        )
                    else:
                        env[k] = self.switch(c, b, a, s)
                        if not env[k].node.label:
                            env[k].node.label = k
                continue
            if isinstance(s, ast.For):
                if s.orelse:
                    raise GNCompileError("for ... else is not supported", s)
                if isinstance(s.iter, ast.Call) and self.member(s.iter.func) == "Repeat":
                    self.repeat_loop(s, env)  # one Repeat zone; the body is built once
                    continue
                # unrolled at compile time: the sequence (range, list, enumerate, zip...) must be known
                for item in self.iterate(s.iter, env):
                    for k, x in self.assign(s.target, item, s):
                        env[k] = x
                    self.block(s.body, env, False)
                continue
            if isinstance(s, ast.Return):
                if not allow_return or i != len(stmts) - 1:
                    raise GNCompileError(
                        "only a single `return` as the last top-level statement is supported",
                        s,
                    )
                if s.value is None:
                    raise GNCompileError("return needs a value", s)
                rv = s.value
                if isinstance(rv, ast.Call) and self.member(rv.func) == "Outputs":
                    # return gn.Outputs(name=value, ...): named outputs
                    if rv.args or not rv.keywords or any(k.arg is None for k in rv.keywords):
                        raise GNCompileError(f"usage: return {self.alias}.Outputs(name=value, ...)", s)
                    self.out_names = [k.arg for k in rv.keywords if k.arg is not None]
                    vals = tuple(self.expr(k.value, env) for k in rv.keywords)
                    ret = (s, vals if len(vals) > 1 else vals[0])
                    continue
                ret = (s, self.expr(rv, env))
                continue
            raise GNCompileError(f"unsupported statement {type(s).__name__}", s)
        return ret
