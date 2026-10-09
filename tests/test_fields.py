"""Built-in fields, Evaluate at Index / on Domain, named attributes."""

import random

import bpy
from mathutils import Vector

from .common import EXAMPLES, CompilerTestCase, evaluate, grid


class TestFields(CompilerTestCase):
    def setUp(self):
        super().setUp()
        self.groups = self.compile(EXAMPLES.read_text(encoding="utf-8"))
        self.harness = self.compile(
            """def zz_store_vec(mesh: gn.tGeometry, step: int = 1) -> gn.tGeometry:
    return gn.StoreNamedAttribute(mesh, 'out', neighbor_delta(step))
def zz_store_face(mesh: gn.tGeometry) -> gn.tGeometry:
    return gn.StoreNamedAttribute(mesh, 'out', face_avg_offset(1.0))
"""
        )

    def test_at_index(self):
        mesh, verts, _ = grid(6, jitter=0.3, seed=1)
        out = evaluate(self.harness["zz_store_vec"], mesh, {"step": 3}, attrs=("out",))["attrs"]["out"]
        P = [Vector(v) for v in verts]
        for i in range(len(P) - 3):
            self.assertLess((Vector(out[i]) - (P[i + 3] - P[i])).length, 1e-6)
        for i in range(len(P) - 3, len(P)):  # out of range reads zero
            self.assertLess((Vector(out[i]) + P[i]).length, 1e-6)

    def test_on_domain(self):
        mesh, verts, faces = grid(6, jitter=0.3, seed=1)
        out = evaluate(self.harness["zz_store_face"], mesh, attrs=("out",))["attrs"]["out"]
        P = [Vector(v) for v in verts]
        centers = [sum((P[v] for v in f), Vector()) / 4 for f in faces]
        adj: list[list[int]] = [[] for _ in P]
        for fi, f in enumerate(faces):
            for v in f:
                adj[v].append(fi)
        for i, p in enumerate(P):
            expect = sum((centers[f] for f in adj[i]), Vector()) / len(adj[i]) - p
            self.assertLess((Vector(out[i]) - expect).length, 1e-6)

    def test_edge_vertices(self):
        g = self.compile(
            """def zz_edges(mesh: gn.tGeometry) -> gn.tGeometry:
    v1, v2, p1, p2 = gn.EdgeVertices()
    mesh = gn.StoreNamedAttribute(mesh, 'ev', gn.tVec(v1, v2, gn.EdgeVerticesVertexIndex1 + gn.EdgeVerticesVertexIndex2), domain='EDGE')
    mesh = gn.StoreNamedAttribute(mesh, 'ed', p2 - p1, domain='EDGE')
    return gn.StoreNamedAttribute(mesh, 'total', gn.AttributeStatistic(mesh, gn.Length(gn.EdgeVerticesPosition2 - gn.EdgeVerticesPosition1), 'sum', domain='EDGE'))
"""
        )["zz_edges"]
        self.assertEqual(sum(n.bl_idname == "GeometryNodeInputMeshEdgeVertices" for n in g.nodes), 1)
        mesh, verts, _ = grid(4, jitter=0.3, seed=5)
        r = evaluate(g, mesh, attrs=("ev", "ed", "total"))
        P = [Vector(v) for v in verts]
        self.assertEqual(len(r["attrs"]["ev"]), r["edges"])  # stored per edge
        total = 0.0
        for (a, b), ev, ed in zip(r["edge_verts"], r["attrs"]["ev"], r["attrs"]["ed"]):
            self.assertEqual((round(ev[0]), round(ev[1]), round(ev[2])), (a, b, a + b))
            self.assertLess((Vector(ed) - (P[b] - P[a])).length, 1e-6)
            total += (P[b] - P[a]).length
        self.assertAlmostEqual(r["attrs"]["total"][0], total, places=4)

    def test_named_attributes(self):
        g = self.compile(
            """def zz_attr(mesh: gn.tGeometry) -> gn.tGeometry:
    w = gn.NamedAttribute('weight')
    d = gn.NamedAttribute('dir', gn.tVec)
    f = gn.NamedAttribute('flag', type=bool)
    nxt = gn.EvaluateAtIndex(gn.NamedAttribute('weight'), gn.Index + 1)
    a = 1.0 if gn.NamedAttributeExists('weight') else 0.0
    b = 10.0 if gn.NamedAttributeExists('nope') else 0.0
    return gn.StoreNamedAttribute(mesh, 'out', d * w + gn.tVec(nxt, 1.0 if f else 0.0, a + b))
"""
        )["zz_attr"]
        named = [n for n in g.nodes if n.bl_idname == "GeometryNodeInputNamedAttribute"]
        self.assertEqual(
            sorted(n.inputs["Name"].default_value for n in named),
            ["dir", "flag", "nope", "weight"],
        )
        rnd = random.Random(3)
        n = 20
        me = bpy.data.meshes.new("__test_attr")
        me.vertices.add(n)
        W = [rnd.uniform(-2, 2) for _ in range(n)]
        D = [Vector([rnd.uniform(-1, 1) for _ in range(3)]) for _ in range(n)]
        F = [rnd.random() < 0.5 for _ in range(n)]
        me.attributes.new("weight", "FLOAT", "POINT").data.foreach_set("value", W)
        a = me.attributes.new("dir", "FLOAT_VECTOR", "POINT")
        for k in range(n):
            a.data[k].vector = D[k]
        me.attributes.new("flag", "BOOLEAN", "POINT").data.foreach_set("value", F)
        out = evaluate(g, me, attrs=("out",))["attrs"]["out"]
        for k in range(n):
            expect = D[k] * W[k] + Vector((W[k + 1] if k + 1 < n else 0.0, 1.0 if F[k] else 0.0, 1.0))
            self.assertLess((Vector(out[k]) - expect).length, 1e-6)
