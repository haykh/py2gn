"""Domain Size, Attribute Statistic, Mesh to Curve, Reverse Curve, Spline Parameter, Is Spline Cyclic."""

import itertools
import math
import statistics as st

import bpy
from mathutils import Vector

from py2gn.compiler import GNCompileError, gn_compile

from .common import CompilerTestCase, evaluate, grid

SRC = """
def zz_sizes(mesh: gn.tGeometry) -> gn.tGeometry:
    mesh = gn.StoreNamedAttribute(mesh, "sz", gn.tVec(gn.DomainSize(mesh), gn.DomainSize(mesh, "EDGE"), gn.DomainSize(mesh, "FACE")))
    return gn.StoreNamedAttribute(mesh, "sc", gn.DomainSize(mesh, "CORNER"))

def zz_stats(mesh: gn.tGeometry) -> gn.tGeometry:
    mean, med, tot, lo, hi, rng, sd, var = gn.AttributeStatistic(mesh, gn.Position.z)
    mesh = gn.StoreNamedAttribute(mesh, "s1", gn.tVec(mean, med, tot))
    mesh = gn.StoreNamedAttribute(mesh, "s2", gn.tVec(lo, hi, rng))
    mesh = gn.StoreNamedAttribute(mesh, "s3", gn.tVec(sd, var, gn.AttributeStatistic(mesh, gn.Position.z, "sum", selection=gn.Index < 5)))
    mesh = gn.StoreNamedAttribute(mesh, "s4", gn.tVec(gn.AttributeStatistic(mesh, gn.Position.z, "mean", domain="FACE"), 0, 0))
    return gn.StoreNamedAttribute(mesh, "vmean", gn.AttributeStatistic(mesh, gn.Position, "mean"))

def zz_curve(mesh: gn.tGeometry, rev: bool = False) -> gn.tGeometry:
    c = gn.MeshToCurve(mesh)
    c = gn.ReverseCurve(c, selection=rev)
    f, L, i = gn.SplineParameter()
    c = gn.StoreNamedAttribute(c, "par", gn.tVec(f, L, i))
    return gn.StoreNamedAttribute(c, "cyc", gn.IsSplineCyclic)

def zz_statif(m: gn.tGeometry) -> gn.tGeometry:
    return gn.FlipFaces(m) if gn.AttributeStatistic(m, gn.Position.z, "max") > 0 and gn.DomainSize(m, "FACE") > 3 else m
"""


class TestQueries(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(SRC)

    def test_domain_size(self):
        mesh, _, _ = grid(4)
        a = evaluate(self.groups["zz_sizes"], mesh, attrs=("sz", "sc"))["attrs"]
        self.assertEqual(a["sz"][0], (16.0, 24.0, 9.0))
        self.assertEqual(a["sc"][0], 36)

    def test_attribute_statistic(self):
        mesh, verts, faces = grid(4, jitter=0.1, seed=7)
        a = evaluate(self.groups["zz_stats"], mesh, attrs=("s1", "s2", "s3", "s4", "vmean"))["attrs"]
        z = [v[2] for v in verts]
        fz = [sum(verts[i][2] for i in f) / 4 for f in faces]
        got = [*a["s1"][0], *a["s2"][0], *a["s3"][0], a["s4"][0][0]]
        ref = [
            st.mean(z),
            st.median(z),
            sum(z),
            min(z),
            max(z),
            max(z) - min(z),
            st.pstdev(z),
            st.pvariance(z),
            sum(z[:5]),
            st.mean(fz),
        ]
        for g, r in zip(got, ref):
            self.assertAlmostEqual(g, r, places=5)
        vref = sum((Vector(v) for v in verts), Vector()) / len(verts)
        self.assertLess((Vector(a["vmean"][0]) - vref).length, 1e-6)

    def test_single_values_drive_geometry_switch(self):
        self.assertIn("zz_statif", self.groups)

    def test_curves(self):
        for closed in (True, False):
            for rev in (False, True):
                with self.subTest(closed=closed, rev=rev):
                    k = 8
                    pts = [(math.cos(i * math.tau / k), math.sin(i * math.tau / k), 0) for i in range(k)]
                    edges = [(i, (i + 1) % k) for i in range(k if closed else k - 1)]
                    m = bpy.data.meshes.new("__test_ring")
                    m.from_pydata(pts, edges, [])
                    r = evaluate(self.groups["zz_curve"], m, {"rev": rev}, attrs=("par", "cyc"))
                    self.assertEqual(r["curves"], 1)
                    self.assertEqual(set(r["curve_attrs"]["cyc"]), {closed})
                    P = r["curve_positions"]
                    seg = [(P[(i + 1) % k] - P[i]).length for i in range(k if closed else k - 1)]
                    total = sum(seg)
                    for i, (f, length, idx) in enumerate(r["curve_attrs"]["par"]):
                        cum = sum(seg[:i])
                        self.assertAlmostEqual(f, cum / total, places=5)
                        self.assertAlmostEqual(length, cum, places=5)
                        self.assertEqual(round(idx), i)
                    first = Vector(pts[-1] if rev else pts[0])
                    self.assertLess((P[0] - first).length, 1e-5)


RESAMPLE_SRC = """
def zz_resample(m: gn.tGeometry, n: int = 5) -> gn.tGeometry:
    return gn.ResampleCurve(gn.MeshToCurve(m), n)

def zz_resample_length(m: gn.tGeometry) -> gn.tGeometry:
    return gn.ResampleCurve(gn.MeshToCurve(m), length=0.25)

def zz_resample_evaluated(m: gn.tGeometry) -> gn.tGeometry:
    return gn.ResampleCurve(gn.MeshToCurve(m), mode="EVALUATED")
"""


def line_mesh(length: float = 1.0):
    me = bpy.data.meshes.new("__test_line")
    me.from_pydata([(0, 0, 0), (length, 0, 0)], [(0, 1)], [])
    return me


class TestResample(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(RESAMPLE_SRC)

    def test_count(self):
        for n in (2, 5, 9):
            with self.subTest(n=n):
                r = evaluate(self.groups["zz_resample"], line_mesh(), {"n": n})
                xs = [p.x for p in r["curve_positions"]]
                self.assertEqual(len(xs), n)
                for i, x in enumerate(xs):
                    self.assertAlmostEqual(x, i / (n - 1), places=5)

    def test_length(self):
        r = evaluate(self.groups["zz_resample_length"], line_mesh(), attrs=())
        self.assertEqual([round(p.x, 5) for p in r["curve_positions"]], [0.0, 0.25, 0.5, 0.75, 1.0])

    def test_evaluated(self):
        r = evaluate(self.groups["zz_resample_evaluated"], line_mesh())
        self.assertEqual(len(r["curve_positions"]), 2)  # a poly curve evaluates to its own points

    def test_mode_errors(self):
        head = "def zz(c: gn.tGeometry) -> gn.tGeometry:\n"
        for body, fragment in (
            ("    return gn.ResampleCurve(c, 8, length=0.1)\n", "either count= or length="),
            (
                "    return gn.ResampleCurve(c, length=0.1, mode='COUNT')\n",
                "'length' only applies in mode='LENGTH'",
            ),
            ("    return gn.ResampleCurve(c, 8, mode='EVALUATED')\n", "'count' only applies in mode='COUNT'"),
            ("    return gn.ResampleCurve(c, mode='SMOOTH')\n", "EVALUATED, COUNT, LENGTH"),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))


BEZIER_SRC = """
def zz_quadratic(m: gn.tGeometry) -> gn.tGeometry:
    return gn.QuadraticBezier(gn.tVec(0, 0, 0), gn.tVec(1, 2, 0), gn.tVec(2, 0, 1), resolution=4)

def zz_segment(m: gn.tGeometry) -> gn.tGeometry:
    c = gn.BezierSegment(gn.tVec(0, 0, 0), gn.tVec(0, 1, 0), gn.tVec(2, 1, 0), gn.tVec(2, 0, 0), resolution=4)
    return gn.ResampleCurve(c, mode="EVALUATED")

def zz_segment_offset(m: gn.tGeometry) -> gn.tGeometry:
    c = gn.BezierSegment(start=gn.tVec(0, 0, 0), end=gn.tVec(2, 0, 0), start_handle=gn.tVec(0, 1, 0),
                         end_handle=gn.tVec(0, 1, 0), resolution=4, mode="OFFSET")
    return gn.ResampleCurve(c, mode="EVALUATED")

def zz_segment_raw(m: gn.tGeometry) -> gn.tGeometry:
    return gn.BezierSegment(resolution=8)
"""


def bezier(points, t):
    """de Casteljau: works for any degree."""
    pts = [Vector(p) for p in points]
    while len(pts) > 1:
        pts = [a.lerp(b, t) for a, b in itertools.pairwise(pts)]
    return pts[0]


class TestBezier(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(BEZIER_SRC)

    def _check(self, name, control):
        mesh, _, _ = grid(2)
        pts = evaluate(self.groups[name], mesh)["curve_positions"]
        self.assertEqual(len(pts), 5)  # resolution 4 -> 5 evaluated points
        for i, p in enumerate(pts):
            self.assertLess((p - bezier(control, i / 4)).length, 1e-5, (name, i))

    def test_quadratic(self):
        self._check("zz_quadratic", [(0, 0, 0), (1, 2, 0), (2, 0, 1)])

    def test_segment_positions(self):
        self._check("zz_segment", [(0, 0, 0), (0, 1, 0), (2, 1, 0), (2, 0, 0)])

    def test_segment_offsets(self):
        # OFFSET: handles are relative to their endpoints -> same control points as above
        self._check("zz_segment_offset", [(0, 0, 0), (0, 1, 0), (2, 1, 0), (2, 0, 0)])

    def test_segment_is_two_point_bezier(self):
        mesh, _, _ = grid(2)
        r = evaluate(self.groups["zz_segment_raw"], mesh)
        self.assertEqual((r["curves"], len(r["curve_positions"])), (1, 2))

    def test_mode_error(self):
        with self.assertRaises(GNCompileError) as cm:
            gn_compile(
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.BezierSegment(mode='RELATIVE')\n"
            )
        self.assertIn("POSITION, OFFSET", str(cm.exception))


CIRCLE_SRC = """
def zz_circle_radius(m: gn.tGeometry) -> gn.tGeometry:
    return gn.CurveToMesh(gn.CurveCircle(radius=2.0, resolution=8))

def zz_circle_positional(m: gn.tGeometry) -> gn.tGeometry:
    return gn.CurveCircle(0.5, 16)

def zz_circle_points(m: gn.tGeometry) -> gn.tGeometry:
    off = gn.tVec(2, 3, 0)
    c, center = gn.CurveCircle(gn.tVec(1, 0, 0) + off, gn.tVec(0, 1, 0) + off, gn.tVec(-1, 0, 0) + off, resolution=12)
    return gn.StoreNamedAttribute(c, "center", center)

def zz_circle_center_drives_if(m: gn.tGeometry) -> gn.tGeometry:
    c, center = gn.CurveCircle(gn.tVec(1, 0, 0), gn.tVec(0, 1, 0), gn.tVec(-1, 0, 0))
    return c if center.x > -1 else m  # the centre is a single value: allowed
"""


class TestCurveCircle(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(CIRCLE_SRC)

    def test_radius(self):
        mesh, _, _ = grid(2)
        r = evaluate(self.groups["zz_circle_radius"], mesh)
        self.assertEqual((len(r["verts"]), r["edges"]), (8, 8))  # cyclic
        self.assertTrue(all(abs(v.length - 2.0) < 1e-5 and abs(v.z) < 1e-6 for v in r["verts"]))

    def test_positional_radius(self):
        mesh, _, _ = grid(2)
        pts = evaluate(self.groups["zz_circle_positional"], mesh)["curve_positions"]
        self.assertEqual(len(pts), 16)
        self.assertTrue(all(abs(p.length - 0.5) < 1e-5 for p in pts))

    def test_points_and_center(self):
        mesh, _, _ = grid(2)
        r = evaluate(self.groups["zz_circle_points"], mesh, attrs=("center",))
        pts, centers = r["curve_positions"], r["curve_attrs"]["center"]
        self.assertEqual(len(pts), 12)
        self.assertTrue(all((Vector(c) - Vector((2, 3, 0))).length < 1e-5 for c in centers))
        self.assertTrue(all(abs((p - Vector((2, 3, 0))).length - 1.0) < 1e-5 for p in pts))

    def test_center_is_single_value(self):
        self.assertIn("zz_circle_center_drives_if", self.groups)

    def test_errors(self):
        head = "def zz(m: gn.tGeometry) -> gn.tGeometry:\n"
        a, b, c = "gn.tVec(1, 0, 0)", "gn.tVec(0, 1, 0)", "gn.tVec(-1, 0, 0)"
        for body, fragment in (
            (
                f"    return gn.CurveCircle({a}, {b}, {c}, radius=2.0).Curve\n",
                "either a radius or three points",
            ),
            (f"    return gn.CurveCircle({a}, {b}).Curve\n", "needs all three (missing point3)"),
            ("    return gn.CurveCircle(radius=1.0, mode='POINTS')\n", "mode='POINTS' but a radius given"),
            ("    c, center = gn.CurveCircle(radius=1.0)\n    return c\n", "tuple unpacking size mismatch"),
            ("    return gn.CurveCircle(size=1.0)\n", "unknown argument 'size'"),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(head + body)
                self.assertIn(fragment, str(cm.exception))
