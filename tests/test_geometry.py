"""Geometry operations: values threaded through code, switches, capture, ordering."""

import math

import bpy
from mathutils import Vector

from .common import EXAMPLES, CompilerTestCase, evaluate, grid

SRC = """
def zz_stack(mesh: gn.tGeometry, count: int = 3, spacing: float = 1.0) -> gn.tGeometry:
    copies, k = gn.DuplicateElements(mesh, count, domain="FACE")
    copies = gn.SetPosition(copies, offset=gn.tVec(0, 0, (k + 1) * spacing))
    return gn.JoinGeometry(mesh, copies)

def zz_store(mesh: gn.tGeometry) -> gn.tGeometry:
    return gn.StoreNamedAttribute(mesh, "h", gn.Position.x * 2 + gn.Index)

def zz_capture(mesh: gn.tGeometry) -> gn.tGeometry:
    mesh, p0 = gn.CaptureAttribute(mesh, gn.Position)
    mesh = gn.SetPosition(mesh, offset=gn.tVec(0, 0, 1))
    mesh = gn.StoreNamedAttribute(mesh, "p0", p0)
    return gn.StoreNamedAttribute(mesh, "plive", gn.Position)

def zz_geo_if(mesh: gn.tGeometry, flip: bool = False) -> gn.tGeometry:
    if flip:
        mesh = gn.FlipFaces(mesh)
    return mesh

def zz_ring(points: gn.tGeometry, closed: bool = True) -> gn.tGeometry:
    c = gn.PointsToCurves(points)
    c = gn.SetSplineCyclic(c, closed)
    return gn.CurveToMesh(c)

def zz_points(mesh: gn.tGeometry, mode_faces: bool = False) -> gn.tGeometry:
    pts = gn.MeshToPoints(mesh, mode="FACES") if mode_faces else gn.MeshToPoints(mesh)
    return pts

def zz_points_args(mesh: gn.tGeometry, r: float = 0.25) -> gn.tGeometry:
    # fields are evaluated on the chosen domain: face index and face-centre height
    pts = gn.MeshToPoints(mesh, selection=gn.Index % 2 == 0, position=gn.Position + gn.tVec(0, 0, 1), radius=r * (gn.Index + 1),
                         mode="FACES")
    return gn.StoreNamedAttribute(pts, "src", gn.Index)

def zz_points_modes(mesh: gn.tGeometry) -> gn.tGeometry:
    e = gn.MeshToPoints(mesh, mode="EDGES")
    c = gn.MeshToPoints(mesh, mode="CORNERS")
    m = gn.StoreNamedAttribute(mesh, "ne", gn.DomainSize(e, "POINT", component="POINTCLOUD"))
    return gn.StoreNamedAttribute(m, "nc", gn.DomainSize(c, "POINT", component="POINTCLOUD"))

def zz_joinorder(a: gn.tGeometry, dz: float = 5.0) -> gn.tGeometry:
    b = gn.SetPosition(a, offset=gn.tVec(0, 0, dz))
    return gn.JoinGeometry(b, a)
"""


HIDDEN_SRC = """
def zz_ext_const(m: gn.tGeometry) -> gn.tGeometry:
    out, top, side = gn.ExtrudeMesh(m, offset=gn.tVec(1, 0, 0), scale=2.0)
    return out

def zz_ext_local(m: gn.tGeometry) -> gn.tGeometry:
    up = gn.tVec(1, 0, 0)  # a local constant is still a constant
    out, top, side = gn.ExtrudeMesh(m, offset=up, scale=2.0)
    return out

def zz_setpos_const(m: gn.tGeometry) -> gn.tGeometry:
    return gn.SetPosition(m, position=gn.tVec(5, 5, 5))

def zz_points_const(m: gn.tGeometry) -> gn.tGeometry:
    return gn.MeshToPoints(m, position=gn.tVec(7, 0, 0))

def zz_stat_const(m: gn.tGeometry) -> gn.tGeometry:
    return gn.StoreNamedAttribute(m, "s", gn.AttributeStatistic(m, 2.0, "sum"))

def zz_select_const(m: gn.tGeometry, keep: bool = True) -> gn.tGeometry:
    m = gn.DeleteGeometry(m, False)        # constant selection False: delete nothing
    return gn.DeleteGeometry(m, not keep)  # parameter: delete everything when keep=False
"""


def unit_quad():
    mesh = bpy.data.meshes.new("__test_quad")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    return mesh


class TestHiddenDefaults(CompilerTestCase):
    """Constants fed to sockets without a value widget must be linked, not stored.

    Regression: Extrude Mesh > Offset, Set Position > Position and Mesh to Points > Position
    evaluate an implicit field when unlinked, so a stored constant was silently ignored.
    """

    def setUp(self):
        super().setUp()
        self.groups = self.compile(HIDDEN_SRC)

    def test_extrude_offset_constant(self):
        for name in ("zz_ext_const", "zz_ext_local"):
            with self.subTest(name=name):
                vs = evaluate(self.groups[name], unit_quad())["verts"]
                self.assertEqual(sorted({round(v.x, 4) for v in vs}), [0.0, 1.0, 2.0, 3.0])  # moved along +x
                self.assertTrue(all(abs(v.z) < 1e-6 for v in vs))  # not along the normal

    def test_set_position_constant(self):
        vs = evaluate(self.groups["zz_setpos_const"], unit_quad())["verts"]
        self.assertTrue(all((v - Vector((5, 5, 5))).length < 1e-6 for v in vs))

    def test_mesh_to_points_constant(self):
        ps = evaluate(self.groups["zz_points_const"], unit_quad())["points"]
        self.assertTrue(ps and all((p - Vector((7, 0, 0))).length < 1e-6 for p in ps))

    def test_attribute_statistic_constant(self):
        a = evaluate(self.groups["zz_stat_const"], unit_quad(), attrs=("s",))["attrs"]
        self.assertAlmostEqual(a["s"][0], 8.0)

    def test_constant_selection(self):
        self.assertEqual(len(evaluate(self.groups["zz_select_const"], unit_quad())["verts"]), 4)
        self.assertEqual(
            len(evaluate(self.groups["zz_select_const"], unit_quad(), {"keep": False}).get("verts", [])),
            0,
        )

    def test_constants_are_shared(self):
        g = self.compile(
            "def zz_share(m: gn.tGeometry) -> gn.tGeometry:\n"
            "    m = gn.SetPosition(m, position=gn.tVec(0, 0, 1))\n"
            "    return gn.MeshToPoints(m, position=gn.tVec(0, 0, 1))\n"
        )["zz_share"]
        self.assertEqual(sum(n.bl_idname == "ShaderNodeCombineXYZ" for n in g.nodes), 1)


class TestGeometry(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SRC)
        self.groups.update(self.compile(EXAMPLES.read_text(encoding="utf-8")))

    def test_modifier_flag(self):
        for name in ("zz_stack", "zz_ring", "solidify"):
            self.assertTrue(self.groups[name].is_modifier, name)
        self.assertFalse(self.groups["smoothstep"].is_modifier)

    def test_solidify(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["solidify"], mesh, {"thickness": 0.2})
        self.assertEqual((len(r["verts"]), r["faces"]), (44, 30))
        self.assertEqual(sorted({round(v.z, 4) for v in r["verts"]}), [0.0, 0.2])
        self.assertEqual(sum(z < -0.99 for z in r["face_normal_z"]), 9)
        self.assertEqual(sum(z > 0.99 for z in r["face_normal_z"]), 9)

    def test_duplicate_and_set_position(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_stack"], mesh)
        self.assertEqual(r["faces"], 36)
        self.assertEqual(sorted({round(v.z, 4) for v in r["verts"]}), [0.0, 1.0, 2.0, 3.0])

    def test_store_attr(self):
        mesh, verts, _ = grid(4)
        h = evaluate(self.groups["zz_store"], mesh, attrs=("h",))["attrs"]["h"]
        for i, v in enumerate(h):
            self.assertAlmostEqual(v, 2 * verts[i][0] + i, places=5)

    def test_capture_freezes_fields(self):
        mesh, verts, _ = grid(4)
        a = evaluate(self.groups["zz_capture"], mesh, attrs=("p0", "plive"))["attrs"]
        for i, v in enumerate(verts):
            self.assertLess((Vector(a["p0"][i]) - Vector(v)).length, 1e-6)
            self.assertLess((Vector(a["plive"][i]) - Vector(v) - Vector((0, 0, 1))).length, 1e-6)

    def test_geometry_switch(self):
        mesh, _, _ = grid(4)
        self.assertTrue(all(z > 0.99 for z in evaluate(self.groups["zz_geo_if"], mesh)["face_normal_z"]))
        mesh, _, _ = grid(4)
        flipped = evaluate(self.groups["zz_geo_if"], mesh, {"flip": True})["face_normal_z"]
        self.assertTrue(all(z < -0.99 for z in flipped))

    def test_join_order(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_joinorder"], mesh)
        self.assertAlmostEqual(r["verts"][0].z, 5.0)
        self.assertAlmostEqual(r["verts"][-1].z, 0.0)

    def test_mesh_to_points(self):
        mesh, verts, faces = grid(4, jitter=0.2, seed=2)
        r = evaluate(self.groups["zz_points"], mesh)
        self.assertEqual(r.get("verts", []), [])  # output is a point cloud; the mesh is gone
        self.assertEqual(len(r["points"]), len(verts))
        for p, v in zip(r["points"], verts):
            self.assertLess((p - Vector(v)).length, 1e-6)
        self.assertTrue(all(abs(x - 0.05) < 1e-6 for x in r["radii"]))  # node default radius

        mesh, verts, faces = grid(4, jitter=0.2, seed=2)
        r = evaluate(self.groups["zz_points"], mesh, {"mode_faces": True})
        centres = [sum((Vector(verts[i]) for i in f), Vector()) / 4 for f in faces]
        self.assertEqual(len(r["points"]), len(faces))
        for p, c in zip(r["points"], centres):
            self.assertLess((p - c).length, 1e-5)

    def test_mesh_to_points_arguments(self):
        mesh, verts, faces = grid(4, jitter=0.2, seed=2)
        r = evaluate(self.groups["zz_points_args"], mesh, {"r": 0.25}, attrs=("src",))
        kept = [i for i in range(len(faces)) if i % 2 == 0]
        self.assertEqual(len(r["points"]), len(kept))
        for p, rad, fi in zip(r["points"], r["radii"], kept):
            c = sum((Vector(verts[i]) for i in faces[fi]), Vector()) / 4 + Vector((0, 0, 1))
            self.assertLess((p - c).length, 1e-5)
            self.assertAlmostEqual(rad, 0.25 * (fi + 1), places=5)

    def test_mesh_to_points_modes(self):
        mesh, _, _ = grid(4)
        a = evaluate(self.groups["zz_points_modes"], mesh, attrs=("ne", "nc"))["attrs"]
        self.assertEqual((a["ne"][0], a["nc"][0]), (24, 36))

    def test_points_to_curve_to_mesh(self):
        for closed, edges in ((True, 8), (False, 7)):
            with self.subTest(closed=closed):
                pc = bpy.data.pointclouds.new("__test_pc")
                pc.resize(8)
                for i, d in enumerate(pc.attributes["position"].data):
                    d.vector = (
                        math.cos(i * math.tau / 8),
                        math.sin(i * math.tau / 8),
                        0,
                    )
                r = evaluate(self.groups["zz_ring"], pc, {"closed": closed})
                self.assertEqual((len(r["verts"]), r["edges"]), (8, edges))
