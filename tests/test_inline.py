"""@gn.inline: expansion at the call site instead of a node group."""

import math
import random

import bpy
from mathutils import Vector

from py2gn.compiler import GNCompileError, gn_compile, reference_functions

from .common import CompilerTestCase, evaluate, evaluate_per_point, grid, iface, rel_err

SRC = """
import py2gn.lang as gn


def zz_scalar(x: float, y: float):
    return sq(x) + lerp3(x, y) + twice_sq(y)  # inline functions may be defined later


@gn.inline
def sq(x):
    return x * x


@gn.inline
def lerp3(a, b, t: float = 0.5):
    return a + (b - a) * t


@gn.inline
def twice_sq(x):
    return sq(x) * 2  # inline calling inline


@gn.inline
def polar(p: gn.tVec):
    return gn.Outputs(r=gn.Length(p), a=gn.Atan2(p.y, p.x))


def zz_vector(p: gn.tVec, q: gn.tVec):
    return lerp3(p, q, t=0.25)


def zz_outputs(p: gn.tVec):
    r, a = polar(p)
    return gn.Outputs(radius=r, angle=a)


def zz_promote(x: float):
    r, a = polar(x)  # float -> (x, x, x), like a vector socket
    return r


@gn.inline
def lift(mesh: gn.tGeometry, k: float = 1.0):
    return gn.SetPosition(mesh, offset=gn.tVec(0, 0, k))


def zz_geo(mesh: gn.tGeometry) -> gn.tGeometry:
    return lift(lift(mesh), k=2.0)
"""

INLINE = ("sq", "lerp3", "twice_sq", "polar", "lift")


class TestInline(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SRC)
        self.ref = reference_functions(SRC)

    def test_no_groups_for_inline_functions(self):
        self.assertEqual(
            sorted(self.groups),
            ["zz_geo", "zz_outputs", "zz_promote", "zz_scalar", "zz_vector"],
        )
        for name in INLINE:
            self.assertNotIn(name, bpy.data.node_groups)
        for g in self.groups.values():
            self.assertFalse(any(n.bl_idname == "GeometryNodeGroup" for n in g.nodes), g.name)

    def _check(self, name, make_row, n=100):
        rnd = random.Random(1)
        samples = [make_row(rnd) for _ in range(n)]
        got = evaluate_per_point(self.groups[name], samples)
        for row, out in zip(samples, got):
            ref = self.ref[name](*row)
            ref = ref if isinstance(ref, tuple) else (ref,)
            for r, g in zip(ref, out):
                self.assertLess(rel_err(r, g), 1e-4, name)

    def test_values_match_reference(self):
        self._check("zz_scalar", lambda r: [r.uniform(-3, 3), r.uniform(-3, 3)])
        vec = lambda r: Vector([r.uniform(-2, 2) for _ in range(3)])
        self._check("zz_vector", lambda r: [vec(r), vec(r)])
        self._check("zz_outputs", lambda r: [vec(r)])

    def test_generic_parameters(self):
        # the same inline function produced scalar Math in one caller and Vector Math in the other
        self.assertTrue(any(n.bl_idname == "ShaderNodeMath" for n in self.groups["zz_scalar"].nodes))
        vnodes = self.groups["zz_vector"].nodes
        self.assertTrue(any(n.bl_idname == "ShaderNodeVectorMath" for n in vnodes))
        self.assertFalse(any(n.bl_idname == "ShaderNodeMath" for n in vnodes))

    def test_callers_outputs_not_clobbered(self):
        self.assertEqual(
            [i.name for i in iface(self.groups["zz_outputs"], "OUTPUT")],
            ["radius", "angle"],
        )
        self.assertEqual([i.name for i in iface(self.groups["zz_promote"], "OUTPUT")], ["Result"])

    def test_vector_promotion(self):
        got = evaluate_per_point(self.groups["zz_promote"], [[x] for x in (-2.0, 0.5, 3.0)])
        for (x,), (r,) in zip([[-2.0], [0.5], [3.0]], got):
            self.assertAlmostEqual(r, math.sqrt(3) * abs(x), places=5)

    def test_geometry(self):
        mesh, _, _ = grid(3)
        r = evaluate(self.groups["zz_geo"], mesh)
        self.assertTrue(all(abs(v.z - 3.0) < 1e-6 for v in r["verts"]))

    def test_unused_inline_is_not_compiled(self):
        groups = self.compile(
            "@gn.inline\ndef broken(x):\n    return x + nope\n\ndef zz_ok(x: float):\n    return x\n"
        )
        self.assertEqual(list(groups), ["zz_ok"])

    def test_errors(self):
        cases = (
            (
                "@gn.inline\ndef r(x):\n    return r(x)\n\ndef zz(x: float):\n    return r(x)\n",
                "recursive inline call: r -> r",
                3,
            ),
            (
                "@gn.inline\ndef f(a, b):\n    return a + b\n\ndef zz(x: float):\n    return f(x)\n",
                "f() missing argument 'b'",
                6,
            ),
            (
                "@gn.inline\ndef f(a):\n    return a\n\ndef zz(x: float):\n    return f(x, c=1)\n",
                "f() has no parameter 'c'",
                6,
            ),
            (
                "@gn.inline\ndef f(m: gn.tGeometry):\n    return m\n\ndef zz(x: float):\n    return f(x)\n",
                "'m' expects geometry",
                6,
            ),
            (
                "@gn.inline\ndef f(a):\n    return a + nope\n\ndef zz(x: float):\n    return f(x)\n",
                "undefined name 'nope' (in inline f(), called at line 6)",
                3,
            ),
            (
                "@staticmethod\ndef zz(x: float):\n    return x\n",
                "unsupported decorator @staticmethod",
                1,
            ),
            (
                "def zz(x: float):\n    return gn.inline(x)\n",
                "gn.inline is a decorator",
                2,
            ),
        )
        for src, fragment, line in cases:
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(src)
                self.assertIn(fragment, str(cm.exception))
                self.assertEqual(cm.exception.lineno, line)
