"""Shared helpers: compile, build test geometry, evaluate node groups."""

from __future__ import annotations

import os
import random
import unittest
from pathlib import Path

import bpy
from mathutils import Vector

from py2gn.compiler import gn_compile

ADDON_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ADDON_ROOT / "examples" / "functions.py"
ARTIFACTS = Path(os.environ.get("PY2GN_TEST_ARTIFACTS", ADDON_ROOT / "tests" / "artifacts"))

ATTR_TYPE = {
    "NodeSocketVector": "FLOAT_VECTOR",
    "NodeSocketBool": "BOOLEAN",
    "NodeSocketInt": "INT",
}


def iface(group, in_out):
    return [i for i in group.interface.items_tree if i.item_type == "SOCKET" and i.in_out == in_out]


class CompilerTestCase(unittest.TestCase):
    """Removes every node group / object / mesh created during a test."""

    def setUp(self):
        self._groups = {g.name for g in bpy.data.node_groups}
        self._objects = {o.name for o in bpy.data.objects}
        self._meshes = {m.name for m in bpy.data.meshes}
        self._clouds = {p.name for p in bpy.data.pointclouds}

    def tearDown(self):
        for o in [o for o in bpy.data.objects if o.name not in self._objects]:
            bpy.data.objects.remove(o)
        for g in [g for g in bpy.data.node_groups if g.name not in self._groups]:
            bpy.data.node_groups.remove(g)
        for m in [m for m in bpy.data.meshes if m.name not in self._meshes]:
            bpy.data.meshes.remove(m)
        for p in [p for p in bpy.data.pointclouds if p.name not in self._clouds]:
            bpy.data.pointclouds.remove(p)

    def compile(self, src: str) -> dict:
        return {g.name: g for g in gn_compile(src)}


def grid(n: int = 4, jitter: float = 0.0, seed: int = 0):
    rnd = random.Random(seed)
    verts = [
        (
            x + rnd.uniform(-jitter, jitter),
            y + rnd.uniform(-jitter, jitter),
            rnd.uniform(-1, 1) if jitter else 0.0,
        )
        for y in range(n)
        for x in range(n)
    ]
    faces = [
        (y * n + x, y * n + x + 1, (y + 1) * n + x + 1, (y + 1) * n + x)
        for y in range(n - 1)
        for x in range(n - 1)
    ]
    mesh = bpy.data.meshes.new("__test_grid")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh, verts, faces


def with_defaults(group, values: dict):
    """Copy of ``group`` with interface defaults changed (modifier overrides are not scriptable here)."""
    copy = group.copy()
    assert copy is not None
    for it in iface(copy, "INPUT"):
        if it.name in values:
            it.default_value = values[it.name]
    return copy


def evaluate(group, data, inputs: dict | None = None, attrs=()) -> dict:
    """Run ``group`` as a modifier on ``data``; snapshot the resulting mesh / curves."""
    g = with_defaults(group, inputs) if inputs else group
    assert g is not None
    ob = bpy.data.objects.new("__test_obj", data)
    bpy.context.scene.collection.objects.link(ob)
    ob.modifiers.new("test", "NODES").node_group = g
    try:
        eo = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        gs = eo.evaluated_geometry()  # keep a reference: its mesh dies with it
        out: dict = {}
        if gs.mesh is not None:
            me = gs.mesh
            flat = [0] * (2 * len(me.edges))
            me.edges.foreach_get("vertices", flat)
            out["edge_verts"] = list(zip(flat[0::2], flat[1::2]))
            loops = [0] * len(me.loops)
            me.loops.foreach_get("vertex_index", loops)
            starts, totals = [0] * len(me.polygons), [0] * len(me.polygons)
            me.polygons.foreach_get("loop_start", starts)
            me.polygons.foreach_get("loop_total", totals)
            out["polys"] = [tuple(loops[s : s + t]) for s, t in zip(starts, totals)]
            out.update(
                verts=[v.co.copy() for v in me.vertices],
                edges=len(me.edges),
                faces=len(me.polygons),
                face_normal_z=[p.normal.z for p in me.polygons],
            )
            out["attrs"] = _attrs(me.attributes, attrs)
        if gs.curves is not None:
            cu = gs.curves
            out["curves"] = len(cu.curves)
            out["curve_positions"] = [Vector(d.vector) for d in cu.attributes["position"].data]
            out["curve_attrs"] = _attrs(cu.attributes, attrs)
        if gs.pointcloud is not None:
            pc = gs.pointcloud
            out["points"] = [Vector(d.vector) for d in pc.attributes["position"].data]
            out["radii"] = (
                [d.value for d in pc.attributes["radius"].data] if "radius" in pc.attributes else []
            )
            out["point_attrs"] = _attrs(pc.attributes, attrs)
        del gs
        return out
    finally:
        bpy.data.objects.remove(ob)
        if inputs:
            bpy.data.node_groups.remove(g)


def _attrs(attributes, names):
    return {
        a.name: [tuple(d.vector) if a.data_type == "FLOAT_VECTOR" else d.value for d in a.data]
        for a in attributes
        if a.name in names
    }


def evaluate_per_point(group, samples: list[list]) -> list[list]:
    """Evaluate a value-only group once per sample, as a field over len(samples) points.

    Inputs are fed per point through named attributes, outputs read back the same way,
    so this exercises real field evaluation rather than constant folding.
    """
    ins, outs = iface(group, "INPUT"), iface(group, "OUTPUT")
    n = len(samples)
    me = bpy.data.meshes.new("__test_points")
    me.vertices.add(n)
    for j, it in enumerate(ins):
        a = me.attributes.new(f"in{j}", ATTR_TYPE.get(it.socket_type, "FLOAT"), "POINT")
        for k in range(n):
            if it.socket_type == "NodeSocketVector":
                a.data[k].vector = samples[k][j]
            else:
                a.data[k].value = samples[k][j]
    tree = bpy.data.node_groups.new("__test_harness", "GeometryNodeTree")
    assert tree is not None
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi, go = tree.nodes.new("NodeGroupInput"), tree.nodes.new("NodeGroupOutput")
    gn = tree.nodes.new("GeometryNodeGroup")
    gn.node_tree = group
    for j, it in enumerate(ins):
        na = tree.nodes.new("GeometryNodeInputNamedAttribute")
        na.data_type = ATTR_TYPE.get(it.socket_type, "FLOAT")
        na.inputs["Name"].default_value = f"in{j}"
        tree.links.new(na.outputs["Attribute"], gn.inputs[j])
    geo = gi.outputs[0]
    for j, it in enumerate(outs):
        sn = tree.nodes.new("GeometryNodeStoreNamedAttribute")
        sn.data_type = ATTR_TYPE.get(it.socket_type, "FLOAT")
        sn.inputs["Name"].default_value = f"out{j}"
        tree.links.new(geo, sn.inputs["Geometry"])
        tree.links.new(gn.outputs[j], sn.inputs["Value"])
        geo = sn.outputs[0]
    tree.links.new(geo, go.inputs[0])
    try:
        res = evaluate(tree, me, attrs=[f"out{j}" for j in range(len(outs))])["attrs"]
    finally:
        bpy.data.node_groups.remove(tree)
        bpy.data.meshes.remove(me)
    return [[res[f"out{j}"][k] for j in range(len(outs))] for k in range(n)]


def unit_cube(offset=(0.0, 0.0, 0.0)):
    """Closed, outward-oriented unit cube [0, 1]^3 (+ offset)."""
    ox, oy, oz = offset
    verts = [(x + ox, y + oy, z + oz) for z in (0, 1) for y in (0, 1) for x in (0, 1)]
    faces = [
        (0, 2, 3, 1),
        (4, 5, 7, 6),
        (0, 1, 5, 4),
        (2, 6, 7, 3),
        (0, 4, 6, 2),
        (1, 3, 7, 5),
    ]
    mesh = bpy.data.meshes.new("__test_cube")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def volume(r: dict) -> float:
    """Signed volume of an evaluated closed mesh (divergence theorem over a fan triangulation)."""
    v = r["verts"]
    total = 0.0
    for poly in r["polys"]:
        a = v[poly[0]]
        for i in range(1, len(poly) - 1):
            total += a.dot(v[poly[i]].cross(v[poly[i + 1]]))
    return total / 6.0


def rel_err(ref, got) -> float:
    if isinstance(ref, bool) or isinstance(got, bool):
        return 0.0 if bool(ref) == bool(got) else 1.0
    if isinstance(ref, Vector) or isinstance(got, tuple):
        r = ref.copy() if isinstance(ref, Vector) else Vector(ref)
        g = got.copy() if isinstance(got, Vector) else Vector(got)
        return (r - g).length / max(1.0, r.length)
    return abs(ref - got) / max(1.0, abs(ref))
