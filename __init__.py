"""py2gn: compile human-readable Python code into Geometry Nodes groups.

This top-level module deliberately does not import ``bpy`` so that ``py2gn.lang`` (the editor stub module) can be imported outside Blender.
"""

_needs_reload = "_loaded" in locals()
_loaded = True

_SUBMODULES = (
    "compiler.names",
    "compiler.errors",
    "compiler.values",
    "compiler.tables",
    "compiler.params",
    "compiler.analysis",
    "compiler.builder",
    "compiler.interface",
    "compiler.compile",
    "compiler.reference",
    "compiler",
    "ui.props",
    "ui.actions",
    "ui.ide",
    "ui.watcher",
    "ui.operators",
    "ui.panels",
    "ui",
)

if _needs_reload:
    import importlib
    import sys

    for _name in _SUBMODULES:
        _mod = sys.modules.get(f"{__name__}.{_name}")
        if _mod is not None:
            importlib.reload(_mod)
    print("py2gn reloaded")


def register():
    from . import ui

    ui.register()


def unregister():
    from . import ui

    ui.unregister()
