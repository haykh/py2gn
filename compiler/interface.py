"""Synchronising node-group interface sockets with a function signature."""

from __future__ import annotations

from .errors import GNCompileError
from .values import BOOL, GEO, IFACE_SOCKET, INT, LIMITS, SUBTYPES, VEC


def sync_sockets(ng, in_out, specs):
    """Reuse existing interface sockets with matching name+type so links in parent trees survive."""
    existing = [it for it in ng.interface.items_tree if it.item_type == "SOCKET" and it.in_out == in_out]
    used, items = set(), []
    for spec in specs:
        name, T, default = spec[:3]
        meta = spec[3] if len(spec) > 3 else None
        st = IFACE_SOCKET[T]
        it = next(
            (x for x in existing if x.name == name and x.socket_type == st and x.identifier not in used),
            None,
        )
        if it is None:
            it = ng.interface.new_socket(name=name, in_out=in_out, socket_type=st)
        used.add(it.identifier)
        items.append(it)
        if meta is not None:  # inputs: the source is the source of truth (absent options are reset)
            _apply_meta(it, T, meta)
        if default is not None and T != GEO:  # after min/max: Blender clamps the default into the range
            it.default_value = _coerce_default(name, T, default)
    for x in existing:
        if x.identifier not in used:
            ng.interface.remove(x)
    return items


def _apply_meta(it, T, meta: dict) -> None:
    it.description = meta.get("description", "")
    if T in LIMITS:
        lo, hi = LIMITS[T]
        it.min_value = meta.get("min", lo)
        it.max_value = meta.get("max", hi)
    if T in SUBTYPES:
        it.subtype = meta.get("subtype", "NONE")


def reorder_interface(ng, ordered):
    for pos, it in enumerate(ordered):
        ng.interface.move(it, pos)


def _coerce_default(name, T, default):
    """Convert a literal parameter default to the socket's value type."""
    try:
        if T == VEC:
            if isinstance(default, (tuple, list)):
                if len(default) != 3:
                    raise ValueError
                return tuple(float(c) for c in default)
            return (float(default),) * 3
        if T == BOOL:
            return bool(default)
        if T == INT:
            return int(default)
        return float(default)
    except (TypeError, ValueError):
        raise GNCompileError(f"default {default!r} of '{name}' does not fit type {T.lower()}") from None
