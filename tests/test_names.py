"""The naming convention: gn. namespace, bare names are yours, hints, migration."""

import ast
import importlib.util

import bpy

from py2gn.compiler import GNCompileError, gn_compile, names

from .common import ADDON_ROOT, CompilerTestCase, iface


def _lang_public_names() -> set[str]:
    spec = importlib.util.spec_from_file_location("_lang_check", ADDON_ROOT / "lang.py")
    assert spec is not None and spec.loader is not None
    tree = ast.parse((ADDON_ROOT / "lang.py").read_text(encoding="utf-8"))
    out = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
        elif isinstance(n, ast.Assign):
            out.update(t.id for t in n.targets if isinstance(t, ast.Name))
    return {x for x in out if not x.startswith("_")}


class TestNames(CompilerTestCase):
    def test_lang_matches_compiler(self):
        self.assertEqual(_lang_public_names(), names.PUBLIC)

    def test_alias_forms(self):
        for header, ns in (
            ("import py2gn.lang as gn", "gn"),
            ("import py2gn.lang as L", "L"),
            ("from py2gn import lang", "lang"),
            ("from py2gn import lang as G", "G"),
            ("import py2gn.lang", "py2gn.lang"),
        ):
            with self.subTest(header=header):
                src = f"{header}\n\ndef zz_alias(x: {ns}.tFloat) -> {ns}.Outputs(y={ns}.tFloat):\n    return {ns}.Sin(x) * {ns}.Pi\n"
                g = self.compile(src)["zz_alias"]
                self.assertEqual(
                    [(i.name, i.socket_type) for i in iface(g, "OUTPUT")],
                    [("y", "NodeSocketFloat")],
                )

    def test_bare_names_are_yours(self):
        # parameters named like built-ins are just parameters
        g = self.compile("def zz_p(Position: gn.tVec, Index: int):\n    return Position * Index\n")["zz_p"]
        self.assertFalse(any(n.bl_idname == "GeometryNodeInputPosition" for n in g.nodes))
        # a function / node group called like a built-in is called bare, the built-in via gn.
        groups = self.compile(
            "def Sin(x: float):\n    return x * 2\ndef zz_use(x: float):\n    return Sin(x) + gn.Sin(x)\n"
        )
        nodes = groups["zz_use"].nodes
        self.assertEqual(
            sum(n.bl_idname == "GeometryNodeGroup" and n.node_tree.name == "Sin" for n in nodes),
            1,
        )
        self.assertEqual(
            sum(n.bl_idname == "ShaderNodeMath" and n.operation == "SINE" for n in nodes),
            1,
        )
        # an existing node group of the .blend with a built-in's name is reachable too
        bpy.data.node_groups["Sin"].name = "JoinGeometry"
        g = self.compile("def zz_grp(x: float):\n    return JoinGeometry(x)\n")["zz_grp"]
        self.assertTrue(any(n.bl_idname == "GeometryNodeGroup" for n in g.nodes))

    def test_hints(self):
        for src, fragment in (
            ("def zz(x):\n    return x + position.z\n", "gn.Position"),
            ("def zz(m: geo) -> geo:\n    return m\n", "use gn.tGeometry"),
            (
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return store_attr(m, 'a', 1.0)\n",
                "gn.StoreNamedAttribute",
            ),
            ("def zz(x):\n    return gn.Positon.x\n", "did you mean gn.Position"),
            ("def zz(x):\n    return gn.Position()\n", "is a value, not a function"),
            ("def zz(x):\n    return gn.Sin\n", "is a function: call it"),
            ("def zz(x: gn.Vec):\n    return x\n", "types are gn.tFloat"),
            (
                "import py2gn.lang as L\n\ndef zz(x):\n    return gn.Sin(x)\n",
                "undefined name 'gn'",
            ),
        ):
            with self.subTest(fragment=fragment):
                with self.assertRaises(GNCompileError) as cm:
                    gn_compile(src)
                self.assertIn(fragment, str(cm.exception))

    def test_messages_use_public_names(self):
        with self.assertRaises(GNCompileError) as cm:
            gn_compile(
                "def zz(m: gn.tGeometry) -> gn.tGeometry:\n    return gn.SetPosition(m, ofset=gn.Normal)\n"
            )
        self.assertIn("gn.SetPosition() has no parameter 'ofset'", str(cm.exception))
