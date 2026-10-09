"""Compile-time Python: lists, loops, f-strings, comprehensions, *args, local helpers."""

import random

import bpy
from mathutils import Vector

from py2gn.compiler import GNCompileError, gn_compile, reference_functions

from .common import CompilerTestCase, evaluate, evaluate_per_point, grid, iface, rel_err

SRC = """
import py2gn.lang as gn

OFFSETS = None  # module-level statements are ignored


def zz_store_loop(m: gn.tGeometry) -> gn.tGeometry:
    vals = [gn.Position.x, gn.Position.y * 2, gn.Index + 0.5]
    for i, v in enumerate(vals):
        m = gn.StoreNamedAttribute(m, f"a{i}", v)
    for name, v in zip(["px", "py"], [gn.Position.x, gn.Position.y]):
        m = gn.StoreNamedAttribute(m, "p_" + name, v)
    return m


def zz_switch_comp(m: gn.tGeometry) -> gn.tGeometry:
    m = zz_store_loop(m)
    picked = gn.IndexSwitch(gn.Index % 3, *[gn.NamedAttribute(f"a{i}") for i in range(3)])
    return gn.StoreNamedAttribute(m, "picked", picked)


def zz_closure(m: gn.tGeometry, k: float = 2.0) -> gn.tGeometry:
    def lift(g, dz):  # sees k from the enclosing function
        return gn.SetPosition(g, offset=gn.tVec(0, 0, dz * k))

    m = lift(m, 1.0)
    return lift(m, 0.5)  # 3.0 in total


def zz_lambda(x: float, y: float):
    sq = lambda t: t * t  # noqa: E731
    pick = lambda xs, i: xs[i]  # noqa: E731
    vals = [sq(x), sq(y), x * y]
    total = 0.0
    for v in vals[1:]:
        total += v
    return pick(vals, 0) + total + len(vals)


def zz_listops(x: float):
    xs = []
    for i in range(4):
        if i % 2 == 0:  # known while compiling
            xs.append(x * i)
    xs.extend([x, x])
    ys = [v + 1 for v in xs if True] + [x] * 2
    return sum_all(ys)


@gn.inline
def sum_all(xs):
    total = 0.0
    for v in xs:
        total += v
    return total


def zz_polys(m: gn.tGeometry) -> gn.tGeometry:
    # the pattern from wall.py: per-point corner positions, one k-gon per selected point
    corners = [gn.tVec(0, 0, 0), gn.tVec(0.2, 0, 0), gn.tVec(0.2, 0.2, 0), gn.tVec(0, 0.2, 0)]
    for i, c in enumerate(corners):
        m = gn.StoreNamedAttribute(m, f"TEMP_q{i}", gn.Position + c + gn.tVec(0, 0, 1))

    def polys(sel, prefix, k):
        pts = gn.MeshToPoints(m, selection=sel)
        mesh = gn.RealizeInstances(gn.InstanceOnPoints(pts, gn.MeshCircle(k, fill="NGON")))
        pos = gn.IndexSwitch(
            gn.Index % k,
            *[gn.NamedAttribute(f"TEMP_{prefix}{i}", type=gn.tVec) for i in range(k)],
        )
        return gn.SetPosition(mesh, pos)

    return polys(gn.Index < 3, "q", len(corners))


def zz_generator_join(m: gn.tGeometry) -> gn.tGeometry:
    return gn.JoinGeometry(*(gn.SetPosition(m, offset=gn.tVec(0, 0, z)) for z in range(3)))
"""


class TestMeta(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SRC)
        self.ref = reference_functions(SRC)

    def test_loops_and_fstrings(self):
        mesh, verts, _ = grid(3)
        a = evaluate(self.groups["zz_store_loop"], mesh, attrs=("a0", "a1", "a2", "p_px", "p_py"))["attrs"]
        for i, (x, y, _z) in enumerate(verts):
            self.assertAlmostEqual(a["a0"][i], x)
            self.assertAlmostEqual(a["a1"][i], 2 * y)
            self.assertAlmostEqual(a["a2"][i], i + 0.5)
            self.assertAlmostEqual(a["p_px"][i], x)
            self.assertAlmostEqual(a["p_py"][i], y)

    def test_starred_comprehension(self):
        mesh, verts, _ = grid(3)
        a = evaluate(self.groups["zz_switch_comp"], mesh, attrs=("picked",))["attrs"]
        for i, (x, y, _z) in enumerate(verts):
            self.assertAlmostEqual(a["picked"][i], (x, 2 * y, i + 0.5)[i % 3])

    def test_closure_sees_enclosing_scope(self):
        mesh, _, _ = grid(2)
        vs = evaluate(self.groups["zz_closure"], mesh)["verts"]
        self.assertTrue(all(abs(v.z - 3.0) < 1e-6 for v in vs))

    def test_values_match_python(self):
        rnd = random.Random(4)
        for name, n_in in (("zz_lambda", 2), ("zz_listops", 1)):
            samples = [[rnd.uniform(-2, 2) for _ in range(n_in)] for _ in range(50)]
            got = evaluate_per_point(self.groups[name], samples)
            for row, (g,) in zip(samples, got):
                self.assertLess(rel_err(self.ref[name](*row), g), 1e-5, name)

    def test_wall_pattern(self):
        mesh, verts, _ = grid(3)
        r = evaluate(self.groups["zz_polys"], mesh)
        self.assertEqual((len(r["verts"]), r["faces"]), (12, 3))
        corners = [Vector(c) for c in ((0, 0, 1), (0.2, 0, 1), (0.2, 0.2, 1), (0, 0.2, 1))]
        expected = [Vector(verts[p]) + c for p in range(3) for c in corners]
        for v, e in zip(r["verts"], expected):
            self.assertLess((v - e).length, 1e-5)

    def test_generator_into_join(self):
        mesh, _, _ = grid(2)
        r = evaluate(self.groups["zz_generator_join"], mesh)
        self.assertEqual(sorted({round(v.z, 4) for v in r["verts"]}), [0.0, 1.0, 2.0])

    def test_no_helper_groups(self):
        self.assertNotIn("polys", bpy.data.node_groups)
        self.assertEqual([i.name for i in iface(self.groups["zz_lambda"], "OUTPUT")], ["Result"])

    def test_errors(self):
        head = "def zz(m: gn.tGeometry) -> gn.tGeometry:\n"
        for body, fragment in (
            (
                "    for i in range(gn.DomainSize(m)):\n        m = gn.FlipFaces(m)\n    return m\n",
                "must be known at compile time",
            ),
            ("    for p in gn.Position:\n        m = gn.FlipFaces(m)\n    return m\n", "Repeat zone"),
            ("    return gn.StoreNamedAttribute(m, f'a{gn.Index}', 1.0)\n", "must be known at compile time"),
            ("    for i in range(3):\n        break\n    return m\n", "`break` is not supported"),
            ("    xs = [1.0, 2.0]\n    return gn.StoreNamedAttribute(m, 'a', xs)\n", "got a list of 2"),
            (
                "    xs = [1.0, 2.0]\n    return gn.StoreNamedAttribute(m, 'a', xs[gn.Index])\n",
                "must be known at compile time",
            ),
            ("    xs = [1.0]\n    return gn.StoreNamedAttribute(m, 'a', xs[3])\n", "index 3 out of range"),
            ("    gn.FlipFaces(m)\n    return m\n", "result of this expression is discarded"),
            (
                "    def f(x):\n        return x + nope\n    return gn.StoreNamedAttribute(m, 'a', f(1.0))\n",
                "undefined name 'nope' (in f(), called at line 4)",
            ),
            ("    f = lambda x: f(x)\n    return gn.StoreNamedAttribute(m, 'a', f(1.0))\n", "recursive"),
            (
                "    name = 'a' if gn.Index > 2 else 'b'\n    return gn.StoreNamedAttribute(m, name, 1.0)\n",
                "strings are compile-time only",
            ),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))
