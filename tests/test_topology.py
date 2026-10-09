"""Mesh topology nodes, instancing, Index Switch, and named multi-output results."""

import math

from mathutils import Vector

from py2gn.compiler import GNCompileError, gn_compile

from .common import CompilerTestCase, evaluate, grid, iface

SRC = """
def zz_vertex(m: gn.tGeometry) -> gn.tGeometry:
    _c, total = gn.CornersOfVertex(gn.Index)
    m = gn.StoreNamedAttribute(m, "valence", total)
    # weights are evaluated per corner: the lowest face index around the vertex comes first
    first = gn.CornersOfVertex(weights=gn.FaceOfCorner().FaceIndex, sort_index=0).CornerIndex
    return gn.StoreNamedAttribute(m, "minface", gn.FaceOfCorner(first).FaceIndex)

def zz_corner(m: gn.tGeometry) -> gn.tGeometry:
    f = gn.FaceOfCorner()
    m = gn.StoreNamedAttribute(m, "face", f.FaceIndex, domain="CORNER")
    m = gn.StoreNamedAttribute(m, "inface", f.IndexInFace, domain="CORNER")
    m = gn.StoreNamedAttribute(m, "vert", gn.VertexOfCorner(), domain="CORNER")
    nxt = gn.VertexOfCorner(gn.OffsetCornerInFace(gn.Index, 1))
    m = gn.StoreNamedAttribute(m, "nextvert", nxt, domain="CORNER")
    return gn.StoreNamedAttribute(m, "nextedge", gn.EdgesOfCorner().NextEdgeIndex, domain="CORNER")

def zz_edge_face(m: gn.tGeometry) -> gn.tGeometry:
    m = gn.StoreNamedAttribute(m, "efaces", gn.CornersOfEdge().Total, domain="EDGE")
    return gn.StoreNamedAttribute(m, "fcorners", gn.CornersOfFace().Total, domain="FACE")

def zz_circle(m: gn.tGeometry, k: int = 6) -> gn.tGeometry:
    return gn.MeshCircle(k, radius=2.0, fill="NGON")

def zz_inst(m: gn.tGeometry) -> gn.tGeometry:
    return gn.RealizeInstances(gn.InstanceOnPoints(m, gn.MeshCircle(4, radius=0.5, fill="NGON")))

def zz_inst_rot(m: gn.tGeometry) -> gn.tGeometry:
    c = gn.MeshCircle(8, radius=0.5)
    return gn.RealizeInstances(gn.InstanceOnPoints(m, c, rotation=gn.tVec(gn.Pi / 2, 0, 0)))

def zz_inst_sel(m: gn.tGeometry) -> gn.tGeometry:
    c = gn.MeshCircle(4, radius=0.5)
    return gn.RealizeInstances(gn.InstanceOnPoints(m, c, selection=gn.Index < 2, scale=2.0))

def zz_switch(m: gn.tGeometry) -> gn.tGeometry:
    m = gn.StoreNamedAttribute(m, "s", gn.IndexSwitch(gn.Index % 3, 10.0, 20.0, 30.0))
    return gn.StoreNamedAttribute(m, "v", gn.IndexSwitch(gn.Index % 2, gn.tVec(1, 0, 0), gn.tVec(0, 1, 0)))

def zz_switch_geo(m: gn.tGeometry, which: int = 0) -> gn.tGeometry:
    return gn.IndexSwitch(which, m, gn.MeshCircle(5, fill="NGON"), gn.FlipFaces(m))

def zz_switch_const(x: float, y: float):
    return gn.IndexSwitch(1, x, y)

def zz_return_named(m: gn.tGeometry):
    return gn.FaceOfCorner(3)

def zz_extrude_named(m: gn.tGeometry) -> gn.tGeometry:
    e = gn.ExtrudeMesh(m, scale=0.5)
    return gn.StoreNamedAttribute(e.Mesh, "top", e.Top, domain="FACE")
"""


class TestTopology(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SRC)

    def test_corners_of_vertex(self):
        mesh, verts, faces = grid(4)
        a = evaluate(self.groups["zz_vertex"], mesh, attrs=("valence", "minface"))["attrs"]
        for v in range(len(verts)):
            around = [f for f, poly in enumerate(faces) if v in poly]
            self.assertEqual(a["valence"][v], len(around))
            self.assertEqual(a["minface"][v], min(around))

    def test_corner_queries(self):
        mesh, _, _ = grid(4)
        r = evaluate(
            self.groups["zz_corner"],
            mesh,
            attrs=("face", "inface", "vert", "nextvert", "nextedge"),
        )
        a, polys, edges = r["attrs"], r["polys"], r["edge_verts"]
        c = 0
        for f, poly in enumerate(polys):
            for i, vert in enumerate(poly):
                nxt = poly[(i + 1) % len(poly)]
                self.assertEqual((a["face"][c], a["inface"][c], a["vert"][c]), (f, i, vert))
                self.assertEqual(a["nextvert"][c], nxt)
                self.assertEqual(set(edges[a["nextedge"][c]]), {vert, nxt})
                c += 1

    def test_edge_and_face_totals(self):
        mesh, _, _ = grid(4)
        r = evaluate(self.groups["zz_edge_face"], mesh, attrs=("efaces", "fcorners"))
        polys = r["polys"]
        for e, (u, w) in enumerate(r["edge_verts"]):
            shared = sum(
                1 for p in polys if u in p and w in p and abs(p.index(u) - p.index(w)) in (1, len(p) - 1)
            )
            self.assertEqual(r["attrs"]["efaces"][e], shared)
        self.assertEqual(set(r["attrs"]["fcorners"]), {4})

    def test_mesh_circle(self):
        mesh, _, _ = grid(2)
        r = evaluate(self.groups["zz_circle"], mesh)
        self.assertEqual((len(r["verts"]), r["faces"]), (6, 1))
        for v in r["verts"]:
            self.assertAlmostEqual(v.length, 2.0, places=5)

    def test_instance_on_points_and_realize(self):
        mesh, verts, _ = grid(2)
        r = evaluate(self.groups["zz_inst"], mesh)
        self.assertEqual((len(r["verts"]), r["faces"]), (16, 4))
        for v in r["verts"]:
            self.assertAlmostEqual(min((v - Vector(p)).length for p in verts), 0.5, places=5)

    def test_rotation_constant(self):
        mesh, verts, _ = grid(2)
        r = evaluate(self.groups["zz_inst_rot"], mesh)
        self.assertEqual(len(r["verts"]), 32)
        # rotated 90 degrees about x: every circle lies in an xz plane through its point
        self.assertTrue(all(min(abs(v.y - p[1]) for p in verts) < 1e-5 for v in r["verts"]))
        self.assertAlmostEqual(max(abs(v.z) for v in r["verts"]), 0.5, places=5)

    def test_selection_and_scale(self):
        mesh, verts, _ = grid(2)
        r = evaluate(self.groups["zz_inst_sel"], mesh)
        self.assertEqual(len(r["verts"]), 8)  # only points 0 and 1 are selected
        # scale 2 doubles the 0.5 radius: every vertex is at distance 1 from one of the selected points
        # (not "nearest": the points are 1 apart, so each circle passes through the other point)
        for v in r["verts"]:
            self.assertTrue(any(abs((v - Vector(p)).length - 1.0) < 1e-5 for p in verts[:2]))

    def test_index_switch(self):
        mesh, _, _ = grid(3)
        a = evaluate(self.groups["zz_switch"], mesh, attrs=("s", "v"))["attrs"]
        for i, s in enumerate(a["s"]):
            self.assertAlmostEqual(s, (10.0, 20.0, 30.0)[i % 3])
            self.assertEqual(a["v"][i], ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))[i % 2])

    def test_index_switch_geometry(self):
        for which, nverts in ((0, 4), (1, 5), (2, 4)):
            with self.subTest(which=which):
                mesh, _, _ = grid(2)
                r = evaluate(self.groups["zz_switch_geo"], mesh, {"which": which})
                self.assertEqual(len(r["verts"]), nverts)

    def test_index_switch_constant_folds(self):
        nodes = self.groups["zz_switch_const"].nodes
        self.assertFalse(any(n.bl_idname == "GeometryNodeIndexSwitch" for n in nodes))

    def test_named_results(self):
        g = self.groups["zz_return_named"]
        self.assertEqual([i.name for i in iface(g, "OUTPUT")], ["FaceIndex", "IndexInFace"])
        mesh, _, _ = grid(2)
        r = evaluate(self.groups["zz_extrude_named"], mesh, attrs=("top",))
        self.assertEqual(sum(bool(x) for x in r["attrs"]["top"]), 1)

    def test_errors(self):
        head = "def zz(m: gn.tGeometry) -> gn.tGeometry:\n"
        for body, fragment in (
            (
                "    return gn.StoreNamedAttribute(m, 'a', gn.FaceOfCorner() + 1)\n",
                "gn.FaceOfCorner() returns several outputs (FaceIndex, IndexInFace)",
            ),
            (
                "    return gn.StoreNamedAttribute(m, 'a', gn.FaceOfCorner().Face)\n",
                "gn.FaceOfCorner() has no output 'Face'",
            ),
            (
                "    return gn.IndexSwitch(gn.Index % 2, m, m)\n",
                "needs a single-value index",
            ),
            (
                "    return gn.IndexSwitch(0, m, 1.0)\n",
                "all geometry or all non-geometry",
            ),
            ("    return gn.IndexSwitch(m)\n", "usage: gn.IndexSwitch(index, value0"),
            ("    return gn.MeshCircle(6, fill='QUADS')\n", "NONE, NGON, TRIANGLE_FAN"),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))
        self.assertTrue(math.isfinite(0.0))


SAMPLE_SRC = """
def zz_edges_of_vertex(m: gn.tGeometry) -> gn.tGeometry:
    first, total = gn.EdgesOfVertex(weights=gn.Index, sort_index=0)  # weights are evaluated per edge
    m = gn.StoreNamedAttribute(m, "deg", total)
    return gn.StoreNamedAttribute(m, "e0", first)

def zz_sample_lift(m: gn.tGeometry) -> gn.tGeometry:
    other = gn.SetPosition(m, offset=gn.tVec(0, 0, 5))
    return gn.StoreNamedAttribute(m, "lifted", gn.SampleIndex(other, gn.Position, gn.Index))

def zz_sample_mirror(m: gn.tGeometry) -> gn.tGeometry:
    n = gn.DomainSize(m)
    return gn.StoreNamedAttribute(m, "mirror", gn.SampleIndex(m, gn.Index, n - 1 - gn.Index))

def zz_clamp(m: gn.tGeometry) -> gn.tGeometry:
    m = gn.StoreNamedAttribute(m, "c", gn.SampleIndex(m, gn.Position.x, gn.Index + 100, clamp=True))
    return gn.StoreNamedAttribute(m, "nc", gn.SampleIndex(m, gn.Position.x + 7, gn.Index + 100))

def zz_face_sample(m: gn.tGeometry) -> gn.tGeometry:
    return gn.StoreNamedAttribute(m, "f0", gn.SampleIndex(m, gn.Position, 0, domain="FACE"))

def zz_bool_sample(m: gn.tGeometry) -> gn.tGeometry:
    return gn.StoreNamedAttribute(m, "b", gn.SampleIndex(m, gn.Index % 2 == 0, gn.Index + 1))

def zz_nearest(m: gn.tGeometry) -> gn.tGeometry:
    target = gn.SetPosition(m, offset=gn.tVec(0.1, 0.1, 0))
    idx = gn.SampleNearest(target, gn.Position)
    m = gn.StoreNamedAttribute(m, "near", idx)
    return gn.StoreNamedAttribute(m, "nearpos", gn.SampleIndex(target, gn.Position, idx))

def zz_nearest_face(m: gn.tGeometry) -> gn.tGeometry:
    return gn.StoreNamedAttribute(m, "nf", gn.SampleNearest(m, gn.tVec(2.4, 0.5, 0), domain="FACE"))
"""


class TestSampling(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SAMPLE_SRC)

    def test_edges_of_vertex(self):
        mesh, verts, _ = grid(4)
        r = evaluate(self.groups["zz_edges_of_vertex"], mesh, attrs=("deg", "e0"))
        for v in range(len(verts)):
            at = [i for i, (a, b) in enumerate(r["edge_verts"]) if v in (a, b)]
            self.assertEqual(r["attrs"]["deg"][v], len(at))
            self.assertEqual(r["attrs"]["e0"][v], min(at))

    def test_sample_other_geometry(self):
        mesh, verts, _ = grid(3)
        a = evaluate(self.groups["zz_sample_lift"], mesh, attrs=("lifted",))["attrs"]
        for i, p in enumerate(verts):
            self.assertLess((Vector(a["lifted"][i]) - Vector(p) - Vector((0, 0, 5))).length, 1e-6)

    def test_sample_int_and_bool(self):
        mesh, verts, _ = grid(3)
        n = len(verts)
        a = evaluate(self.groups["zz_sample_mirror"], mesh, attrs=("mirror",))["attrs"]
        self.assertEqual(list(a["mirror"]), [n - 1 - i for i in range(n)])
        mesh, _, _ = grid(3)
        a = evaluate(self.groups["zz_bool_sample"], mesh, attrs=("b",))["attrs"]
        self.assertEqual(list(a["b"]), [(i + 1) % 2 == 0 and i + 1 < n for i in range(n)])

    def test_clamp(self):
        mesh, verts, _ = grid(3)
        a = evaluate(self.groups["zz_clamp"], mesh, attrs=("c", "nc"))["attrs"]
        self.assertTrue(all(abs(x - verts[-1][0]) < 1e-6 for x in a["c"]))  # clamped to the last point
        self.assertTrue(all(abs(x) < 1e-6 for x in a["nc"]))  # out of range: zero

    def test_sample_face_domain(self):
        mesh, _, _ = grid(3)
        a = evaluate(self.groups["zz_face_sample"], mesh, attrs=("f0",))["attrs"]
        self.assertTrue(all((Vector(v) - Vector((0.5, 0.5, 0))).length < 1e-6 for v in a["f0"]))

    def test_sample_nearest(self):
        mesh, verts, _ = grid(4)
        a = evaluate(self.groups["zz_nearest"], mesh, attrs=("near", "nearpos"))["attrs"]
        self.assertEqual(list(a["near"]), list(range(len(verts))))
        for i, p in enumerate(verts):
            self.assertLess((Vector(a["nearpos"][i]) - Vector(p) - Vector((0.1, 0.1, 0))).length, 1e-6)
        mesh, _, _ = grid(4)
        a = evaluate(self.groups["zz_nearest_face"], mesh, attrs=("nf",))["attrs"]
        self.assertEqual(set(a["nf"]), {2})  # (2.4, 0.5) lies in face x=2, y=0

    def test_sampling_errors(self):
        head = "def zz(m: gn.tGeometry) -> gn.tGeometry:\n"
        for body, fragment in (
            (
                "    return gn.StoreNamedAttribute(m, 'a', gn.SampleIndex(m, gn.Position))\n",
                "missing required argument(s): index",
            ),
            (
                "    return gn.StoreNamedAttribute(m, 'a', gn.SampleIndex(m, m, 0))\n",
                "must be a value, not geometry",
            ),
            (
                "    return gn.StoreNamedAttribute(m, 'a', gn.SampleIndex(m, 1.0, 0, clamp=gn.Index > 0))\n",
                "'clamp' option must be known at compile time",
            ),
            (
                "    return gn.StoreNamedAttribute(m, 'a', gn.SampleNearest(m, domain='CURVE'))\n",
                "POINT, EDGE, FACE, CORNER",
            ),
            ("    return gn.FlipFaces(m) if gn.SampleNearest(m) > 0 else m\n", "single-value condition"),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))
