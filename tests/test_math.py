"""Pure value functions: compiled graphs vs. the plain-Python reference semantics."""

import random

from mathutils import Vector

from py2gn.compiler import reference_functions

from .common import EXAMPLES, CompilerTestCase, evaluate_per_point, iface, rel_err

VALUE_FUNCTIONS = ("smoothstep", "ripple", "polar", "fbm_like", "piecewise")


class TestMath(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.src = EXAMPLES.read_text(encoding="utf-8")
        self.groups = self.compile(self.src)
        self.ref = reference_functions(self.src)

    def _check(self, name, n=200, seed=0, tol=1e-4):
        group = self.groups[name]
        rnd = random.Random(seed)
        samples = []
        for _ in range(n):
            row: list = []
            for j, it in enumerate(iface(group, "INPUT")):
                if it.socket_type == "NodeSocketVector":
                    row.append(Vector([rnd.uniform(-2, 2) for _ in range(3)]))
                elif it.socket_type == "NodeSocketBool":
                    row.append(rnd.random() < 0.5)
                else:
                    row.append(rnd.uniform(-3, 3) if j == 0 else it.default_value + rnd.uniform(-0.3, 0.3))
            samples.append(row)
        got = evaluate_per_point(group, samples)
        worst = 0.0
        for row, out in zip(samples, got):
            ref = self.ref[name](*row)
            ref = ref if isinstance(ref, tuple) else (ref,)
            for r, g in zip(ref, out):
                worst = max(worst, rel_err(r, g))
        self.assertLess(worst, tol, f"{name}: max relative error {worst:.2e}")

    def test_value_functions(self):
        for name in VALUE_FUNCTIONS:
            with self.subTest(function=name):
                self._check(name)

    def test_interface(self):
        g = self.groups["polar"]
        self.assertEqual([i.name for i in iface(g, "OUTPUT")], ["radius", "angle", "inside"])
        self.assertEqual(
            [i.socket_type for i in iface(g, "OUTPUT")],
            ["NodeSocketFloat", "NodeSocketFloat", "NodeSocketBool"],
        )
        r = self.groups["ripple"]
        self.assertEqual([i.name for i in iface(r, "OUTPUT")], ["offset", "h"])
        self.assertAlmostEqual(iface(r, "INPUT")[1].default_value, 4.0)

    def test_vec_default(self):
        g = self.groups["flatten_above_top"]
        up = next(i for i in iface(g, "INPUT") if i.name == "up")
        self.assertEqual(tuple(up.default_value), (0.0, 0.0, 1.0))

    def test_return_outputs(self):
        g = self.compile(
            "def zz_o(p: gn.tVec):\n    r = gn.Length(p)\n    return gn.Outputs(radius=r, dir=gn.Normalize(p), big=r > 1)\n"
        )["zz_o"]
        self.assertEqual([i.name for i in iface(g, "OUTPUT")], ["radius", "dir", "big"])
        self.assertEqual(
            [i.socket_type for i in iface(g, "OUTPUT")],
            ["NodeSocketFloat", "NodeSocketVector", "NodeSocketBool"],
        )
        g = self.compile("def zz_o2(x: float) -> gn.Outputs(n=int):\n    return gn.Floor(x)\n")["zz_o2"]
        self.assertEqual(
            [(i.name, i.socket_type) for i in iface(g, "OUTPUT")],
            [("n", "NodeSocketInt")],
        )

    def test_constant_folding(self):
        g = self.compile("def zz_fold(x: float):\n    return x * (2 * gn.Pi / gn.Tau) + gn.Sin(0)\n")[
            "zz_fold"
        ]
        math_nodes = [n for n in g.nodes if n.bl_idname == "ShaderNodeMath"]
        self.assertEqual(len(math_nodes), 2)  # x*1 and +0 stay; the constants are folded
