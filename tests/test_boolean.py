"""Mesh Boolean (operations x solvers by volume, operands, intersecting edges, errors) and Mesh Bevel."""

from py2gn.compiler import GNCompileError, gn_compile

from .common import CompilerTestCase, evaluate, unit_cube, volume

# Two unit cubes, the second shifted by (0.5, 0.25, 0.25): overlap 0.5 * 0.75 * 0.75 = 0.28125.
# The shift avoids coplanar faces, which Blender's FLOAT solver cannot handle (with a pure x shift it
# returned union 1.0 / intersect 1.0 / difference 0.0 while EXACT and MANIFOLD were right).
OPS = {"UNION": 2 - 0.28125, "INTERSECT": 0.28125, "DIFFERENCE": 1 - 0.28125}
SOLVERS = ("EXACT", "FLOAT", "MANIFOLD")


def _case(op: str, solver: str) -> str:
    call = f'gn.MeshBoolean(a, b, operation="{op}", solver="{solver}")'
    body = f"    return {call}\n" if solver == "FLOAT" else f"    m, _e = {call}\n    return m\n"
    return (
        f"def zz_{op.lower()}_{solver.lower()}(a: gn.tGeometry) -> gn.tGeometry:\n"
        "    b = gn.SetPosition(a, offset=gn.tVec(0.5, 0.25, 0.25))\n" + body
    )


CASES = "".join(_case(op, solver) for op in OPS for solver in SOLVERS)

EXTRA = """
def zz_two_cutters(a: gn.tGeometry) -> gn.tGeometry:
    left = gn.SetPosition(a, offset=gn.tVec(-0.75, 0, 0))
    right = gn.SetPosition(a, offset=gn.tVec(0.75, 0, 0))
    m, _e = gn.MeshBoolean(a, left, right, operation="DIFFERENCE", solver="EXACT")
    return m  # [0, 1] minus [-0.75, 0.25] minus [0.75, 1.75] -> [0.25, 0.75]

def zz_union3(a: gn.tGeometry) -> gn.tGeometry:
    b = gn.SetPosition(a, offset=gn.tVec(0.5, 0, 0))
    c = gn.SetPosition(a, offset=gn.tVec(0, 0.5, 0))
    m, _e = gn.MeshBoolean(a, b, c, operation="UNION", solver="EXACT")  # coplanar faces: needs EXACT
    return m

def zz_edges(a: gn.tGeometry, tolerant: bool = False) -> gn.tGeometry:
    b = gn.SetPosition(a, offset=gn.tVec(0.5, 0.5, 0.5))
    m, edges = gn.MeshBoolean(a, b, operation="UNION", solver="EXACT", hole_tolerant=tolerant)
    return gn.StoreNamedAttribute(m, "isect", edges, domain="EDGE")
"""


class TestMeshBoolean(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(CASES + EXTRA)

    def test_operations_and_solvers(self):
        for op, expect in OPS.items():
            for solver in SOLVERS:
                with self.subTest(op=op, solver=solver):
                    r = evaluate(self.groups[f"zz_{op.lower()}_{solver.lower()}"], unit_cube())
                    self.assertAlmostEqual(volume(r), expect, places=4)

    def test_multiple_operands(self):
        self.assertAlmostEqual(volume(evaluate(self.groups["zz_two_cutters"], unit_cube())), 0.5, places=4)
        # inclusion-exclusion: 3 - |AB| - |AC| - |BC| + |ABC| = 3 - 0.5 - 0.5 - 0.25 + 0.25 = 2
        self.assertAlmostEqual(volume(evaluate(self.groups["zz_union3"], unit_cube())), 2.0, places=4)

    def test_intersecting_edges(self):
        r = evaluate(self.groups["zz_edges"], unit_cube(), attrs=("isect",))
        marked = sum(bool(x) for x in r["attrs"]["isect"])
        self.assertGreater(marked, 0)
        self.assertLess(marked, r["edges"])
        self.assertAlmostEqual(volume(r), 2 - 0.125, places=4)

    def test_errors(self):
        head = "def zz(a: gn.tGeometry) -> gn.tGeometry:\n"
        for body, fragment in (
            (
                "    return gn.MeshBoolean(a, a, self_intersection=True)\n",
                "only applies to solver='EXACT'",
            ),
            (
                "    m, e = gn.MeshBoolean(a, a, solver='MANIFOLD', hole_tolerant=True)\n    return m\n",
                "only applies to solver='EXACT'",
            ),
            (
                "    return gn.MeshBoolean(a, a, operation='XOR')\n",
                "INTERSECT, UNION, DIFFERENCE",
            ),
            (
                "    return gn.MeshBoolean(a, a, solver='FAST')\n",
                "EXACT, FLOAT, MANIFOLD",
            ),
            ("    return gn.MeshBoolean(a, 1.0)\n", "meshes must be geometry"),
            ("    return gn.MeshBoolean()\n", "usage: mesh = gn.MeshBoolean"),
            (
                "    return gn.MeshBoolean(a, a, mode='UNION')\n",
                "unknown argument: mode",
            ),
            (
                "    m, e = gn.MeshBoolean(a, a)\n    return m\n",
                "tuple unpacking size mismatch",
            ),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))


BEVEL_SRC = """
def zz_bevel_edges(a: gn.tGeometry) -> gn.tGeometry:
    m, vf, ef, _o, _mid = gn.MeshBevel(a, 0.1)
    m = gn.StoreNamedAttribute(m, "vf", vf, domain="FACE")
    return gn.StoreNamedAttribute(m, "ef", ef, domain="FACE")

def zz_bevel_side(a: gn.tGeometry) -> gn.tGeometry:
    return gn.MeshBevel(a, 0.1, start_left_offset=0.3).Mesh

def zz_bevel_vertices(a: gn.tGeometry) -> gn.tGeometry:
    return gn.MeshBevel(a, 0.25, affect="VERTICES").Mesh

def zz_bevel_segments(a: gn.tGeometry) -> gn.tGeometry:
    return gn.MeshBevel(a, 0.1, segments=3).Mesh

def zz_bevel_profile(a: gn.tGeometry, use_profile: bool = False) -> gn.tGeometry:
    plain = gn.MeshBevel(a, 0.2, segments=3).Mesh
    shaped = gn.MeshBevel(a, 0.2, segments=3, profile=gn.QuadraticBezier(resolution=4)).Mesh
    return shaped if use_profile else plain

def zz_bevel_top(a: gn.tGeometry) -> gn.tGeometry:
    r = gn.MeshBevel(a, 0.1, selection=gn.Position.z > 0.9)  # edge midpoints on the top face
    return gn.StoreNamedAttribute(r.Mesh, "ef", r.EdgeFace, domain="FACE")
"""


def coords(r, axis):
    return sorted({round(v[axis], 4) for v in r["verts"]})


class TestMeshBevel(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(BEVEL_SRC)

    def test_edges(self):
        r = evaluate(self.groups["zz_bevel_edges"], unit_cube(), attrs=("vf", "ef"))
        self.assertEqual((len(r["verts"]), r["edges"], r["faces"]), (24, 48, 26))
        for axis in range(3):
            self.assertEqual(coords(r, axis), [0.0, 0.1, 0.9, 1.0])
        self.assertEqual(sum(r["attrs"]["ef"]), 12)  # one new face per edge
        self.assertEqual(sum(r["attrs"]["vf"]), 8)  # one per corner

    def test_offset_sets_all_sides_and_sides_override(self):
        plain = evaluate(self.groups["zz_bevel_edges"], unit_cube())
        side = evaluate(self.groups["zz_bevel_side"], unit_cube())
        self.assertNotEqual(sorted(tuple(v) for v in plain["verts"]), sorted(tuple(v) for v in side["verts"]))
        self.assertTrue(any(abs(c - 0.3) < 1e-4 or abs(c - 0.7) < 1e-4 for v in side["verts"] for c in v))

    def test_vertices(self):
        r = evaluate(self.groups["zz_bevel_vertices"], unit_cube())
        self.assertEqual((len(r["verts"]), r["edges"], r["faces"]), (24, 36, 14))
        self.assertEqual(coords(r, 0), [0.0, 0.25, 0.75, 1.0])

    def test_segments_and_profile(self):
        r = evaluate(self.groups["zz_bevel_segments"], unit_cube())
        self.assertEqual((len(r["verts"]), r["edges"], r["faces"]), (96, 192, 98))
        plain = evaluate(self.groups["zz_bevel_profile"], unit_cube())["verts"]
        shaped = evaluate(self.groups["zz_bevel_profile"], unit_cube(), {"use_profile": True})["verts"]
        self.assertNotEqual(sorted(tuple(v) for v in plain), sorted(tuple(v) for v in shaped))

    def test_selection(self):
        r = evaluate(self.groups["zz_bevel_top"], unit_cube(), attrs=("ef",))
        self.assertEqual(sum(r["attrs"]["ef"]), 4)  # only the 4 top edges
        self.assertEqual(r["faces"], 6 + 4)

    def test_errors(self):
        head = "def zz(a: gn.tGeometry) -> gn.tGeometry:\n"
        for body, fragment in (
            (
                "    return gn.MeshBevel(a, 0.1, affect='VERTICES', miter=True).Mesh\n",
                "'miter' only applies to affect='EDGES'",
            ),
            (
                "    return gn.MeshBevel(a, 0.1, affect='VERTICES', end_left_offset=0.2).Mesh\n",
                "'end_left_offset' only applies to affect='EDGES'",
            ),
            (
                "    return gn.MeshBevel(a, 0.1, spread=0.3).Mesh\n",
                "'spread' only has an effect with miter=True",
            ),
            ("    return gn.MeshBevel(a, 0.1, affect='FACES').Mesh\n", "VERTICES, EDGES"),
            ("    return gn.MeshBevel(a, 0.1, profile=0.5).Mesh\n", "'profile' must be geometry"),
            ("    return gn.MeshBevel(a, 0.1)\n", "returns several outputs (Mesh, VertexFace"),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))
