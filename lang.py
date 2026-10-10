"""py2gn language: every built-in, for editor support.

Import it under an alias at the top of a function file::

    import py2gn.lang as gn

    def offset(mesh: gn.tGeometry, k: float = 0.1) -> gn.tGeometry:
        return gn.SetPosition(mesh, offset=gn.Normal * k)

Conventions
-----------
* Built-ins are only reachable through the alias (``gn.X``); bare names are always yours
  (parameters, locals, functions of the file, node groups of the .blend).
* Nodes, fields and functions are PascalCase after Blender's node names:
  ``gn.JoinGeometry``, ``gn.Position``, ``gn.EvaluateAtIndex``; math keeps conventional
  names: ``gn.Sin``, ``gn.Clamp``, ``gn.Dot``.
* Socket types are ``t``-prefixed: ``gn.tFloat``, ``gn.tInt``, ``gn.tBool``, ``gn.tVec``,
  ``gn.tGeometry``. Python's ``float``, ``int``, ``bool`` work as annotations too.
* Keyword arguments are snake_case (``selection=``, ``domain=``), option strings uppercase
  (``domain="FACE"``).

The compiler only reads the import line; nothing here runs in Blender. Bodies are ``...``.
"""

from __future__ import annotations

from collections.abc import Callable as _Callable
from collections.abc import Iterator as _Iterator
from typing import Any as _Any
from typing import Literal as _Literal
from typing import NamedTuple as _NamedTuple
from typing import overload as _overload

_Number = float | int | bool
_Domain = _Literal["POINT", "EDGE", "FACE", "CORNER", "CURVE", "INSTANCE", "LAYER"]
_DuplicateDomain = _Literal["POINT", "EDGE", "FACE", "SPLINE", "LAYER", "INSTANCE"]
_DeleteDomain = _Literal["POINT", "EDGE", "FACE", "CURVE", "INSTANCE", "LAYER"]
_Component = _Literal["MESH", "POINTCLOUD", "CURVE", "INSTANCES", "GREASEPENCIL"]
_Stat = _Literal[
    "mean",
    "median",
    "sum",
    "min",
    "max",
    "range",
    "std",
    "standard_deviation",
    "variance",
    "var",
]


# ========================================================== multi-output results
# Nodes with several outputs return these: unpack them (``c, total = ...``) or pick one by
# name (``gn.FaceOfCorner(c).FaceIndex``).
class _CornerQuery(_NamedTuple):
    CornerIndex: int
    Total: int


class _EdgesOfVertex(_NamedTuple):
    EdgeIndex: int
    Total: int


class _FaceOfCorner(_NamedTuple):
    FaceIndex: int
    IndexInFace: int


class _EdgesOfCorner(_NamedTuple):
    NextEdgeIndex: int
    PreviousEdgeIndex: int


class _ExtrudeResult(_NamedTuple):
    Mesh: tGeometry
    Top: bool
    Side: bool


class _DuplicateResult(_NamedTuple):
    Geometry: tGeometry
    DuplicateIndex: int


class _GridResult(_NamedTuple):
    Mesh: tGeometry
    UVMap: tVec


class _SeparateResult(_NamedTuple):
    Selection: tGeometry
    Inverted: tGeometry


class _BevelResult(_NamedTuple):
    Mesh: tGeometry
    VertexFace: bool
    EdgeFace: bool
    OuterEdge: bool
    MidEdge: bool


class _CurveCircleResult(_NamedTuple):
    Curve: tGeometry
    Center: tVec


class _BooleanResult(_NamedTuple):
    Mesh: tGeometry
    IntersectingEdges: bool


# ===================================================================== types
class tVec:
    """3D vector socket type; ``gn.tVec(x, y, z)`` / ``gn.tVec(s)`` build one (Combine XYZ).

    ``a * s`` scales, ``a * b`` and ``a / b`` are component-wise, ``a @ b`` is the dot product,
    ``v.x / v.y / v.z`` read components (Separate XYZ).
    """

    x: float
    y: float
    z: float

    @_overload
    def __init__(self, s: _Number, /) -> None: ...
    @_overload
    def __init__(self, x: _Number, y: _Number, z: _Number, /) -> None: ...
    def __init__(self, *args: _Number) -> None: ...

    def __add__(self, other: tVec | _Number) -> tVec: ...
    def __radd__(self, other: tVec | _Number) -> tVec: ...
    def __sub__(self, other: tVec | _Number) -> tVec: ...
    def __rsub__(self, other: tVec | _Number) -> tVec: ...
    def __mul__(self, other: tVec | _Number) -> tVec: ...
    def __rmul__(self, other: tVec | _Number) -> tVec: ...
    def __truediv__(self, other: tVec | _Number) -> tVec: ...
    def __rtruediv__(self, other: tVec | _Number) -> tVec: ...
    def __floordiv__(self, other: tVec | _Number) -> tVec: ...
    def __mod__(self, other: tVec | _Number) -> tVec: ...
    def __pow__(self, other: tVec | _Number) -> tVec: ...
    def __matmul__(self, other: tVec) -> float: ...
    def __neg__(self) -> tVec: ...
    def __pos__(self) -> tVec: ...


class tGeometry:
    """Geometry socket type (mesh, curves, point cloud, instances...).

    Geometry operations return a *new* geometry value; rebind the variable:
    ``mesh = gn.SetPosition(mesh, offset=gn.Normal * 0.1)``.
    """


tFloat = float
"""Float socket type (same as ``float``); ``gn.tFloat(x)`` is a cast."""
tInt = int
"""Integer socket type (same as ``int``); ``gn.tInt(x)`` truncates."""
tBool = bool
"""Boolean socket type (same as ``bool``); ``gn.tBool(x)`` is ``x != 0``."""


_Subtype = _Literal[
    "NONE", "PIXEL", "PERCENTAGE", "FACTOR",
    # float only
    "MASS", "ANGLE", "TIME", "TIME_ABSOLUTE", "DISTANCE", "WAVELENGTH", "COLOR_TEMPERATURE", "FREQUENCY",
    # vector only
    "TRANSLATION", "DIRECTION", "VELOCITY", "ACCELERATION", "EULER", "XYZ",
]  # fmt: skip


@_overload
def Param[T](
    default: T,
    /,
    *,
    min: float | None = None,
    max: float | None = None,
    description: str = "",
    subtype: _Subtype | None = None,
) -> T: ...
@_overload
def Param(
    *,
    min: float | None = None,
    max: float | None = None,
    description: str = "",
    subtype: _Subtype | None = None,
) -> _Any: ...
def Param(default: _Any = None, /, **options: _Any) -> _Any:
    """Group-input settings, written as the parameter's default::

        def Wall(
            Height: float = gn.Param(2.0, min=0, max=10, subtype="DISTANCE", description="Wall height"),
            Dir: gn.tVec = gn.Param(gn.tVec(0, 0, 1), subtype="DIRECTION"),
            Count: int = gn.Param(4, min=1),
        ): ...

    ``min`` / ``max`` apply to float, int and vector inputs (vectors: per component); ``subtype``
    to float (``FACTOR``, ``ANGLE``, ``DISTANCE``, ``TIME``...), int (``FACTOR``, ``PERCENTAGE``...)
    and vector inputs (``TRANSLATION``, ``DIRECTION``, ``EULER``, ``XYZ``...); ``description`` is the
    tooltip, for any input. Options left out are reset on recompile -- the source is the truth.
    """
    ...


class _ForEachElement[*Ts]:
    """A For Each Geometry Element zone; see :func:`ForEachElement`."""

    Geometry: tGeometry
    """The iterated geometry (the per-element results are fields on it)."""
    Generated: tGeometry
    """Everything passed to ``generate()``, joined over all elements."""

    def __iter__(self) -> _Iterator[tuple[int, tGeometry, *Ts]]: ...
    def result(self, **values: _Any) -> None:
        """Per-element outputs; after the loop ``each.<name>`` is a field on ``each.Geometry``."""
        ...

    def generate(self, geometry: tGeometry, **fields: _Any) -> None:
        """Geometry made for this element (joined into ``each.Generated``); ``fields`` live on it."""
        ...

    def __getattr__(self, name: str) -> _Any: ...


def ForEachElement[*Ts](
    geometry: tGeometry, *values: *Ts, domain: _Domain = "POINT", selection: bool | None = None
) -> _ForEachElement[*Ts]:
    """A loop over the elements of ``geometry`` (one For Each Geometry Element zone)::

        each = gn.ForEachElement(mesh, gn.Position, domain="FACE")
        for i, element, center in each:          # index, the element's geometry, the values
            each.result(height=center.z * 2)     # per element -> a field after the loop
            each.generate(gn.SetPosition(gn.MeshCircle(6, radius=0.1), offset=center), source=i)
        mesh = gn.StoreNamedAttribute(each.Geometry, "h", each.height, domain="FACE")
        dots = each.Generated

    ``values`` are fields evaluated on ``domain``; inside the body they (and the index) are single
    values. Iterations are independent: nothing assigned in the body carries over -- use
    ``result``/``generate`` (at the top level of the body). Each zone can be iterated once.
    """
    ...


def Repeat(iterations: _Number) -> range:
    """A loop built as one Repeat zone (instead of unrolling)::

        x = gn.Position.x
        for i in gn.Repeat(n):        # n may be computed by nodes, e.g. gn.DomainSize(mesh)
            x = x * 2 + i             # i: the iteration index

    Variables assigned in the body that exist before the loop are the zone's state (fields, values
    or geometry) and hold the final values afterwards; their type is fixed by the value before the
    loop. Others are local to the body. ``iterations`` must be a single value, not a field.
    A plain ``for i in range(n)`` with a compile-time ``n`` is unrolled instead.
    """
    ...


def Outputs(**values: _Any) -> _Any:
    """Named outputs.

    In the return statement (valid for every type checker)::

        return gn.Outputs(radius=r, angle=a)

    or as the return annotation, to fix the socket types::

        def f(p: gn.tVec) -> gn.Outputs(radius=float, angle=float): ...
    """
    ...


def inline[**P, R](fn: _Callable[P, R]) -> _Callable[P, R]:
    """Decorator: expand the function at every call instead of creating a node group.

    ::

        @gn.inline
        def lerp(a, b, t: float = 0.5):
            return a + (b - a) * t

    No group named ``lerp`` is made; each call puts the nodes into the calling function.
    Parameters without annotation accept any value, so one inline function works for floats
    and vectors alike; ``gn.tVec`` promotes scalars, ``gn.tGeometry`` requires geometry.
    Inline functions may call each other (not recursively) and be defined anywhere in the file;
    they are only checked when called.
    """
    return fn


# ================================================================ constants
Pi: float = 3.141592653589793
Tau: float = 6.283185307179586
E: float = 2.718281828459045

# =================================================================== fields
# Fields are evaluated on the geometry (and domain) of the node that consumes them.
Position: tVec
"""Position node."""
Normal: tVec
"""Normal node."""
CurveTangent: tVec
"""Curve Tangent node."""
Index: int
"""Index node."""
ID: int
"""ID node (stable id)."""
Radius: float
"""Radius node."""
IsSplineCyclic: bool
"""Is Spline Cyclic node."""
SplineParameterFactor: float
"""Spline Parameter > Factor: 0..1 along the spline (by length)."""
SplineParameterLength: float
"""Spline Parameter > Length: arc length from the spline start."""
SplineParameterIndex: int
"""Spline Parameter > Index: point index within its spline."""
EdgeNeighbors: int
"""Edge Neighbors > Face Count (edge domain): how many faces use the edge -- 1 on a boundary,
2 inside a manifold surface, 0 for a loose edge."""
EdgeVerticesVertexIndex1: int
"""Edge Vertices > Vertex Index 1 (edge domain)."""
EdgeVerticesVertexIndex2: int
"""Edge Vertices > Vertex Index 2 (edge domain)."""
EdgeVerticesPosition1: tVec
"""Edge Vertices > Position 1 (edge domain)."""
EdgeVerticesPosition2: tVec
"""Edge Vertices > Position 2 (edge domain)."""
SceneTimeSeconds: float
"""Scene Time > Seconds (single value)."""
SceneTimeFrame: float
"""Scene Time > Frame (single value)."""


def SplineParameter() -> tuple[float, float, int]:
    """Spline Parameter node: ``factor, length, index = gn.SplineParameter()``."""
    ...


def EdgeVertices() -> tuple[int, int, tVec, tVec]:
    """Edge Vertices node: ``v1, v2, p1, p2 = gn.EdgeVertices()``.

    Edge-domain fields: use them on the edge domain, e.g.
    ``gn.StoreNamedAttribute(mesh, "len", gn.Length(p2 - p1), domain="EDGE")``;
    read on points they are averaged over the connected edges.
    """
    ...


def SceneTime() -> tuple[float, float]:
    """Scene Time node: ``seconds, frame = gn.SceneTime()``."""
    ...


# ==================================================== field evaluation / attributes
def EvaluateAtIndex[T: (float, int, bool, tVec)](value: T, index: _Number, domain: _Domain = "POINT") -> T:
    """Evaluate at Index: ``value`` (and every field inside it) evaluated at another index.

    Out-of-range indices give zero / False.
    """
    ...


def EvaluateOnDomain[T: (float, int, bool, tVec)](value: T, domain: _Domain = "POINT") -> T:
    """Evaluate on Domain: compute ``value`` on ``domain``, interpolate to the current one."""
    ...


@_overload
def NamedAttribute(name: str, /) -> float: ...
@_overload
def NamedAttribute[T: (float, int, bool, tVec)](name: str, /, type: type[T]) -> T: ...
def NamedAttribute(name: str, /, type: _Any = float) -> _Any:
    """Named Attribute > Attribute (name must be a string literal; missing reads as 0 / False).

    ``gn.NamedAttribute("weight")``, ``gn.NamedAttribute("dir", gn.tVec)``.
    """
    ...


def NamedAttributeExists(name: str, /) -> bool:
    """Named Attribute > Exists."""
    ...


# ================================================================= geometry
def SetPosition(
    geometry: tGeometry,
    position: tVec | None = None,
    offset: tVec | None = None,
    selection: bool | None = None,
) -> tGeometry:
    """Set Position. Omitted arguments keep the node defaults (implicit position, zero offset)."""
    ...


def StoreNamedAttribute(
    geometry: tGeometry,
    name: str,
    value: float | bool | tVec,
    domain: _Domain = "POINT",
    selection: bool | None = None,
) -> tGeometry:
    """Store Named Attribute; the data type follows ``value``."""
    ...


def RemoveNamedAttribute(
    geometry: tGeometry, name: str, mode: _Literal["EXACT", "WILDCARD"] = "EXACT"
) -> tGeometry:
    """Remove Named Attribute (name must be a string literal).

    ``gn.RemoveNamedAttribute(g, "TEMP_*", mode="WILDCARD")`` removes every match.
    """
    ...


def JoinGeometry(*geometries: tGeometry) -> tGeometry:
    """Join Geometry, in argument order."""
    ...


def DeleteGeometry(
    geometry: tGeometry,
    selection: bool,
    domain: _DeleteDomain = "POINT",
    mode: _Literal["ALL", "EDGE_FACE", "ONLY_FACE"] = "ALL",
) -> tGeometry:
    """Delete Geometry: remove the elements of ``domain`` where ``selection`` is true.

    ``selection`` is evaluated on ``domain``. For meshes, ``mode`` picks what goes with a deleted
    edge/face: ``ALL`` also removes unused vertices/edges, ``EDGE_FACE`` keeps the vertices,
    ``ONLY_FACE`` removes just the faces.
    """
    ...


def SeparateGeometry(
    geometry: tGeometry, selection: bool, domain: _DeleteDomain = "POINT"
) -> _SeparateResult:
    """Separate Geometry -> ``(Selection, Inverted)``: the selected elements of ``domain`` and the rest.

    ``picked, rest = gn.SeparateGeometry(mesh, gn.Position.x < 1, domain="FACE")``. The selection is
    evaluated on ``domain``; it is required (Blender's default would select everything).
    """
    ...


def SplitEdges(mesh: tGeometry, selection: bool | None = None) -> tGeometry:
    """Split Edges: duplicate the vertices along the selected edges so faces there no longer share them.

    ``selection`` is evaluated on the edge domain (``gn.Position`` = edge midpoint); omitted = all edges,
    which separates every face.
    """
    ...


def MeshBevel(
    mesh: tGeometry,
    offset: float | None = None,
    segments: _Number | None = None,
    selection: bool | None = None,
    affect: _Literal["EDGES", "VERTICES"] = "EDGES",
    shape: float | None = None,
    profile: tGeometry | None = None,
    miter: bool | None = None,
    spread: float | None = None,
    start_left_offset: float | None = None,
    start_right_offset: float | None = None,
    end_left_offset: float | None = None,
    end_right_offset: float | None = None,
) -> _BevelResult:
    """Mesh Bevel -> ``(Mesh, VertexFace, EdgeFace, OuterEdge, MidEdge)``.

    ``offset`` is the bevel width in both modes; with ``affect="EDGES"`` (default) it sets all four
    per-side offsets, which ``start_left_offset`` ... ``end_right_offset`` override individually.
    ``miter`` / ``spread`` (spread needs ``miter=True``) and the per-side offsets are Edges-only.
    ``shape`` and ``profile`` (a curve) matter with ``segments`` > 1. The selection is evaluated on
    edges or vertices; the other outputs select the faces / edges the bevel created.
    """
    ...


@_overload
def MeshBoolean(
    *meshes: tGeometry,
    operation: _Literal["INTERSECT", "UNION", "DIFFERENCE"] = "DIFFERENCE",
    solver: _Literal["FLOAT"] = "FLOAT",
) -> tGeometry: ...
@_overload
def MeshBoolean(
    *meshes: tGeometry,
    operation: _Literal["INTERSECT", "UNION", "DIFFERENCE"] = "DIFFERENCE",
    solver: _Literal["MANIFOLD"],
) -> _BooleanResult: ...
@_overload
def MeshBoolean(
    *meshes: tGeometry,
    operation: _Literal["INTERSECT", "UNION", "DIFFERENCE"] = "DIFFERENCE",
    solver: _Literal["EXACT"],
    self_intersection: bool = False,
    hole_tolerant: bool = False,
) -> _BooleanResult: ...
def MeshBoolean(
    *meshes: tGeometry,
    operation: _Any = "DIFFERENCE",
    solver: _Any = "FLOAT",
    **flags: _Any,
) -> _Any:
    """Mesh Boolean.

    ``DIFFERENCE``: the first mesh minus all the others; ``UNION`` / ``INTERSECT``: all meshes.
    The ``FLOAT`` solver (node default) returns the mesh; ``EXACT`` and ``MANIFOLD`` also return
    the intersecting-edges field (edge domain): ``mesh, edges = gn.MeshBoolean(a, b, solver="EXACT")``.
    ``self_intersection`` / ``hole_tolerant`` exist only for ``EXACT``.
    ``FLOAT`` is fast but fails on coplanar overlapping faces (e.g. two boxes sharing a face
    plane); use ``EXACT`` or ``MANIFOLD`` (closed manifold input) there.
    """
    ...


def MeshCircle(
    vertices: _Number = 32,
    radius: float = 1.0,
    fill: _Literal["NONE", "NGON", "TRIANGLE_FAN"] = "NONE",
) -> tGeometry:
    """Mesh Circle primitive (XY plane, centred at the origin)."""
    ...


def BezierSegment(
    start: tVec | None = None,
    start_handle: tVec | None = None,
    end_handle: tVec | None = None,
    end: tVec | None = None,
    resolution: _Number = 16,
    mode: _Literal["POSITION", "OFFSET"] = "POSITION",
) -> tGeometry:
    """Bezier Segment: a cubic Bezier curve with two control points.

    ``mode="OFFSET"``: each handle is an offset from its own endpoint. Omitted points keep the node's
    defaults (start (-1, 0, 0), end (1, 0, 0), start handle (-0.5, 0.5, 0), end handle (0, 0, 0)).
    ``resolution`` (evaluated points per segment) comes last, unlike in the node.
    """
    ...


@_overload
def CurveCircle(radius: float = 1.0, resolution: _Number = 32) -> tGeometry: ...
@_overload
def CurveCircle(point1: tVec, point2: tVec, point3: tVec, resolution: _Number = 32) -> _CurveCircleResult: ...
def CurveCircle(*args: _Any, **kwargs: _Any) -> _Any:
    """Curve Circle: a cyclic curve with ``resolution`` points (XY plane).

    ``gn.CurveCircle(radius=2.0)`` -> the curve; ``gn.CurveCircle(p1, p2, p3)`` -> the circle through
    three points and its centre: ``curve, center = ...``. The mode follows the arguments.
    """
    ...


def QuadraticBezier(
    start: tVec | None = None, middle: tVec | None = None, end: tVec | None = None, resolution: _Number = 16
) -> tGeometry:
    """Quadratic Bezier: a poly curve with ``resolution + 1`` points from start, through the pull of
    ``middle``, to end. Defaults: (-1, 0, 0), (0, 2, 0), (1, 0, 0)."""
    ...


def Grid(
    size_x: float = 1.0, size_y: float = 1.0, vertices_x: _Number = 3, vertices_y: _Number = 3
) -> _GridResult:
    """Grid primitive (XY plane, centred at the origin) -> ``(Mesh, UVMap)``.

    ``mesh, uv = gn.Grid(2, 1, 5, 3)`` or ``gn.Grid(...).Mesh``. ``UVMap`` is a face-corner field
    on the grid. Fewer than 2 vertices along an axis gives an empty mesh (Blender's behaviour).
    """
    ...


def InstanceOnPoints(
    points: tGeometry,
    instance: tGeometry | None = None,
    selection: bool | None = None,
    rotation: tVec | None = None,
    scale: tVec | float | None = None,
    pick_instance: bool = False,
    instance_index: _Number | None = None,
) -> tGeometry:
    """Instance on Points. ``rotation`` is an Euler XYZ vector in radians (converted to a rotation)."""
    ...


def RealizeInstances(
    geometry: tGeometry,
    selection: bool | None = None,
    realize_all: bool = True,
    depth: _Number = 0,
) -> tGeometry:
    """Realize Instances."""
    ...


@_overload
def IndexSwitch(index: _Number, /, *values: tGeometry) -> tGeometry: ...
@_overload
def IndexSwitch[T: (float, int, bool, tVec)](index: _Number, /, *values: T) -> T: ...
def IndexSwitch(index: _Number, /, *values: _Any) -> _Any:
    """Index Switch: ``values[index]`` (out of range gives the type's default).

    Works for numbers, vectors and geometry; over geometry the index must be a single value.
    """
    ...


# ------------------------------------------------------------ mesh topology
# Field functions; omitted index inputs default to the element being evaluated.
def CornersOfVertex(
    vertex_index: _Number | None = None,
    weights: float | None = None,
    sort_index: _Number = 0,
) -> _CornerQuery:
    """Corners of Vertex: the ``sort_index``-th corner around the vertex (ordered by ``weights``) and the total."""
    ...


def CornersOfEdge(
    edge_index: _Number | None = None,
    weights: float | None = None,
    sort_index: _Number = 0,
) -> _CornerQuery:
    """Corners of Edge: corners of the faces using the edge, ordered by ``weights``, and the total."""
    ...


def CornersOfFace(
    face_index: _Number | None = None,
    weights: float | None = None,
    sort_index: _Number = 0,
) -> _CornerQuery:
    """Corners of Face: the ``sort_index``-th corner of the face (ordered by ``weights``) and the total."""
    ...


def EdgesOfVertex(
    vertex_index: _Number | None = None, weights: float | None = None, sort_index: _Number = 0
) -> _EdgesOfVertex:
    """Edges of Vertex: the ``sort_index``-th edge at the vertex (ordered by ``weights``, evaluated on
    edges) and the number of edges there."""
    ...


def SampleIndex[T: (float, int, bool, tVec)](
    geometry: tGeometry, value: T, index: _Number, domain: _Domain = "POINT", clamp: bool = False
) -> T:
    """Sample Index: ``value`` evaluated on ``geometry`` (not the current geometry!) at ``index``.

    ``index`` is required (the node's default is 0, not the current index). Out-of-range indices
    give zero / False unless ``clamp=True`` (a compile-time option). Typical:
    ``gn.SampleIndex(target, gn.Position, gn.SampleNearest(target, gn.Position))``.
    """
    ...


def SampleNearest(
    geometry: tGeometry,
    sample_position: tVec | None = None,
    domain: _Literal["POINT", "EDGE", "FACE", "CORNER"] = "POINT",
) -> int:
    """Sample Nearest: index of the element of ``geometry`` closest to ``sample_position``
    (default: the position of the element being evaluated)."""
    ...


def FaceOfCorner(corner_index: _Number | None = None) -> _FaceOfCorner:
    """Face of Corner: the face a corner belongs to, and its position in that face."""
    ...


def VertexOfCorner(corner_index: _Number | None = None) -> int:
    """Vertex of Corner."""
    ...


def EdgesOfCorner(corner_index: _Number | None = None) -> _EdgesOfCorner:
    """Edges of Corner: the next and previous edge around the corner's face."""
    ...


def OffsetCornerInFace(corner_index: _Number | None = None, offset: _Number = 0) -> int:
    """Offset Corner in Face: the corner ``offset`` steps further around the same face."""
    ...


def MergeByDistance(
    geometry: tGeometry,
    distance: float = 0.001,
    mode: _Literal["ALL", "CONNECTED"] = "ALL",
    selection: bool | None = None,
) -> tGeometry:
    """Merge by Distance. ``CONNECTED`` only merges vertices joined by an edge.

    ``distance`` must be a single value (not a field); use ``selection`` for per-element control.
    """
    ...


def DuplicateElements(
    geometry: tGeometry,
    amount: _Number = 1,
    domain: _DuplicateDomain = "POINT",
    selection: bool | None = None,
) -> _DuplicateResult:
    """Duplicate Elements -> ``(geometry, duplicate_index)``."""
    ...


def CaptureAttribute[*Ts](
    geometry: tGeometry, *values: *Ts, domain: _Domain = "POINT"
) -> tuple[tGeometry, *Ts]:
    """Capture Attribute: freeze field values on ``geometry``.

    ``mesh, p0 = gn.CaptureAttribute(mesh, gn.Position)`` -- ``p0`` keeps the pre-edit positions.
    """
    ...


def PointsToCurves(points: tGeometry, group_id: _Number = 0, weight: float = 0.0) -> tGeometry:
    """Points to Curves."""
    ...


def SetSplineCyclic(curve: tGeometry, cyclic: bool, selection: bool | None = None) -> tGeometry:
    """Set Spline Cyclic."""
    ...


def ResampleCurve(
    curve: tGeometry,
    count: _Number | None = None,
    length: float | None = None,
    mode: _Literal["EVALUATED", "COUNT", "LENGTH"] | None = None,
    selection: bool | None = None,
) -> tGeometry:
    """Resample Curve. The mode follows the arguments: ``count=`` (or nothing) -> COUNT points per spline,
    ``length=`` -> segments of that length; ``mode="EVALUATED"`` uses the evaluated points.
    ``count`` and ``length`` can be fields (evaluated per spline).
    """
    ...


def ReverseCurve(curve: tGeometry, selection: bool | None = None) -> tGeometry:
    """Reverse Curve."""
    ...


def CurveToMesh(
    curve: tGeometry,
    profile: tGeometry | None = None,
    scale: float = 1.0,
    fill_caps: bool = False,
) -> tGeometry:
    """Curve to Mesh. ``fill_caps`` must be a single value."""
    ...


def MeshToCurve(
    mesh: tGeometry,
    selection: bool | None = None,
    mode: _Literal["EDGES", "FACES"] = "EDGES",
) -> tGeometry:
    """Mesh to Curve."""
    ...


def MeshToPoints(
    mesh: tGeometry,
    selection: bool | None = None,
    position: tVec | None = None,
    radius: float | None = None,
    mode: _Literal["VERTICES", "EDGES", "FACES", "CORNERS"] = "VERTICES",
) -> tGeometry:
    """Mesh to Points: one point per vertex / edge / face / corner (a point cloud).

    Fields passed in are evaluated on the chosen domain (face centre, face index, ...).
    """
    ...


def ExtrudeMesh(
    mesh: tGeometry,
    offset: tVec | None = None,
    scale: float = 1.0,
    mode: _Literal["VERTICES", "EDGES", "FACES"] = "FACES",
    individual: bool = True,
    selection: bool | None = None,
) -> _ExtrudeResult:
    """Extrude Mesh -> ``(mesh, top, side)``. Omitted ``offset`` = the node's implicit normal."""
    ...


def FlipFaces(mesh: tGeometry, selection: bool | None = None) -> tGeometry:
    """Flip Faces."""
    ...


def DomainSize(geometry: tGeometry, domain: _Domain = "POINT", component: _Component | None = None) -> int:
    """Domain Size (single value). The component follows from ``domain``; POINT defaults to MESH."""
    ...


@_overload
def AttributeStatistic[F: (float, tVec)](
    geometry: tGeometry,
    value: F,
    stat: _Stat,
    domain: _Domain = "POINT",
    selection: bool | None = None,
) -> F: ...
@_overload
def AttributeStatistic[F: (float, tVec)](
    geometry: tGeometry,
    value: F,
    stat: None = None,
    domain: _Domain = "POINT",
    selection: bool | None = None,
) -> tuple[F, F, F, F, F, F, F, F]: ...
def AttributeStatistic(
    geometry: tGeometry,
    value: _Any,
    stat: _Any = None,
    domain: _Domain = "POINT",
    selection: _Any = None,
) -> _Any:
    """Attribute Statistic (single values).

    With ``stat`` -> that statistic; without -> ``(mean, median, sum, min, max, range, std, variance)``.
    Standard deviation / variance are population statistics (divide by N).
    """
    ...


# ===================================================================== math
# Scalar functions; those typed F also accept vectors (component-wise Vector Math).
def Sin[F: (float, tVec)](x: F, /) -> F: ...
def Cos[F: (float, tVec)](x: F, /) -> F: ...
def Tan[F: (float, tVec)](x: F, /) -> F: ...
def Asin(x: float, /) -> float: ...
def Acos(x: float, /) -> float: ...
def Atan(x: float, /) -> float: ...
def Atan2(y: float, x: float, /) -> float: ...
def Sinh(x: float, /) -> float: ...
def Cosh(x: float, /) -> float: ...
def Tanh(x: float, /) -> float: ...
def Sqrt(x: float, /) -> float: ...
def InverseSqrt(x: float, /) -> float: ...
def Exp(x: float, /) -> float: ...
def Log(x: float, base: float = E, /) -> float:
    """Logarithm; natural log unless ``base`` is given."""
    ...


def Abs[F: (float, tVec)](x: F, /) -> F: ...
def Floor[F: (float, tVec)](x: F, /) -> F: ...
def Ceil[F: (float, tVec)](x: F, /) -> F: ...
def Round[F: (float, tVec)](x: F, /) -> F: ...
def Trunc(x: float, /) -> float: ...
def Fract[F: (float, tVec)](x: F, /) -> F: ...
def Sign[F: (float, tVec)](x: F, /) -> F: ...
def Radians(x: float, /) -> float: ...
def Degrees(x: float, /) -> float: ...
def Pow[F: (float, tVec)](x: F, y: F | float, /) -> F: ...
def FMod(x: float, y: float, /) -> float:
    """Truncated modulo (C ``fmod``). Python's ``%`` is floored."""
    ...


def Mod(x: float, y: float, /) -> float:
    """Floored modulo, same as ``x % y``."""
    ...


def Snap[F: (float, tVec)](x: F, step: F, /) -> F: ...
def PingPong(x: float, scale: float, /) -> float: ...
def Wrap[F: (float, tVec)](x: F, lo: F | float, hi: F | float, /) -> F: ...


@_overload
def Min(a: float, b: float, /, *rest: float) -> float: ...
@_overload
def Min(a: tVec, b: tVec | float, /, *rest: tVec | float) -> tVec: ...
def Min(a: _Any, b: _Any, /, *rest: _Any) -> _Any: ...


@_overload
def Max(a: float, b: float, /, *rest: float) -> float: ...
@_overload
def Max(a: tVec, b: tVec | float, /, *rest: tVec | float) -> tVec: ...
def Max(a: _Any, b: _Any, /, *rest: _Any) -> _Any: ...


def Clamp[F: (float, tVec)](x: F, lo: F | float = 0.0, hi: F | float = 1.0, /) -> F:
    """Clamp to [lo, hi] (Clamp node for scalars, Min/Max for vectors)."""
    ...


def Mix[F: (float, tVec)](a: F, b: F, t: float, /) -> F:
    """Linear interpolation ``a + (b - a) * t``."""
    ...


def Length(v: tVec, /) -> float: ...
def Dot(a: tVec, b: tVec, /) -> float: ...
def Cross(a: tVec, b: tVec, /) -> tVec: ...
def Normalize(v: tVec, /) -> tVec: ...
def Distance(a: tVec, b: tVec, /) -> float: ...
def Project(a: tVec, b: tVec, /) -> tVec: ...
def Reflect(a: tVec, n: tVec, /) -> tVec: ...
