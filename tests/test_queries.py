"""Domain Size, Attribute Statistic, Mesh to Curve, Reverse Curve, Spline Parameter, Is Spline Cyclic."""

import math
import statistics as st

import bpy
from mathutils import Vector

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
