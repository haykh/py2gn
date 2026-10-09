"""Static analysis on generated node graphs (field dependency)."""

from __future__ import annotations

from .tables import FIELDS, SINGLE_VALUE_GEO_NODES, SINGLE_VALUE_INPUTS, TOPOLOGY_NODES

FIELD_SOURCES = (
    {idname for idname, _, _ in FIELDS.values() if idname not in SINGLE_VALUE_INPUTS}
    | {
        "GeometryNodeInputNamedAttribute",
        "GeometryNodeFieldAtIndex",
        "GeometryNodeFieldOnDomain",
    }
    | TOPOLOGY_NODES
)


def tree_has_field_source(tree, seen=None):
    seen = seen if seen is not None else set()
    if tree is None or tree.name in seen:
        return False
    seen.add(tree.name)
    for n in tree.nodes:
        if n.bl_idname in FIELD_SOURCES:
            return True
        if n.bl_idname == "GeometryNodeGroup" and tree_has_field_source(n.node_tree, seen):
            return True
    return False


def depends_on_field(sock, seen=None):
    seen = seen if seen is not None else set()
    n = sock.node
    if n.name in seen:
        return False
    seen.add(n.name)
    if n.bl_idname in FIELD_SOURCES:
        return True
    if n.bl_idname in SINGLE_VALUE_GEO_NODES:
        return False
    if sock.type != "GEOMETRY" and any(i.type == "GEOMETRY" for i in n.inputs):
        return True
    if n.bl_idname == "GeometryNodeGroup" and tree_has_field_source(n.node_tree):
        return True
    for i in n.inputs:
        for l in i.links:
            if depends_on_field(l.from_socket, seen):
                return True
    return False
