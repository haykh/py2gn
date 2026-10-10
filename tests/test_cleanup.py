"""Delete / Separate Geometry, Split Edges, Merge by Distance, Remove Named Attribute."""

import bpy

from py2gn.compiler import GNCompileError, gn_compile

from .common import CompilerTestCase, evaluate, grid

SRC = """
def zz_merge(mesh: gn.tGeometry, d: float = 0.001, connected: bool = False) -> gn.tGeometry:
    if connected:
        mesh = gn.MergeByDistance(mesh, d, mode="CONNECTED")
    else:
        mesh = gn.MergeByDistance(mesh, distance=d)
    return mesh

def zz_merge_sel(mesh: gn.tGeometry) -> gn.tGeometry:
    return gn.MergeByDistance(mesh, 0.01, selection=gn.Position.y < 0.5)

def zz_del_points(mesh: gn.tGeometry) -> gn.tGeometry:
    return gn.DeleteGeometry(mesh, gn.Index < 4)                       # bottom row of vertices

def zz_del_face(mesh: gn.tGeometry, mode_ef: bool = False, mode_of: bool = False) -> gn.tGeometry:
    if mode_ef:
        mesh = gn.DeleteGeometry(mesh, gn.Index == 0, domain="FACE", mode="EDGE_FACE")
    elif mode_of:
        mesh = gn.DeleteGeometry(mesh, gn.Index == 0, domain="FACE", mode="ONLY_FACE")
    else:
        mesh = gn.DeleteGeometry(mesh, selection=gn.Index == 0, domain="FACE")
    return mesh

def zz_del_by_centre(mesh: gn.tGeometry) -> gn.tGeometry:
    # selection is evaluated on the FACE domain: position = face centre
    return gn.DeleteGeometry(mesh, gn.Position.x < 1, domain="FACE")

def zz_del_points_cloud(mesh: gn.tGeometry) -> gn.tGeometry:
    pts = gn.MeshToPoints(mesh)
    return gn.DeleteGeometry(pts, gn.Position.x > 1.5)

def zz_split_all(mesh: gn.tGeometry) -> gn.tGeometry:
    return gn.SplitEdges(mesh)

def zz_split_line(mesh: gn.tGeometry) -> gn.tGeometry:
    # edge domain: Position is the edge midpoint -> the three vertical edges on x = 1
    return gn.SplitEdges(mesh, selection=gn.Abs(gn.Position.x - 1) < 0.01)

def zz_split_roundtrip(mesh: gn.tGeometry) -> gn.tGeometry:
    return gn.MergeByDistance(gn.SplitEdges(mesh))

def zz_remove(mesh: gn.tGeometry, wildcard: bool = False) -> gn.tGeometry:
    mesh = gn.StoreNamedAttribute(mesh, "bt_a", 1.0)
    mesh = gn.StoreNamedAttribute(mesh, "bt_b", 2.0)
    mesh = gn.StoreNamedAttribute(mesh, "keep", 3.0)
    if wildcard:
        mesh = gn.RemoveNamedAttribute(mesh, "bt_*", mode="WILDCARD")
    else:
        mesh = gn.RemoveNamedAttribute(mesh, "bt_a")
    return mesh
"""


def two_quads(gap: float = 0.0):
    """Two quads touching along x=1 (the right one shifted by ``gap``); 8 separate vertices."""
    verts = [
        (0, 0, 0),
        (1, 0, 0),
        (1, 1, 0),
        (0, 1, 0),
        (1 + gap, 0, 0),
        (2, 0, 0),
        (2, 1, 0),
        (1 + gap, 1, 0),
    ]
    mesh = bpy.data.meshes.new("__test_quads")
    mesh.from_pydata(verts, [], [(0, 1, 2, 3), (4, 5, 6, 7)])
    mesh.update()
    return mesh


class TestCleanup(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SRC)

    def test_delete_points(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_del_points"], mesh)
        self.assertEqual((len(r["verts"]), r["faces"]), (12, 6))  # faces touching the row go too
        self.assertTrue(all(v.y > 0.5 for v in r["verts"]))

    def test_delete_face_modes(self):
        # face 0 is the corner face: vertex 0 and two edges are used by it alone
        for inputs, expect in (
            ({}, (15, 22, 8)),  # ALL: face + its now-unused edges and vertex
            ({"mode_ef": True}, (16, 22, 8)),  # EDGE_FACE: keeps the vertex (now loose)
            ({"mode_of": True}, (16, 24, 8)),  # ONLY_FACE: just the face
        ):
            with self.subTest(**inputs):
                mesh, _, _ = grid(4)
                r = evaluate(self.groups["zz_del_face"], mesh, inputs)
                self.assertEqual((len(r["verts"]), r["edges"], r["faces"]), expect)

    def test_delete_selection_on_domain(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_del_by_centre"], mesh)
        self.assertEqual(r["faces"], 6)  # the left column of faces (centres at x = 0.5)
        self.assertEqual(min(v.x for v in r["verts"]), 1.0)

    def test_delete_point_cloud(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_del_points_cloud"], mesh)
        self.assertEqual(len(r["points"]), 8)
        self.assertTrue(all(p.x < 1.5 for p in r["points"]))

    def test_split_all_edges(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_split_all"], mesh)
        self.assertEqual((len(r["verts"]), r["edges"], r["faces"]), (36, 36, 9))  # every face on its own

    def test_split_selected_edges(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_split_line"], mesh)
        # the 4 vertices and 3 edges on x = 1 are duplicated: the grid falls apart into two pieces
        self.assertEqual((len(r["verts"]), r["edges"], r["faces"]), (20, 27, 9))
        self.assertEqual(sum(abs(v.x - 1) < 1e-6 for v in r["verts"]), 8)

    def test_split_then_merge_restores(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_split_roundtrip"], mesh)
        self.assertEqual((len(r["verts"]), r["edges"], r["faces"]), (16, 24, 9))

    def test_merge_all_vs_connected(self):
        r = evaluate(self.groups["zz_merge"], two_quads())
        self.assertEqual((len(r["verts"]), r["faces"]), (6, 2))
        # the coincident vertices belong to different islands: CONNECTED leaves them alone
        r = evaluate(self.groups["zz_merge"], two_quads(), {"connected": True})
        self.assertEqual(len(r["verts"]), 8)

    def test_merge_distance(self):
        self.assertEqual(
            len(evaluate(self.groups["zz_merge"], two_quads(0.01), {"d": 0.001})["verts"]),
            8,
        )
        self.assertEqual(
            len(evaluate(self.groups["zz_merge"], two_quads(0.01), {"d": 0.02})["verts"]),
            6,
        )

    def test_merge_selection(self):
        # only the bottom pair (y = 0) is selected
        self.assertEqual(len(evaluate(self.groups["zz_merge_sel"], two_quads())["verts"]), 7)

    def test_merge_distance_must_be_single_value(self):
        from py2gn.compiler import GNCompileError, gn_compile

        with self.assertRaises(GNCompileError) as cm:
            gn_compile(
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.MergeByDistance(m, distance=0.001 * (gn.Index + 1))\n"
            )
        self.assertIn("'Distance' needs a single value", str(cm.exception))
        self.assertEqual(cm.exception.lineno, 2)

    def test_remove_named_attribute(self):
        mesh = bpy.data.meshes.new("__test_one")
        mesh.from_pydata([(0, 0, 0)], [], [])
        names = ("bt_a", "bt_b", "keep")
        self.assertEqual(
            sorted(evaluate(self.groups["zz_remove"], mesh, attrs=names)["attrs"]),
            ["bt_b", "keep"],
        )
        mesh = bpy.data.meshes.new("__test_one")
        mesh.from_pydata([(0, 0, 0)], [], [])
        self.assertEqual(
            sorted(evaluate(self.groups["zz_remove"], mesh, {"wildcard": True}, attrs=names)["attrs"]),
            ["keep"],
        )

    def test_menu_values_are_checked(self):
        from py2gn.compiler import GNCompileError, gn_compile

        for src, fragment in (
            (
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.MergeByDistance(m, mode='SOMETIMES')\n",
                "ALL, CONNECTED",
            ),
            (
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.RemoveNamedAttribute(m, 'a', mode='REGEX')\n",
                "EXACT, WILDCARD",
            ),
            (
                "def zz(m: gn.tGeometry, n: float) -> gn.tGeometry:\n    return gn.RemoveNamedAttribute(m, n)\n",
                "string literal",
            ),
            (
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.RemoveNamedAttribute(m)\n",
                "missing required argument(s): name",
            ),
            (
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.DeleteGeometry(m)\n",
                "missing required argument(s): selection",
            ),
            (
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.DeleteGeometry(m, gn.Index > 2, domain='SPLINE')\n",
                "POINT, EDGE, FACE, CURVE",
            ),
            (
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.DeleteGeometry(m, gn.Index > 2, mode='FACES')\n",
                "ALL, EDGE_FACE, ONLY_FACE",
            ),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(src)
                self.assertIn(fragment, str(cm.exception))


SEPARATE_SRC = """
def zz_sep_faces(m: gn.tGeometry, inverted: bool = False) -> gn.tGeometry:
    picked, rest = gn.SeparateGeometry(m, gn.Position.x < 1, domain="FACE")  # face centres
    return rest if inverted else picked

def zz_sep_points(m: gn.tGeometry) -> gn.tGeometry:
    return gn.SeparateGeometry(m, gn.Index < 4).Selection  # the bottom row of vertices

def zz_sep_rejoin(m: gn.tGeometry) -> gn.tGeometry:
    s = gn.SeparateGeometry(m, gn.Index % 2 == 0, domain="FACE")
    return gn.JoinGeometry(s.Selection, s.Inverted)
"""


class TestSeparate(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SEPARATE_SRC)

    def test_faces(self):
        for inverted, expect in ((False, (8, 3)), (True, (12, 6))):
            with self.subTest(inverted=inverted):
                mesh, _, _ = grid(4)
                r = evaluate(self.groups["zz_sep_faces"], mesh, {"inverted": inverted})
                self.assertEqual((len(r["verts"]), r["faces"]), expect)
                xs = [v.x for v in r["verts"]]
                self.assertTrue(max(xs) <= 1.0 + 1e-6 if not inverted else min(xs) >= 1.0 - 1e-6)

    def test_points(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_sep_points"], mesh)
        self.assertEqual((len(r["verts"]), r["edges"], r["faces"]), (4, 3, 0))
        self.assertTrue(all(abs(v.y) < 1e-6 for v in r["verts"]))

    def test_parts_add_up(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_sep_rejoin"], mesh)
        self.assertEqual(r["faces"], 9)

    def test_errors(self):
        head = "def zz(m: gn.tGeometry) -> gn.tGeometry:\n"
        for body, fragment in (
            ("    return gn.SeparateGeometry(m).Selection\n", "missing required argument(s): selection"),
            (
                "    return gn.SeparateGeometry(m, gn.Index > 1, domain='CORNER').Selection\n",
                "POINT, EDGE, FACE",
            ),
            (
                "    return gn.SeparateGeometry(m, gn.Index > 1)\n",
                "returns several outputs (Selection, Inverted)",
            ),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))
