"""Value types of the language and the compile-time value representation."""

from __future__ import annotations

import ast
from typing import Any

from .errors import GNCompileError
from .names import DEFAULT_ALIAS, OLD_NAMES, TYPES, namespace_member

FLOAT, INT, BOOL, VEC, GEO = "FLOAT", "INT", "BOOL", "VECTOR", "GEOMETRY"


IFACE_SOCKET = {
    FLOAT: "NodeSocketFloat",
    INT: "NodeSocketInt",
    BOOL: "NodeSocketBool",
    VEC: "NodeSocketVector",
    GEO: "NodeSocketGeometry",
}


FROM_SOCKTYPE = {
    "VALUE": FLOAT,
    "INT": INT,
    "BOOLEAN": BOOL,
    "VECTOR": VEC,
    "GEOMETRY": GEO,
}


PYTHON_TYPES = {"float": FLOAT, "int": INT, "bool": BOOL}


# Interface-socket subtypes (Blender 5.2) and the "no limit" values of min/max
_COMMON_SUBTYPES = ("NONE", "PIXEL", "PERCENTAGE", "FACTOR")
SUBTYPES = {
    FLOAT: (
        *_COMMON_SUBTYPES,
        "MASS",
        "ANGLE",
        "TIME",
        "TIME_ABSOLUTE",
        "DISTANCE",
        "WAVELENGTH",
        "COLOR_TEMPERATURE",
        "FREQUENCY",
    ),
    INT: _COMMON_SUBTYPES,
    VEC: (*_COMMON_SUBTYPES, "TRANSLATION", "DIRECTION", "VELOCITY", "ACCELERATION", "EULER", "XYZ"),
}
_FLT_MAX = 3.4028234663852886e38
LIMITS = {FLOAT: (-_FLT_MAX, _FLT_MAX), VEC: (-_FLT_MAX, _FLT_MAX), INT: (-(2**31), 2**31 - 1)}


class Val:
    """A compile-time value: either a Python constant or a node output socket."""

    __slots__ = ("const", "depth", "node", "sock", "type")

    type: str
    sock: Any  # bpy.types.NodeSocket | None
    const: Any  # float | bool | tuple[float, float, float] | None
    depth: int
    node: Any  # bpy.types.Node | None

    def __init__(
        self,
        type: str,
        sock: Any = None,
        const: Any = None,
        depth: int = 0,
        node: Any = None,
    ):
        self.type, self.sock, self.const, self.depth, self.node = (
            type,
            sock,
            const,
            depth,
            node,
        )

    @property
    def is_const(self):
        return self.sock is None


class NamedVals(tuple):
    """Several outputs of one node: unpack them, or pick one by name (``.FaceIndex``)."""

    names: tuple[str, ...]
    label: str

    def __new__(cls, vals, names, label):
        obj = super().__new__(cls, vals)
        obj.names = tuple(names)
        obj.label = label
        return obj


class Closure:
    """A nested ``def`` or ``lambda``: expanded inline at each call, seeing its enclosing scope."""

    __slots__ = ("env", "name", "node")

    def __init__(self, node, env: dict, name: str):
        self.node, self.env, self.name = node, env, name


def output_name(socket_name: str) -> str:
    """Blender output socket name -> attribute name: "Index in Face" -> "IndexInFace"."""
    return "".join(w[:1].upper() + w[1:] for w in socket_name.split())


def cval(x):
    if isinstance(x, bool):
        return Val(BOOL, const=x)
    if isinstance(x, (int, float)):
        return Val(FLOAT, const=float(x))
    if isinstance(x, (tuple, list)) and len(x) == 3:
        return Val(VEC, const=tuple(float(c) for c in x))
    raise GNCompileError(f"unsupported constant {x!r}")


def annot_type(a, where, aliases: set[str]):
    """Type of a parameter / output annotation: float, int, bool or gn.tFloat ... gn.tGeometry."""
    if a is None:
        return FLOAT
    if isinstance(a, ast.Name) and a.id in PYTHON_TYPES:
        return PYTHON_TYPES[a.id]
    pub = namespace_member(a, aliases)
    if pub in TYPES:
        return TYPES[pub]
    alias = DEFAULT_ALIAS if DEFAULT_ALIAS in aliases else min(aliases)
    hint = ""
    if isinstance(a, ast.Name) and a.id in OLD_NAMES:
        hint = f" -- use {alias}.{OLD_NAMES[a.id]}"
    elif pub is not None:
        hint = f" -- types are {', '.join(f'{alias}.{t}' for t in TYPES)}"
    raise GNCompileError(f"unknown type annotation {ast.unparse(a)}{hint}", where)
