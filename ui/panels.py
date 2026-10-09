"""Sidebar panels in the Text Editor and the Geometry Node Editor."""

import bpy

from ..compiler import SOURCE_KEY


def _draw(layout, context, in_text_editor: bool) -> None:
    settings = context.scene.py2gn

    col = layout.column(align=True)
    col.label(text="Source File (external IDE)")
    col.prop(settings, "source_path", text="")
    row = col.row(align=True)
    row.operator("py2gn.compile_file", icon="FILE_SCRIPT")
    row.prop(settings, "watch", text="", icon="FILE_REFRESH", toggle=True)
    col.operator("py2gn.setup_ide", icon="CONSOLE")

    if in_text_editor:
        layout.separator()
        col = layout.column(align=True)
        col.label(text="Text Block")
        col.operator("py2gn.compile_text", icon="NODETREE")
        col.operator("py2gn.new_example", icon="FILE_NEW")

    if settings.status:
        box = layout.box()
        box.alert = settings.status_error
        for i, chunk in enumerate(_wrap(settings.status, 42)):
            box.label(
                text=chunk,
                icon=("ERROR" if settings.status_error else "CHECKMARK") if i == 0 else "BLANK1",
            )

    made = [g for g in bpy.data.node_groups if SOURCE_KEY in g]
    if made:
        layout.separator()
        col = layout.column(align=True)
        col.label(text="Compiled Groups")
        for g in made:
            col.label(text=g.name, icon="NODE")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    return [*lines, cur] if cur else lines


class PY2GN_PT_text_editor(bpy.types.Panel):
    bl_space_type = "TEXT_EDITOR"
    bl_region_type = "UI"
    bl_category = "py2gn"
    bl_label = "py2gn"

    def draw(self, context):
        _draw(self.layout, context, True)


class PY2GN_PT_node_editor(bpy.types.Panel):
    bl_space_type = "NODE_EDITOR"
    bl_region_type = "UI"
    bl_category = "py2gn"
    bl_label = "py2gn"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return space is not None and getattr(space, "tree_type", "") == "GeometryNodeTree"

    def draw(self, context):
        _draw(self.layout, context, False)
