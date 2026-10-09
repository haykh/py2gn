"""Mesh Boolean: operations x solvers by volume, multiple operands, intersecting edges, errors."""

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
