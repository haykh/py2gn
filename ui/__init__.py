"""Blender UI: settings, operators, panels and the source-file watcher."""

import bpy

from . import operators, panels, props, watcher

_CLASSES = (
    props.PY2GN_Settings,
    operators.PY2GN_OT_compile_text,
    operators.PY2GN_OT_compile_file,
    operators.PY2GN_OT_new_example,
    operators.PY2GN_OT_setup_ide,
    panels.PY2GN_PT_text_editor,
    panels.PY2GN_PT_node_editor,
)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.py2gn = bpy.props.PointerProperty(type=props.PY2GN_Settings)
    watcher.start()


def unregister():
    watcher.stop()
    del bpy.types.Scene.py2gn
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
