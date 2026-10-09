"""Recompile the scene's source file when it changes on disk (polling timer)."""

from __future__ import annotations

import os

import bpy

_INTERVAL = 0.5
_mtimes: dict[str, float] = {}


def forget(path: str) -> None:
    _mtimes.pop(bpy.path.abspath(path), None)


def _tick() -> float:
    from .actions import compile_path, set_status

    for scene in bpy.data.scenes:
        settings = getattr(scene, "py2gn", None)
        if settings is None or not settings.watch or not settings.source_path:
            continue
        path = bpy.path.abspath(settings.source_path)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if _mtimes.get(path) == mtime:
            continue
        _mtimes[path] = mtime
        set_status(scene, compile_path(path))
    return _INTERVAL


def start() -> None:
    if not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=_INTERVAL, persistent=True)


def stop() -> None:
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    _mtimes.clear()
