"""for ... in gn.ForEachElement(...): one For Each Geometry Element zone."""

from mathutils import Vector

from py2gn.compiler import GNCompileError, gn_compile

from .common import CompilerTestCase, evaluate, grid

SRC = """
def zz_face_results(m: gn.tGeometry) -> gn.tGeometry:
    each = gn.ForEachElement(m, gn.Position, domain="FACE")
    for i, element, center in each:
        each.result(cx=center.x * 2, idx=i, n=gn.DomainSize(element, "FACE"))
    g = gn.StoreNamedAttribute(each.Geometry, "cx", each.cx, domain="FACE")
    g = gn.StoreNamedAttribute(g, "idx", each.idx, domain="FACE")
    return gn.StoreNamedAttribute(g, "n", each.n, domain="FACE")

def zz_generate(m: gn.tGeometry) -> gn.tGeometry:
    each = gn.ForEachElement(m, gn.Position)
    for i, _el, p in each:
        each.generate(gn.SetPosition(gn.MeshCircle(4, radius=0.1, fill="NGON"), offset=p), source=i)
    return gn.StoreNamedAttribute(each.Generated, "source", each.source)

def zz_selection_and_switch(m: gn.tGeometry) -> gn.tGeometry:
    each = gn.ForEachElement(m, selection=gn.Index < 3)
    for i, _el in each:
        shape = gn.MeshCircle(3, fill="NGON") if i % 2 == 0 else gn.MeshCircle(5, fill="NGON")  # single-value i
        each.generate(shape)
    return each.Generated

def zz_two_generates(m: gn.tGeometry) -> gn.tGeometry:
    each = gn.ForEachElement(m, gn.Position, selection=gn.Index < 2)
    for _i, _el, p in each:
        each.generate(gn.SetPosition(gn.MeshCircle(3), offset=p))
        each.generate(gn.SetPosition(gn.MeshCircle(4), offset=p))
    return each.Generated
"""


class TestForEach(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SRC)

    def test_per_element_results(self):
        mesh, verts, faces = grid(4)
        g = self.groups["zz_face_results"]
        self.assertEqual(sum(n.bl_idname == "GeometryNodeForeachGeometryElementInput" for n in g.nodes), 1)
        a = evaluate(g, mesh, attrs=("cx", "idx", "n"))["attrs"]
        for f, poly in enumerate(faces):
            centre_x = sum(verts[v][0] for v in poly) / 4
            self.assertAlmostEqual(a["cx"][f], 2 * centre_x, places=5)
            self.assertEqual((a["idx"][f], a["n"][f]), (f, 1))  # the element is a single face

    def test_generate_with_fields(self):
        mesh, verts, _ = grid(3)
        r = evaluate(self.groups["zz_generate"], mesh, attrs=("source",))
        self.assertEqual((len(r["verts"]), r["faces"]), (4 * len(verts), len(verts)))
        for v, src in zip(r["verts"], r["attrs"]["source"]):
            self.assertAlmostEqual((v - Vector(verts[src])).length, 0.1, places=5)

    def test_selection_and_single_value_index(self):
        mesh, _, _ = grid(3)
        r = evaluate(self.groups["zz_selection_and_switch"], mesh)
        self.assertEqual((len(r["verts"]), r["faces"]), (3 + 5 + 3, 3))

    def test_several_generates_are_joined(self):
        mesh, _, _ = grid(3)
        self.assertEqual(len(evaluate(self.groups["zz_two_generates"], mesh)["verts"]), 2 * (3 + 4))

    def test_errors(self):
        head = "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    each = gn.ForEachElement(m, gn.Position)\n"
        for body, fragment in (
            (
                "    total = 0.0\n    for i, e, p in each:\n        total = total + p.x\n    return m\n",
                "iterations are independent",
            ),
            (
                "    for i, e, p in each:\n        if p.x > 0:\n            each.result(a=p.x)\n    return m\n",
                "at the top level of the loop body",
            ),
            ("    each.result(a=1.0)\n    return m\n", "can only be called inside its loop"),
            ("    return gn.StoreNamedAttribute(m, 'a', each.a)\n", "available after the loop"),
            (
                "    for i, e in each:\n        each.result(a=i)\n    return m\n",
                "(index, element, value): 3 names",
            ),
            (
                (
                    "    for i, e, p in each:\n        each.result(a=i)\n    for i, e, p in each:\n        each.result(b=i)\n"
                    "    return m\n"
                ),
                "already used",
            ),
            (
                "    for i, e, p in each:\n        each.result(a=i)\n    return gn.StoreNamedAttribute(m, 'a', each.b)\n",
                "has no output 'b'",
            ),
            ("    for i, e, p in each:\n        each.result(Geometry=i)\n    return m\n", "reserved"),
            ("    return each\n", "is a loop: iterate it"),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))
