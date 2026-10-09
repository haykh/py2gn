"""Public names of the language (``gn.<Name>``) and their internal equivalents.

Naming convention
-----------------
* Everything built in lives in one namespace, imported as ``import py2gn.lang as gn``
  (any alias works; ``gn`` is assumed when a file has no such import).
* Bare names are always the user's: parameters, locals, functions of the file and node
  groups of the .blend. Python's own ``float``, ``int``, ``bool`` and ``range`` stay bare.
* Nodes, fields and functions are PascalCase after Blender's node names
  (``gn.JoinGeometry``, ``gn.Position``); math keeps conventional names (``gn.Sin``).
* Socket types are ``t``-prefixed: ``gn.tFloat``, ``gn.tInt``, ``gn.tBool``, ``gn.tVec``,
  ``gn.tGeometry``.

This module has no ``bpy`` dependency (used by the migration tool outside Blender).
"""

from __future__ import annotations

import ast
import difflib

DEFAULT_ALIAS = "gn"
MODULE = "py2gn.lang"

# Socket types: public name -> internal type id (see values.py)
TYPES = {
    "tFloat": "FLOAT",
    "tInt": "INT",
    "tBool": "BOOL",
    "tVec": "VECTOR",
    "tGeometry": "GEOMETRY",
}

# Public -> internal name used by the builder. Groups only matter for documentation.
FIELDS = {
    "Position": "position",
    "Normal": "normal",
    "CurveTangent": "tangent",
    "Index": "index",
    "ID": "id",
    "Radius": "radius",
    "IsSplineCyclic": "is_cyclic",
    "SplineParameterFactor": "spline_factor",
    "SplineParameterLength": "spline_length",
    "SplineParameterIndex": "spline_index",
    "EdgeVerticesVertexIndex1": "edge_vertex_1",
    "EdgeVerticesVertexIndex2": "edge_vertex_2",
    "EdgeVerticesPosition1": "edge_position_1",
    "EdgeVerticesPosition2": "edge_position_2",
    "SceneTimeSeconds": "time",
    "SceneTimeFrame": "frame",
}
CONSTANTS = {"Pi": "pi", "Tau": "tau", "E": "e"}
TUPLE_FIELDS = {
    "SplineParameter": "spline_parameter",
    "EdgeVertices": "edge_vertices",
    "SceneTime": "scene_time",
}
FIELD_FUNCTIONS = {
    "EvaluateAtIndex": "at_index",
    "EvaluateOnDomain": "on_domain",
    "NamedAttribute": "attr",
    "NamedAttributeExists": "attr_exists",
}
GEOMETRY = {
    "SetPosition": "set_position",
    "StoreNamedAttribute": "store_attr",
    "RemoveNamedAttribute": "remove_attr",
    "JoinGeometry": "join",
    "DeleteGeometry": "delete",
    "MergeByDistance": "merge_by_distance",
    "SplitEdges": "split_edges",
    "MeshBoolean": "mesh_boolean",
    "MeshCircle": "mesh_circle",
    "InstanceOnPoints": "instance_on_points",
    "RealizeInstances": "realize_instances",
    "IndexSwitch": "index_switch",
    "CornersOfVertex": "corners_of_vertex",
    "EdgesOfVertex": "edges_of_vertex",
    "SampleIndex": "sample_index",
    "SampleNearest": "sample_nearest",
    "CornersOfEdge": "corners_of_edge",
    "CornersOfFace": "corners_of_face",
    "FaceOfCorner": "face_of_corner",
    "VertexOfCorner": "vertex_of_corner",
    "EdgesOfCorner": "edges_of_corner",
    "OffsetCornerInFace": "offset_corner_in_face",
    "DuplicateElements": "duplicate",
    "CaptureAttribute": "capture",
    "PointsToCurves": "points_to_curves",
    "SetSplineCyclic": "set_cyclic",
    "ReverseCurve": "reverse_curve",
    "CurveToMesh": "curve_to_mesh",
    "MeshToCurve": "mesh_to_curve",
    "MeshToPoints": "mesh_to_points",
    "ExtrudeMesh": "extrude",
    "FlipFaces": "flip_faces",
    "DomainSize": "domain_size",
    "AttributeStatistic": "attr_stat",
}
MATH = {
    "Sin": "sin",
    "Cos": "cos",
    "Tan": "tan",
    "Asin": "asin",
    "Acos": "acos",
    "Atan": "atan",
    "Atan2": "atan2",
    "Sinh": "sinh",
    "Cosh": "cosh",
    "Tanh": "tanh",
    "Sqrt": "sqrt",
    "InverseSqrt": "inversesqrt",
    "Exp": "exp",
    "Log": "log",
    "Abs": "abs",
    "Floor": "floor",
    "Ceil": "ceil",
    "Round": "round",
    "Trunc": "trunc",
    "Fract": "fract",
    "Sign": "sign",
    "Radians": "radians",
    "Degrees": "degrees",
    "Pow": "pow",
    "Min": "min",
    "Max": "max",
    "FMod": "fmod",
    "Mod": "mod",
    "Snap": "snap",
    "PingPong": "pingpong",
    "Wrap": "wrap",
    "Clamp": "clamp",
    "Mix": "lerp",
    "Length": "length",
    "Dot": "dot",
    "Cross": "cross",
    "Normalize": "normalize",
    "Distance": "distance",
    "Project": "project",
    "Reflect": "reflect",
}
CONSTRUCTORS = {"tVec": "vec", "tFloat": "float", "tInt": "int", "tBool": "bool"}
SPECIAL = {"Outputs": "outputs", "Param": "param", "Repeat": "repeat"}
DECORATORS = {"inline": "inline"}

CALLABLE = {
    **TUPLE_FIELDS,
    **FIELD_FUNCTIONS,
    **GEOMETRY,
    **MATH,
    **CONSTRUCTORS,
    **SPECIAL,
}
VALUES = {**FIELDS, **CONSTANTS}
PUBLIC = set(CALLABLE) | set(VALUES) | set(TYPES) | set(DECORATORS)

# internal -> public (for messages); constructors map back to their type name
PUBLIC_OF = {internal: public for public, internal in {**CALLABLE, **VALUES}.items()}

# Python builtins that stay bare in function files
PYTHON_BARE = {"float", "int", "bool", "range"}

# Pre-namespace (v0.1) names -> public names, for migration and "did you mean" hints
OLD_NAMES: dict[str, str] = {
    # types (annotations, constructors, attr(..., type))
    "vec": "tVec",
    "Vec": "tVec",
    "vec3": "tVec",
    "Vec3": "tVec",
    "Vector": "tVec",
    "geo": "tGeometry",
    "Geo": "tGeometry",
    "geometry": "tGeometry",
    "Geometry": "tGeometry",
    # constants / fields
    "pi": "Pi",
    "tau": "Tau",
    "e": "E",
    "position": "Position",
    "normal": "Normal",
    "tangent": "CurveTangent",
    "index": "Index",
    "id": "ID",
    "radius": "Radius",
    "is_cyclic": "IsSplineCyclic",
    "curve_factor": "SplineParameterFactor",
    "spline_factor": "SplineParameterFactor",
    "curve_length": "SplineParameterLength",
    "spline_length": "SplineParameterLength",
    "curve_index": "SplineParameterIndex",
    "spline_index": "SplineParameterIndex",
    "edge_vertex_1": "EdgeVerticesVertexIndex1",
    "edge_vertex_2": "EdgeVerticesVertexIndex2",
    "edge_position_1": "EdgeVerticesPosition1",
    "edge_position_2": "EdgeVerticesPosition2",
    "time": "SceneTimeSeconds",
    "frame": "SceneTimeFrame",
    "spline_parameter": "SplineParameter",
    "edge_vertices": "EdgeVertices",
    # field functions
    "at_index": "EvaluateAtIndex",
    "on_domain": "EvaluateOnDomain",
    "attr": "NamedAttribute",
    "attr_exists": "NamedAttributeExists",
    # geometry
    "set_position": "SetPosition",
    "store_attr": "StoreNamedAttribute",
    "store_named_attribute": "StoreNamedAttribute",
    "remove_attr": "RemoveNamedAttribute",
    "remove_named_attribute": "RemoveNamedAttribute",
    "remove_attribute": "RemoveNamedAttribute",
    "join": "JoinGeometry",
    "join_geometry": "JoinGeometry",
    "delete": "DeleteGeometry",
    "delete_geometry": "DeleteGeometry",
    "merge_by_distance": "MergeByDistance",
    "duplicate": "DuplicateElements",
    "duplicate_elements": "DuplicateElements",
    "capture": "CaptureAttribute",
    "capture_attribute": "CaptureAttribute",
    "points_to_curves": "PointsToCurves",
    "points_to_curve": "PointsToCurves",
    "set_cyclic": "SetSplineCyclic",
    "set_spline_cyclic": "SetSplineCyclic",
    "reverse_curve": "ReverseCurve",
    "curve_to_mesh": "CurveToMesh",
    "mesh_to_curve": "MeshToCurve",
    "mesh_to_points": "MeshToPoints",
    "extrude": "ExtrudeMesh",
    "extrude_mesh": "ExtrudeMesh",
    "flip_faces": "FlipFaces",
    "domain_size": "DomainSize",
    "attribute_domain_size": "DomainSize",
    "attr_stat": "AttributeStatistic",
    "attribute_statistic": "AttributeStatistic",
    # math (including the Python builtins the old language reused)
    **{internal: public for public, internal in MATH.items()},
    "lerp": "Mix",
    "mix": "Mix",
    "outputs": "Outputs",
}


def find_aliases(tree: ast.Module) -> set[str]:
    """Names under which ``py2gn.lang`` is imported at module level (default: {"gn"})."""
    aliases: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == MODULE:
                    aliases.add(a.asname or MODULE)  # bare `import py2gn.lang` -> dotted access
        elif isinstance(node, ast.ImportFrom) and node.module == "py2gn":
            for a in node.names:
                if a.name == "lang":
                    aliases.add(a.asname or "lang")
    return aliases or {DEFAULT_ALIAS}


def dotted(node: ast.expr) -> str | None:
    """``a.b.c`` -> "a.b.c" for Name/Attribute chains, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def namespace_member(node: ast.expr, aliases: set[str]) -> str | None:
    """If ``node`` is ``<alias>.Name``, return "Name" (public spelling), else None."""
    if isinstance(node, ast.Attribute) and dotted(node.value) in aliases:
        return node.attr
    return None


def suggest(name: str, alias: str) -> str:
    """Hint for an unknown name: old spelling or close public match."""
    if name in OLD_NAMES:
        return f" -- built-ins live in the namespace now: {alias}.{OLD_NAMES[name]}"
    close = difflib.get_close_matches(name, sorted(PUBLIC), n=1)
    return f" -- did you mean {alias}.{close[0]}?" if close else ""
