"""Lookup tables: operators, built-in functions, fields, geometry operations."""

from __future__ import annotations

import ast
import math

from .values import BOOL, FLOAT, INT, VEC

CONSTS = {"pi": math.pi, "tau": math.tau, "e": math.e}


# Built-in fields: bare names that resolve to input nodes (parameters with the same name shadow them).
FIELDS = {
    "position": ("GeometryNodeInputPosition", "Position", VEC),
    "normal": ("GeometryNodeInputNormal", "Normal", VEC),
    "tangent": ("GeometryNodeInputTangent", "Tangent", VEC),
    "index": ("GeometryNodeInputIndex", "Index", INT),
    "id": ("GeometryNodeInputID", "ID", INT),
    "radius": ("GeometryNodeInputRadius", "Radius", FLOAT),
    "curve_factor": ("GeometryNodeSplineParameter", "Factor", FLOAT),
    "curve_length": ("GeometryNodeSplineParameter", "Length", FLOAT),
    "curve_index": ("GeometryNodeSplineParameter", "Index", INT),
    "spline_factor": ("GeometryNodeSplineParameter", "Factor", FLOAT),
    "spline_length": ("GeometryNodeSplineParameter", "Length", FLOAT),
    "spline_index": ("GeometryNodeSplineParameter", "Index", INT),
    "is_cyclic": ("GeometryNodeInputSplineCyclic", "Cyclic", BOOL),
    "edge_neighbors": ("GeometryNodeInputMeshEdgeNeighbors", "Face Count", INT),
    "edge_vertex_1": ("GeometryNodeInputMeshEdgeVertices", "Vertex Index 1", INT),
    "edge_vertex_2": ("GeometryNodeInputMeshEdgeVertices", "Vertex Index 2", INT),
    "edge_position_1": ("GeometryNodeInputMeshEdgeVertices", "Position 1", VEC),
    "edge_position_2": ("GeometryNodeInputMeshEdgeVertices", "Position 2", VEC),
    "time": ("GeometryNodeInputSceneTime", "Seconds", FLOAT),
    "frame": ("GeometryNodeInputSceneTime", "Frame", FLOAT),
}

# Zero-argument calls returning several fields of one node: ``a, b, ... = name()``
TUPLE_FIELDS = {
    "spline_parameter": ("spline_factor", "spline_length", "spline_index"),
    "edge_vertices": (
        "edge_vertex_1",
        "edge_vertex_2",
        "edge_position_1",
        "edge_position_2",
    ),
    "scene_time": ("time", "frame"),
}

# Field-function nodes whose unlinked index inputs evaluate the current element (so they are fields)
TOPOLOGY_NODES = {
    "GeometryNodeCornersOfVertex",
    "GeometryNodeCornersOfEdge",
    "GeometryNodeCornersOfFace",
    "GeometryNodeFaceOfCorner",
    "GeometryNodeVertexOfCorner",
    "GeometryNodeEdgesOfCorner",
    "GeometryNodeOffsetCornerInFace",
    "GeometryNodeEdgesOfVertex",
}

# Input nodes that give single values, not fields (everything else in FIELDS is a field)
SINGLE_VALUE_INPUTS = {"GeometryNodeInputSceneTime"}


DOMAINS = ("POINT", "EDGE", "FACE", "CORNER", "CURVE", "INSTANCE", "LAYER")


FIELD_DATA_TYPE = {FLOAT: "FLOAT", INT: "INT", BOOL: "BOOLEAN", VEC: "FLOAT_VECTOR"}


# Geometry operations.  name -> (bl_idname, params, outputs, auto_type_param)
# param = (keyword, kind, target); kind: G geometry input, V value/field input, S string literal -> socket,
#                                       E string literal -> enum property (target = (prop, choices))
#                                       M string literal -> menu socket (target = (socket, {ARG: menu item}))
#                                       P compile-time bool -> node property (target = property name)
# Positional arguments bind to params in order; anything not given keeps the node's own default
# (e.g. unlinked Position on Set Position stays the implicit position field).
K_GEO, K_VAL, K_STR, K_ENUM, K_MENU, K_PROP = "geo", "val", "str", "enum", "menu", "prop"


DUP_DOMAINS = ("POINT", "EDGE", "FACE", "SPLINE", "LAYER", "INSTANCE")
DELETE_DOMAINS = ("POINT", "EDGE", "FACE", "CURVE", "INSTANCE", "LAYER")


GEO_OPS = {
    "set_position": (
        "GeometryNodeSetPosition",
        [
            ("geometry", K_GEO, "Geometry"),
            ("position", K_VAL, "Position"),
            ("offset", K_VAL, "Offset"),
            ("selection", K_VAL, "Selection"),
        ],
        ["Geometry"],
        None,
    ),
    "store_attr": (
        "GeometryNodeStoreNamedAttribute",
        [
            ("geometry", K_GEO, "Geometry"),
            ("name", K_STR, "Name"),
            ("value", K_VAL, "Value"),
            ("domain", K_ENUM, ("domain", DOMAINS)),
            ("selection", K_VAL, "Selection"),
        ],
        ["Geometry"],
        "value",
    ),
    "duplicate": (
        "GeometryNodeDuplicateElements",
        [
            ("geometry", K_GEO, "Geometry"),
            ("amount", K_VAL, "Amount"),
            ("domain", K_ENUM, ("domain", DUP_DOMAINS)),
            ("selection", K_VAL, "Selection"),
        ],
        ["Geometry", "Duplicate Index"],
        None,
    ),
    "points_to_curves": (
        "GeometryNodePointsToCurves",
        [
            ("points", K_GEO, "Points"),
            ("group_id", K_VAL, "Curve Group ID"),
            ("weight", K_VAL, "Weight"),
        ],
        ["Curves"],
        None,
    ),
    "set_cyclic": (
        "GeometryNodeSetSplineCyclic",
        [
            ("curve", K_GEO, "Curve"),
            ("cyclic", K_VAL, "Cyclic"),
            ("selection", K_VAL, "Selection"),
        ],
        ["Curve"],
        None,
    ),
    "curve_to_mesh": (
        "GeometryNodeCurveToMesh",
        [
            ("curve", K_GEO, "Curve"),
            ("profile", K_GEO, "Profile Curve"),
            ("scale", K_VAL, "Scale"),
            ("fill_caps", K_VAL, "Fill Caps"),
        ],
        ["Mesh"],
        None,
    ),
    "extrude": (
        "GeometryNodeExtrudeMesh",
        [
            ("mesh", K_GEO, "Mesh"),
            ("offset", K_VAL, "Offset"),
            ("scale", K_VAL, "Offset Scale"),
            ("mode", K_ENUM, ("mode", ("VERTICES", "EDGES", "FACES"))),
            ("individual", K_VAL, "Individual"),
            ("selection", K_VAL, "Selection"),
        ],
        ["Mesh", "Top", "Side"],
        None,
    ),
    "flip_faces": (
        "GeometryNodeFlipFaces",
        [("mesh", K_GEO, "Mesh"), ("selection", K_VAL, "Selection")],
        ["Mesh"],
        None,
    ),
    "reverse_curve": (
        "GeometryNodeReverseCurve",
        [("curve", K_GEO, "Curve"), ("selection", K_VAL, "Selection")],
        ["Curve"],
        None,
    ),
    "mesh_to_curve": (
        "GeometryNodeMeshToCurve",
        [
            ("mesh", K_GEO, "Mesh"),
            ("selection", K_VAL, "Selection"),
            ("mode", K_ENUM, ("mode", ("EDGES", "FACES"))),
        ],
        ["Curve"],
        None,
    ),
    "resample_curve": (
        "GeometryNodeResampleCurve",
        [
            ("curve", K_GEO, "Curve"),
            ("count", K_VAL, "Count"),
            ("length", K_VAL, "Length"),
            ("mode", K_MENU, ("Mode", {"EVALUATED": "Evaluated", "COUNT": "Count", "LENGTH": "Length"})),
            ("selection", K_VAL, "Selection"),
        ],
        ["Curve"],
        None,
    ),
    "mesh_to_points": (
        "GeometryNodeMeshToPoints",
        [
            ("mesh", K_GEO, "Mesh"),
            ("selection", K_VAL, "Selection"),
            ("position", K_VAL, "Position"),
            ("radius", K_VAL, "Radius"),
            ("mode", K_ENUM, ("mode", ("VERTICES", "EDGES", "FACES", "CORNERS"))),
        ],
        ["Points"],
        None,
    ),
    "delete": (
        "GeometryNodeDeleteGeometry",
        [
            ("geometry", K_GEO, "Geometry"),
            ("selection", K_VAL, "Selection"),
            ("domain", K_ENUM, ("domain", DELETE_DOMAINS)),
            ("mode", K_ENUM, ("mode", ("ALL", "EDGE_FACE", "ONLY_FACE"))),
        ],
        ["Geometry"],
        None,
    ),
    "mesh_circle": (
        "GeometryNodeMeshCircle",
        [
            ("vertices", K_VAL, "Vertices"),
            ("radius", K_VAL, "Radius"),
            ("fill", K_ENUM, ("fill_type", ("NONE", "NGON", "TRIANGLE_FAN"))),
        ],
        ["Mesh"],
        None,
    ),
    # curve primitives: resolution last, so positional calls read like the math
    "bezier_segment": (
        "GeometryNodeCurvePrimitiveBezierSegment",
        [
            ("start", K_VAL, "Start"),
            ("start_handle", K_VAL, "Start Handle"),
            ("end_handle", K_VAL, "End Handle"),
            ("end", K_VAL, "End"),
            ("resolution", K_VAL, "Resolution"),
            ("mode", K_ENUM, ("mode", ("POSITION", "OFFSET"))),
        ],
        ["Curve"],
        None,
    ),
    "quadratic_bezier": (
        "GeometryNodeCurveQuadraticBezier",
        [
            ("start", K_VAL, "Start"),
            ("middle", K_VAL, "Middle"),
            ("end", K_VAL, "End"),
            ("resolution", K_VAL, "Resolution"),
        ],
        ["Curve"],
        None,
    ),
    "grid": (
        "GeometryNodeMeshGrid",
        [
            ("size_x", K_VAL, "Size X"),
            ("size_y", K_VAL, "Size Y"),
            ("vertices_x", K_VAL, "Vertices X"),
            ("vertices_y", K_VAL, "Vertices Y"),
        ],
        ["Mesh", "UV Map"],
        None,
    ),
    "instance_on_points": (
        "GeometryNodeInstanceOnPoints",
        [
            ("points", K_GEO, "Points"),
            ("instance", K_GEO, "Instance"),
            ("selection", K_VAL, "Selection"),
            ("rotation", K_VAL, "Rotation"),
            ("scale", K_VAL, "Scale"),
            ("pick_instance", K_VAL, "Pick Instance"),
            ("instance_index", K_VAL, "Instance Index"),
        ],
        ["Instances"],
        None,
    ),
    "realize_instances": (
        "GeometryNodeRealizeInstances",
        [
            ("geometry", K_GEO, "Geometry"),
            ("selection", K_VAL, "Selection"),
            ("realize_all", K_VAL, "Realize All"),
            ("depth", K_VAL, "Depth"),
        ],
        ["Geometry"],
        None,
    ),
    # mesh topology (field functions; their index inputs default to the current element)
    "corners_of_vertex": (
        "GeometryNodeCornersOfVertex",
        [
            ("vertex_index", K_VAL, "Vertex Index"),
            ("weights", K_VAL, "Weights"),
            ("sort_index", K_VAL, "Sort Index"),
        ],
        ["Corner Index", "Total"],
        None,
    ),
    "corners_of_edge": (
        "GeometryNodeCornersOfEdge",
        [
            ("edge_index", K_VAL, "Edge Index"),
            ("weights", K_VAL, "Weights"),
            ("sort_index", K_VAL, "Sort Index"),
        ],
        ["Corner Index", "Total"],
        None,
    ),
    "corners_of_face": (
        "GeometryNodeCornersOfFace",
        [
            ("face_index", K_VAL, "Face Index"),
            ("weights", K_VAL, "Weights"),
            ("sort_index", K_VAL, "Sort Index"),
        ],
        ["Corner Index", "Total"],
        None,
    ),
    "face_of_corner": (
        "GeometryNodeFaceOfCorner",
        [("corner_index", K_VAL, "Corner Index")],
        ["Face Index", "Index in Face"],
        None,
    ),
    "vertex_of_corner": (
        "GeometryNodeVertexOfCorner",
        [("corner_index", K_VAL, "Corner Index")],
        ["Vertex Index"],
        None,
    ),
    "edges_of_corner": (
        "GeometryNodeEdgesOfCorner",
        [("corner_index", K_VAL, "Corner Index")],
        ["Next Edge Index", "Previous Edge Index"],
        None,
    ),
    "offset_corner_in_face": (
        "GeometryNodeOffsetCornerInFace",
        [("corner_index", K_VAL, "Corner Index"), ("offset", K_VAL, "Offset")],
        ["Corner Index"],
        None,
    ),
    "edges_of_vertex": (
        "GeometryNodeEdgesOfVertex",
        [
            ("vertex_index", K_VAL, "Vertex Index"),
            ("weights", K_VAL, "Weights"),
            ("sort_index", K_VAL, "Sort Index"),
        ],
        ["Edge Index", "Total"],
        None,
    ),
    "sample_index": (
        "GeometryNodeSampleIndex",
        [
            ("geometry", K_GEO, "Geometry"),
            ("value", K_VAL, "Value"),
            ("index", K_VAL, "Index"),
            ("domain", K_ENUM, ("domain", DOMAINS)),
            ("clamp", K_PROP, "clamp"),
        ],
        ["Value"],
        "value",
    ),
    "sample_nearest": (
        "GeometryNodeSampleNearest",
        [
            ("geometry", K_GEO, "Geometry"),
            ("sample_position", K_VAL, "Sample Position"),
            ("domain", K_ENUM, ("domain", ("POINT", "EDGE", "FACE", "CORNER"))),
        ],
        ["Index"],
        None,
    ),
    "separate_geometry": (
        "GeometryNodeSeparateGeometry",
        [
            ("geometry", K_GEO, "Geometry"),
            ("selection", K_VAL, "Selection"),
            ("domain", K_ENUM, ("domain", DELETE_DOMAINS)),
        ],
        ["Selection", "Inverted"],
        None,
    ),
    "mesh_bevel": (
        "GeometryNodeMeshBevel",
        [
            ("mesh", K_GEO, "Mesh"),
            ("offset", K_VAL, "Offset"),  # Edges mode: fills the four per-side offsets (see Builder)
            ("segments", K_VAL, "Segments"),
            ("selection", K_VAL, "Selection"),
            ("affect", K_MENU, ("Affect Kind", {"VERTICES": "Vertices", "EDGES": "Edges"})),
            ("shape", K_VAL, "Shape"),
            ("profile", K_GEO, "Profile"),
            ("miter", K_VAL, "Miter"),
            ("spread", K_VAL, "Spread"),
            ("start_left_offset", K_VAL, "Start Left Offset"),
            ("start_right_offset", K_VAL, "Start Right Offset"),
            ("end_left_offset", K_VAL, "End Left Offset"),
            ("end_right_offset", K_VAL, "End Right Offset"),
        ],
        ["Mesh", "Vertex Face", "Edge Face", "Outer Edge", "Mid Edge"],
        None,
    ),
    "split_edges": (
        "GeometryNodeSplitEdges",
        [("mesh", K_GEO, "Mesh"), ("selection", K_VAL, "Selection")],
        ["Mesh"],
        None,
    ),
    "merge_by_distance": (
        "GeometryNodeMergeByDistance",
        [
            ("geometry", K_GEO, "Geometry"),
            ("distance", K_VAL, "Distance"),
            ("mode", K_MENU, ("Mode", {"ALL": "All", "CONNECTED": "Connected"})),
            ("selection", K_VAL, "Selection"),
        ],
        ["Geometry"],
        None,
    ),
    "remove_attr": (
        "GeometryNodeRemoveAttribute",
        [
            ("geometry", K_GEO, "Geometry"),
            ("name", K_STR, "Name"),
            (
                "mode",
                K_MENU,
                ("Pattern Mode", {"EXACT": "Exact", "WILDCARD": "Wildcard"}),
            ),
        ],
        ["Geometry"],
        None,
    ),
}


# domain_size(geo, domain) -> (default component, output socket); POINT works for MESH/POINTCLOUD/CURVE
DOMAIN_SIZE = {
    "POINT": ("MESH", "Point Count"),
    "EDGE": ("MESH", "Edge Count"),
    "FACE": ("MESH", "Face Count"),
    "CORNER": ("MESH", "Face Corner Count"),
    "CURVE": ("CURVE", "Spline Count"),
    "INSTANCE": ("INSTANCES", "Instance Count"),
    "LAYER": ("GREASEPENCIL", "Layer Count"),
}


COMPONENTS = ("MESH", "POINTCLOUD", "CURVE", "INSTANCES", "GREASEPENCIL")
COMPONENT_DOMAINS = {
    "MESH": ("POINT", "EDGE", "FACE", "CORNER"),
    "POINTCLOUD": ("POINT",),
    "CURVE": ("POINT", "CURVE"),
    "INSTANCES": ("INSTANCE",),
    "GREASEPENCIL": ("LAYER",),
}


STATS = {
    "mean": "Mean",
    "median": "Median",
    "sum": "Sum",
    "min": "Min",
    "max": "Max",
    "range": "Range",
    "std": "Standard Deviation",
    "standard_deviation": "Standard Deviation",
    "variance": "Variance",
    "var": "Variance",
}


STAT_ORDER = [
    "Mean",
    "Median",
    "Sum",
    "Min",
    "Max",
    "Range",
    "Standard Deviation",
    "Variance",
]


# nodes whose non-geometry outputs are single values (not fields) even though they take geometry
SINGLE_VALUE_GEO_NODES = {
    "GeometryNodeAttributeStatistic",
    "GeometryNodeAttributeDomainSize",
    # inside a for-each zone: the index, the element and the input values are single values
    "GeometryNodeForeachGeometryElementInput",
    "GeometryNodeCurvePrimitiveCircle",  # Center (points mode) is a single value
}


GEO_REQUIRED = {
    "store_attr": {"name", "value"},
    "duplicate": set(),
    "set_cyclic": {"cyclic"},
    "remove_attr": {"name"},
    # the node's default selection is True (= delete everything): make it explicit
    "delete": {"selection"},
    "separate_geometry": {"selection"},  # same reason: an omitted selection means "everything"
    # Sample Index's Index socket defaults to 0, not to the evaluated element's index
    "sample_index": {"value", "index"},
}


GEO_ALIASES = {
    "store_named_attribute": "store_attr",
    "duplicate_elements": "duplicate",
    "points_to_curve": "points_to_curves",
    "set_spline_cyclic": "set_cyclic",
    "extrude_mesh": "extrude",
    "join_geometry": "join",
    "capture_attribute": "capture",
    "attribute_statistic": "attr_stat",
    "attribute_domain_size": "domain_size",
    "remove_named_attribute": "remove_attr",
    "delete_geometry": "delete",
    "remove_attribute": "remove_attr",
}


GEO_FUNCS = (
    set(GEO_OPS)
    | set(GEO_ALIASES)
    | {"join", "capture", "domain_size", "attr_stat", "mesh_boolean", "index_switch", "curve_circle"}
)


BIN_F = {
    ast.Add: "ADD",
    ast.Sub: "SUBTRACT",
    ast.Mult: "MULTIPLY",
    ast.Div: "DIVIDE",
    ast.Pow: "POWER",
    ast.Mod: "FLOORED_MODULO",
}


BIN_V = {
    ast.Add: "ADD",
    ast.Sub: "SUBTRACT",
    ast.Mult: "MULTIPLY",
    ast.Div: "DIVIDE",
    ast.Pow: "POWER",
}


CMP: dict[type[ast.cmpop], str] = {
    ast.Lt: "LESS_THAN",
    ast.Gt: "GREATER_THAN",
    ast.LtE: "LESS_EQUAL",
    ast.GtE: "GREATER_EQUAL",
    ast.Eq: "EQUAL",
    ast.NotEq: "NOT_EQUAL",
}


def fmod_floor(a, b):
    return a - b * math.floor(a / b)


def sign_of(a):
    return (a > 0) - (a < 0)


FOLD = {  # constant folding for scalar Math ops
    "ADD": lambda a, b: a + b,
    "SUBTRACT": lambda a, b: a - b,
    "MULTIPLY": lambda a, b: a * b,
    "DIVIDE": lambda a, b: a / b if b else 0.0,
    "POWER": lambda a, b: a**b,
    "FLOORED_MODULO": lambda a, b: fmod_floor(a, b) if b else 0.0,
    "MINIMUM": min,
    "MAXIMUM": max,
    "ARCTAN2": math.atan2,
    "SINE": math.sin,
    "COSINE": math.cos,
    "TANGENT": math.tan,
    "ARCSINE": math.asin,
    "ARCCOSINE": math.acos,
    "ARCTANGENT": math.atan,
    "SINH": math.sinh,
    "COSH": math.cosh,
    "TANH": math.tanh,
    "SQRT": math.sqrt,
    "EXPONENT": math.exp,
    "ABSOLUTE": abs,
    "FLOOR": math.floor,
    "CEIL": math.ceil,
    "TRUNC": math.trunc,
    "FRACT": lambda a: a - math.floor(a),
    "SIGN": sign_of,
    "RADIANS": math.radians,
    "DEGREES": math.degrees,
    "LOGARITHM": lambda a, b: math.log(a, b),
}


UNARY_F = {
    "sin": "SINE",
    "cos": "COSINE",
    "tan": "TANGENT",
    "asin": "ARCSINE",
    "acos": "ARCCOSINE",
    "atan": "ARCTANGENT",
    "sinh": "SINH",
    "cosh": "COSH",
    "tanh": "TANH",
    "sqrt": "SQRT",
    "inversesqrt": "INVERSE_SQRT",
    "exp": "EXPONENT",
    "abs": "ABSOLUTE",
    "floor": "FLOOR",
    "ceil": "CEIL",
    "round": "ROUND",
    "trunc": "TRUNC",
    "fract": "FRACT",
    "sign": "SIGN",
    "radians": "RADIANS",
    "degrees": "DEGREES",
}


UNARY_V = {
    "sin": "SINE",
    "cos": "COSINE",
    "tan": "TANGENT",
    "abs": "ABSOLUTE",
    "floor": "FLOOR",
    "ceil": "CEIL",
    "round": "ROUND",
    "fract": "FRACTION",
    "sign": "SIGN",
    "normalize": "NORMALIZE",
}


BINARY_F = {
    "atan2": "ARCTAN2",
    "pow": "POWER",
    "min": "MINIMUM",
    "max": "MAXIMUM",
    "fmod": "MODULO",
    "mod": "FLOORED_MODULO",
    "snap": "SNAP",
    "pingpong": "PINGPONG",
    "wrap": None,
}


BINARY_V = {
    "min": "MINIMUM",
    "max": "MAXIMUM",
    "cross": "CROSS_PRODUCT",
    "project": "PROJECT",
    "reflect": "REFLECT",
    "snap": "SNAP",
    "pow": "POWER",
}


BUILTIN_NAMES = (
    set(UNARY_F)
    | set(UNARY_V)
    | set(BINARY_F)
    | set(BINARY_V)
    | {
        "vec",
        "Vector",
        "vec3",
        "float",
        "int",
        "bool",
        "length",
        "dot",
        "distance",
        "log",
        "lerp",
        "mix",
        "clamp",
        "wrap",
        "at_index",
        "on_domain",
        "attr",
        "attr_exists",
    }
    | set(TUPLE_FIELDS)
    | GEO_FUNCS
)
