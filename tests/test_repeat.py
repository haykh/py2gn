"""for ... in gn.Repeat(n): one Repeat zone instead of unrolled copies."""

import random

from py2gn.compiler import GNCompileError, gn_compile, reference_functions

from .common import CompilerTestCase, evaluate, evaluate_per_point, grid, rel_err

SRC = """
def zz_double(m: gn.tGeometry) -> gn.tGeometry:
    x = gn.Position.x  # a field as loop state
    for _ in gn.Repeat(3):
        x = x * 2
    return gn.StoreNamedAttribute(m, "x", x)

def zz_sum(m: gn.tGeometry, n: int = 5) -> gn.tGeometry:
    s = 0
    for i in gn.Repeat(n):  # count from a parameter; i is the iteration index
        s += i
    return gn.StoreNamedAttribute(m, "s", s)

def zz_lift(m: gn.tGeometry) -> gn.tGeometry:
    for _ in gn.Repeat(gn.DomainSize(m, "FACE")):  # count computed by nodes
        m = gn.SetPosition(m, offset=gn.tVec(0, 0, 0.5))
    return m

def zz_multi(m: gn.tGeometry) -> gn.tGeometry:
    v = gn.tVec(0, 0, 0)
    k = 0
    for i in gn.Repeat(4):
        step = gn.tVec(1, 0, 0) if gn.Index % 2 == 0 else gn.tVec(0, 1, 0)  # field switch inside
        v = v + step * i
        k += 1
    m = gn.StoreNamedAttribute(m, "v", v)
    return gn.StoreNamedAttribute(m, "k", k)

def zz_nested(m: gn.tGeometry) -> gn.tGeometry:
    c = 0
    for _ in gn.Repeat(3):
        for _ in gn.Repeat(2):
            c += 1
        for j in range(2):  # unrolled inside the zone
            c += j
    return gn.StoreNamedAttribute(m, "c", c)

def zz_values(x: float):
    y = x
    for i in gn.Repeat(6):  # x arrives per point (a field); the count must stay a single value
        y = y * 0.5 + i
    return y
"""


def count(group, idname):
    return sum(n.bl_idname == idname for n in group.nodes)


class TestRepeat(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SRC)

    def test_field_state_body_built_once(self):
        g = self.groups["zz_double"]
        self.assertEqual(count(g, "GeometryNodeRepeatInput"), 1)
        self.assertEqual(count(g, "ShaderNodeMath"), 1)  # one multiply, not three
        mesh, verts, _ = grid(3)
        a = evaluate(g, mesh, attrs=("x",))["attrs"]
        for i, p in enumerate(verts):
            self.assertAlmostEqual(a["x"][i], 8 * p[0], places=5)

    def test_iteration_index_and_parameter_count(self):
        for n in (5, 10):
            with self.subTest(n=n):
                mesh, _, _ = grid(2)
                a = evaluate(self.groups["zz_sum"], mesh, {"n": n}, attrs=("s",))["attrs"]
                self.assertEqual(set(a["s"]), {n * (n - 1) // 2})

    def test_geometry_state_and_computed_count(self):
        mesh, _, _ = grid(3)  # 4 faces
        vs = evaluate(self.groups["zz_lift"], mesh)["verts"]
        self.assertTrue(all(abs(v.z - 2.0) < 1e-6 for v in vs))
        self.assertEqual(count(self.groups["zz_lift"], "GeometryNodeSetPosition"), 1)

    def test_several_items_and_switch_inside(self):
        mesh, verts, _ = grid(3)
        a = evaluate(self.groups["zz_multi"], mesh, attrs=("v", "k"))["attrs"]
        for i in range(len(verts)):
            expect = (6.0, 0.0, 0.0) if i % 2 == 0 else (0.0, 6.0, 0.0)
            self.assertEqual(a["v"][i], expect)
            self.assertEqual(a["k"][i], 4)

    def test_nested_zones(self):
        mesh, _, _ = grid(2)
        a = evaluate(self.groups["zz_nested"], mesh, attrs=("c",))["attrs"]
        self.assertEqual(set(a["c"]), {3 * (2 + 1)})
        self.assertEqual(count(self.groups["zz_nested"], "GeometryNodeRepeatInput"), 2)

    def test_values_match_python(self):
        rnd = random.Random(2)
        samples = [[rnd.uniform(-5, 5)] for _ in range(40)]
        got = evaluate_per_point(self.groups["zz_values"], samples)
        ref = reference_functions(SRC)["zz_values"]
        for (x,), (g,) in zip(samples, got):
            self.assertLess(rel_err(ref(x), g), 1e-5)

    def test_errors(self):
        head = "def zz(m: gn.tGeometry) -> gn.tGeometry:\n"
        for body, fragment in (
            (
                "    for _ in gn.Repeat(gn.Index):\n        m = gn.FlipFaces(m)\n    return m\n",
                "must be a single value, but it is a field",
            ),
            (
                (
                    "    x = 0.0\n    for _ in gn.Repeat(2):\n        x = gn.tVec(1, 0, 0)\n"
                    "    return gn.StoreNamedAttribute(m, 'x', x)\n"
                ),
                "'x' changes type inside the loop",
            ),
            (
                "    xs = []\n    for _ in gn.Repeat(2):\n        xs.append(1.0)\n    return m\n",
                "can't change inside it",
            ),
            (
                "    name = 'a'\n    for _ in gn.Repeat(2):\n        name = 'b'\n    return m\n",
                "holds a compile-time value",
            ),
            (
                "    for _ in gn.Repeat(2):\n        t = 1.0\n    return gn.StoreNamedAttribute(m, 'a', t)\n",
                "only assigned inside a gn.Repeat loop",
            ),
            (
                "    for a, b in gn.Repeat(2):\n        m = gn.FlipFaces(m)\n    return m\n",
                "the iteration index: one name",
            ),
            ("    for _ in gn.Repeat(2):\n        break\n    return m\n", "`break` is not supported"),
            ("    return gn.StoreNamedAttribute(m, 'a', gn.Repeat(3))\n", "is only valid as a loop"),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))
