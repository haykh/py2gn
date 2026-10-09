"""Diagnostics, interface preservation and safety rules."""

import bpy

from py2gn.compiler import GNCompileError, gn_compile

from .common import CompilerTestCase

CASES = [
    ("def zz(x):\n    return x + q\n", "undefined name 'q'", 2),
    (
        "def zz(x):\n    while x:\n        pass\n    return x\n",
        "unsupported statement While",
        2,
    ),
    ("def zz(n: float):\n    return gn.NamedAttribute(n)\n", "string literal", 2),
    (
        "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return m + 1\n",
        "geometry used where a value is expected",
        2,
    ),
    (
        "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.SetPosition(m, ofset=gn.tVec(0, 0, 1))\n",
        "no parameter 'ofset'",
        2,
    ),
    (
        "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.ExtrudeMesh(m, mode='SIDEWAYS')\n",
        "must be one of",
        2,
    ),
    (
        "def zz(c: gn.tGeometry) -> gn.tGeometry:\n    return gn.CurveToMesh(c, fill_caps=gn.Index > 2)\n",
        "needs a single value",
        2,
    ),
    (
        "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    if gn.Position.z > 0:\n        m = gn.FlipFaces(m)\n    return m\n",
        "single-value condition",
        2,
    ),
    (
        "def zz(c: gn.tGeometry):\n    return gn.DomainSize(c, 'EDGE', component='CURVE')\n",
        "has no EDGE domain",
        2,
    ),
    ("def zz(x: string):\n    return x\n", "unknown type annotation", 1),
    # every built-in field counts as a field for geometry if/else (regression: is_cyclic was missed)
    (
        "def zz(c: gn.tGeometry) -> gn.tGeometry:\n    return gn.ReverseCurve(c) if gn.IsSplineCyclic else c\n",
        "single-value condition",
        2,
    ),
    (
        "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.FlipFaces(m) if gn.EdgeVerticesVertexIndex1 > 0 else m\n",
        "single-value condition",
        2,
    ),
    (
        "def zz():\n    a, b = gn.EdgeVertices(1)\n    return a\n",
        "usage: v1, v2, p1, p2 = gn.EdgeVertices()",
        2,
    ),
]


class TestErrors(CompilerTestCase):
    def test_messages_and_lines(self):
        for src, fragment, line in CASES:
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(src)
                self.assertIn(fragment, str(cm.exception))
                self.assertEqual(cm.exception.lineno, line)
                self.assertNotIn("zz", bpy.data.node_groups, "failed new group must be removed")

    def test_syntax_error(self):
        with self.assertRaises(SyntaxError):
            gn_compile("def zz(x):\n    y = x +\n")

    def test_does_not_overwrite_foreign_groups(self):
        bpy.data.node_groups.new("zz_handmade", "GeometryNodeTree")
        with self.assertRaises(GNCompileError):
            gn_compile("def zz_handmade(x):\n    return x\n")

    def test_recompile_keeps_links(self):
        self.compile("def zz_f(p: gn.tVec, a: float = 1.0):\n    o = p * a\n    return o, a\n")
        user = bpy.data.node_groups.new("__test_user", "GeometryNodeTree")
        pos = user.nodes.new("GeometryNodeInputPosition")
        node = user.nodes.new("GeometryNodeGroup")
        node.node_tree = bpy.data.node_groups["zz_f"]
        sp = user.nodes.new("GeometryNodeSetPosition")
        user.links.new(pos.outputs[0], node.inputs["p"])
        user.links.new(node.outputs["o"], sp.inputs["Offset"])
        self.compile(
            "def zz_f(p: gn.tVec, a: float = 1.0, b: float = 0.0):\n    o = p * a + gn.tVec(b)\n    return o, a\n"
        )
        self.assertEqual([s.name for s in node.inputs], ["p", "a", "b"])
        self.assertEqual(
            sorted((lk.from_socket.name, lk.to_socket.name) for lk in user.links),
            [("Position", "p"), ("o", "Offset")],
        )
