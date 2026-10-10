"""Regenerate the README's checklist of Geometry Nodes (supported / not yet).

    blender --background --factory-startup --python tools/node_checklist.py

(or ``scripts/update_node_list.ps1``). The node list and grouping come from Blender's own Add menu
(``bl_ui/node_add_menu_geometry.py``); a node is ticked when the compiler can emit it. Only the
block between ``<!-- nodes:start -->`` and ``<!-- nodes:end -->`` in README.md is rewritten.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

import bl_ui
import bpy

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

from py2gn.compiler import names, tables

START, END = "<!-- nodes:start -->", "<!-- nodes:end -->"

# Add-menu helpers whose first string argument is a node idname
NODE_HELPERS = (
    "node_operator",
    "node_operator_with_outputs",
    "node_operator_with_searchable_enum",  # Math, Vector Math, Boolean Math... (one entry per operation in search)
    "node_operator_with_searchable_enum_socket",
)

ZONE_HELPERS = {
    "repeat_zone": "GeometryNodeRepeatInput",
    "simulation_zone": "GeometryNodeSimulationInput",
    "for_each_element_zone": "GeometryNodeForeachGeometryElementInput",
    "closure_zone": "NodeClosureInput",
}

# Nodes the builder emits for syntax rather than for a named gn. function
SYNTAX = {
    "ShaderNodeMath": "operators, `gn.Sin` `gn.Sqrt` `gn.Min` ...",
    "ShaderNodeVectorMath": "vector operators, `gn.Dot` `gn.Cross` `gn.Length` ...",
    "FunctionNodeCompare": "comparisons",
    "FunctionNodeBooleanMath": "`and` `or` `not`",
    "GeometryNodeSwitch": "`if` / `else`, `a if c else b`",
    "ShaderNodeClamp": "`gn.Clamp`",
    "ShaderNodeCombineXYZ": "`gn.tVec(x, y, z)`",
    "ShaderNodeSeparateXYZ": "`.x` `.y` `.z`",
    "ShaderNodeValue": "float constants",
    "FunctionNodeInputBool": "bool constants",
    "GeometryNodeRepeatInput": "`for i in gn.Repeat(n)`",
    "GeometryNodeForeachGeometryElementInput": "`for ... in gn.ForEachElement(...)`",
    "GeometryNodeJoinGeometry": "`gn.JoinGeometry`",
    "GeometryNodeCaptureAttribute": "`gn.CaptureAttribute`",
    "GeometryNodeAttributeDomainSize": "`gn.DomainSize`",
    "GeometryNodeAttributeStatistic": "`gn.AttributeStatistic`",
    "GeometryNodeMeshBoolean": "`gn.MeshBoolean`",
    "GeometryNodeIndexSwitch": "`gn.IndexSwitch`",
    "GeometryNodeFieldAtIndex": "`gn.EvaluateAtIndex`",
    "GeometryNodeFieldOnDomain": "`gn.EvaluateOnDomain`",
    "GeometryNodeInputNamedAttribute": "`gn.NamedAttribute`, `gn.NamedAttributeExists`",
    "NodeGroupInput": "function parameters",
    "NodeGroupOutput": "return values",
}


def menu_tree() -> list[tuple[list[str], str]]:
    """[(menu path, node idname)] in the order of Blender's Add menu."""
    src = Path(os.path.dirname(bl_ui.__file__), "node_add_menu_geometry.py").read_text(encoding="utf-8")
    menus: dict[str, tuple[str, list]] = {}
    for cls in [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)]:
        label, mpath, items = None, None, []
        for st in cls.body:
            if (
                isinstance(st, ast.Assign)
                and isinstance(st.targets[0], ast.Name)
                and isinstance(st.value, ast.Constant)
            ):
                if st.targets[0].id == "bl_label":
                    label = st.value.value
                if st.targets[0].id == "menu_path":
                    mpath = st.value.value
            if isinstance(st, ast.FunctionDef) and st.name == "draw":
                calls = sorted(
                    (c for c in ast.walk(st) if isinstance(c, ast.Call)),
                    key=lambda c: (c.lineno, c.col_offset),
                )
                for c in calls:
                    fn = c.func.attr if isinstance(c.func, ast.Attribute) else getattr(c.func, "id", "")
                    pos = [
                        a.value for a in c.args if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    ]
                    kw = {k.arg: k.value.value for k in c.keywords if isinstance(k.value, ast.Constant)}
                    if fn in NODE_HELPERS and pos:
                        items.append(("node", pos[0]))
                    elif fn in ZONE_HELPERS:
                        items.append(("node", ZONE_HELPERS[fn]))
                    elif fn == "color_mix_node":
                        items.append(("node", "ShaderNodeMix"))
                    elif fn == "draw_menu" and (kw.get("path") or pos):
                        items.append(("menu", kw.get("path") or pos[0]))
        if label is not None:
            menus[str(mpath or label or "Root")] = (str(label), items)
    seen: set[str] = set()
    out: list[tuple[list[str], str]] = []

    def walk(path: str, trail: list[str]) -> None:
        if path not in menus:  # "Group" / "Layout": node groups, frames, reroutes
            return
        for kind, v in menus[path][1]:
            if kind == "menu":
                walk(v, [*trail, (menus[v][0] if v in menus else "") or v])
            elif v not in seen:
                seen.add(v)
                out.append((trail, v))

    walk("Root", [])
    return out


def supported() -> dict[str, str]:
    """idname -> how py2gn reaches it."""
    out = dict(SYNTAX)
    for internal, spec in tables.GEO_OPS.items():
        pub = names.PUBLIC_OF.get(internal)
        if pub:
            out.setdefault(spec[0], f"`gn.{pub}`")
    by_node: dict[str, list[str]] = {}
    for internal, (idname, _sock, _t) in tables.FIELDS.items():
        pub = names.PUBLIC_OF.get(internal)
        if pub:
            by_node.setdefault(idname, []).append(f"`gn.{pub}`")
    for internal, fields in tables.TUPLE_FIELDS.items():
        pub = names.PUBLIC_OF.get(internal)
        if pub:
            idname = tables.FIELDS[fields[0]][0]
            by_node.setdefault(idname, []).insert(0, f"`gn.{pub}()`")
    for idname, spellings in by_node.items():
        out.setdefault(idname, ", ".join(spellings))
    # anything else the compiler emits by name
    emitted = set()
    for f in (ROOT / "compiler").glob("*.py"):
        emitted |= set(
            re.findall(
                r'"((?:GeometryNode|ShaderNode|FunctionNode)[A-Za-z0-9]+)"', f.read_text(encoding="utf-8")
            )
        )
    for idname in emitted - set(out):
        out[idname] = ""
    return out


def render() -> str:
    tree = menu_tree()
    ok = supported()
    ng = bpy.data.node_groups.new("__checklist", "GeometryNodeTree")
    assert ng is not None
    try:
        label = {idn: ng.nodes.new(idn).bl_label for _, idn in tree}
    finally:
        bpy.data.node_groups.remove(ng)
    done = sum(1 for _, idn in tree if idn in ok)
    summary = (
        f"**{done} of {len(tree)}** nodes of Blender {bpy.app.version_string} "
        "(generated by `tools/node_checklist.py`, grouped as in the Add menu)."
    )
    lines = [START, "", summary, ""]
    current: list[str] | None = None
    for path, idn in tree:
        if path != current:
            top = path[0] if path else "Other"
            if current is None or not current or current[0] != top:
                lines += ["", f"#### {top}", ""]
            if len(path) > 1:
                lines.append(f"- **{' / '.join(path[1:])}**")
            current = path
        indent = "  " if len(path) > 1 else ""
        mark = "x" if idn in ok else " "
        how = f" - {ok[idn]}" if ok.get(idn) else ""
        lines.append(f"{indent}- [{mark}] {label[idn]}{how}")
    lines += ["", END]
    in_menu = {idn for _, idn in tree}
    not_nodes = {
        "GeometryNodeGroup",
        "GeometryNodeTree",
        "GeometryNodeRepeatOutput",
        "GeometryNodeForeachGeometryElementOutput",
    }  # group calls, the tree type, zone outputs
    stray = sorted(idn for idn in ok if idn not in in_menu and idn not in not_nodes)
    if stray:  # supported nodes the Add menu doesn't list (renamed? removed?) -- worth a look
        print(f"node checklist: note: supported but not in the Add menu: {', '.join(stray)}")
    return "\n".join(lines)


def main() -> None:
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    block = render()
    if START in text and END in text:
        a, b = text.index(START), text.index(END) + len(END)
        text = text[:a] + block + text[b:]
    elif "<details>" in text and "\n...\n" in text:
        text = text.replace("\n...\n", "\n" + block + "\n", 1)  # first run: the placeholder
    else:
        raise SystemExit(f"README.md has neither {START}/{END} markers nor the '...' placeholder")
    readme.write_text(text, encoding="utf-8", newline="\n")
    print(f"node checklist: {block.splitlines()[2]}")


if __name__ == "__main__":
    main()
