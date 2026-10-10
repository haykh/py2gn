"""Compile source text into Geometry Nodes groups."""

from __future__ import annotations

import ast

import bpy

from .builder import Builder
from .errors import GNCompileError
from .interface import reorder_interface, sync_sockets
from .names import DEFAULT_ALIAS, find_aliases, namespace_member
from .params import function_kind, param_default, parse_param
from .values import GEO, NamedVals, Val, annot_type

SOURCE_KEY = "gn_source"


def compile_function(fdef, src, funcs, aliases: set[str] | None = None, inlines: dict | None = None):
    aliases = aliases or {DEFAULT_ALIAS}
    name = fdef.name
    ng = bpy.data.node_groups.get(name)
    if ng is not None and (ng.bl_idname != "GeometryNodeTree" or SOURCE_KEY not in ng):
        raise GNCompileError(
            f"a node group named '{name}' already exists and was not made by py2gn; "
            f"rename the function to avoid overwriting it",
            fdef,
        )
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    assert ng is not None

    a = fdef.args
    if a.vararg or a.kwarg or a.kwonlyargs or a.posonlyargs:
        raise GNCompileError("only plain positional parameters are supported", fdef)
    defaults = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults)
    alias = DEFAULT_ALIAS if DEFAULT_ALIAS in aliases else min(aliases)
    in_specs = []
    for arg, dflt in zip(a.args, defaults):
        T = annot_type(arg.annotation, arg, aliases)
        meta = None if dflt is None else parse_param(dflt, aliases, alias, T, arg.arg)
        if meta is not None:
            dv = meta["default"]
        else:
            dv = None if dflt is None else param_default(dflt, aliases)
            meta = {}
        in_specs.append((arg.arg, T, dv, meta))

    ng.nodes.clear()
    in_items = sync_sockets(ng, "INPUT", in_specs)

    b = Builder(ng, funcs, src, aliases, inlines)
    gin = ng.nodes.new("NodeGroupInput")
    gin.location = (-250.0, 0.0)
    env = {}
    for it, (pname, T, _dv, _meta) in zip(in_items, in_specs):
        sock = next(s for s in gin.outputs if s.identifier == it.identifier)
        env[pname] = Val(T, sock=sock, depth=0, node=None)

    ret = b.block(fdef.body, env, True)
    if ret is None:
        raise GNCompileError(f"{name}() has no return statement", fdef)
    rnode, rval = ret
    vals = list(rval) if isinstance(rval, tuple) else [rval]
    for v in vals:
        if isinstance(v, tuple):
            raise GNCompileError("nested tuples in return are not supported", rnode)

    # output names/types
    ra = fdef.returns
    if isinstance(ra, ast.Call) and namespace_member(ra.func, aliases) == "Outputs":
        if ra.args or any(k.arg is None for k in ra.keywords):
            raise GNCompileError(f"usage: -> {b.alias}.Outputs(name=type, ...)", ra)
        ra = ast.Dict(
            keys=[ast.Constant(k.arg) for k in ra.keywords],
            values=[k.value for k in ra.keywords],
        )
    if isinstance(ra, ast.Dict) and b.out_names is not None:
        raise GNCompileError(
            f"name outputs either in the annotation or in `return {b.alias}.Outputs(...)`, not both",
            rnode,
        )
    if isinstance(ra, ast.Dict):
        if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in ra.keys):
            raise GNCompileError("output names must be string literals", fdef)
        names = [k.value for k in ra.keys if isinstance(k, ast.Constant)]
        types = [annot_type(v, ra, aliases) for v in ra.values]
        if len(names) != len(vals):
            raise GNCompileError(
                f"return annotation declares {len(names)} outputs, return has {len(vals)}",
                rnode,
            )
    else:
        if isinstance(ra, ast.Tuple):
            types = [annot_type(x, ra, aliases) for x in ra.elts]
        elif ra is not None:
            types = [annot_type(ra, ra, aliases)]
        else:
            types = [v.type for v in vals]
        if len(types) != len(vals):
            if isinstance(rval, NamedVals) and len(types) == 1:
                b.single(rval, rnode)  # explains the outputs and how to pick one
            raise GNCompileError(
                f"the return annotation declares {len(types)} output(s), but {len(vals)} value(s) are returned",
                rnode,
            )
        if b.out_names is not None:
            names = list(b.out_names)
        elif len(vals) == 1:
            names = ["Result"]
        elif isinstance(rval, NamedVals):  # `return gn.FaceOfCorner(c)`: the node's output names
            names = list(rval.names)
        elif isinstance(rnode.value, ast.Tuple):
            names = [
                x.id if isinstance(x, ast.Name) else f"Result{i}" for i, x in enumerate(rnode.value.elts)
            ]
        else:
            names = [f"Result{i}" for i in range(len(vals))]
    seen = {}
    for i, nm in enumerate(names):  # dedupe
        if nm in seen:
            seen[nm] += 1
            names[i] = f"{nm}.{seen[nm]:03d}"
        else:
            seen[nm] = 0

    out_items = sync_sockets(ng, "OUTPUT", [(n, T, None) for n, T in zip(names, types)])
    reorder_interface(ng, out_items + in_items)

    gout = ng.nodes.new("NodeGroupOutput")
    gout.location = ((b.max_depth + 1) * 200.0, 0.0)
    for it, v in zip(out_items, vals):
        v = b.materialize(b.single(v, rnode))  # lists, strings, loops... are not outputs
        sock = next(s for s in gout.inputs if s.identifier == it.identifier)
        ng.links.new(v.sock, sock)

    # validate: e.g. a field (position/index/attribute-dependent) feeding a single-value socket
    for l in ng.links:
        if not l.is_valid:
            line = b.node_line.get(l.to_node.name)
            tn = l.to_node.label or l.to_node.bl_label
            raise GNCompileError(
                f"'{tn}' input '{l.to_socket.name}' needs a single value but receives a field "
                f"(it depends on position/index/an attribute/etc.)",
                lineno=line,
            )
    has_geo = any(T == GEO for _, T, *_ in in_specs) and types and types[0] == GEO
    ng.is_modifier = bool(has_geo)

    seg = ast.get_source_segment(src, fdef) or ""
    ng[SOURCE_KEY] = seg
    doc = ast.get_docstring(fdef)
    if doc:
        ng.description = doc
    return ng


def gn_compile(src):
    """Compile every top-level `def` in `src` into a Geometry Nodes group. Returns the groups.

    Functions decorated with ``@gn.inline`` get no group: their body is expanded at every call.
    """
    tree = ast.parse(src)
    aliases = find_aliases(tree)
    alias = DEFAULT_ALIAS if DEFAULT_ALIAS in aliases else min(aliases)
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    kinds = {f.name: function_kind(f, aliases, alias) for f in defs}
    inlines = {f.name: f for f in defs if kinds[f.name] == "inline"}  # usable from anywhere in the file
    funcs, out = {}, []
    for node in defs:
        if kinds[node.name] == "inline":
            continue
        existed = node.name in bpy.data.node_groups
        try:
            g = compile_function(node, src, funcs, aliases, inlines)
        except Exception:
            ng = bpy.data.node_groups.get(node.name)
            if not existed and ng is not None:
                bpy.data.node_groups.remove(ng)  # don't leave half-built new groups behind
            raise
        funcs[node.name] = g
        out.append(g)
    return out
