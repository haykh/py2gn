"""Operators."""

import os

import bpy

from .actions import compile_path, compile_source, set_status

EXAMPLE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples", "functions.py")


class PY2GN_OT_compile_text(bpy.types.Operator):
    bl_idname = "py2gn.compile_text"
    bl_label = "Compile Text"
    bl_description = "Compile every top-level def in the active text into a Geometry Nodes group"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and space.type == "TEXT_EDITOR" and space.text is not None

    def execute(self, context):
        text = context.space_data.text
        result = compile_source(text.as_string(), text.name)
        set_status(context.scene, result)
        if not result.ok:
            if result.lineno:
                text.cursor_set(result.lineno - 1)
            self.report({"ERROR"}, result.message)
            return {"CANCELLED"}
        self.report({"INFO"}, result.message)
        return {"FINISHED"}


class PY2GN_OT_compile_file(bpy.types.Operator):
    bl_idname = "py2gn.compile_file"
    bl_label = "Compile File"
    bl_description = "Compile the source file set in the py2gn panel"

    @classmethod
    def poll(cls, context):
        return bool(context.scene.py2gn.source_path)

    def execute(self, context):
        result = compile_path(context.scene.py2gn.source_path)
        set_status(context.scene, result)
        self.report({"INFO"} if result.ok else {"ERROR"}, result.message)
        return {"FINISHED"} if result.ok else {"CANCELLED"}


class PY2GN_OT_setup_ide(bpy.types.Operator):
    bl_idname = "py2gn.setup_ide"
    bl_label = "Set Up Folder for IDE"
    bl_description = (
        "Write pyrefly.toml, ruff.toml and .vscode/settings.json next to the source file so an IDE "
        "type-checks it against py2gn.lang (existing files are left alone)"
    )

    @classmethod
    def poll(cls, context):
        return bool(context.scene.py2gn.source_path)

    def execute(self, context):
        from .ide import setup_folder

        folder = os.path.dirname(bpy.path.abspath(context.scene.py2gn.source_path))
        try:
            written, skipped = setup_folder(folder)
        except FileNotFoundError as ex:
            self.report({"ERROR"}, str(ex))
            return {"CANCELLED"}
        msg = f"{folder}: wrote {', '.join(written) or 'nothing'}"
        if skipped:
            msg += f" (kept existing {', '.join(skipped)})"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class PY2GN_OT_new_example(bpy.types.Operator):
    bl_idname = "py2gn.new_example"
    bl_label = "New Example Text"
    bl_description = "Create a text block with example functions"

    def execute(self, context):
        with open(EXAMPLE_FILE, encoding="utf-8") as fh:
            body = fh.read()
        text = bpy.data.texts.new("py2gn_functions.py")
        text.write(body)
        space = context.space_data
        if space is not None and space.type == "TEXT_EDITOR":
            space.text = text
        return {"FINISHED"}
