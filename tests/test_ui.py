"""Operators, panels and the source-file watcher."""

import os
import time

import bpy

from py2gn.ui import watcher

from .common import ARTIFACTS, CompilerTestCase


class TestUI(CompilerTestCase):
    def test_registered(self):
        for idname in (
            "compile_text",
            "compile_file",
            "new_example",
            "setup_ide",
        ):
            self.assertTrue(hasattr(bpy.ops.py2gn, idname))
        self.assertTrue(hasattr(bpy.types, "PY2GN_PT_text_editor"))
        self.assertTrue(hasattr(bpy.types, "PY2GN_PT_node_editor"))
        self.assertTrue(hasattr(bpy.context.scene, "py2gn"))

    def test_setup_ide(self):
        from py2gn.ui.ide import setup_folder, venv_python

        folder = ARTIFACTS / "ide"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ruff.toml").write_text("# user's own\n", encoding="utf-8")
        if venv_python() is None:
            self.skipTest("no .venv in the checkout")
        written, skipped = setup_folder(str(folder))
        self.assertEqual(
            sorted(written),
            sorted(["pyrefly.toml", os.path.join(".vscode", "settings.json")]),
        )
        self.assertEqual(skipped, ["ruff.toml"])
        self.assertEqual((folder / "ruff.toml").read_text(encoding="utf-8"), "# user's own\n")
        self.assertIn(
            "python-interpreter-path",
            (folder / "pyrefly.toml").read_text(encoding="utf-8"),
        )

    def test_compile_file_and_watch(self):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        path = ARTIFACTS / "watched.py"
        path.write_text(
            "import py2gn.lang as gn\n\ndef zz_w(x: float):\n    return x * 2\n",
            encoding="utf-8",
        )
        settings = bpy.context.scene.py2gn
        settings.source_path = str(path)
        self.assertEqual(bpy.ops.py2gn.compile_file(), {"FINISHED"})
        self.assertIn("zz_w", bpy.data.node_groups)
        self.assertFalse(settings.status_error)

        settings.watch = True
        watcher._tick()  # first tick records the current file
        time.sleep(0.05)
        path.write_text("def zz_w(x: float):\n    return x * 2 + zz_missing\n", encoding="utf-8")
        os.utime(path, (time.time() + 5, time.time() + 5))
        watcher._tick()
        self.assertTrue(settings.status_error)
        self.assertIn("zz_missing", settings.status)
        path.write_text("def zz_w(x: float, y: float = 1.0):\n    return x * y\n", encoding="utf-8")
        os.utime(path, (time.time() + 10, time.time() + 10))
        watcher._tick()
        self.assertFalse(settings.status_error, settings.status)
        self.assertEqual(len(bpy.data.node_groups["zz_w"].interface.items_tree), 3)
        settings.watch = False
