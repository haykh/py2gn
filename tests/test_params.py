"""Group-input metadata: gn.Param(default, min, max, description, subtype)."""

import bpy

from py2gn.compiler import GNCompileError, gn_compile, reference_functions

from .common import CompilerTestCase, evaluate, grid, iface

SRC = """
def zz_params(
    m: gn.tGeometry,
    Height: float = gn.Param(2.0, min=0.0, max=10.0, subtype="DISTANCE", description="Wall height"),
    Taper: float = gn.Param(0.5, min=0, max=1, subtype="factor"),
    Count: int = gn.Param(4, min=1, max=64, description="Merlons per edge"),
    Dir: gn.tVec = gn.Param(gn.tVec(0, 0, 1), min=-1, max=1, subtype="DIRECTION"),
    Flip: bool = gn.Param(False, description="Flip the normals"),
    Angle: float = gn.Param(gn.Pi / 4, subtype="ANGLE"),
    Spin: gn.tVec = gn.Param(gn.tVec(0, 0, 2 * gn.Pi), subtype="EULER"),
    Plain: float = 3.0,
) -> gn.tGeometry:
    return gn.SetPosition(m, offset=Dir * Height * Taper * Count)
"""


def items(group):
    return {i.name: i for i in iface(group, "INPUT")}


class TestParams(CompilerTestCase):
    def test_metadata(self):
        it = items(self.compile(SRC)["zz_params"])
        h = it["Height"]
        self.assertEqual(
            (h.default_value, h.min_value, h.max_value, h.subtype, h.description),
            (2.0, 0.0, 10.0, "DISTANCE", "Wall height"),
        )
        self.assertEqual((it["Taper"].subtype, it["Taper"].max_value), ("FACTOR", 1.0))
        c = it["Count"]
        self.assertEqual(
            (c.default_value, c.min_value, c.max_value, c.description), (4, 1, 64, "Merlons per edge")
        )
        d = it["Dir"]
        self.assertEqual(
            (tuple(d.default_value), d.min_value, d.max_value, d.subtype),
            ((0.0, 0.0, 1.0), -1.0, 1.0, "DIRECTION"),
        )
        self.assertEqual((it["Flip"].default_value, it["Flip"].description), (False, "Flip the normals"))
        self.assertEqual(it["Angle"].subtype, "ANGLE")
        self.assertAlmostEqual(it["Angle"].default_value, 0.7853982, places=6)
        self.assertAlmostEqual(tuple(it["Spin"].default_value)[2], 6.2831853, places=5)
        self.assertEqual(it["Spin"].subtype, "EULER")
        self.assertEqual(
            (it["Plain"].default_value, it["Plain"].subtype, it["Plain"].description), (3.0, "NONE", "")
        )

    def test_values_still_work(self):
        mesh, _, _ = grid(2)
        vs = evaluate(self.compile(SRC)["zz_params"], mesh)["verts"]
        self.assertTrue(all(abs(v.z - 2.0 * 0.5 * 4) < 1e-6 for v in vs))
        self.assertAlmostEqual(reference_functions(SRC)["zz_params"].__defaults__[0], 2.0)

    def test_recompile_resets_and_keeps_links(self):
        g = self.compile(SRC)["zz_params"]
        user = bpy.data.node_groups.new("__test_user", "GeometryNodeTree")
        node = user.nodes.new("GeometryNodeGroup")
        node.node_tree = g
        val = user.nodes.new("ShaderNodeValue")
        user.links.new(val.outputs[0], node.inputs["Height"])
        plain = SRC.replace(
            'gn.Param(2.0, min=0.0, max=10.0, subtype="DISTANCE", description="Wall height")', "2.0"
        )
        it = items(self.compile(plain)["zz_params"])["Height"]
        self.assertEqual((it.subtype, it.description), ("NONE", ""))
        self.assertLess(it.min_value, -1e30)
        self.assertGreater(it.max_value, 1e30)
        self.assertEqual(len(user.links), 1)  # same socket identity: the link survived

    def test_inline_defaults(self):
        g = self.compile(
            "@gn.inline\ndef f(x, k: float = gn.Param(3.0, min=0)):\n    return x * k\n"
            "def zz_i(x: float):\n    return f(x)\n"
        )["zz_i"]
        self.assertTrue(any(n.bl_idname == "ShaderNodeMath" for n in g.nodes))

    def test_errors(self):
        for sig, fragment in (
            ("x: float = gn.Param(5.0, min=0, max=1)", "lies outside [0.0, 1.0]"),
            ("x: float = gn.Param(0.5, min=2, max=1)", "min 2.0 is greater than max 1.0"),
            ("x: bool = gn.Param(True, min=0)", "min applies to float, int and vector"),
            ("x: int = gn.Param(1, subtype='ANGLE')", "not valid for int"),
            ("x: bool = gn.Param(True, subtype='FACTOR')", "bool parameters have no subtypes"),
            ("x: float = gn.Param(1.0, step=0.1)", "unknown Param option 'step'"),
            ("x: int = gn.Param(1, max=2.5)", "must be a whole number"),
            ("x: float = gn.Param(1.0, description=gn.Pi)", "description must be a string literal"),
            ("x: float = gn.Param(1.0, 2.0)", "takes one positional argument"),
            ("x: float = gn.Param(gn.Index)", "defaults must be constants"),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(f"def zz({sig}):\n    return x\n")
                self.assertIn(fragment, str(cm.exception))
        with self.assertRaises(GNCompileError) as cm:
            gn_compile("def zz(x: float):\n    return gn.Param(1.0)\n")
        self.assertIn("only allowed as a parameter default", str(cm.exception))
