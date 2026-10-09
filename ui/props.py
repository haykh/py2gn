"""Per-scene settings."""

import bpy

from . import watcher


def _watch_changed(self, _context):
    # compile immediately when watching starts, then on every save
    watcher.forget(self.source_path)


class PY2GN_Settings(bpy.types.PropertyGroup):
    source_path: bpy.props.StringProperty(
        name="Source",
        description="Python file with the functions to compile (edit it in any IDE)",
        subtype="FILE_PATH",
    )
    watch: bpy.props.BoolProperty(
        name="Recompile on Save",
        description="Watch the source file and recompile whenever it changes on disk",
        default=False,
        update=_watch_changed,
    )
    status: bpy.props.StringProperty(name="Status", default="")
    status_error: bpy.props.BoolProperty(name="Status Is Error", default=False)
